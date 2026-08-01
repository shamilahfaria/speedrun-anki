"""Generate recall cards and transfer probes from supplied source material.

Two paths, one output type:

* AI path -- a `CardProvider` proposes cards; each proposal is only accepted if
  its quote is a verbatim span of the source, which is what makes provenance
  correct rather than merely present.
* Offline path -- a deterministic extractive generator used whenever AI is
  disabled, keyless, or failing. Lower quality, still fully provenanced. The
  result is flagged `degraded=True`; nothing crashes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from speedrun_ai.cards import (
    PROBE_TAG,
    TOPIC_TAG_PREFIX,
    CardKind,
    GeneratedCard,
    Provenance,
    ProvenanceError,
    passage_index_for_offset,
    passage_spans,
    topic_tag,
)
from speedrun_ai.provider import (
    DEFAULT_MAX_PROBES,
    DEFAULT_MAX_RECALL,
    CardProvider,
    GenerationRequest,
    Suggestion,
    get_provider,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PROBE_TAG",
    "TOPIC_TAG_PREFIX",
    "CardKind",
    "GeneratedCard",
    "GenerationResult",
    "Provenance",
    "ProvenanceError",
    "generate_cards",
    "topic_tag",
]

_STOPWORDS = frozenset(
    """a an the of to in on at by for from with and or but if then than that
    this these those is are was were be been being it its as into onto over
    under between during each per not no can may might must should would could
    which who whom whose what when where why how one two both all any more most
    such only same so very just about above below after before again further
    does do did done has have had having they them their there here you your we
    our i he she his her""".split()
)


@dataclass(frozen=True)
class GenerationResult:
    """Cards plus an honest account of how they were produced."""

    cards: Tuple[GeneratedCard, ...]
    provider_name: str
    degraded: bool = False
    degraded_reason: str = ""
    rejected: int = 0
    rejection_reasons: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cards", tuple(self.cards))
        object.__setattr__(self, "rejection_reasons", tuple(self.rejection_reasons))

    @property
    def recall_cards(self) -> Tuple[GeneratedCard, ...]:
        return tuple(c for c in self.cards if c.kind is CardKind.RECALL)

    @property
    def probes(self) -> Tuple[GeneratedCard, ...]:
        return tuple(c for c in self.cards if c.kind is CardKind.PROBE)

    def as_notes(self) -> List[Dict[str, Any]]:
        return [card.as_note() for card in self.cards]


def generate_cards(
    source_text: str,
    source_id: str,
    topic: str,
    provider: Optional[CardProvider] = None,
    max_recall: int = DEFAULT_MAX_RECALL,
    max_probes: int = DEFAULT_MAX_PROBES,
) -> GenerationResult:
    """Generate cards for one piece of source material.

    Never raises on provider trouble: it degrades to the offline generator.
    """
    request = GenerationRequest(
        source_id=source_id,
        source_text=source_text,
        topic=topic,
        max_recall=max_recall,
        max_probes=max_probes,
    )
    if provider is None:
        provider = get_provider()

    if not provider.available:
        reason = provider.unavailable_reason or "AI provider unavailable"
        logger.info("Generating offline: %s", reason)
        return _offline_result(request, provider.name, reason)

    try:
        suggestions = provider.suggest_cards(request)
    except Exception as exc:
        reason = "provider %s failed (%s); used offline generation" % (
            provider.name,
            type(exc).__name__,
        )
        logger.warning("%s", reason)
        return _offline_result(request, provider.name, reason)

    cards, rejected, reasons = _cards_from_suggestions(request, suggestions)
    if not cards:
        reason = "provider %s produced no usable cards; used offline generation" % (
            provider.name,
        )
        logger.info("%s", reason)
        offline = _offline_result(request, provider.name, reason)
        return GenerationResult(
            cards=offline.cards,
            provider_name=provider.name,
            degraded=True,
            degraded_reason=reason,
            rejected=rejected,
            rejection_reasons=reasons,
        )

    return GenerationResult(
        cards=cards,
        provider_name=provider.name,
        degraded=False,
        degraded_reason="",
        rejected=rejected,
        rejection_reasons=reasons,
    )


# --- AI path ---------------------------------------------------------------


def _cards_from_suggestions(
    request: GenerationRequest, suggestions: Sequence[Suggestion]
) -> Tuple[Tuple[GeneratedCard, ...], int, Tuple[str, ...]]:
    cards: List[GeneratedCard] = []
    reasons: List[str] = []
    rejected = 0
    recall_used = 0
    probes_used = 0

    for suggestion in suggestions:
        if suggestion.kind is CardKind.PROBE:
            if probes_used >= request.max_probes:
                continue
        elif recall_used >= request.max_recall:
            continue
        try:
            card = GeneratedCard.from_source(
                front=suggestion.front,
                back=suggestion.back,
                kind=suggestion.kind,
                topic=request.topic,
                source_id=request.source_id,
                source_text=request.source_text,
                quote=suggestion.quote,
            )
        except (ProvenanceError, ValueError) as exc:
            rejected += 1
            reasons.append(str(exc))
            continue
        cards.append(card)
        if card.kind is CardKind.PROBE:
            probes_used += 1
        else:
            recall_used += 1

    return tuple(cards), rejected, tuple(reasons)


# --- offline path ----------------------------------------------------------


def _offline_result(
    request: GenerationRequest, provider_name: str, reason: str
) -> GenerationResult:
    cards = offline_cards(
        source_text=request.source_text,
        source_id=request.source_id,
        topic=request.topic,
        max_recall=request.max_recall,
        max_probes=request.max_probes,
    )
    return GenerationResult(
        cards=cards,
        provider_name=provider_name,
        degraded=True,
        degraded_reason=reason,
        rejected=0,
        rejection_reasons=(),
    )


def sentences_with_spans(text: str) -> List[Tuple[int, int, str]]:
    """Split into sentences, keeping exact offsets into `text`."""
    results: List[Tuple[int, int, str]] = []
    for p_start, p_end in passage_spans(text):
        passage = text[p_start:p_end]
        offset = 0
        for piece in re.split(r"(?<=[.!?])\s+", passage):
            start = passage.find(piece, offset)
            if start < 0 or not piece.strip():
                continue
            offset = start + len(piece)
            stripped = piece.strip()
            abs_start = p_start + start + piece.index(stripped)
            results.append((abs_start, abs_start + len(stripped), stripped))
    return results


def _key_term(sentence: str) -> Optional[str]:
    """Longest content word in the sentence; ties broken by first position."""
    best: Optional[str] = None
    for word in re.findall(r"[A-Za-z][A-Za-z\-']{2,}", sentence):
        if word.lower() in _STOPWORDS:
            continue
        if best is None or len(word) > len(best):
            best = word
    return best


def offline_cards(
    source_text: str,
    source_id: str,
    topic: str,
    max_recall: int = DEFAULT_MAX_RECALL,
    max_probes: int = DEFAULT_MAX_PROBES,
) -> Tuple[GeneratedCard, ...]:
    """Deterministic, no-AI card extraction.

    Recall cards blank out the most distinctive term of a sentence. Probes ask
    for a restatement plus a new example, which is a weaker transfer test than
    a model-written probe but still forces a change of surface form.
    """
    sentences = [s for s in sentences_with_spans(source_text) if len(s[2]) > 30]
    cards: List[GeneratedCard] = []

    for _, _, sentence in sentences[:max_recall]:
        term = _key_term(sentence)
        if not term:
            continue
        blanked = sentence.replace(term, "_____", 1)
        cards.append(
            GeneratedCard.from_source(
                front="Fill in the blank: %s" % blanked,
                back=term,
                kind=CardKind.RECALL,
                topic=topic,
                source_id=source_id,
                source_text=source_text,
                quote=sentence,
            )
        )

    # One probe per passage, so probes spread across the material.
    seen_passages: List[int] = []
    for start, _, sentence in sentences:
        if len(seen_passages) >= max_probes:
            break
        index = passage_index_for_offset(source_text, start)
        if index in seen_passages:
            continue
        seen_passages.append(index)
        cards.append(
            GeneratedCard.from_source(
                front=(
                    "In your own words, restate the idea below and give one new "
                    "example or application it would cover:\n%s" % sentence
                ),
                back=(
                    "Any restatement that preserves the meaning, plus a case not "
                    "mentioned in the source. Source says: %s" % sentence
                ),
                kind=CardKind.PROBE,
                topic=topic,
                source_id=source_id,
                source_text=source_text,
                quote=sentence,
            )
        )

    return tuple(cards)

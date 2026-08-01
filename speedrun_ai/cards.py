"""Card model with provenance that cannot be omitted.

The product invariant this module enforces: every generated card points at the
exact span of source material it came from. That is checked at construction
time, so an unprovenanced (or hallucinated) card cannot exist as an object --
there is no later validation pass to forget to run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

PROBE_TAG = "speedrun::probe"
TOPIC_TAG_PREFIX = "speedrun::topic::"


class CardKind(str, Enum):
    """Plain recall vs. transfer probe."""

    RECALL = "recall"
    PROBE = "probe"


class ProvenanceError(ValueError):
    """Raised when a card's link back to its source is missing or wrong."""


def topic_tag(topic: str) -> str:
    """`"Organic Chemistry"` -> `"speedrun::topic::organic_chemistry"`."""
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string")
    slug = re.sub(r"[^a-z0-9]+", "_", topic.strip().lower()).strip("_")
    if not slug:
        raise ValueError("topic %r has no usable characters" % (topic,))
    return TOPIC_TAG_PREFIX + slug


def passage_spans(text: str) -> List[Tuple[int, int]]:
    """Character spans of blank-line separated passages, in document order."""
    spans: List[Tuple[int, int]] = []
    position = 0
    for chunk in re.split(r"\n\s*\n", text):
        start = text.find(chunk, position)
        if start < 0:  # pragma: no cover - defensive
            continue
        spans.append((start, start + len(chunk)))
        position = start + len(chunk)
    return spans


def passage_index_for_offset(text: str, offset: int) -> int:
    for index, (start, end) in enumerate(passage_spans(text)):
        if start <= offset < end:
            return index
    return 0


def locate_quote(source_text: str, quote: str) -> Tuple[int, int]:
    """Return the span of `quote` inside `source_text`.

    Falls back to a whitespace-tolerant search, because a model may normalise
    line breaks when echoing a span back. The returned span always satisfies
    ``source_text[start:end]`` being real source text.
    """
    if not isinstance(source_text, str) or not source_text:
        raise ProvenanceError("source_text must be a non-empty string")
    if not isinstance(quote, str) or not quote.strip():
        raise ProvenanceError("quote must be a non-empty string")

    start = source_text.find(quote)
    if start >= 0:
        return start, start + len(quote)

    tolerant = r"\s+".join(re.escape(part) for part in quote.split())
    match = re.search(tolerant, source_text)
    if match:
        return match.start(), match.end()

    raise ProvenanceError("quote is not present in the source material: %r" % (quote,))


@dataclass(frozen=True)
class Provenance:
    """Source identifier plus an exact locator into that source."""

    source_id: str
    start: int
    end: int
    quote: str
    passage_index: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ProvenanceError("provenance requires a non-empty source_id")
        if not isinstance(self.quote, str) or not self.quote.strip():
            raise ProvenanceError("provenance requires a non-empty quote")
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise ProvenanceError("provenance offsets must be integers")
        if self.start < 0 or self.end < 0:
            raise ProvenanceError("provenance offsets must be non-negative")
        if self.end <= self.start:
            raise ProvenanceError(
                "provenance span must be non-empty (start=%d, end=%d)"
                % (self.start, self.end)
            )
        if self.end - self.start != len(self.quote):
            raise ProvenanceError(
                "provenance span length does not match the quote length"
            )
        if not isinstance(self.passage_index, int) or self.passage_index < 0:
            raise ProvenanceError("passage_index must be a non-negative integer")

    def verify_against(self, source_text: str) -> None:
        """Raise unless the recorded span really selects the recorded quote."""
        if not isinstance(source_text, str):
            raise ProvenanceError("source_text must be a string")
        if self.end > len(source_text):
            raise ProvenanceError(
                "provenance span runs past the end of the source material"
            )
        if source_text[self.start : self.end] != self.quote:
            raise ProvenanceError(
                "provenance span does not match the source material at "
                "[%d:%d]" % (self.start, self.end)
            )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "start": self.start,
            "end": self.end,
            "quote": self.quote,
            "passage_index": self.passage_index,
        }


@dataclass(frozen=True)
class GeneratedCard:
    """A card that is, by construction, traceable to its source span."""

    front: str
    back: str
    kind: CardKind
    topic: str
    provenance: Provenance  # no default: omitting it is a TypeError
    extra_tags: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ProvenanceError(
                "every card requires a Provenance instance, got %r"
                % (type(self.provenance).__name__,)
            )
        for name in ("front", "back", "topic"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("card %s must be a non-empty string" % name)
        object.__setattr__(self, "kind", CardKind(self.kind))
        object.__setattr__(self, "extra_tags", tuple(self.extra_tags))

    @classmethod
    def from_source(
        cls,
        *,
        front: str,
        back: str,
        kind: CardKind,
        topic: str,
        source_id: str,
        source_text: str,
        quote: str,
        extra_tags: Tuple[str, ...] = (),
    ) -> "GeneratedCard":
        """Build a card, deriving the locator from the source text itself.

        Raises ProvenanceError if `quote` does not occur in `source_text`,
        which is what stops an invented span from becoming a card.
        """
        start, end = locate_quote(source_text, quote)
        provenance = Provenance(
            source_id=source_id,
            start=start,
            end=end,
            quote=source_text[start:end],
            passage_index=passage_index_for_offset(source_text, start),
        )
        card = cls(
            front=front,
            back=back,
            kind=kind,
            topic=topic,
            provenance=provenance,
            extra_tags=tuple(extra_tags),
        )
        card.verify_against(source_text)
        return card

    @property
    def tags(self) -> Tuple[str, ...]:
        tags = [topic_tag(self.topic)]
        if self.kind is CardKind.PROBE:
            tags.append(PROBE_TAG)
        tags.extend(self.extra_tags)
        seen: List[str] = []
        for tag in tags:
            if tag not in seen:
                seen.append(tag)
        return tuple(seen)

    def verify_against(self, source_text: str) -> None:
        self.provenance.verify_against(source_text)

    def as_note(self) -> Dict[str, Any]:
        """Flat dict for the Anki note layer (no pylib import on purpose)."""
        return {
            "front": self.front,
            "back": self.back,
            "kind": self.kind.value,
            "tags": list(self.tags),
            "source_id": self.provenance.source_id,
            "source_start": self.provenance.start,
            "source_end": self.provenance.end,
            "source_quote": self.provenance.quote,
            "passage_index": self.provenance.passage_index,
        }

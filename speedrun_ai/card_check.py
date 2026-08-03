"""AI card check: 50 generated cards against a 50-pair gold set, three buckets.

What this evaluates
-------------------
Generate 50 cards from one real source document with the existing
`generate_cards()` pipeline, then sort every card into exactly one of three
buckets:

    correct-and-useful  /  wrong  /  correct-but-bad-teaching

The third bucket is the point of the exercise. A generator that never states
a falsehood can still produce cards that teach nothing -- a blank over a
throwaway word, a stem that cannot be answered without the source in front of
you, an "answer" that is a whole sentence copied back. Scoring only for
correctness scores that failure as a success, which is why "wrong" and "bad
teaching" are separated here rather than pooled into "not good".

The cutoff, set before looking
------------------------------
The pass threshold below was written into this file before a single card was
generated and before any result existed -- that is the whole value of a
cutoff. A threshold chosen after seeing the numbers measures nothing except
the author's willingness to pass. The two constants
`PASS_THRESHOLD_CORRECT_AND_USEFUL` and `MAX_ACCEPTABLE_WRONG_RATE` are
printed in every report, next to the result they judge.

Run it::

    python -m speedrun_ai.card_check                      # live generation + LLM grading
    python -m speedrun_ai.card_check --grader heuristic   # offline, deterministic
    python -m speedrun_ai.card_check --offline-generation  # no network at all
    python -m speedrun_ai.card_check --json

Grading honesty: with `--grader llm` the grader is Gemini. **LLM grading of
LLM output is a weak evaluation** -- the grader shares failure modes with the
generator, and it is not human review. The report says so on every LLM run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from speedrun_ai.cards import CardKind, GeneratedCard, Provenance
from speedrun_ai.generate import generate_cards
from speedrun_ai.provider import (
    API_KEY_ENV,
    CardProvider,
    GeminiProvider,
    NullProvider,
    ProviderError,
)
from speedrun_ai.retrieval import Bm25Retriever, Passage

# Model this harness generates and grades with. Named here rather than taken
# from `provider.DEFAULT_MODEL` so the harness pins something it has actually
# called, not merely something `models.list()` advertises.
#
# What was observed on 2026-08-03 with the key in this environment:
#   gemini-2.5-flash-lite  -- listed by models.list(), but generate_content
#       returns 404 "no longer available to new users". Listing is not
#       evidence of callability. This was the original package default, and
#       every generation call through it degraded silently to the offline
#       extractor, which stops the run being an AI card check at all.
#   gemini-3.5-flash-lite  -- callable. It produced the 50-card deck in
#       results/card_check_deck.json. It later returned 429, which is quota
#       exhaustion on the key, not a bad model id.
#   gemini-flash-lite-latest -- callable; an alias, so it survives the next
#       retirement. Used here for that reason.
CARD_CHECK_MODEL = "gemini-flash-lite-latest"

# ---------------------------------------------------------------------------
# THE CUTOFF. Set before generating a single card and before seeing a single
# grade, on 2026-08-03. Not revised afterwards. If a future run wants a
# different bar, change it and re-baseline, but say that is what happened.
# ---------------------------------------------------------------------------
CUTOFF_SET_BEFORE_RESULTS_NOTE = (
    "PASS CUTOFF DECLARED BEFORE ANY CARD WAS GENERATED OR GRADED: a run passes "
    "only if at least 70% of the 50 cards are correct-and-useful AND at most "
    "10% are wrong. Written into this file before any result existed and not "
    "revised since."
)

# At least this share of the 50 cards must land in correct-and-useful.
PASS_THRESHOLD_CORRECT_AND_USEFUL = 0.70

# And no more than this share may be wrong. A deck can clear the first bar and
# still fail here: a wrong card on a spaced-repetition schedule teaches the
# error, so wrongness gets its own ceiling rather than being traded off.
MAX_ACCEPTABLE_WRONG_RATE = 0.10

# Cutoff of the fixture data (source document + gold set), not a model
# knowledge cutoff.
DATA_CUTOFF = "2026-08-03"

TARGET_CARDS = 50

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GOLD_PATH = FIXTURES_DIR / "gold" / "gold_set.json"
SOURCE_MANIFEST = FIXTURES_DIR / "source" / "manifest.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
DECK_CACHE = RESULTS_DIR / "card_check_deck.json"

LLM_GRADING_CAVEAT = (
    "**GRADED BY AN LLM, NOT BY A HUMAN. LLM grading of LLM output is a weak "
    "evaluation: the grader shares training data, blind spots and failure "
    "modes with the generator, so it is systematically likelier to accept the "
    "kind of mistake the generator makes. Treat these counts as a smoke test, "
    "not human review.**"
)


class GradingError(RuntimeError):
    """A card could not be graded. Never silently bucketed."""


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _http_status(exc: Exception) -> str:
    """The HTTP status in an SDK exception, or "" if there is none.

    Only the status code is lifted out, never the message body: an SDK error
    string can echo request metadata, and the point here is the one field that
    tells a rerunner what to do differently (429 wait, 404 change the model).
    """
    for attribute in ("code", "status_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return str(value)
    match = re.search(r"\b([45]\d\d)\b", str(exc))
    return match.group(1) if match else ""


# --- the rubric -------------------------------------------------------------


class Bucket(str, Enum):
    CORRECT_AND_USEFUL = "correct-and-useful"
    WRONG = "wrong"
    CORRECT_BUT_BAD_TEACHING = "correct-but-bad-teaching"


BUCKET_DEFINITIONS: Dict[Bucket, str] = {
    Bucket.WRONG: (
        "The card states something false, contradicts the gold set or the cited "
        "source span, answers a different question than the one asked, or asserts "
        "material that is not supported anywhere in the source. Any factual error "
        "puts the card here regardless of how well written it is, because a wrong "
        "card on a repetition schedule installs the error by rehearsal."
    ),
    Bucket.CORRECT_BUT_BAD_TEACHING: (
        "Everything asserted is true, but the card fails as an item of instruction: "
        "the front cannot be answered without the source in view (dangling 'this "
        "process', no named subject), the answer is given away in the question, the "
        "blank falls on a throwaway word rather than the load-bearing idea, the back "
        "is a whole sentence copied back instead of a discrete fact, or the card "
        "bundles several ideas that should be tested separately."
    ),
    Bucket.CORRECT_AND_USEFUL: (
        "The card is factually correct against the gold set and the cited source "
        "span, the front is self-contained and answerable by someone who knows the "
        "material and has never seen the source, the answer is the load-bearing "
        "idea rather than a fragment or a restatement, and it tests exactly one "
        "thing. This is the only bucket that counts toward the pass threshold."
    ),
}

# Precedence: a card that is both wrong and badly taught is counted wrong.
# The buckets are a partition, so the order settles the overlaps.
BUCKET_PRECEDENCE: Tuple[Bucket, ...] = (
    Bucket.WRONG,
    Bucket.CORRECT_BUT_BAD_TEACHING,
    Bucket.CORRECT_AND_USEFUL,
)


@dataclass(frozen=True)
class Grade:
    bucket: Bucket
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "bucket", Bucket(self.bucket))


# --- gold set ---------------------------------------------------------------


@dataclass(frozen=True)
class GoldPair:
    id: str
    section: str
    question: str
    answer: str


@dataclass(frozen=True)
class GoldSet:
    pairs: Tuple[GoldPair, ...]
    data_cutoff: str
    source_id: str = ""
    authoring_note: str = ""


def load_gold(path: Optional[Path] = None) -> GoldSet:
    raw = json.loads(Path(path or GOLD_PATH).read_text(encoding="utf-8"))
    pairs = tuple(
        GoldPair(
            id=entry["id"],
            section=entry.get("section", ""),
            question=entry["question"],
            answer=entry["answer"],
        )
        for entry in raw["pairs"]
    )
    ids = [p.id for p in pairs]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate gold pair ids in %s" % (path or GOLD_PATH))
    return GoldSet(
        pairs=pairs,
        data_cutoff=raw["data_cutoff"],
        source_id=raw.get("source_id", ""),
        authoring_note=raw.get("authoring_note", ""),
    )


# --- source document --------------------------------------------------------


@dataclass(frozen=True)
class Section:
    index: int
    title: str
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class SourceDoc:
    source_id: str
    text: str
    sections: Tuple[Section, ...]
    data_cutoff: str
    cutoff_note: str = ""


def load_source(manifest_path: Optional[Path] = None) -> SourceDoc:
    manifest_path = Path(manifest_path or SOURCE_MANIFEST)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    text = (manifest_path.parent / manifest["file"]).read_text(encoding="utf-8")
    marker = manifest.get("section_marker", "## ")

    starts = [m.start() for m in re.finditer(r"^%s" % re.escape(marker), text, re.M)]
    if not starts:
        raise ValueError("no sections found in %s" % manifest["file"])
    sections: List[Section] = []
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else len(text)
        chunk = text[start:stop].rstrip()
        title = text[start:stop].splitlines()[0][len(marker) :].strip()
        sections.append(
            Section(
                index=index,
                title=title,
                text=chunk,
                start=start,
                end=start + len(chunk),
            )
        )
    return SourceDoc(
        source_id=manifest["source_id"],
        text=text,
        sections=tuple(sections),
        data_cutoff=manifest["data_cutoff"],
        cutoff_note=manifest.get("cutoff_note", ""),
    )


# --- generation -------------------------------------------------------------


@dataclass(frozen=True)
class Deck:
    cards: Tuple[GeneratedCard, ...]
    provider_name: str
    model: str
    degraded: bool
    degraded_reason: str
    rejected: int
    source_id: str
    data_cutoff: str

    @property
    def fingerprint(self) -> str:
        """Stable id for this exact set of cards, so a stale grade cache is
        detected instead of quietly reused."""
        digest = hashlib.blake2b(digest_size=16)
        for card in self.cards:
            digest.update(("%s\x1f%s\x1e" % (card.front, card.back)).encode("utf-8"))
        return digest.hexdigest()


def generate_deck(
    source: SourceDoc,
    provider: Optional[CardProvider] = None,
    target: int = TARGET_CARDS,
    per_section_recall: int = 6,
    per_section_probes: int = 2,
    model: str = CARD_CHECK_MODEL,
) -> Deck:
    """Generate `target` cards from one document, spread evenly over sections.

    Each section is generated separately and asked for more cards than its
    share, then cards are taken round-robin across sections until the target is
    met. That keeps coverage even instead of letting the first two sections
    supply the whole deck.

    Provenance offsets from `generate_cards` are relative to the section text,
    so they are rebased onto the whole document here; every stored card's span
    indexes the full source.
    """
    per_section: List[List[GeneratedCard]] = []
    degraded = False
    reasons: List[str] = []
    rejected = 0
    provider_name = ""

    for section in source.sections:
        result = generate_cards(
            source_text=section.text,
            source_id="%s#s%02d" % (source.source_id, section.index),
            topic=section.title,
            provider=provider,
            max_recall=per_section_recall,
            max_probes=per_section_probes,
        )
        provider_name = result.provider_name
        rejected += result.rejected
        if result.degraded:
            degraded = True
            if result.degraded_reason and result.degraded_reason not in reasons:
                reasons.append(result.degraded_reason)
        per_section.append([_rebase(card, section, source) for card in result.cards])

    picked: List[GeneratedCard] = []
    depth = 0
    while len(picked) < target:
        added = False
        for bucket in per_section:
            if depth < len(bucket):
                picked.append(bucket[depth])
                added = True
                if len(picked) == target:
                    break
        if not added:
            break
        depth += 1

    if len(picked) < target:
        raise GradingError(
            "only %d cards could be generated from %d sections (wanted %d). "
            "Not padding the deck: a short deck would change every denominator "
            "in the report."
            % (len(picked), len(source.sections), target)
        )

    return Deck(
        cards=tuple(picked),
        provider_name=provider_name,
        model=model if not degraded else "",
        degraded=degraded,
        degraded_reason="; ".join(reasons),
        rejected=rejected,
        source_id=source.source_id,
        data_cutoff=source.data_cutoff,
    )


def build_provider() -> CardProvider:
    """The provider this harness generates with.

    Not `get_provider()`: that one uses the package default model, which is
    retired upstream, so every call would degrade to offline extraction and
    the report would be measuring the extractor instead of the AI.
    """
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        return NullProvider("no %s key found in the environment" % API_KEY_ENV)
    return GeminiProvider(model=CARD_CHECK_MODEL, api_key=key)


def _rebase(card: GeneratedCard, section: Section, source: SourceDoc) -> GeneratedCard:
    """Re-express a section-relative span as a span into the whole document."""
    start = section.start + card.provenance.start
    end = section.start + card.provenance.end
    if source.text[start:end] != card.provenance.quote:  # pragma: no cover
        raise GradingError(
            "rebased provenance does not match the document for card %r"
            % (card.front[:60],)
        )
    provenance = Provenance(
        source_id=source.source_id,
        start=start,
        end=end,
        quote=card.provenance.quote,
        passage_index=section.index,
    )
    return GeneratedCard(
        front=card.front,
        back=card.back,
        kind=card.kind,
        topic=card.topic,
        provenance=provenance,
        extra_tags=card.extra_tags,
    )


def make_card(
    front: str, back: str, kind: CardKind = CardKind.RECALL, topic: str = "Test"
) -> GeneratedCard:
    """Build a standalone card whose provenance quote is its own answer.

    For exercising the rubric on hand-written examples; real decks come from
    `generate_deck`.
    """
    return GeneratedCard.from_source(
        front=front,
        back=back,
        kind=kind,
        topic=topic,
        source_id="inline",
        source_text=back,
        quote=back,
    )


def save_deck(deck: Deck, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "data_cutoff": deck.data_cutoff,
        "source_id": deck.source_id,
        "provider_name": deck.provider_name,
        "model": deck.model,
        "degraded": deck.degraded,
        "degraded_reason": deck.degraded_reason,
        "rejected": deck.rejected,
        "fingerprint": deck.fingerprint,
        "cards": [
            {
                "front": card.front,
                "back": card.back,
                "kind": card.kind.value,
                "topic": card.topic,
                "provenance": card.provenance.as_dict(),
            }
            for card in deck.cards
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_deck(path: Path) -> Deck:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cards = tuple(
        GeneratedCard(
            front=entry["front"],
            back=entry["back"],
            kind=CardKind(entry["kind"]),
            topic=entry["topic"],
            provenance=Provenance(**entry["provenance"]),
        )
        for entry in raw["cards"]
    )
    return Deck(
        cards=cards,
        provider_name=raw["provider_name"],
        model=raw.get("model", ""),
        degraded=raw.get("degraded", False),
        degraded_reason=raw.get("degraded_reason", ""),
        rejected=raw.get("rejected", 0),
        source_id=raw["source_id"],
        data_cutoff=raw["data_cutoff"],
    )


# --- matching a card to the gold set ----------------------------------------


def gold_references(gold: GoldSet, card: GeneratedCard, k: int = 3) -> List[GoldPair]:
    """The gold pairs most likely to cover this card's material.

    BM25 over the gold questions and answers, reusing the retriever already in
    this package. These are what the grader checks the card against, so a card
    is never judged against the whole 50-pair set at once.
    """
    retriever = Bm25Retriever()
    retriever.index(
        [
            Passage(id=pair.id, text="%s %s" % (pair.question, pair.answer))
            for pair in gold.pairs
        ]
    )
    by_id = {pair.id: pair for pair in gold.pairs}
    query = "%s %s %s" % (card.front, card.back, card.provenance.quote)
    return [by_id[hit.passage_id] for hit in retriever.search(query, k=k)]


# --- graders ----------------------------------------------------------------


class Grader(ABC):
    name = "grader"
    is_llm = False
    limitation_note = ""

    @abstractmethod
    def describe(self) -> str: ...

    @abstractmethod
    def grade(self, card: GeneratedCard, references: Sequence[GoldPair]) -> Grade: ...


_ANAPHORIC = (
    "this process",
    "this reaction",
    "this enzyme",
    "this molecule",
    "this pathway",
    "this structure",
    "the above",
    "the following",
    "it is inhibited",
    "they are",
)

_HEURISTIC_STOPWORDS = frozenset(
    """the and for that with from this these those which what when where whys
    into onto over under about above below than then there here they them their
    have has had been being are was were will would could should must can may
    not but its it's your you our per each some such only same both all any
    more most one two both fill blank word words given give name state""".split()
)


# Words that make a stem depend on a sentence the learner cannot see.
_DEMONSTRATIVE_OPENERS = frozenset(
    "that this these those it its they their such he she".split()
)


def _content_words(text: str, min_length: int = 4) -> frozenset:
    """Content words, splitting on hyphens.

    Hyphens split because a cloze answer is often one component of a
    hyphenated term in the source ("bisphosphate" out of
    "fructose-2,6-bisphosphate"). Keeping the term whole made those answers
    look absent from their own source span, which showed up as false entries
    in the wrong bucket.
    """
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(
        t for t in tokens if len(t) >= min_length and t not in _HEURISTIC_STOPWORDS
    )


def _numbers(text: str) -> frozenset:
    """Numbers that carry meaning, ignoring ones embedded in chemical names."""
    return frozenset(
        re.findall(r"(?<![A-Za-z0-9\-,.])(\d+(?:\.\d+)?)(?![\-,.]?\d)", text)
    )


class HeuristicGrader(Grader):
    """Deterministic, offline, mechanical. Grades structure, not truth.

    Every rule below is a syntactic check on the card and its matched gold
    pairs. That is enough to catch the pedagogy failures reliably, and it
    catches only the mechanically visible kind of wrongness (a number that
    contradicts the gold answer on the same topic, or an answer with nothing in
    common with the span it claims to come from).
    """

    name = "heuristic"
    is_llm = False
    limitation_note = (
        "The heuristic grader cannot verify facts. It detects only mechanically "
        "visible wrongness -- a numeric contradiction with a matched gold answer, "
        "or an answer unsupported by the span the card cites -- so it will "
        "under-count the wrong bucket. Its pedagogy checks are reliable; its "
        "correctness checks are a floor, not a verdict."
    )

    def describe(self) -> str:
        return "HeuristicGrader (deterministic, offline, structural)"

    def grade(self, card: GeneratedCard, references: Sequence[GoldPair]) -> Grade:
        for bucket in BUCKET_PRECEDENCE:
            if bucket is Bucket.WRONG:
                reason = self._wrong_reason(card, references)
            elif bucket is Bucket.CORRECT_BUT_BAD_TEACHING:
                reason = self._bad_teaching_reason(card)
            else:
                reason = "passes every mechanical check applied"
            if reason:
                return Grade(bucket=bucket, reason=reason)
        raise GradingError("no bucket applied")  # pragma: no cover - unreachable

    def _wrong_reason(
        self, card: GeneratedCard, references: Sequence[GoldPair]
    ) -> str:
        back_numbers = _numbers(card.back)
        # Topic match is judged on the whole card against the whole gold pair:
        # the question carries most of the shared vocabulary, and an answer
        # alone is often too short to match anything.
        card_words = _content_words(
            "%s %s" % (card.front, card.back), min_length=3
        )
        for pair in references:
            gold_numbers = _numbers(pair.answer)
            gold_words = _content_words(
                "%s %s" % (pair.question, pair.answer), min_length=3
            )
            if not back_numbers or not gold_numbers:
                continue
            union = card_words | gold_words
            if not union:
                continue
            if len(card_words & gold_words) / float(len(union)) < 0.25:
                continue  # different material; a number clash means nothing
            if back_numbers.isdisjoint(gold_numbers):
                return (
                    "numeric contradiction: card says %s where gold pair %s on the "
                    "same material says %s"
                    % (sorted(back_numbers), pair.id, sorted(gold_numbers))
                )
        back_words = _content_words(card.back)
        quote_words = _content_words(card.provenance.quote)
        if back_words and quote_words and not (back_words & quote_words):
            return (
                "the answer shares no content word with the source span the card "
                "cites, so it is not supported by its own provenance"
            )
        return ""

    def _bad_teaching_reason(self, card: GeneratedCard) -> str:
        front_lower = card.front.lower()
        for phrase in _ANAPHORIC:
            if phrase in front_lower:
                return (
                    "the front refers to %r without naming it, so it cannot be "
                    "answered without the source in view" % phrase
                )
        stem = re.sub(r"^[^:?]{0,40}:\s*", "", card.front.strip())
        opener = re.findall(r"[a-z]+", stem.lower()[:20])
        if opener and opener[0] in _DEMONSTRATIVE_OPENERS:
            return (
                "the stem opens with %r and never names its subject, so it can "
                "only be answered with the previous sentence in view" % opener[0]
            )
        if len(card.front.split()) < 5:
            return "the front is too short to pose an answerable question"
        back_words = _content_words(card.back, min_length=5)
        front_words = _content_words(card.front, min_length=5)
        if back_words and back_words <= front_words:
            return "the answer appears in the question, so the card tests nothing"
        if card.kind is CardKind.RECALL and card.back.strip() == card.provenance.quote.strip():
            if len(card.back.split()) >= 20:
                return (
                    "the answer is a whole source sentence copied back rather than "
                    "a discrete fact to be recalled"
                )
        if "_____" in card.front and len(card.back.split()) == 1:
            raw_word = card.back.strip().strip(".,;:")
            blank_word = raw_word.lower()
            # Short ALL-CAPS answers (ATP, GTP, NAD) are load-bearing, not
            # throwaway; length alone is the wrong test for a cloze answer.
            trivially_short = len(blank_word) <= 3 and raw_word.islower()
            if trivially_short or blank_word in _HEURISTIC_STOPWORDS:
                return (
                    "the blank falls on a throwaway word (%r), not on the "
                    "load-bearing idea" % card.back.strip()
                )
        if card.front.count("?") >= 2:
            return "the front bundles several questions that should be separate cards"
        return ""


GRADER_PROMPT = """You are grading flashcards for an MCAT study tool.

Put the card in EXACTLY ONE bucket:

1. "wrong" -- {wrong}
2. "correct-but-bad-teaching" -- {bad}
3. "correct-and-useful" -- {good}

If a card is both wrong and badly taught, it is "wrong".

REFERENCE ANSWER KEY (hand-written; treat as authoritative):
{references}

SOURCE SPAN THE CARD CITES (verbatim from the source document):
{quote}

CARD
front: {front}
back: {back}

Return ONLY JSON: {{"bucket": "...", "reason": "one sentence"}}
"""


class LlmGrader(Grader):
    """Gemini as the grader. NETWORK PATH.

    This is the weakest link in the harness and is labelled as such everywhere
    it is used: the same family of model that wrote the cards is judging them.
    """

    name = "llm-gemini"
    is_llm = True
    limitation_note = LLM_GRADING_CAVEAT

    def __init__(
        self,
        model: str = CARD_CHECK_MODEL,
        api_key: Optional[str] = None,
        retries: int = 5,
        retry_delay: float = 12.0,
        pace_seconds: float = 4.5,
        sleep: Optional[Any] = None,
    ):
        self.model = model
        self.__api_key = (
            api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        ).strip()
        self.retries = max(1, int(retries))
        # The API answers a 429 with a retryDelay of about 11 seconds, so the
        # backoff starts above that rather than below it.
        self.retry_delay = float(retry_delay)
        # Spacing between calls. Grading 50 cards back to back exceeds the
        # free tier's per-minute allowance partway through; pacing is what
        # lets a 50-card run complete at all.
        self.pace_seconds = float(pace_seconds)
        self._sleep = sleep if sleep is not None else _default_sleep
        self._called_before = False
        self._client: Any = None

    def describe(self) -> str:
        return "LlmGrader(model=%s, key=%s)" % (
            self.model,
            "<set:redacted>" if self.__api_key else "<unset>",
        )

    def __repr__(self) -> str:  # never leak the key
        return self.describe()

    __str__ = __repr__

    def _load_client(self) -> Any:
        if self._client is None:
            if not self.__api_key:
                raise ProviderError(
                    "no %s in the environment; cannot grade with Gemini" % API_KEY_ENV
                )
            from google import genai  # lazy on purpose

            self._client = genai.Client(api_key=self.__api_key)
        return self._client

    def grade(self, card: GeneratedCard, references: Sequence[GoldPair]) -> Grade:
        prompt = GRADER_PROMPT.format(
            wrong=BUCKET_DEFINITIONS[Bucket.WRONG],
            bad=BUCKET_DEFINITIONS[Bucket.CORRECT_BUT_BAD_TEACHING],
            good=BUCKET_DEFINITIONS[Bucket.CORRECT_AND_USEFUL],
            references="\n".join(
                "- Q: %s\n  A: %s" % (p.question, p.answer) for p in references
            ),
            quote=card.provenance.quote,
            front=card.front,
            back=card.back,
        )
        # Retry transient quota errors. Grading 50 cards is 50 sequential
        # calls, which trips a free-tier rate limit partway through, and a
        # partial grading is useless because it changes every denominator.
        response = None
        for attempt in range(1, self.retries + 1):
            if self._called_before and self.pace_seconds > 0:
                self._sleep(self.pace_seconds)
            self._called_before = True
            try:
                client = self._load_client()
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={
                        "temperature": 0.0,
                        "response_mime_type": "application/json",
                    },
                )
                break
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001 - reclassified below
                status = _http_status(exc)
                transient = status in ("429", "500", "502", "503", "504")
                if not transient or attempt >= self.retries:
                    raise GradingError(
                        "Gemini grading request failed after %d attempt(s): %s "
                        "(HTTP %s). 429 means the key's quota is exhausted, which "
                        "is a different problem from a retired model id (404)."
                        % (attempt, type(exc).__name__, status or "unknown")
                    ) from None
                self._sleep(self.retry_delay * attempt)
        text = getattr(response, "text", None)
        if not text:
            raise GradingError("Gemini returned an empty grading response")
        return parse_grade(text)


def parse_grade(text: str) -> Grade:
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        payload = json.loads(cleaned)
    except ValueError:
        raise GradingError("grader returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise GradingError("grader returned an unexpected JSON shape")
    raw_bucket = str(payload.get("bucket", "")).strip().lower()
    try:
        bucket = Bucket(raw_bucket)
    except ValueError:
        raise GradingError("grader returned an unknown bucket %r" % raw_bucket) from None
    return Grade(bucket=bucket, reason=str(payload.get("reason", "")).strip())


# --- report -----------------------------------------------------------------


@dataclass(frozen=True)
class GradedCard:
    front: str
    back: str
    kind: str
    topic: str
    source_start: int
    source_end: int
    quote: str
    bucket: Bucket
    reason: str
    reference_ids: Tuple[str, ...]


@dataclass(frozen=True)
class CardCheckReport:
    grades: Tuple[GradedCard, ...]
    counts: Dict[Bucket, int]
    grader_name: str
    grader_description: str
    grader_is_llm: bool
    grader_limitation_note: str
    provider_name: str
    model: str
    degraded: bool
    degraded_reason: str
    rejected: int
    source_id: str
    data_cutoff: str
    gold_size: int
    pass_threshold: float = PASS_THRESHOLD_CORRECT_AND_USEFUL
    max_wrong_rate: float = MAX_ACCEPTABLE_WRONG_RATE
    deck_from_cache: bool = False

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def percentages(self) -> Dict[Bucket, float]:
        total = float(self.total or 1)
        return {b: 100.0 * self.counts[b] / total for b in Bucket}

    @property
    def passed(self) -> bool:
        pct = self.percentages
        return (
            pct[Bucket.CORRECT_AND_USEFUL] / 100.0 >= self.pass_threshold
            and pct[Bucket.WRONG] / 100.0 <= self.max_wrong_rate
        )

    @property
    def verdict(self) -> str:
        pct = self.percentages
        useful_ok = pct[Bucket.CORRECT_AND_USEFUL] / 100.0 >= self.pass_threshold
        wrong_ok = pct[Bucket.WRONG] / 100.0 <= self.max_wrong_rate
        if useful_ok and wrong_ok:
            return "PASS against the pre-declared cutoff."
        failures = []
        if not useful_ok:
            failures.append(
                "correct-and-useful %.1f%% is below the %.0f%% floor"
                % (pct[Bucket.CORRECT_AND_USEFUL], self.pass_threshold * 100)
            )
        if not wrong_ok:
            failures.append(
                "wrong %.1f%% is above the %.0f%% ceiling"
                % (pct[Bucket.WRONG], self.max_wrong_rate * 100)
            )
        return "FAIL against the pre-declared cutoff: " + "; ".join(failures) + "."

    def to_dict(self) -> Dict[str, Any]:
        """Stable dict. Deliberately contains no timestamp."""
        pct = self.percentages
        return {
            "data_cutoff": self.data_cutoff,
            "source_id": self.source_id,
            "cards_graded": self.total,
            "gold_pairs": self.gold_size,
            "cutoff": {
                "note": CUTOFF_SET_BEFORE_RESULTS_NOTE,
                "pass_threshold_correct_and_useful": self.pass_threshold,
                "max_acceptable_wrong_rate": self.max_wrong_rate,
            },
            "generation": {
                "provider": self.provider_name,
                "model": self.model,
                "degraded": self.degraded,
                "degraded_reason": self.degraded_reason,
                "suggestions_rejected_for_bad_provenance": self.rejected,
                "deck_from_cache": self.deck_from_cache,
            },
            "grader": {
                "name": self.grader_name,
                "description": self.grader_description,
                "is_llm": self.grader_is_llm,
                "limitation_note": self.grader_limitation_note,
                "human_review": False,
            },
            "buckets": {
                bucket.value: {
                    "definition": BUCKET_DEFINITIONS[bucket],
                    "count": self.counts[bucket],
                    "percent": round(pct[bucket], 4),
                }
                for bucket in BUCKET_PRECEDENCE
            },
            "passed": self.passed,
            "verdict": self.verdict,
            "cards": [
                {
                    "front": g.front,
                    "back": g.back,
                    "kind": g.kind,
                    "topic": g.topic,
                    "bucket": g.bucket.value,
                    "reason": g.reason,
                    "source_span": [g.source_start, g.source_end],
                    "gold_references": list(g.reference_ids),
                }
                for g in self.grades
            ],
        }

    def format_text(self) -> str:
        pct = self.percentages
        lines: List[str] = []
        lines.append("Speedrun AI card check -- 50 generated cards vs a 50-pair gold set")
        lines.append("=" * 72)
        lines.append("Data cutoff: %s (source document and gold set frozen on this date)" % self.data_cutoff)
        lines.append("Source: %s | Gold pairs: %d" % (self.source_id, self.gold_size))
        lines.append(
            "Generation: provider=%s model=%s%s"
            % (
                self.provider_name,
                self.model or "(none: offline extraction)",
                " [FROM CACHE]" if self.deck_from_cache else "",
            )
        )
        if self.degraded:
            lines.append("  DEGRADED: %s" % self.degraded_reason)
            lines.append(
                "  **THESE CARDS DID NOT COME FROM THE AI PATH.** They were "
                "produced by the deterministic offline extractor after the "
                "provider was unavailable, so the counts below describe that "
                "extractor and say nothing about the model's card quality."
            )
        if self.rejected:
            lines.append(
                "  %d suggestions rejected before grading because their quote was "
                "not verbatim in the source." % self.rejected
            )
        lines.append("Grader: %s" % self.grader_description)
        lines.append("")
        lines.append(CUTOFF_SET_BEFORE_RESULTS_NOTE)
        lines.append("")
        if self.grader_is_llm:
            lines.append(LLM_GRADING_CAVEAT)
        else:
            lines.append(
                "Grading was mechanical and deterministic, not human review. "
                + self.grader_limitation_note
            )
        lines.append("")
        header = "%-28s %7s %9s" % ("bucket", "count", "percent")
        lines.append(header)
        lines.append("-" * len(header))
        for bucket in BUCKET_PRECEDENCE:
            lines.append(
                "%-28s %7d %8.1f%%"
                % (bucket.value, self.counts[bucket], pct[bucket])
            )
        lines.append("-" * len(header))
        lines.append("%-28s %7d %8.1f%%" % ("total", self.total, sum(pct.values())))
        lines.append("")
        lines.append(
            "Cutoff: correct-and-useful must be at least %.0f%% (got %.1f%%); "
            "wrong must be at most %.0f%% (got %.1f%%)."
            % (
                self.pass_threshold * 100,
                pct[Bucket.CORRECT_AND_USEFUL],
                self.max_wrong_rate * 100,
                pct[Bucket.WRONG],
            )
        )
        lines.append(self.verdict)
        lines.append("")
        lines.append("Bucket definitions used")
        lines.append("-" * 23)
        for bucket in BUCKET_PRECEDENCE:
            lines.append("%s:" % bucket.value)
            for chunk in _wrap(BUCKET_DEFINITIONS[bucket], 72):
                lines.append("  " + chunk)
        lines.append("")
        lines.append("Cards not in correct-and-useful")
        lines.append("-" * 31)
        listed = 0
        for graded in self.grades:
            if graded.bucket is Bucket.CORRECT_AND_USEFUL:
                continue
            listed += 1
            lines.append("[%s] %s" % (graded.bucket.value, graded.front.strip()[:96]))
            lines.append("    answer: %s" % graded.back.strip()[:96])
            lines.append("    reason: %s" % graded.reason.strip()[:150])
        if not listed:
            lines.append("(none)")
        return "\n".join(lines)


def _wrap(text: str, width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        if current and sum(len(w) + 1 for w in current) + len(word) > width:
            lines.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _card_key(card: GeneratedCard) -> str:
    return hashlib.blake2b(
        ("%s\x1f%s" % (card.front, card.back)).encode("utf-8"), digest_size=12
    ).hexdigest()


class GradeCache:
    """Grades already obtained, keyed by card and by grader.

    Fifty sequential LLM calls on a rate-limited key do not always finish.
    Without this, a 429 on card 41 throws away forty completed grades and the
    harness is effectively unrunnable. Entries are namespaced by grader name so
    heuristic grades never masquerade as LLM grades.
    """

    def __init__(self, path: Path, grader_name: str):
        self.path = Path(path)
        self.grader_name = grader_name
        self._entries: Dict[str, Grade] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("grader") == grader_name:
                for key, value in raw.get("grades", {}).items():
                    self._entries[key] = Grade(
                        bucket=Bucket(value["bucket"]), reason=value.get("reason", "")
                    )

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, card: GeneratedCard) -> Optional[Grade]:
        return self._entries.get(_card_key(card))

    def put(self, card: GeneratedCard, grade: Grade) -> None:
        self._entries[_card_key(card)] = grade
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "grader": self.grader_name,
            "grades": {
                key: {"bucket": grade.bucket.value, "reason": grade.reason}
                for key, grade in self._entries.items()
            },
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )


def run_card_check(
    deck: Deck,
    gold: GoldSet,
    grader: Grader,
    deck_from_cache: bool = False,
    cache: Optional[GradeCache] = None,
) -> CardCheckReport:
    if deck.data_cutoff != gold.data_cutoff:
        raise ValueError(
            "deck cutoff %r and gold cutoff %r disagree: the gold set was not "
            "written against this source snapshot"
            % (deck.data_cutoff, gold.data_cutoff)
        )
    graded: List[GradedCard] = []
    counts = {bucket: 0 for bucket in Bucket}
    for card in deck.cards:
        references = gold_references(gold, card)
        # `is not None`, not truthiness: GradeCache defines __len__, so an
        # empty cache is falsy and `if cache:` silently skipped every write.
        grade = cache.get(card) if cache is not None else None
        if grade is None:
            grade = grader.grade(card, references)
            if cache is not None:
                cache.put(card, grade)
        counts[grade.bucket] += 1
        graded.append(
            GradedCard(
                front=card.front,
                back=card.back,
                kind=card.kind.value,
                topic=card.topic,
                source_start=card.provenance.start,
                source_end=card.provenance.end,
                quote=card.provenance.quote,
                bucket=grade.bucket,
                reason=grade.reason,
                reference_ids=tuple(p.id for p in references),
            )
        )
    return CardCheckReport(
        grades=tuple(graded),
        counts=counts,
        grader_name=grader.name,
        grader_description=grader.describe(),
        grader_is_llm=grader.is_llm,
        grader_limitation_note=grader.limitation_note,
        provider_name=deck.provider_name,
        model=deck.model,
        degraded=deck.degraded,
        degraded_reason=deck.degraded_reason,
        rejected=deck.rejected,
        source_id=deck.source_id,
        data_cutoff=deck.data_cutoff,
        gold_size=len(gold.pairs),
        deck_from_cache=deck_from_cache,
    )


# --- CLI --------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m speedrun_ai.card_check",
        description=(
            "Generate 50 cards from one source document and sort them into "
            "correct-and-useful / wrong / correct-but-bad-teaching."
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--grader",
        default="auto",
        choices=["auto", "heuristic", "llm"],
        help="auto uses the LLM grader when a key is present, else heuristic",
    )
    parser.add_argument(
        "--offline-generation",
        action="store_true",
        help="generate with AI disabled (deterministic offline extraction)",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="ignore the cached deck and call the provider again",
    )
    parser.add_argument(
        "--deck-cache",
        default=str(DECK_CACHE),
        help="where the generated deck is cached so runs are repeatable",
    )
    parser.add_argument(
        "--regrade",
        action="store_true",
        help="ignore cached grades and grade every card again",
    )
    args = parser.parse_args(argv)

    gold = load_gold()
    source = load_source()
    cache_path = Path(args.deck_cache)

    deck_from_cache = False
    if cache_path.exists() and not args.regenerate and not args.offline_generation:
        deck = load_deck(cache_path)
        deck_from_cache = True
    else:
        provider: Optional[CardProvider]
        if args.offline_generation:
            provider = NullProvider("AI disabled by --offline-generation")
        else:
            provider = build_provider()
        try:
            deck = generate_deck(source, provider=provider)
        except (GradingError, ProviderError) as exc:
            print("GENERATION FAILED: %s" % exc, file=sys.stderr)
            return 2
        if not args.offline_generation:
            save_deck(deck, cache_path)

    choice = args.grader
    if choice == "auto":
        choice = "llm" if os.environ.get(API_KEY_ENV, "").strip() else "heuristic"
    grader: Grader = LlmGrader() if choice == "llm" else HeuristicGrader()

    grade_cache = None
    if not args.regrade:
        grade_cache = GradeCache(
            RESULTS_DIR / ("card_check_grades_%s.json" % grader.name),
            grader_name=grader.name,
        )
    try:
        report = run_card_check(
            deck=deck,
            gold=gold,
            grader=grader,
            deck_from_cache=deck_from_cache,
            cache=grade_cache,
        )
    except (GradingError, ProviderError) as exc:
        completed = len(grade_cache) if grade_cache is not None else 0
        print(
            "GRADING FAILED: %s\nNo counts are reported: a partial grading "
            "changes every denominator. %d of %d grades completed so far are "
            "kept, so rerunning resumes rather than starting over."
            % (exc, completed, len(deck.cards)),
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(report.format_text())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())

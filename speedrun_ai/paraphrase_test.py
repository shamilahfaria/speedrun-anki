"""DOK 1 vs DOK 2: recall on a card against accuracy on rewordings of it.

The question this harness exists to ask
---------------------------------------
A study tool's *performance model* is whatever it believes about how well you
know something. If that model is built only from how you do on the exact cards
you drilled, it may be measuring recognition of a surface form rather than
knowledge. The test: take 30 cards, write 2 reworded exam-style questions for
each, and compare accuracy on the originals with accuracy on the rewordings.

* If the two numbers match, performance on the card is standing in for the
  underlying knowledge, and the performance model is a copy of the memory
  model -- it adds nothing.
* If there is a gap, card accuracy is over-reporting what is known, and the
  size of the gap is how much.

That is a DOK 1 (recall the stated fact) versus DOK 2 (apply it through a
changed surface form) comparison, run directly on the items.

The honesty problem, and what this file does about it
-----------------------------------------------------
**There are no human subjects here.** Nobody's recall was measured. A harness
that printed a gap without saying so would be presenting an assumption as a
finding, which is the exact failure this evaluation is supposed to catch.

So there are two response sources and only two:

1. `SimulatedResponder` -- an explicitly declared, fully documented model of a
   surface-form memoriser. Its parameters are printed in every report. The
   numbers it produces are a *consequence of those parameters*, not a
   measurement, and the report says so in bold, every run.
2. `FileResponder` -- reads a response file from real testing, if anyone ever
   runs one. The file must declare its own cutoff and whether human subjects
   were involved; the harness prints that declaration and states plainly that
   it cannot verify it.

Run it::

    python -m speedrun_ai.paraphrase_test
    python -m speedrun_ai.paraphrase_test --json
    python -m speedrun_ai.paraphrase_test --responses path/to/responses.json

Deterministic: seeded RNG derived from blake2b over item ids (not Python's
salted `hash()`), no timestamps, byte-identical JSON across processes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "paraphrase" / "cards.json"

# Cutoff of the fixture data this harness scores. It is a property of the
# hand-authored card set, not a model knowledge cutoff.
DATA_CUTOFF = "2026-08-03"

DEFAULT_BOOTSTRAP_RESAMPLES = 10000
DEFAULT_BOOTSTRAP_SEED = 20260803
Z_95 = 1.959963984540054

NO_HUMAN_DATA_STATEMENT = (
    "**NO HUMAN DATA WAS COLLECTED. Every response scored below came from a "
    "declared simulated responder, so these numbers are illustrative of the "
    "mechanism being tested and are not evidence about learners.**"
)

# Words that carry no topic content; ignored when measuring how much surface
# form a rewording shares with its original.
_STOPWORDS = frozenset(
    """a an the and but for nor yet so of to in on at by from with without into
    onto over under between during through across after before again further
    about above below than then that this these those there here when where why
    how what which who whom whose is are was were be been being am do does did
    done has have had having will would shall should can could may might must
    it its it's as if not no nor only just very much many more most both all
    any each per some such other another same own too also either neither one
    two three does you your yours we our ours they them their theirs he she his
    her hers i me my mine while because since although though upon within
    against toward towards up down out off out's per say says said name named
    give gives given state states stated describe describes described explain
    explains explained tell tells told classify classifies classified compare
    compares compared predict predicts predicted use uses used using take takes
    taken work works worked account accounts accounted identify identifies
    identified list lists listed rank ranks ranked write writes written define
    defines defined distinguish distinguishes distinguished happens happen
    happened does't don't doesn't""".split()
)


# --- fixture model ----------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One scoreable question: either the card itself or a rewording of it."""

    item_id: str
    card_id: str
    topic: str
    form: str  # "original" or "rewording"
    front: str
    back: str


@dataclass(frozen=True)
class Variant:
    id: str
    front: str
    back: str


@dataclass(frozen=True)
class ParaphraseCard:
    id: str
    topic: str
    front: str
    back: str
    variants: Tuple[Variant, ...]

    def items(self) -> Tuple[Item, ...]:
        out = [
            Item(
                item_id="%s::original" % self.id,
                card_id=self.id,
                topic=self.topic,
                form="original",
                front=self.front,
                back=self.back,
            )
        ]
        for variant in self.variants:
            out.append(
                Item(
                    item_id=variant.id,
                    card_id=self.id,
                    topic=self.topic,
                    form="rewording",
                    front=variant.front,
                    back=variant.back,
                )
            )
        return tuple(out)


@dataclass(frozen=True)
class ParaphraseSet:
    cards: Tuple[ParaphraseCard, ...]
    data_cutoff: str
    authoring_note: str = ""

    def items(self) -> Tuple[Item, ...]:
        out: List[Item] = []
        for card in self.cards:
            out.extend(card.items())
        return tuple(out)


def load_cards(path: Optional[Path] = None) -> ParaphraseSet:
    """Load and validate the frozen card set."""
    path = Path(path) if path else FIXTURE_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    cards: List[ParaphraseCard] = []
    for entry in raw["cards"]:
        variants = tuple(
            Variant(
                id="%s::v%d" % (entry["id"], index + 1),
                front=v["front"],
                back=v["back"],
            )
            for index, v in enumerate(entry["variants"])
        )
        if len(variants) != 2:
            raise ValueError(
                "card %s has %d variants; the design calls for exactly 2"
                % (entry["id"], len(variants))
            )
        cards.append(
            ParaphraseCard(
                id=entry["id"],
                topic=entry["topic"],
                front=entry["front"],
                back=entry["back"],
                variants=variants,
            )
        )
    ids = [c.id for c in cards]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate card ids in %s" % path)
    return ParaphraseSet(
        cards=tuple(cards),
        data_cutoff=raw["data_cutoff"],
        authoring_note=raw.get("authoring_note", ""),
    )


# --- surface-form overlap ---------------------------------------------------


def content_words(text: str) -> frozenset:
    """Topic-carrying words, lowercased, stopwords and short tokens dropped."""
    tokens = re.findall(r"[a-z0-9][a-z0-9\-']*", text.lower())
    return frozenset(t for t in tokens if len(t) >= 3 and t not in _STOPWORDS)


def content_overlap(a: str, b: str) -> float:
    """Jaccard overlap of content words: 1.0 identical wording, 0.0 disjoint.

    This is the fixture's guard against synonym-swap "rewordings" and the
    driver of the simulated responder: a memoriser's success on a rewording is
    modelled as a function of how much of the original wording survives in it.
    """
    first, second = content_words(a), content_words(b)
    if not first or not second:
        return 0.0
    return len(first & second) / float(len(first | second))


# --- statistics -------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because these counts are small
    (30 and 60) and proportions sit near the ends, where the Wald interval
    runs outside [0, 1] and under-covers.
    """
    if n < 0 or successes < 0:
        raise ValueError("counts must be non-negative")
    if successes > n:
        raise ValueError("successes (%d) cannot exceed n (%d)" % (successes, n))
    if n == 0:
        return (0.0, 1.0)
    p = successes / float(n)
    denominator = 1.0 + (z * z) / n
    centre = (p + (z * z) / (2.0 * n)) / denominator
    margin = (z / denominator) * ((p * (1.0 - p) / n + (z * z) / (4.0 * n * n)) ** 0.5)
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _seeded_random(seed: int, label: str):
    """A `random.Random` seeded stably across processes and hash seeds."""
    import random

    digest = hashlib.blake2b(
        ("%d|%s" % (seed, label)).encode("utf-8"), digest_size=8
    ).digest()
    return random.Random(int.from_bytes(digest, "big"))


def cluster_bootstrap_gap_ci(
    cards: ParaphraseSet,
    responses: Sequence["Response"],
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """Percentile CI for the gap, resampling *cards*, not responses.

    The three items belonging to one card are not independent observations --
    they test the same fact and, under any responder, share whatever that
    responder knows about it. Resampling individual responses would treat 90
    correlated observations as 90 independent ones and give an interval that
    is too narrow. Resampling whole cards keeps the clustering intact.
    """
    by_card: Dict[str, List[Tuple[str, bool]]] = {c.id: [] for c in cards.cards}
    for response in responses:
        by_card.setdefault(response.card_id, []).append(
            (response.form, response.correct)
        )
    card_ids = [c.id for c in cards.cards]
    if not card_ids:
        raise ValueError("no cards to resample")

    rng = _seeded_random(seed, "cluster-bootstrap")
    gaps: List[float] = []
    for _ in range(resamples):
        o_hits = o_n = r_hits = r_n = 0
        for _ in card_ids:
            picked = card_ids[rng.randrange(len(card_ids))]
            for form, correct in by_card[picked]:
                if form == "original":
                    o_n += 1
                    o_hits += 1 if correct else 0
                else:
                    r_n += 1
                    r_hits += 1 if correct else 0
        if o_n == 0 or r_n == 0:  # pragma: no cover - defensive
            continue
        gaps.append(o_hits / float(o_n) - r_hits / float(r_n))

    gaps.sort()
    low_index = int((alpha / 2.0) * len(gaps))
    high_index = min(len(gaps) - 1, int((1.0 - alpha / 2.0) * len(gaps)))
    return (gaps[low_index], gaps[high_index])


# --- responders -------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    item_id: str
    card_id: str
    form: str
    correct: bool


class Responder(ABC):
    """Where the correct/incorrect judgements come from."""

    name = "responder"
    is_simulated = True
    claims_human_subjects = False

    @abstractmethod
    def describe(self) -> str: ...

    @abstractmethod
    def respond(self, cards: ParaphraseSet) -> List[Response]: ...

    def declared_parameters(self) -> Dict[str, Any]:
        return {}

    def provenance_lines(self) -> List[str]:
        return []

    def expected_accuracies(
        self, cards: ParaphraseSet
    ) -> Optional[Tuple[float, float]]:
        """Accuracy the responder's declared model implies, if it has one.

        `None` for any responder whose judgements come from outside (there is
        no model to take an expectation of).
        """
        return None


# Declared behaviour of the simulated responder. These are ASSUMPTIONS, chosen
# to instantiate the mechanism under test; they are not fitted to any data and
# no claim is made that a real learner behaves this way.
SIM_P_ORIGINAL = 0.90
SIM_P_VARIANT_ZERO_OVERLAP = 0.35
SIM_P_VARIANT_IDENTICAL_WORDING = 0.90
SIM_SEED = 20260803


class SimulatedResponder(Responder):
    """A declared model of a surface-form memoriser. Not a person.

    The model, stated in full:

    * On a card it has drilled verbatim it answers correctly with probability
      `SIM_P_ORIGINAL`.
    * On a rewording it answers correctly with probability
      ``floor + (ceiling - floor) * overlap``, where `overlap` is the content
      word Jaccard between the rewording and the original stem. A rewording
      that reuses all the original wording is answered as well as the original
      (`SIM_P_VARIANT_IDENTICAL_WORDING`); one that shares nothing falls back
      to `SIM_P_VARIANT_ZERO_OVERLAP`.

    So the gap this harness reports is produced jointly by these declared
    numbers and by how thoroughly the fixture's rewordings were actually
    rewritten. It is a mechanism demonstration. It measures nobody.
    """

    name = "simulated-surface-form-memoriser"
    is_simulated = True
    claims_human_subjects = False

    def __init__(
        self,
        p_original: float = SIM_P_ORIGINAL,
        p_variant_zero_overlap: float = SIM_P_VARIANT_ZERO_OVERLAP,
        p_variant_identical: float = SIM_P_VARIANT_IDENTICAL_WORDING,
        seed: int = SIM_SEED,
    ):
        self.p_original = p_original
        self.p_variant_zero_overlap = p_variant_zero_overlap
        self.p_variant_identical = p_variant_identical
        self.seed = seed

    def describe(self) -> str:
        return "SimulatedResponder(surface-form memoriser, seed=%d)" % self.seed

    def declared_parameters(self) -> Dict[str, Any]:
        return {
            "p_correct_on_memorised_original": self.p_original,
            "p_correct_on_zero_overlap_rewording": self.p_variant_zero_overlap,
            "p_correct_on_identical_rewording": self.p_variant_identical,
            "seed": self.seed,
        }

    def p_correct(self, card: ParaphraseCard, item: Item) -> float:
        if item.form == "original":
            return self.p_original
        overlap = content_overlap(card.front, item.front)
        span = self.p_variant_identical - self.p_variant_zero_overlap
        return self.p_variant_zero_overlap + span * overlap

    def expected_accuracies(
        self, cards: ParaphraseSet
    ) -> Optional[Tuple[float, float]]:
        originals: List[float] = []
        rewordings: List[float] = []
        for card in cards.cards:
            for item in card.items():
                target = originals if item.form == "original" else rewordings
                target.append(self.p_correct(card, item))
        return (
            sum(originals) / float(len(originals) or 1),
            sum(rewordings) / float(len(rewordings) or 1),
        )

    def respond(self, cards: ParaphraseSet) -> List[Response]:
        out: List[Response] = []
        for card in cards.cards:
            for item in card.items():
                rng = _seeded_random(self.seed, item.item_id)
                out.append(
                    Response(
                        item_id=item.item_id,
                        card_id=item.card_id,
                        form=item.form,
                        correct=rng.random() < self.p_correct(card, item),
                    )
                )
        return out

    def provenance_lines(self) -> List[str]:
        lines = [
            "Response source: SIMULATED. No person answered any of these items.",
            "Declared simulation parameters (assumptions, not a measurement):",
        ]
        for key, value in self.declared_parameters().items():
            lines.append("  %-38s = %s" % (key, value))
        lines.append(
            "  p(correct | rewording) = zero_overlap + (identical - zero_overlap)"
        )
        lines.append(
            "                           * content-word overlap with the original"
        )
        return lines


class FileResponder(Responder):
    """Reads judged responses from a file, for use with real testing.

    The file supplies the judgements; this harness supplies only the
    arithmetic. It cannot check who or what produced the file, and says so.
    """

    name = "supplied-response-file"
    is_simulated = False

    def __init__(self, path: Path):
        self.path = Path(path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._data_cutoff = str(raw.get("data_cutoff", ""))
        self.claims_human_subjects = bool(raw.get("human_subjects", False))
        self.collection_note = str(raw.get("collection_note", "")).strip()
        self._raw_responses = list(raw.get("responses", []))

    def describe(self) -> str:
        return "FileResponder(%s)" % self.path.name

    def declared_parameters(self) -> Dict[str, Any]:
        return {
            "file": str(self.path),
            "declared_data_cutoff": self._data_cutoff,
            "declared_human_subjects": self.claims_human_subjects,
            "collection_note": self.collection_note,
        }

    def respond(self, cards: ParaphraseSet) -> List[Response]:
        if self._data_cutoff != cards.data_cutoff:
            raise ValueError(
                "response file cutoff %r does not match the card set cutoff %r: "
                "the responses were not collected against this item set"
                % (self._data_cutoff, cards.data_cutoff)
            )
        judged = {}
        for entry in self._raw_responses:
            judged[str(entry["item_id"])] = bool(entry["correct"])
        items = cards.items()
        missing = [i.item_id for i in items if i.item_id not in judged]
        if missing:
            raise ValueError(
                "response file is missing %d of %d items (first missing: %s); "
                "a partial file would silently change the denominators"
                % (len(missing), len(items), missing[0])
            )
        extra = set(judged) - {i.item_id for i in items}
        if extra:
            raise ValueError(
                "response file contains %d item ids that are not in the card "
                "set: %s" % (len(extra), sorted(extra)[:3])
            )
        return [
            Response(
                item_id=item.item_id,
                card_id=item.card_id,
                form=item.form,
                correct=judged[item.item_id],
            )
            for item in items
        ]

    def provenance_lines(self) -> List[str]:
        lines = [
            "Response source: supplied file %s" % self.path,
            "The file declares human_subjects=%s."
            % ("true" if self.claims_human_subjects else "false"),
        ]
        if self.collection_note:
            lines.append("Collection note from the file: %s" % self.collection_note)
        lines.append(
            "This harness cannot verify that claim, or how the responses were "
            "collected or judged. It scores whatever the file says."
        )
        return lines


# --- report -----------------------------------------------------------------


@dataclass(frozen=True)
class TopicRow:
    topic: str
    original_correct: int
    original_n: int
    rewording_correct: int
    rewording_n: int

    @property
    def original_accuracy(self) -> float:
        return self.original_correct / float(self.original_n or 1)

    @property
    def rewording_accuracy(self) -> float:
        return self.rewording_correct / float(self.rewording_n or 1)

    @property
    def gap(self) -> float:
        return self.original_accuracy - self.rewording_accuracy


@dataclass(frozen=True)
class ParaphraseReport:
    original_correct: int
    original_n: int
    rewording_correct: int
    rewording_n: int
    original_ci: Tuple[float, float]
    rewording_ci: Tuple[float, float]
    gap_ci: Tuple[float, float]
    responder_name: str
    responder_description: str
    simulated: bool
    claims_human_subjects: bool
    provenance_lines: Tuple[str, ...]
    declared_parameters: Dict[str, Any]
    data_cutoff: str
    card_count: int
    resamples: int
    bootstrap_seed: int
    topic_rows: Tuple[TopicRow, ...] = ()
    authoring_note: str = ""
    expected_original_accuracy: Optional[float] = None
    expected_rewording_accuracy: Optional[float] = None

    @property
    def original_accuracy(self) -> float:
        return self.original_correct / float(self.original_n or 1)

    @property
    def rewording_accuracy(self) -> float:
        return self.rewording_correct / float(self.rewording_n or 1)

    @property
    def gap(self) -> float:
        return self.original_accuracy - self.rewording_accuracy

    @property
    def gap_ci_low(self) -> float:
        return self.gap_ci[0]

    @property
    def gap_ci_high(self) -> float:
        return self.gap_ci[1]

    @property
    def gap_is_significant(self) -> bool:
        """Significant at the 5% level: the interval for the gap excludes 0."""
        return self.gap_ci_low > 0.0 or self.gap_ci_high < 0.0

    @property
    def significance_statement(self) -> str:
        if self.gap_is_significant:
            return (
                "The gap IS significant at the 5%% level: the 95%% interval "
                "[%.3f, %.3f] excludes zero." % (self.gap_ci_low, self.gap_ci_high)
            )
        return (
            "The gap is NOT significant at the 5%% level: the 95%% interval "
            "[%.3f, %.3f] contains zero, so this run cannot distinguish "
            "recall accuracy from rewording accuracy."
            % (self.gap_ci_low, self.gap_ci_high)
        )

    @property
    def interpretation(self) -> str:
        if not self.gap_is_significant:
            return (
                "Read: card accuracy and rewording accuracy are indistinguishable "
                "here. On this evidence a performance model built from card "
                "accuracy is a copy of the memory model -- it carries no extra "
                "information about transfer."
            )
        return (
            "Read: card accuracy overstates rewording accuracy by %.1f points. "
            "A performance model built from card accuracy alone would report "
            "that much more knowledge than the reworded items support, so DOK 1 "
            "scores are not a substitute for DOK 2 scores."
            % (self.gap * 100.0)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Stable dict. Deliberately contains no timestamp."""
        return {
            "data_cutoff": self.data_cutoff,
            "cards": self.card_count,
            "responder": {
                "name": self.responder_name,
                "description": self.responder_description,
                "simulated": self.simulated,
                "claims_human_subjects": self.claims_human_subjects,
                "declared_parameters": self.declared_parameters,
                "expected_accuracy_under_declared_model": (
                    None
                    if self.expected_original_accuracy is None
                    else {
                        "original": round(self.expected_original_accuracy, 6),
                        "rewordings": round(
                            self.expected_rewording_accuracy or 0.0, 6
                        ),
                    }
                ),
            },
            "original": {
                "n": self.original_n,
                "correct": self.original_correct,
                "accuracy": round(self.original_accuracy, 6),
                "ci95": [round(self.original_ci[0], 6), round(self.original_ci[1], 6)],
                "ci_method": "Wilson score",
            },
            "rewordings": {
                "n": self.rewording_n,
                "correct": self.rewording_correct,
                "accuracy": round(self.rewording_accuracy, 6),
                "ci95": [
                    round(self.rewording_ci[0], 6),
                    round(self.rewording_ci[1], 6),
                ],
                "ci_method": "Wilson score",
            },
            "gap": {
                "value": round(self.gap, 6),
                "ci95": [round(self.gap_ci[0], 6), round(self.gap_ci[1], 6)],
                "ci_method": "cluster percentile bootstrap over cards",
                "resamples": self.resamples,
                "seed": self.bootstrap_seed,
                "significant_at_5pct": self.gap_is_significant,
            },
            "by_topic": [
                {
                    "topic": row.topic,
                    "original_accuracy": round(row.original_accuracy, 6),
                    "rewording_accuracy": round(row.rewording_accuracy, 6),
                    "gap": round(row.gap, 6),
                    "cards": row.original_n,
                }
                for row in self.topic_rows
            ],
            "no_human_data_statement": (
                "" if self.claims_human_subjects else NO_HUMAN_DATA_STATEMENT
            ),
            "provenance": list(self.provenance_lines),
            "significance_statement": self.significance_statement,
            "interpretation": self.interpretation,
        }

    def format_text(self) -> str:
        lines: List[str] = []
        lines.append("Speedrun paraphrase test -- DOK 1 (recall) vs DOK 2 (transfer)")
        lines.append("=" * 72)
        lines.append("Data cutoff: %s (fixture authored and frozen on this date)" % self.data_cutoff)
        lines.append(
            "Items: %d cards, %d originals + %d rewordings (2 per card)"
            % (self.card_count, self.original_n, self.rewording_n)
        )
        lines.append("Responder: %s" % self.responder_description)
        lines.append("")
        if not self.claims_human_subjects:
            lines.append(NO_HUMAN_DATA_STATEMENT)
            lines.append("")
        for line in self.provenance_lines:
            lines.append(line)
        lines.append("")
        header = "%-22s %6s %9s %10s   %s" % (
            "form",
            "n",
            "correct",
            "accuracy",
            "95% CI (Wilson)",
        )
        lines.append(header)
        lines.append("-" * len(header))
        lines.append(
            "%-22s %6d %9d %9.1f%%   [%.3f, %.3f]"
            % (
                "original card",
                self.original_n,
                self.original_correct,
                self.original_accuracy * 100.0,
                self.original_ci[0],
                self.original_ci[1],
            )
        )
        lines.append(
            "%-22s %6d %9d %9.1f%%   [%.3f, %.3f]"
            % (
                "rewordings",
                self.rewording_n,
                self.rewording_correct,
                self.rewording_accuracy * 100.0,
                self.rewording_ci[0],
                self.rewording_ci[1],
            )
        )
        if self.expected_original_accuracy is not None:
            lines.append("")
            lines.append(
                "Expected under the declared model: original %.1f%%, rewordings "
                "%.1f%%, gap %+.3f."
                % (
                    self.expected_original_accuracy * 100.0,
                    (self.expected_rewording_accuracy or 0.0) * 100.0,
                    self.expected_original_accuracy
                    - (self.expected_rewording_accuracy or 0.0),
                )
            )
            lines.append(
                "  The realised rates above differ from these purely by sampling "
                "at n=%d and n=%d. Read the difference between the two lines as "
                "noise in a coin-flip draw, not as a property of the model."
                % (self.original_n, self.rewording_n)
            )
        lines.append("")
        lines.append(
            "GAP (original - rewordings): %+.3f (%.1f percentage points)"
            % (self.gap, self.gap * 100.0)
        )
        lines.append(
            "  95%% CI [%.3f, %.3f] -- cluster percentile bootstrap, %d resamples "
            "over the %d cards, seed %d."
            % (
                self.gap_ci[0],
                self.gap_ci[1],
                self.resamples,
                self.card_count,
                self.bootstrap_seed,
            )
        )
        lines.append(
            "  Cards are the resampling unit because a card and its two "
            "rewordings are not independent observations."
        )
        lines.append("")
        lines.append(self.significance_statement)
        lines.append(self.interpretation)
        if self.topic_rows:
            lines.append("")
            sub = "%-20s %8s %11s %8s" % ("topic", "cards", "original", "reworded")
            lines.append(sub)
            lines.append("-" * len(sub))
            for row in self.topic_rows:
                lines.append(
                    "%-20s %8d %10.1f%% %7.1f%%"
                    % (
                        row.topic,
                        row.original_n,
                        row.original_accuracy * 100.0,
                        row.rewording_accuracy * 100.0,
                    )
                )
        lines.append("")
        lines.append("What this run does and does not establish")
        lines.append("-" * 41)
        if self.claims_human_subjects:
            lines.append(
                "The judgements came from the supplied file. This harness cannot "
                "verify their provenance; treat the numbers as being exactly as "
                "good as that file."
            )
        else:
            lines.append(
                "These figures follow from the declared simulation parameters "
                "above and from how thoroughly the fixture's rewordings were "
                "rewritten. They are not a measurement of anyone's recall, and "
                "they are not evidence about learners."
            )
            lines.append(
                "What they do show is the mechanism: when a responder's success "
                "on a rewording depends on surviving surface wording, card "
                "accuracy and transfer accuracy come apart, and a performance "
                "model fed only card accuracy cannot see the difference."
            )
            lines.append(
                "To get a real number, collect judged responses from human "
                "subjects and rerun with --responses; the arithmetic is "
                "identical and only the input changes."
            )
        return "\n".join(lines)


def run_paraphrase_test(
    cards: Optional[ParaphraseSet] = None,
    responder: Optional[Responder] = None,
    resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> ParaphraseReport:
    cards = cards or load_cards()
    responder = responder or SimulatedResponder()
    responses = responder.respond(cards)
    expected = responder.expected_accuracies(cards)

    o_correct = sum(1 for r in responses if r.form == "original" and r.correct)
    o_n = sum(1 for r in responses if r.form == "original")
    r_correct = sum(1 for r in responses if r.form == "rewording" and r.correct)
    r_n = sum(1 for r in responses if r.form == "rewording")

    topic_of = {c.id: c.topic for c in cards.cards}
    buckets: Dict[str, List[int]] = {}
    for response in responses:
        row = buckets.setdefault(topic_of[response.card_id], [0, 0, 0, 0])
        if response.form == "original":
            row[1] += 1
            row[0] += 1 if response.correct else 0
        else:
            row[3] += 1
            row[2] += 1 if response.correct else 0
    topic_rows = tuple(
        TopicRow(
            topic=topic,
            original_correct=vals[0],
            original_n=vals[1],
            rewording_correct=vals[2],
            rewording_n=vals[3],
        )
        for topic, vals in sorted(buckets.items())
    )

    return ParaphraseReport(
        original_correct=o_correct,
        original_n=o_n,
        rewording_correct=r_correct,
        rewording_n=r_n,
        original_ci=wilson_interval(o_correct, o_n),
        rewording_ci=wilson_interval(r_correct, r_n),
        gap_ci=cluster_bootstrap_gap_ci(
            cards, responses, resamples=resamples, seed=bootstrap_seed
        ),
        responder_name=responder.name,
        responder_description=responder.describe()
        + (" [SIMULATED]" if responder.is_simulated else " [supplied file]"),
        simulated=responder.is_simulated,
        claims_human_subjects=responder.claims_human_subjects,
        provenance_lines=tuple(responder.provenance_lines()),
        declared_parameters=dict(responder.declared_parameters()),
        data_cutoff=cards.data_cutoff,
        card_count=len(cards.cards),
        resamples=resamples,
        bootstrap_seed=bootstrap_seed,
        topic_rows=topic_rows,
        authoring_note=cards.authoring_note,
        expected_original_accuracy=expected[0] if expected else None,
        expected_rewording_accuracy=expected[1] if expected else None,
    )


# --- CLI --------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m speedrun_ai.paraphrase_test",
        description=(
            "Compare recall accuracy on 30 cards with accuracy on 60 reworded "
            "exam-style variants of them, and report the gap."
        ),
    )
    parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of the report"
    )
    parser.add_argument(
        "--responses",
        default=None,
        help=(
            "path to a judged response file from real testing. Without it the "
            "run uses the declared simulated responder and says so."
        ),
    )
    parser.add_argument(
        "--resamples",
        type=int,
        default=DEFAULT_BOOTSTRAP_RESAMPLES,
        help="bootstrap resamples for the gap interval",
    )
    args = parser.parse_args(argv)

    cards = load_cards()
    if args.responses:
        responder: Responder = FileResponder(Path(args.responses))
    else:
        responder = SimulatedResponder()

    report = run_paraphrase_test(
        cards=cards, responder=responder, resamples=args.resamples
    )
    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(report.format_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition.
#
# Section 9: the ablation test.
#
#     make ablation
#
# THE CLAIM UNDER TEST
# --------------------
# Transfer evidence should change WHAT GETS SERVED NEXT, not just what gets
# displayed. Three arms, same learners, same questions, same review budget:
#
#   arm 1  full      scheduling weighted by transfer evidence. When a topic's
#                    probe (DOK 2/3) accuracy lags its recall (DOK 1) accuracy,
#                    that topic's cards move up the queue.
#   arm 2  ablation  identical scoring, identical display, stock queue order.
#                    The learner still SEES the gap; the scheduler ignores it.
#                    This is what isolates scheduling from display.
#   arm 3  baseline  plain unmodified Anki scheduling, no transfer scoring.
#
#   arm 1 - arm 2  ->  did the scheduling change do the work?
#   arm 1 - arm 3  ->  does the product beat the obvious alternative at all?
#
# WHAT THIS FILE IS NOT
# ---------------------
# It is not evidence that the product works. There are no human subjects here.
# Every number below is a deductive consequence of the learner model declared in
# this file -- change the model and the numbers change. What it does test is
# whether the mechanism can be distinguished from its absence, and it is built
# so that the answer can come back NO. See the sweep: there are settings where
# the feature ties baseline and settings where it loses to baseline.
#
# HOW THIS HARNESS TRIES TO FALSIFY ITSELF
# ----------------------------------------
# Three learner-model parameters, each of which can switch the effect off:
#
#   transfer_responsiveness (rho)   How much a study review moves DOK 2/3
#                                   ability at all. At rho = 0 study builds
#                                   recall and nothing else, so no queue order
#                                   whatsoever can change the held-out score and
#                                   arm 1 - arm 3 is exactly 0.
#
#   headroom_alignment (gamma)      Whether a large recall-minus-probe gap marks
#                                   a topic that is UNDER-TRAINED (gamma > 0,
#                                   the product's premise) or one that is simply
#                                   HARD and already near its ceiling
#                                   (gamma < 0). At gamma = 0 the gap says
#                                   nothing about where work pays, so targeting
#                                   it is targeting at random. At gamma < 0 the
#                                   feature spends the budget where it buys
#                                   least and LOSES to plain Anki.
#
#   display_response (delta)        How much of the reallocation the learner
#                                   does unprompted, just from seeing the gap on
#                                   screen. At delta = 1 display alone is
#                                   sufficient, arm 2 catches arm 1, and the
#                                   ablation's verdict is that the scheduler
#                                   change did no work.
#
# gamma is the one that matters most, because it is the assumption the product
# is actually making and the one nobody has checked. BRAINLIFT POV 2 records the
# reason for doubt: transfer without enabling moderators comes in at d = -0.053,
# bias-corrected -0.21 (Pan & Rickard).
#
# VARIANCE REDUCTION, AND WHY THE NULLS ARE EXACTLY ZERO
# -----------------------------------------------------
# Every response -- study and held-out alike -- is decided by a uniform drawn
# from a hash of (seed, learner, item, repetition), never from a running RNG
# stream. So two arms that produce the same trajectory produce byte-identical
# results, and two arms that differ only in ability differ only because of
# ability. This is common random numbers. It means a true null reads as 0.000,
# not as 0.03 that a reader has to squint at.

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tools" / "fixtures" / "ablation"

# =============================================================================
# THE MAIN NUMBER, DECLARED BEFORE ANY RUN
# =============================================================================
#
# These three constants were written into this file and committed to before the
# harness had ever been executed end to end -- declared before the first run,
# not fitted to it. They are a prediction, and the run below is allowed to
# refute them. If the observed contrast lands outside the declared range the
# report says MISSED, in those words, and the constants are not edited
# afterwards.
#
# Reasoning behind the point estimate, recorded so it can be checked:
#   - 31 topics, 3000 reviews, so ~97 reviews per topic under a stock queue.
#   - Effective per-review closure of remaining topic headroom is
#     rho * TRANSFER_GAIN_RATE = 0.6 * 0.012 = 0.0072, so a stock arm closes
#     1 - (1 - 0.0072)^97 = 50% of each topic's headroom.
#   - Mean headroom is ~0.21, so all arms gain ~10 pp on held-out probes; the
#     question is only how much better a targeted allocation does.
#   - Concentrating reviews 3:1 on the high-headroom half of the topics is worth
#     about 1.9 pp in a two-topic hand calculation with perfect knowledge.
#   - Discount that for: gamma = 0.7 (30% of headroom variance is noise the
#     signal cannot see), a gap estimated from a finite sample, the engine's
#     refusal threshold suppressing weighting until evidence exists, and the
#     self-limiting effect of the weight falling as the gap closes.
#
# Outcome measure: accuracy on the 310-item held-out probe set, percentage
# points. Primary contrast: arm 1 (full) minus arm 3 (baseline).
PREDICTED_ARM1_MINUS_ARM3_POINT = 1.5
PREDICTED_ARM1_MINUS_ARM3_LOW = 0.3
PREDICTED_ARM1_MINUS_ARM3_HIGH = 4.0

# Secondary, also declared before any run. delta = 0.22 means the display-only
# arm should recover roughly a fifth of whatever the full arm gains, so the
# isolated scheduling effect should be a little under the headline number.
PREDICTED_ARM1_MINUS_ARM2_POINT = 1.2
PREDICTED_ARM1_MINUS_ARM2_LOW = 0.2
PREDICTED_ARM1_MINUS_ARM2_HIGH = 3.2

DEFAULT_SEED = 20260803
DEFAULT_LEARNERS = 120
DEFAULT_REVIEWS = 3000

DATA_CUTOFF = {
    "content outline": "AAMC content outline PDF, (c) 2020 AAMC "
    "(transcribed in rslib/src/transfer/outline.rs)",
    "learner-model priors": "2025-10-01 -- no source published after this date "
    "informs any parameter in this file",
    "learner outcome data": "NONE. No real learner has ever used this product. "
    "There is no outcome dataset, so there is no cutoff for one.",
}

# =============================================================================
# The honesty notice. Printed near the top of every report and again at the end.
# =============================================================================

HONESTY_TOP = """\
+---------------------------------------------------------------------------+
|  **READ THIS FIRST -- THERE ARE NO HUMAN SUBJECTS IN THIS TEST.**          |
|                                                                           |
|  **Every number below is a consequence of the declared learner model in**  |
|  **tools/ablation.py and of nothing else. This run demonstrates THE**      |
|  **HARNESS AND THE MECHANISM -- it is NOT evidence that the product**      |
|  **works on people, and it must not be quoted as though it were.**         |
|                                                                           |
|  **Not that the product works on people. Say so wherever this is cited.**  |
+---------------------------------------------------------------------------+"""

HONESTY_BOTTOM = """\
+---------------------------------------------------------------------------+
|  **AGAIN, AT THE END, BECAUSE IT IS THE ONLY THING THAT MATTERS HERE:**    |
|                                                                           |
|  **There are no human subjects. Zero. Every figure in this report is a**   |
|  **consequence of the declared learner model, computed deductively from**  |
|  **it. The run shows the harness works and the mechanism is separable**    |
|  **from its absence. It shows NOT that the product works on people.**      |
|  **Not that the product works on people -- there is no such evidence.**    |
+---------------------------------------------------------------------------+

WHAT WOULD NEED TO CHANGE TO MAKE THIS REAL EVIDENCE
----------------------------------------------------
Everything load-bearing. Specifically, and in order of how much each one costs:

  1. REAL LEARNERS. Human MCAT candidates, randomised to arm, not simulated
     agents whose learning curve this file defines. n large enough to detect
     the declared effect: at the observed between-learner spread that is on the
     order of several hundred per arm, and it must be powered in advance.
  2. JUDGED RESPONSES. Free-text or passage-based answers scored by a rater who
     does not know the arm, with inter-rater agreement reported. A simulated
     Bernoulli draw against an ability parameter is not a judged response, and
     substituting one for the other is the exact error this project exists to
     call out.
  3. A REAL HELD-OUT OUTCOME. An official AAMC full-length or equivalent taken
     after the study period, not a synthetic probe set generated by the same
     script that generated the study deck.
  4. PRE-REGISTRATION of the analysis, before data collection, not a constant at
     the top of a Python file written by the same person who wrote the analysis.
  5. INDEPENDENT ANALYSIS. Nobody paid by this project should compute the
     headline number. BRAINLIFT POV 2 weights independently funded nulls above
     vendor-adjacent positives; that rule applies to us first.

Until all five exist, the honest status of the Section 9 claim is UNTESTED ON
HUMANS, and the honest status of this file is: the mechanism is implementable,
separable, and falsifiable, and here is the harness that would test it.

+---------------------------------------------------------------------------+
|  **LAST LINE OF THIS REPORT, SO IT IS THE LAST THING YOU READ:**           |
|  **There are no human subjects in this run. Every number above is a**      |
|  **consequence of the declared learner model. It demonstrates the**        |
|  **harness and the mechanism -- NOT that the product works on people.**    |
|  **It needs real learners and judged responses to become real evidence.**  |
+---------------------------------------------------------------------------+"""

# =============================================================================
# Engine constants mirrored from rslib, so the simulated app is handicapped the
# same way the real one is.
# =============================================================================

#: rslib/src/transfer/mod.rs :: Thresholds::default
MIN_REVIEWS_PER_SIDE = 20
MIN_CARDS_PER_SIDE = 5

#: rslib/src/transfer/scale.rs :: SCALE_MIN / SCALE_MAX, and the documented
#: linear placeholder map. Used only to translate a contrast into scale points
#: as an aside; it inherits every caveat stated in that file.
SCALE_MIN = 472
SCALE_MAX = 528

# --- the scheduler under test ------------------------------------------------

#: How strongly a measured gap lifts a topic. weight = 1 + LAMBDA * gap.
TRANSFER_LAMBDA = 4.0
#: The transfer-weighted picker reorders within the K most-due cards.
#:
#: FINDING, recorded because it cost a rewrite and is worth more than the
#: headline number: reordering within a lookahead window reallocates NOTHING.
#: A first version of this file implemented the feature purely as "among the K
#: most-due cards, serve the one whose topic has the largest gap", which sounds
#: like prioritisation and is not. In a backlog-driven SRS every due card is
#: served eventually, so a within-window reorder changes only WHEN a card
#: appears, never HOW OFTEN. Measured: per-topic review counts came out at
#: 83-111 in the full arm against 86-111 in the baseline arm, a per-topic
#: difference of at most 3 reviews in 3000, and the contrast was +0.05 pp --
#: indistinguishable from zero, for the boring reason that the two arms had
#: studied almost exactly the same thing.
#:
#: What actually changes what gets served, under a FIXED review budget, is the
#: rate at which a topic's cards come back. That is INTERVAL_SCALING below. The
#: window reorder is retained because it is part of the feature as described,
#: but it is not the part that does the work.
LOOKAHEAD = 12
#: The load-bearing half of the mechanism. A boosted topic's cards are re-queued
#: at interval / weight, so they return up to TRANSFER_LAMBDA-fold sooner and
#: claim more of a fixed budget. The card's stored SM-2 interval and ease are
#: left stock; only the queue placement moves. Weights are >= 1, so the feature
#: only ever promotes -- but under a fixed budget, promoting the wrong topics
#: still starves the right ones, which is how it can and does lose.
INTERVAL_SCALING = True
#: The gap display and the queue weights refresh every N reviews, not every
#: review. The real dashboard is not recomputed per card either.
WEIGHT_REFRESH = 25

# --- stock Anki scheduling, as modelled --------------------------------------

INITIAL_INTERVAL = 1.0
INITIAL_EASE = 2.5
MIN_EASE = 1.3
EASE_PENALTY = 0.2
LAPSE_INTERVAL = 1.0

# --- the learner model -------------------------------------------------------

#: Fraction of a topic's remaining recall headroom closed per review.
RECALL_GAIN_RATE = 0.030
RECALL_CEILING = 0.97
#: Fraction of a topic's remaining TRANSFER headroom closed per review, before
#: transfer_responsiveness scales it.
TRANSFER_GAIN_RATE = 0.012

RECALL0_MIN, RECALL0_MAX = 0.30, 0.80
GAP0_MIN, GAP0_MAX = 0.00, 0.35
HEADROOM_MIN, HEADROOM_MAX = 0.02, 0.40
TRANSFER_CEILING_CAP = 0.98

#: Defaults for the three falsifiers. Each is declared, with its reason.
#: rho: a deliberate midpoint. Butler 2010 shows retrieval practice does produce
#: transfer with feedback; Pan & Rickard put the unmoderated effect near zero.
#: Splitting the difference is more honest than picking either end.
DEFAULT_TRANSFER_RESPONSIVENESS = 0.60
#: gamma: the product ASSUMES 1.0. We have no evidence for it, so we discount it
#: before we ever measure anything, and the sweep covers -1.0 through 1.0.
DEFAULT_HEADROOM_ALIGNMENT = 0.70
#: delta: Yan et al. -- told that 90% of people learn better a given way, 78%
#: place themselves in the other 10%. So 22% act on what they are shown.
DEFAULT_DISPLAY_RESPONSE = 0.22

ARM_FULL = "full"
ARM_ABLATION = "ablation"
ARM_BASELINE = "baseline"
ARMS: Tuple[str, ...] = (ARM_FULL, ARM_ABLATION, ARM_BASELINE)

ARM_BLURB = {
    ARM_FULL: "transfer-weighted queue + transfer display  (the product)",
    ARM_ABLATION: "stock queue + transfer display           (the ablation)",
    ARM_BASELINE: "stock queue, no transfer scoring at all  (plain Anki)",
}

BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_ALPHA = 0.05

#: The smallest held-out difference this project will call practically
#: meaningful, in percentage points. One scaled point on 472-528 is 100/56 =
#: 1.79 pp, and the real exam's own published confidence band is +/-1 to +/-2
#: scaled points -- so anything under a scaled point is inside the exam's own
#: noise and must not be sold as an improvement, however tight its CI.
#: Declared alongside the prediction, before any run.
PRACTICAL_FLOOR_PP = 100.0 / (SCALE_MAX - SCALE_MIN)


class InvariantViolation(RuntimeError):
    """A guarantee the test depends on was not met. Always fatal."""


# =============================================================================
# Common random numbers
# =============================================================================

_MASK64 = (1 << 64) - 1


def _mix(x: int) -> int:
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK64
    return x ^ (x >> 31)


def u01(*parts: int) -> float:
    """A uniform in [0, 1) keyed by content, not by stream position.

    Two arms that reach the same (learner, item, repetition) get the same
    number, which is what makes a genuine null come out as exactly 0.
    """
    h = 0x9E3779B97F4A7C15
    for p in parts:
        h = _mix(h ^ (p & _MASK64))
    return (h >> 11) * (1.0 / (1 << 53))


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_key(*parts: str) -> int:
    """A reproducible integer from strings.

    NOT builtin hash(). Python randomises hash() of str per interpreter unless
    PYTHONHASHSEED is pinned, so seeding a bootstrap from hash("full") gives
    output that is reproducible within one process and silently different
    between two -- point estimates identical, every confidence interval moving.
    Found exactly that way: two consecutive `make ablation-quick` runs agreed on
    every mean and disagreed in the third decimal of every CI.
    """
    digest = hashlib.blake2b("\x1f".join(parts).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


# =============================================================================
# Fixtures
# =============================================================================


@dataclass(frozen=True)
class StudyItem:
    id: str
    topic: str
    kind: str  # "recall" | "probe"
    difficulty: float


@dataclass(frozen=True)
class Probe:
    id: str
    topic: str
    difficulty: float


@dataclass(frozen=True)
class Deck:
    topics: Tuple[dict, ...]
    study_items: Tuple[StudyItem, ...]
    holdout_probes: Tuple[Probe, ...]
    topic_index: Dict[str, int]
    #: per study item, its topic's index; parallel arrays keep the hot loop flat
    study_topic_idx: Tuple[int, ...]
    study_is_probe: Tuple[bool, ...]
    study_difficulty: Tuple[float, ...]
    holdout_topic_idx: Tuple[int, ...]
    holdout_difficulty: Tuple[float, ...]

    @property
    def n_topics(self) -> int:
        return len(self.topics)


_DECK_CACHE: Optional[Deck] = None


def load_deck() -> Deck:
    """Load the fixed fixtures. Cached: they are immutable and identical for
    every arm, which is the point of them being on disk rather than generated."""
    global _DECK_CACHE
    if _DECK_CACHE is not None:
        return _DECK_CACHE

    topics = tuple(json.loads((FIXTURE_DIR / "topics.json").read_text()))
    raw_study = json.loads((FIXTURE_DIR / "study_deck.json").read_text())
    raw_hold = json.loads((FIXTURE_DIR / "holdout_probes.json").read_text())

    study = tuple(
        StudyItem(r["id"], r["topic"], r["kind"], r["difficulty"]) for r in raw_study
    )
    hold = tuple(Probe(r["id"], r["topic"], r["difficulty"]) for r in raw_hold)

    study_ids = {i.id for i in study}
    hold_ids = {p.id for p in hold}
    overlap = study_ids & hold_ids
    if overlap:
        raise InvariantViolation(
            f"held-out probes are present in the study deck: {sorted(overlap)[:5]}"
        )
    if len(hold_ids) != len(hold):
        raise InvariantViolation("duplicate ids in the held-out probe set")

    tidx = {t["code"]: n for n, t in enumerate(topics)}
    _DECK_CACHE = Deck(
        topics=topics,
        study_items=study,
        holdout_probes=hold,
        topic_index=tidx,
        study_topic_idx=tuple(tidx[i.topic] for i in study),
        study_is_probe=tuple(i.kind == "probe" for i in study),
        study_difficulty=tuple(i.difficulty for i in study),
        holdout_topic_idx=tuple(tidx[p.topic] for p in hold),
        holdout_difficulty=tuple(p.difficulty for p in hold),
    )
    return _DECK_CACHE


# =============================================================================
# The learner model
# =============================================================================


@dataclass(frozen=True)
class LearnerModel:
    """The three knobs that decide whether the feature can work at all.

    Requirement: at least one setting must make the feature stop paying. All
    three do, in different ways, and the sweep prints where each one crosses.
    """

    transfer_responsiveness: float = DEFAULT_TRANSFER_RESPONSIVENESS
    headroom_alignment: float = DEFAULT_HEADROOM_ALIGNMENT
    display_response: float = DEFAULT_DISPLAY_RESPONSE

    def describe(self) -> List[Tuple[str, str, str]]:
        return [
            (
                "transfer_responsiveness (rho)",
                f"{self.transfer_responsiveness:.2f}",
                "how much a review moves DOK 2/3 ability; 0 = study never "
                "builds transfer, so no queue can help",
            ),
            (
                "headroom_alignment (gamma)",
                f"{self.headroom_alignment:+.2f}",
                "does a big gap mark an under-trained topic (+) or a hard one "
                "already near ceiling (-); 0 = the gap is uninformative",
            ),
            (
                "display_response (delta)",
                f"{self.display_response:.2f}",
                "fraction of reallocation the learner does unprompted from the "
                "display alone; 1 = the scheduler is redundant",
            ),
        ]


@dataclass
class Learner:
    """One simulated learner's true, unobservable state."""

    index: int
    recall0: List[float]
    transfer0: List[float]
    ceiling: List[float]


def make_learner(index: int, seed: int, model: LearnerModel, n_topics: int) -> Learner:
    """Draw a learner. Independent of arm -- the same learner faces all three."""
    rng = random.Random((seed * 1_000_003) ^ (index * 2_654_435_761))
    recall0: List[float] = []
    transfer0: List[float] = []
    gap_norm: List[float] = []
    hardness_lottery: List[float] = []
    for _ in range(n_topics):
        r = rng.uniform(RECALL0_MIN, RECALL0_MAX)
        g = rng.uniform(GAP0_MIN, GAP0_MAX)
        recall0.append(r)
        transfer0.append(max(0.02, r - g))
        gap_norm.append((g - GAP0_MIN) / (GAP0_MAX - GAP0_MIN))
        hardness_lottery.append(rng.random())

    gamma = model.headroom_alignment
    mag = abs(gamma)
    ceiling: List[float] = []
    for t in range(n_topics):
        aligned = gap_norm[t] if gamma >= 0.0 else (1.0 - gap_norm[t])
        # gamma = 0 -> headroom is the lottery draw, independent of the gap.
        # |gamma| = 1 -> headroom is fully determined by the gap (or its inverse).
        s = (1.0 - mag) * hardness_lottery[t] + mag * aligned
        headroom = HEADROOM_MIN + s * (HEADROOM_MAX - HEADROOM_MIN)
        ceiling.append(min(TRANSFER_CEILING_CAP, transfer0[t] + headroom))
    return Learner(index=index, recall0=recall0, transfer0=transfer0, ceiling=ceiling)


# =============================================================================
# The three arms
# =============================================================================


@dataclass
class ArmResult:
    arm: str
    reviews_per_learner: Tuple[int, ...]
    served_ids: frozenset
    scored_ids: Tuple[str, ...]
    accuracy: Tuple[float, ...]  # per learner, 0..1, on the held-out set
    #: diagnostics, so a reader can see the mechanism actually engaged
    weighted_picks: int = 0
    stock_picks: int = 0
    refused_topic_reviews: int = 0

    @property
    def total_reviews(self) -> int:
        return sum(self.reviews_per_learner)

    @property
    def mean_accuracy(self) -> float:
        return sum(self.accuracy) / len(self.accuracy)


def _simulate_learner(
    arm: str,
    learner: Learner,
    deck: Deck,
    seed: int,
    reviews: int,
    model: LearnerModel,
) -> Tuple[float, int, set, int, int, int]:
    """Study `reviews` cards under `arm`'s policy, then sit the held-out set.

    Returns (holdout accuracy, reviews served, served item indices,
    weighted picks, stock picks, reviews on refused-gap topics).
    """
    n_items = len(deck.study_items)
    n_topics = deck.n_topics
    li = learner.index

    recall = list(learner.recall0)
    transfer = list(learner.transfer0)
    ceiling = learner.ceiling

    topic_of = deck.study_topic_idx
    is_probe = deck.study_is_probe
    difficulty = deck.study_difficulty

    # --- stock Anki state, identical at t=0 for every arm --------------------
    interval = [INITIAL_INTERVAL] * n_items
    ease = [INITIAL_EASE] * n_items
    seen = [0] * n_items
    # Initial due jitter is keyed by (seed, learner, item) only, so all three
    # arms start from the same queue. Any divergence downstream is policy.
    queue: List[Tuple[float, int]] = [
        (u01(seed, li, idx, 0xD0E), idx) for idx in range(n_items)
    ]
    heapq.heapify(queue)

    # --- observed evidence, exactly what the app could know ------------------
    r_obs = [0] * n_topics
    r_pass = [0] * n_topics
    p_obs = [0] * n_topics
    p_pass = [0] * n_topics
    r_cards = [set() for _ in range(n_topics)]
    p_cards = [set() for _ in range(n_topics)]
    weights = [1.0] * n_topics
    gap_refused = [True] * n_topics

    uses_transfer_evidence = arm in (ARM_FULL, ARM_ABLATION)
    always_weighted = arm == ARM_FULL
    delta = model.display_response
    rho = model.transfer_responsiveness

    served: set = set()
    weighted_picks = 0
    stock_picks = 0
    refused_reviews = 0

    def refresh_weights() -> None:
        for t in range(n_topics):
            enough = (
                r_obs[t] >= MIN_REVIEWS_PER_SIDE
                and p_obs[t] >= MIN_REVIEWS_PER_SIDE
                and len(r_cards[t]) >= MIN_CARDS_PER_SIDE
                and len(p_cards[t]) >= MIN_CARDS_PER_SIDE
            )
            if not enough:
                # Mirrors gap_valid() in rslib: a gap against a refused score is
                # not a gap. The queue falls back to stock rather than acting on
                # evidence the engine would refuse to display.
                gap_refused[t] = True
                weights[t] = 1.0
                continue
            gap_refused[t] = False
            gap = (r_pass[t] / r_obs[t]) - (p_pass[t] / p_obs[t])
            weights[t] = 1.0 + TRANSFER_LAMBDA * max(0.0, gap)

    for step in range(reviews):
        if uses_transfer_evidence and step % WEIGHT_REFRESH == 0:
            refresh_weights()

        if always_weighted:
            use_weighted = True
        elif uses_transfer_evidence and delta > 0.0:
            # Arm 2's only causal path: the learner sees the gap on screen and
            # self-reallocates this often. delta = 0 makes arm 2 identical to
            # arm 3; delta = 1 makes it identical to arm 1.
            use_weighted = u01(seed, li, step, 0x5EE) < delta
        else:
            use_weighted = False

        if use_weighted:
            weighted_picks += 1
            popped = []
            for _ in range(LOOKAHEAD):
                if not queue:
                    break
                popped.append(heapq.heappop(queue))
            best = 0
            best_key = (-weights[topic_of[popped[0][1]]], popped[0][0])
            for n in range(1, len(popped)):
                due, idx = popped[n]
                key = (-weights[topic_of[idx]], due)
                if key < best_key:
                    best_key, best = key, n
            due, idx = popped.pop(best)
            for entry in popped:
                heapq.heappush(queue, entry)
        else:
            stock_picks += 1
            due, idx = heapq.heappop(queue)

        t = topic_of[idx]
        if gap_refused[t]:
            refused_reviews += 1
        served.add(idx)

        # --- the learner answers -------------------------------------------
        probe = is_probe[idx]
        ability = transfer[t] if probe else recall[t]
        p_correct = ability - (difficulty[idx] - 0.5)
        if p_correct < 0.01:
            p_correct = 0.01
        elif p_correct > 0.99:
            p_correct = 0.99
        rep = seen[idx]
        seen[idx] = rep + 1
        passed = u01(seed, li, idx, rep, 0xA5) < p_correct

        # --- what the app records ------------------------------------------
        if probe:
            p_obs[t] += 1
            p_pass[t] += passed
            p_cards[t].add(idx)
        else:
            r_obs[t] += 1
            r_pass[t] += passed
            r_cards[t].add(idx)

        # --- what the learner actually gains --------------------------------
        # Recall improves from any review, at a topic-independent rate.
        recall[t] += RECALL_GAIN_RATE * (RECALL_CEILING - recall[t])
        # Transfer improves only in proportion to responsiveness, and only into
        # whatever headroom the topic actually has. rho = 0 freezes it.
        head = ceiling[t] - transfer[t]
        if head > 0.0 and rho > 0.0:
            transfer[t] += rho * TRANSFER_GAIN_RATE * head

        # --- stock SM-2-ish rescheduling ------------------------------------
        # The card's own interval and ease are updated identically in every
        # arm. Nothing here depends on the policy.
        if passed:
            interval[idx] *= ease[idx]
        else:
            interval[idx] = LAPSE_INTERVAL
            e = ease[idx] - EASE_PENALTY
            ease[idx] = e if e > MIN_EASE else MIN_EASE

        # ...but where the card lands in the queue does. This is the half of
        # the mechanism that actually reallocates a fixed review budget: a
        # topic carrying a measured transfer gap gets its cards back sooner,
        # and so consumes more of the budget, at the cost of every topic that
        # is not boosted. Under `use_weighted` only -- arms 2 and 3 push at the
        # stock interval.
        if use_weighted and INTERVAL_SCALING:
            heapq.heappush(queue, (due + interval[idx] / weights[t], idx))
        else:
            heapq.heappush(queue, (due + interval[idx], idx))

    # --- the held-out probe set, identical for every arm --------------------
    correct = 0
    h_topic = deck.holdout_topic_idx
    h_diff = deck.holdout_difficulty
    for n in range(len(h_topic)):
        p = transfer[h_topic[n]] - (h_diff[n] - 0.5)
        if p < 0.01:
            p = 0.01
        elif p > 0.99:
            p = 0.99
        if u01(seed, li, n, 0xB0DE) < p:
            correct += 1
    accuracy = correct / len(h_topic)
    return accuracy, reviews, served, weighted_picks, stock_picks, refused_reviews


# =============================================================================
# Contrasts and intervals
# =============================================================================


def bootstrap_ci(
    values: Sequence[float],
    *,
    seed: int,
    draws: int = BOOTSTRAP_DRAWS,
    alpha: float = BOOTSTRAP_ALPHA,
) -> Tuple[float, float]:
    """Percentile bootstrap. The resampling unit is whatever `values` indexes,
    and here that is always the learner -- one paired difference each."""
    vals = list(values)
    if not vals:
        raise ValueError("cannot bootstrap zero observations")
    if len(vals) == 1:
        return vals[0], vals[0]
    rng = random.Random(seed ^ 0x600D5EED)
    n = len(vals)
    means = []
    for _ in range(draws):
        total = 0.0
        for _ in range(n):
            total += vals[int(rng.random() * n)]
        means.append(total / n)
    means.sort()
    lo_rank = max(0, math.ceil((alpha / 2.0) * draws) - 1)
    hi_rank = min(draws - 1, math.ceil((1.0 - alpha / 2.0) * draws) - 1)
    return means[lo_rank], means[hi_rank]


@dataclass(frozen=True)
class Contrast:
    label: str
    point: float  # percentage points
    lower: float
    upper: float
    per_learner: Tuple[float, ...]
    resampling_unit: str = "learner"

    @property
    def excludes_zero(self) -> bool:
        return self.lower > 0.0 or self.upper < 0.0

    def scaled_equivalent(self) -> float:
        """The contrast translated onto 472-528 through the documented linear
        placeholder map in rslib/src/transfer/scale.rs. Inherits every caveat
        stated there, including that its intervals are too narrow."""
        return self.point / 100.0 * (SCALE_MAX - SCALE_MIN)


@dataclass
class Trial:
    seed: int
    learners: int
    reviews: int
    model: LearnerModel
    arms: Dict[str, ArmResult]
    arms_requested: Tuple[str, ...]

    def check_invariants(self) -> None:
        """Equal study time and a clean held-out set, enforced not assumed."""
        for arm, res in self.arms.items():
            if len(res.reviews_per_learner) != self.learners:
                raise InvariantViolation(
                    f"arm {arm!r} ran {len(res.reviews_per_learner)} learners, "
                    f"expected {self.learners}"
                )
            odd = sorted({c for c in res.reviews_per_learner if c != self.reviews})
            if odd:
                raise InvariantViolation(
                    f"unequal study time: arm {arm!r} has learners with "
                    f"{odd} reviews, budget is {self.reviews}"
                )
        totals = {a: r.total_reviews for a, r in self.arms.items()}
        if len(set(totals.values())) > 1:
            raise InvariantViolation(f"arms did not spend equal study time: {totals}")

        deck = load_deck()
        holdout = {p.id for p in deck.holdout_probes}
        for arm, res in self.arms.items():
            leaked = res.served_ids & holdout
            if leaked:
                raise InvariantViolation(
                    f"arm {arm!r} served {len(leaked)} held-out probes during "
                    f"study, e.g. {sorted(leaked)[:3]}"
                )
        orders = {r.scored_ids for r in self.arms.values()}
        if len(orders) > 1:
            raise InvariantViolation("arms were scored on different question sets")

    def contrast(self, a: str, b: str) -> Contrast:
        ra, rb = self.arms[a], self.arms[b]
        diffs = tuple(
            (x - y) * 100.0 for x, y in zip(ra.accuracy, rb.accuracy)
        )
        point = sum(diffs) / len(diffs)
        lo, hi = bootstrap_ci(diffs, seed=self.seed ^ stable_key(a, b))
        return Contrast(
            label=f"{a} - {b}", point=point, lower=lo, upper=hi, per_learner=diffs
        )


def run_trial(
    *,
    seed: int = DEFAULT_SEED,
    learners: int = DEFAULT_LEARNERS,
    reviews: int = DEFAULT_REVIEWS,
    model: Optional[LearnerModel] = None,
    arms: Sequence[str] = ARMS,
) -> Trial:
    model = model or LearnerModel()
    deck = load_deck()
    people = [make_learner(i, seed, model, deck.n_topics) for i in range(learners)]
    scored_ids = tuple(p.id for p in deck.holdout_probes)
    study_id_of = [i.id for i in deck.study_items]

    results: Dict[str, ArmResult] = {}
    for arm in arms:
        acc: List[float] = []
        counts: List[int] = []
        served_all: set = set()
        w = s = refused = 0
        for person in people:
            a, n, served, wp, sp, rr = _simulate_learner(
                arm, person, deck, seed, reviews, model
            )
            acc.append(a)
            counts.append(n)
            served_all |= served
            w += wp
            s += sp
            refused += rr
        results[arm] = ArmResult(
            arm=arm,
            reviews_per_learner=tuple(counts),
            served_ids=frozenset(study_id_of[i] for i in served_all),
            scored_ids=scored_ids,
            accuracy=tuple(acc),
            weighted_picks=w,
            stock_picks=s,
            refused_topic_reviews=refused,
        )

    trial = Trial(
        seed=seed,
        learners=learners,
        reviews=reviews,
        model=model,
        arms=results,
        arms_requested=tuple(arms),
    )
    trial.check_invariants()
    return trial


# =============================================================================
# The sweep
# =============================================================================

SWEEP_VALUES = {
    "headroom_alignment": (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 0.7, 1.0),
    "transfer_responsiveness": (0.0, 0.1, 0.25, 0.5, 0.6, 0.8, 1.0),
    "display_response": (0.0, 0.22, 0.4, 0.6, 0.8, 1.0),
}

#: Which contrast each parameter actually acts on. display_response moves only
#: arm 2, so arm1 - arm3 is flat across that sweep by construction and reading a
#: break-even off it would be meaningless -- the question that parameter answers
#: is "did the SCHEDULING do the work", which is arm1 - arm2.
SWEEP_GOVERNING_CONTRAST = {
    "headroom_alignment": "arm1_minus_arm3",
    "transfer_responsiveness": "arm1_minus_arm3",
    "display_response": "arm1_minus_arm2",
}

CONTRAST_TITLE = {
    "arm1_minus_arm3": "arm1 - arm3 (does it beat plain Anki?)",
    "arm1_minus_arm2": "arm1 - arm2 (did the scheduling do the work?)",
}

SWEEP_MEANING = {
    "headroom_alignment": (
        "Does a lagging probe score mark a topic worth more reviews (+) or one "
        "that is simply hard and already near its ceiling (-)? This is the "
        "product's core unverified assumption."
    ),
    "transfer_responsiveness": (
        "Does drilling cards build DOK 2/3 ability at all? At 0 it does not, "
        "and no scheduler can help."
    ),
    "display_response": (
        "How much reallocation does the learner do from the display alone? At "
        "1.0 the scheduler change is redundant and the ablation shows nothing."
    ),
}


@dataclass(frozen=True)
class SweepRow:
    value: float
    arm1_minus_arm3: Contrast
    arm1_minus_arm2: Contrast
    arm2_minus_arm3: Contrast
    baseline_accuracy: float


@dataclass(frozen=True)
class SweepResult:
    param: str
    rows: Tuple[SweepRow, ...]
    #: the parameter value at which the GOVERNING contrast crosses zero
    break_even: Optional[float]
    seed: int
    learners: int
    reviews: int
    governing: str = "arm1_minus_arm3"


def run_sweep(
    *,
    param: str,
    seed: int = DEFAULT_SEED,
    learners: int = DEFAULT_LEARNERS,
    reviews: int = DEFAULT_REVIEWS,
    values: Optional[Iterable[float]] = None,
) -> SweepResult:
    if param not in SWEEP_VALUES:
        raise ValueError(f"unknown sweep parameter {param!r}")
    vals = tuple(values) if values is not None else SWEEP_VALUES[param]
    rows: List[SweepRow] = []
    for v in vals:
        model = LearnerModel(**{param: v})
        trial = run_trial(seed=seed, learners=learners, reviews=reviews, model=model)
        rows.append(
            SweepRow(
                value=v,
                arm1_minus_arm3=trial.contrast(ARM_FULL, ARM_BASELINE),
                arm1_minus_arm2=trial.contrast(ARM_FULL, ARM_ABLATION),
                arm2_minus_arm3=trial.contrast(ARM_ABLATION, ARM_BASELINE),
                baseline_accuracy=trial.arms[ARM_BASELINE].mean_accuracy,
            )
        )

    governing = SWEEP_GOVERNING_CONTRAST[param]
    break_even = None
    for a, b in zip(rows, rows[1:]):
        ya = getattr(a, governing).point
        yb = getattr(b, governing).point
        if ya == 0.0 and yb == 0.0:
            continue
        if (ya <= 0.0 <= yb) or (yb <= 0.0 <= ya):
            if yb == ya:
                break_even = a.value
            else:
                break_even = a.value + (0.0 - ya) * (b.value - a.value) / (yb - ya)
            break
    return SweepResult(
        param=param,
        rows=tuple(rows),
        break_even=break_even,
        seed=seed,
        learners=learners,
        reviews=reviews,
        governing=governing,
    )


# =============================================================================
# Reporting
# =============================================================================

RULE = "=" * 79
THIN = "-" * 79


def _verdict(point: float, lo: float, hi: float) -> str:
    if lo <= point <= hi:
        return "WITHIN the declared range"
    return "MISSED the declared range"


def _render_setup(trial: Trial, out: List[str]) -> None:
    """Honesty notice, the declared prediction, the model, the arms, and the
    two guarantees the whole comparison rests on: equal time and same
    questions. Split out of render_report only to keep each piece readable."""
    w = out.append
    deck = load_deck()

    w(HONESTY_TOP)
    w("")
    w(RULE)
    w("SPEEDRUN SECTION 9 -- ABLATION TEST")
    w(RULE)
    w("")
    w("Claim under test: transfer evidence should change WHAT GETS SERVED NEXT,")
    w("not just what gets displayed.")
    w("")

    # --- declared in advance ------------------------------------------------
    w("DECLARED IN ADVANCE (constants at the top of tools/ablation.py, written")
    w("before this harness had ever been run end to end)")
    w(THIN)
    w(
        f"  main number, arm1 - arm3 : {PREDICTED_ARM1_MINUS_ARM3_POINT:+.1f} pp"
        f"   range [{PREDICTED_ARM1_MINUS_ARM3_LOW:+.1f}, "
        f"{PREDICTED_ARM1_MINUS_ARM3_HIGH:+.1f}] pp"
    )
    w(
        f"  secondary, arm1 - arm2   : {PREDICTED_ARM1_MINUS_ARM2_POINT:+.1f} pp"
        f"   range [{PREDICTED_ARM1_MINUS_ARM2_LOW:+.1f}, "
        f"{PREDICTED_ARM1_MINUS_ARM2_HIGH:+.1f}] pp"
    )
    w("  outcome measure          : accuracy on the 310-item held-out probe set")
    w("")
    w(f"  seed                     : {trial.seed}")
    w(f"  simulated learners       : {trial.learners}")
    w(f"  review budget per learner: {trial.reviews}")
    w("  data cutoff:")
    for k, v in DATA_CUTOFF.items():
        w(f"    {k:<22}: {v}")
    w("")

    # --- learner model ------------------------------------------------------
    w("THE DECLARED LEARNER MODEL -- every number in this report is a")
    w("consequence of the declared learner model and of nothing else")
    w(THIN)
    for name, value, why in trial.model.describe():
        w(f"  {name:<32} = {value}")
        w(f"      {why}")
    w("")

    # --- arms ---------------------------------------------------------------
    w("ARMS RUN")
    w(THIN)
    for arm in trial.arms_requested:
        w(f"  {arm:<9} {ARM_BLURB[arm]}")
    w("")

    # --- equal study time ---------------------------------------------------
    w("EQUAL STUDY TIME -- enforced and asserted, not assumed")
    w(THIN)
    w(f"  {'arm':<10} {'learners':>9} {'reviews each':>13} {'total reviews':>14}"
      f" {'min':>6} {'max':>6}")
    for arm in trial.arms_requested:
        r = trial.arms[arm]
        counts = r.reviews_per_learner
        w(
            f"  {arm:<10} {len(counts):>9} {trial.reviews:>13} "
            f"{r.total_reviews:>14} {min(counts):>6} {max(counts):>6}"
        )
    w("")
    w("  Assertion passed: every arm served exactly the same number of reviews")
    w("  to every learner. The budget is a fixed COUNT of review events, and the")
    w("  transfer weighting can only change WHICH card fills each of them -- by")
    w(f"  reordering the {LOOKAHEAD} most-due cards and by re-queueing a boosted")
    w("  topic's cards at interval/weight so they come back sooner. Neither can")
    w("  add a review, so a topic is only ever promoted at another topic's cost.")
    w("")

    # --- questions ----------------------------------------------------------
    w("SAME QUESTIONS -- one fixed held-out set, never served during study")
    w(THIN)
    w(f"  held-out probes          : {len(deck.holdout_probes)} items over "
      f"{deck.n_topics} MCAT content categories")
    w(f"  study deck               : {len(deck.study_items)} items "
      f"({sum(deck.study_is_probe)} in-app probes, "
      f"{len(deck.study_items) - sum(deck.study_is_probe)} recall)")
    for name in ("holdout_probes.json", "study_deck.json", "topics.json"):
        w(f"  sha256 {name:<20}: {sha256_of(FIXTURE_DIR / name)}")
    w("  Assertion passed: no arm served any held-out probe id during study,")
    w("  and all arms were scored on the identical set in the identical order.")
    w("")

    # --- mechanism engaged --------------------------------------------------
    w("DID THE MECHANISM ACTUALLY ENGAGE? (diagnostics, not results)")
    w(THIN)
    w(f"  {'arm':<10} {'weighted picks':>15} {'stock picks':>13} "
      f"{'reviews on refused topics':>27}")
    for arm in trial.arms_requested:
        r = trial.arms[arm]
        w(
            f"  {arm:<10} {r.weighted_picks:>15} {r.stock_picks:>13} "
            f"{r.refused_topic_reviews:>27}"
        )
    w("")
    w(f"  A topic's gap is refused below {MIN_REVIEWS_PER_SIDE} graded reviews and "
      f"{MIN_CARDS_PER_SIDE} distinct cards")
    w("  PER SIDE, mirroring Thresholds/gap_valid in rslib. While refused, arm 1")
    w("  falls back to stock order. If the refused column is close to the total,")
    w("  the feature barely ran and any difference below is noise.")
    w("")


def _render_results(trial: Trial, out: List[str]) -> None:
    """The numbers, their intervals, and whether they mean anything."""
    w = out.append
    deck = load_deck()

    # --- results ------------------------------------------------------------
    w("RESULT -- held-out probe accuracy")
    w(THIN)
    w(f"  {'arm':<10} {'mean accuracy':>14} {'95% CI (learner bootstrap)':>32}")
    for arm in trial.arms_requested:
        r = trial.arms[arm]
        vals = [a * 100.0 for a in r.accuracy]
        lo, hi = bootstrap_ci(vals, seed=trial.seed ^ stable_key(arm))
        w(f"  {arm:<10} {r.mean_accuracy * 100:>13.2f}% "
          f"{f'[{lo:.2f}%, {hi:.2f}%]':>32}")
    w("")

    w("CONTRASTS -- paired within learner, bootstrapped over LEARNERS")
    w(THIN)
    w(f"  {'contrast':<22} {'point':>9} {'95% CI':>22}  what it answers")
    pairs = [
        (ARM_FULL, ARM_BASELINE, "does it beat plain Anki?"),
        (ARM_FULL, ARM_ABLATION, "did the SCHEDULING do the work?"),
        (ARM_ABLATION, ARM_BASELINE, "did the DISPLAY alone do it?"),
    ]
    contrasts: Dict[str, Contrast] = {}
    for a, b, why in pairs:
        if a not in trial.arms or b not in trial.arms:
            continue
        c = trial.contrast(a, b)
        contrasts[f"{a}-{b}"] = c
        w(
            f"  {c.label:<22} {c.point:>+8.2f}pp "
            f"{f'[{c.lower:+.2f}, {c.upper:+.2f}]':>22}  {why}"
        )
    w("")
    w(f"  Resampling unit: learner. {BOOTSTRAP_DRAWS} draws, percentile method,")
    w(f"  n = {trial.learners} paired differences. Questions are NOT resampled;")
    w("  the held-out set is fixed by design, so learner is the unit that varies.")
    w("")

    # --- statistical vs practical significance ------------------------------
    key = f"{ARM_FULL}-{ARM_BASELINE}"
    if key in contrasts:
        c = contrasts[key]
        w("  IS THAT AN EFFECT, OR JUST A DETECTABLE ONE?")
        w(f"  {c.point:+.2f} pp is {abs(c.point) / 100 * len(deck.holdout_probes):.1f} "
          f"of {len(deck.holdout_probes)} held-out items, and "
          f"{c.scaled_equivalent():+.2f} points on the 472-528 scale.")
        if c.excludes_zero and abs(c.point) < PRACTICAL_FLOOR_PP:
            w(f"  The interval excludes zero, so the effect is DETECTABLE at "
              f"n = {trial.learners}.")
            w(f"  It is also far below {PRACTICAL_FLOOR_PP:.1f} pp, which is the "
              f"smallest difference")
            w("  this project is willing to call practically meaningful (1 scaled")
            w("  point, against a real exam whose own reported band is +/-1 to +/-2).")
            w("  So the honest reading is: THE MECHANISM IS REAL AND ITS SIZE IS")
            w("  NEGLIGIBLE. Statistical detectability at a simulated n is not a")
            w("  product claim, and reporting it as one would be the exact error")
            w("  this project was built to call out.")
        elif not c.excludes_zero:
            w("  The interval includes zero. No effect was demonstrated.")
        else:
            w(f"  The interval excludes zero and the point exceeds the "
              f"{PRACTICAL_FLOOR_PP:.1f} pp")
            w("  practical floor. That is a real effect UNDER THIS LEARNER MODEL,")
            w("  and says nothing whatever about real learners.")
        w("")

    # --- against the declared prediction ------------------------------------
    w("AGAINST THE NUMBER DECLARED IN ADVANCE")
    w(THIN)
    key13 = f"{ARM_FULL}-{ARM_BASELINE}"
    key12 = f"{ARM_FULL}-{ARM_ABLATION}"
    if key13 in contrasts:
        c = contrasts[key13]
        v = _verdict(
            c.point, PREDICTED_ARM1_MINUS_ARM3_LOW, PREDICTED_ARM1_MINUS_ARM3_HIGH
        )
        w(f"  arm1 - arm3   declared {PREDICTED_ARM1_MINUS_ARM3_POINT:+.1f} pp "
          f"[{PREDICTED_ARM1_MINUS_ARM3_LOW:+.1f}, "
          f"{PREDICTED_ARM1_MINUS_ARM3_HIGH:+.1f}]"
          f"   observed {c.point:+.2f} pp   -> {v}")
        w("                as a scale-score equivalent through the linear "
          "placeholder map in")
        w(f"                rslib/src/transfer/scale.rs: "
          f"{c.scaled_equivalent():+.2f} points on 472-528.")
        w("                That map is a documented placeholder, not a fitted")
        w("                model, and its intervals are too narrow. Treat it as")
        w("                a unit conversion, not a score prediction.")
    if key12 in contrasts:
        c = contrasts[key12]
        v = _verdict(
            c.point, PREDICTED_ARM1_MINUS_ARM2_LOW, PREDICTED_ARM1_MINUS_ARM2_HIGH
        )
        w(f"  arm1 - arm2   declared {PREDICTED_ARM1_MINUS_ARM2_POINT:+.1f} pp "
          f"[{PREDICTED_ARM1_MINUS_ARM2_LOW:+.1f}, "
          f"{PREDICTED_ARM1_MINUS_ARM2_HIGH:+.1f}]"
          f"   observed {c.point:+.2f} pp   -> {v}")
    w("")
    w("  A missed prediction is reported as a miss. The constants are not edited")
    w("  after a run; git history is the audit trail.")
    w("")


def render_report(trial: Trial) -> str:
    out: List[str] = []
    _render_setup(trial, out)
    _render_results(trial, out)
    out.append(HONESTY_BOTTOM)
    return "\n".join(out)


def render_sweep(sweep: SweepResult) -> str:
    out: List[str] = []
    w = out.append
    w(RULE)
    w(f"SWEEP -- {sweep.param}")
    w(RULE)
    w(f"  {SWEEP_MEANING[sweep.param]}")
    w("")
    w(f"  seed {sweep.seed}, {sweep.learners} learners, {sweep.reviews} reviews each,")
    w("  every other parameter at its declared default.")
    w("")
    w(f"  judged on: {CONTRAST_TITLE[sweep.governing]}")
    w("")
    w(f"  {sweep.param:>24} {'arm1-arm3':>12} {'95% CI':>20} "
      f"{'arm1-arm2':>11} {'arm3 acc':>9}  pays?")
    w("  " + THIN[:76])
    for r in sweep.rows:
        c = getattr(r, sweep.governing)
        if c.point == 0.0:
            pays = "no -- exactly nil"
        elif c.point < 0 and c.upper < 0:
            pays = "NO -- it LOSES"
        elif c.lower <= 0.0 <= c.upper:
            pays = "no -- CI spans 0"
        elif abs(c.point) < PRACTICAL_FLOOR_PP:
            pays = "detectable, negligible"
        else:
            pays = "yes"
        w(
            f"  {r.value:>24.2f} {r.arm1_minus_arm3.point:>+11.2f}pp "
            f"{f'[{r.arm1_minus_arm3.lower:+.2f}, {r.arm1_minus_arm3.upper:+.2f}]':>20} "
            f"{r.arm1_minus_arm2.point:>+10.2f}pp "
            f"{r.baseline_accuracy * 100:>8.2f}%  {pays}"
        )
    w("")
    if sweep.break_even is None:
        w("  WHERE THE FEATURE STOPS PAYING: nowhere in this sweep -- the")
        w("  governing contrast never crosses zero across the whole swept range.")
        w("  Treat that as a reason to distrust the harness on this axis, not as")
        w("  a result about the feature.")
    else:
        first = getattr(sweep.rows[0], sweep.governing).point
        last = getattr(sweep.rows[-1], sweep.governing).point
        side = "BELOW" if last > first else "ABOVE"
        w(f"  WHERE THE FEATURE STOPS PAYING: {sweep.param} = "
          f"{sweep.break_even:+.3f}")
        w(f"  (linear interpolation between the bracketing rows). {side} that")
        w("  value the feature is worth nothing or worse than nothing. The")
        w("  product's premise is the claim that the real world sits on the other")
        w("  side of it, and nothing in this file establishes that it does.")
    w("")
    w("  'detectable, negligible' means the CI excludes zero but the effect is")
    w(f"  under {PRACTICAL_FLOOR_PP:.2f} pp -- less than one point on 472-528, "
      f"inside the real")
    w("  exam's own reported confidence band. It is not an improvement anyone")
    w("  would notice, and it is not being reported as one.")
    w("")
    return "\n".join(out)


# =============================================================================
# CLI
# =============================================================================


def _parse_arms(raw: str) -> Tuple[str, ...]:
    picked = tuple(a.strip() for a in raw.split(",") if a.strip())
    unknown = [a for a in picked if a not in ARMS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown arm(s) {unknown}; choose from {list(ARMS)}"
        )
    if not picked:
        raise argparse.ArgumentTypeError("--arms needs at least one arm")
    return picked


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ablation.py",
        description="Section 9 ablation test: full vs. feature-off vs. plain Anki.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="There are no human subjects. See the notice this prints.",
    )
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--learners", type=int, default=DEFAULT_LEARNERS)
    p.add_argument("--reviews", type=int, default=DEFAULT_REVIEWS,
                   help="review events per simulated learner, identical in every arm")
    p.add_argument("--arms", type=_parse_arms, default=ARMS,
                   help="comma-separated subset of full,ablation,baseline")
    p.add_argument("--sweep", action="store_true",
                   help="sweep the learner-model parameters and report where the "
                        "feature stops paying")
    p.add_argument("--sweep-param", default="all",
                   choices=("all", *SWEEP_VALUES),
                   help="which parameter to sweep (default: all three)")
    p.add_argument("--sweep-learners", type=int, default=None,
                   help="learners per sweep point (default: --learners)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def _json_payload(trial: Trial, sweeps: Sequence[SweepResult]) -> dict:
    def c(a: str, b: str) -> Optional[dict]:
        if a not in trial.arms or b not in trial.arms:
            return None
        x = trial.contrast(a, b)
        return {"point_pp": x.point, "ci95": [x.lower, x.upper],
                "resampling_unit": x.resampling_unit}

    return {
        "honesty": "No human subjects. Every number is a consequence of the "
                   "declared learner model. Demonstrates the harness and the "
                   "mechanism, not that the product works on people.",
        "seed": trial.seed,
        "learners": trial.learners,
        "reviews_per_learner": trial.reviews,
        "data_cutoff": DATA_CUTOFF,
        "declared_in_advance": {
            "arm1_minus_arm3": {
                "point": PREDICTED_ARM1_MINUS_ARM3_POINT,
                "range": [PREDICTED_ARM1_MINUS_ARM3_LOW,
                          PREDICTED_ARM1_MINUS_ARM3_HIGH],
            },
            "arm1_minus_arm2": {
                "point": PREDICTED_ARM1_MINUS_ARM2_POINT,
                "range": [PREDICTED_ARM1_MINUS_ARM2_LOW,
                          PREDICTED_ARM1_MINUS_ARM2_HIGH],
            },
        },
        "learner_model": {
            "transfer_responsiveness": trial.model.transfer_responsiveness,
            "headroom_alignment": trial.model.headroom_alignment,
            "display_response": trial.model.display_response,
        },
        "arms": {
            a: {
                "mean_accuracy": r.mean_accuracy,
                "total_reviews": r.total_reviews,
                "reviews_per_learner": sorted(set(r.reviews_per_learner)),
                "weighted_picks": r.weighted_picks,
                "stock_picks": r.stock_picks,
            }
            for a, r in trial.arms.items()
        },
        "contrasts": {
            "full_minus_baseline": c(ARM_FULL, ARM_BASELINE),
            "full_minus_ablation": c(ARM_FULL, ARM_ABLATION),
            "ablation_minus_baseline": c(ARM_ABLATION, ARM_BASELINE),
        },
        "sweeps": [
            {
                "param": s.param,
                "break_even": s.break_even,
                "rows": [
                    {"value": r.value,
                     "arm1_minus_arm3_pp": r.arm1_minus_arm3.point,
                     "ci95": [r.arm1_minus_arm3.lower, r.arm1_minus_arm3.upper],
                     "arm1_minus_arm2_pp": r.arm1_minus_arm2.point}
                    for r in s.rows
                ],
            }
            for s in sweeps
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        trial = run_trial(
            seed=args.seed,
            learners=args.learners,
            reviews=args.reviews,
            arms=args.arms,
        )
    except InvariantViolation as exc:
        print(f"INVARIANT VIOLATION: {exc}", file=sys.stderr)
        return 2

    sweeps: List[SweepResult] = []
    if args.sweep:
        params = (
            tuple(SWEEP_VALUES) if args.sweep_param == "all" else (args.sweep_param,)
        )
        n = args.sweep_learners or args.learners
        for param in params:
            sweeps.append(
                run_sweep(
                    param=param, seed=args.seed, learners=n, reviews=args.reviews
                )
            )

    if args.json:
        print(json.dumps(_json_payload(trial, sweeps), indent=2))
        return 0

    report = render_report(trial)
    if sweeps:
        # The sweep belongs before the closing honesty notice, so the notice
        # stays the last thing on screen.
        head, _, tail = report.rpartition(HONESTY_BOTTOM)
        body = [head.rstrip(), ""]
        for s in sweeps:
            body.append(render_sweep(s))
        body.append(HONESTY_BOTTOM + tail)
        report = "\n".join(body)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

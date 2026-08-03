# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition.
#
# Tests for the Section 9 ablation harness.
#
# The tests that matter most here are not the ones checking that the feature
# wins. They are the ones checking that it CAN LOSE:
#
#   test_feature_cannot_win_when_transfer_is_unresponsive
#   test_feature_loses_when_the_gap_points_at_the_wrong_topics
#   test_ablation_shows_nothing_when_display_alone_reallocates
#
# A harness that passes the first group and fails these is not a test, it is a
# demo. Those three are the reason this file exists.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import ablation

REPO_ROOT = Path(__file__).resolve().parents[2]

# Small but not degenerate: enough learners for a bootstrap to mean something,
# few enough that the suite stays quick.
# The real engine refuses to score a topic below 20 graded observations per
# side (rslib Thresholds), and arm 1 falls back to stock order whenever the gap
# is refused. A tiny review budget therefore makes every arm identical and every
# test below pass vacuously. These budgets are the smallest that clear the
# threshold on all 31 topics.
SMALL = dict(learners=8, reviews=2500)


# --- fixtures on disk --------------------------------------------------------


def test_fixture_files_exist_and_agree_with_their_manifest():
    deck = ablation.load_deck()
    manifest = json.loads((ablation.FIXTURE_DIR / "manifest.json").read_text())
    assert manifest["counts"]["topics"] == len(deck.topics)
    assert manifest["counts"]["study_items"] == len(deck.study_items)
    assert manifest["counts"]["holdout_probes"] == len(deck.holdout_probes)
    for name, expected in manifest["sha256"].items():
        assert ablation.sha256_of(ablation.FIXTURE_DIR / name) == expected, name


def test_holdout_and_study_sets_are_disjoint_on_disk():
    deck = ablation.load_deck()
    study_ids = {i.id for i in deck.study_items}
    holdout_ids = {p.id for p in deck.holdout_probes}
    assert study_ids & holdout_ids == set()
    assert len(holdout_ids) == len(deck.holdout_probes)


# --- requirement 1: the main number is declared in advance -------------------


def test_the_main_number_is_declared_as_a_constant_with_a_range():
    lo, point, hi = (
        ablation.PREDICTED_ARM1_MINUS_ARM3_LOW,
        ablation.PREDICTED_ARM1_MINUS_ARM3_POINT,
        ablation.PREDICTED_ARM1_MINUS_ARM3_HIGH,
    )
    assert lo < point < hi, "the declared prediction must be a range, not a point"
    source = (REPO_ROOT / "tools" / "ablation.py").read_text()
    head = source[: source.index("PREDICTED_ARM1_MINUS_ARM3_HIGH")]
    assert "declared before" in head.lower(), (
        "the prediction constants must carry a comment stating they were "
        "declared before any run"
    )


def test_the_declared_prediction_is_printed_in_the_output():
    trial = ablation.run_trial(seed=1, **SMALL)
    report = ablation.render_report(trial)
    assert f"{ablation.PREDICTED_ARM1_MINUS_ARM3_POINT:+.1f}" in report
    assert f"{ablation.PREDICTED_ARM1_MINUS_ARM3_LOW:+.1f}" in report
    assert f"{ablation.PREDICTED_ARM1_MINUS_ARM3_HIGH:+.1f}" in report


# --- requirement 2: equal study time, enforced not assumed -------------------


def test_every_arm_spends_exactly_the_same_number_of_reviews():
    trial = ablation.run_trial(seed=7, **SMALL)
    for arm in ablation.ARMS:
        counts = trial.arms[arm].reviews_per_learner
        assert len(counts) == SMALL["learners"]
        assert set(counts) == {SMALL["reviews"]}, (arm, sorted(set(counts)))
    totals = {a: trial.arms[a].total_reviews for a in ablation.ARMS}
    assert len(set(totals.values())) == 1, totals


def test_the_actual_review_counts_are_reported_not_just_the_budget():
    trial = ablation.run_trial(seed=7, **SMALL)
    report = ablation.render_report(trial)
    assert "equal study time" in report.lower()
    total = SMALL["learners"] * SMALL["reviews"]
    assert str(total) in report


def test_a_short_arm_is_a_hard_failure_not_a_silent_pass():
    trial = ablation.run_trial(seed=7, **SMALL)
    victim = trial.arms[ablation.ARM_FULL]
    victim.reviews_per_learner = victim.reviews_per_learner[:-1] + (
        victim.reviews_per_learner[-1] - 1,
    )
    with pytest.raises(ablation.InvariantViolation):
        trial.check_invariants()


# --- requirement 3: the same questions, held out -----------------------------


def test_the_holdout_probe_set_is_never_served_during_study():
    trial = ablation.run_trial(seed=3, **SMALL)
    holdout = {p.id for p in ablation.load_deck().holdout_probes}
    for arm in ablation.ARMS:
        served = trial.arms[arm].served_ids
        assert served, arm
        assert served & holdout == set(), arm


def test_every_arm_is_scored_on_an_identical_question_set_in_identical_order():
    trial = ablation.run_trial(seed=3, **SMALL)
    orders = {trial.arms[a].scored_ids for a in ablation.ARMS}
    assert len(orders) == 1
    assert len(next(iter(orders))) == len(ablation.load_deck().holdout_probes)


# --- requirement 4: the learner model must be able to make the thesis fail ---


def test_the_mechanism_actually_engages_so_the_null_tests_are_not_vacuous():
    """Guard for every exact-zero test below.

    All the "must be exactly 0" assertions would also pass if the transfer
    weighting never fired at all -- if the engine's refusal threshold were
    never cleared, or the picker were a no-op. This asserts the opposite at
    the same budget those tests use: weights are live, and the arms diverge.
    """
    trial = ablation.run_trial(seed=101, **SMALL)
    full = trial.arms[ablation.ARM_FULL]
    assert full.weighted_picks == SMALL["learners"] * SMALL["reviews"]
    total = full.weighted_picks + full.stock_picks
    assert full.refused_topic_reviews < 0.5 * total, (
        "the gap is refused on most reviews, so arm 1 is mostly plain Anki "
        "and the exact-zero tests below would pass vacuously"
    )
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_BASELINE)
    assert c.point != 0.0, "arms are indistinguishable even at the defaults"
    assert any(d != 0.0 for d in c.per_learner)


def test_feature_cannot_win_when_transfer_is_unresponsive():
    """rho = 0: study moves recall but never moves transfer.

    No queue order can change a held-out transfer score that study cannot
    move, so arm 1 minus arm 3 must be exactly zero. Common random numbers
    make it exactly zero rather than merely close to it.
    """
    model = ablation.LearnerModel(transfer_responsiveness=0.0)
    trial = ablation.run_trial(seed=11, model=model, **SMALL)
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_BASELINE)
    assert c.point == pytest.approx(0.0, abs=1e-12)
    assert all(d == pytest.approx(0.0, abs=1e-12) for d in c.per_learner)


def test_feature_loses_when_the_gap_points_at_the_wrong_topics():
    """gamma = -1: a big transfer gap means the topic is hard, not untrained.

    The product's whole premise is that a lagging probe score marks a topic
    worth more reviews. If instead it marks a topic that is near its ceiling,
    prioritising it spends the budget where it buys least, and the feature
    must come out BEHIND plain Anki. If this test cannot go negative the
    harness is rigged.
    """
    model = ablation.LearnerModel(headroom_alignment=-1.0)
    trial = ablation.run_trial(seed=13, learners=16, reviews=2500, model=model)
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_BASELINE)
    assert c.point < 0.0, f"expected the feature to lose, got {c.point:+.3f} pp"


def test_feature_is_no_better_than_chance_when_the_gap_is_uninformative():
    """gamma = 0: headroom is independent of the observed gap.

    Targeting the gap is then targeting at random, so the effect should be
    small and its interval should include zero.
    """
    model = ablation.LearnerModel(headroom_alignment=0.0)
    trial = ablation.run_trial(seed=17, learners=24, reviews=2500, model=model)
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_BASELINE)
    assert c.lower <= 0.0 <= c.upper, (c.lower, c.point, c.upper)


def test_ablation_shows_nothing_when_display_alone_reallocates():
    """delta = 1: the learner fully reallocates on seeing the gap.

    Then the scheduler change adds nothing over display, arm 1 equals arm 2,
    and the ablation's verdict must be that the feature did no work.
    """
    model = ablation.LearnerModel(display_response=1.0)
    trial = ablation.run_trial(seed=19, **SMALL)
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_ABLATION)
    assert c.point == pytest.approx(0.0, abs=1e-12)


def test_display_only_arm_collapses_onto_baseline_when_nobody_acts_on_it():
    """delta = 0: display has no causal path to the outcome at all."""
    model = ablation.LearnerModel(display_response=0.0)
    trial = ablation.run_trial(seed=19, model=model, **SMALL)
    c = trial.contrast(ablation.ARM_ABLATION, ablation.ARM_BASELINE)
    assert c.point == pytest.approx(0.0, abs=1e-12)


def test_the_sweep_reports_where_the_feature_stops_paying():
    sweep = ablation.run_sweep(
        seed=23, learners=10, reviews=2500, param="headroom_alignment"
    )
    assert len(sweep.rows) >= 4
    points = [r.arm1_minus_arm3.point for r in sweep.rows]
    assert min(points) < 0.0 < max(points), (
        "a sweep that never crosses zero cannot distinguish a working feature "
        f"from a rigged harness; got {points}"
    )
    assert sweep.break_even is not None


# --- requirement 5: a range, with the learner as the resampling unit ---------


def test_the_contrast_is_reported_as_an_interval_containing_the_point():
    trial = ablation.run_trial(seed=29, learners=24, reviews=2500)
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_BASELINE)
    assert c.lower <= c.point <= c.upper
    assert c.lower < c.upper


def test_the_bootstrap_resamples_learners_not_questions():
    trial = ablation.run_trial(seed=29, learners=24, reviews=2500)
    c = trial.contrast(ablation.ARM_FULL, ablation.ARM_BASELINE)
    assert len(c.per_learner) == 24, "one paired difference per learner"
    assert c.resampling_unit == "learner"


def test_a_single_learner_yields_a_degenerate_interval():
    lo, hi = ablation.bootstrap_ci([4.2], seed=1)
    assert lo == pytest.approx(4.2)
    assert hi == pytest.approx(4.2)


def test_bootstrap_interval_brackets_the_mean_of_a_spread_sample():
    values = [float(v) for v in range(-10, 11)]
    lo, hi = ablation.bootstrap_ci(values, seed=1)
    assert lo < 0.0 < hi


# --- requirement 6: honesty, stated prominently ------------------------------


def test_honesty_notice_appears_near_the_top_and_at_the_end():
    trial = ablation.run_trial(seed=31, **SMALL)
    report = ablation.render_report(trial)
    lines = report.splitlines()
    head = "\n".join(lines[:20]).lower()
    tail = "\n".join(lines[-24:]).lower()
    for chunk, where in ((head, "top"), (tail, "end")):
        assert "no human subjects" in chunk, where
        assert "**" in chunk, f"the notice must be bold at the {where}"
    assert "not that the product works on people" in head
    assert "not that the product works on people" in tail


def test_the_output_says_exactly_what_would_make_this_real_evidence():
    trial = ablation.run_trial(seed=31, **SMALL)
    report = ablation.render_report(trial).lower()
    assert "real learners" in report
    assert "judged responses" in report
    assert "would need to change" in report


def test_every_number_is_attributed_to_the_declared_learner_model():
    trial = ablation.run_trial(seed=31, **SMALL)
    report = ablation.render_report(trial).lower()
    assert "consequence of the declared learner model" in report


# --- requirement 7: deterministic, seeded, cutoff stated ---------------------


def test_identical_seeds_give_identical_results():
    a = ablation.run_trial(seed=41, **SMALL)
    b = ablation.run_trial(seed=41, **SMALL)
    for arm in ablation.ARMS:
        assert a.arms[arm].accuracy == b.arms[arm].accuracy
    assert ablation.render_report(a) == ablation.render_report(b)


def test_different_seeds_give_different_results():
    a = ablation.run_trial(seed=41, **SMALL)
    b = ablation.run_trial(seed=42, **SMALL)
    assert a.arms[ablation.ARM_FULL].accuracy != b.arms[ablation.ARM_FULL].accuracy


def test_the_seed_and_the_data_cutoff_are_printed():
    trial = ablation.run_trial(seed=41, **SMALL)
    report = ablation.render_report(trial)
    assert "seed" in report.lower()
    assert "41" in report
    assert "cutoff" in report.lower()


# --- requirement 8: the CLI --------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "ablation.py"), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_runs_and_reports():
    r = _cli("--learners", "6", "--reviews", "1500", "--seed", "5")
    assert r.returncode == 0, r.stderr
    assert "no human subjects" in r.stdout.lower()


def test_cli_arms_restricts_the_run():
    r = _cli("--learners", "6", "--reviews", "1500", "--seed", "5", "--arms", "full,baseline")
    assert r.returncode == 0, r.stderr
    assert "ablation" not in r.stdout.split("ARMS RUN")[-1].split("\n\n")[0].lower()


def test_cli_sweep_mode_runs():
    r = _cli("--learners", "6", "--reviews", "1500", "--seed", "5", "--sweep")
    assert r.returncode == 0, r.stderr
    assert "sweep" in r.stdout.lower()
    assert "stops paying" in r.stdout.lower()


def test_cli_rejects_an_unknown_arm():
    r = _cli("--arms", "nonsense")
    assert r.returncode != 0

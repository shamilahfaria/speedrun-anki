"""Tests for the DOK 1 vs DOK 2 paraphrase harness.

Written before `speedrun_ai/paraphrase_test.py` existed. The point of the
harness is a comparison between recall on a memorised card and accuracy on a
reworded version of the same question, so these tests pin down three things:

1. the fixture really is 30 cards x 2 substantially reworded variants,
2. the arithmetic and the intervals are right,
3. the honesty contract holds -- a run that used no human subjects says so, in
   bold, every time, and never presents its numbers as findings about learners.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from speedrun_ai import paraphrase_test as pt

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- fixture shape ----------------------------------------------------------


@pytest.fixture(scope="module")
def cardset() -> "pt.ParaphraseSet":
    return pt.load_cards()


def test_fixture_has_thirty_cards_each_with_two_variants(cardset):
    assert len(cardset.cards) == 30
    for card in cardset.cards:
        assert len(card.variants) == 2, card.id


def test_fixture_ids_are_unique(cardset):
    card_ids = [c.id for c in cardset.cards]
    assert len(set(card_ids)) == len(card_ids)
    item_ids = [item.item_id for item in cardset.items()]
    assert len(set(item_ids)) == len(item_ids) == 90


def test_fixture_declares_a_data_cutoff(cardset):
    assert cardset.data_cutoff == pt.DATA_CUTOFF
    assert cardset.authoring_note.strip()


def test_fixture_covers_the_four_named_subject_areas(cardset):
    topics = {c.topic for c in cardset.cards}
    assert {"Biochemistry", "Organic Chemistry", "Physics", "Psych/Soc"} <= topics


def test_variants_are_substantially_reworded_not_synonym_swaps(cardset):
    """A variant that reuses most of the original's content words is a synonym
    swap, and a memoriser would clear it on surface match alone."""
    for card in cardset.cards:
        for variant in card.variants:
            assert variant.front.strip() != card.front.strip()
            overlap = pt.content_overlap(card.front, variant.front)
            assert overlap <= 0.35, (variant.id, overlap)


def test_variants_are_exam_style_stems_not_bare_prompts(cardset):
    for card in cardset.cards:
        for variant in card.variants:
            assert len(variant.front.split()) >= 8, variant.id
            assert variant.back.strip()


# --- statistics -------------------------------------------------------------


def test_wilson_interval_matches_hand_computed_value():
    low, high = pt.wilson_interval(27, 30)
    assert low == pytest.approx(0.74378, abs=1e-4)
    assert high == pytest.approx(0.96541, abs=1e-4)


def test_wilson_interval_of_zero_successes_starts_at_zero():
    low, high = pt.wilson_interval(0, 20)
    assert low == 0.0
    assert 0.0 < high < 0.25


def test_wilson_interval_of_no_observations_is_the_whole_range():
    assert pt.wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_interval_rejects_impossible_counts():
    with pytest.raises(ValueError):
        pt.wilson_interval(5, 3)


def test_cluster_bootstrap_gap_ci_is_deterministic_and_brackets_the_gap():
    cards = pt.load_cards()
    responder = pt.SimulatedResponder()
    responses = responder.respond(cards)
    first = pt.cluster_bootstrap_gap_ci(cards, responses)
    second = pt.cluster_bootstrap_gap_ci(cards, responses)
    assert first == second
    report = pt.run_paraphrase_test(cards=cards, responder=responder)
    assert first[0] <= report.gap <= first[1]


# --- responders -------------------------------------------------------------


def test_simulated_responder_answers_every_item_and_is_reproducible(cardset):
    responder = pt.SimulatedResponder()
    first = responder.respond(cardset)
    second = pt.SimulatedResponder().respond(cardset)
    assert len(first) == 90
    assert [r.correct for r in first] == [r.correct for r in second]
    assert responder.is_simulated is True


def test_simulated_responder_declares_its_parameters(cardset):
    declared = pt.SimulatedResponder().declared_parameters()
    assert set(declared) >= {
        "p_correct_on_memorised_original",
        "p_correct_on_zero_overlap_rewording",
        "p_correct_on_identical_rewording",
        "seed",
    }


def test_file_responder_reads_a_supplied_response_file(tmp_path, cardset):
    payload = {
        "data_cutoff": pt.DATA_CUTOFF,
        "human_subjects": True,
        "collection_note": "collected from 12 students, spring session",
        "responses": [
            {"item_id": item.item_id, "correct": True} for item in cardset.items()
        ],
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    responder = pt.FileResponder(path)
    responses = responder.respond(cardset)
    assert len(responses) == 90
    assert responder.is_simulated is False
    assert responder.claims_human_subjects is True


def test_file_responder_rejects_a_file_missing_items(tmp_path, cardset):
    payload = {
        "data_cutoff": pt.DATA_CUTOFF,
        "human_subjects": False,
        "responses": [{"item_id": cardset.cards[0].id + "::original", "correct": True}],
    }
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        pt.FileResponder(path).respond(cardset)


def test_file_responder_rejects_a_cutoff_mismatch(tmp_path, cardset):
    payload = {
        "data_cutoff": "1999-01-01",
        "human_subjects": False,
        "responses": [
            {"item_id": item.item_id, "correct": True} for item in cardset.items()
        ],
    }
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        pt.FileResponder(path).respond(cardset)


# --- the report -------------------------------------------------------------


def test_gap_is_original_accuracy_minus_rewording_accuracy(cardset):
    report = pt.run_paraphrase_test(cards=cardset, responder=pt.SimulatedResponder())
    assert report.original_accuracy == pytest.approx(
        report.original_correct / report.original_n
    )
    assert report.rewording_accuracy == pytest.approx(
        report.rewording_correct / report.rewording_n
    )
    assert report.gap == pytest.approx(
        report.original_accuracy - report.rewording_accuracy
    )
    assert report.original_n == 30
    assert report.rewording_n == 60


def test_significance_flag_agrees_with_the_gap_interval(cardset):
    report = pt.run_paraphrase_test(cards=cardset, responder=pt.SimulatedResponder())
    excludes_zero = report.gap_ci_low > 0.0 or report.gap_ci_high < 0.0
    assert report.gap_is_significant is excludes_zero
    assert "significant" in report.significance_statement.lower()


def test_report_states_the_data_cutoff_and_the_responder(cardset):
    text = pt.run_paraphrase_test(
        cards=cardset, responder=pt.SimulatedResponder()
    ).format_text()
    assert pt.DATA_CUTOFF in text
    assert "simulated" in text.lower()


def test_simulated_report_carries_the_bold_no_human_data_statement(cardset):
    text = pt.run_paraphrase_test(
        cards=cardset, responder=pt.SimulatedResponder()
    ).format_text()
    assert pt.NO_HUMAN_DATA_STATEMENT in text
    assert pt.NO_HUMAN_DATA_STATEMENT.startswith("**")
    assert pt.NO_HUMAN_DATA_STATEMENT.endswith("**")
    lowered = pt.NO_HUMAN_DATA_STATEMENT.lower()
    assert "no human data" in lowered
    assert "illustrative" in lowered


def test_simulated_report_separates_the_declared_model_from_the_sample(cardset):
    """At n=30 and n=60 the realised rates wander well away from the declared
    probabilities. A reader must be able to see both, or a sampling artefact
    reads as a property of the model."""
    responder = pt.SimulatedResponder()
    expected = responder.expected_accuracies(cardset)
    assert expected is not None
    expected_original, expected_rewording = expected
    assert expected_original == pytest.approx(pt.SIM_P_ORIGINAL)
    assert pt.SIM_P_VARIANT_ZERO_OVERLAP <= expected_rewording <= pt.SIM_P_ORIGINAL

    report = pt.run_paraphrase_test(cards=cardset, responder=responder)
    assert report.expected_original_accuracy == pytest.approx(expected_original)
    assert report.expected_rewording_accuracy == pytest.approx(expected_rewording)
    text = report.format_text()
    assert "expected under the declared model" in text.lower()
    assert "sampling" in text.lower()


def test_file_responder_reports_no_model_expectation(tmp_path, cardset):
    payload = {
        "data_cutoff": pt.DATA_CUTOFF,
        "human_subjects": True,
        "collection_note": "collected from 12 students, spring session",
        "responses": [
            {"item_id": item.item_id, "correct": True} for item in cardset.items()
        ],
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    responder = pt.FileResponder(path)
    assert responder.expected_accuracies(cardset) is None
    report = pt.run_paraphrase_test(cards=cardset, responder=responder)
    assert report.expected_original_accuracy is None
    assert "expected under the declared model" not in report.format_text().lower()


def test_report_never_calls_simulated_numbers_findings(cardset):
    report = pt.run_paraphrase_test(cards=cardset, responder=pt.SimulatedResponder())
    text = report.format_text().lower()
    assert "not evidence about learners" in text
    assert "not a measurement" in text


def test_supplied_human_file_gets_an_unverified_provenance_warning(tmp_path, cardset):
    payload = {
        "data_cutoff": pt.DATA_CUTOFF,
        "human_subjects": True,
        "collection_note": "collected from 12 students, spring session",
        "responses": [
            {"item_id": item.item_id, "correct": True} for item in cardset.items()
        ],
    }
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    text = pt.run_paraphrase_test(
        cards=cardset, responder=pt.FileResponder(path)
    ).format_text()
    assert "cannot verify" in text.lower()
    assert "collected from 12 students" in text
    assert pt.NO_HUMAN_DATA_STATEMENT not in text


def test_report_json_is_stable_across_runs(cardset):
    first = pt.run_paraphrase_test(
        cards=cardset, responder=pt.SimulatedResponder()
    ).to_dict()
    second = pt.run_paraphrase_test(
        cards=cardset, responder=pt.SimulatedResponder()
    ).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert "timestamp" not in json.dumps(first)


# --- CLI --------------------------------------------------------------------


def test_cli_runs_and_prints_the_disclaimer():
    proc = subprocess.run(
        [sys.executable, "-m", "speedrun_ai.paraphrase_test"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert pt.NO_HUMAN_DATA_STATEMENT in proc.stdout
    assert pt.DATA_CUTOFF in proc.stdout


def test_cli_json_output_is_byte_identical_across_processes():
    cmd = [sys.executable, "-m", "speedrun_ai.paraphrase_test", "--json"]
    first = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    second = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["no_human_data_statement"] == pt.NO_HUMAN_DATA_STATEMENT
    assert payload["responder"]["simulated"] is True

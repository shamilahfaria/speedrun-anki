"""Tests for the train/test leakage check.

Written before speedrun_ai/leakage_check.py exists. They pin the three
detectors named in the requirement -- normalised-text hash for exact matches,
token Jaccard, character n-gram similarity -- plus the reporting and exit-code
contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speedrun_ai import leakage_check as lc


# --- normalisation and exact matching ---------------------------------------


def test_normalise_collapses_case_whitespace_and_punctuation():
    a = "Glycolysis takes place in the CYTOSOL."
    b = "glycolysis   takes place,  in the cytosol"
    assert lc.normalise(a) == lc.normalise(b)


def test_text_hash_is_stable_and_matches_normalised_equals():
    a = "Where does glycolysis happen?"
    b = "where does GLYCOLYSIS happen"
    assert lc.text_hash(a) == lc.text_hash(b)
    assert lc.text_hash(a) == lc.text_hash(a)
    assert lc.text_hash(a) != lc.text_hash("something else entirely")


def test_text_hash_is_not_python_salted_hash():
    # A fixed digest for a fixed input: must not vary per process.
    assert lc.text_hash("abc") == lc.text_hash("  ABC!  ")
    assert len(lc.text_hash("abc")) == 64


# --- similarity primitives ---------------------------------------------------


def test_jaccard_bounds():
    assert lc.jaccard(set(), set()) == 0.0
    assert lc.jaccard({"a"}, {"a"}) == 1.0
    assert lc.jaccard({"a", "b"}, {"c", "d"}) == 0.0
    assert lc.jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_char_ngrams_are_contiguous_windows_of_the_normalised_text():
    grams = lc.char_ngrams("ab cd", n=4)
    assert grams == {"ab c", "b cd"}


def test_char_similarity_is_dice_over_ngram_sets():
    a, b = "the mitochondrial matrix", "the mitochondrial matrix"
    assert lc.char_similarity(a, b) == pytest.approx(1.0)
    assert lc.char_similarity("aaaa", "zzzz") == 0.0
    partial = lc.char_similarity(
        "glycolysis happens in the cytosol",
        "glycolysis happens in the cytosol of the cell",
    )
    assert 0.5 < partial < 1.0


def test_containment_is_asymmetric():
    short = {"a", "b"}
    long = {"a", "b", "c", "d"}
    assert lc.containment(short, long) == 1.0
    assert lc.containment(long, short) == 0.5


# --- pair scoring ------------------------------------------------------------


def test_identical_texts_are_flagged_exact():
    pair = lc.score_pair(
        lc.Item("q1", "queries", "Glycolysis occurs in the cytosol."),
        lc.Item("p1", "corpus", "glycolysis occurs in the cytosol"),
    )
    assert pair.exact is True
    assert pair.similarity == pytest.approx(1.0)
    assert pair.flagged is True
    assert "exact" in pair.reason


def test_near_copy_is_flagged_by_similarity():
    pair = lc.score_pair(
        lc.Item("q1", "queries", "Glycolysis occurs in the cytosol and yields two ATP"),
        lc.Item("p1", "corpus", "Glycolysis occurs in the cytosol and yields 2 ATP net"),
    )
    assert pair.exact is False
    assert pair.similarity >= lc.NEAR_THRESHOLD
    assert pair.flagged is True


def test_unrelated_texts_are_not_flagged():
    pair = lc.score_pair(
        lc.Item("q1", "queries", "how does a competitive inhibitor change Km"),
        lc.Item("p1", "corpus", "The speed of sound in air is roughly 343 metres per second."),
    )
    assert pair.flagged is False
    assert pair.similarity < lc.NEAR_THRESHOLD


def test_query_copied_verbatim_inside_a_long_passage_is_flagged_by_containment():
    # Similarity alone misses this: the passage is far longer than the query,
    # so Jaccard is structurally low even though the query is a literal quote.
    query = "which enzyme catalyses the rate limiting step of glycolysis"
    passage = (
        "Metabolism review. Which enzyme catalyses the rate limiting step of "
        "glycolysis? Phosphofructokinase-1 does, and it is inhibited by ATP and "
        "citrate while being activated by AMP. Students often confuse this with "
        "hexokinase, which catalyses the first committed step but is not rate "
        "limiting under physiological conditions in most tissues of the body."
    )
    pair = lc.score_pair(lc.Item("q1", "queries", query), lc.Item("p1", "corpus", passage))
    assert pair.similarity < lc.NEAR_THRESHOLD
    assert pair.containment >= lc.CONTAINMENT_THRESHOLD
    assert pair.flagged is True
    assert "containment" in pair.reason


def test_topically_relevant_but_not_copied_is_not_flagged():
    # A retrieval corpus is SUPPOSED to answer its queries. Sharing subject
    # matter is the task, not leakage; only copied text is leakage.
    query = "where in the cell does glycolysis happen and how much ATP does it yield"
    passage = (
        "Glycolysis takes place in the cytosol and does not require oxygen. One "
        "molecule of glucose is split into two molecules of pyruvate, with a net "
        "yield of two ATP and two NADH. The rate-limiting step is catalysed by "
        "phosphofructokinase-1, which is inhibited by high levels of ATP and "
        "citrate and activated by AMP and fructose-2,6-bisphosphate."
    )
    pair = lc.score_pair(lc.Item("q1", "queries", query), lc.Item("p1", "corpus", passage))
    assert pair.flagged is False


# --- the run -----------------------------------------------------------------


def _write_fixtures(directory: Path, corpus_texts, query_texts):
    (directory / "corpus.json").write_text(
        json.dumps(
            {
                "name": "t",
                "version": 1,
                "data_cutoff": "2026-08-01",
                "passages": [
                    {"id": "p%02d" % i, "text": t} for i, t in enumerate(corpus_texts)
                ],
            }
        ),
        encoding="utf-8",
    )
    (directory / "queries.json").write_text(
        json.dumps(
            {
                "name": "t",
                "version": 1,
                "data_cutoff": "2026-08-01",
                "queries": [
                    {
                        "id": "q%02d" % i,
                        "text": t,
                        "relevant_ids": ["p00"],
                    }
                    for i, t in enumerate(query_texts)
                ],
            }
        ),
        encoding="utf-8",
    )


def test_run_on_clean_fixtures_reports_clean_and_exits_zero(tmp_path):
    _write_fixtures(
        tmp_path,
        corpus_texts=[
            "Glycolysis takes place in the cytosol with a net yield of two ATP.",
            "The citric acid cycle operates in the mitochondrial matrix.",
        ],
        query_texts=[
            "how much energy comes out of splitting one sugar molecule",
            "which compartment hosts the Krebs pathway",
        ],
    )
    report = lc.run(tmp_path)
    assert report.clean is True
    assert report.flagged == []
    assert report.exit_code == 0


def test_run_detects_an_exact_copy_and_exits_non_zero(tmp_path):
    shared = "The citric acid cycle operates in the mitochondrial matrix."
    _write_fixtures(
        tmp_path,
        corpus_texts=["Glycolysis takes place in the cytosol.", shared],
        query_texts=["which compartment hosts the Krebs pathway", shared.lower()],
    )
    report = lc.run(tmp_path)
    assert report.clean is False
    assert report.exit_code != 0
    assert any(p.exact for p in report.flagged)
    assert any(p.right_id == "p01" and p.left_id == "q01" for p in report.flagged)


def test_run_reports_top_pairs_even_when_all_are_below_threshold(tmp_path):
    _write_fixtures(
        tmp_path,
        corpus_texts=["Glycolysis takes place in the cytosol."],
        query_texts=["how much energy comes out of splitting one sugar molecule"],
    )
    report = lc.run(tmp_path)
    assert report.clean is True
    assert len(report.top_pairs) >= 1
    assert report.top_pairs[0].flagged is False


def test_run_also_checks_the_corpus_against_itself(tmp_path):
    dupe = "Glycolysis takes place in the cytosol with a net yield of two ATP."
    _write_fixtures(
        tmp_path,
        corpus_texts=[dupe, dupe.upper()],
        query_texts=["which compartment hosts the Krebs pathway"],
    )
    report = lc.run(tmp_path)
    assert report.clean is False
    assert any(
        p.left_kind == "corpus" and p.right_kind == "corpus" for p in report.flagged
    )


def test_report_text_states_method_and_thresholds(tmp_path):
    _write_fixtures(
        tmp_path,
        corpus_texts=["Glycolysis takes place in the cytosol."],
        query_texts=["which compartment hosts the Krebs pathway"],
    )
    text = lc.run(tmp_path).format_text()
    assert "sha256" in text.lower()
    assert "jaccard" in text.lower()
    assert "dice" in text.lower() or "n-gram" in text.lower()
    assert str(lc.NEAR_THRESHOLD) in text
    assert str(lc.CONTAINMENT_THRESHOLD) in text
    assert "CLEAN" in text


def test_main_returns_the_reports_exit_code(tmp_path, capsys):
    dupe = "Glycolysis takes place in the cytosol with a net yield of two ATP."
    _write_fixtures(tmp_path, corpus_texts=[dupe], query_texts=[dupe])
    assert lc.main(["--fixtures", str(tmp_path)]) != 0
    assert "LEAKAGE" in capsys.readouterr().out


def test_json_output_is_valid_json(tmp_path, capsys):
    _write_fixtures(
        tmp_path,
        corpus_texts=["Glycolysis takes place in the cytosol."],
        query_texts=["which compartment hosts the Krebs pathway"],
    )
    assert lc.main(["--fixtures", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["clean"] is True
    assert payload["near_threshold"] == lc.NEAR_THRESHOLD


# --- the real, shipped fixtures ---------------------------------------------


def test_shipped_fixtures_load_and_produce_a_report():
    # Whether they are clean is the script's job to report, not this test's job
    # to assert. This only pins that the real fixtures are checkable.
    report = lc.run()
    assert report.query_count > 0
    assert report.corpus_count > 0
    assert report.top_pairs

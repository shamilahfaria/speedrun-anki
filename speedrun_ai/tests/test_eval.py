"""Evaluation tests.

Two things matter here: the numbers are reproducible, and the report is honest
about what produced them (which embedder, which cutoff).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from speedrun_ai.eval import (
    DEFAULT_KS,
    EvalReport,
    load_fixtures,
    precision_at_k,
    recall_at_k,
    run_eval,
)
from speedrun_ai.retrieval import Bm25Retriever, EmbeddingRetriever, HashingEmbedder

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- metric arithmetic ------------------------------------------------------


def test_precision_at_k_counts_hits_over_k():
    retrieved = ["p1", "p2", "p3"]
    relevant = {"p1", "p3", "p9"}
    assert precision_at_k(retrieved, relevant, 3) == pytest.approx(2 / 3)
    assert precision_at_k(retrieved, relevant, 1) == pytest.approx(1.0)
    assert precision_at_k(retrieved, relevant, 2) == pytest.approx(0.5)


def test_precision_denominator_is_k_not_the_short_result_list():
    """Returning fewer than k results must not flatter precision@k."""
    assert precision_at_k(["p1"], {"p1", "p2"}, 5) == pytest.approx(1 / 5)


def test_recall_at_k_counts_hits_over_relevant_total():
    retrieved = ["p1", "p2", "p3"]
    relevant = {"p1", "p3", "p9"}
    assert recall_at_k(retrieved, relevant, 3) == pytest.approx(2 / 3)
    assert recall_at_k(retrieved, relevant, 1) == pytest.approx(1 / 3)


def test_metrics_handle_empty_inputs():
    assert precision_at_k([], {"p1"}, 3) == 0.0
    assert recall_at_k([], {"p1"}, 3) == 0.0
    assert recall_at_k(["p1"], set(), 3) == 0.0
    with pytest.raises(ValueError):
        precision_at_k(["p1"], {"p1"}, 0)


# --- fixtures ---------------------------------------------------------------


def test_fixtures_load_and_are_self_consistent():
    fixtures = load_fixtures()
    assert len(fixtures.corpus) >= 20
    assert len(fixtures.queries) >= 8
    ids = [p.id for p in fixtures.corpus]
    assert len(ids) == len(set(ids)), "passage ids must be unique"
    known = set(ids)
    for query in fixtures.queries:
        assert query.relevant_ids, "every query needs labelled relevant passages"
        assert query.relevant_ids <= known, (
            "query %s labels unknown passages" % query.id
        )
        assert query.text.strip()
    exams = {p.meta.get("exam") for p in fixtures.corpus}
    assert {"MCAT", "LSAT", "GMAT"} <= exams


def test_fixtures_declare_a_data_cutoff():
    fixtures = load_fixtures()
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", fixtures.data_cutoff)


# --- the report -------------------------------------------------------------


@pytest.fixture(scope="module")
def report() -> EvalReport:
    return run_eval()


def test_report_covers_both_retrievers(report):
    names = {row.retriever for row in report.rows}
    assert names == {"bm25", "embedding"}


def test_report_has_precision_and_recall_for_every_k(report):
    for row in report.rows:
        assert set(row.precision_at_k) == set(DEFAULT_KS)
        assert set(row.recall_at_k) == set(DEFAULT_KS)
        for value in list(row.precision_at_k.values()) + list(row.recall_at_k.values()):
            assert 0.0 <= value <= 1.0


def test_report_states_its_cutoff_and_embedder(report):
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", report.data_cutoff)
    assert report.embedder_name
    assert report.requires_network is False
    text = report.format_text()
    assert report.data_cutoff in text
    assert report.embedder_name in text
    assert "precision@" in text.lower()


def test_eval_is_deterministic_across_runs():
    first = run_eval()
    second = run_eval()
    assert first.to_dict() == second.to_dict()
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )


def test_eval_is_deterministic_across_processes():
    """Guards against PYTHONHASHSEED leaking into the embedder."""
    script = (
        "import json;"
        "from speedrun_ai.eval import run_eval;"
        "print(json.dumps(run_eval().to_dict(), sort_keys=True))"
    )
    outputs = []
    for seed in ("0", "12345"):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed},
            check=True,
        )
        outputs.append(completed.stdout.strip())
    assert outputs[0] == outputs[1]


def test_eval_uses_no_network_by_default(report):
    assert report.embedder_requires_network is False


def test_run_eval_accepts_injected_retrievers():
    fixtures = load_fixtures()
    custom = run_eval(
        fixtures=fixtures,
        retrievers=[Bm25Retriever(), EmbeddingRetriever(HashingEmbedder())],
        ks=(1, 2),
    )
    assert {row.retriever for row in custom.rows} == {"bm25", "embedding"}
    assert set(custom.rows[0].precision_at_k) == {1, 2}


def test_per_query_detail_is_present(report):
    for row in report.rows:
        assert len(row.per_query) == len(load_fixtures().queries)
        for detail in row.per_query:
            assert detail["query_id"]
            assert isinstance(detail["retrieved"], list)


def test_cli_runs_and_prints_the_cutoff():
    completed = subprocess.run(
        [sys.executable, "-m", "speedrun_ai.eval"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "data cutoff" in completed.stdout.lower()
    assert "bm25" in completed.stdout
    assert "embedding" in completed.stdout


def test_cli_json_output_is_parseable():
    completed = subprocess.run(
        [sys.executable, "-m", "speedrun_ai.eval", "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["data_cutoff"]
    assert len(payload["rows"]) == 2


def test_gemini_embedder_path_skips_explicitly_without_a_key(monkeypatch):
    """No key -> a clear skip, never fabricated numbers."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    completed = subprocess.run(
        [sys.executable, "-m", "speedrun_ai.eval", "--embedder", "gemini"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
    )
    combined = (completed.stdout + completed.stderr).lower()
    assert "skip" in combined
    assert completed.returncode != 0

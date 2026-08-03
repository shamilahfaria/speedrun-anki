"""Tests for the AI card check: 50 generated cards against a 50-pair gold set.

Written before `speedrun_ai/card_check.py` existed. The load-bearing claims:

1. the gold set really is 50 authored Q&A pairs and the source really is one
   document that the generated cards can be traced back to,
2. the rubric is a partition -- every card lands in exactly one of three
   buckets, and the bucket rules are written down in the code,
3. the pass threshold is a module constant, so it is fixed before any result
   exists, and the report is scored against it,
4. an LLM grader is labelled as one, with the weak-evaluation caveat attached.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from speedrun_ai import card_check as cc
from speedrun_ai.cards import CardKind
from speedrun_ai.provider import CardProvider, GenerationRequest, Suggestion

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- the cutoff, declared up front -----------------------------------------


def test_pass_threshold_is_a_module_constant_in_range():
    assert isinstance(cc.PASS_THRESHOLD_CORRECT_AND_USEFUL, float)
    assert 0.0 < cc.PASS_THRESHOLD_CORRECT_AND_USEFUL <= 1.0
    assert isinstance(cc.MAX_ACCEPTABLE_WRONG_RATE, float)
    assert 0.0 <= cc.MAX_ACCEPTABLE_WRONG_RATE < 1.0


def test_cutoff_declaration_is_documented_in_the_source_file():
    """The comment is the audit trail for 'set before you look'."""
    text = Path(cc.__file__).read_text(encoding="utf-8")
    head = text[: text.index("PASS_THRESHOLD_CORRECT_AND_USEFUL")]
    assert "before" in head.lower()
    # The declaration itself is a literal in the file, above the constants it
    # governs -- that ordering is the audit trail.
    declaration = "PASS CUTOFF DECLARED BEFORE ANY CARD WAS GENERATED OR GRADED"
    assert declaration in text
    assert declaration in cc.CUTOFF_SET_BEFORE_RESULTS_NOTE
    assert text.index(declaration) < text.index(
        "PASS_THRESHOLD_CORRECT_AND_USEFUL = "
    )


# --- gold set ---------------------------------------------------------------


@pytest.fixture(scope="module")
def gold() -> "cc.GoldSet":
    return cc.load_gold()


def test_gold_set_is_fifty_unique_pairs(gold):
    assert len(gold.pairs) == 50
    ids = [p.id for p in gold.pairs]
    assert len(set(ids)) == 50
    for pair in gold.pairs:
        assert pair.question.strip()
        assert pair.answer.strip()
        assert len(pair.question.split()) >= 5, pair.id


def test_gold_set_declares_the_same_cutoff_as_the_harness(gold):
    assert gold.data_cutoff == cc.DATA_CUTOFF


# --- source document --------------------------------------------------------


@pytest.fixture(scope="module")
def source() -> "cc.SourceDoc":
    return cc.load_source()


def test_source_is_one_document_split_into_verbatim_sections(source):
    assert source.source_id
    assert len(source.text) > 4000
    assert len(source.sections) >= 8
    for section in source.sections:
        assert section.text in source.text
        assert source.text[section.start : section.end] == section.text


def test_source_declares_the_same_cutoff(source):
    assert source.data_cutoff == cc.DATA_CUTOFF


# --- generation -------------------------------------------------------------


class EchoProvider(CardProvider):
    """Quotes each section back verbatim, so every suggestion survives the
    provenance check and the count logic is what is under test.

    Local to this file on purpose: `tests/stubs.py` replays a fixed list, and
    this needs a response that depends on the request.
    """

    name = "echo-stub"

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def describe(self) -> str:
        return "echo stub provider"

    def suggest_cards(self, request: GenerationRequest):
        from speedrun_ai.generate import sentences_with_spans

        out = []
        sentences = [s for _, _, s in sentences_with_spans(request.source_text)]
        for index, sentence in enumerate(sentences[: request.max_recall]):
            out.append(
                Suggestion(
                    front="Q%d about %s?" % (index, request.topic),
                    back=sentence,
                    kind=CardKind.RECALL,
                    quote=sentence,
                )
            )
        for index, sentence in enumerate(sentences[: request.max_probes]):
            out.append(
                Suggestion(
                    front="Apply %d: %s?" % (index, request.topic),
                    back=sentence,
                    kind=CardKind.PROBE,
                    quote=sentence,
                )
            )
        return out


def test_generate_deck_returns_exactly_the_target_number_of_cards(source):
    provider = EchoProvider()
    deck = cc.generate_deck(source, provider=provider, target=cc.TARGET_CARDS)
    assert len(deck.cards) == cc.TARGET_CARDS
    assert deck.provider_name == provider.name


def test_every_generated_card_quote_is_verbatim_in_the_whole_source(source):
    deck = cc.generate_deck(
        source, provider=EchoProvider(), target=cc.TARGET_CARDS
    )
    for card in deck.cards:
        assert card.provenance.quote in source.text


def test_generated_deck_round_trips_through_json(tmp_path, source):
    deck = cc.generate_deck(
        source, provider=EchoProvider(), target=cc.TARGET_CARDS
    )
    path = tmp_path / "deck.json"
    cc.save_deck(deck, path)
    loaded = cc.load_deck(path)
    assert [c.front for c in loaded.cards] == [c.front for c in deck.cards]
    assert loaded.provider_name == deck.provider_name
    assert loaded.data_cutoff == deck.data_cutoff


def test_card_check_pins_its_own_generation_model(monkeypatch):
    """The package default model is retired upstream (404 for new keys), so
    this harness pins a model it has actually reached rather than inheriting
    one that silently degrades every run to the offline generator."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    provider = cc.build_provider()
    assert provider.model == cc.CARD_CHECK_MODEL
    assert cc.LlmGrader().model == cc.CARD_CHECK_MODEL


def test_build_provider_is_null_without_a_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    provider = cc.build_provider()
    assert provider.available is False


def test_a_degraded_deck_is_not_reported_as_an_ai_result(gold, source):
    """If the provider fell over, the deck came from deterministic extraction.
    Reporting that as an AI card check would be the wrong claim entirely."""
    deck = cc.generate_deck(
        source,
        provider=cc.NullProvider("simulated provider outage"),
        target=cc.TARGET_CARDS,
    )
    assert deck.degraded is True
    text = cc.run_card_check(
        deck=deck, gold=gold, grader=cc.HeuristicGrader()
    ).format_text()
    lowered = text.lower()
    assert "did not come from the ai path" in lowered
    assert "simulated provider outage" in lowered


# --- the rubric -------------------------------------------------------------


def test_exactly_three_buckets_each_with_a_written_definition():
    assert len(list(cc.Bucket)) == 3
    assert set(cc.BUCKET_DEFINITIONS) == set(cc.Bucket)
    for bucket, definition in cc.BUCKET_DEFINITIONS.items():
        assert len(definition.split()) >= 15, bucket


def test_buckets_are_ordered_by_precedence_wrong_first():
    assert cc.BUCKET_PRECEDENCE[0] is cc.Bucket.WRONG
    assert set(cc.BUCKET_PRECEDENCE) == set(cc.Bucket)


def test_heuristic_grader_puts_a_numeric_contradiction_in_wrong(gold):
    card = cc.make_card(
        front="How many net ATP does glycolysis yield per glucose?",
        back="Glycolysis yields a net of 17 ATP per glucose molecule.",
    )
    grade = cc.HeuristicGrader().grade(card, references=cc.gold_references(gold, card))
    assert grade.bucket is cc.Bucket.WRONG
    assert grade.reason.strip()


def test_heuristic_grader_puts_a_non_self_contained_front_in_bad_teaching(gold):
    card = cc.make_card(
        front="Fill in the blank: This process is inhibited by _____.",
        back="ATP",
    )
    grade = cc.HeuristicGrader().grade(card, references=cc.gold_references(gold, card))
    assert grade.bucket is cc.Bucket.CORRECT_BUT_BAD_TEACHING


def test_heuristic_grader_puts_an_answer_given_away_in_bad_teaching(gold):
    card = cc.make_card(
        front="Phosphofructokinase-1 catalyses the rate-limiting step: which "
        "enzyme catalyses the rate-limiting step of glycolysis?",
        back="Phosphofructokinase-1",
    )
    grade = cc.HeuristicGrader().grade(card, references=cc.gold_references(gold, card))
    assert grade.bucket is cc.Bucket.CORRECT_BUT_BAD_TEACHING


def test_heuristic_grader_accepts_a_clean_card(gold):
    card = cc.make_card(
        front="Which enzyme catalyses the rate-limiting step of glycolysis?",
        back="Phosphofructokinase-1.",
    )
    grade = cc.HeuristicGrader().grade(card, references=cc.gold_references(gold, card))
    assert grade.bucket is cc.Bucket.CORRECT_AND_USEFUL


def test_hyphenated_terms_do_not_read_as_unsupported_answers(gold):
    """A cloze answer that is one component of a hyphenated term in the cited
    span is supported by that span. Treating it as wrong is a tokenisation
    artefact, and it inflates the wrong bucket with false positives."""
    quote = (
        "That enzyme is inhibited by ATP and by citrate, and it is activated "
        "by AMP and by fructose-2,6-bisphosphate."
    )
    card = cc.GeneratedCard.from_source(
        front="Which molecules activate phosphofructokinase-1 in the liver?",
        back="bisphosphate",
        kind=CardKind.RECALL,
        topic="Glycolysis",
        source_id="inline",
        source_text=quote,
        quote=quote,
    )
    grade = cc.HeuristicGrader().grade(card, references=cc.gold_references(gold, card))
    assert grade.bucket is not cc.Bucket.WRONG, grade.reason


def test_a_stem_opening_with_a_demonstrative_is_bad_teaching(gold):
    """'That enzyme is inhibited by...' cannot be answered by someone who is
    not already looking at the previous sentence."""
    quote = "That enzyme is inhibited by ATP and by citrate."
    card = cc.GeneratedCard.from_source(
        front="Fill in the blank: That enzyme is inhibited by _____ and by citrate.",
        back="ATP",
        kind=CardKind.RECALL,
        topic="Glycolysis",
        source_id="inline",
        source_text=quote,
        quote=quote,
    )
    grade = cc.HeuristicGrader().grade(card, references=cc.gold_references(gold, card))
    assert grade.bucket is cc.Bucket.CORRECT_BUT_BAD_TEACHING
    assert "name" in grade.reason.lower() or "refer" in grade.reason.lower()


def test_heuristic_grader_is_not_an_llm_and_says_what_it_cannot_do():
    grader = cc.HeuristicGrader()
    assert grader.is_llm is False
    assert "cannot" in grader.limitation_note.lower()


def test_llm_grader_declares_itself_and_the_weak_evaluation_caveat():
    grader = cc.LlmGrader(api_key="unused-in-this-test")
    assert grader.is_llm is True
    assert "llm" in grader.limitation_note.lower()
    assert "weak" in grader.limitation_note.lower()


def test_gold_references_are_ranked_and_capped(gold):
    card = cc.make_card(
        front="Which enzyme catalyses the rate-limiting step of glycolysis?",
        back="Phosphofructokinase-1.",
    )
    refs = cc.gold_references(gold, card, k=3)
    assert 1 <= len(refs) <= 3
    assert all(isinstance(r, cc.GoldPair) for r in refs)


# --- the report -------------------------------------------------------------


@pytest.fixture(scope="module")
def report(gold, source) -> "cc.CardCheckReport":
    deck = cc.generate_deck(
        source, provider=EchoProvider(), target=cc.TARGET_CARDS
    )
    return cc.run_card_check(deck=deck, gold=gold, grader=cc.HeuristicGrader())


def test_every_card_lands_in_exactly_one_bucket(report):
    assert sum(report.counts.values()) == cc.TARGET_CARDS
    assert set(report.counts) == set(cc.Bucket)
    assert len(report.grades) == cc.TARGET_CARDS


def test_percentages_sum_to_one_hundred(report):
    assert sum(report.percentages.values()) == pytest.approx(100.0, abs=1e-6)


def test_report_scores_itself_against_the_declared_cutoff(report):
    assert report.pass_threshold == cc.PASS_THRESHOLD_CORRECT_AND_USEFUL
    expected = (
        report.percentages[cc.Bucket.CORRECT_AND_USEFUL] / 100.0
        >= cc.PASS_THRESHOLD_CORRECT_AND_USEFUL
        and report.percentages[cc.Bucket.WRONG] / 100.0
        <= cc.MAX_ACCEPTABLE_WRONG_RATE
    )
    assert report.passed is expected


def test_report_text_states_cutoff_thresholds_and_grader(report):
    text = report.format_text()
    assert cc.DATA_CUTOFF in text
    assert cc.CUTOFF_SET_BEFORE_RESULTS_NOTE in text
    assert "%.0f%%" % (cc.PASS_THRESHOLD_CORRECT_AND_USEFUL * 100) in text
    assert report.grader_name in text
    for bucket in cc.Bucket:
        assert bucket.value in text


def test_report_with_an_llm_grader_prints_the_weak_evaluation_warning(gold, source):
    deck = cc.generate_deck(
        source, provider=EchoProvider(), target=cc.TARGET_CARDS
    )
    graded = cc.run_card_check(
        deck=deck,
        gold=gold,
        grader=cc.HeuristicGrader(),
    )
    text = graded.format_text()
    assert "not human review" in text.lower()
    assert cc.LLM_GRADING_CAVEAT not in text  # heuristic run must not claim it

    llm_like = cc.run_card_check(
        deck=deck, gold=gold, grader=_FakeLlmGrader()
    ).format_text()
    assert cc.LLM_GRADING_CAVEAT in llm_like
    assert "not human review" in llm_like.lower()


class _FakeLlmGrader(cc.Grader):
    """Stands in for `LlmGrader` so the caveat path is testable offline."""

    name = "fake-llm"
    is_llm = True
    limitation_note = cc.LLM_GRADING_CAVEAT

    def describe(self) -> str:
        return "fake llm grader"

    def grade(self, card, references):
        return cc.Grade(bucket=cc.Bucket.CORRECT_AND_USEFUL, reason="stub")


def test_report_json_is_stable_across_runs(report, gold, source):
    again = cc.run_card_check(
        deck=cc.generate_deck(
            source, provider=EchoProvider(), target=cc.TARGET_CARDS
        ),
        gold=gold,
        grader=cc.HeuristicGrader(),
    )
    assert json.dumps(report.to_dict(), sort_keys=True) == json.dumps(
        again.to_dict(), sort_keys=True
    )


# --- CLI --------------------------------------------------------------------


def test_cli_runs_offline_with_the_heuristic_grader(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "speedrun_ai.card_check",
            "--grader",
            "heuristic",
            "--offline-generation",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stderr
    assert cc.CUTOFF_SET_BEFORE_RESULTS_NOTE in proc.stdout
    assert cc.DATA_CUTOFF in proc.stdout

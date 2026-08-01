"""Card generation tests.

Central claim under test: a card without correct provenance cannot be built.
"""

import dataclasses

import pytest

from speedrun_ai.generate import (
    PROBE_TAG,
    CardKind,
    GeneratedCard,
    Provenance,
    ProvenanceError,
    generate_cards,
    topic_tag,
)
from speedrun_ai.provider import NullProvider, Suggestion
from speedrun_ai.tests.stubs import ExplodingProvider, StubProvider, WildProvider

SOURCE = (
    "Glycolysis occurs in the cytosol and converts one molecule of glucose into "
    "two molecules of pyruvate, yielding a net of two ATP and two NADH.\n\n"
    "The citric acid cycle takes place in the mitochondrial matrix, where each "
    "acetyl-CoA is oxidised to two molecules of carbon dioxide.\n\n"
    "Oxidative phosphorylation uses the proton gradient across the inner "
    "mitochondrial membrane to drive ATP synthase."
)
SOURCE_ID = "mcat-bio-metabolism-01"


def make_card(**overrides):
    kwargs = dict(
        front="Where in the cell does glycolysis occur?",
        back="In the cytosol.",
        kind=CardKind.RECALL,
        topic="Biology",
        source_id=SOURCE_ID,
        source_text=SOURCE,
        quote="Glycolysis occurs in the cytosol",
    )
    kwargs.update(overrides)
    return GeneratedCard.from_source(**kwargs)


# --- provenance is impossible to omit --------------------------------------


def test_card_cannot_be_constructed_without_a_provenance_argument():
    with pytest.raises(TypeError):
        GeneratedCard(  # type: ignore[call-arg]
            front="q",
            back="a",
            kind=CardKind.RECALL,
            topic="Biology",
        )


def test_card_rejects_none_provenance():
    with pytest.raises(ProvenanceError):
        GeneratedCard(
            front="q",
            back="a",
            kind=CardKind.RECALL,
            topic="Biology",
            provenance=None,  # type: ignore[arg-type]
        )


def test_card_rejects_a_prose_provenance_stand_in():
    with pytest.raises(ProvenanceError):
        GeneratedCard(
            front="q",
            back="a",
            kind=CardKind.RECALL,
            topic="Biology",
            provenance="somewhere in chapter 3",  # type: ignore[arg-type]
        )


def test_card_is_frozen():
    card = make_card()
    with pytest.raises(dataclasses.FrozenInstanceError):
        card.provenance = None  # type: ignore[misc]


def test_provenance_rejects_degenerate_spans():
    with pytest.raises(ProvenanceError):
        Provenance(source_id=SOURCE_ID, start=5, end=5, quote="", passage_index=0)
    with pytest.raises(ProvenanceError):
        Provenance(source_id=SOURCE_ID, start=9, end=4, quote="abc", passage_index=0)
    with pytest.raises(ProvenanceError):
        Provenance(source_id="", start=0, end=3, quote="abc", passage_index=0)
    with pytest.raises(ProvenanceError):
        Provenance(source_id=SOURCE_ID, start=-1, end=3, quote="abc", passage_index=0)


# --- provenance is correct, not merely present -----------------------------


def test_provenance_offsets_select_the_exact_span():
    card = make_card()
    prov = card.provenance
    assert SOURCE[prov.start : prov.end] == "Glycolysis occurs in the cytosol"
    assert prov.source_id == SOURCE_ID
    assert prov.passage_index == 0
    card.verify_against(SOURCE)


def test_passage_index_tracks_the_paragraph_the_quote_came_from():
    card = make_card(quote="the mitochondrial matrix")
    assert card.provenance.passage_index == 1
    assert SOURCE[card.provenance.start : card.provenance.end] == (
        "the mitochondrial matrix"
    )


def test_quote_absent_from_source_is_rejected():
    """The hallucination guard: an invented span cannot become a card."""
    with pytest.raises(ProvenanceError):
        make_card(quote="Glycolysis occurs in the mitochondrial matrix")


def test_verify_against_rejects_a_different_source_text():
    card = make_card()
    with pytest.raises(ProvenanceError):
        card.verify_against("Completely unrelated text about the LSAT.")


# --- tagging ----------------------------------------------------------------


def test_topic_tag_is_normalised():
    assert topic_tag("Organic Chemistry") == "speedrun::topic::organic_chemistry"


def test_recall_card_has_topic_tag_and_no_probe_tag():
    card = make_card(kind=CardKind.RECALL)
    assert "speedrun::topic::biology" in card.tags
    assert PROBE_TAG not in card.tags


def test_probe_card_carries_the_probe_tag():
    card = make_card(kind=CardKind.PROBE)
    assert PROBE_TAG in card.tags
    assert "speedrun::topic::biology" in card.tags


# --- generation with AI available ------------------------------------------


def stub_with_good_suggestions():
    return StubProvider(
        [
            Suggestion(
                front="Where does glycolysis occur?",
                back="In the cytosol.",
                kind=CardKind.RECALL,
                quote="Glycolysis occurs in the cytosol",
            ),
            Suggestion(
                front="Net ATP yield of glycolysis per glucose?",
                back="Two ATP.",
                kind=CardKind.RECALL,
                quote="a net of two ATP and two NADH",
            ),
            Suggestion(
                front=(
                    "A cell is treated with a drug that collapses the inner "
                    "mitochondrial proton gradient. What happens to ATP synthase "
                    "output?"
                ),
                back="It falls, because the gradient drives ATP synthase.",
                kind=CardKind.PROBE,
                quote="drive ATP synthase",
            ),
        ]
    )


def test_every_generated_card_has_valid_provenance():
    result = generate_cards(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=stub_with_good_suggestions(),
    )
    assert result.cards
    for card in result.cards:
        assert isinstance(card.provenance, Provenance)
        assert card.provenance.source_id == SOURCE_ID
        card.verify_against(SOURCE)
        assert SOURCE[card.provenance.start : card.provenance.end] == (
            card.provenance.quote
        )


def test_generation_produces_both_recall_cards_and_probes():
    result = generate_cards(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=stub_with_good_suggestions(),
    )
    kinds = {card.kind for card in result.cards}
    assert CardKind.RECALL in kinds
    assert CardKind.PROBE in kinds
    assert any(PROBE_TAG in c.tags for c in result.cards)
    assert any(PROBE_TAG not in c.tags for c in result.cards)
    assert all("speedrun::topic::biology" in c.tags for c in result.cards)
    assert result.degraded is False


def test_hallucinated_suggestion_is_dropped_and_counted_not_crashed():
    provider = StubProvider(
        [
            Suggestion(
                front="Where does glycolysis occur?",
                back="In the cytosol.",
                kind=CardKind.RECALL,
                quote="Glycolysis occurs in the cytosol",
            ),
            Suggestion(
                front="Invented",
                back="Invented",
                kind=CardKind.RECALL,
                quote="Glycolysis occurs in the nucleus",
            ),
        ]
    )
    result = generate_cards(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=provider,
    )
    assert len(result.cards) == 1
    assert result.rejected == 1
    assert any("nucleus" in reason for reason in result.rejection_reasons)


def test_note_export_shape_is_stable():
    card = make_card()
    note = card.as_note()
    assert note["front"] == card.front
    assert note["back"] == card.back
    assert set(note["tags"]) == set(card.tags)
    assert note["source_id"] == SOURCE_ID
    assert note["source_start"] == card.provenance.start
    assert note["source_end"] == card.provenance.end


# --- generation with AI disabled (hard product requirement) -----------------


def test_ai_disabled_still_produces_cards_and_flags_degraded():
    result = generate_cards(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=NullProvider("ai disabled by configuration"),
    )
    assert result.degraded is True
    assert result.cards, "system must remain usable with AI disabled"
    assert "disabled" in result.degraded_reason.lower()
    for card in result.cards:
        card.verify_against(SOURCE)
    kinds = {card.kind for card in result.cards}
    assert CardKind.RECALL in kinds
    assert CardKind.PROBE in kinds


def test_provider_failure_degrades_instead_of_crashing():
    result = generate_cards(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=ExplodingProvider(),
    )
    assert result.degraded is True
    assert result.cards
    for card in result.cards:
        card.verify_against(SOURCE)


def test_unexpected_provider_exception_also_degrades():
    result = generate_cards(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=WildProvider(),
    )
    assert result.degraded is True
    assert result.cards


def test_offline_fallback_is_deterministic():
    kwargs = dict(
        source_text=SOURCE,
        source_id=SOURCE_ID,
        topic="Biology",
        provider=NullProvider("ai disabled"),
    )
    first = generate_cards(**kwargs)
    second = generate_cards(**kwargs)
    assert [c.as_note() for c in first.cards] == [c.as_note() for c in second.cards]


def test_generate_cards_without_a_provider_argument_uses_selection(monkeypatch):
    """No key in env -> NullProvider -> degraded but working."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = generate_cards(source_text=SOURCE, source_id=SOURCE_ID, topic="Biology")
    assert result.degraded is True
    assert result.cards

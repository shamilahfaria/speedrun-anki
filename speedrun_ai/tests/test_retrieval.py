"""Retrieval tests.

The point of the module is comparability, so almost every test here is
parametrised over both retrievers: identical interface, identical inputs.
"""

import pytest

from speedrun_ai.retrieval import (
    Bm25Retriever,
    EmbeddingRetriever,
    HashingEmbedder,
    Passage,
    Retriever,
    SearchResult,
    cosine_similarity,
)

CORPUS = [
    Passage(
        id="p1",
        text=(
            "Glycolysis occurs in the cytosol and converts glucose into two "
            "molecules of pyruvate, producing a net gain of two ATP."
        ),
    ),
    Passage(
        id="p2",
        text=(
            "The citric acid cycle runs in the mitochondrial matrix and "
            "oxidises acetyl-CoA to carbon dioxide."
        ),
    ),
    Passage(
        id="p3",
        text=(
            "In a valid syllogism the conclusion follows necessarily from the "
            "premises, regardless of whether the premises are true."
        ),
    ),
    Passage(
        id="p4",
        text=(
            "A weighted average problem requires multiplying each value by its "
            "weight before dividing by the total weight."
        ),
    ),
]


def retriever_factories():
    return [
        pytest.param(Bm25Retriever, id="bm25"),
        pytest.param(lambda: EmbeddingRetriever(HashingEmbedder()), id="embedding"),
    ]


@pytest.fixture(params=retriever_factories())
def retriever(request):
    return request.param()


def test_both_implement_the_shared_interface(retriever):
    assert isinstance(retriever, Retriever)
    assert isinstance(retriever.name, str) and retriever.name
    retriever.index(CORPUS)
    results = retriever.search("glycolysis cytosol ATP", k=2)
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_before_index_raises(retriever):
    with pytest.raises(RuntimeError):
        retriever.search("anything", k=1)


def test_results_are_ranked_and_capped(retriever):
    retriever.index(CORPUS)
    results = retriever.search("mitochondrial matrix acetyl-CoA", k=3)
    assert len(results) <= 3
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in results] == list(range(1, len(results) + 1))
    assert all(r.passage.id == r.passage_id for r in results)


def test_k_larger_than_corpus_is_safe(retriever):
    retriever.index(CORPUS)
    results = retriever.search("syllogism premises", k=99)
    assert len(results) <= len(CORPUS)


def test_empty_query_does_not_crash(retriever):
    retriever.index(CORPUS)
    assert isinstance(retriever.search("   ", k=3), list)


def test_search_is_deterministic(retriever):
    retriever.index(CORPUS)
    first = retriever.search("weighted average total weight", k=4)
    second = retriever.search("weighted average total weight", k=4)
    assert [(r.passage_id, r.score) for r in first] == [
        (r.passage_id, r.score) for r in second
    ]


def test_reindexing_replaces_the_corpus(retriever):
    retriever.index(CORPUS)
    retriever.index(CORPUS[:1])
    results = retriever.search("syllogism premises", k=5)
    assert {r.passage_id for r in results} <= {"p1"}


def test_verbatim_sentence_retrieves_its_own_passage(retriever):
    """Weakest honest shared claim: an exact quote ranks its source first."""
    retriever.index(CORPUS)
    query = "the citric acid cycle runs in the mitochondrial matrix"
    results = retriever.search(query, k=3)
    assert results
    assert results[0].passage_id == "p2"


def test_empty_corpus_indexes_and_searches(retriever):
    retriever.index([])
    assert retriever.search("anything", k=3) == []


# --- pieces specific to one implementation ---------------------------------


def test_passage_validates_its_fields():
    with pytest.raises(ValueError):
        Passage(id="", text="something")
    with pytest.raises(ValueError):
        Passage(id="p1", text="  ")


def test_hashing_embedder_is_stable_across_instances():
    """Must not depend on PYTHONHASHSEED, or the eval is not reproducible."""
    a = HashingEmbedder().embed(["glycolysis occurs in the cytosol"])
    b = HashingEmbedder().embed(["glycolysis occurs in the cytosol"])
    assert a == b
    assert len(a[0]) == HashingEmbedder().dimension


def test_hashing_embedder_vectors_are_normalised():
    vector = HashingEmbedder().embed(["carbon dioxide"])[0]
    assert pytest.approx(sum(v * v for v in vector), rel=1e-9) == 1.0


def test_hashing_embedder_needs_no_network():
    assert HashingEmbedder().requires_network is False


def test_cosine_similarity_basics():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_bm25_scores_are_positive_for_matching_terms():
    retriever = Bm25Retriever()
    retriever.index(CORPUS)
    results = retriever.search("pyruvate", k=1)
    assert results and results[0].passage_id == "p1"
    assert results[0].score > 0

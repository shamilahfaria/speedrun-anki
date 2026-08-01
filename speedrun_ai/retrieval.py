"""Two retrievers over a corpus of passages, behind one interface.

`Bm25Retriever` (lexical baseline) and `EmbeddingRetriever` (dense vectors)
take the same inputs and return the same result type, so `eval.py` can compare
them without special-casing either.

Only the standard library is required. The default embedder is a local,
deterministic feature-hashing embedder that needs no network; a Gemini-backed
embedder is available but is explicitly a network path.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TOKEN_RE = re.compile(r"[a-z0-9]+")

BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> List[str]:
    """Shared tokenizer, so both retrievers see identical inputs."""
    return TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class Passage:
    id: str
    text: str
    meta: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("passage id must be a non-empty string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("passage text must be a non-empty string")


@dataclass(frozen=True)
class SearchResult:
    passage_id: str
    score: float
    rank: int
    passage: Passage


class Retriever(ABC):
    """The shared interface. Both implementations must satisfy exactly this."""

    name = "retriever"

    def __init__(self) -> None:
        self._passages: List[Passage] = []
        self._indexed = False

    @abstractmethod
    def index(self, passages: Sequence[Passage]) -> None:
        """(Re)build the index. Replaces any previously indexed corpus."""

    @abstractmethod
    def search(self, query: str, k: int = 5) -> List[SearchResult]:
        """Top-k passages, highest score first. Deterministic for equal input."""

    def _require_index(self) -> None:
        if not self._indexed:
            raise RuntimeError(
                "%s.search() called before index(); index the corpus first"
                % type(self).__name__
            )

    def _rank(self, scored: Iterable[Tuple[str, float]], k: int) -> List[SearchResult]:
        """Sort, drop non-positive scores, and number the ranks.

        Ties break on passage id so results never depend on dict ordering.
        """
        by_id = {p.id: p for p in self._passages}
        ordered = sorted(
            ((pid, score) for pid, score in scored if score > 0.0),
            key=lambda item: (-item[1], item[0]),
        )
        return [
            SearchResult(passage_id=pid, score=score, rank=position, passage=by_id[pid])
            for position, (pid, score) in enumerate(ordered[: max(0, k)], start=1)
        ]


# --- lexical baseline -------------------------------------------------------


class Bm25Retriever(Retriever):
    """Okapi BM25, pure Python, no dependencies."""

    name = "bm25"

    def __init__(self, k1: float = BM25_K1, b: float = BM25_B):
        super().__init__()
        self.k1 = k1
        self.b = b
        self._term_freqs: List[Counter] = []
        self._lengths: List[int] = []
        self._doc_freq: Counter = Counter()
        self._avg_length = 0.0

    def index(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)
        self._term_freqs = []
        self._lengths = []
        self._doc_freq = Counter()
        for passage in self._passages:
            tokens = tokenize(passage.text)
            counts = Counter(tokens)
            self._term_freqs.append(counts)
            self._lengths.append(len(tokens))
            for term in counts:
                self._doc_freq[term] += 1
        total = sum(self._lengths)
        self._avg_length = (total / len(self._lengths)) if self._lengths else 0.0
        self._indexed = True

    def _idf(self, term: str) -> float:
        n_docs = len(self._passages)
        df = self._doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 5) -> List[SearchResult]:
        self._require_index()
        query_terms = tokenize(query)
        if not query_terms or not self._passages:
            return []
        scored: List[Tuple[str, float]] = []
        for position, passage in enumerate(self._passages):
            counts = self._term_freqs[position]
            length = self._lengths[position] or 1
            score = 0.0
            for term in query_terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                denominator = tf + self.k1 * (
                    1.0 - self.b + self.b * length / (self._avg_length or 1.0)
                )
                score += self._idf(term) * (tf * (self.k1 + 1.0)) / denominator
            scored.append((passage.id, score))
        return self._rank(scored, k)


# --- embeddings -------------------------------------------------------------


class Embedder(ABC):
    """Turns text into vectors. Swappable so the eval can state what it ran."""

    name = "embedder"
    requires_network = False

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]: ...


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class HashingEmbedder(Embedder):
    """Local deterministic embeddings via the hashing trick.

    Word unigrams, word bigrams and character 4-grams are hashed with blake2b
    (NOT Python's `hash()`, which is salted per process) into a fixed-width
    signed vector, then L2-normalised. No model weights, no network, identical
    output on every machine and every run.

    It is a real dense-vector retriever, but it is lexical under the hood: it
    cannot match synonyms the way a trained embedding model can. The eval
    reports which embedder produced its numbers for exactly this reason.
    """

    name = "hashing-embedder"
    requires_network = False

    def __init__(self, dimension: int = 512):
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def _bucket(self, feature: str) -> Tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self._dimension
        sign = 1.0 if (value >> 63) & 1 else -1.0
        return index, sign

    def _features(self, text: str) -> Counter:
        tokens = tokenize(text)
        features: Counter = Counter()
        for token in tokens:
            features["w:" + token] += 1.0
        for first, second in zip(tokens, tokens[1:]):
            features["b:%s_%s" % (first, second)] += 0.5
        compact = " ".join(tokens)
        for start in range(max(0, len(compact) - 3)):
            features["c:" + compact[start : start + 4]] += 0.25
        return features

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            vector = [0.0] * self._dimension
            for feature, weight in sorted(self._features(text).items()):
                index, sign = self._bucket(feature)
                # Sublinear weighting, same idea as tf damping in BM25.
                damped = 1.0 + math.log(weight) if weight > 1.0 else weight
                vector[index] += sign * damped
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0:
                vector = [v / norm for v in vector]
            vectors.append(vector)
        return vectors


class GeminiEmbedder(Embedder):
    """Gemini embeddings. NETWORK PATH -- never used by the offline eval.

    Kept behind the same `Embedder` interface so the eval can run against it
    deliberately, with `--embedder gemini` and a key present.
    """

    name = "gemini-embedding-001"
    requires_network = True

    def __init__(
        self,
        model: str = "gemini-embedding-001",
        dimension: int = 768,
        api_key: Optional[str] = None,
    ):
        self.model = model
        self._dimension = dimension
        self._api_key = api_key
        self._client: Any = None

    @property
    def dimension(self) -> int:
        return self._dimension

    def _load_client(self) -> Any:
        if self._client is None:
            import os

            from speedrun_ai.provider import API_KEY_ENV, ProviderError

            key = self._api_key or os.environ.get(API_KEY_ENV, "").strip()
            if not key:
                raise ProviderError(
                    "no %s in the environment; cannot embed with Gemini" % API_KEY_ENV
                )
            from google import genai  # lazy: keeps the offline path importable

            self._client = genai.Client(api_key=key)
        return self._client

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        from speedrun_ai.provider import ProviderError

        client = self._load_client()
        try:
            response = client.models.embed_content(
                model=self.model,
                contents=list(texts),
                config={"output_dimensionality": self._dimension},
            )
        except Exception as exc:
            raise ProviderError(
                "Gemini embedding request failed: %s" % type(exc).__name__
            ) from None
        return [list(item.values) for item in response.embeddings]


class EmbeddingRetriever(Retriever):
    """Dense retrieval by cosine similarity over an `Embedder`."""

    name = "embedding"

    def __init__(self, embedder: Optional[Embedder] = None):
        super().__init__()
        self.embedder = embedder or HashingEmbedder()
        self._vectors: List[List[float]] = []

    @property
    def requires_network(self) -> bool:
        return self.embedder.requires_network

    def index(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)
        texts = [p.text for p in self._passages]
        self._vectors = self.embedder.embed(texts) if texts else []
        self._indexed = True

    def search(self, query: str, k: int = 5) -> List[SearchResult]:
        self._require_index()
        if not query.strip() or not self._passages:
            return []
        query_vector = self.embedder.embed([query])[0]
        scored = [
            (passage.id, cosine_similarity(query_vector, self._vectors[position]))
            for position, passage in enumerate(self._passages)
        ]
        return self._rank(scored, k)

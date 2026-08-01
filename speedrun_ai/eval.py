"""Rerunnable retrieval evaluation: keyword baseline vs. embedding retriever.

Run it:

    python -m speedrun_ai.eval
    python -m speedrun_ai.eval --json

Guarantees
----------
* Deterministic. No sampling, no timestamps in the output, no reliance on
  Python's salted `hash()`. The same fixtures give byte-identical JSON on every
  run and on every machine.
* Offline by default. The default embedder is local, so the numbers below are
  produced without a network call.
* Honest about provenance of the numbers: the report names the embedder that
  produced them and the fixture data cutoff. Running against Gemini embeddings
  is opt-in (`--embedder gemini`) and skips loudly if it cannot run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from speedrun_ai.retrieval import (
    Bm25Retriever,
    Embedder,
    EmbeddingRetriever,
    HashingEmbedder,
    Passage,
    Retriever,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_KS: Tuple[int, ...] = (1, 3, 5)


# --- metrics ----------------------------------------------------------------


def precision_at_k(retrieved: Sequence[str], relevant: FrozenSet[str], k: int) -> float:
    """Fraction of the k result slots that are relevant.

    The denominator is k, not len(retrieved): a retriever that returns two
    results when asked for five does not get credit for the empty slots.
    """
    if k <= 0:
        raise ValueError("k must be a positive integer")
    if not retrieved or not relevant:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in relevant)
    return hits / float(k)


def recall_at_k(retrieved: Sequence[str], relevant: FrozenSet[str], k: int) -> float:
    """Fraction of the relevant passages found within the top k."""
    if k <= 0:
        raise ValueError("k must be a positive integer")
    if not retrieved or not relevant:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in relevant)
    return hits / float(len(relevant))


# --- fixtures ---------------------------------------------------------------


@dataclass(frozen=True)
class LabelledQuery:
    id: str
    text: str
    relevant_ids: FrozenSet[str]


@dataclass(frozen=True)
class Fixtures:
    corpus: Tuple[Passage, ...]
    queries: Tuple[LabelledQuery, ...]
    data_cutoff: str
    cutoff_note: str = ""
    labelling_note: str = ""


def load_fixtures(directory: Optional[Path] = None) -> Fixtures:
    """Load and validate the frozen corpus + labelled query set."""
    directory = Path(directory) if directory else FIXTURES_DIR
    corpus_raw = json.loads((directory / "corpus.json").read_text(encoding="utf-8"))
    queries_raw = json.loads((directory / "queries.json").read_text(encoding="utf-8"))

    if corpus_raw["data_cutoff"] != queries_raw["data_cutoff"]:
        raise ValueError(
            "corpus and query cutoffs disagree (%s vs %s): the labels were not "
            "made against this corpus snapshot"
            % (corpus_raw["data_cutoff"], queries_raw["data_cutoff"])
        )

    passages: List[Passage] = []
    for entry in corpus_raw["passages"]:
        passages.append(
            Passage(
                id=entry["id"],
                text=entry["text"],
                meta={
                    "exam": entry.get("exam", ""),
                    "section": entry.get("section", ""),
                    "title": entry.get("title", ""),
                },
            )
        )
    known = {p.id for p in passages}
    if len(known) != len(passages):
        raise ValueError("duplicate passage ids in corpus.json")

    queries: List[LabelledQuery] = []
    for entry in queries_raw["queries"]:
        relevant = frozenset(entry["relevant_ids"])
        unknown = relevant - known
        if unknown:
            raise ValueError(
                "query %s labels passages not in the corpus: %s"
                % (entry["id"], sorted(unknown))
            )
        if not relevant:
            raise ValueError("query %s has no relevant passages" % entry["id"])
        queries.append(
            LabelledQuery(id=entry["id"], text=entry["text"], relevant_ids=relevant)
        )

    return Fixtures(
        corpus=tuple(passages),
        queries=tuple(queries),
        data_cutoff=corpus_raw["data_cutoff"],
        cutoff_note=corpus_raw.get("cutoff_note", ""),
        labelling_note=queries_raw.get("labelling_note", ""),
    )


# --- report -----------------------------------------------------------------


@dataclass(frozen=True)
class RetrieverRow:
    retriever: str
    precision_at_k: Dict[int, float]
    recall_at_k: Dict[int, float]
    per_query: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "retriever": self.retriever,
            "precision_at_k": {
                str(k): round(v, 6) for k, v in sorted(self.precision_at_k.items())
            },
            "recall_at_k": {
                str(k): round(v, 6) for k, v in sorted(self.recall_at_k.items())
            },
            "per_query": [dict(detail) for detail in self.per_query],
        }


@dataclass(frozen=True)
class EvalReport:
    rows: Tuple[RetrieverRow, ...]
    data_cutoff: str
    embedder_name: str
    embedder_requires_network: bool
    ks: Tuple[int, ...]
    corpus_size: int
    query_count: int
    cutoff_note: str = ""

    @property
    def requires_network(self) -> bool:
        return self.embedder_requires_network

    def to_dict(self) -> Dict[str, Any]:
        """Stable dict. Deliberately contains no timestamp."""
        return {
            "data_cutoff": self.data_cutoff,
            "embedder": self.embedder_name,
            "embedder_requires_network": self.embedder_requires_network,
            "ks": list(self.ks),
            "corpus_size": self.corpus_size,
            "query_count": self.query_count,
            "rows": [row.as_dict() for row in self.rows],
        }

    def format_text(self) -> str:
        lines: List[str] = []
        lines.append("Speedrun retrieval evaluation")
        lines.append("=" * 60)
        lines.append("Data cutoff: %s" % self.data_cutoff)
        lines.append(
            "Embedder: %s (network: %s)"
            % (
                self.embedder_name,
                "yes" if self.embedder_requires_network else "no",
            )
        )
        lines.append(
            "Corpus: %d passages | Queries: %d labelled"
            % (self.corpus_size, self.query_count)
        )
        lines.append("")
        header = "%-12s" % "retriever"
        for k in self.ks:
            header += "%-14s" % ("precision@%d" % k)
        for k in self.ks:
            header += "%-12s" % ("recall@%d" % k)
        lines.append(header)
        lines.append("-" * len(header))
        for row in self.rows:
            line = "%-12s" % row.retriever
            for k in self.ks:
                line += "%-14.3f" % row.precision_at_k[k]
            for k in self.ks:
                line += "%-12.3f" % row.recall_at_k[k]
            lines.append(line)
        lines.append("")
        lines.append(
            "Metrics are macro-averaged over queries. Precision@k divides by k."
        )
        if self.cutoff_note:
            lines.append("")
            lines.append("Cutoff note: %s" % self.cutoff_note)
        return "\n".join(lines)


# --- the run ----------------------------------------------------------------


def run_eval(
    fixtures: Optional[Fixtures] = None,
    retrievers: Optional[Sequence[Retriever]] = None,
    ks: Sequence[int] = DEFAULT_KS,
    embedder: Optional[Embedder] = None,
) -> EvalReport:
    """Score every retriever on the fixed query set. Deterministic."""
    fixtures = fixtures or load_fixtures()
    ks = tuple(sorted(set(int(k) for k in ks)))
    if not ks:
        raise ValueError("at least one k is required")
    embedder = embedder or HashingEmbedder()
    if retrievers is None:
        retrievers = [Bm25Retriever(), EmbeddingRetriever(embedder)]

    max_k = max(ks)
    rows: List[RetrieverRow] = []
    for retriever in retrievers:
        retriever.index(fixtures.corpus)
        precision_sums = {k: 0.0 for k in ks}
        recall_sums = {k: 0.0 for k in ks}
        per_query: List[Dict[str, Any]] = []
        for query in fixtures.queries:
            results = retriever.search(query.text, k=max_k)
            retrieved = [r.passage_id for r in results]
            for k in ks:
                precision_sums[k] += precision_at_k(retrieved, query.relevant_ids, k)
                recall_sums[k] += recall_at_k(retrieved, query.relevant_ids, k)
            per_query.append(
                {
                    "query_id": query.id,
                    "retrieved": retrieved,
                    "relevant": sorted(query.relevant_ids),
                    "hits_at_max_k": sorted(set(retrieved) & set(query.relevant_ids)),
                }
            )
        n = float(len(fixtures.queries)) or 1.0
        rows.append(
            RetrieverRow(
                retriever=retriever.name,
                precision_at_k={k: precision_sums[k] / n for k in ks},
                recall_at_k={k: recall_sums[k] / n for k in ks},
                per_query=tuple(per_query),
            )
        )

    embedding_retrievers = [r for r in retrievers if isinstance(r, EmbeddingRetriever)]
    if embedding_retrievers:
        active = embedding_retrievers[0].embedder
        embedder_name = active.name
        requires_network = bool(active.requires_network)
    else:
        embedder_name = "none"
        requires_network = False

    return EvalReport(
        rows=tuple(rows),
        data_cutoff=fixtures.data_cutoff,
        embedder_name=embedder_name,
        embedder_requires_network=requires_network,
        ks=ks,
        corpus_size=len(fixtures.corpus),
        query_count=len(fixtures.queries),
        cutoff_note=fixtures.cutoff_note,
    )


# --- CLI --------------------------------------------------------------------


def _build_embedder(choice: str) -> Embedder:
    if choice == "hashing":
        return HashingEmbedder()
    if choice == "gemini":
        from speedrun_ai.retrieval import GeminiEmbedder

        return GeminiEmbedder()
    raise ValueError("unknown embedder %r" % choice)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m speedrun_ai.eval",
        description="Compare the keyword baseline against the embedding retriever.",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit JSON instead of a table"
    )
    parser.add_argument(
        "--embedder",
        default="hashing",
        choices=["hashing", "gemini"],
        help="hashing (local, offline, default) or gemini (network, needs a key)",
    )
    parser.add_argument(
        "--ks",
        default=",".join(str(k) for k in DEFAULT_KS),
        help="comma-separated cutoffs, e.g. 1,3,5",
    )
    args = parser.parse_args(argv)

    ks = tuple(int(part) for part in args.ks.split(",") if part.strip())
    embedder = _build_embedder(args.embedder)

    if embedder.requires_network:
        # Never fabricate numbers for a path that cannot run: probe it first.
        try:
            embedder.embed(["connectivity probe"])
        except Exception as exc:
            print(
                "SKIPPED: the %s embedder could not run (%s). No numbers are "
                "reported for it. Re-run with a valid GEMINI_API_KEY and network "
                "access, or use --embedder hashing for the offline baseline."
                % (embedder.name, type(exc).__name__),
                file=sys.stderr,
            )
            return 2

    report = run_eval(ks=ks, embedder=embedder)
    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(report.format_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())

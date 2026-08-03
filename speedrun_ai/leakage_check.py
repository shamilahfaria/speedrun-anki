"""Train/test leakage check for the retrieval fixtures.

Run it:

    python -m speedrun_ai.leakage_check
    python -m speedrun_ai.leakage_check --json
    python -m speedrun_ai.leakage_check --fixtures path/to/dir

What it is for
--------------
The evaluation set (`fixtures/queries.json`) is held back. The corpus
(`fixtures/corpus.json`) is what the retrievers index -- the training data, in
the sense that matters here: it is the material the system is allowed to see.
If an evaluation item is a verbatim or near-verbatim copy of something in the
corpus, the reported precision/recall numbers measure string matching rather
than retrieval, and are worthless.

What counts as leakage, and what does not
-----------------------------------------
A retrieval corpus is *supposed* to answer its queries. Sharing subject matter
with a passage is the task, not a leak. What is a leak is copied *text*: a
query that is the passage, or a query lifted word-for-word out of one. So the
detectors below all measure textual overlap, and the containment detector works
on word trigrams -- preserving word order -- rather than on a bag of words,
because a bag of words cannot tell a quotation from a shared topic.

Method (all three run on every pair)
------------------------------------
1. Exact match: SHA-256 of the normalised text. Normalisation lowercases,
   drops punctuation, and collapses whitespace, using the same tokenizer the
   retrievers use, so "Glycolysis, in the CYTOSOL." and "glycolysis in the
   cytosol" hash identically. Any collision is a leak, full stop.
2. Near copy, symmetric: Jaccard over the normalised token sets, and
   Sorensen-Dice over the sets of character 4-grams of the normalised text.
   The pair's `similarity` is the larger of the two. Jaccard catches reordered
   copies; character n-grams catch edits inside words and small insertions.
3. Near copy, asymmetric: containment of the shorter text's word trigrams in
   the longer text's. A one-line query quoted inside a 60-word passage has low
   Jaccard by construction -- the lengths are too different -- but containment
   near 1.0. This is the detector that catches "the query was cut and pasted
   out of the corpus".

Thresholds are stated in the report and in the constants below. Pairs below
threshold are still printed, highest first, so a human can eyeball the margin
instead of trusting the cutoff.

Exits non-zero if anything is flagged.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from speedrun_ai.eval import load_fixtures
from speedrun_ai.retrieval import tokenize

# --- stated thresholds -------------------------------------------------------

#: max(token Jaccard, char-4-gram Dice) at or above this is a near copy.
NEAR_THRESHOLD = 0.60

#: Fraction of the shorter text's word trigrams found in the longer text.
#: At or above this, the shorter text is a quotation of the longer one.
CONTAINMENT_THRESHOLD = 0.90

#: Character n-gram width.
NGRAM_N = 4

#: Word n-gram width for containment.
WORD_NGRAM_N = 3

#: How many below-threshold pairs to print for eyeballing.
TOP_PAIRS = 10


# --- primitives --------------------------------------------------------------


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Uses the retrievers' tokenizer so the check sees exactly the text the
    retrievers see -- a difference here would mean checking the wrong thing.
    """
    return " ".join(tokenize(text))


def text_hash(text: str) -> str:
    """SHA-256 of the normalised text.

    Deliberately not Python's `hash()`, which is salted per process and would
    make this script's output unreproducible across runs.
    """
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def token_set(text: str) -> FrozenSet[str]:
    return frozenset(tokenize(text))


def jaccard(a, b) -> float:
    """|A n B| / |A u B|. Zero for two empty sets, by convention."""
    a, b = set(a), set(b)
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def char_ngrams(text: str, n: int = NGRAM_N) -> FrozenSet[str]:
    """Contiguous character n-grams of the normalised text."""
    compact = normalise(text)
    if len(compact) < n:
        return frozenset([compact]) if compact else frozenset()
    return frozenset(compact[i : i + n] for i in range(len(compact) - n + 1))


def dice(a, b) -> float:
    """Sorensen-Dice: 2|A n B| / (|A| + |B|)."""
    a, b = set(a), set(b)
    total = len(a) + len(b)
    if total == 0:
        return 0.0
    return 2.0 * len(a & b) / total


def char_similarity(a: str, b: str, n: int = NGRAM_N) -> float:
    return dice(char_ngrams(a, n), char_ngrams(b, n))


def containment(a, b) -> float:
    """|A n B| / |A|. Asymmetric: how much of A is inside B."""
    a, b = set(a), set(b)
    if not a:
        return 0.0
    return len(a & b) / len(a)


def word_ngrams(text: str, n: int = WORD_NGRAM_N) -> FrozenSet[str]:
    """Word n-grams of the normalised text, order preserved.

    Falls back to a smaller n for texts shorter than n words rather than
    returning nothing, so a two-word item is still comparable.
    """
    tokens = tokenize(text)
    if not tokens:
        return frozenset()
    width = min(n, len(tokens))
    return frozenset(
        " ".join(tokens[i : i + width]) for i in range(len(tokens) - width + 1)
    )


# --- items and pairs ---------------------------------------------------------


@dataclass(frozen=True)
class Item:
    id: str
    kind: str  # "queries" or "corpus"
    text: str


@dataclass(frozen=True)
class Pair:
    left_id: str
    left_kind: str
    right_id: str
    right_kind: str
    exact: bool
    token_jaccard: float
    char_dice: float
    containment: float
    left_text: str = ""
    right_text: str = ""

    @property
    def similarity(self) -> float:
        return max(self.token_jaccard, self.char_dice)

    @property
    def reason(self) -> str:
        reasons: List[str] = []
        if self.exact:
            reasons.append("exact (identical normalised text)")
        if self.similarity >= NEAR_THRESHOLD:
            reasons.append(
                "near copy (similarity %.3f >= %.2f)"
                % (self.similarity, NEAR_THRESHOLD)
            )
        if self.containment >= CONTAINMENT_THRESHOLD:
            reasons.append(
                "containment %.3f >= %.2f (shorter text quoted in longer)"
                % (self.containment, CONTAINMENT_THRESHOLD)
            )
        return "; ".join(reasons)

    @property
    def flagged(self) -> bool:
        return bool(self.reason)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "left": {"id": self.left_id, "kind": self.left_kind},
            "right": {"id": self.right_id, "kind": self.right_kind},
            "exact": self.exact,
            "token_jaccard": round(self.token_jaccard, 6),
            "char_dice": round(self.char_dice, 6),
            "containment": round(self.containment, 6),
            "similarity": round(self.similarity, 6),
            "flagged": self.flagged,
            "reason": self.reason,
        }


def score_pair(left: Item, right: Item) -> Pair:
    """Run all three detectors over one pair."""
    left_tokens, right_tokens = tokenize(left.text), tokenize(right.text)
    shorter, longer = (
        (left.text, right.text)
        if len(left_tokens) <= len(right_tokens)
        else (right.text, left.text)
    )
    return Pair(
        left_id=left.id,
        left_kind=left.kind,
        right_id=right.id,
        right_kind=right.kind,
        exact=text_hash(left.text) == text_hash(right.text),
        token_jaccard=jaccard(token_set(left.text), token_set(right.text)),
        char_dice=char_similarity(left.text, right.text),
        containment=containment(word_ngrams(shorter), word_ngrams(longer)),
        left_text=left.text,
        right_text=right.text,
    )


def _cross(left: Sequence[Item], right: Sequence[Item]) -> List[Pair]:
    return [score_pair(a, b) for a in left for b in right]


def _within(items: Sequence[Item]) -> List[Pair]:
    return [score_pair(a, b) for a, b in itertools.combinations(items, 2)]


def _ranked(pairs: Sequence[Pair]) -> List[Pair]:
    """Worst first. Ties break on ids so the report is deterministic."""
    return sorted(
        pairs,
        key=lambda p: (
            -max(p.similarity, p.containment),
            -p.similarity,
            p.left_id,
            p.right_id,
        ),
    )


# --- report ------------------------------------------------------------------


def _truncate(text: str, width: int = 76) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 3] + "..."


@dataclass(frozen=True)
class LeakageReport:
    fixtures_dir: str
    data_cutoff: str
    corpus_count: int
    query_count: int
    query_vs_corpus: Tuple[Pair, ...]
    corpus_vs_corpus: Tuple[Pair, ...]
    query_vs_query: Tuple[Pair, ...]

    @property
    def all_pairs(self) -> Tuple[Pair, ...]:
        return self.query_vs_corpus + self.corpus_vs_corpus + self.query_vs_query

    @property
    def flagged(self) -> List[Pair]:
        return [p for p in _ranked(self.all_pairs) if p.flagged]

    @property
    def top_pairs(self) -> List[Pair]:
        """Highest-similarity query-vs-corpus pairs, flagged or not."""
        return _ranked(self.query_vs_corpus)[:TOP_PAIRS]

    @property
    def clean(self) -> bool:
        return not self.flagged

    @property
    def exit_code(self) -> int:
        return 0 if self.clean else 1

    @property
    def comparisons(self) -> int:
        return len(self.all_pairs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clean": self.clean,
            "exit_code": self.exit_code,
            "fixtures_dir": self.fixtures_dir,
            "data_cutoff": self.data_cutoff,
            "corpus_count": self.corpus_count,
            "query_count": self.query_count,
            "comparisons": self.comparisons,
            "near_threshold": NEAR_THRESHOLD,
            "containment_threshold": CONTAINMENT_THRESHOLD,
            "method": {
                "exact": "sha256 of normalised text",
                "symmetric": "max(token Jaccard, char-%d-gram Dice)" % NGRAM_N,
                "asymmetric": "word-%d-gram containment, shorter in longer"
                % WORD_NGRAM_N,
            },
            "flagged": [p.as_dict() for p in self.flagged],
            "top_query_vs_corpus": [p.as_dict() for p in self.top_pairs],
        }

    def _table(self, pairs: Sequence[Pair], limit: int) -> List[str]:
        lines = [
            "  %-10s %-14s %8s %8s %8s %8s"
            % ("query", "passage", "jaccard", "char", "contain", "max"),
            "  " + "-" * 60,
        ]
        for p in _ranked(pairs)[:limit]:
            lines.append(
                "  %-10s %-14s %8.3f %8.3f %8.3f %8.3f"
                % (
                    p.left_id,
                    p.right_id,
                    p.token_jaccard,
                    p.char_dice,
                    p.containment,
                    max(p.similarity, p.containment),
                )
            )
        return lines

    def format_text(self) -> str:
        lines: List[str] = []
        lines.append("Speedrun leakage check: evaluation set vs. corpus")
        lines.append("=" * 72)
        lines.append("Fixtures    : %s" % self.fixtures_dir)
        lines.append("Data cutoff : %s" % self.data_cutoff)
        lines.append(
            "Inputs      : %d corpus passages, %d held-back queries"
            % (self.corpus_count, self.query_count)
        )
        lines.append("Comparisons : %d pairs" % self.comparisons)
        lines.append("")
        lines.append("Method")
        lines.append("-" * 72)
        lines.append(
            "  exact       sha256 of normalised text (lowercased, punctuation"
        )
        lines.append(
            "              stripped, whitespace collapsed). Any match is a leak."
        )
        lines.append(
            "  symmetric   max(token Jaccard, character %d-gram Dice) >= %.2f"
            % (NGRAM_N, NEAR_THRESHOLD)
        )
        lines.append(
            "  asymmetric  word %d-gram containment (shorter text inside longer)"
            % WORD_NGRAM_N
        )
        lines.append("              >= %.2f" % CONTAINMENT_THRESHOLD)
        lines.append("")
        lines.append(
            "  Shared subject matter is not leakage -- a retrieval corpus is meant"
        )
        lines.append(
            "  to answer its queries. Copied text is. All three detectors measure"
        )
        lines.append("  textual overlap only.")
        lines.append("")

        lines.append("Flagged pairs")
        lines.append("-" * 72)
        if not self.flagged:
            lines.append("  none")
        for p in self.flagged:
            lines.append(
                "  [%s %s] <-> [%s %s]"
                % (p.left_kind, p.left_id, p.right_kind, p.right_id)
            )
            lines.append("      %s" % p.reason)
            lines.append("      left : %s" % _truncate(p.left_text))
            lines.append("      right: %s" % _truncate(p.right_text))
        lines.append("")

        lines.append(
            "Closest query-vs-corpus pairs (top %d, below threshold included so the"
            % TOP_PAIRS
        )
        lines.append("margin is visible rather than assumed)")
        lines.append("-" * 72)
        lines.extend(self._table(self.query_vs_corpus, TOP_PAIRS))
        lines.append("")

        if self.corpus_vs_corpus:
            lines.append("Closest corpus-vs-corpus pairs (near-duplicate passages")
            lines.append("distort retrieval metrics even without test leakage)")
            lines.append("-" * 72)
            lines.extend(self._table(self.corpus_vs_corpus, 5))
            lines.append("")

        if self.query_vs_query:
            lines.append("Closest query-vs-query pairs (duplicated eval items")
            lines.append("double-count whatever they measure)")
            lines.append("-" * 72)
            lines.extend(self._table(self.query_vs_query, 5))
            lines.append("")

        lines.append("=" * 72)
        if self.clean:
            lines.append(
                "VERDICT: CLEAN -- 0 of %d pairs exceeded any threshold."
                % self.comparisons
            )
            lines.append(
                "         Highest observed: similarity %.3f, containment %.3f."
                % self._peaks()
            )
        else:
            lines.append(
                "VERDICT: LEAKAGE -- %d of %d pairs exceeded a threshold. The eval"
                % (len(self.flagged), self.comparisons)
            )
            lines.append(
                "         numbers cannot be trusted until these are removed."
            )
        return "\n".join(lines)

    def _peaks(self) -> Tuple[float, float]:
        if not self.all_pairs:
            return (0.0, 0.0)
        return (
            max(p.similarity for p in self.all_pairs),
            max(p.containment for p in self.all_pairs),
        )


# --- the run -----------------------------------------------------------------


def run(fixtures_dir: Optional[Path] = None) -> LeakageReport:
    """Compare every eval query against every corpus passage, and each set
    against itself."""
    directory = Path(fixtures_dir) if fixtures_dir else None
    fixtures = load_fixtures(directory)
    resolved = str(directory.resolve()) if directory else "speedrun_ai/fixtures"

    corpus = [Item(p.id, "corpus", p.text) for p in fixtures.corpus]
    queries = [Item(q.id, "queries", q.text) for q in fixtures.queries]

    return LeakageReport(
        fixtures_dir=resolved,
        data_cutoff=fixtures.data_cutoff,
        corpus_count=len(corpus),
        query_count=len(queries),
        query_vs_corpus=tuple(_cross(queries, corpus)),
        corpus_vs_corpus=tuple(_within(corpus)),
        query_vs_query=tuple(_within(queries)),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m speedrun_ai.leakage_check",
        description="Flag evaluation items that are copies or near copies of "
        "corpus passages.",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="fixture directory (default: speedrun_ai/fixtures)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    report = run(Path(args.fixtures) if args.fixtures else None)
    if args.json:
        print(json.dumps(report.to_dict(), sort_keys=True, indent=2))
    else:
        print(report.format_text())
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())

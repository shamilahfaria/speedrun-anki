# speedrun_ai

AI card generation and retrieval evaluation for the Speedrun study tool.

This package is self-contained. It does not import `anki`, `aqt`, `rslib` or
the protobuf layer, and it modifies nothing in them. Cards cross the boundary
as plain dicts via `GeneratedCard.as_note()`.

## Card kinds

Two kinds of card, distinguished by Anki note tags:

| Kind | Tags |
| --- | --- |
| Plain recall | `speedrun::topic::<name>` |
| Transfer probe | `speedrun::topic::<name>` **and** `speedrun::probe` |

A transfer probe is a reworded or applied variant: it tests whether the
knowledge survives a change of surface form, so recognising the original
phrasing is not enough to answer it.

## Working with AI disabled

This is a hard requirement, not a nicety. Every path degrades instead of
failing:

* `get_provider()` returns a `NullProvider` when AI is switched off, when
  `GEMINI_API_KEY` is absent, or when it is blank.
* `generate_cards()` catches **any** provider exception and falls back to
  deterministic offline extraction. It never raises because of the provider.
* The result carries `degraded=True` and a `degraded_reason` so the UI can say
  so honestly rather than silently shipping weaker cards.
* Offline cards are lower quality (blanked key terms, restate-and-apply
  probes) but carry exactly the same provenance guarantees.
* The retrieval eval's default embedder is local, so nothing here needs a
  network to run.

```python
from speedrun_ai import generate_cards, get_provider, ProviderConfig

result = generate_cards(
    source_text=chapter_text,
    source_id="mcat-bio-ch4",
    topic="Biology",
    provider=get_provider(ProviderConfig(ai_enabled=False)),
)
result.degraded  # True
[c.as_note() for c in result.cards]
```

## Provenance is structural, not conventional

Every card points at the exact span it came from. This is enforced at
construction, so an unprovenanced card cannot exist as an object:

* `GeneratedCard.provenance` has no default, so omitting it is a `TypeError`.
* `__post_init__` rejects anything that is not a `Provenance` instance, so
  `None` or a prose string like `"somewhere in chapter 3"` is a
  `ProvenanceError`.
* `GeneratedCard.from_source()` derives the character offsets by locating the
  quote in the source text. If the model returns a span that is **not** in the
  source, the card is rejected rather than created. That is the hallucination
  guard: an invented quote cannot become a card.
* `Provenance` records `source_id`, `start`, `end`, `quote` and
  `passage_index`, and `verify_against(source_text)` re-checks that
  `source_text[start:end] == quote` at any later point.

Rejected suggestions are counted in `result.rejected` with reasons in
`result.rejection_reasons` — dropped cards are visible, not silent.

## Provider

`CardProvider` is the only AI surface the rest of the code sees.
`GeminiProvider` targets **Gemini 2.5 Flash-Lite** through the `google-genai`
SDK; `NullProvider` is the disabled/keyless case. Selection is one call:

```python
provider = get_provider()  # reads env
provider = get_provider(ProviderConfig(ai_enabled=False))  # forced off
```

The key is read from `GEMINI_API_KEY`, never hardcoded. It is held in a
name-mangled private attribute and never appears in `repr()`, `str()`,
`describe()`, or any log record — `describe()` prints `key=<set:redacted>`.
SDK import and client construction are lazy, so building a `GeminiProvider`
is safe with no network and no SDK installed.

To use the live path: `pip install google-genai` and export `GEMINI_API_KEY`.

## Running the eval

```bash
cd <repo root>
python -m speedrun_ai.eval            # table
python -m speedrun_ai.eval --json     # machine-readable
python -m speedrun_ai.eval --ks 1,3,5,10
```

It compares two retrievers behind one interface on the same fixed inputs:

* `Bm25Retriever` — Okapi BM25 keyword baseline, pure Python.
* `EmbeddingRetriever` — cosine similarity over an `Embedder`.

The default embedder is `HashingEmbedder`: local, offline, deterministic
feature hashing (word unigrams, bigrams, character 4-grams) via blake2b, not
Python's per-process-salted `hash()`. **It is a dense-vector retriever but it
is lexical underneath — it has no trained semantics and cannot match synonyms
the way a real embedding model can.** The report always names the embedder
that produced its numbers, because "the embedding retriever scored X" means
nothing without that.

To evaluate real Gemini embeddings instead:

```bash
python -m speedrun_ai.eval --embedder gemini    # needs key + network
```

If that path cannot run, it prints `SKIPPED: ...` to stderr and exits `2`
without reporting numbers. It never substitutes the local embedder's results
for the network embedder's.

### Reproducibility

Given the same fixtures the eval is deterministic: no sampling, no timestamp
in the output, ties broken by passage id, and hashing that does not depend on
`PYTHONHASHSEED`. `--json` output is byte-identical across repeated runs,
across hash seeds, and across Python 3.9 and 3.12 (all three are covered by
tests).

## What the data cutoff means

`corpus.json` and `queries.json` both declare `"data_cutoff": "2026-08-01"`,
and `load_fixtures()` refuses to load if the two disagree — labels must belong
to the corpus snapshot they were judged against.

The cutoff means:

1. **The corpus is frozen at that date.** The 24 passages were hand-written
   for this fixture set, not scraped, and none describes material published
   after the cutoff.
2. **The labels were judged against that snapshot.** A passage is marked
   relevant when it contains enough to answer the query, not merely when it
   shares vocabulary. Labels are binary and complete for this corpus.
3. **Scores are only comparable within a cutoff.** Changing the corpus or the
   labels invalidates comparison with earlier runs, so bump the cutoff and the
   fixture `version` together when you edit either file, and re-baseline.

The cutoff is a property of *this fixture data*. It is not a model knowledge
cutoff and says nothing about what Gemini was trained on.

## Interpreting the numbers

`precision@k` divides by `k`, not by the number of results returned — a
retriever that returns two results when asked for five gets no credit for the
empty slots. `recall@k` divides by the number of labelled relevant passages.
Both are macro-averaged over queries (each query weighted equally).

The corpus is 24 passages and most queries have one or two relevant passages,
so `precision@5` is capped low by construction (with one relevant passage the
ceiling is 0.2). Read precision@1 and recall@3/recall@5 as the informative
columns; do not read a low precision@5 as a failure.

## Tests

```bash
python -m pytest speedrun_ai/tests -q
```

No test requires a live API key or network access; the provider is stubbed
(`speedrun_ai/tests/stubs.py`). Two tests shell out to a subprocess to check
cross-process determinism and the CLI, but only to this same package.

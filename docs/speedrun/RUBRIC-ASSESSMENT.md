# Rubric self-assessment

Graded against the assignment brief as of the Friday early submission.

Rules used, so this is worth reading:

- **MET** requires a check someone else can run and an artifact behind it. Not
  "implemented", not "should work".
- **PARTIAL** means some of the requirement is demonstrably true and some is
  not, with the gap named.
- **NOT MET** is used freely. A rubric assessment that grades its own work
  generously is worth nothing, and the whole thesis of this project is that a
  confident number without evidence behind it is a lie.

Sunday scope is graded as NOT MET rather than omitted, because the brief is one
rubric and hiding the unfinished half would misrepresent completion.

---

## 1. Functional requirements

| # | Requirement | Status | Evidence / gap |
|---|---|---|---|
| 1.1 | Three separately displayed scores, each with a confidence range | **MET** | `rslib/src/transfer/`; Wilson intervals; desktop view. `cargo test -p anki --lib transfer::` (10), `qt/tests/test_transfer_view.py` (3) |
| 1.2 | Give-up rule preventing scoring without sufficient data | **MET** | Engine-level, not display logic. `give_up_rule_refuses_to_score_thin_evidence`; refusal returns `point = 0.0` so a caller cannot render a number it never received |
| 1.3 | Real Rust-level modification to the scheduling/query engine | **MET** | New `TransferService` in `rslib`, reachable via protobuf dispatch from Python and iOS. Not a Python/UI skin |
| 1.4 | Desktop app as primary tool | **MET** | Tools → Transfer Report; installer builds and runs from a clean venv |
| 1.5 | Phone app as full-featured companion sharing the same engine | **PARTIAL** | Engine sharing is real and proven: iOS submodule pins our fork, CI compiles our `transfer` module into the iOS static library, unsigned IPA produced. **Gap:** no SwiftUI surface displays the scores. "Full-featured companion" is not yet true |
| 1.6 | Bidirectional sync, offline with reconciliation | **PARTIAL** | Inherited from amgi (sync client, offline-first, merge-on-divergence) and it compiles against our engine. **Gap:** never exercised. No device run, no reconciliation test |
| 1.7 | AI-generated cards traceable to named sources | **MET** | `Provenance` carries source id, character span, verbatim quote. Enforced by construction — adversarially verified that null/empty/inverted provenance all raise `ProvenanceError` |
| 1.8 | AI evals **beating** simpler baseline methods | **MET, with a caveat that matters** | With real `gemini-embedding-001` embeddings the retriever beats BM25 on every metric — p@1 1.000 vs 0.950, r@3 1.000 vs 0.950, r@5 1.000 vs 0.950. Results committed at `speedrun_ai/results/eval-gemini.json`. **Caveat:** the benchmark is now saturated. A perfect p@1 on 24 passages means the eval has no headroom left and can no longer discriminate between a good retriever and an excellent one; see §6.3 |
| 1.9 | App must function with AI disabled | **MET** | `NullProvider` path produces cards, marked degraded with a stated reason, each still traceable to a real span |
| 1.10 | Paraphrase / rewording test distinguishing memory from performance | **PARTIAL** | The *mechanism* exists and is tested (`speedrun::probe` partitions recall from transfer; `memory_and_performance_are_measured_separately`). **Gap:** no experiment has been run on real reworded items to show the distinction holds outside synthetic fixtures |
| 1.11 | Coverage map dashboard per exam topic | **PARTIAL** | Per-topic table with memory, performance, gap, and evidence counts. **Gap:** topics come from user tags, not from an official exam outline, so it does not yet show *coverage* — what has not been studied at all is invisible |
| 1.12 | Crash resilience, zero data corruption | **NOT MET** | Not attempted. No crash suite |
| 1.13 | Ablation test (feature on / off / baseline Anki) validating the thesis | **NOT MET** | Not attempted. This is the single most important missing item — it is the test that could show the product's premise is wrong |

**Functional: 7 MET · 4 PARTIAL · 2 NOT MET (13 items)**

---

## 2. Performance benchmarks

| # | Budget | Status | Measured |
|---|---|---|---|
| 2.1 | Dashboard first load < 1s | **MET** | 441 ms @ 50k cards / 400k reviews |
| 2.2 | Dashboard refresh < 500 ms | **MET** | 399 ms median, p95 403 ms, worst 404 ms |
| 2.3 | 50,000-card deck benchmarked (median/p95/worst) | **MET** | `tools/bench_transfer.py`, rerunnable |
| 2.4 | Button press ack p95 < 50 ms (both platforms) | **NOT MET** | Not measured |
| 2.5 | Next card render p95 < 100 ms | **NOT MET** | Not measured |
| 2.6 | Session sync < 5s | **NOT MET** | Not measured |
| 2.7 | Cold start < 5s desktop / < 4s phone | **NOT MET** | Not measured |
| 2.8 | Memory usage capped and stated for 50k deck, desktop and midrange phone | **NOT MET** | Not measured |
| 2.9 | UI never blocked > 100 ms | **NOT MET** | Not measured. Note: Anki's own watchdog fired during benchmarking before optimisation, so this needs real attention, not a rubber stamp |
| 2.10 | Zero corrupted collections in 20× crash test | **NOT MET** | Not attempted |
| 2.11 | 20-card sync test (10 phone offline + 10 desktop) landing correctly | **NOT MET** | Not attempted |

**Performance: 3 MET · 8 NOT MET (11 items)**

The three that are met are the ones our change could plausibly have broken. The
rest are inherited Anki behaviour that still has to be measured, not assumed.

---

## 3. Impact metrics

| # | Metric | Status |
|---|---|---|
| 3.1 | Memory model calibration (Brier / log-loss on held-back data) | **NOT MET** — the engine emits intervals but nothing has verified that 80% confidence is right 80% of the time |
| 3.2 | Performance prediction accuracy on held-back exam-style questions | **NOT MET** |
| 3.3 | Sync integrity: 0 lost/duplicated reviews across 20 test cards | **NOT MET** |
| 3.4 | Latency budgets | **PARTIAL** — see §2 |
| 3.5 | Crash resilience | **NOT MET** |
| 3.6 | 50k-card benchmark | **MET** |

**Impact: 1 MET · 1 PARTIAL · 4 NOT MET**

§3.1 deserves emphasis. Reporting a confidence interval that has never been
checked for calibration is exactly the failure mode this product accuses the
market of. Until it is measured, the intervals are honest in *form* only.

---

## 4. Code quality expectations

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1 | Rust unit tests, 3 minimum | **MET** | 10 |
| 4.2 | Python integration test calling the Rust function | **MET** | 4, through the real protobuf FFI, not a reimplementation |
| 4.3 | Documented rationale for why the change belongs in Rust | **MET** | `rslib/src/transfer/mod.rs` header and `SPEEDRUN.md`; the argument is reachability from the iOS FFI, not performance |
| 4.4 | Proof that undo works and the collection does not corrupt | **NOT MET** | Our service is read-only, which is a reason to expect safety, not evidence of it. Untested |
| 4.5 | Reproducible / rerunnable eval setups with stated data cutoffs | **MET** | `speedrun_ai/eval.py` — byte-identical across hash seeds and Python versions, cutoff stated in output |
| 4.6 | Leakage-check scripts (no test data contamination) | **NOT MET** | Not written |
| 4.7 | Traceability table linking features to code and measurable results | **MET** | `SPEEDRUN.md`, including a second table of claims that are *not* yet true |
| 4.8 | Clean build verified on a fresh machine | **MET** | GitHub Actions `macos-26` runner builds from nothing: 3 Rust slices, Swift, xcarchive, unsigned IPA |
| 4.9 | AGPL v3+ licensing with proper attribution to Anki | **MET** | `SPEEDRUN.md`; AGPL headers on every added file; upstream notices retained; full 12,068-commit history preserved so what was inherited is visible |

**Code quality: 7 MET · 2 NOT MET (9 items)**

---

## 5. Two-stage deadline

**Friday early submission — MET in full**

| Deliverable | Status |
|---|---|
| Brainlift v1 | MET |
| Working Rust change | MET |
| Review loop | MET |
| Desktop installer | MET |
| Syncing phone app | PARTIAL — builds against our engine, produces an IPA; sync unexercised |
| Basic AI integration | MET |

**Sunday final submission — NOT STARTED.** Calibrated memory/performance models,
thesis ablation, paraphrase/leakage/crash tests, packaged installers, updated
Brainlift.

---

## 6. The most important gaps, ranked

1. **No ablation test.** The thesis is unfalsified — not because it survived a
   test, but because no test has been run. Everything else is downstream of
   this.
2. **No calibration.** Intervals are reported without evidence they are
   calibrated. This is the project's own accusation pointed back at it.
3. **The retrieval benchmark is saturated and no longer informative.** With real
   embeddings the requirement is met (p@1 1.000 vs BM25's 0.950), but a perfect
   score is a warning, not a victory: on 24 passages with 20 queries there is
   nothing left to measure. Two things follow. First, the *margin* is one query
   — far too thin to claim embeddings are meaningfully better here. Second, and
   more important, the queries share vocabulary with their passages, so the
   benchmark rewards lexical overlap — which is exactly the capability this
   product argues is the wrong one. A tool whose thesis is *knowledge must
   survive a change of surface form* should be evaluated on paraphrased
   queries. Until it is, the eval measures something adjacent to what matters.
   Fixing this means a larger corpus and deliberately reworded queries, and it
   is a change that could make our own numbers worse.
4. **Sync never exercised.** The strongest untested claim in the project.
5. **Most latency budgets unmeasured**, including the "UI never blocked" one,
   which the pre-optimisation benchmark suggests deserves genuine scrutiny.
6. **No crash or leakage testing.**

---

## 7. Honest overall position

Counting the whole rubric — Friday and Sunday together — roughly **18 MET, 6
PARTIAL, 16 NOT MET**.

That is the correct shape for a Friday early submission whose entire second
stage is the evidence layer, and it should not be read as a mid-project grade of
50%. The Friday bar itself is met. What is missing is almost entirely the
Sunday deliverable: the machinery that would prove the thesis rather than
implement it.

The strongest part of the work is that the honesty guarantee is enforced
structurally rather than promised — the engine refuses to emit a score it cannot
support, the desktop is tested against leaking a refusal as `0%`, and the iOS
domain type models a score as an enum so the compiler forbids reading a refusal
as a number.

The weakest part is that the product's central claim remains **unmeasured**. A
tool whose pitch is calibrated honesty currently ships uncalibrated intervals.
That is the first thing Sunday should fix.

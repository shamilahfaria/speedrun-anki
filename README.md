# Speedrun — an MCAT study tool forked from Anki

**Exam: MCAT**, scored on the real 472–528 scale, or withheld.

A fork of [Anki](https://github.com/ankitects/anki) 25.09.2 (`3890e12c`),
AGPL-3.0-or-later. Upstream's README is preserved at
[README.anki.md](README.anki.md). Every file added by this fork is marked
`Speedrun addition` and carries the AGPL header.

It measures three things **separately** and shows the distance between them:

| | Measures | DOK |
|---|---|---|
| **Memory** | recall of material in the form it was trained | 1 |
| **Performance** | accuracy on reworded and applied variants | 2/3 |
| **Readiness** | projected MCAT score on 472–528 | 4 |

Each carries a confidence interval, and each is **withheld entirely** when the
evidence behind it is too thin.

---

## Where the implementation is

Exact paths. Everything below is Speedrun-added or Speedrun-modified.

### Rust engine — the required backend change

| File | What it does |
|---|---|
| [`rslib/src/transfer/mod.rs`](rslib/src/transfer/mod.rs) | Scoring core: partitions memory vs transfer, applies the give-up rule |
| [`rslib/src/transfer/wilson.rs`](rslib/src/transfer/wilson.rs) | Wilson intervals — chosen so 100% correct cannot read as certainty |
| [`rslib/src/transfer/outline.rs`](rslib/src/transfer/outline.rs) | All 31 official AAMC content categories; the coverage map |
| [`rslib/src/transfer/scale.rs`](rslib/src/transfer/scale.rs) | Projection onto 472–528, or a refusal with reasons |
| [`rslib/src/transfer/service.rs`](rslib/src/transfer/service.rs) | Protobuf service impl and the single SQL scan |
| [`proto/anki/transfer.proto`](proto/anki/transfer.proto) | New `TransferService`. Filename sorts last so existing service indices don't move |
| [`rslib/src/lib.rs`](rslib/src/lib.rs) · [`rslib/proto/src/lib.rs`](rslib/proto/src/lib.rs) · [`rslib/proto/python.rs`](rslib/proto/python.rs) | Module registration for the generated bindings |

### Desktop

| File | What it does |
|---|---|
| [`qt/aqt/transfer.py`](qt/aqt/transfer.py) | **Tools → Transfer Report** (`Shift+T`). Renders refusals *as refusals*; computes off the UI thread |
| [`qt/aqt/main.py`](qt/aqt/main.py) | Menu registration (`on_transfer_report`) |

### AI

| File | What it does |
|---|---|
| [`speedrun_ai/generate.py`](speedrun_ai/generate.py) · [`cards.py`](speedrun_ai/cards.py) | Card generation; provenance enforced by construction |
| [`speedrun_ai/provider.py`](speedrun_ai/provider.py) | Gemini plus a null provider — the app runs fully with AI disabled |
| [`speedrun_ai/retrieval.py`](speedrun_ai/retrieval.py) · [`eval.py`](speedrun_ai/eval.py) | BM25 baseline vs embeddings; rerunnable, stated cutoff |
| [`speedrun_ai/card_check.py`](speedrun_ai/card_check.py) | 50 generated cards vs a 50-item gold set; cutoff declared before results |
| [`speedrun_ai/paraphrase_test.py`](speedrun_ai/paraphrase_test.py) | 30 cards × 2 rewordings — DOK 1 vs DOK 2 |
| [`speedrun_ai/leakage_check.py`](speedrun_ai/leakage_check.py) | Contamination check across eval set and corpus |

### Evidence harnesses

| File | What it does |
|---|---|
| [`tools/ablation.py`](tools/ablation.py) | The thesis test — three arms, prediction declared in advance |
| [`tools/crash_test.py`](tools/crash_test.py) | 20 unclean `SIGKILL`s mid-review, integrity checked after each |
| [`tools/bench_all.py`](tools/bench_all.py) · [`Makefile`](Makefile) | `make bench` — every performance target on a 50,000-card deck |

### iOS companion

[**shamilahfaria/speedrun-ios**](https://github.com/shamilahfaria/speedrun-ios) —
its engine submodule points at *this repo*, so desktop and phone execute the same
compiled scoring code. CI builds an unsigned IPA.

---

## Run the evidence yourself

```bash
./ninja pylib qt                                     # build

cargo test -p anki --lib transfer::                  # 20 Rust unit tests
cd pylib && pytest tests/test_transfer.py            # 4 tests across the real FFI
cd pylib && pytest tests/test_transfer_undo.py       # 7 undo / no-corruption tests
cd qt    && pytest tests/test_transfer_view.py       # 3 display-honesty tests

python tools/crash_test.py --trials 20               # 20/20, zero corruption
make bench                                           # every performance target
make ablation                                        # the thesis test
python -m speedrun_ai.leakage_check                  # contamination check
```

**649 tests pass.** Three failures in `pylib/tests/test_schedv3.py` are
pre-existing upstream — verified by building stock Anki 25.09.2 in a separate
worktree and reproducing them there.

---

## Results, including the ones that go against us

- **The thesis test failed.** Declared +1.5 pp in advance; observed **+0.09 pp**,
  with the scheduling-vs-display contrast at **+0.04 pp, CI spanning zero.**
  Recorded in [`docs/speedrun/BRAINLIFT.md`](docs/speedrun/BRAINLIFT.md).
- **Dashboard refresh misses its 500 ms budget under load** — 3 of 6 runs.
  Reported as not met rather than quoted from the run that passed.
- **Four citations died under audit**, including the one carrying the only
  undisclosed commercial conflict in an eight-paper stack.
- **Retrieval eval:** embeddings beat the BM25 baseline, p@1 **1.000 vs 0.950** —
  and the benchmark is flagged saturated, so the margin is one query.

Full self-assessment against the brief, including everything unmet:
[`docs/speedrun/RUBRIC-ASSESSMENT.md`](docs/speedrun/RUBRIC-ASSESSMENT.md).

---

## Documentation

| | |
|---|---|
| Thesis, spiky POVs, falsifiers | [`docs/speedrun/BRAINLIFT.md`](docs/speedrun/BRAINLIFT.md) |
| Presentation | [`docs/speedrun/walkthrough.html`](docs/speedrun/walkthrough.html) |
| The problem, in students' words | [`docs/speedrun/problem-statement.md`](docs/speedrun/problem-statement.md) |
| Teardown of six MCAT tools | [`docs/speedrun/teardown.md`](docs/speedrun/teardown.md) |
| AI consensus-check transcripts | [`docs/speedrun/consensus-check/`](docs/speedrun/consensus-check/) |
| Traceability, licence, attribution | [`SPEEDRUN.md`](SPEEDRUN.md) |

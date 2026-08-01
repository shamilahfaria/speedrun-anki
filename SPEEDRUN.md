# Speedrun

A study tool for MCAT/LSAT/GMAT preparation, forked from Anki.

It measures three things separately and shows the distance between them:

| | What it measures | Depth of knowledge |
|---|---|---|
| **Memory** | recall of material in the form it was trained | DOK 1 |
| **Performance** | accuracy on reworded and applied variants | DOK 2/3 |
| **Readiness** | projected exam outcome | DOK 4 |

Each is reported with a confidence interval, and each is withheld entirely when
the evidence behind it is too thin.

---

## Attribution and licence

Speedrun is a fork of **[Anki](https://github.com/ankitects/anki)** by Ankitects
Pty Ltd and contributors, based on release **25.09.2** (`3890e12c`).

Anki is licensed under the **GNU Affero General Public License, version 3 or
later**, and Speedrun is distributed under the same terms. The full licence text
is in [LICENSE](LICENSE); third-party components retain their own licences,
including several under the BSD 3-clause licence, recorded in
[LICENSE.logo](LICENSE.logo) and the per-directory notices they ship with.

Every file added by this fork carries the AGPL header and is marked
`Speedrun addition`. All original Anki copyright notices are retained unmodified.

The iOS companion is a fork of **[amgi](https://github.com/antigluten/amgi)**,
also AGPL-3.0, which wraps the same Anki Rust backend through a C FFI.

**Source availability:** the AGPL requires that users interacting with this
software over a network be offered the corresponding source. Speedrun runs
locally and syncs to a user-controlled server; the complete source is this
repository.

---

## Traceability

Every claim about this fork, mapped to the code that implements it and the check
that proves it.

| Claim | Code | Verified by |
|---|---|---|
| Memory, performance and readiness are computed separately | `rslib/src/transfer/mod.rs` (`build_report`) | `cargo test -p anki --lib transfer::` — `memory_and_performance_are_measured_separately` |
| Confidence intervals are honest at small n and at 100% | `rslib/src/transfer/wilson.rs` | `perfect_score_does_not_claim_certainty`, `matches_reference_values` |
| The engine refuses to score thin evidence | `rslib/src/transfer/mod.rs` (`score_reviews`, `Thresholds`) | `give_up_rule_refuses_to_score_thin_evidence` |
| A gap against a refused score is not reported | `rslib/src/transfer/mod.rs` (`gap_valid`) | `gap_is_invalid_when_either_side_was_refused` |
| Unattributable reviews do not inflate readiness | `rslib/src/transfer/mod.rs` (`build_report`) | `untagged_reviews_do_not_inflate_readiness` |
| Manual reschedules are not counted as answers | `rslib/src/transfer/service.rs` (`GRADED_REVIEWS_SQL`) | `pylib/tests/test_transfer.py::test_manual_reschedules_are_excluded` |
| Rust is callable from Python across the real FFI | generated `_backend_generated.py` → `rslib` | `pylib/tests/test_transfer.py` (4 tests) |
| Refusals display as refusals, never as 0% | `qt/aqt/transfer.py` (`_score_cell`) | `qt/tests/test_transfer_view.py::test_refusal_is_shown_as_a_refusal` |
| Existing protobuf service indices are unchanged | `proto/anki/transfer.proto` (filename sorts last) | generated `backend.rs` dispatch table: sync=1, scheduler=13, stats=41, tags=43 unmoved; transfer=45 |
| Desktop and phone run one engine, not two | iOS `anki-upstream` submodule → this repo, branch `speedrun` | `git submodule status` in the iOS repo pins `a84fb5e` |
| The iOS companion actually builds against our engine | [speedrun-ios](https://github.com/shamilahfaria/speedrun-ios) CI | Run 30712722654: all steps green, `aarch64-apple-ios` + `-ios-sim` + `-watchos-sim` slices built, 28.2 MB unsigned IPA produced on a clean runner |
| The build is reproducible on a fresh machine | same CI run | GitHub `macos-26` runner starts from nothing: clones, installs toolchains, builds end to end |
| Transfer report meets its latency budget | `tools/bench_transfer.py` | 50,000 cards / 400,000 reviews: 441 ms cold (budget 1000 ms), 399 ms warm median (budget 500 ms), p95 403 ms |

Not yet true, and listed here rather than omitted:

| Claim | Status |
|---|---|
| iOS companion **syncs** end to end | **Unverified.** It builds and the engine is wired in, but no device run has exercised bidirectional sync or offline reconciliation. |
| The iOS app **displays** the three scores | **Not implemented.** The request factory and domain types exist; no SwiftUI surface calls them yet. |
| Readiness is weighted by the official exam outline | **Not implemented.** Readiness pools probe results across topics and is labelled a floor, not a prediction. |
| Models are calibrated (Brier / log loss on held-back data) | **Not started.** Sunday scope. |
| Ablation test validating the thesis | **Not started.** Sunday scope. Failure modes stated in advance in `BRAINLIFT.md`. |

---

## Why the engine change is in Rust

The iOS client reaches Anki only through a C FFI into `rslib`, dispatching by
protobuf service and method index. Anything implemented in `pylib` is
structurally unreachable from the phone.

So a scoring model written in Python would have to be reimplemented in Swift:
two implementations of one statistical model, drifting apart, capable of
reporting two different readiness numbers for the same collection. Writing it in
`rslib` means desktop and phone execute the same compiled code by construction,
and neither can drift from the other.

Secondarily, scoring scans the entire review log — millions of rows on a
50,000-card collection — against a sub-second budget. That is a scan-and-reduce
that belongs next to SQLite rather than across a serialisation boundary. This is
the weaker of the two arguments and is not why the code lives there.

---

## Marking cards

Speedrun uses note tags rather than a schema change, so everything below syncs,
survives import/export, and needs no migration:

- `speedrun::topic::<name>` — attributes a note to an exam topic.
- `speedrun::probe` — marks a note as a transfer probe: a reworded or applied
  variant of material tested elsewhere.

Untagged notes are treated as plain recall items. Reviews with no topic tag are
excluded from scoring entirely, because they cannot be attributed to exam
content and counting them would inflate the evidence behind a score without
adding evidence about anything.

---

## Building

Requires Rust 1.89 (pinned in `rust-toolchain.toml`), Python 3.9+, and protobuf.

```
./ninja pylib qt      # build
./ninja wheels        # distributable wheels into out/wheels/
./run                 # launch
```

Tests:

```
cargo test -p anki --lib transfer::                      # Rust unit tests
cd pylib && pytest tests/test_transfer.py                # Python across the FFI
cd qt   && pytest tests/test_transfer_view.py            # display honesty
```

```
pytest speedrun_ai/tests                                 # AI slice, no key needed
python -m speedrun_ai.eval                               # retrieval comparison
```

The transfer report is under **Tools → Transfer Report** (`Shift+T`).

### Known upstream test failures

`pylib/tests/test_schedv3.py` fails three tests — `test_button_spacing`,
`test_nextIvl`, `test_failmult` — on this base. These are **pre-existing in stock
Anki 25.09.2 and are not caused by this fork.** Verified by building the
unmodified base commit in a separate worktree and running the same suite:

| tree | result |
|---|---|
| stock 25.09.2 | 3 failed, 86 passed |
| this fork | 3 failed, 90 passed |

Same three failures; the four extra passes are `tests/test_transfer.py`.

Note also that `test_schedv3.py` cannot be run in isolation — it hits an import
ordering problem in `anki.models` that only resolves when the full `tests/`
directory runs. This is also true of the unmodified base.

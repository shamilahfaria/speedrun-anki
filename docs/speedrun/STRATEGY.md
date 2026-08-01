# Speedrun — Strategy

## The claim we are willing to be wrong about

Retention and readiness are different quantities, and study tools that report only
the first are selling the second. Speedrun measures three things separately and
shows the gap between them, including when the gap is embarrassing.

| Score | DOK | Question it answers | Evidence it is computed from |
|---|---|---|---|
| Memory | 1 | Can you recall the fact as it was trained? | FSRS retrievability over the card's own review history |
| Performance | 2/3 | Can you use the fact on a question you have never seen? | Reviews of *transfer probes* — paraphrased and applied variants |
| Readiness | 4 | What would you score on the real exam? | Performance, weighted by the official exam outline's topic distribution |

The thesis is falsifiable, and the ablation test in the final submission is designed
to falsify it: if memory score alone predicts held-back novel-question performance
as well as our three-score model does, the product's core claim is wrong and the
evidence layer will say so.

## Why this is a Rust change, not a Python change

This is the assignment's load-bearing technical requirement, and the rationale has
to survive scrutiny. Two independent reasons, either sufficient:

1. **The mobile app shares the Rust core, and only the Rust core.** The iOS
   companion (forked from `amgi`) reaches Anki through a C FFI into `rslib`. Logic
   written in `pylib` is structurally unreachable from the phone. A scoring engine
   written in Python would have to be reimplemented in Swift — two implementations
   of a calibrated statistical model, drifting apart, producing different scores on
   two devices for one collection. The assignment requires both platforms share the
   same engine. That requirement alone forces the scoring engine into `rslib`.

2. **The cost model.** Computing three scores with confidence intervals per exam
   topic means aggregating the full revlog — on a 50,000-card collection that is
   millions of rows — against a <1s dashboard first-load budget and a <500ms
   refresh. This is a scan-and-reduce over SQLite that belongs next to the
   database, not across a serialization boundary.

Reason 1 is the stronger one and is not a performance argument, which matters: it
means the choice would still be correct even if Python were fast enough.

## What ships when

**Friday (early submission)** — the skeleton must be real end-to-end, not mocked:
Brainlift v1 · a working Rust change in `rslib` with unit tests + a Python
integration test calling it · desktop installer · iOS app building against *our*
fork of the engine and syncing · basic AI card generation. A thin path through
every layer beats a thick path through one.

**Sunday (final)** — the evidence layer: calibrated memory/performance models with
Brier/log-loss on held-back data · the ablation test (feature on / off / baseline
Anki) · paraphrase, leakage, and crash tests · packaged installers · updated
Brainlift.

## Non-negotiables

- **The give-up rule.** Below a data threshold, the app returns *insufficient
  evidence*, not a number with a wide error bar. A confident-looking score computed
  from four reviews is the exact dishonesty this product exists to reject.
- **AI is optional.** The app is fully functional with AI disabled. AI-generated
  cards are traceable to a named source or they do not ship.
- **Three numbers, always separate.** No blended "readiness score" that hides which
  component is weak. The gap is the product.
- **AGPL-3.0**, with attribution to Anki (`ankitects/anki`) and amgi
  (`antigluten/amgi`). Some upstream Anki components are BSD-3; preserve those
  headers.

## Stack (frozen at GROUND)

| Layer | Choice | Note |
|---|---|---|
| Engine | Rust 1.92.0 (pinned by `rust-toolchain.toml`) | fork: `shamilahfaria/speedrun-anki` |
| Desktop | Python ≥3.12 + Qt + TypeScript | upstream Anki build via `ninja` |
| Mobile | Swift 6.2 / SwiftUI, iOS 18+ | fork: `shamilahfaria/speedrun-ios` (amgi) |
| Cross-layer | protobuf | existing Anki backend service pattern |
| LLM | Gemini 2.5 Flash-Lite | behind a provider interface — see D-001 |
| Build | `ninja`, `just`, `uv`, `cargo` | |

Code lives at `~/dev/speedrun/`, **not** in Google Drive — see D-003.

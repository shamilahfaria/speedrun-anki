# Decision Ledger — Speedrun

| ID | Decision | Phase |
|---|---|---|
| D-001 | Gemini 2.5 Flash-Lite as default LLM provider | GROUND |
| D-002 | Fork amgi for iOS companion instead of building from scratch | GROUND |
| D-003 | Code lives outside Google Drive | GROUND |
| D-004 | Rust change is the scoring engine, justified by mobile shared core | GROUND |

---

### D-001 · Gemini 2.5 Flash-Lite as default LLM provider
2026-07-31 · GROUND

**Decided:** Gemini 2.5 Flash-Lite ($0.10/$0.40 per M input/output tokens) as the
default provider for AI card generation, behind a thin provider interface so the
model is a config value, not a code dependency.
**Instead of:** OpenAI nano ($0.20/$1.25) — the agent's first proposal, chosen by
default familiarity rather than cost. Also considered Kimi K2.6 ($0.60/$2.50),
which the user raised as a cheap option; it is 6x the input cost of Flash-Lite and
has a thinner embeddings ecosystem. User already holds a Gemini key.
**Accepting:** Gemini's embeddings/eval tooling is less mature than OpenAI's, so
the AI-vs-keyword-baseline eval may need more hand-rolled scaffolding. Wrong if
Flash-Lite's card-generation quality fails the eval bar against the keyword
baseline — in which case the provider interface makes the swap cheap.

### D-002 · Fork amgi for iOS companion instead of building from scratch
2026-07-31 · GROUND

**Decided:** Fork [antigluten/amgi](https://github.com/antigluten/amgi) (AGPL-3.0,
SwiftUI, iOS 18+, Swift 6.2) as the iOS companion app. It already wraps the
official `ankitects/anki` Rust backend over a 4-function C FFI and ships working
bidirectional sync, FSRS scheduling, and offline-first behavior.
**Instead of:** Building a minimal native sync client from scratch against the
Rust engine's FFI — the agent's first proposal, made after asserting without
checking that no open-source iOS Anki client existed. That assertion was wrong.
The user pushed back; a search surfaced amgi, and `gh api` confirmed AGPL-3.0,
190 stars, and a push 5 days prior. Also surfaced but rejected: TeamKickAss/Anki,
travisbikkle/open-anki, detbar/Anki-iOS — all substantially less maintained and
none wrapping the official Rust backend.
**Accepting:** We inherit amgi's architecture and Swift 6.2 / iOS 18+ floor, and
its FFI surface is only 4 functions — exposing our new Rust scoring calls may
require widening that boundary. AGPL-3.0 on both amgi and our Anki fork is
license-compatible. Wrong if amgi's pinned Anki backend version diverges far
enough from our fork that rebasing costs more than the client would have.

**Process note:** the agent's stated risk assessment ("iOS is the highest-risk
item on the Friday bar") was built on the unchecked assertion, and collapsed once
the assertion was tested. Check before ranking risk.

### D-003 · Code lives outside Google Drive
2026-07-31 · GROUND

**Decided:** Clone both forks to `~/dev/speedrun/`. The Google Drive project folder
holds documents and deliverables only.
**Instead of:** Working directly in the Drive-synced project folder — the agent's
first action, done without thinking about it, and briefly the actual state of the
repo before being caught. Cargo's `target/` output for Anki runs to multiple GB of
rapidly-rewritten small files, and Cargo relies on filesystem locking; a sync
daemon competing for those locks stalls or corrupts builds. It would also make the
required "clean build on a fresh machine" claim untestable, since the build would
depend on sync state.
**Accepting:** The code is no longer backed up by Drive — GitHub is now the only
copy, so commits must be pushed rather than accumulated locally. Documents and code
live in two places, so paths in docs must be absolute or explained.

### D-004 · Rust change is the scoring engine, justified by the mobile shared core
2026-07-31 · GROUND

**Decided:** The required Rust-level modification is a new scoring/aggregation
module in `rslib` computing memory (DOK 1), performance (DOK 2/3), and readiness
(DOK 4) with confidence intervals and an engine-level give-up rule, exposed via the
existing protobuf backend service. Primary written rationale: the iOS app reaches
Anki only through a C FFI into `rslib`, so anything in `pylib` is unreachable from
the phone and would have to be reimplemented in Swift — two drifting
implementations of one statistical model, which the assignment's "same engine"
requirement forbids.
**Instead of:** Leading with the performance argument (millions of revlog rows
against a <1s dashboard budget) — the agent's first framing. It is true and is kept
as a secondary reason, but it is weaker, because it invites the reply "so optimize
the Python." The architectural reason has no such reply. Also considered:
modifying the queue builder to interleave transfer probes, which is a genuine
scheduler change but produces no visible artifact for Friday and is harder to unit
test; deferred, not rejected.
**Accepting:** A read-side aggregation module is a less dramatic "scheduler change"
than rewriting FSRS, and a reviewer skimming for scheduler edits might undervalue
it. Mitigated by the written rationale and by the give-up rule living in engine
behavior rather than UI. Wrong if a reviewer reads "query engine" as excluded from
the requirement — the assignment text says "scheduling/query engine," which it
is not.

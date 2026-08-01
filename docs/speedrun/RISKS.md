# Speedrun — Risk Register

Ordered by expected damage to the Friday bar, not by likelihood.

## R-1 · Xcode is not installed on the build machine
**Status:** OPEN — blocking iOS work
The machine has Command Line Tools only (`/Library/Developer/CommandLineTools`).
amgi requires Xcode with an iOS 18+ SDK and Swift 6.2. Installation is a multi-GB
App Store download requiring an Apple ID, which only the operator can start.
**Mitigation:** operator starts the download immediately; all Rust/Python/desktop
work proceeds in parallel and does not depend on it. The iOS slice is sequenced
last on Friday's path for exactly this reason.
**Trip point:** if Xcode is not usable by the time the Rust scoring engine passes
its tests, the iOS slice drops to "builds against our fork" and the study UI work
moves to Sunday.

## R-2 · amgi's pinned Anki backend diverges from our fork
**Status:** OPEN — under investigation
amgi vendors or submodules `anki-upstream` at some commit. Our engine change lands
on a *different* commit of `ankitects/anki`. If the gap is large, repointing amgi's
bridge at our fork means resolving upstream drift, not just changing a path.
**Mitigation:** identify amgi's pinned commit before writing any Rust; if it is
close to our fork point, rebase our change onto that commit so both apps compile
the same `rslib`. Prefer moving our fork to amgi's commit over moving amgi.
**Trip point:** if drift exceeds what can be resolved in ~1 hour, Friday's iOS
deliverable becomes "iOS app builds and syncs against unmodified engine," and the
shared-scoring claim moves to Sunday — but the claim is not made until it is true.

## R-3 · The Rust change is judged cosmetic
**Status:** MITIGATED BY DESIGN
The assignment explicitly rejects "just the Python UI layer." A scoring function
that merely reads values FSRS already computes would likely read as cosmetic.
**Mitigation:** the change is a new aggregation-and-inference module in `rslib`
that (a) reads the full revlog, (b) computes three distinct statistics with
confidence intervals, (c) implements the give-up rule as engine behavior rather
than display logic, and (d) is exposed through the protobuf backend service so it
is reachable from Python *and* Swift. The written rationale leads with the
mobile-shared-core argument, which is an architectural necessity, not a
performance preference — see STRATEGY.md.

## R-4 · Time budget: one night to a five-part bar
Friday requires Brainlift, Rust change, review loop, desktop installer, iOS sync,
and AI integration. Any one of these can absorb a whole night.
**Mitigation:** thin path through every layer before any layer is deepened. A
demo that touches all five shallowly satisfies the bar; a perfect scoring engine
with no installer does not.
**Trip point:** the Rust change plus its tests is the one item with no acceptable
degraded form — it is the assignment's named centerpiece. Everything else has a
defined thin version.

## R-5 · Google Drive corrupting the build
**Status:** CLOSED — see D-003
Cargo's file locking and multi-GB `target/` output are hostile to a syncing
filesystem. Code relocated to `~/dev/speedrun/`; the Drive folder holds documents
only.

## R-6 · Evidence layer is unfalsifiable in practice
The ablation test only means something if held-back data is genuinely held back.
Leakage — AI-generated cards trained on the same items used to test transfer — is
the easy, invisible failure, and it would make every number in the final
submission meaningless while looking excellent.
**Mitigation:** data cutoff declared before generation; leakage-check script
written *before* the eval, not after; test items quarantined in a separate store
the generator cannot read. This is Sunday work but the quarantine has to exist
from the first generated card, so it is designed in on Friday.

## R-7 · Calibration claims outrun the data
"80% confidence should be correct 80% of the time" needs enough reviews per bucket
for a Brier score to mean anything. A single night of synthetic study data will not
produce a genuinely calibrated model.
**Mitigation:** state the data volume and its provenance next to every calibration
number; if the data is synthetic, say so in the submission rather than presenting a
Brier score as if it came from real users. The give-up rule applies to our own
claims, not only to the app's.

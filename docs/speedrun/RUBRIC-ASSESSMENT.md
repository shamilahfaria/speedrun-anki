# Rubric self-assessment — scored out of 100

**Correction, and it matters.** An earlier version of this file was graded
against a text summary of the brief. This version is graded against the actual
assignment PDF, which is substantially more specific. Several requirements were
missed entirely in the first pass — a competitor teardown, an AI consensus
check, choosing an exam, mapping readiness onto a real score scale, and the AI
card check. The score below is much lower than the first pass implied, and the
first pass was wrong, not unlucky.

**The weights are mine.** The assignment does not publish point values, so the
weighting is constructed from its own emphasis: what §3 calls non-negotiable,
what §7 lists for Friday, what §8 requires as tests, and what §10 sets as
targets. The arithmetic is shown so it can be re-weighted by anyone who
disagrees.

Grading rule: credit requires a check someone else can run. "Implemented" earns
nothing on its own.

---

## Scorecard

| § | Category | Earned | Possible |
|---|---|---|---|
| 1 | Brainlift v1 | 11.5 | 18 |
| 2 | Competitor teardown | 0 | 7 |
| 3 | Rust change | 11.5 | 14 |
| 4 | Two apps, one engine, sync | 5.5 | 14 |
| 5 | Three scores + give-up rule | 6.5 | 11 |
| 6 | Coverage map | 1 | 4 |
| 7 | AI requirements | 6 | 10 |
| 8 | Thesis test (ablation) | 0 | 9 |
| 9 | Paraphrase / leakage / crash | 0 | 6 |
| 10 | Performance targets | 1.5 | 5 |
| 11 | Licensing + exam choice | 1.5 | 2 |
| | **Total** | **45** | **100** |

Scoped to the Friday early submission alone — which the brief says is "graded as
it stands" — the same arithmetic gives roughly **57/100**, because the Sunday
evidence layer (§8, §9) is not yet in scope there.

---

## 1. Brainlift v1 — 11.5 / 18

| Item | Earned | Note |
|---|---|---|
| Purpose and what is out of scope | 1.5 / 2 | Purpose stated; out-of-scope not written down |
| DOK 1: ≥5 named sources with links | 2.5 / 4 | 11 sources, independently verified — but the brief specifically requires the **systems lineage** (SuperMemo's scheduling work, FSRS, Anki's design decisions) and none of it is cited |
| DOK 2: own words, what you took **and rejected** | 2 / 3 | Paraphrased throughout, and Butler was explicitly rejected — but not done per-source as required |
| DOK 3: where sources disagree, field assumptions | 2 / 3 | The Butler contradiction is genuine DOK 3 work; no teardown findings feed it |
| DOK 4: ≥3 Spiky POVs in the required shape | 2.5 / 4 | Five POVs exist, but not shaped as *consensus says X, I think Y, here is my evidence, here is what would prove me wrong*. Falsification sits in its own section instead of inside each POV |
| AI consensus check transcripts | 0 / 2 | Not done |
| Traceability table, **one row per POV** | 1 / 2 | Ours is one row per feature. The brief wants POV → what it forced you to build → how you would know it was wrong |

**Also breached:** §3 says *Brainlift v1 before the first commit*. Code was
committed first. Not separately penalised above, but it is a stated
non-negotiable and worth recording.

## 2. Competitor teardown — 0 / 7

Required: use **at least three** current MCAT/LSAT/GMAT tools for real — sign
up, study on them, log where they break, and answer *what DOK level does this
tool actually measure versus what it implies*. Not attempted. The market claim
in the Brainlift is therefore asserted from secondary evidence rather than
observed behaviour.

## 3. Rust change — 11.5 / 14

| Item | Earned | Note |
|---|---|---|
| Working end to end, with the diff | 5 / 5 | `TransferService`; matches §8's third option — a mastery query returning per-topic mastery and recall, fast enough for the dashboard on 50,000 cards |
| 3 Rust unit tests | 3 / 3 | 10 |
| 1 Python test calling it | 2 / 2 | 4, through the real FFI |
| Proof undo works, collection does not corrupt | 0 / 3 | Not tested. Read-only is a reason to expect safety, not evidence |
| One-page note on why it belongs in Rust | 1 / 1 | Reachability from the iOS FFI |
| Ships to the phone, **checked there** | 0.5 / 1 | Compiles into the iOS static library; never executed on device |

## 4. Two apps, one engine, sync — 5.5 / 14

| Item | Earned | Note |
|---|---|---|
| Phone builds on the shared engine | 5 / 5 | Unsigned IPA from CI; submodule pins our fork |
| Phone runs real sessions, shows the same three scores | 0 / 3 | No SwiftUI surface |
| 20-card sync test, all landing once | 0 / 5 | Not attempted |
| Conflict rule written down and demonstrated | 0.5 / 2 | Inherited from amgi; not written by us, not demonstrated |

## 5. Three scores + give-up rule — 6.5 / 11

| Item | Earned | Note |
|---|---|---|
| Three separate scores, each with a range | 4 / 4 | Wilson intervals, never blended |
| Readiness on the **real exam scale**, with method | 0 / 3 | Ours is a proportion. The brief wants *Projected MCAT: 508, likely range 503–512* |
| Score metadata: percent of exam covered, confidence indicator, last updated, main reasons | 0.5 / 3 | Only evidence counts are shown |
| Give-up rule enforced | 2 / 2 | Enforced in the engine. Note ours (20 reviews, 5 cards) is far weaker than the brief's example (200 graded reviews and 50% topic coverage) |

## 6. Coverage map — 1 / 4

Required: **every topic on the official outline**, marked covered or not, with a
percentage on the dashboard, and the app abstaining below your line. Ours groups
by user-supplied tags, so material never studied is invisible — which is exactly
the blind spot a coverage map exists to remove.

## 7. AI requirements — 6 / 10

| Item | Earned | Note |
|---|---|---|
| Every output traced to a named source | 3 / 3 | Provenance enforced by construction |
| **AI card check**: gold set of 50 Q&A, 50 cards from one real source, scored correct-and-useful / wrong / correct-but-bad-teaching, cutoff set before looking | 0 / 4 | Not done. Our eval measures *retrieval*, not card quality — a different thing than the brief asks for |
| Eval beats a simpler method | 2 / 2 | `gemini-embedding-001` p@1 1.000 vs BM25 0.950 |
| App still scores with AI off | 1 / 1 | `NullProvider` |

## 8. Thesis test (ablation) — 0 / 9

Required: three builds — full app, feature off, plain Anki — same questions,
same study time, main number stated in advance. Not attempted. The brief is
explicit that a disproved POV scores well and an untested one scores nothing.

## 9. Paraphrase / leakage / crash — 0 / 6

- Paraphrase test (30 cards, 2 rewordings each): not done
- Leakage check script: not written
- Crash test (kill mid-review 20×, zero corruption): not attempted

## 10. Performance targets — 1.5 / 5

Seven targets in §10. Two met — dashboard first load 441 ms (<1s) and refresh
399 ms (<500 ms) — plus a rerunnable 50k benchmark reporting p50/p95/worst.
Unmeasured: button ack p95 <50 ms, next card p95 <100 ms, session sync <5s, cold
start <5s/<4s, memory ceiling, UI never blocked >100 ms, crash test.

Also: the brief asks for **one command, e.g. `make bench`**. Ours is a Python
script, not a make target.

## 11. Licensing + exam choice — 1.5 / 2

AGPL-3.0-or-later with attribution, BSD components noted, full upstream history
preserved. **But no exam was chosen** — §6 requires deciding before writing code
and stating it at the top of the README. We built exam-agnostic, which is
precisely why §5's real-scale readiness and §6's coverage map could not be
implemented. One skipped decision propagated into three unmet requirements.

---

## What this says

The engineering that exists is solid and honestly verified: a real Rust change
reachable from both platforms, an engine that refuses to score thin evidence, a
display layer tested against leaking a refusal as 0%, an iOS build proven on a
clean machine, and three independent baseline comparisons rather than assumed
regressions.

The gap is not code quality. It is **coverage of what was actually asked**.
Three of the largest misses are cheap in effort and were simply never started —
choosing an exam, tearing down three competitor tools, running the AI consensus
check. Two more are the assignment's centre of gravity: the ablation test and
calibration, which are the only things that would move this from a tool that
*asserts* honest measurement to one that *demonstrates* it.

The single highest-leverage fix is choosing an exam. It unblocks real-scale
readiness, the official-outline coverage map, and a meaningful give-up rule in
one move.

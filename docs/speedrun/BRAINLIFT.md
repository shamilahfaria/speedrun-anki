# Brainlift v1 — Speedrun

**Owner:** Shamilah Faria · **Exam: MCAT** (472–528) · **Updated:** 2026-08-02

> Version note. An earlier draft argued "nothing on the market measures transfer"
> and that retention stops binding "around week six." Both were false. They were
> withdrawn under evidence, and the withdrawals are recorded rather than edited
> away — §7 is the record of what changed and why.

---

## 1. Purpose, and what is out of scope

**Purpose.** Build an MCAT study tool that reports what it can defend and
withholds what it cannot, on the real 472–528 scale — and that uses evidence
about transfer to decide *what to serve next*, not only what to display.

**Explicitly out of scope**

- Any exam other than the MCAT. The original thesis was generalised across
  MCAT/LSAT/GMAT and that generalisation was wrong; the LSAT has almost nothing
  worth putting on a flashcard.
- Claiming to replace AAMC full-length practice tests. They are among the
  highest-validity predictors in consumer education. We do not compete with them,
  and any framing that implies otherwise is a defect.
- Content authoring. We do not write an MCAT curriculum.
- Predicting admissions outcomes.
- Proving learning gains in a week. §10 of the brief grades the bridge, not the
  final number, and we take that literally.

---

## 2. DOK 1 — Sources

Named and linked. `scripts/check-sources.sh` verifies they resolve; a separate
blind pass verified each says what is claimed about it, having been given no
access to the argument.

### Systems lineage

| # | Source | Link |
|---|---|---|
| S1 | Woźniak, *Algorithm SM-2* — the original spec | <https://super-memory.com/english/ol/sm2.htm> |
| S2 | SuperMemo, *Two components of long-term memory* | <https://www.supermemo.com/en/blog/two-components-of-long-term-memory> |
| S3 | FSRS — *The Algorithm* (DSR model, parameters) | <https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm> |
| S4 | Expertium, *FSRS Algorithm* — writeup and stated flaws | <https://expertium.github.io/Algorithm.html> |
| S5 | `srs-benchmark` — 10,000 collections, ~350M reviews | <https://github.com/open-spaced-repetition/srs-benchmark> |
| S6 | Anki manual, *Deck Options* — what desired retention means | <https://docs.ankiweb.net/deck-options.html> |
| S7 | Anki manual, *Statistics* — True Retention | <https://docs.ankiweb.net/stats.html> |
| S8 | Expertium, *Retention* — desired vs retrievability vs true | <https://expertium.github.io/Retention.html> |
| S9 | FSRS wiki, *The optimal retention* — the objective function | <https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-optimal-retention> |
| S10 | Anki forums — developers stating the limits | <https://forums.ankiweb.net/t/clarify-what-optimal-retention-means/42803> |
| S11 | Ye, *The history of FSRS for Anki* | <https://www.lesswrong.com/posts/G7fpGCi8r7nCKXsQk/the-history-of-fsrs-for-anki> |
| S12 | SuperMemo, *SuperMemo is better than FSRS by far* | <https://www.supermemo.com/en/blog/supermemo-is-better-than-fsrs-by-far> |

### Learning science

| # | Source | Link |
|---|---|---|
| L1 | Butler (2010), *Repeated testing produces superior transfer* | <https://andymatuschak.org/files/papers/Butler%20-%202010%20-%20Repeated%20Testing%20Produces%20Superior%20Transfer%20of%20Learning%20Relative%20to%20Repeated.pdf> |
| L2 | Koriat & Bjork (2005), *Illusions of competence* | <https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Koriat_RBjork_2005.pdf> |
| L3 | Bjork & Bjork, *Desirable difficulties* (relays Yan et al. 2016) | <https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-introducing-desirable-difficulties-into-practice-and-instruction-bjork-and-bjork.pdf> |
| L4 | Bjork, Dunlosky & Kornell (2013), *Self-regulated learning* | <https://gwern.net/doc/psychology/spaced-repetition/2013-bjork.pdf> |
| L5 | Karaca et al. (2023), calibration across four exams | <https://pmc.ncbi.nlm.nih.gov/articles/PMC10607382/> |
| L6 | Deng, Gluckstein & Larsen (2015), flashcards vs Step 1 | <https://pmc.ncbi.nlm.nih.gov/articles/PMC4673073/> |

**Could not open:** SM-17/SM-18 primary text. `supermemo.guru`,
`supermemopedia.com` and `help.supermemo.org` all return 403 and the Internet
Archive is blocked here. SM-17 is therefore cited only via FSRS's
characterisation of it — an interested party. Flagged, not papered over.

---

## 3. DOK 2 — Each source in my words: what I took, what I rejected

**S1 · SM-2.** One state variable per card plus a repetition counter; intervals
multiply by ease, a failure resets the sequence. Woźniak says it was "constructed
by means of the trial-and-error approach." **Took:** there is no probability of
recall in SM-2 and no retention target, so a retention percentage from an
SM-2-era tool is not a model output at all. **Rejected:** nothing — it does not
overclaim.

**S2 · Two-component model.** Retrievability = probability of recall now;
stability = how fast that decays. **Took:** the vocabulary, and the argument that
one "memory strength" variable cannot account for optimal spacing. **Rejected:**
the implicit framing that spacing is the only frontier worth working on.

**S3, S4 · FSRS.** Difficulty–Stability–Retrievability; 13 parameters in v3, 21
in FSRS-6; stability converges to a bound instead of growing linearly. **Took:**
the DSR vocabulary and Expertium's candour — difficulty is "a crude heuristic"
that "doesn't take R into account." **Rejected:** any reading of retrievability as
knowledge. It is a per-card probability about one scheduled review.

**S5, S12 · The benchmarks.** ~350M reviews; FSRS-6 shows 99.6% superiority over
SM-2 by log loss. **Took:** FSRS is genuinely better at its own job. **Rejected:**
the headline as usually quoted — the maintainers say a fair FSRS/SM-2 comparison
is impossible because SM-2 "wasn't originally designed to predict probabilities,"
a neural net (RWKV-P) beats FSRS on the same benchmark, the FSRS-vs-SM-17 result
rests on **19 users**, and SuperMemo calls the metric "entirely inappropriate."

**S6–S10 · What Anki actually claims.** Desired retention "controls how likely
you are to remember cards when they are scheduled for a review." True Retention is
"expected to be close to" desired — hedged. Expertium separates desired retention
from average retrievability ("If FSRS is inaccurate, this number will also be
inaccurate"). The optimal-retention objective minimises **minutes studied ÷
summed recall probability**, all cards weighted equally, no exam, deadline or
topic-weight model. **Took:** all of it; this is the spine of POV 3. **Rejected:**
my own earlier belief that these tools oversell. They do not. The overclaim
happens downstream, in the learner's inference and in prep marketing.

**L1 · Butler (2010).** Retrieval practice beat restudy on novel inferential
questions, and repeating the *same* item transferred about as well as varying it.
**Took:** flashcards are not inert; any pitch resting on "flashcards don't
transfer" is dead. **Rejected:** my first reading, which had it backwards. Butler
measured group means under a manipulation, not whether one learner's recall
predicts that same learner's transfer.

**L2 · Koriat & Bjork (2005).** Judgments of learning are made with the answer
visible; the test removes it. **Took:** the mechanism, and the paradigm — elicit a
prediction, then score it against outcome on the same items. **Rejected:** nothing.

**L3 · Yan et al. via Bjork & Bjork.** Told most people learn better interleaved,
participants concluded they were personally the exception. **Took:** this, and
reversed my product design because of it (§7). **Rejected:** my earlier use of it
as *support*. It is a warning.

**L4 · Bjork, Dunlosky & Kornell (2013).** Overconfidence is typical; fluency is
the dominant, corrupted cue; fluent items get dropped soonest. **Took:** the
direction of the error. **Rejected:** treating a review chapter as contrarian —
citing an *Annual Review* is citing consensus.

**L5 · Karaca et al. (2023).** Bottom-quartile students overpredicted by ~15
points; confidence stayed flat across four exams. **Took:** miscalibration is
sticky. **Rejected:** stretching it — this is grade-level prediction in one
course, not item-level allocation, and it is one study.

**L6 · Deng et al. (2015).** ~1,700 extra cards ≈ 1 Step 1 point; a second card
system showed no relationship. **Took:** card volume is a weak lever.
**Rejected:** using it as support. Read honestly it says flashcards barely move
the outcome, which argues against this market more than for it.

---

## 4. DOK 3 — Where sources disagree, what the field assumes

**The metric war is unresolved and both sides are interested parties.** FSRS
publishes 83.3% superiority over SM-17 — on 19 users. SuperMemo replies that ML
calibration metrics are "entirely inappropriate," proposes its own Universal
Metric, and claims 1–3% error against FSRS's 15–20%. Each grades with the ruler
it built; neither has published on the other's terms. Anyone quoting either
number as settled is quoting an advocate.

**Butler contradicts the folk model.** Test-prep culture says content review ends
and then you live in passages — implying cards stop paying. Butler's data say
retrieval practice, including same-item repetition, transfers better than
restudy. The folk model is the one embedded in most study plans, and it is the
one the experiment does not support.

**The unexamined assumption: retrievability proxies readiness.** No system claims
this. Anki scopes desired retention to one card at its next review. Expertium
says average retrievability is only as good as the model. FSRS's objective is
explicitly *time-efficiency* — minutes per unit of recall probability, every card
equal, no exam model. Yet retention percentage is what learners steer by, because
it is the only number they are given. The gap is not between what the systems
claim and what is true; it is between what they claim and what users infer, and
nothing in the tooling closes it.

**What the field assumes and does not check:** that a recall probe and an
application probe are comparably difficult. They are not — different formats,
different guessing parameters, different difficulty distributions. A "gap"
between them can be manufactured entirely by construction.

**What the teardown exposed:** §8, recorded as secondhand.

---

## 5. DOK 4 — Spiky POVs

Each stated as *consensus says X · I think Y · here is my evidence · here is what
would prove me wrong.* POV 2 is the claim tested in §9 of the brief.

### POV 1 — An instrument that cannot refuse is not an instrument

**Consensus says:** always show the student a number; communicate uncertainty
with error bars or a confidence label.

**I think:** below an evidence threshold the correct output is *no number*, and
the refusal must be structurally impossible to render as one — a type, not a
convention. Error bars get ignored; a missing number cannot be.

**My evidence:** L4 — fluency is the dominant metacognitive cue, and the more
fluent something feels the sooner it is dropped, so a weakly-supported number is
absorbed as reassurance. L5 — confidence did not update across four real
disconfirming results, so a number plus a caveat corrects nobody. And the blind
consensus reader, which called the refusal type *"the single strongest evidence in
the packet, more than any citation… it is not cosmetic."*

**What would prove me wrong:** if students shown a refusal behave no differently
from students shown a wide interval — same next action, same allocation — the
refusal is ceremony and the interval is cheaper.

### POV 2 — Displays don't change behaviour; defaults do *(tested in §9)*

**Consensus says:** show the student their weak areas and they will reallocate.

**I think:** the evidence predicts they will not, and a tool built on that
assumption fails in a way its own literature forecasts. The intervention belongs
in **what gets served next**, not in what gets displayed. Transfer evidence should
reorder the queue, not decorate a dashboard.

**My evidence:** L3 — participants told most people learn better interleaved
concluded they were *personally the exception*. L5 — three disconfirming exam
results moved confidence not at all. Both say behaviour change routed through
belief change fails. The consensus reader reached this independently and called it
the most damaging item in my own stack: *"Your evidence base predicts your
product's failure mode… it should be a scheduler — change what is served next
rather than what the learner believes."*

**What would prove me wrong:** the §9 ablation. Build (1) full app with
transfer-weighted scheduling, (2) the same app with that scheduling off but the
same information still displayed, (3) stock Anki. If (1) and (2) are
indistinguishable over equal study time, the scheduler adds nothing over the
display and this POV is dead.

### POV 3 — Retention optimisation is time-efficiency optimisation, and was never a readiness claim

**Consensus says:** high retention in your spaced-repetition tool means you are on
track for the exam.

**I think:** retention is a per-card probability about one scheduled review, and
the optimiser behind it minimises *study minutes per unit of recall probability
with every card weighted equally*. There is no exam in that objective function, no
deadline, no topic weighting. Treating it as readiness is a category error the
tools never invited.

**My evidence:** S9 — the documented objective is minutes ÷ summed recall
probability. S6 — desired retention is scoped to "when they come up for review
again." S8 — average retrievability is a model output, accurate only if the model
is. S10 — developers state the assumptions themselves (assumes 10 new cards/day,
ignores existing non-new cards, "designed for long-term study").

**What would prove me wrong:** if per-topic retrievability predicts MCAT passage
performance with meaningful incremental validity over topic coverage and study
hours, the schedulers already carry the readiness signal and a separate transfer
measure is redundant.

---

## 6. Traceability — one row per POV

| POV | What it forced me to build | How I will know it was wrong | Code | Number |
|---|---|---|---|---|
| **1 · Must refuse** | Give-up rule inside the engine, not the UI. A refusal carries the shortfall and `point = 0.0`, so a caller that never received a number cannot render one. On iOS the domain type is an enum — rendering a refusal as a number is a compile error. | Refusal and wide-interval groups behave identically | `rslib/src/transfer/mod.rs` (`score_reviews`, `Thresholds`); `qt/aqt/transfer.py` (`_score_cell`); `Sources/AnkiKit/TransferTypes.swift` | 10 Rust tests; `test_refusal_is_shown_as_a_refusal` asserts no `0%` leak |
| **2 · Defaults over displays** | **Not yet built.** Needs transfer-weighted queue ordering in the Rust scheduler plus the three-build harness. | §9 ablation: build (1) ≈ build (2) | **Gap** — `rslib/src/transfer/` measures; it does not schedule | Pending |
| **3 · Retention ≠ readiness** | Memory and transfer partitioned by tag, never pooled; both reported with intervals; readiness on the 472–528 scale or withheld. | Per-topic retrievability shows incremental validity over coverage + hours | `rslib/src/transfer/mod.rs` (`build_report`); `proto/anki/transfer.proto` | `memory_and_performance_are_measured_separately`; 441 ms cold / 399 ms warm @ 50k cards |

Rows with a gap are marked as gaps. A traceability table listing only successes is
a marketing document.

---

## 7. What changed, and what killed it

The brief says *"I was wrong, here is the evidence"* scores well. Four things
changed under evidence; transcripts in [`consensus-check/`](consensus-check/).

1. **"Nothing on the market measures transfer" — withdrawn as false.** AAMC
   full-lengths, UWorld and Blueprint all score novel passages, and AAMC FLs are
   among the highest-validity predictors in consumer education. *Killed by:* the
   cold consensus pass.
2. **"Week six" — withdrawn as invented precision.** Section-specific,
   baseline-dependent, and retention is a persistent maintenance cost rather than
   a phase that ends. *Killed by:* the cold pass. The honest replacement is a
   per-student marginal-return rule.
3. **"Flashcards don't build transfer" — withdrawn; Butler says the opposite.**
   *Killed by:* reading L1 properly after a blind citation check flagged the claim
   as overstated.
4. **"Show the gap and students reallocate" — reversed into POV 2.** My own
   citation predicts learners exempt themselves. *Killed by:* pass two, which
   noticed my evidence base predicted my product's failure mode.

**Two live objections I have not answered, recorded rather than buried:**

- **The gap is a difference score.** rel(D) = (r₁₁+r₂₂−2r₁₂)/(2−2r₁₂) ≈ .50 for
  plausible inputs, and gets *worse* as the two measures correlate. Showing two
  numbers side by side and letting the learner subtract does not escape this — it
  launders it. This is why POV 2 moves the intervention into scheduling and why §9
  tests the scheduler rather than the chart.
- **Wilson is the wrong variance component.** It handles binomial sampling error;
  the dominant variance in passage performance is item sampling and
  person-by-occasion. Our intervals are therefore too narrow, and
  "narrow-and-principled" is the most dangerous failure available because it looks
  like rigor. Fixing it needs a passage-level random effect. **Not done.**

**Deliberately not claimed:** that any of this improves scores. That is §9's job,
and §9 has not been run.

---

## 8. Teardown of existing tools

*Pending — see `teardown.md`. Recorded as secondhand evidence: these tools were
researched from public documentation and user reports rather than used, and every
claim is labelled with its provenance. §2 asks for behaviour observed first-hand,
so this section is weaker than the brief requires and is marked as such.*

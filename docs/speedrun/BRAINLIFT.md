# BrainLift — Speedrun

**Owner:** Shamilah Faria · **Exam:** MCAT (472–528) · **Updated:** 2026-08-02

---

## 1. Purpose

- Build an MCAT tool that reports what it can defend and **withholds what it cannot**, on the real 472–528 scale.
- Out of scope: other exams; replacing AAMC full-lengths; writing curriculum; predicting admissions; proving score gains in a week.

---

## 2. Experts

Tiered by what survived an adversarial audit — not by citation count.

**Load-bearing (replicated or independently corroborated)**
- **Rowland (2014)** — retrieval beats restudy, g = 0.50. Corroborated independently by Adesope (0.51). *Funding not stated; no commercial tie.*
- **Feedback amplifies retrieval** — Rowland: g = 0.73 with vs 0.39 without.
- **Pan & Rickard (2018)** — transfer is conditional. 192 effects, N = 10,382. *APA + NSF.*
- **Kraft (2020)** — education benchmarks: <0.05 small, 0.05–0.20 **medium**, ≥0.20 **large**. *Funding not stated.*

**Cut after audit — recorded so the cut is visible**
- **Ehrlinger, Mitchum & Dweck (2016)** — I called this an RCT. It isn't. Sample sizes by "rule of thumb," stopping rule "imperfectly enforced," **zero replications in 159 citations**. 🚩 **Undisclosed: Dweck holds book royalties and co-founded Mindset Works Inc.** — the only commercial conflict in an 8-paper stack.
- **Metcalfe & Finn (2008)** — causal claim rests on two *accepted nulls* at n ≈ 24. Never replicated in 18 years.
- **Thiede (2003)** — Thulé (N = 82) replicated the outcome and **killed both mediators**.
- **Butler (2010) as far-transfer evidence** — one **N = 20** cell where subjects were given hints and told to apply prior learning. Butler's own words: the hint was *"to negate the need for them to recognize"* relevance.

**Systems lineage** — [SM-2](https://super-memory.com/english/ol/sm2.htm) · [FSRS](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm) · [Anki deck options](https://docs.ankiweb.net/deck-options.html) · [FSRS optimal retention](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-optimal-retention) · [Expertium on retention](https://expertium.github.io/Retention.html)

**Full source list + teardown:** [problem-statement.md](problem-statement.md) · [teardown.md](teardown.md)

---

## 3. SpikyPOVs

### POV 1 — A percentage cannot tell a guess from knowledge *(tested in §9)*

- **Consensus:** your practice score tells you where you stand.
- **I think:** percent correct is blind to the distinction that matters most, and that blindness covers a third of your correct answers.
- **Evidence:**
  - **38–40%** of correct MCQ responses are rated *guess* or low-confidence (Butler, Karpicke & Roediger 2008).
  - Feedback on correct-but-guessed items **doubles retention: .40 → .85**.
  - **67%** of correct answers carried a coded reasoning flaw (Surry 2018, N = 14 — small, treat as upper bound).
  - AAMC has collected per-question confidence since **Oct 2022**. Four years, zero reports of anyone using it.
- **What would prove me wrong:** if confident-and-wrong rate predicts outcomes no better than raw accuracy.
- **Note:** confidence-*tailored feedback* was tried and failed (Mory 1994). The claim is that confidence is worth **capturing**, not that tailoring works.

### POV 2 — "Evidence-based" is a claim nobody in this market can support, including us

- **Consensus:** cite the science of learning; the strategies are settled.
- **I think:** audit it and it does not hold at the confidence everyone displays.
- **Evidence:**
  - Transfer without enabling moderators: **d = −0.053**, bias-corrected **−0.21** (Pan & Rickard).
  - Brunmair & Richter's title moderator **"similarity matters" goes non-significant in the authors' own outlier-inclusive model**.
  - Interleaving: two **preregistered** classroom trials, **N = 399** and **N = 1,056**, both **null** (Rowlandson & Simpson 2025).
  - Karpicke's 2025 flagship review devotes a figure to Butler and cites **neither** the meta-analysis that conditionalises it **nor** the replication that reattributes its mechanism.
  - EEF's own caveat: metacognition *"lost a padlock because a large percentage of the studies were not independently evaluated… commercial providers typically have larger impacts."* Its +8 months rests on **I² = 99.96%**.
  - **0.13%** of education articles are replications. EEF efficacy→effectiveness: **1 of 7 survived**, mean 0.25 → 0.01.
- **What would prove me wrong:** a preregistered multi-site trial replicating any core claim at published magnitude.

### POV 3 — Retention optimisation was never a readiness claim

- **Consensus:** high retention in your SRS means you're on track.
- **I think:** it's a per-card probability about one scheduled review, and the optimiser minimises **study minutes ÷ summed recall probability** — every card weighted equally, no exam, no deadline, no topic weighting.
- **Evidence:** Anki's docs scope desired retention to *"when they come up for review again."* Expertium: average retrievability is a model output, *"If FSRS is inaccurate, this number will also be inaccurate."* FSRS's optimal-retention objective is explicitly time-efficiency.
- **What would prove me wrong:** if per-topic retrievability predicts MCAT passage performance with incremental validity over topic coverage and study hours.

---

## 4. Knowledge Tree

- **The gap is real and reported.** Students with matured decks and finished content review post FLs "in the low 500s" — *"a lot of isolated facts memorized from Anki,"* can't apply them when a question *"requires integrating multiple ideas."*
- **A second failure the transfer framing missed:** passing the card by recognising the card. *"memorizing what the answer looks like rather than the actual information"* — the mechanism a reworded probe detects, and no tool has one.
- **Nobody reports uncertainty.** The MCAT publishes **±1 / ±2** confidence bands. **Zero of six tools** publish any. Blueprint's own data: **7.2-point mean absolute error**, worst miss **33 points** (a 472 against an official 505) — reported as a point estimate.
- **Nobody rewords an item.** Across six vendors: zero item-variation features. Every "retest" is verbatim repetition, which inflates the metric being sold as progress.
- **Design consequences:** memory and transfer partitioned by tag, never pooled · engine returns a *refusal*, not a number, below threshold · on iOS `Score` is an enum, so rendering a refusal as a number is a **compile error**.
- **Trap worth recording:** protobuf service indices are descriptor-pool positions and the iOS client hardcodes them. `transfer.proto` must sort last or the phone breaks with no compile error.

---

## 5. Citation standard

Adopted after four citations failed audit in one session.

- Every load-bearing number: **full text read**, not abstract.
- Record **replication status** and **funding/COI** beside the claim.
- **Subgroup cells are hypothesis generators, not findings.** I cited Rowland's g = 0.03 as "testing does nothing"; it's k = 17, flips to 0.26 at ≥1-day retention, and Rowland uses it as evidence **for** feedback.
- Weight **independently funded nulls** above vendor-adjacent positives. Nobody is paid to find nothing.
- Apply **Kraft's** benchmarks, not Cohen's.

---

## 6. What changed

- ❌ *"Nothing on the market measures transfer"* — **false.** AAMC FLs, UWorld, Blueprint all score novel passages.
- ❌ *"Week six"* — invented precision.
- ❌ *"Flashcards don't build transfer"* — Butler shows the opposite.
- ❌ *"Reviews are the weakest-evidenced metric"* — **I had Rowland inverted.** Review is the moderator that pays (0.73 vs 0.39); volume is the one that doesn't (ns).
- ❌ *"Show the gap and students reallocate"* — my own citation (Yan et al.) predicts they'll exempt themselves: told 90% learn better a given way, **78% put themselves in the 10%.**

**Unanswered, recorded not buried:** the memory−performance gap is a **difference score**, rel(D) ≈ .50 for plausible inputs. And Wilson handles binomial sampling error when the dominant variance is item sampling — **our intervals are too narrow.**

**Not claimed:** that any of this raises scores. That's §9, and §9 hasn't run.

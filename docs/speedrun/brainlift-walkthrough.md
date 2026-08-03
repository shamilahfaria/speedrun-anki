# BrainLift walkthrough — talk track

~6 minutes. Each beat is one idea. Bold lines are the ones to say close to verbatim.

---

## 1 · Open with the student, not the product (45s)

An MCAT student finishes content review. Matures the AnKing deck. Four thousand cards.

Their full-lengths: **493, 500, 496, 500.**

In their words:

> *"a lot of isolated facts memorized from Anki, but I can't apply them when a question requires integrating multiple ideas"*

And another, naming what a study tool did to them:

> *"it gave me a false sense of security by the time I got into practice questions"*

**Every number this student sees is going up. The one number that matters isn't moving.**

---

## 2 · The question I started with (30s)

**Why do people who study hard plateau — and why does nothing warn them?**

I assumed the answer was: their tools measure memorization and sell it as readiness.

That assumption was half right and half badly wrong, and finding out which half took the whole project.

---

## 3 · What the teardown found (60s)

I took apart six MCAT tools — UWorld, the Anki decks, Blueprint, Kaplan, Jack Westin, Memm.

**The MCAT itself publishes a confidence band on every score.** ±1 per section, ±2 total. The AAMC says the bands exist "to discourage distinctions between applicants with similar scores."

**Not one of the six tools publishes any interval at all.**

> **The products are more confident than the exam they predict.**

The sharpest single number, from Blueprint's *own published data*: mean absolute error of **7.2 points**, and one student whose diagnostic read **472** — the literal floor of the scale — against an official **505**. Reported as a point estimate, no error bar.

And: **not one of six tools ever rewords a question.** Every "retest" is the identical item. Which matters, because of the next slide.

---

## 4 · The thing nobody measures (60s)

Two numbers from the research:

- **38–40% of correct multiple-choice answers are guesses or low-confidence.**
- Giving feedback on those correct-but-guessed items **doubles** later retention — **.40 → .85**.

So the highest-value thing to review is **the answer you got right and shouldn't have.**

Now: **a percentage score cannot tell those apart.** 90% is 90% whether you knew it or guessed it.

**The AAMC has collected per-question confidence data since October 2022.** Four years. I could not find a single student anywhere reporting they used it to change how they study.

**The signal exists. Nothing is connected to it.**

---

## 5 · Where I was wrong — the part worth dwelling on (90s)

This is the strongest section. Don't rush it.

I built a confident thesis: *reviewing everything is why you're plateaued; volume of novel questions is what pays.*

Then I ran three things against it — a steelman told to destroy it, a replication audit, and a check against the field's own consensus documents.

**Four of my citations died.**

- **I had the central paper backwards.** I cited Rowland's meta-analysis for "review doesn't matter." His actual finding: with feedback **g = 0.73**, without it **0.39**. Review is the moderator that *pays*. Volume — number of tests — was **not significant**. I had it exactly inverted.
- **My favourite finding had an undisclosed conflict of interest.** I called one paper "the most product-relevant finding — and it's an RCT." It isn't an RCT. It has **zero replications across 159 citations in ten years.** And its senior author holds book royalties and co-founded a company selling the curriculum it supports — disclosed nowhere. It was the only commercial conflict in an eight-paper stack, and it was sitting under my favourite result.
- **"Nothing on the market measures transfer"** — flatly false. AAMC full-lengths, UWorld and Blueprint all score novel passages.
- **"Show students the gap and they'll reallocate"** — my *own* citation predicts they won't. Told that 90% of people learn better a given way, **78% put themselves in the 10%.**

**Two things made this happen, and neither was mine:** I was asked not to search for evidence that confirmed my predictions, and I was asked to record who funded each study. Those two instructions cost me four citations and found the one conflict.

---

## 6 · So what survives (45s)

Almost nothing that's an effect-size claim — because in education, effect sizes don't survive scale.

**0.13% of education findings are ever replicated.** Of seven EEF programmes tested at scale, **one survived**; the mean went from 0.25 to 0.01.

So the POVs deliberately don't rest on any effect surviving replication. They rest on **what instruments are blind to:**

1. **A percentage can't tell a guess from knowledge** — and that's a third of your correct answers.
2. **"Evidence-based" is a claim nobody in this market can support, including us.**
3. **Retention optimisation was never a readiness claim** — FSRS minimises study-minutes-per-recall-probability, with no exam in the objective function at all. The schedulers are honest; the inference downstream isn't.

---

## 7 · What that forced us to build (45s)

Each POV had to change the code, or it wasn't a POV.

- The engine **refuses to emit a score** below an evidence threshold — it returns a refusal, not a number with wide error bars. A caller that never receives a number can't render one.
- On iOS, a score is an **enum**, so rendering a refusal as a number is a **compile error**, not a code review comment.
- Memory and transfer are **partitioned and never pooled**.
- Readiness is reported on the real **472–528** scale with its range, the percent of the outline covered, and the reasons — or withheld.

**The guarantee is structural, not a promise in a README.**

---

## 8 · Close on falsifiability (30s)

Every POV states what would kill it. The headline one:

> **If confident-and-wrong rate predicts outcomes no better than raw accuracy, POV 1 is dead.**

And two objections I have not answered, which are in the document rather than buried:

- The memory-minus-performance gap is a **difference score** — reliability around **.50**.
- Our confidence intervals are **too narrow**: they model sampling error when the dominant variance is passage-to-passage.

**A tool whose whole pitch is honest measurement doesn't get to hide its own weakest numbers.**

---

## If asked

**"Isn't this just spaced repetition with extra steps?"**
No — spaced repetition optimises time-per-unit-recall. We measure whether recall survives a change in wording, which is a different quantity, and we refuse to report it when we can't.

**"How do you know the gap is real?"**
We don't yet. That's the ablation test, and it hasn't run. The claim on the record is the *measurement* one — that percent-correct is blind to guessing — which is verifiable independent of whether the gap predicts scores.

**"Why should I trust your numbers over UWorld's?"**
You shouldn't trust them more. You should notice ours come with a range and a refusal state, and theirs don't.

**"What's the weakest part?"**
The intervals are too narrow, and there's no student outcome data behind the score mapping — it's a documented linear placeholder, not a fitted model. Both are stated in the document.

# AI consensus check — pass one, POV cold

**Method.** The POV was given to a frontier model with no supporting evidence and
no framing, and it was instructed to be blunt rather than agreeable. Per the
assignment: a frontier model approximates the consensus, and is used here as a
detector, not an oracle. Enthusiastic agreement would have meant the POV merely
restated the consensus. It did not agree.

**The claim as presented (since withdrawn in part):**

> "Every MCAT/LSAT/GMAT study tool optimizes card retention, but retention stops
> being the binding constraint around week six. After that the constraint is
> transfer to novel exam passages, which nothing on the market measures — so
> students grind cards while their score plateaus.
>
> Therefore a study tool should report three separate numbers rather than one:
> memory, performance, and projected readiness — and should show the gap between
> them rather than collapsing them into a single confidence figure."

---

## Verdict: "consensus dressed as insight"

> "The diagnosis is **consensus dressed as insight**. The market claim inside it
> is **factually wrong**. The prescription is **a reasonable but under-argued
> product idea that is neither novel nor validated**."

On the transfer point being old news:

> "'Memorizing facts does not produce the ability to apply them to novel
> material' — this is the single most established finding in the transfer
> literature, going back to Thorndike & Woodworth (1901). It is also the most
> repeated piece of advice in test prep culture. [...] You have not found a
> hidden constraint; you have found the thing everyone already says out loud."

On the market claim:

> "'Nothing on the market measures transfer' — false, and confidently false.
> AAMC full-lengths, UWorld, Blueprint, Kaplan, 7Sage's per-question-type
> analytics, LSAT Demon, Magoosh — all of them score you on novel passages you
> have never seen, break it down by question type, and most project a score.
> AAMC FLs are among the highest-validity performance predictors in any consumer
> education product."

On the LSAT generalization:

> "the LSAT reference is the tell. The LSAT has almost nothing worth putting on a
> flashcard. [...] You have generalized a model of studying derived from MCAT
> Psych/Soc — the most declaratively loaded section of the most declaratively
> loaded exam — onto two tests where the premise barely holds. If you say this
> sentence in front of anyone who has taught the LSAT, you lose the room in the
> first thirty seconds."

The narrower claim it offered as survivable:

> "**no product jointly models the two signals.** Anki/FSRS knows your memory
> state and knows nothing about your passage performance. UWorld knows your
> passage performance and knows nothing about your card scheduling. Nobody uses
> transfer data to decide *when a card has stopped earning its review time*. That
> is a real, unglamorous, integration-shaped gap."

---

## Strongest objection: the gap is a difference score

> "**Your three numbers are not three numbers. Performance already contains
> memory, and the residual you are calling 'the gap' is a difference score — the
> least reliable quantity in psychometrics — that almost certainly has no
> incremental validity over the practice-test score a student already has for
> free.**"

The arithmetic, which is the part that changed our design:

> "rel(D) = (r₁₁ + r₂₂ − 2r₁₂) / (2 − 2r₁₂)
>
> Say your memory measure and your performance measure each have reliability .85
> — generous for anything built from consumer-app interaction data — and
> correlate at .70, which is *low* for two measures of overlapping content. Then
> rel(D) = (.85 + .85 − 1.40) / (2 − 1.40) = .50. You are about to put a number
> on a student's dashboard with a reliability of .5 [...] If your two measures
> are better-correlated — which they will be — the difference gets *less*
> reliable, not more. Your metric is punished for being about the same content."

On the benchmark it must beat:

> "The student's most recent full-length practice score is free, already exists,
> and predicts the real thing at roughly r = .7–.85. Your three-number system has
> to add variance *over that*. Not correlate with outcomes — add."

On actionability:

> "**a diagnostic with no distinct remedy is a decoration.** If the prescribed
> response to a large gap is 'do more practice passages,' you have built an
> expensive instrument that outputs advice available for free."

---

## What the literature already establishes

> "**Retrieval practice does transfer, but conditionally.** This one actually
> cuts against you. Butler (2010) [...] Your framing treats cards as inert; the
> literature does not."

> "**Students systematically misjudge their own learning.** [...] **This is the
> strongest support your idea has and you are not using it.** Your product is
> best understood as a metacognitive calibration intervention — correcting a
> known, documented, robust illusion — not as the discovery of an unmeasured
> constraint."

> "**Near vs. far transfer are different things.** [...] If you build reworded
> items and call the result a transfer measure, you will be measuring memory with
> extra steps and reporting it as a second construct."

---

## On "week six"

> "No. It is invented precision [...] You have taken a marketing artifact of
> Kaplan's calendar and reported it as a property of cognition."

Three reasons given: it is section-specific (CARS has zero declarative content),
baseline-dependent, and retention is a persistent maintenance cost rather than a
phase that ends. The honest version it proposed:

> "*shift allocation when the estimated marginal score gain per hour of cards
> drops below the marginal gain per hour of passages.*"

---

## What it would require to believe the gap is real

Given as gates, in order: reliability of the **difference** test–retested above
~.75; common-scale calibration via IRT or a counterbalanced matched design;
within-person rather than between-person analysis; **incremental validity over
the last full-length score** (ΔR², cross-validated, held-out students);
interventional evidence with study time held constant; and effect size in scaled
score points, not correlations.

> "If the gap adds nothing beyond the practice test the student already took, you
> built a dashboard, not an instrument. This is the test I would run first if I
> only got one."

---

## Six ways this team fools itself

1. **The transfer measure is a memory test.** "This is the modal failure and it
   is nearly invisible from the inside. Paraphrase-robustness is near transfer;
   it correlates with card memory at .8+."
2. **Study-time confound eats the effect.** "it will be a graph of who quit."
3. **You find 'week six' in your own data because you went looking for it.**
4. **Goodhart destroys the measure the moment you display it.** "Novel items
   become seen items. Your transfer measure decays into a retention measure over
   six weeks of use — the exact collapse the product exists to prevent."
5. **You validate on engagement instead of scores.**
6. **Projected readiness flatters through regression to the mean.**

---

## Bottom line, verbatim

> "The diagnosis is true but universally known, and the market claim inside it is
> wrong in a way that will discredit you with anyone who has taught these exams
> [...] The strongest honest version of this pitch is much narrower and much
> better: *spaced repetition schedulers and practice-passage analytics live in
> separate products and never inform each other, so nobody can tell a student
> when the marginal card has stopped being worth the marginal passage — and
> students' own sense of readiness is documented to be systematically wrong in
> exactly the direction that matters.*"

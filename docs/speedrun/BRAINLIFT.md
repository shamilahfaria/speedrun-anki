# Brainlift v1 — Speedrun

**Owner:** Shamilah Faria
**Status:** v1, Friday early submission
**Last updated:** 2026-08-01

---

## Purpose

Build a study tool for MCAT/LSAT/GMAT preparation that measures three different
things separately — recall, performance on unfamiliar phrasing, and projected
exam readiness — and shows the distance between them instead of collapsing them
into one confident number.

The bet: the useful product is not a better memorisation engine. Anki already is
one. The useful product is an honest instrument, because the thing that fails
these students is not their memory, it is their *measurement* of their memory.

---

## Spiky POVs

Ordered by how much disagreement each would draw from someone building a
competing tool.

### 1. A retention percentage is not a readiness score, and reporting it as one is the industry's core dishonesty.

Every spaced-repetition tool reports a retention figure. Learners steer by it,
because it is the only number they are given. Nothing in that number is evidence
about performance on an item they have not seen. We report both, separately, and
the gap between them — and the gap is the headline, not a footnote.

### 2. Refusing to score is a product feature, and it must live in the engine, not the interface.

Below a threshold of evidence, the correct output is "not enough evidence," not a
number with wide error bars. A number with wide error bars still gets read as a
number. This is implemented as engine behaviour: `sufficient == false` returns
`point = 0.0`, so a caller that never receives a score *cannot* render one. Put
that rule in the display layer and it survives exactly until someone writes a
second display layer.

### 3. "Flashcards don't transfer" is false, and building on it would have been building on sand.

This is the POV I got wrong first and corrected under evidence. Butler (2010)
found repeated *retrieval* beats restudying on novel inferential questions, and
that repeating the same item transferred about as well as varying it. Retrieval
practice is not the problem.
<https://andymatuschak.org/files/papers/Butler%20-%202010%20-%20Repeated%20Testing%20Produces%20Superior%20Transfer%20of%20Learning%20Relative%20to%20Repeated.pdf>

The surviving claim is narrower and stronger: retrieval practice *does* build
transfer, **and a learner still cannot read their transfer performance off their
recall performance.** Butler measured group means under a manipulation; he never
measured whether one person's recall accuracy predicts their own performance on
novel items. That is a calibration question, it is unanswered in the literature I
could reach, and it is the question our engine is built to answer per learner.

### 4. The learner's own confidence is the least reliable instrument in the room, and it does not self-correct.

Koriat & Bjork (2005): judgments of learning are made with the answer visible;
the exam takes the answer away, and learners fail to discount it.
<https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/Koriat_RBjork_2005.pdf>
Karaca et al. (2023): the weakest students overpredicted by ~15 points and their
confidence did not move across a semester of disconfirming results.
<https://pmc.ncbi.nlm.nih.gov/articles/PMC10607382/>
Bjork & Bjork relay the sharpest version: told that most people learn better
under interleaving, most participants concluded they were personally the
exception.
<https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-06/itow-introducing-desirable-difficulties-into-practice-and-instruction-bjork-and-bjork.pdf>

Design consequence: showing someone a better number is not enough. The tool has
to show the *disagreement* between two numbers, because a single number gets
absorbed into an existing belief and a contradiction cannot be.

### 5. Card volume is a weak lever, and selling it as the main one is malpractice.

Deng, Gluckstein & Larsen (2015): roughly 1,700 additional unique cards were
associated with about one additional Step 1 point, and one of the two card
systems studied showed no relationship to score at all.
<https://pmc.ncbi.nlm.nih.gov/articles/PMC4673073/>
This is correlational self-report, not a causal measurement — but a tool whose
main promise is "more cards" is promising the weakest available lever.

---

## Knowledge tree

**Measurement (the product's centre)**
- Separating DOK 1 recall from DOK 2/3 transfer requires the two to be
  distinguishable in the data. Implemented with note tags (`speedrun::probe`,
  `speedrun::topic::<name>`) rather than a schema change — tags already sync,
  already survive import/export, and need no migration, which keeps the
  zero-corruption guarantee cheap.
- Wilson score interval, not the normal approximation. Study data is small-n with
  proportions pinned near 1.0; the normal approximation escapes [0,1] and
  collapses to zero width at 100%, which would let the product claim certainty
  from a handful of easy reviews. The statistics had to refuse that structurally.
- Give-up rule: 20 graded reviews and 5 distinct cards minimum, per score.

**Engine placement**
- The scoring model lives in Rust (`rslib/src/transfer/`) because the iOS client
  reaches Anki only through a C FFI into rslib. Anything in pylib is unreachable
  from the phone, so a Python model would have to be reimplemented in Swift — two
  implementations of one statistical model, drifting apart, disagreeing about the
  same collection. In Rust, both platforms run the same compiled code by
  construction.
- Exposed as a new protobuf service, which auto-generates the Rust trait, the
  Python binding, and the dispatch entry the iOS client calls. One definition,
  three languages, no hand-written FFI.

**A trap worth recording**
- Protobuf service indices are descriptor-pool positions, and proto files are
  sorted alphabetically before the pool is built. The iOS client hardcodes those
  indices. A new proto file named anything sorting before `tags.proto` silently
  renumbers existing services and breaks the phone with no compile error. Named
  `transfer.proto` so it sorts last; verified in the generated dispatch table
  that every existing index was unmoved and ours appended at 45.

---

## What would prove this wrong

Stated before running it, so it cannot be quietly redefined afterwards.

1. **The gap is not real.** If, across learners with sufficient evidence, memory
   and performance scores track each other closely, then the separation is
   measuring noise and the product's premise is dead. The ablation test
   (Speedrun on / Speedrun off / stock Anki) is designed to be able to return
   this answer.
2. **The gap is real but useless.** If the gap exists but does not predict
   anything about scored outcomes, we are reporting a true fact with no decision
   value.
3. **The engine is not calibrated.** If our stated 80% confidence intervals do
   not contain the truth about 80% of the time on held-back data (Brier score,
   log loss), then we are committing the exact sin we accuse competitors of, with
   better vocabulary.
4. **The probes are not measuring transfer.** If reworded probes are answered at
   the same rate as their source cards, the paraphrase test has failed and the
   probes are just more recall items wearing a costume.

Any of these outcomes gets written up rather than buried. A tool whose whole
pitch is honest measurement does not get to hide a negative result.

---

## Sources

Verified independently: an automated check re-fetched every source with no access
to the reasoning behind the claims. Nine supported, one overstated (Butler —
corrected above, and the correction left visible), three unverifiable because
Student Doctor Network returns 403 to fetchers. Reachability separately confirmed
by `scripts/check-sources.sh`: 10 reachable, 2 bot-blocked, 0 dead.

Full citation list and the first-person accounts: [problem-statement.md](problem-statement.md).

**Known hole:** Reddit (r/Mcat, r/LSAT, r/medschoolanki) was unreachable from the
research environment. That is where repetition users discuss this most directly,
so the single most on-point account — high retention alongside a flat score — is
not in a readable primary source here. The pattern is described secondhand by
companies selling preparation material, which was excluded as marketing rather
than testimony. Closing this needs a Reddit-capable path, not more searching.

---

## Insights

- **The correction was worth more than the original claim.** The thesis I started
  with ("flashcards don't transfer") was popular, intuitive, and contradicted by
  the first paper I checked carefully. The thesis that survived — recall practice
  works, *and* your recall score still doesn't tell you your transfer performance
  — is narrower, harder to say in one breath, and actually defensible.
- **Blind verification is structurally different from careful review.** The check
  that caught this had no access to what I was arguing. A reviewer who knew the
  thesis would very likely have read Butler as close enough.
- **Honesty guarantees decay upward through the stack.** The engine can refuse to
  produce a number, but the display layer can still render that refusal as a 0%.
  The guarantee has to be re-asserted, and tested, at every layer that can undo
  it — so there is a test asserting no `0%` leaks into a refused cell.

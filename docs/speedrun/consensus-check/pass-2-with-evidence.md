# AI consensus check — pass two, with evidence

**Method.** Same reader, now given (a) explicit withdrawal of the claims it
falsified, (b) the five primary sources, and (c) a description of what was
actually built. It was asked to name specifically what moved and what did not.
Per the assignment's warning, models fold under pressure and will call a bad idea
brilliant if pushed — so no argument was made, only evidence supplied, and it was
asked to name what changed its mind.

**Withdrawn before it read anything:** "nothing on the market measures transfer"
(false); "week six" (invented precision); the LSAT/GMAT generalization (product
now targets MCAT only).

---

## 1. Does the calibration reframe survive?

> "It survives as a *claim*. It does not reduce the *technical burden* by one
> bit, and I think the team may believe it does."

> "Calibration is defined as |belief − criterion|. You cannot tell a learner
> their calibration is off without a criterion. The criterion here is a transfer
> measure. So every objection I raised about measuring transfer [...] is still
> fully in force, because the transfer measure is now load-bearing in a *harder*
> way than before. A capability claim can survive on group-level validity. A
> calibration claim is inherently individual-level."

What improved:

> "the claim is now about a *decision-support gap* rather than a *measurement
> gap*. 'No product tells a student when the marginal card has stopped being
> worth the marginal passage' is, as far as I can tell, true, and it is the
> honest residue of the withdrawn overclaim. That is a real and unoccupied space."

What did not survive — a second overclaim caught:

> "**'neither informs the other' is false in the same species as 'nothing
> measures transfer.'** [...] The defensible claim is about *incremental validity
> at the margin* [...] The current sentence is a rhetorical escalation of a true
> narrower claim, and it is the same move that produced 'week six.'"

## 2. Difference scores, and a direct hit on our Wilson interval

> "Displaying two numbers side by side and letting the learner perform the
> subtraction does not escape the psychometrics — it launders them. It is
> arguably worse than an explicit gap score, because an explicit difference can
> carry an explicit interval *on the difference*."

> "**the Wilson interval is correct reasoning about the wrong variance
> component.** Wilson handles binomial sampling error on a proportion under item
> exchangeability. The dominant variance in passage performance is item sampling
> [...] and person-by-occasion. Your intervals will be too narrow, and
> narrow-and-principled is the most dangerous failure mode available, because it
> looks like rigor."

What it says to display instead, ranked:

1. **Elicit the learner's prediction before the passage set and score it against
   the outcome on those same items.** "This is Koriat & Bjork's own paradigm and
   it is the construct your revised claim is actually about [...] which removes
   the two-different-instruments attenuation that drives rel(D) to .50. This is
   the display that follows from your reframe. The memory-versus-transfer gap is
   not."
2. Two intervals, separately labelled, never subtracted for the user.
3. A **discordance flag**, not a gap magnitude — sign and existence, not
   magnitude. With the warning: "with rel(D) around .50, this flag fires rarely
   and late. **If your core value proposition requires it to fire for most users
   within the first few weeks, the psychometrics are telling you the product
   doesn't work.** Run that simulation before building the UI."

## 3. Does Karaca rescue the paraphrase measure?

> "Mostly a separate issue [...] A perfectly-received signal about the wrong
> construct is still the wrong construct. So no, Karaca does not rescue the
> paraphrase measure."

The exception, which it volunteered against its own position:

> "if what you are estimating is *miscalibration* rather than *transfer
> capability*, then a near-transfer item is a legitimate criterion, because the
> learner predicted on that same item. [...] That is the strongest argument
> available for your side and I'd have been underdelivering not to find it."

With the caveat that calibration measured on near transfer generalises to far
transfer "only if miscalibration is a reasonably stable person-level trait,"
which is "an open assumption, not a premise."

## 4. Goodhart / pool depletion

> "Engineerable, not fatal. But none of the three built guarantees touch it, and
> the team may be counting them as coverage."

Requirements it named:

- **"A hard exposure ledger with permanent burn.** Any item seen once is
  *ineligible* for the transfer estimate — not down-weighted, ineligible. And
  pool exhaustion must trigger the same refusal type you already built. You built
  the right primitive; extend it to this. **That single change would move me more
  than any argument.**"
- A pool-life projection: days until refusal becomes permanent at observed burn
  rate. "If that is shorter than a study horizon, this is a one-time diagnostic,
  not a longitudinal instrument, and should be scoped and sold as one."
- Content-stratified reserves, so burn falls on items rather than domains.
- A drift audit: compare early-pool against late-pool estimates within a user.
- No leakage of content targeting into the display.

## 5. Which failure modes remain live

| Failure mode | Status |
|---|---|
| Rigor theater — precision about the wrong quantity | **LIVE, intensified.** "Wilson intervals and refusal types are real engineering aimed at sampling error in a measure whose construct is unvalidated." |
| Assuming the learner acts on the number | **LIVE, and self-falsified by our own citation** — see below |
| Literature as decoration | **Largely resolved.** "The citations are now on-topic and the withdrawals were real." |
| Selection effects in validation | **LIVE, untouched** |
| Mistaking an absent competitor feature for a user need | **LIVE — "the objection I'd bet on"** |
| Correlational evidence constraining design | **Partly live.** Deng "argues against your market more than for it." |

### The finding that should change the product

> "**The one that got worse:** Yan et al. is the most damaging item in your own
> stack, cited approvingly. Participants told the general finding concluded they
> were personally the exception. A dashboard that tells a learner their allocation
> is wrong will meet exactly that response. Your evidence base predicts your
> product's failure mode. The correct inference is that this should not primarily
> be a *display*. It should be a *scheduler* — change what is served next rather
> than what the learner believes. Behavior change routed through belief change is
> the mechanism Karaca and Yan both say fails. Behavior change routed through
> defaults does not require recalibration to work."

## 6. Verdict, split by conjunct

- "Metacognitive judgments are overconfident and fluency-driven" — **consensus.**
  "nobody cites a review for a contrarian claim."
- "Learners cannot read transfer off recall" — **contrarian in the strong form,
  wrong as stated**, defensible in the marginal-actionability form.
- "Confidence fails to correct under disconfirming feedback" — **contrarian,
  thinly supported**, and "if true it damages your product more than it justifies
  it."
- "No product closes this loop" — **true, but a market fact, not a scientific
  finding.**

### What moved it

> "The withdrawal of 'nothing measures transfer' was my central objection and it
> is conceded outright [...] Accepting Butler 2010 including the part that cuts
> against you [...] is a costly concession that removes the obvious product story,
> and you made it anyway; I weight costly concessions heavily. And **the
> refusal-as-a-distinct-type is the single strongest evidence in the packet**,
> more than any citation. Most products emit a number with a disclaimer nobody
> reads. Making it a *type error* to render a refusal as a number is a structural
> commitment against the exact failure I predicted, and it is not cosmetic."

### What did not move it

> "Karaca, for the reasons above. Deng, which cuts the other way. The Wilson
> choice, which is right reasoning about the wrong variance. And Yan et al., which
> moved me in the direction opposite to the one intended."

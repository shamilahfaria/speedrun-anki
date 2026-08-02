# Teardown: what MCAT tools actually measure

**Provenance.** These tools were researched from public vendor documentation,
help centres, published data, and user reports on Student Doctor Network and
Reddit. They were **not used first-hand** — no accounts were created. §2 of the
brief asks for behaviour observed by studying on them, so this is weaker evidence
than the brief requires, and every claim below is labelled: **[VENDOR DOC]**,
**[VENDOR DATA]**, **[USER REPORT]**, or **[CANNOT DETERMINE]**.

A note on one exclusion and its reversal: a research pass excluded all Reddit
quotes on the grounds that Reddit was unreachable and therefore unverifiable.
That was a correct instinct from a wrong premise — its fetcher was blocked, but
`old.reddit.com` is reachable by other means. Six quotes across five threads were
subsequently re-fetched and string-matched against the raw pages by hand. They
are included, and marked as verified.

---

## The benchmark nobody meets: the exam itself

All **[VENDOR DOC — AAMC]**:

- The MCAT reports every section score with a **±1 confidence band** and the
  total with **±2**. AAMC states scores "will not be perfectly precise" and that
  the bands are "intended to discourage distinctions between applicants with
  similar scores."
- Only **35%** of science questions test Skill 1, knowledge of concepts. **65%**
  test reasoning, research design and data interpretation.
- CARS contains **zero** recall content: "Everything you need to know to answer
  test questions is in the passages and the questions themselves." Its largest
  component is *Reasoning Beyond the Text*, at 40%.

**Not one of the six tools below publishes a confidence interval, standard error,
or score band on its own primary metric. The products are more confident than the
exam they predict.**

---

## What each tool reports, and what it measures

### UWorld MCAT QBank

- **Metric:** percentage correct, benchmarked against other users' average — not
  a percentile. **[VENDOR DOC]** The QBank emits no predicted score; the
  separately sold practice exams do, claiming scaled scores that "predict your
  exam readiness."
- **DOK measured vs implied:** genuinely mixed, and **never disaggregated**. One
  percentage pools DOK 1 discretes with DOK 3 passage reasoning — and the student
  silently controls the mix, since custom tests of ≤4 questions return only
  discretes. **[USER REPORT]**
- **Refuses to score?** No. A user reports their average "flatlined at 50%" at
  ~22% through the bank; the number is displayed and treated as stable at low n.
- **Rewording?** No, and near-disconfirmed: items are hand-authored fixed assets,
  and "UWorld does not use AI to create test prep questions." **[VENDOR DOC]**
  Reset is "a permanent and irreversible purge," once per subscription. No
  warning is published that second-pass percentages aren't comparable to first.
- **Calibration?** **None.** No confidence rating, no self-prediction, no
  confidence-vs-correctness comparison anywhere.
- **The number's predictive value, from users in one thread [USER REPORT,
  verified]:** 80% → 512. 71% → 520. 68% → 514–520. Non-monotonic, inside a
  single discussion.

### The Anki deck ecosystem (AnKing / MilesDown / Jack Sparrow)

- **Metric:** card counts, True Retention, retrievability. Note that AnKing's own
  MCAT deck page makes **no progress or score claim at all** — measurement is
  outsourced entirely to Anki's generic scheduler.
- **DOK:** 1, unambiguously. Retrievability is the probability of recall for
  *that specific card*, conditioned on that card's own history. Nothing in the
  model has a term for a novel stem or an inference chain. Anki's own manual
  concedes the ceiling: shared decks "should be used as a supplement to external
  material, not as a replacement." **[VENDOR DOC]**
- **Refuses to score?** No — and the whole validity claim reduces to one manual
  sentence: "Again counts as 'Fail'; Hard, Good, and Easy count as 'Pass'." Anki
  never sees your answer. **The student is simultaneously the examinee and the
  entire scoring apparatus.** The nearest "you don't know this" signal is the
  leech mechanism, which at 8 lapses *suspends* the card — the scoreboard
  improves because the hard item left the room.
- **Rewording?** **No item-variation feature of any kind.** The card front is
  byte-identical on review 1 and review 40. The manual names the resulting
  failure itself: small decks mean "you will end up seeing cards in a
  recognizable order… which leads to weaker memories."
- **Calibration?** It *looks* like calibration — desired retention vs True
  Retention — but the "actual" is the same self-report as the "predicted." And
  FSRS is worst-calibrated exactly where diligent students live: a contributor
  states its accuracy "is worse for very high (>95%) and very low (<60%)
  probabilities." **[VENDOR DOC]**
- **Volume inflation:** AnkiWeb lists *notes*; marketing counts *cards* — roughly
  2×, confirmed by a moderator. **No published correlation exists between any
  deck's retention or maturity metrics and an MCAT score.** Outcome claims are
  single anecdotes.

### Blueprint MCAT — the strongest finding here

Blueprint publishes per-student data comparing its own full-lengths to official
MCAT results. Re-deriving from **their own 54-student table [VENDOR DATA]**:

| From Blueprint's published data | |
|---|---|
| Mean **absolute** error, last Blueprint FL vs official (n=43) | **7.2 points** |
| Students off by ≥5 points | **65%** |
| Students off by ≥10 points | **19%** |
| Worst single miss | **33 points** — Blueprint FL **472**, the floor of the scale, vs official **505** |
| Largest within-student swing across Blueprint FLs | **22 points** (478 → 499 → 487) |

Blueprint reports this instrument's output as a **point estimate with no error
band.** The AAMC reports the real thing with ±2.

There is also an internal contradiction **[VENDOR DOC vs VENDOR DATA]**:
marketing calls the diagnostic "statistically equivalent to the real MCAT, with
an average difference of just 0.3 point," while Blueprint's own PDF shows the
same diagnostic sitting 13.1 points *below* official scores — and sells that gap
as proof the course works. A *mean* difference of 0.3 measures bias, not
precision; errors of +8 and −8 average to zero.

Methodology, from the PDF itself: ~1,000 students emailed, 164 responded, 54 in
the final dataset. A ~5% response rate, self-reported and self-selected.

Also: the "Popular Opinion" hint shows the most-selected answer among other
students, described in Blueprint's help docs as providing "affirmation" for
students who struggle with confidence. That **actively corrupts** calibration by
leaking the modal answer before the student commits.

### Kaplan MCAT

- **Metric:** scaled score plus percentile rankings. **[VENDOR DOC]**
- **Refuses to score?** No, and Kaplan runs hard the other way: its own FAQ says
  the practice tests "pinpoint your true score with absolute confidence," and
  answers the question "are Kaplan's scores deflated?" with "No."
- **Calibration?** No loop — but tellingly, Kaplan **assigns the calibration work
  to the student by hand**, advising them to keep "a dedicated error log" and to
  "treat as an error" any item they guessed correctly. The product sells the
  score; the blog tells you to keep a paper log because the score cannot tell a
  lucky guess from knowledge.
- **The number's predictive value [USER REPORT, n=288 self-reported, 2015]:**
  mean difference from actual — AAMC 6.03 points, **Kaplan 14.06**, TPR 11.70,
  EK 8.86. Across **141 Kaplan users, every single one scored above their Kaplan
  composite**, from +3 to +27. The thread author's own regression: r² = 0.36, so
  "if you're in the 505 range for the Kaplan… others who have scored similarly
  have been in the 508–523 range" — **a 15-point band, reported to the student as
  a point estimate.**
  *Counter-evidence, not laundered:* several users report the opposite direction,
  the author concedes self-selection bias, and the data is 2015–2021.

### Jack Westin

- **The most prominent personal number on the front page is a "Daily Streak."**
  **[VENDOR DOC]** That is activity, not knowledge.
- Its institutional dashboard names a tile: **"JW QBank usage — a predictor of
  score improvement."** The vendor explicitly frames *volume consumed* as the
  predictor. **[VENDOR DOC]**
- Its "not there yet" signal — student tiering for early intervention — is
  surfaced **to advisors, not to the student.**
- **[USER REPORT, verified]** A student consistently getting 0–1 wrong on JW
  passages scored ~71% and ~79% on official AAMC question packs, and attributes
  it to JW's answer logic being "more direct" than AAMC's. Near-ceiling accuracy
  inside the tool; official material tells a different story.

### Memm

*Corrected after a second research pass reached Reddit through archive APIs
(PullPush, Arctic Shift) that an earlier pass could not. The earlier version of
this section said no progress mechanic was documented beyond a streak. That was
wrong.*

- **Metric: a three-button self-rating, and a streak.** Memm's own onboarding
  post documents it: "Grade the difficulty of each card using the three buttons…
  If you get the card wrong, select 'Again'. If you got the card correct but it
  was difficult, select 'Good'. If you got the card correct easily, select
  'Easy'." **[VENDOR DOC]** So it is structurally identical to Anki: **the
  student is the entire scoring apparatus.** There is no accuracy metric because
  there is nothing to be graded on — "Flashcard-based only — no practice questions
  or full-length tests." **[THIRD-PARTY REVIEW]**
- **Refuses to score?** It never emits one, but that is the absence of assessment
  rather than epistemic restraint. **A streak always increments.**
- **Rewording?** Searched 165 archived comments and 97 post titles for
  `reword` / `rephras` / `verbatim` / `same card`: **zero hits.**
  **[CANNOT DETERMINE]** — not established either way.
- **The most striking find in the whole teardown is on Memm's own blog.** In a
  vendor-published success interview, the student describes the exact failure a
  fixed-wording card produces: "I was memorizing the cards, not the content on the
  cards… I would see a card and immediately know the answer, but it was more
  pattern recognition from seeing the card before rather than actually
  understanding what the card was testing me on." **[VENDOR-published user
  interview]** The vendor is publishing, as marketing, a first-person account of
  its own metric being satisfied without the knowledge it claims to represent.
- **Outcome claims:** "average score increase of 11.6 points" from a post-test
  survey with no denominator; "13.4 point avg. increase of retakers"; "98%
  satisfaction rate." Against which, from a verified buyer on Memm's own review
  platform: **"Memm made my score go DOWN."** **[USER REPORT]**
- **Weight the positive reviews carefully:** roughly 60 of 97 r/Mcat "Memm" posts
  are moderator-removed, and several positive posts carry referral codes.
  Organic negative reports have no such incentive.
- **Relevant to our own crash-resilience requirement:** a 2023 incident wiped
  in-app progress for users mid-preparation — "All my work for the past few
  months...gone," three weeks before one student's exam date. **[USER REPORT]** A
  study tool that loses a collection loses months, which is why "zero corrupted
  collections" is a product requirement and not a nicety.

---

## What students say

**[USER REPORT — all re-fetched and string-matched against the raw pages]**

A student who finished content review and matured two major decks reports
full-lengths "in the low 500s."
<https://old.reddit.com/r/Mcat/comments/1s3jntm/should_i_quit/>

Four full-lengths in at 493, 500, 496, 500, with "4,000 Anki cards to review."
<https://old.reddit.com/r/Mcat/comments/1upen54/4_fls_in_still_stuck_at_500_test_end_of_july_4000/>

The clearest statement of the gap, from a student who had matured 80% of their
deck: they have "a lot of isolated facts memorized from Anki" but cannot apply
them when a question "requires integrating multiple ideas."
<https://old.reddit.com/r/Mcat/comments/1lou4yd/struggling_with_the_big_picture_after_content/>

The calibration failure named outright: a deck "gave me a false sense of security
by the time I got into practice questions," in a thread where another student
writes decks are "not good at all for building the critical thinking that the
MCAT tests."
<https://old.reddit.com/r/Mcat/comments/1k69rhy/any_success_with_anking/>

And the mechanism, from the author of a widely-used community resource:
"memorizing what the answer looks like rather than the actual information," which
"can lead to situations where someone can 'recall' the answer in Anki but not in
real life."
<https://old.reddit.com/r/Anki/comments/1ge2aui/note_types_to_avoid_pattern_matching/>

On SDN, an OMS-2 reports the endpoint: "I was doing 1,400 cards a day and
spending 6 hours on review alone… I stopped using anki second year and my test
average increased from high D's to mostly A's."
<https://forums.studentdoctor.net/threads/percentage-correct-on-mature-cards.1445727/>

---

## Four cross-cutting findings

**1. Not one tool reports uncertainty.** Every one emits a point estimate. The
only instrument here with real psychometrics behind it — the actual MCAT — is the
only one that publishes confidence bands and warns against over-reading small
differences.

**2. Not one tool rewords an item.** Across six vendors: **zero** item-variation
or isomorphic-item features, and none marketed. Every "retest" mechanism is
verbatim repetition — UWorld's reset, Blueprint's recycle mode and 5-attempt
full-lengths, Anki's byte-identical fronts. All of them therefore inflate the
metric they report as progress, and none warns the student that second-pass
numbers aren't comparable to first-pass.

**3. Calibration is absent everywhere.** No tool compares predicted performance
to actual performance. The features that resemble it are not: Anki's
Again/Hard/Good/Easy is self-report scored against itself; Blueprint's flashcard
"comfort" rating has no right/wrong to check against; Blueprint's "Popular
Opinion" hint corrupts it outright. Kaplan outsources it to a paper error log.

**4. Every headline score-gain claim is baselined on the vendor's own
uncalibrated diagnostic**, and its magnitude depends entirely on that diagnostic
reading low. None uses a control group. Response rates, where disclosed, are
around 5%.

---

## What this does and does not support

**Supports POV 1** (an instrument that cannot refuse is not an instrument):
directly and strongly. The exam itself publishes ±1 and ±2 bands; not one prep
tool publishes any. Blueprint emits a floor-of-scale 472 from a half-length
diagnostic against a student who scored 505.

**Supports POV 3** (retention optimisation was never a readiness claim): the
deck ecosystem makes no score claim at all, and Anki's manual explicitly positions
shared decks as a supplement rather than a replacement. The overclaim is
downstream of the tool.

**Supplies a second, distinct failure the transfer framing missed:** students
passing cards by recognising the card. That is not a limit of transfer — it is
evidence the original success was a property of the card's surface. A reworded
probe detects it directly, and no tool on the market has one.

The sharpest version of this is that **a vendor publishes it as marketing.**
Memm's own success-story interview has the student saying they were "memorizing
the cards, not the content on the cards" and knew answers by "pattern recognition
from seeing the card before." The failure is well enough known to appear in
promotional copy, and still nothing in any product measures it.

**Does not support** any claim that these tools fail to measure performance on
novel material. UWorld, Blueprint, Kaplan and Jack Westin all do. What they do
not do is report uncertainty, vary an item, or check a prediction against an
outcome.

**Weakest part of this teardown:** it is secondhand. Much of the user evidence is
2015–2021, and no first-person account was found stating a numeric retention
figure alongside a disappointing score — the single conjunction this product's
thesis would most like to cite.

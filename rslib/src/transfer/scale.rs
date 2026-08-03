// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
//
// Speedrun addition: mapping transfer performance onto the real MCAT scale.
//
// WHY THIS IS THE MOST DANGEROUS FILE IN THE PROJECT
//
// Everything else here measures something. This file *projects* — it turns an
// observed proportion into a number a person may use to decide whether to sit a
// $340 exam that gates their career. The assignment is explicit that inventing a
// readiness number is an automatic fail, and this is where that would happen.
//
// So the mapping is stated, provisional, and deliberately conservative:
//
//   1. It is a documented linear map, not a fitted model. We have no student
//      outcome data. A curve fitted to nothing is a curve that lies with more
//      decimal places.
//   2. It refuses far more often than it reports. Below the coverage floor it
//      returns no number at all, whatever the accuracy looks like.
//   3. The interval comes from the Wilson bounds on the underlying proportion,
//      so a thin evidence base yields a wide band rather than a confident point.
//   4. Confidence is driven by COVERAGE, not by accuracy. A learner scoring 95%
//      on 8% of the outline is not "high confidence" — they are unmeasured.
//
// KNOWN LIMITATION, STATED RATHER THAN HIDDEN: the interval reflects binomial
// sampling error only. The dominant variance in real passage performance is item
// sampling and person-by-occasion, so these bounds are TOO NARROW. Until that is
// modelled, treat the projection as a floor on uncertainty, not an estimate of
// it. This is recorded in docs/speedrun/BRAINLIFT.md as an open question.

use crate::transfer::Score;

/// The real MCAT total scale.
pub const SCALE_MIN: u32 = 472;
pub const SCALE_MAX: u32 = 528;

/// Below this fraction of the official outline, no projection is made at all.
///
/// The brief's worked example refuses below 50% topic coverage. We adopt that.
/// A projection from a fifth of the exam is a guess wearing a uniform.
pub const MIN_COVERAGE_FRACTION: f64 = 0.50;

/// Minimum graded probe observations before projecting.
pub const MIN_PROBE_OBSERVATIONS: u32 = 200;

/// Map a proportion in 0..1 onto 472..528.
///
/// Deliberately linear across the full scale. The real relationship is
/// certainly not linear — scaled scores are equated against a national
/// distribution we do not have — but a linear map is honest about being a
/// placeholder in a way that an invented curve is not.
fn proportion_to_scaled(p: f64) -> u32 {
    let clamped = p.clamp(0.0, 1.0);
    let span = (SCALE_MAX - SCALE_MIN) as f64;
    SCALE_MIN + (clamped * span).round() as u32
}

/// Confidence label, driven by coverage first and evidence volume second.
fn confidence_label(coverage: f64, observations: u32) -> &'static str {
    if coverage >= 0.85 && observations >= 800 {
        "high"
    } else if coverage >= 0.65 && observations >= 400 {
        "moderate"
    } else {
        "low"
    }
}

pub struct Projection {
    pub point: u32,
    pub lower: u32,
    pub upper: u32,
    pub sufficient: bool,
    pub confidence: String,
    pub reasons: Vec<String>,
    pub give_up_rule: String,
}

/// Project a scaled score, or refuse and say why.
///
/// `readiness` is the pooled probe proportion; `coverage` is the fraction of the
/// official outline with any attributable evidence.
pub fn project(readiness: Score, coverage: f64, covered: u32, total: u32) -> Projection {
    let give_up_rule = format!(
        "No projection below {}% outline coverage or {} graded probe reviews.",
        (MIN_COVERAGE_FRACTION * 100.0) as u32,
        MIN_PROBE_OBSERVATIONS
    );

    let mut reasons = Vec::new();

    // Refusals are reported with their cause, always. A learner who is told
    // nothing learns nothing; a learner told "you have covered 18% of the
    // outline" knows exactly what to do next.
    if !readiness.sufficient {
        reasons.push(format!(
            "Not enough graded probe reviews yet ({} so far).",
            readiness.observations
        ));
    }
    if coverage < MIN_COVERAGE_FRACTION {
        reasons.push(format!(
            "Only {} of {} exam topics have any evidence ({:.0}% of the outline).",
            covered,
            total,
            coverage * 100.0
        ));
    }
    if readiness.observations < MIN_PROBE_OBSERVATIONS {
        reasons.push(format!(
            "{} graded probe reviews; {} needed to project a score.",
            readiness.observations, MIN_PROBE_OBSERVATIONS
        ));
    }

    let ok = readiness.sufficient
        && coverage >= MIN_COVERAGE_FRACTION
        && readiness.observations >= MIN_PROBE_OBSERVATIONS;

    if !ok {
        return Projection {
            point: 0,
            lower: 0,
            upper: 0,
            sufficient: false,
            confidence: "none".into(),
            reasons,
            give_up_rule,
        };
    }

    let confidence = confidence_label(coverage, readiness.observations);
    reasons.push(format!(
        "Based on {} graded probe reviews across {:.0}% of the exam outline.",
        readiness.observations,
        coverage * 100.0
    ));
    reasons.push(
        "Range reflects sampling error on your own answers only; it does not \
         model passage-to-passage variation, so treat it as a floor on \
         uncertainty."
            .into(),
    );

    Projection {
        point: proportion_to_scaled(readiness.point),
        lower: proportion_to_scaled(readiness.lower),
        upper: proportion_to_scaled(readiness.upper),
        sufficient: true,
        confidence: confidence.to_string(),
        reasons,
        give_up_rule,
    }
}

#[cfg(test)]
mod test {
    use super::*;

    fn score(point: f64, lower: f64, upper: f64, obs: u32) -> Score {
        Score {
            point,
            lower,
            upper,
            observations: obs,
            cards: obs,
            sufficient: true,
            needed_observations: 20,
            needed_cards: 5,
        }
    }

    #[test]
    fn maps_onto_the_real_scale() {
        assert_eq!(proportion_to_scaled(0.0), 472);
        assert_eq!(proportion_to_scaled(1.0), 528);
        assert_eq!(proportion_to_scaled(0.5), 500);
        // Never escapes the scale, whatever it is handed.
        assert_eq!(proportion_to_scaled(-5.0), 472);
        assert_eq!(proportion_to_scaled(99.0), 528);
    }

    #[test]
    fn refuses_below_the_coverage_floor() {
        // Excellent accuracy, huge evidence base, but a fifth of the outline.
        let p = project(score(0.95, 0.93, 0.97, 5000), 0.20, 12, 59);
        assert!(!p.sufficient, "must refuse on coverage alone");
        assert_eq!(p.point, 0);
        assert!(
            p.reasons.iter().any(|r| r.contains("outline")),
            "refusal must name coverage as the cause: {:?}",
            p.reasons
        );
    }

    #[test]
    fn refuses_on_thin_evidence_even_with_full_coverage() {
        let p = project(score(0.80, 0.70, 0.88, 40), 1.0, 59, 59);
        assert!(!p.sufficient);
        assert!(p.reasons.iter().any(|r| r.contains("probe reviews")));
    }

    #[test]
    fn projects_with_a_range_when_earned() {
        let p = project(score(0.64, 0.60, 0.68, 900), 0.90, 53, 59);
        assert!(p.sufficient);
        assert_eq!(p.point, 508); // 472 + 0.64*56 = 507.8 -> 508
        assert!(p.lower < p.point && p.point < p.upper);
        assert_eq!(p.confidence, "high");
        // The give-up rule travels with the score so it can be checked.
        assert!(p.give_up_rule.contains("50%"));
    }

    #[test]
    fn confidence_tracks_coverage_not_accuracy() {
        // Near-perfect accuracy, mediocre coverage -> not high confidence.
        let strong_thin = project(score(0.98, 0.96, 0.99, 400), 0.55, 33, 59);
        assert!(strong_thin.sufficient);
        assert_ne!(strong_thin.confidence, "high");

        // Mediocre accuracy, broad coverage -> better confidence.
        let weak_broad = project(score(0.55, 0.52, 0.58, 900), 0.90, 53, 59);
        assert_eq!(weak_broad.confidence, "high");
    }

    #[test]
    fn a_refusal_still_explains_itself() {
        let p = project(score(0.5, 0.4, 0.6, 10), 0.10, 6, 59);
        assert!(!p.sufficient);
        assert!(!p.reasons.is_empty(), "a refusal with no reasons is useless");
        assert!(!p.give_up_rule.is_empty());
    }
}

// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
//
// Speedrun addition.

/// z for a two-sided 95% interval.
const Z: f64 = 1.959_963_984_540_054;

/// A proportion with a confidence interval.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Proportion {
    pub point: f64,
    pub lower: f64,
    pub upper: f64,
}

/// Wilson score interval for a binomial proportion.
///
/// Chosen over the normal approximation deliberately. Study data is exactly the
/// regime where the normal approximation misbehaves: small counts per topic, and
/// proportions pinned near 1.0 for well-known material. The normal approximation
/// produces intervals that extend past 1.0 and collapses to zero width when
/// every review passed, which would let the product claim certainty from a
/// handful of easy reviews -- the failure this codebase exists to avoid.
///
/// Returns `None` for n == 0; there is no proportion to report.
pub fn wilson_interval(successes: u32, trials: u32) -> Option<Proportion> {
    if trials == 0 {
        return None;
    }
    let n = trials as f64;
    let p_hat = successes as f64 / n;
    let z2 = Z * Z;

    let denom = 1.0 + z2 / n;
    let center = (p_hat + z2 / (2.0 * n)) / denom;
    let spread = (p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n)).sqrt();
    let half_width = (Z / denom) * spread;

    Some(Proportion {
        point: p_hat,
        lower: (center - half_width).max(0.0),
        upper: (center + half_width).min(1.0),
    })
}

#[cfg(test)]
mod test {
    use super::*;

    /// Tolerance for comparing against externally-computed reference values.
    const EPS: f64 = 1e-4;

    #[test]
    fn matches_reference_values() {
        // Reference values for the 95% Wilson score interval, computed from the
        // closed form. 8/10 is the standard worked example.
        let p = wilson_interval(8, 10).unwrap();
        assert!((p.point - 0.8).abs() < EPS, "point was {}", p.point);
        assert!((p.lower - 0.490_1).abs() < EPS, "lower was {}", p.lower);
        assert!((p.upper - 0.943_3).abs() < EPS, "upper was {}", p.upper);

        // Symmetric case: the interval must be centered on 0.5.
        let p = wilson_interval(50, 100).unwrap();
        assert!((p.lower - 0.403_8).abs() < EPS, "lower was {}", p.lower);
        assert!((p.upper - 0.596_2).abs() < EPS, "upper was {}", p.upper);
    }

    #[test]
    fn perfect_score_does_not_claim_certainty() {
        // The whole point of choosing Wilson. Ten straight passes is not proof
        // of mastery, and the interval must say so by staying wide and by not
        // pinning the lower bound at 1.0.
        let p = wilson_interval(10, 10).unwrap();
        assert_eq!(p.point, 1.0);
        assert!(p.upper <= 1.0);
        assert!(
            p.lower < 0.8,
            "10/10 should still admit real doubt, lower was {}",
            p.lower
        );

        // And more evidence must narrow it.
        let more = wilson_interval(200, 200).unwrap();
        assert!(
            more.lower > p.lower,
            "200/200 ({}) should be more confident than 10/10 ({})",
            more.lower,
            p.lower
        );
    }

    #[test]
    fn bounds_stay_within_zero_and_one() {
        // Includes the degenerate ends, where the normal approximation escapes
        // [0, 1] entirely.
        for (successes, trials) in [(0, 1), (1, 1), (0, 5), (5, 5), (0, 1000), (1000, 1000)] {
            let p = wilson_interval(successes, trials).unwrap();
            assert!(
                p.lower >= 0.0 && p.upper <= 1.0 && p.lower <= p.upper,
                "{successes}/{trials} produced [{}, {}]",
                p.lower,
                p.upper
            );
        }
    }

    #[test]
    fn no_trials_yields_no_proportion() {
        assert!(wilson_interval(0, 0).is_none());
    }
}

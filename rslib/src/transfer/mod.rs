// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
//
// Speedrun addition: transfer-of-learning measurement.
//
// This module answers three questions separately, and refuses to answer any of
// them when the evidence is thin:
//
//   memory      (DOK 1)   -- can the learner recall material as it was trained?
//   performance (DOK 2/3) -- can they use it on an item they have not seen?
//   readiness   (DOK 4)   -- what would they score on the real exam?
//
// The separation is the product. A tool that reports only the first and calls it
// readiness is the thing this exists to replace.
//
// WHY THIS IS IN RUST, NOT PYTHON
//
// The iOS client reaches Anki solely through a C FFI into rslib and dispatches
// by protobuf service/method index. Anything implemented in pylib is structurally
// unreachable from the phone, so a scoring model written in Python would have to
// be reimplemented in Swift -- two implementations of one statistical model,
// drifting apart, showing two different numbers for one collection. Placing it
// here means desktop and phone execute the same compiled code by construction.
//
// Secondarily: scoring scans the full revlog, which on a 50k-card collection is
// millions of rows, against a sub-second budget. That is a scan-and-reduce that
// belongs next to SQLite rather than across a serialization boundary. This is the
// weaker of the two arguments and is not the reason the code lives here.

pub mod service;
pub mod wilson;

use std::collections::HashMap;
use std::collections::HashSet;
use std::sync::Arc;

use wilson::wilson_interval;

/// Marks a card as a transfer probe -- a reworded or applied variant testing
/// whether the underlying knowledge survives a change of surface form.
/// Untagged cards are treated as plain recall items.
pub const PROBE_TAG: &str = "speedrun::probe";

/// Prefix for exam topic attribution, e.g. `speedrun::topic::biochem`.
pub const TOPIC_PREFIX: &str = "speedrun::topic::";

/// Tags are used rather than a new column on purpose: they already sync, they
/// already survive import/export, and they require no schema migration -- which
/// keeps the "zero corrupted collections" guarantee cheap to honour.
pub fn parse_tags(raw: &str) -> (Vec<String>, bool) {
    let mut topics = Vec::new();
    let mut is_probe = false;
    for tag in raw.split_whitespace() {
        if tag.eq_ignore_ascii_case(PROBE_TAG) {
            is_probe = true;
        } else if let Some(topic) = tag
            .to_ascii_lowercase()
            .strip_prefix(TOPIC_PREFIX)
            .map(str::to_string)
        {
            if !topic.is_empty() {
                topics.push(topic);
            }
        }
    }
    (topics, is_probe)
}

/// One graded review, already attributed to its topics.
///
/// `topics` is a shared slice rather than a `Vec<String>` on purpose. A large
/// collection produces hundreds of thousands of reviews but only a handful of
/// distinct tag strings -- 20 across a 50,000-card benchmark. Owning the topic
/// strings per review meant allocating a `Vec` and its `String`s once per row,
/// which cost roughly three quarters of the total scoring time. Sharing one
/// parsed result per distinct tag string makes cloning a refcount bump.
#[derive(Debug, Clone)]
pub struct GradedReview {
    pub card_id: i64,
    pub topics: Arc<[Arc<str>]>,
    pub is_probe: bool,
    pub passed: bool,
}

/// Build a shared topic list. Used by the DB layer's parse cache and by tests.
pub fn topic_list<S: AsRef<str>>(topics: &[S]) -> Arc<[Arc<str>]> {
    topics.iter().map(|t| Arc::from(t.as_ref())).collect()
}

/// The give-up rule, as engine behaviour rather than display logic.
///
/// Below these counts the engine returns a refusal, not a number with a wide
/// interval. A confident-looking score computed from four reviews is precisely
/// the dishonesty this product rejects, and a caller that never sees a number
/// cannot accidentally render one.
#[derive(Debug, Clone, Copy)]
pub struct Thresholds {
    pub min_reviews: u32,
    pub min_cards: u32,
}

impl Default for Thresholds {
    fn default() -> Self {
        Self {
            min_reviews: 20,
            min_cards: 5,
        }
    }
}

/// A scored proportion, or an explicit refusal to score.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Score {
    pub point: f64,
    pub lower: f64,
    pub upper: f64,
    pub observations: u32,
    pub cards: u32,
    pub sufficient: bool,
    pub needed_observations: u32,
    pub needed_cards: u32,
}

impl Score {
    fn insufficient(observations: u32, cards: u32, t: Thresholds) -> Self {
        Self {
            point: 0.0,
            lower: 0.0,
            upper: 0.0,
            observations,
            cards,
            sufficient: false,
            needed_observations: t.min_reviews,
            needed_cards: t.min_cards,
        }
    }
}

#[derive(Debug, Clone)]
pub struct TopicScore {
    pub topic: String,
    pub memory: Score,
    pub performance: Score,
    pub gap: f64,
    pub gap_valid: bool,
}

#[derive(Debug, Clone)]
pub struct TransferReport {
    pub topics: Vec<TopicScore>,
    pub readiness: Score,
}

/// Score a slice of reviews. Pure -- no database, no clock.
fn score_reviews<'a>(reviews: impl Iterator<Item = &'a GradedReview>, t: Thresholds) -> Score {
    let mut passed = 0u32;
    let mut total = 0u32;
    let mut cards = HashSet::new();
    for r in reviews {
        total += 1;
        if r.passed {
            passed += 1;
        }
        cards.insert(r.card_id);
    }
    let card_count = cards.len() as u32;

    if total < t.min_reviews || card_count < t.min_cards {
        return Score::insufficient(total, card_count, t);
    }
    // Unreachable for total == 0 given min_reviews >= 1, but a caller may pass
    // min_reviews: 0; refuse rather than divide by zero.
    let Some(p) = wilson_interval(passed, total) else {
        return Score::insufficient(total, card_count, t);
    };
    Score {
        point: p.point,
        lower: p.lower,
        upper: p.upper,
        observations: total,
        cards: card_count,
        sufficient: true,
        needed_observations: t.min_reviews,
        needed_cards: t.min_cards,
    }
}

/// Build the full report from attributed reviews.
///
/// Reviews carrying no topic tag are ignored: they cannot be attributed to exam
/// content, and silently folding them into a total would inflate the evidence
/// count behind a score without adding evidence about any topic.
pub fn build_report(reviews: &[GradedReview], t: Thresholds) -> TransferReport {
    let mut by_topic: HashMap<&str, Vec<&GradedReview>> = HashMap::new();
    for r in reviews {
        for topic in r.topics.iter() {
            by_topic.entry(topic.as_ref()).or_default().push(r);
        }
    }

    let mut topics: Vec<TopicScore> = by_topic
        .into_iter()
        .map(|(topic, rs)| {
            let memory = score_reviews(rs.iter().copied().filter(|r| !r.is_probe), t);
            let performance = score_reviews(rs.iter().copied().filter(|r| r.is_probe), t);
            let gap_valid = memory.sufficient && performance.sufficient;
            TopicScore {
                topic: topic.to_string(),
                gap: if gap_valid {
                    memory.point - performance.point
                } else {
                    0.0
                },
                gap_valid,
                memory,
                performance,
            }
        })
        .collect();
    topics.sort_by(|a, b| a.topic.cmp(&b.topic));

    // Readiness pools probe reviews across every attributed topic.
    //
    // Honest limitation: this is not yet weighted by the official exam outline's
    // topic distribution, so it projects performance on the mix the learner
    // happens to have studied, not the mix the exam will ask. Blueprint
    // weighting is deliberately deferred rather than faked.
    let readiness = score_reviews(
        reviews.iter().filter(|r| r.is_probe && !r.topics.is_empty()),
        t,
    );

    TransferReport { topics, readiness }
}

#[cfg(test)]
mod test {
    use super::*;

    fn review(card_id: i64, topic: &str, is_probe: bool, passed: bool) -> GradedReview {
        GradedReview {
            card_id,
            topics: topic_list(&[topic]),
            is_probe,
            passed,
        }
    }

    /// n reviews across n distinct cards, `passes` of which passed.
    fn many(start_id: i64, topic: &str, is_probe: bool, passes: u32, total: u32) -> Vec<GradedReview> {
        (0..total)
            .map(|i| review(start_id + i as i64, topic, is_probe, i < passes))
            .collect()
    }

    #[test]
    fn parses_probe_and_topic_tags() {
        let (topics, is_probe) = parse_tags("  speedrun::topic::biochem marked speedrun::probe ");
        assert_eq!(topics, vec!["biochem"]);
        assert!(is_probe);

        // Plain recall card with two topics.
        let (topics, is_probe) =
            parse_tags("speedrun::topic::biochem speedrun::topic::amino_acids");
        assert_eq!(topics, vec!["biochem", "amino_acids"]);
        assert!(!is_probe);

        // Unrelated tags must not be mistaken for topics.
        let (topics, is_probe) = parse_tags("leech marked");
        assert!(topics.is_empty());
        assert!(!is_probe);
    }

    #[test]
    fn give_up_rule_refuses_to_score_thin_evidence() {
        let t = Thresholds {
            min_reviews: 20,
            min_cards: 5,
        };

        // Plenty of reviews, but all on one card -- no breadth.
        let narrow: Vec<_> = (0..30).map(|_| review(1, "biochem", false, true)).collect();
        let report = build_report(&narrow, t);
        let topic = &report.topics[0];
        assert!(
            !topic.memory.sufficient,
            "30 reviews of a single card must not produce a score"
        );
        assert_eq!(topic.memory.cards, 1);
        assert_eq!(topic.memory.needed_cards, 5);
        // A refusal must not leak a number a caller could render.
        assert_eq!(topic.memory.point, 0.0);

        // Enough breadth, not enough reviews.
        let shallow = many(1, "biochem", false, 5, 6);
        let report = build_report(&shallow, t);
        assert!(!report.topics[0].memory.sufficient);
        assert_eq!(report.topics[0].memory.observations, 6);

        // Both bars cleared.
        let ample = many(1, "biochem", false, 18, 20);
        let report = build_report(&ample, t);
        assert!(report.topics[0].memory.sufficient);
        assert!((report.topics[0].memory.point - 0.9).abs() < 1e-9);
    }

    #[test]
    fn memory_and_performance_are_measured_separately() {
        let t = Thresholds::default();
        // The signature failure this product exists to expose: near-perfect
        // recall of trained material, much weaker performance on reworded items.
        let mut reviews = many(1, "biochem", false, 24, 25); // memory 96%
        reviews.extend(many(100, "biochem", true, 12, 25)); // performance 48%

        let report = build_report(&reviews, t);
        assert_eq!(report.topics.len(), 1, "both sets are one topic");
        let topic = &report.topics[0];

        assert!(topic.memory.sufficient && topic.performance.sufficient);
        assert!((topic.memory.point - 0.96).abs() < 1e-9);
        assert!((topic.performance.point - 0.48).abs() < 1e-9);

        // The gap is the headline number.
        assert!(topic.gap_valid);
        assert!((topic.gap - 0.48).abs() < 1e-9);

        // Probe reviews must not contaminate the memory score, and vice versa.
        assert_eq!(topic.memory.observations, 25);
        assert_eq!(topic.performance.observations, 25);
    }

    #[test]
    fn gap_is_invalid_when_either_side_was_refused() {
        let t = Thresholds::default();
        // Strong memory evidence, almost no probes.
        let mut reviews = many(1, "biochem", false, 24, 25);
        reviews.extend(many(100, "biochem", true, 2, 2));

        let report = build_report(&reviews, t);
        let topic = &report.topics[0];
        assert!(topic.memory.sufficient);
        assert!(!topic.performance.sufficient);
        assert!(
            !topic.gap_valid,
            "a gap measured against a refused score is not a gap"
        );
        assert_eq!(topic.gap, 0.0);
    }

    #[test]
    fn untagged_reviews_do_not_inflate_readiness() {
        let t = Thresholds::default();
        let mut reviews = many(1, "biochem", true, 15, 25);
        // 40 probe reviews with no topic attribution at all.
        reviews.extend((0..40).map(|i| GradedReview {
            card_id: 500 + i,
            topics: topic_list::<&str>(&[]),
            is_probe: true,
            passed: true,
        }));

        let report = build_report(&reviews, t);
        assert_eq!(
            report.readiness.observations, 25,
            "unattributed reviews must not count toward exam readiness"
        );
        assert_eq!(report.topics.len(), 1);
    }

    #[test]
    fn a_card_in_two_topics_counts_toward_both() {
        let t = Thresholds {
            min_reviews: 2,
            min_cards: 1,
        };
        let reviews = vec![
            GradedReview {
                card_id: 1,
                topics: topic_list(&["biochem", "amino_acids"]),
                is_probe: false,
                passed: true,
            },
            GradedReview {
                card_id: 2,
                topics: topic_list(&["biochem", "amino_acids"]),
                is_probe: false,
                passed: false,
            },
        ];
        let report = build_report(&reviews, t);
        assert_eq!(report.topics.len(), 2);
        // Sorted alphabetically.
        assert_eq!(report.topics[0].topic, "amino_acids");
        assert_eq!(report.topics[1].topic, "biochem");
        for topic in &report.topics {
            assert_eq!(topic.memory.observations, 2);
            assert!((topic.memory.point - 0.5).abs() < 1e-9);
        }
    }
}

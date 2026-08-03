// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
//
// Speedrun addition.

use std::collections::HashMap;
use std::sync::Arc;

use crate::prelude::*;
use crate::transfer::build_report;
use crate::transfer::outline;
use crate::transfer::parse_tags;
use crate::transfer::scale;
use crate::transfer::topic_list;
use crate::transfer::GradedReview;
use crate::transfer::Score;
use crate::transfer::Thresholds;

/// Reviews with `ease = 0` carry no rating (manual reschedules and similar), and
/// review kinds 4/5 are Manual/Rescheduled -- neither is evidence the learner
/// answered anything, so both are excluded before any counting happens.
const GRADED_REVIEWS_SQL: &str = "
SELECT r.cid, r.ease, n.tags
FROM revlog r
JOIN cards c ON c.id = r.cid
JOIN notes n ON n.id = c.nid
WHERE r.id >= ?1
  AND r.ease > 0
  AND r.type NOT IN (4, 5)
";

impl Collection {
    /// Load every graded review, attributed to topics via note tags.
    ///
    /// Single scan with the joins pushed into SQLite. Tag parsing is memoised by
    /// the raw tag string, which is the difference between a report that meets
    /// its latency budget and one that does not: a 50,000-card collection
    /// produces ~400,000 review rows but only ~20 distinct tag strings, so
    /// parsing per row re-derived the same handful of answers twenty thousand
    /// times over. Measured at ~740ms of the ~950ms total before this cache.
    ///
    /// The tag column is read as a borrowed `&str` rather than an owned
    /// `String` for the same reason -- on a cache hit nothing is allocated at
    /// all.
    fn graded_reviews(&mut self, since_millis: i64) -> Result<Vec<GradedReview>> {
        let mut cache: HashMap<Box<str>, (Arc<[Arc<str>]>, bool)> = HashMap::new();

        self.storage
            .db
            .prepare_cached(GRADED_REVIEWS_SQL)?
            .query_and_then([since_millis], |row| -> Result<GradedReview> {
                let card_id: i64 = row.get(0)?;
                let ease: i64 = row.get(1)?;
                let raw_tags: &str = row.get_ref(2)?.as_str()?;

                let (topics, is_probe) = match cache.get(raw_tags) {
                    Some(hit) => hit.clone(),
                    None => {
                        let (parsed, is_probe) = parse_tags(raw_tags);
                        let entry = (topic_list(&parsed), is_probe);
                        cache.insert(raw_tags.into(), entry.clone());
                        entry
                    }
                };

                Ok(GradedReview {
                    card_id,
                    topics,
                    is_probe,
                    // Again (1) is the only failing rating; Hard/Good/Easy pass.
                    passed: ease > 1,
                })
            })?
            .collect()
    }

    /// Epoch millis of the most recent graded review, or 0 if there are none.
    ///
    /// Surfaced alongside the projection because a readiness number computed
    /// from reviews three weeks old is a different claim from one computed
    /// today, and the learner cannot tell the difference without being told.
    fn last_graded_review_millis(&mut self, since_millis: i64) -> Result<i64> {
        let stamp: Option<i64> = self
            .storage
            .db
            .prepare_cached(
                "SELECT max(r.id) FROM revlog r
                 WHERE r.id >= ?1 AND r.ease > 0 AND r.type NOT IN (4, 5)",
            )?
            .query_row([since_millis], |row| row.get(0))?;
        Ok(stamp.unwrap_or(0))
    }
}

impl crate::services::TransferService for Collection {
    fn compute_transfer_scores(
        &mut self,
        input: anki_proto::transfer::ComputeTransferScoresRequest,
    ) -> Result<anki_proto::transfer::TransferScores> {
        let defaults = Thresholds::default();
        let thresholds = Thresholds {
            // A caller passing 0 gets the safe default rather than a disabled
            // give-up rule. Turning the honesty guarantee off must be explicit,
            // and there is currently no way to express it.
            min_reviews: if input.min_reviews == 0 {
                defaults.min_reviews
            } else {
                input.min_reviews
            },
            min_cards: if input.min_cards == 0 {
                defaults.min_cards
            } else {
                input.min_cards
            },
        };

        let reviews = self.graded_reviews(input.since_millis)?;
        let report = build_report(&reviews, thresholds);

        // Coverage is computed against the official outline, not against the
        // learner's tags, so untouched topics are visible rather than absent.
        let mut counts: HashMap<String, u32> = HashMap::new();
        for r in &reviews {
            for topic in r.topics.iter() {
                *counts.entry(topic.to_string()).or_default() += 1;
            }
        }
        let coverage = outline::build_coverage(&counts);

        // Most recent review counted, so the learner can see how stale this is.
        let last_updated_millis = self.last_graded_review_millis(input.since_millis)?;

        let projection = scale::project(
            report.readiness,
            coverage.fraction,
            coverage.covered_count,
            coverage.total_count,
        );

        Ok(anki_proto::transfer::TransferScores {
            topics: report
                .topics
                .into_iter()
                .map(|t| anki_proto::transfer::TopicScores {
                    topic: t.topic,
                    memory: Some(score_to_proto(t.memory)),
                    performance: Some(score_to_proto(t.performance)),
                    gap: t.gap,
                    gap_valid: t.gap_valid,
                })
                .collect(),
            readiness: Some(score_to_proto(report.readiness)),
            projected: Some(anki_proto::transfer::ProjectedScore {
                point: projection.point,
                lower: projection.lower,
                upper: projection.upper,
                sufficient: projection.sufficient,
                confidence: projection.confidence,
                reasons: projection.reasons,
                last_updated_millis,
                give_up_rule: projection.give_up_rule,
            }),
            coverage: Some(anki_proto::transfer::Coverage {
                entries: coverage
                    .entries
                    .into_iter()
                    .map(|e| anki_proto::transfer::CoverageEntry {
                        code: e.code.to_string(),
                        title: e.title.to_string(),
                        section: e.section.to_string(),
                        covered: e.covered,
                        observations: e.observations,
                    })
                    .collect(),
                covered_count: coverage.covered_count,
                total_count: coverage.total_count,
                fraction: coverage.fraction,
            }),
        })
    }
}

fn score_to_proto(score: Score) -> anki_proto::transfer::ScoreInterval {
    anki_proto::transfer::ScoreInterval {
        point: score.point,
        lower: score.lower,
        upper: score.upper,
        observations: score.observations,
        cards: score.cards,
        sufficient: score.sufficient,
        needed_observations: score.needed_observations,
        needed_cards: score.needed_cards,
    }
}

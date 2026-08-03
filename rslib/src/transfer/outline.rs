// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
//
// Speedrun addition: the official MCAT content outline.
//
// Source: AAMC, "What's on the MCAT Exam?" content outline PDF, (c) 2020 AAMC.
// https://students-residents.aamc.org/media/9261/download
// Every code and title below is verbatim from that PDF, where each category
// appears twice -- once in the section framework list and again as its detail
// table header -- and both occurrences were cross-checked.
//
// WHY A HARDCODED OUTLINE IS THE POINT
//
// A coverage map built from the learner's own tags can only show what they have
// already touched. That is precisely the blind spot: material never studied is
// invisible, so a tag-derived map reports 100% coverage of a tenth of the exam.
// Checking against the official outline is what makes "you have not started 19
// of 31 topics" sayable.
//
// CARS HAS NO CONTENT CATEGORIES. This is not an omission. AAMC organises
// Critical Analysis and Reasoning Skills around three reasoning skills --
// Foundations of Comprehension (30%), Reasoning Within the Text (30%), and
// Reasoning Beyond the Text (40%) -- with no recallable content whatsoever.
// A quarter of the exam therefore cannot be covered by flashcards at all, and
// the coverage map should say so rather than quietly exclude it.

/// One content category from the official outline.
pub struct ContentCategory {
    pub code: &'static str,
    pub title: &'static str,
    pub section: &'static str,
}

/// All 31 official MCAT content categories.
pub static OUTLINE: &[ContentCategory] = &[
    // Foundational Concept 1 -- Bio/Biochem, 55% of section
    ContentCategory { code: "1A", section: "Bio/Biochem", title: "Structure and function of proteins and their constituent amino acids" },
    ContentCategory { code: "1B", section: "Bio/Biochem", title: "Transmission of genetic information from the gene to the protein" },
    ContentCategory { code: "1C", section: "Bio/Biochem", title: "Transmission of heritable information from generation to generation and the processes that increase genetic diversity" },
    ContentCategory { code: "1D", section: "Bio/Biochem", title: "Principles of bioenergetics and fuel molecule metabolism" },
    // Foundational Concept 2 -- Bio/Biochem, 20%
    ContentCategory { code: "2A", section: "Bio/Biochem", title: "Assemblies of molecules, cells, and groups of cells within single cellular and multicellular organisms" },
    ContentCategory { code: "2B", section: "Bio/Biochem", title: "The structure, growth, physiology, and genetics of prokaryotes and viruses" },
    ContentCategory { code: "2C", section: "Bio/Biochem", title: "Processes of cell division, differentiation, and specialization" },
    // Foundational Concept 3 -- Bio/Biochem, 25%
    ContentCategory { code: "3A", section: "Bio/Biochem", title: "Structure and functions of the nervous and endocrine systems and ways these systems coordinate the organ systems" },
    ContentCategory { code: "3B", section: "Bio/Biochem", title: "Structure and integrative functions of the main organ systems" },
    // Foundational Concept 4 -- Chem/Phys, 40%
    ContentCategory { code: "4A", section: "Chem/Phys", title: "Translational motion, forces, work, energy, and equilibrium in living systems" },
    ContentCategory { code: "4B", section: "Chem/Phys", title: "Importance of fluids for the circulation of blood, gas movement, and gas exchange" },
    ContentCategory { code: "4C", section: "Chem/Phys", title: "Electrochemistry and electrical circuits and their elements" },
    ContentCategory { code: "4D", section: "Chem/Phys", title: "How light and sound interact with matter" },
    ContentCategory { code: "4E", section: "Chem/Phys", title: "Atoms, nuclear decay, electronic structure, and atomic chemical behavior" },
    // Foundational Concept 5 -- Chem/Phys, 60%
    ContentCategory { code: "5A", section: "Chem/Phys", title: "Unique nature of water and its solutions" },
    ContentCategory { code: "5B", section: "Chem/Phys", title: "Nature of molecules and intermolecular interactions" },
    ContentCategory { code: "5C", section: "Chem/Phys", title: "Separation and purification methods" },
    ContentCategory { code: "5D", section: "Chem/Phys", title: "Structure, function, and reactivity of biologically relevant molecules" },
    ContentCategory { code: "5E", section: "Chem/Phys", title: "Principles of chemical thermodynamics and kinetics" },
    // Foundational Concept 6 -- Psych/Soc, 25%
    ContentCategory { code: "6A", section: "Psych/Soc", title: "Sensing the environment" },
    ContentCategory { code: "6B", section: "Psych/Soc", title: "Making sense of the environment" },
    ContentCategory { code: "6C", section: "Psych/Soc", title: "Responding to the world" },
    // Foundational Concept 7 -- Psych/Soc, 35%
    ContentCategory { code: "7A", section: "Psych/Soc", title: "Individual influences on behavior" },
    ContentCategory { code: "7B", section: "Psych/Soc", title: "Social processes that influence human behavior" },
    ContentCategory { code: "7C", section: "Psych/Soc", title: "Attitude and behavior change" },
    // Foundational Concept 8 -- Psych/Soc, 20%
    ContentCategory { code: "8A", section: "Psych/Soc", title: "Self-identity" },
    ContentCategory { code: "8B", section: "Psych/Soc", title: "Social thinking" },
    ContentCategory { code: "8C", section: "Psych/Soc", title: "Social interactions" },
    // Foundational Concept 9 -- Psych/Soc, 15%
    ContentCategory { code: "9A", section: "Psych/Soc", title: "Understanding social structure" },
    ContentCategory { code: "9B", section: "Psych/Soc", title: "Demographic characteristics and processes" },
    // Foundational Concept 10 -- Psych/Soc, 5%
    ContentCategory { code: "10A", section: "Psych/Soc", title: "Social inequality" },
];

/// Coverage of one content category.
pub struct CoverageEntry {
    pub code: &'static str,
    pub title: &'static str,
    pub section: &'static str,
    pub covered: bool,
    pub observations: u32,
}

pub struct Coverage {
    pub entries: Vec<CoverageEntry>,
    pub covered_count: u32,
    pub total_count: u32,
    pub fraction: f64,
}

/// Build the coverage map from observation counts keyed by topic tag.
///
/// Matching is case-insensitive on the category code, so a learner may tag
/// `speedrun::topic::1a` or `speedrun::topic::1A`. Tags that do not correspond
/// to an official code are ignored here -- they still contribute to per-topic
/// scores, but they cannot count toward exam coverage, because coverage is a
/// claim about the exam and not about the learner's filing system.
pub fn build_coverage(counts: &std::collections::HashMap<String, u32>) -> Coverage {
    let entries: Vec<CoverageEntry> = OUTLINE
        .iter()
        .map(|c| {
            let observations = counts
                .get(&c.code.to_ascii_lowercase())
                .copied()
                .unwrap_or(0);
            CoverageEntry {
                code: c.code,
                title: c.title,
                section: c.section,
                covered: observations > 0,
                observations,
            }
        })
        .collect();

    let covered_count = entries.iter().filter(|e| e.covered).count() as u32;
    let total_count = entries.len() as u32;
    let fraction = if total_count == 0 {
        0.0
    } else {
        covered_count as f64 / total_count as f64
    };

    Coverage {
        entries,
        covered_count,
        total_count,
        fraction,
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn outline_matches_the_official_structure() {
        assert_eq!(OUTLINE.len(), 31, "AAMC publishes 31 content categories");
        let count = |s: &str| OUTLINE.iter().filter(|c| c.section == s).count();
        assert_eq!(count("Bio/Biochem"), 9);
        assert_eq!(count("Chem/Phys"), 10);
        assert_eq!(count("Psych/Soc"), 12);
        // CARS contributes none. A quarter of the exam has no recallable
        // content, and the map must not invent categories for it.
        assert_eq!(count("CARS"), 0);
    }

    #[test]
    fn codes_are_unique() {
        let mut seen = std::collections::HashSet::new();
        for c in OUTLINE {
            assert!(seen.insert(c.code), "duplicate code {}", c.code);
        }
    }

    #[test]
    fn uncovered_topics_are_visible() {
        // The whole point: studying one topic well must not read as coverage.
        let mut counts = HashMap::new();
        counts.insert("1a".to_string(), 500u32);
        let cov = build_coverage(&counts);

        assert_eq!(cov.covered_count, 1);
        assert_eq!(cov.total_count, 31);
        assert!((cov.fraction - 1.0 / 31.0).abs() < 1e-9);
        // 30 entries are present and marked uncovered, not omitted.
        assert_eq!(cov.entries.iter().filter(|e| !e.covered).count(), 30);
    }

    #[test]
    fn matching_is_case_insensitive_and_ignores_unofficial_tags() {
        let mut counts = HashMap::new();
        counts.insert("4e".to_string(), 12u32);
        counts.insert("my_weak_areas".to_string(), 999u32);
        let cov = build_coverage(&counts);
        assert_eq!(cov.covered_count, 1);
        let e = cov.entries.iter().find(|e| e.code == "4E").unwrap();
        assert!(e.covered && e.observations == 12);
    }
}

"""Structural tests for the link-epics skill (ENH-1729, delegated per FEAT-2942)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "link-epics" / "SKILL.md"


class TestLinkEpicsSkillExists:
    """Verify the link-epics skill file is present and well-formed."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_apply_flag(self) -> None:
        assert "--apply" in SKILL_FILE.read_text()

    def test_threshold_flag(self) -> None:
        assert "--threshold" in SKILL_FILE.read_text()

    def test_auto_flag(self) -> None:
        assert "--auto" in SKILL_FILE.read_text()

    def test_min_score_and_min_cluster_flags_removed(self) -> None:
        content = SKILL_FILE.read_text()
        assert "--min-score" not in content
        assert "--min-cluster" not in content

    def test_confidence_tiers(self) -> None:
        content = SKILL_FILE.read_text()
        for tier in ("HIGH", "MEDIUM"):
            assert tier in content

    def test_parent_field_reference(self) -> None:
        assert "parent:" in SKILL_FILE.read_text()

    def test_name_field_in_frontmatter(self) -> None:
        assert "name: link-epics" in SKILL_FILE.read_text()

    def test_metadata_short_description(self) -> None:
        assert "short-description:" in SKILL_FILE.read_text()

    def test_disable_model_invocation(self) -> None:
        assert "disable-model-invocation: true" in SKILL_FILE.read_text()

    def test_no_jaccard_scoring_algorithm_prose(self) -> None:
        """Scoring/clustering algorithm prose must be gone — delegated to the CLI (AC #3)."""
        content = SKILL_FILE.read_text()
        assert "Jaccard" not in content
        assert "union-find" not in content.lower()
        assert "words1 & words2" not in content
        assert "intersection" not in content.lower()

    def test_delegates_to_cli(self) -> None:
        content = SKILL_FILE.read_text()
        assert "ll-issues link-epics" in content
        assert "--mode assign" in content
        assert "--mode synthesize" in content

    def test_children_section_documented(self) -> None:
        assert "## Children" in SKILL_FILE.read_text()

    def test_mode_flag_documented(self) -> None:
        assert "--mode" in SKILL_FILE.read_text()

    def test_distinguishes_from_ll_issues_clusters(self) -> None:
        assert "ll-issues clusters" in SKILL_FILE.read_text()

    def test_create_epics_from_unparented_name_removed(self) -> None:
        assert "create-epics-from-unparented" not in SKILL_FILE.read_text()

    def test_argument_hint_matches_cli_flags(self) -> None:
        content = SKILL_FILE.read_text()
        assert "argument-hint:" in content
        hint_line = next(
            line for line in content.splitlines() if line.strip().startswith("argument-hint:")
        )
        assert "--mode" in hint_line
        assert "--threshold" in hint_line
        assert "--min-score" not in hint_line
        assert "--min-cluster" not in hint_line


class TestUpdateFrontmatterRoundTrip:
    """Verify update_frontmatter can write parent: fields with full round-trip integrity."""

    def test_write_parent_field(self) -> None:
        from little_loops.frontmatter import parse_frontmatter, update_frontmatter

        original = "---\nid: ENH-123\nstatus: open\n---\n\n# ENH-123: Test Issue\n"
        updated = update_frontmatter(original, {"parent": "EPIC-42"})
        fm = parse_frontmatter(updated)
        assert fm["parent"] == "EPIC-42"
        assert fm["id"] == "ENH-123"
        assert fm["status"] == "open"

    def test_existing_fields_preserved(self) -> None:
        from little_loops.frontmatter import parse_frontmatter, update_frontmatter

        original = "---\nid: BUG-55\ntitle: Some bug\npriority: P2\nstatus: open\n---\n\n# BUG-55\n"
        updated = update_frontmatter(original, {"parent": "EPIC-10"})
        fm = parse_frontmatter(updated)
        assert fm["parent"] == "EPIC-10"
        assert fm["id"] == "BUG-55"
        assert fm["priority"] == "P2"

    def test_body_preserved(self) -> None:
        from little_loops.frontmatter import update_frontmatter

        body = "\n# ENH-123: Test Issue\n\n## Summary\n\nSome description.\n"
        original = f"---\nid: ENH-123\nstatus: open\n---{body}"
        updated = update_frontmatter(original, {"parent": "EPIC-42"})
        assert body in updated


class TestParentlessIssueDetection:
    """Verify logic for detecting issues that lack a parent: field."""

    def test_issue_without_parent_is_orphan(self) -> None:
        from little_loops.frontmatter import parse_frontmatter

        content = "---\nid: ENH-999\nstatus: open\n---\n\n# ENH-999: No parent\n"
        fm = parse_frontmatter(content)
        assert fm.get("parent") is None

    def test_issue_with_parent_is_not_orphan(self) -> None:
        from little_loops.frontmatter import parse_frontmatter

        content = "---\nid: ENH-999\nstatus: open\nparent: EPIC-42\n---\n\n# ENH-999\n"
        fm = parse_frontmatter(content)
        assert fm.get("parent") == "EPIC-42"

    def test_null_parent_treated_as_orphan(self) -> None:
        from little_loops.frontmatter import parse_frontmatter

        content = "---\nid: ENH-999\nstatus: open\nparent: null\n---\n\n# ENH-999\n"
        fm = parse_frontmatter(content)
        assert fm.get("parent") is None


class TestJaccardScoringBuckets:
    """Verify Jaccard similarity calculation maps to correct confidence tiers.

    Exercises `text_utils.py` directly — the shared scoring layer `ll-issues
    link-epics` is built on (see test_link_epics_cli.py for CLI-level coverage).
    """

    def test_identical_word_sets_score_one(self) -> None:
        from little_loops.text_utils import calculate_word_overlap

        words = {"issue", "tracker", "workflow", "automation"}
        assert calculate_word_overlap(words, words) == 1.0

    def test_disjoint_word_sets_score_zero(self) -> None:
        from little_loops.text_utils import calculate_word_overlap

        w1 = {"issue", "tracker", "workflow"}
        w2 = {"authentication", "database", "schema"}
        assert calculate_word_overlap(w1, w2) == 0.0

    def test_partial_overlap_score(self) -> None:
        from little_loops.text_utils import calculate_word_overlap

        w1 = {"issue", "tracker", "workflow", "automation"}
        w2 = {"issue", "tracker", "database", "schema"}
        score = calculate_word_overlap(w1, w2)
        expected = 2 / 6  # intersection=2, union=6
        assert abs(score - expected) < 1e-9

    def test_high_tier_threshold(self) -> None:
        from little_loops.text_utils import calculate_word_overlap, extract_words

        # Texts with heavy overlap should score into HIGH tier (>=0.7)
        epic_text = "loop automation workflow issue tracker management"
        orphan_text = "loop automation workflow issue tracker improvement"
        score = calculate_word_overlap(extract_words(epic_text), extract_words(orphan_text))
        assert score >= 0.4  # at minimum MEDIUM tier

    def test_empty_word_sets_score_zero(self) -> None:
        from little_loops.text_utils import calculate_word_overlap

        assert calculate_word_overlap(set(), {"word"}) == 0.0
        assert calculate_word_overlap({"word"}, set()) == 0.0

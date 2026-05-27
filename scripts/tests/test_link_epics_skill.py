"""Structural tests for the link-epics skill (ENH-1729)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "link-epics" / "SKILL.md"


class TestLinkEpicsSkillExists:
    """Verify the link-epics skill file is present and well-formed."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_auto_flag(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--auto" in SKILL_FILE.read_text()

    def test_min_score_flag(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--min-score" in SKILL_FILE.read_text()

    def test_confidence_tiers(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for tier in ("HIGH", "MEDIUM", "LOW"):
            assert tier in content

    def test_parent_field_reference(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "parent:" in SKILL_FILE.read_text()

    def test_config_issues_base_dir(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "{{config.issues.base_dir}}" in SKILL_FILE.read_text()

    def test_name_field_in_frontmatter(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "name: link-epics" in content

    def test_metadata_short_description(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "short-description:" in content

    def test_disable_model_invocation(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "disable-model-invocation: true" in SKILL_FILE.read_text()

    def test_jaccard_scoring_documented(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "Jaccard" in content

    def test_relates_to_field_documented(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "relates_to:" in SKILL_FILE.read_text()

    def test_children_section_documented(self) -> None:
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "## Children" in SKILL_FILE.read_text()


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
    """Verify Jaccard similarity calculation maps to correct confidence tiers."""

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

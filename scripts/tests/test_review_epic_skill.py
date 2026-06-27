"""Structural tests for the review-epic skill (BUG-2333)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "review-epic" / "SKILL.md"


class TestReviewEpicSkillExists:
    """Verify the review-epic skill file exists and has correct structure."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "skills/review-epic/SKILL.md must exist"

    def test_parent_only_child_resolution(self) -> None:
        content = SKILL_FILE.read_text()
        assert "issue.parent == EPIC_ID" in content, (
            "Child resolution must use parent: backrefs only (BUG-2333 fix)"
        )

    def test_no_forward_ids_union(self) -> None:
        content = SKILL_FILE.read_text()
        assert "forward_ids" not in content, (
            "forward_ids union with relates_to must be removed (BUG-2333 fix)"
        )
        assert "forward_ids ∪ backward_ids" not in content, (
            "Union of forward_ids and backward_ids must be removed (BUG-2333 fix)"
        )

    def test_parity_comment_references_issue_progress(self) -> None:
        content = SKILL_FILE.read_text()
        assert "issue_progress.py" in content, (
            "Child resolution block must cite issue_progress.py as the reference implementation"
        )

    def test_related_not_children_section_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "Related (not children)" in content, (
            "Step 8 report must include a 'Related (not children)' section (BUG-2333)"
        )

    def test_related_not_children_variable_defined(self) -> None:
        content = SKILL_FILE.read_text()
        assert "related_not_children" in content, (
            "Step 2c must define related_not_children for relates_to entries that are not children"
        )

    def test_relates_to_not_in_child_ids(self) -> None:
        content = SKILL_FILE.read_text()
        assert "not in child_ids" in content, (
            "related_not_children must exclude entries that are also children"
        )

    def test_epic_progress_command_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "ll-issues epic-progress" in content, (
            "Skill must call ll-issues epic-progress for aggregate counts"
        )

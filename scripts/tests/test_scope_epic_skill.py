"""Structural tests for the scope-epic skill (FEAT-1857)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "scope-epic" / "SKILL.md"


class TestScopeEpicSkillExists:
    """Verify the scope-epic skill file exists and has correct structure."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_FILE.exists(), "skills/scope-epic/SKILL.md must exist (FEAT-1857)"

    def test_edit_in_allowed_tools(self) -> None:
        content = SKILL_FILE.read_text()
        frontmatter_end = content.index("---", 3)
        frontmatter = content[:frontmatter_end]
        assert "Edit" in frontmatter, (
            "Edit must be listed in allowed-tools for in-place EPIC wiring"
        )

    def test_write_in_allowed_tools(self) -> None:
        content = SKILL_FILE.read_text()
        frontmatter_end = content.index("---", 3)
        frontmatter = content[:frontmatter_end]
        assert "Write" in frontmatter, (
            "Write must be listed in allowed-tools for creating issue files"
        )

    def test_ask_user_question_in_allowed_tools(self) -> None:
        content = SKILL_FILE.read_text()
        frontmatter_end = content.index("---", 3)
        frontmatter = content[:frontmatter_end]
        assert "AskUserQuestion" in frontmatter, (
            "AskUserQuestion must be listed in allowed-tools for interactive review"
        )

    def test_interactive_review_phase_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "interactive" in content.lower() or "review" in content.lower(), (
            "Skill must include an interactive review phase"
        )

    def test_epic_write_phase_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "EPIC" in content, "Skill must reference EPIC file creation"

    def test_child_write_phase_exists(self) -> None:
        content = SKILL_FILE.read_text()
        assert "child" in content.lower(), "Skill must reference child issue creation"

    def test_relates_to_wiring_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "relates_to" in content, "Skill must reference relates_to frontmatter wiring"

    def test_children_section_wiring_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "## Children" in content or "Children" in content, (
            "Skill must reference ## Children section wiring"
        )

    def test_ll_issues_next_id_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "ll-issues next-id" in content or "next-id" in content, (
            "Skill must reference ll-issues next-id for ID allocation"
        )

    def test_parent_frontmatter_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "parent:" in content, (
            "Skill must reference parent: frontmatter field for child→EPIC wiring"
        )

    def test_git_staging_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "git add" in content, "Skill must reference git add for staging created files"

    def test_from_doc_flag_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "--from-doc" in content, (
            "Skill must support --from-doc flag for loading theme from a file"
        )

    def test_priority_flag_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "--priority" in content, (
            "Skill must support --priority flag to override default EPIC priority"
        )

    def test_min_children_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "min_children" in content, (
            "Skill must reference min_children config for below-threshold warning"
        )

    def test_max_children_referenced(self) -> None:
        content = SKILL_FILE.read_text()
        assert "max_children" in content, (
            "Skill must reference max_children config for above-threshold suggestion"
        )

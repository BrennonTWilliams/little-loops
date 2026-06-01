"""Structural wiring tests for ENH-1859: /ll:review-sprint EPIC awareness."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "review-sprint.md"
SPRINT_GUIDE = PROJECT_ROOT / "docs" / "guides" / "SPRINT_GUIDE.md"
COMMANDS_REF = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"
CLI_REF = PROJECT_ROOT / "docs" / "reference" / "CLI.md"


class TestReviewSprintEpicAwareness:
    """Verify ENH-1859 EPIC-awareness wiring in commands/review-sprint.md."""

    def test_command_file_exists(self) -> None:
        assert COMMAND_FILE.exists(), "commands/review-sprint.md not found"

    def test_phase_3f_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "3f: EPIC Context" in content, (
            "Phase 3f: EPIC Context must be present in review-sprint.md"
        )

    def test_ll_sprint_show_epic_call_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "ll-sprint show EPIC-" in content, (
            "Phase 3f must call 'll-sprint show EPIC-NNN' to resolve EPIC children"
        )

    def test_ll_deps_tree_call_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "ll-deps tree" in content, (
            "Phase 3f must call 'll-deps tree EPIC-NNN --json' for structured edge data"
        )

    def test_epic_context_output_block_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "## EPIC context" in content or "### EPIC Context" in content or "EPIC Context" in content, (
            "review-sprint.md must include an EPIC Context output block"
        )

    def test_ll_sprint_edit_add_fix_command_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "ll-sprint edit" in content and "--add" in content, (
            "review-sprint.md must include a 'll-sprint edit --add' fix command for blocker gaps"
        )

    def test_ll_issues_in_allowed_tools(self) -> None:
        content = COMMAND_FILE.read_text()
        frontmatter_end = content.index("---", 3)
        frontmatter = content[:frontmatter_end]
        assert "Bash(ll-issues:*)" in frontmatter, (
            "ll-issues must be listed in allowed-tools (Phase 3f calls ll-issues epic-progress)"
        )

    def test_ll_deps_in_allowed_tools(self) -> None:
        content = COMMAND_FILE.read_text()
        frontmatter_end = content.index("---", 3)
        frontmatter = content[:frontmatter_end]
        assert "Bash(ll-deps:*)" in frontmatter, (
            "ll-deps must be listed in allowed-tools (Phase 3f calls ll-deps tree)"
        )

    def test_phase_5d_epic_blocker_gap_approval_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "5d" in content and ("EPIC" in content or "blocker" in content.lower()), (
            "Phase 5d interactive approval for EPIC blocker gaps must be present"
        )


class TestSprintGuideEpicAwareness:
    """Verify docs/guides/SPRINT_GUIDE.md mentions EPIC awareness in the review section."""

    def test_sprint_guide_exists(self) -> None:
        assert SPRINT_GUIDE.exists(), "docs/guides/SPRINT_GUIDE.md not found"

    def test_epic_awareness_mentioned(self) -> None:
        content = SPRINT_GUIDE.read_text()
        assert "EPIC" in content and ("awareness" in content.lower() or "blocker gap" in content.lower() or "critical-path" in content.lower()), (
            "SPRINT_GUIDE.md must mention EPIC awareness in the review section"
        )

    def test_epic_context_section_referenced(self) -> None:
        content = SPRINT_GUIDE.read_text()
        assert "EPIC Context" in content or "epic-progress" in content or "ll-sprint show EPIC" in content, (
            "SPRINT_GUIDE.md must reference the EPIC Context section or relevant tools"
        )


class TestCommandsRefEpicAwareness:
    """Verify docs/reference/COMMANDS.md review-sprint output mentions EPIC gaps."""

    def test_commands_ref_exists(self) -> None:
        assert COMMANDS_REF.exists(), "docs/reference/COMMANDS.md not found"

    def test_review_sprint_output_mentions_epic(self) -> None:
        content = COMMANDS_REF.read_text()
        review_sprint_idx = content.index("/ll:review-sprint")
        # Check within the next 500 chars of the review-sprint entry
        section = content[review_sprint_idx : review_sprint_idx + 800]
        assert "EPIC" in section, (
            "COMMANDS.md /ll:review-sprint entry must mention EPIC critical-path gap flags in Output"
        )


class TestCliRefSprintShow:
    """Verify docs/reference/CLI.md documents EPIC ID as valid for ll-sprint show."""

    def test_cli_ref_exists(self) -> None:
        assert CLI_REF.exists(), "docs/reference/CLI.md not found"

    def test_ll_sprint_show_accepts_epic_id(self) -> None:
        content = CLI_REF.read_text()
        assert "EPIC-NNN" in content or "EPIC-" in content, (
            "CLI.md must document that ll-sprint show accepts EPIC IDs"
        )

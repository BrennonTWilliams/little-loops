"""Tests for ENH-1846: ll-history-context wiring across documentation files."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HELP_MD = PROJECT_ROOT / "commands" / "help.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
README = PROJECT_ROOT / "README.md"


class TestEnh1846LlHistoryContextWiring:
    """ENH-1846: ll-history-context must be wired into all documentation and manifest files."""

    def test_help_md_lists_ll_history_context(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-history-context" in content, (
            "commands/help.md must list ll-history-context in the CLI TOOLS block"
        )

    def test_cli_reference_has_ll_history_context_section(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-history-context" in content, (
            "docs/reference/CLI.md must have an ll-history-context section"
        )

    def test_claude_md_lists_ll_history_context(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "ll-history-context" in content, (
            ".claude/CLAUDE.md CLI Tools list must include ll-history-context"
        )

    def test_configure_areas_lists_ll_history_context(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "ll-history-context" in content, (
            "skills/configure/areas.md must enumerate ll-history-context in the tool list"
        )

    def test_configure_areas_count_updated_to_27(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "Authorize all 27" in content, (
            "skills/configure/areas.md must show 'Authorize all 27' ll- CLI tools"
        )

    def test_init_skill_has_bash_permission(self) -> None:
        content = INIT_SKILL.read_text()
        assert '"Bash(ll-history-context:*)"' in content, (
            'skills/init/SKILL.md must include "Bash(ll-history-context:*)" in the permissions block'
        )

    def test_init_skill_has_at_least_three_occurrences(self) -> None:
        content = INIT_SKILL.read_text()
        count = content.count("ll-history-context")
        assert count >= 3, (
            f"skills/init/SKILL.md must mention ll-history-context at least 3 times "
            f"(permissions + 2 CLAUDE.md boilerplate blocks); found {count}"
        )

    def test_readme_tool_count_updated_to_30(self) -> None:
        content = README.read_text()
        assert "30 typed CLI tools" in content, "README.md must say '30 typed CLI tools'"

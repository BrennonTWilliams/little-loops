"""Structural tests verifying ll-ctx-stats is wired into all documentation surfaces (FEAT-1625).

Asserts that ll-ctx-stats appears in commands/help.md, docs/reference/CLI.md,
.claude/CLAUDE.md, skills/configure/areas.md, and skills/init/SKILL.md.
ll-ctx-stats is intentionally excluded from docs/reference/HOST_COMPATIBILITY.md
(that file is for capability-probing tools like ll-doctor only).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HELP_MD = PROJECT_ROOT / "commands" / "help.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"


class TestHelpMdWiring:
    def test_ll_ctx_stats_in_cli_tools_block(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-ctx-stats" in content, (
            "commands/help.md must list ll-ctx-stats in CLI TOOLS block"
        )


class TestCliReferenceWiring:
    def test_ll_ctx_stats_section_present(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-ctx-stats" in content, "docs/reference/CLI.md must have an ll-ctx-stats section"


class TestClaudeMdWiring:
    def test_ll_ctx_stats_in_cli_tools_list(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "ll-ctx-stats" in content, (
            ".claude/CLAUDE.md CLI Tools list must include ll-ctx-stats"
        )


class TestConfigureAreasWiring:
    def test_ll_ctx_stats_in_authorize_all_description(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "ll-ctx-stats" in content, (
            "skills/configure/areas.md must include ll-ctx-stats in the authorize-all description"
        )

    def test_authorize_all_count_is_26(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "Authorize all 26" in content, (
            "skills/configure/areas.md authorize-all count must be 26 (includes ll-ctx-stats)"
        )


class TestInitSkillWiring:
    def test_ll_ctx_stats_permission_in_allow_list(self) -> None:
        content = INIT_SKILL.read_text()
        assert '"Bash(ll-ctx-stats:*)"' in content, (
            'skills/init/SKILL.md must include "Bash(ll-ctx-stats:*)" in permissions.allow list'
        )

    def test_ll_ctx_stats_in_boilerplate_blocks(self) -> None:
        content = INIT_SKILL.read_text()
        occurrences = content.count("ll-ctx-stats")
        assert occurrences >= 2, (
            f"skills/init/SKILL.md must mention ll-ctx-stats at least 2 times "
            f"(allow-list + boilerplate CLAUDE.md blocks), found {occurrences}"
        )

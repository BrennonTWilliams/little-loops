"""Structural tests verifying ll-logs is wired into help, init, and configure files."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HELP_MD = PROJECT_ROOT / "commands" / "help.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"


class TestHelpMdWiring:
    def test_ll_logs_in_cli_tools_block(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-logs" in content, "commands/help.md must list ll-logs in CLI TOOLS block"


class TestInitSkillWiring:
    def test_ll_logs_permission_in_allow_list(self) -> None:
        content = INIT_SKILL.read_text()
        assert '"Bash(ll-logs:*)"' in content, (
            'skills/init/SKILL.md must include "Bash(ll-logs:*)" in permissions.allow list'
        )

    def test_ll_logs_in_boilerplate_blocks(self) -> None:
        content = INIT_SKILL.read_text()
        occurrences = content.count("ll-logs")
        assert occurrences >= 2, (
            f"skills/init/SKILL.md must mention ll-logs at least 2 times "
            f"(file-exists and create-new boilerplate blocks), found {occurrences}"
        )


class TestConfigureAreasWiring:
    def test_ll_logs_in_authorize_all_description(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "ll-logs" in content, (
            "skills/configure/areas.md must include ll-logs in the authorize-all description"
        )

    def test_authorize_all_count_is_24(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "Authorize all 24" in content, (
            "skills/configure/areas.md authorize-all count must be 24 (includes ll-migrate-status)"
        )

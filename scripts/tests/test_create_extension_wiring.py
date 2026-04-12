"""Tests for FEAT-1049: ll-create-extension documentation wiring.

Verifies that ll-create-extension is registered in all authoritative
documentation and manifest files after the FEAT-1048 core CLI rollout.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HELP_MD = PROJECT_ROOT / "commands" / "help.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"


class TestHelpMdWiring:
    """ll-create-extension must appear in the CLI TOOLS block of commands/help.md."""

    def test_ll_create_extension_in_help(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-create-extension" in content, (
            "commands/help.md must list ll-create-extension in the CLI TOOLS block"
        )


class TestInitSkillWiring:
    """ll-create-extension must appear in all three locations in skills/init/SKILL.md."""

    def test_bash_permission_entry(self) -> None:
        content = INIT_SKILL.read_text()
        assert '"Bash(ll-create-extension:*)"' in content, (
            'skills/init/SKILL.md must include "Bash(ll-create-extension:*)" in the permissions block'
        )

    def test_at_least_three_occurrences(self) -> None:
        content = INIT_SKILL.read_text()
        count = content.count("ll-create-extension")
        assert count >= 3, (
            f"skills/init/SKILL.md must mention ll-create-extension at least 3 times "
            f"(permissions + 2 CLAUDE.md boilerplate blocks); found {count}"
        )


class TestConfigureAreasWiring:
    """skills/configure/areas.md must show 14 CLI tools including ll-create-extension."""

    def test_count_updated_to_14(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "Authorize all 14" in content, (
            "skills/configure/areas.md must show 'Authorize all 14' ll- CLI tools"
        )

    def test_ll_create_extension_in_enumeration(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "ll-create-extension" in content, (
            "skills/configure/areas.md must enumerate ll-create-extension in the tool list"
        )

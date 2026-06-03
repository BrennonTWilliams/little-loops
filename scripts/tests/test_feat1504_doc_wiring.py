"""Structural tests verifying ll-doctor is wired into all documentation surfaces (FEAT-1504).

Asserts that ll-doctor appears in commands/help.md, docs/reference/CLI.md,
.claude/CLAUDE.md, skills/configure/areas.md, skills/init/SKILL.md, and
docs/reference/HOST_COMPATIBILITY.md.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HELP_MD = PROJECT_ROOT / "commands" / "help.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
HOST_COMPAT = PROJECT_ROOT / "docs" / "reference" / "HOST_COMPATIBILITY.md"


class TestHelpMdWiring:
    def test_ll_doctor_in_cli_tools_block(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-doctor" in content, "commands/help.md must list ll-doctor in CLI TOOLS block"


class TestCliReferencewiring:
    def test_ll_doctor_section_present(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-doctor" in content, "docs/reference/CLI.md must have an ll-doctor section"


class TestClaudeMdWiring:
    def test_ll_doctor_in_cli_tools_list(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "ll-doctor" in content, ".claude/CLAUDE.md CLI Tools list must include ll-doctor"


class TestConfigureAreasWiring:
    def test_ll_doctor_in_authorize_all_description(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "ll-doctor" in content, (
            "skills/configure/areas.md must include ll-doctor in the authorize-all description"
        )

    def test_authorize_all_count_is_28(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "Authorize all 29" in content, (
            "skills/configure/areas.md authorize-all count must be 29"
        )


class TestInitSkillWiring:
    def test_ll_doctor_permission_in_allow_list(self) -> None:
        content = INIT_SKILL.read_text()
        assert '"Bash(ll-doctor:*)"' in content, (
            'skills/init/SKILL.md must include "Bash(ll-doctor:*)" in permissions.allow list'
        )

    def test_ll_doctor_in_boilerplate_blocks(self) -> None:
        content = INIT_SKILL.read_text()
        occurrences = content.count("ll-doctor")
        assert occurrences >= 2, (
            f"skills/init/SKILL.md must mention ll-doctor at least 2 times "
            f"(file-exists and create-new boilerplate blocks), found {occurrences}"
        )


class TestHostCompatibilityWiring:
    def test_ll_doctor_cross_link_present(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "ll-doctor" in content, (
            "docs/reference/HOST_COMPATIBILITY.md must cross-link to ll-doctor "
            "as the runnable capability check"
        )

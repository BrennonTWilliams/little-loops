"""Tests for FEAT-1049/FEAT-1045: ll-create-extension documentation wiring.

Verifies that ll-create-extension is registered in all authoritative
documentation and manifest files after the FEAT-1048 core CLI rollout (FEAT-1049)
and that SDK documentation updates from FEAT-1045 are present.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HELP_MD = PROJECT_ROOT / "commands" / "help.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
COMMANDS_MD = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"
README = PROJECT_ROOT / "README.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"


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


class TestFeat1045DocUpdates:
    """FEAT-1045: SDK documentation is accurate across all docs after implementation."""

    def test_readme_cli_section_has_ll_create_extension(self) -> None:
        content = README.read_text()
        assert "ll-create-extension" in content, (
            "README.md must have an ll-create-extension section in the CLI Tools block"
        )

    def test_readme_tool_count_is_14(self) -> None:
        content = README.read_text()
        assert "14 CLI tools" in content, (
            "README.md must say '14 CLI tools' (incremented from 13 after ll-create-extension landed)"
        )

    def test_claude_md_lists_ll_create_extension(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "ll-create-extension" in content, (
            ".claude/CLAUDE.md CLI Tools list must include ll-create-extension"
        )

    def test_cli_reference_has_ll_create_extension_section(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-create-extension" in content, (
            "docs/reference/CLI.md must have an ll-create-extension section"
        )

    def test_api_reference_module_table_has_testing(self) -> None:
        content = API_REFERENCE.read_text()
        assert "little_loops.testing" in content, (
            "docs/reference/API.md Module Overview table must include a little_loops.testing row"
        )


class TestBug863HooksInstallRemoved:
    """BUG-863: hooks install must be removed; hooks are automatic via plugin.

    Writing hooks to project settings files produces broken paths because
    ${CLAUDE_PLUGIN_ROOT} is only set when hooks load from a registered plugin's
    own hooks.json — not from project-level settings files.
    """

    def test_init_skill_does_not_have_pwd_substitution(self) -> None:
        """skills/init/SKILL.md must NOT contain the old pwd-substitution step."""
        content = INIT_SKILL.read_text()
        assert "Resolve `${CLAUDE_PLUGIN_ROOT}` by substituting" not in content, (
            "skills/init/SKILL.md must not contain the pwd-substitution step — "
            "hooks are automatic via plugin (BUG-863)"
        )

    def test_init_skill_has_hooks_note(self) -> None:
        """skills/init/SKILL.md Step 10.5 must be the no-op hooks note."""
        content = INIT_SKILL.read_text()
        assert "hooks fire automatically" in content, (
            "skills/init/SKILL.md Step 10.5 must say hooks fire automatically via plugin (BUG-863)"
        )

    def test_configure_areas_does_not_have_pwd_substitution(self) -> None:
        """skills/configure/areas.md must NOT contain the old pwd-substitution step."""
        content = CONFIGURE_AREAS.read_text()
        assert "Run `bash -c 'pwd'` to get the absolute plugin root path" not in content, (
            "skills/configure/areas.md must not contain the pwd-substitution step — "
            "hooks are automatic via plugin (BUG-863)"
        )

    def test_configure_areas_install_is_noop(self) -> None:
        """skills/configure/areas.md hooks install must be a no-op note, not a merge procedure."""
        content = CONFIGURE_AREAS.read_text()
        assert "Manual hook installation is not needed" in content, (
            "skills/configure/areas.md hooks install must say 'Manual hook installation is not needed' (BUG-863)"
        )

    def test_configure_areas_interactive_menu_has_no_install_option(self) -> None:
        """The interactive hooks menu must not offer 'install' as an action."""
        content = CONFIGURE_AREAS.read_text()
        assert "install — add ll- hooks to a settings file" not in content, (
            "skills/configure/areas.md interactive hooks menu must not offer 'install' (BUG-863)"
        )

    def test_commands_md_does_not_say_installs(self) -> None:
        """docs/reference/COMMANDS.md hooks description must not say 'installs'."""
        content = COMMANDS_MD.read_text()
        assert "installs/shows/validates" not in content, (
            "docs/reference/COMMANDS.md must not describe hooks as 'installs/shows/validates' — "
            "install was removed (BUG-863)"
        )

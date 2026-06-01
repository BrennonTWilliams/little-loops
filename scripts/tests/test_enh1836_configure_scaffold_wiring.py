"""Doc-wiring regression tests for ENH-1836: scaffold built-in design token profiles in /ll:configure.

Asserts that skills/configure/areas.md contains the materialization block and that
skills/configure/SKILL.md already declares Bash(python3:*) (no new tool entry needed).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CONFIGURE_SKILL = PROJECT_ROOT / "skills" / "configure" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"


class TestConfigureAreasMdScaffoldBlock:
    """areas.md must contain the Configuration Result materialization block for design_tokens."""

    def test_configuration_result_section_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "Configuration Result" in content, (
            "skills/configure/areas.md must contain a 'Configuration Result' section for design_tokens"
        )

    def test_shutil_copytree_scaffold_command_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "shutil.copytree" in content, (
            "skills/configure/areas.md must reference 'shutil.copytree' in the scaffold step"
        )

    def test_builtin_list_contains_all_three_profiles(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        for profile in ("default", "editorial-mono", "warm-paper"):
            assert profile in content, (
                f"skills/configure/areas.md BUILTIN list must include '{profile}'"
            )

    def test_ask_user_question_in_configuration_result(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        result_idx = content.index("Configuration Result — design_tokens")
        assert "AskUserQuestion" in content[result_idx:], (
            "The 'Configuration Result — design_tokens' section must reference AskUserQuestion "
            "for the interactive scaffold offer"
        )

    def test_dangerously_skip_permissions_guard_before_ask_user_question(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        result_idx = content.index("Configuration Result — design_tokens")
        section = content[result_idx:]
        skip_idx = section.find("DANGEROUSLY_SKIP_PERMISSIONS")
        ask_idx = section.find("AskUserQuestion")
        assert skip_idx != -1, (
            "The 'Configuration Result — design_tokens' section must reference "
            "DANGEROUSLY_SKIP_PERMISSIONS as a non-interactive guard"
        )
        assert skip_idx < ask_idx, (
            "DANGEROUSLY_SKIP_PERMISSIONS guard must appear before AskUserQuestion "
            "(guard-first ordering)"
        )

    def test_skill_md_already_declares_bash_python3(self) -> None:
        content = CONFIGURE_SKILL.read_text()
        assert "Bash(python3:*)" in content, (
            "skills/configure/SKILL.md must already declare Bash(python3:*) — "
            "no new allowed-tool entry should be needed for ENH-1836"
        )

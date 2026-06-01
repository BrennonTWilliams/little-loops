"""Tests for ENH-1866: ll-deps tree wiring across documentation files."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"
MAP_DEPS_SKILL = PROJECT_ROOT / "skills" / "map-dependencies" / "SKILL.md"


class TestEnh1866LlDepsTreeWiring:
    """ENH-1866: ll-deps tree must be documented in CLI.md, API.md, and SKILL.md."""

    def test_cli_md_has_ll_deps_tree_section(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-deps tree" in content, (
            "docs/reference/CLI.md must have an ll-deps tree section"
        )

    def test_cli_md_has_epic_flag(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "--epic" in content, (
            "docs/reference/CLI.md must document the --epic flag for ll-deps tree"
        )

    def test_api_md_main_deps_lists_tree(self) -> None:
        content = API_REFERENCE.read_text()
        # Find the main_deps block and verify 'tree' appears after it
        idx = content.find("main_deps")
        assert idx != -1, "docs/reference/API.md must contain main_deps anchor"
        after = content[idx:]
        sub_idx = after.find("Sub-commands:")
        assert sub_idx != -1, "docs/reference/API.md main_deps block must list Sub-commands"
        sub_line_end = after.index("\n", sub_idx)
        sub_line = after[sub_idx:sub_line_end]
        assert "tree" in sub_line, (
            f"docs/reference/API.md main_deps Sub-commands must include 'tree'; got: {sub_line!r}"
        )

    def test_api_md_stale_suggest_absent_from_main_deps(self) -> None:
        content = API_REFERENCE.read_text()
        idx = content.find("main_deps")
        assert idx != -1
        after = content[idx:]
        sub_idx = after.find("Sub-commands:")
        assert sub_idx != -1
        sub_line_end = after.index("\n", sub_idx)
        sub_line = after[sub_idx:sub_line_end]
        assert "suggest" not in sub_line, (
            f"Stale 'suggest' must not appear in main_deps Sub-commands; got: {sub_line!r}"
        )

    def test_api_md_stale_report_absent_from_main_deps(self) -> None:
        content = API_REFERENCE.read_text()
        idx = content.find("main_deps")
        assert idx != -1
        after = content[idx:]
        sub_idx = after.find("Sub-commands:")
        assert sub_idx != -1
        sub_line_end = after.index("\n", sub_idx)
        sub_line = after[sub_idx:sub_line_end]
        assert "report" not in sub_line, (
            f"Stale 'report' must not appear in main_deps Sub-commands; got: {sub_line!r}"
        )

    def test_skill_md_has_ll_deps_tree_epic_row(self) -> None:
        content = MAP_DEPS_SKILL.read_text()
        assert "ll-deps tree --epic" in content, (
            "skills/map-dependencies/SKILL.md must include an ll-deps tree --epic row"
        )

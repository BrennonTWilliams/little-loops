"""Tests for FEAT-1894: decisions CLI subcommand doc wiring.

Asserts that the decisions subcommand for ll-issues has been wired into all
documentation touchpoints: CLAUDE.md CLI tools list, commands/help.md,
docs/reference/CLI.md, and CONTRIBUTING.md.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
HELP_CMD = PROJECT_ROOT / "commands" / "help.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"


class TestDecisionsCLIMd:
    """.claude/CLAUDE.md must list 'decisions' in the ll-issues entry."""

    def test_decisions_in_ll_issues_list(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "decisions" in content, (
            "CLAUDE.md CLI tools list for ll-issues must include 'decisions'"
        )


class TestDecisionsHelpMd:
    """commands/help.md must reference 'decisions' in the ll-issues line."""

    def test_decisions_in_ll_issues_line(self) -> None:
        content = HELP_CMD.read_text()
        assert "decisions" in content, (
            "commands/help.md must include 'decisions' in the ll-issues entry"
        )


class TestDecisionsCLIReferenceMd:
    """docs/reference/CLI.md must contain an 'll-issues decisions' section."""

    def test_ll_issues_decisions_section_present(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-issues decisions" in content, (
            "docs/reference/CLI.md must contain an 'll-issues decisions' section"
        )


class TestDecisionsContributing:
    """CONTRIBUTING.md must reference 'decisions.py'."""

    def test_decisions_py_present(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "decisions.py" in content, "CONTRIBUTING.md must reference 'decisions.py'"

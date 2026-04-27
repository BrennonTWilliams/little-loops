"""Tests for ENH-1299: file:line references removed from issue-authoring pipeline sources.

Asserts that all five target files are free of `file:line` strings after the
ENH-1299 family (ENH-1302, ENH-1303, ENH-1304) is complete.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CODEBASE_ANALYZER = PROJECT_ROOT / "agents" / "codebase-analyzer.md"
CODEBASE_PATTERN_FINDER = PROJECT_ROOT / "agents" / "codebase-pattern-finder.md"
WIRE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "wire-issue" / "SKILL.md"
MANAGE_ISSUE_TEMPLATES = PROJECT_ROOT / "skills" / "manage-issue" / "templates.md"
REFINE_ISSUE_COMMAND = PROJECT_ROOT / "commands" / "refine-issue.md"


class TestCodebaseAnalyzerNoFileLine:
    """agents/codebase-analyzer.md must contain no file:line references."""

    def test_no_file_line_references(self) -> None:
        content = CODEBASE_ANALYZER.read_text()
        assert "file:line" not in content, (
            "agents/codebase-analyzer.md must not contain file:line references; "
            "use anchor-based equivalents (function/class names) instead"
        )


class TestCodebasePatternFinderNoFileLine:
    """agents/codebase-pattern-finder.md must contain no file:line references."""

    def test_no_file_line_references(self) -> None:
        content = CODEBASE_PATTERN_FINDER.read_text()
        assert "file:line" not in content, (
            "agents/codebase-pattern-finder.md must not contain file:line references; "
            "use anchor-based equivalents (function/class names) instead"
        )


class TestWireIssueSkillNoFileLine:
    """skills/wire-issue/SKILL.md must contain no file:line references."""

    def test_no_file_line_references(self) -> None:
        content = WIRE_ISSUE_SKILL.read_text()
        assert "file:line" not in content, (
            "skills/wire-issue/SKILL.md must not contain file:line references; "
            "use anchor-based equivalents (function/class names) instead"
        )


class TestManageIssueTemplatesNoFileLine:
    """skills/manage-issue/templates.md must contain no file:line references."""

    def test_no_file_line_references(self) -> None:
        content = MANAGE_ISSUE_TEMPLATES.read_text()
        assert "file:line" not in content, (
            "skills/manage-issue/templates.md must not contain file:line references; "
            "use anchor-based equivalents (function/class names) instead"
        )


class TestRefineIssueCommandNoFileLine:
    """commands/refine-issue.md must contain no file:line references."""

    def test_no_file_line_references(self) -> None:
        content = REFINE_ISSUE_COMMAND.read_text()
        assert "file:line" not in content, (
            "commands/refine-issue.md must not contain file:line references; "
            "use anchor-based equivalents (function/class names) instead"
        )

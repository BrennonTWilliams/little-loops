"""Tests for FEAT-1407: EPIC type wiring in skills, commands, and docs.

Verifies that key skill/command/doc .md files include EPIC in type lists.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_CAPTURE = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"
SKILL_NORMALIZE = PROJECT_ROOT / "commands" / "normalize-issues.md"
SKILL_FORMAT = PROJECT_ROOT / "skills" / "format-issue" / "SKILL.md"
SKILL_ISSUE_WORKFLOW = PROJECT_ROOT / "skills" / "issue-workflow" / "SKILL.md"
DOC_CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
DOC_ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"


class TestCaptureIssueEpicWiring:
    """skills/capture-issue/SKILL.md must include EPIC creation flow."""

    def test_epic_in_type_inference(self) -> None:
        content = SKILL_CAPTURE.read_text()
        assert "EPIC" in content, "capture-issue SKILL.md must include EPIC type"

    def test_epics_dir_routing(self) -> None:
        content = SKILL_CAPTURE.read_text()
        assert "epics/" in content, "capture-issue must route EPICs to .issues/epics/"


class TestNormalizeIssuesEpicWiring:
    """commands/normalize-issues.md must include EPIC in validation regex."""

    def test_epic_in_validation_regex(self) -> None:
        content = SKILL_NORMALIZE.read_text()
        assert "EPIC" in content, "normalize-issues.md must include EPIC in validation patterns"


class TestFormatIssueEpicWiring:
    """skills/format-issue/SKILL.md must include For EPICs placement branch."""

    def test_epic_type_branch(self) -> None:
        content = SKILL_FORMAT.read_text()
        assert "EPIC" in content, "format-issue SKILL.md must include EPIC type branch"


class TestIssueWorkflowEpicWiring:
    """skills/issue-workflow/SKILL.md must list epics/ directory."""

    def test_epics_dir_in_table(self) -> None:
        content = SKILL_ISSUE_WORKFLOW.read_text()
        assert "epics/" in content, "issue-workflow must list epics/ in directory table"


class TestClaudeMdEpicWiring:
    """.claude/CLAUDE.md issue type list must include EPIC."""

    def test_epic_in_type_list(self) -> None:
        content = DOC_CLAUDE_MD.read_text()
        assert "EPIC" in content, ".claude/CLAUDE.md must list EPIC as a valid issue type"


class TestArchitectureEpicWiring:
    """docs/ARCHITECTURE.md must show epics/ in issue hierarchy."""

    def test_epics_in_hierarchy(self) -> None:
        content = DOC_ARCHITECTURE.read_text()
        assert "epics/" in content, "ARCHITECTURE.md must show epics/ in issue hierarchy diagram"

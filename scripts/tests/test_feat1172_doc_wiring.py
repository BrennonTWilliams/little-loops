"""Tests for FEAT-1172: completed_at documentation wiring.

Verifies that the `completed_at` frontmatter field added by the
FEAT-1162 family (FEAT-1169/1170/1171/1172) is documented in the
expected locations so issue authors and downstream tooling can
discover it.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

ISSUE_TEMPLATE = PROJECT_ROOT / "docs" / "reference" / "ISSUE_TEMPLATE.md"
MANAGE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "manage-issue" / "SKILL.md"
API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"


class TestIssueTemplateWiring:
    """docs/reference/ISSUE_TEMPLATE.md must document the `completed_at` field."""

    def test_completed_at_in_frontmatter_table(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "`completed_at`" in content, (
            "docs/reference/ISSUE_TEMPLATE.md Frontmatter Fields table must include "
            "a `completed_at` row"
        )

    def test_completed_at_row_describes_completed_dir(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        # The row should mention that the field is set when moving to completed/
        # (populated by manage-issue, ll-auto, or ll-parallel).
        lines = [line for line in content.splitlines() if "`completed_at`" in line]
        assert lines, "expected at least one line referencing `completed_at`"
        row = next((line for line in lines if line.lstrip().startswith("|")), "")
        assert row, "expected a table row for `completed_at`"
        assert "completed" in row.lower(), (
            "`completed_at` table row must mention the completed directory / completion path"
        )


class TestManageIssueSkillWiring:
    """skills/manage-issue/SKILL.md must instruct injection of completed_at."""

    def test_completed_at_mentioned_in_skill(self) -> None:
        content = MANAGE_ISSUE_SKILL.read_text()
        assert "completed_at" in content, (
            "skills/manage-issue/SKILL.md must reference `completed_at` so the LLM "
            "knows to inject it before `git mv`"
        )

    def test_iso_utc_timestamp_command_present(self) -> None:
        content = MANAGE_ISSUE_SKILL.read_text()
        assert 'date -u +"%Y-%m-%dT%H:%M:%SZ"' in content, (
            "skills/manage-issue/SKILL.md must document the shell command "
            '`date -u +"%Y-%m-%dT%H:%M:%SZ"` used to produce the `completed_at` '
            "ISO 8601 UTC timestamp"
        )


class TestApiReferenceUnchanged:
    """docs/reference/API.md already documents `update_frontmatter` (FEAT-1169)."""

    def test_update_frontmatter_documented(self) -> None:
        content = API_REFERENCE.read_text()
        assert "update_frontmatter" in content, (
            "docs/reference/API.md must continue to document `update_frontmatter`"
        )

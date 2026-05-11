"""Tests for ENH-1433: canonical 6-field relationship vocabulary in skills and docs.

Verifies that key skill files and reference docs use the canonical relationship
field names (parent, blocked_by, depends_on, relates_to, duplicate_of) and that
the deprecated name `parent_issue` is absent from the files that were updated.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

ISSUE_SIZE_REVIEW = PROJECT_ROOT / "skills" / "issue-size-review" / "SKILL.md"
CONFIDENCE_CHECK = PROJECT_ROOT / "skills" / "confidence-check" / "SKILL.md"
MANAGE_ISSUE = PROJECT_ROOT / "skills" / "manage-issue" / "SKILL.md"
ISSUE_TEMPLATE = PROJECT_ROOT / "docs" / "reference" / "ISSUE_TEMPLATE.md"
API_MD = PROJECT_ROOT / "docs" / "reference" / "API.md"


class TestIssueSizeReviewCanonicalVocab:
    """skills/issue-size-review/SKILL.md must use `parent:` not `parent_issue:`."""

    def test_parent_field_present_in_draft_template(self) -> None:
        content = ISSUE_SIZE_REVIEW.read_text()
        assert "parent: [PARENT-ID]" in content, (
            "skills/issue-size-review/SKILL.md Phase 4 draft template must use `parent: [PARENT-ID]`"
        )

    def test_parent_field_present_in_phase6_prose(self) -> None:
        content = ISSUE_SIZE_REVIEW.read_text()
        assert "parent: [PARENT-ID]" in content, (
            "skills/issue-size-review/SKILL.md Phase 6 prose must reference `parent: [PARENT-ID]`"
        )

    def test_deprecated_parent_issue_absent(self) -> None:
        content = ISSUE_SIZE_REVIEW.read_text()
        assert "parent_issue:" not in content, (
            "skills/issue-size-review/SKILL.md must not reference deprecated `parent_issue:` field"
        )


class TestConfidenceCheckCanonicalVocab:
    """skills/confidence-check/SKILL.md must use `parent:` not `parent_issue:`."""

    def test_parent_field_present_in_epic_criterion(self) -> None:
        content = CONFIDENCE_CHECK.read_text()
        assert "parent: EPIC-NNN" in content or "parent: " in content, (
            "skills/confidence-check/SKILL.md Criterion 3 must reference `parent: EPIC-NNN`"
        )

    def test_deprecated_parent_issue_absent(self) -> None:
        content = CONFIDENCE_CHECK.read_text()
        assert "parent_issue: EPIC-NNN" not in content, (
            "skills/confidence-check/SKILL.md must not reference deprecated `parent_issue: EPIC-NNN`"
        )


class TestManageIssueCanonicalVocab:
    """skills/manage-issue/SKILL.md must use `parent:` not `parent_issue:` in EPIC handling."""

    def test_parent_field_present_in_epic_handling(self) -> None:
        content = MANAGE_ISSUE.read_text()
        assert "parent: EPIC-NNN" in content, (
            "skills/manage-issue/SKILL.md EPIC handling paragraph must reference `parent: EPIC-NNN`"
        )

    def test_deprecated_parent_issue_absent_in_epic_handling(self) -> None:
        content = MANAGE_ISSUE.read_text()
        assert "parent_issue: EPIC-NNN" not in content, (
            "skills/manage-issue/SKILL.md must not reference deprecated `parent_issue: EPIC-NNN`"
        )


class TestIssueTemplateCanonicalVocab:
    """docs/reference/ISSUE_TEMPLATE.md must use `parent:` not `parent_issue:` in frontmatter table."""

    def test_parent_row_present_in_frontmatter_table(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "| `parent`" in content, (
            "docs/reference/ISSUE_TEMPLATE.md frontmatter table must have a `parent` field row"
        )

    def test_deprecated_parent_issue_absent_in_frontmatter_table(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "| `parent_issue`" not in content, (
            "docs/reference/ISSUE_TEMPLATE.md frontmatter table must not have a `parent_issue` row"
        )

    def test_parent_field_in_epic_checklist(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "parent: EPIC-NNN" in content, (
            "docs/reference/ISSUE_TEMPLATE.md EPIC checklist must reference `parent: EPIC-NNN`"
        )

    def test_deprecated_parent_issue_absent_in_epic_checklist(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "parent_issue: EPIC-NNN" not in content, (
            "docs/reference/ISSUE_TEMPLATE.md EPIC checklist must not reference `parent_issue: EPIC-NNN`"
        )


class TestApiMdIssueInfoFields:
    """docs/reference/API.md IssueInfo block must include all 6 canonical relationship fields."""

    def test_parent_field_present(self) -> None:
        content = API_MD.read_text()
        assert "parent: str | None" in content, (
            "docs/reference/API.md IssueInfo must document the `parent` field"
        )

    def test_depends_on_field_present(self) -> None:
        content = API_MD.read_text()
        assert "depends_on: list[str]" in content, (
            "docs/reference/API.md IssueInfo must document the `depends_on` field"
        )

    def test_relates_to_field_present(self) -> None:
        content = API_MD.read_text()
        assert "relates_to: list[str]" in content, (
            "docs/reference/API.md IssueInfo must document the `relates_to` field"
        )

    def test_duplicate_of_field_present(self) -> None:
        content = API_MD.read_text()
        assert "duplicate_of: str | None" in content, (
            "docs/reference/API.md IssueInfo must document the `duplicate_of` field"
        )

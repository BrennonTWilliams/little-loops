"""Tests for ENH-1428: frontmatter-based status vocabulary in documentation.

Verifies that all doc files use the new status vocabulary introduced by ENH-1427
(open/in_progress/blocked/deferred/done/cancelled) and that stale directory-model
vocabulary (--status active, --status completed, active (default)) is absent.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CLI_MD = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
API_MD = PROJECT_ROOT / "docs" / "reference" / "API.md"
ISSUE_GUIDE = PROJECT_ROOT / "docs" / "guides" / "ISSUE_MANAGEMENT_GUIDE.md"
LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"
GETTING_STARTED = PROJECT_ROOT / "docs" / "guides" / "GETTING_STARTED.md"
README = PROJECT_ROOT / "README.md"


class TestCliMdStatusVocab:
    """docs/reference/CLI.md must use frontmatter-based status vocabulary."""

    def test_new_status_choices_present(self) -> None:
        content = CLI_MD.read_text()
        assert "open` (default)" in content or "`open` (default)" in content or "open (default)" in content, (
            "docs/reference/CLI.md must show `open` as the default --status value"
        )

    def test_in_progress_choice_present(self) -> None:
        content = CLI_MD.read_text()
        assert "in_progress" in content, (
            "docs/reference/CLI.md must list `in_progress` as a --status choice"
        )

    def test_done_choice_present(self) -> None:
        content = CLI_MD.read_text()
        assert "done" in content, (
            "docs/reference/CLI.md must list `done` as a --status choice"
        )

    def test_cancelled_choice_present(self) -> None:
        content = CLI_MD.read_text()
        assert "cancelled" in content, (
            "docs/reference/CLI.md must list `cancelled` as a --status choice"
        )

    def test_status_done_example_present(self) -> None:
        content = CLI_MD.read_text()
        assert "--status done" in content, (
            "docs/reference/CLI.md must show `--status done` in examples (not `--status completed`)"
        )

    def test_stale_status_active_absent(self) -> None:
        content = CLI_MD.read_text()
        assert "--status active" not in content, (
            "docs/reference/CLI.md must not reference `--status active` (replaced by `--status open`)"
        )

    def test_stale_status_completed_absent(self) -> None:
        content = CLI_MD.read_text()
        assert "--status completed" not in content, (
            "docs/reference/CLI.md must not reference `--status completed` (replaced by `--status done`)"
        )

    def test_stale_active_default_absent(self) -> None:
        content = CLI_MD.read_text()
        assert "active (default)" not in content, (
            "docs/reference/CLI.md must not reference `active (default)` (replaced by `open` default)"
        )

    def test_stale_active_directories_prose_absent(self) -> None:
        content = CLI_MD.read_text()
        assert "active category directories" not in content, (
            "docs/reference/CLI.md must not reference 'active category directories' (directory-model prose)"
        )


class TestApiMdStatusVocab:
    """docs/reference/API.md must use frontmatter-based status vocabulary in search/show sections."""

    def test_new_status_choices_present(self) -> None:
        content = API_MD.read_text()
        assert "{open,in_progress,blocked,deferred,done,cancelled,all}" in content, (
            "docs/reference/API.md search section must list new --status choices"
        )

    def test_stale_active_completed_deferred_choices_absent(self) -> None:
        content = API_MD.read_text()
        assert "{active,completed,deferred,all}" not in content, (
            "docs/reference/API.md must not show old `{active,completed,deferred,all}` status choices"
        )

    def test_stale_active_default_absent(self) -> None:
        content = API_MD.read_text()
        assert "default: `active`)" not in content, (
            "docs/reference/API.md must not show `active` as default status"
        )

    def test_stale_show_section_prose_absent(self) -> None:
        content = API_MD.read_text()
        assert "Searches all active category directories and the completed directory" not in content, (
            "docs/reference/API.md show section must not use directory-model prose"
        )

    def test_stale_search_prose_absent(self) -> None:
        content = API_MD.read_text()
        assert "active, completed, and/or deferred" not in content, (
            "docs/reference/API.md must not use 'active, completed, and/or deferred' prose"
        )


class TestIssueManagementGuideVocab:
    """docs/guides/ISSUE_MANAGEMENT_GUIDE.md must use the six shipped status values."""

    def test_in_progress_present(self) -> None:
        content = ISSUE_GUIDE.read_text()
        assert "in_progress" in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md status table must include `in_progress`"
        )

    def test_done_present(self) -> None:
        content = ISSUE_GUIDE.read_text()
        assert "`done`" in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md status table must include `done`"
        )

    def test_cancelled_present(self) -> None:
        content = ISSUE_GUIDE.read_text()
        assert "`cancelled`" in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md status table must include `cancelled`"
        )

    def test_stale_active_value_absent(self) -> None:
        content = ISSUE_GUIDE.read_text()
        # The word "active" appears in prose legitimately, but the table entry should not exist
        assert "| `active` |" not in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not have a table row for `active` status"
        )

    def test_stale_completed_value_absent(self) -> None:
        content = ISSUE_GUIDE.read_text()
        assert "| `completed` |" not in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not have a table row for `completed` status"
        )

    def test_directory_bucketing_statement_absent(self) -> None:
        content = ISSUE_GUIDE.read_text()
        assert "Directory location determines CLI bucketing" not in content, (
            "docs/guides/ISSUE_MANAGEMENT_GUIDE.md must not say 'Directory location determines CLI bucketing'"
        )


class TestLoopsGuideStatusVocab:
    """docs/guides/LOOPS_GUIDE.md must use `--status open` in YAML loop examples."""

    def test_status_open_in_yaml_action(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert 'action: "ll-issues list --status open"' in content, (
            "docs/guides/LOOPS_GUIDE.md YAML loop action must use `--status open` (not `--status active`)"
        )

    def test_stale_status_active_absent(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "--status active" not in content, (
            "docs/guides/LOOPS_GUIDE.md must not reference `--status active`"
        )


class TestReadmeStatusVocab:
    """README.md must use frontmatter-based status vocabulary in examples."""

    def test_status_done_example_present(self) -> None:
        content = README.read_text()
        assert "--status done" in content, (
            "README.md must show `--status done` in examples (not `--status completed`)"
        )

    def test_stale_status_completed_absent(self) -> None:
        content = README.read_text()
        assert "--status completed" not in content, (
            "README.md must not reference `--status completed` (replaced by `--status done`)"
        )

    def test_open_issues_comment_present(self) -> None:
        content = README.read_text()
        assert "open issues" in content, (
            "README.md `ll-issues list` comment should reference 'open issues' not 'active issues'"
        )

    def test_stale_active_issues_comment_absent(self) -> None:
        content = README.read_text()
        assert "List all active issues" not in content, (
            "README.md must not say 'List all active issues' (replaced by 'open issues')"
        )


class TestGettingStartedStatusVocab:
    """docs/guides/GETTING_STARTED.md must list the six shipped status values."""

    def test_in_progress_present(self) -> None:
        content = GETTING_STARTED.read_text()
        assert "in_progress" in content, (
            "docs/guides/GETTING_STARTED.md status list must include `in_progress`"
        )

    def test_done_present(self) -> None:
        content = GETTING_STARTED.read_text()
        assert "`done`" in content or "done`" in content, (
            "docs/guides/GETTING_STARTED.md status list must include `done`"
        )

    def test_cancelled_present(self) -> None:
        content = GETTING_STARTED.read_text()
        assert "cancelled" in content, (
            "docs/guides/GETTING_STARTED.md status list must include `cancelled`"
        )

    def test_stale_active_value_absent(self) -> None:
        content = GETTING_STARTED.read_text()
        # The word "active" in prose is fine; the stale enum list entry is the issue
        assert "`active`" not in content, (
            "docs/guides/GETTING_STARTED.md must not list `active` as a status value"
        )

    def test_stale_completed_value_absent(self) -> None:
        content = GETTING_STARTED.read_text()
        assert "`completed`" not in content, (
            "docs/guides/GETTING_STARTED.md must not list `completed` as a status value"
        )

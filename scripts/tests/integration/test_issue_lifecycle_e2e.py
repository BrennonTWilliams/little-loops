"""End-to-end test: a real issue lifecycle (finding H2).

Drives the real ``ll-issues`` CLI entry point (``main_issues``) to transition
an issue's status, then reads it back through the real ``IssueParser``. No
mocks: a genuine ``BRConfig`` resolves from a real ``.ll/ll-config.json``, the
status write goes through the canonical-enum validation + frontmatter writer,
and the read-back exercises the real parser. The history DB is isolated to a
temp path by the autouse conftest guards.

This closes the gap where status transitions were only ever exercised via
``cmd_*`` functions called directly, never through the dispatching entry point
that parses args and validates the target status.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


def _run_issues(argv: list[str]) -> int:
    """Invoke the real ll-issues entry point with the given argv tail."""
    from little_loops.cli.issues import main_issues

    with patch.object(sys, "argv", ["ll-issues", *argv]):
        return main_issues()


class TestIssueLifecycleEndToEnd:
    def test_create_set_status_read_back(
        self,
        temp_project_dir: Path,
        config_file: Path,
        issues_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """create → set-status done → read-back, through real entry points.

        Uses the conftest ``issues_dir`` fixture which scaffolds a real
        ``P0-BUG-001-critical-crash.md`` with ``status: open``.
        """
        from little_loops.config import BRConfig
        from little_loops.issue_parser import IssueParser

        monkeypatch.chdir(temp_project_dir)
        config = BRConfig(temp_project_dir)
        parser = IssueParser(config)
        issue_path = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"

        # --- Read-back BEFORE: the seeded issue is open ---
        before = parser.parse_file(issue_path)
        assert before.issue_id == "BUG-001"
        assert before.status == "open"

        # --- Transition via the real CLI dispatch ---
        assert _run_issues(["set-status", "BUG-001", "done"]) == 0

        # --- Read-back AFTER: status is now the terminal value ---
        after = parser.parse_file(issue_path)
        assert after.status == "done"
        # The transition only touched status — identity is preserved.
        assert after.issue_id == "BUG-001"
        assert after.title == before.title

    def test_invalid_status_is_rejected_and_file_untouched(
        self,
        temp_project_dir: Path,
        config_file: Path,
        issues_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non-canonical status is rejected and the file is left unchanged.

        This exercises the enum-validation branch of the real status path —
        the kind of negative behavior the prior direct-``cmd`` tests skipped.
        """
        from little_loops.config import BRConfig
        from little_loops.issue_parser import IssueParser

        monkeypatch.chdir(temp_project_dir)
        issue_path = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        original_content = issue_path.read_text()

        # "completed" is a synonym, not a canonical value. The status argument
        # is constrained by argparse ``choices=``, so the invalid value is
        # rejected at the parse layer with a nonzero SystemExit — before any
        # file write can happen.
        with pytest.raises(SystemExit) as exc:
            _run_issues(["set-status", "BUG-001", "completed"])
        assert exc.value.code != 0, "non-canonical status must exit nonzero"

        # File content is byte-for-byte unchanged.
        assert issue_path.read_text() == original_content
        parser = IssueParser(BRConfig(temp_project_dir))
        assert parser.parse_file(issue_path).status == "open"

    def test_unknown_issue_id_errors_cleanly(
        self,
        temp_project_dir: Path,
        config_file: Path,
        issues_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """set-status on a missing ID returns nonzero rather than raising."""
        monkeypatch.chdir(temp_project_dir)
        assert _run_issues(["set-status", "BUG-999", "done"]) != 0

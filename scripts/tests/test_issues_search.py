"""Tests for ll-issues search sub-command."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def search_issues_dir(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Create issue directories with varied sample issues for search tests."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config, indent=2))

    issues_base = temp_project_dir / ".issues"
    bugs_dir = issues_base / "bugs"
    features_dir = issues_base / "features"
    completed_dir = issues_base / "completed"
    deferred_dir = issues_base / "deferred"
    for d in (bugs_dir, features_dir, completed_dir, deferred_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Active bugs
    (bugs_dir / "P0-BUG-001-critical-crash.md").write_text(
        "---\ndiscovered_date: 2026-01-10T00:00:00Z\n---\n"
        "# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch.\n\n"
        "## Labels\n`bug`, `critical`\n"
    )
    (bugs_dir / "P2-BUG-002-caching-issue.md").write_text(
        "---\ndiscovered_date: 2026-02-15T00:00:00Z\n---\n"
        "# BUG-002: Caching problem in API\n\n## Summary\nCache invalidation is broken.\n\n"
        "## Labels\n`bug`, `api`, `cache`\n"
    )

    # Active features
    (features_dir / "P1-FEAT-010-dark-mode.md").write_text(
        "---\ndiscovered_date: 2026-01-20T00:00:00Z\n---\n"
        "# FEAT-010: Add dark mode\n\n## Summary\nImplement dark theme.\n\n"
        "## Labels\n`feature`, `ui`\n"
    )
    (features_dir / "P3-FEAT-011-export-csv.md").write_text(
        "---\ndiscovered_date: 2026-03-01T00:00:00Z\n---\n"
        "# FEAT-011: Export to CSV\n\n## Summary\nAdd CSV export functionality.\n\n"
        "## Labels\n`feature`, `api`\n"
    )

    # Completed issue
    (completed_dir / "P1-BUG-003-fixed-login.md").write_text(
        "---\ndiscovered_date: 2025-12-01T00:00:00Z\n---\n"
        "# BUG-003: Login redirect fails\n\n## Summary\nLogin caching issue was fixed.\n\n"
        "## Labels\n`bug`, `auth`\n"
    )

    return issues_base


def _run_search(temp_project_dir: Path, *argv: str) -> tuple[int, str]:
    """Run ll-issues search with given argv and return (exit_code, stdout)."""
    with patch.object(
        sys, "argv", ["ll-issues", "search", "--config", str(temp_project_dir), *argv]
    ):
        import importlib

        import little_loops.cli.issues as issues_mod

        importlib.reload(issues_mod)
        import io
        from contextlib import redirect_stdout

        from little_loops.cli.issues import main_issues

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main_issues()
        return code, buf.getvalue()


# ---------------------------------------------------------------------------
# Basic behavior
# ---------------------------------------------------------------------------


class TestSearchNoArgs:
    """ll-issues search with no arguments lists all active issues."""

    def test_lists_all_active_issues(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(sys, "argv", ["ll-issues", "search", "--config", str(temp_project_dir)]):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        # Should find active issues (BUG-001, BUG-002, FEAT-010, FEAT-011)
        assert "BUG-001" in captured.out
        assert "BUG-002" in captured.out
        assert "FEAT-010" in captured.out
        assert "FEAT-011" in captured.out
        # Should NOT include completed
        assert "BUG-003" not in captured.out

    def test_shows_total_count(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(sys, "argv", ["ll-issues", "search", "--config", str(temp_project_dir)]):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "4 issue(s) found" in captured.out


# ---------------------------------------------------------------------------
# Text query
# ---------------------------------------------------------------------------


class TestSearchTextQuery:
    """Text query filters by case-insensitive substring in title/body."""

    def test_matches_title(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys, "argv", ["ll-issues", "search", "dark mode", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "FEAT-010" in captured.out
        assert "BUG-001" not in captured.out

    def test_matches_body(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "cache invalidation", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-002" in captured.out

    def test_case_insensitive(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys, "argv", ["ll-issues", "search", "CRITICAL", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out

    def test_no_match_returns_zero(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "xyzzy-no-match", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        assert result == 0


# ---------------------------------------------------------------------------
# --type filter
# ---------------------------------------------------------------------------


class TestSearchTypeFilter:
    def test_filter_bug(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys, "argv", ["ll-issues", "search", "--type", "BUG", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out
        assert "BUG-002" in captured.out
        assert "FEAT-010" not in captured.out

    def test_filter_feat(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--type", "FEAT", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "FEAT-010" in captured.out
        assert "FEAT-011" in captured.out
        assert "BUG-001" not in captured.out

    def test_repeatable_type(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--type",
                "BUG",
                "--type",
                "FEAT",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out
        assert "FEAT-010" in captured.out


# ---------------------------------------------------------------------------
# --priority filter
# ---------------------------------------------------------------------------


class TestSearchPriorityFilter:
    def test_exact_priority(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--priority", "P0", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out
        assert "BUG-002" not in captured.out
        assert "FEAT-010" not in captured.out

    def test_priority_range(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--priority", "P0-P2", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out  # P0
        assert "BUG-002" in captured.out  # P2
        assert "FEAT-010" in captured.out  # P1
        assert "FEAT-011" not in captured.out  # P3


# ---------------------------------------------------------------------------
# --status and --include-completed
# ---------------------------------------------------------------------------


class TestSearchStatusFilter:
    def test_include_completed(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--include-completed", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-003" in captured.out
        assert "[completed]" in captured.out

    def test_status_all(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--status", "all", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out
        assert "BUG-003" in captured.out

    def test_status_completed_only(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--status", "completed", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-003" in captured.out
        assert "BUG-001" not in captured.out

    def test_text_query_with_include_completed(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Searching 'caching' with --include-completed should find both BUG-002 and BUG-003."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "caching",
                "--include-completed",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-002" in captured.out
        assert "BUG-003" in captured.out


# ---------------------------------------------------------------------------
# --label filter
# ---------------------------------------------------------------------------


class TestSearchLabelFilter:
    def test_filter_by_label(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--label", "api", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-002" in captured.out  # has 'api' label
        assert "FEAT-011" in captured.out  # has 'api' label
        assert "FEAT-010" not in captured.out  # has 'ui' label, not 'api'


# ---------------------------------------------------------------------------
# --since / --until date filters
# ---------------------------------------------------------------------------


class TestSearchDateFilter:
    def test_since_filters_old_issues(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--since", "2026-02-01", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-002" in captured.out  # 2026-02-15
        assert "FEAT-011" in captured.out  # 2026-03-01
        assert "BUG-001" not in captured.out  # 2026-01-10
        assert "FEAT-010" not in captured.out  # 2026-01-20

    def test_until_filters_new_issues(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--until", "2026-01-31", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-001" in captured.out  # 2026-01-10
        assert "FEAT-010" in captured.out  # 2026-01-20
        assert "BUG-002" not in captured.out  # 2026-02-15

    def test_invalid_since_returns_error(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--since", "not-a-date", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        assert result == 1


# ---------------------------------------------------------------------------
# --date-field=updated
# ---------------------------------------------------------------------------


class TestSearchDateFieldUpdated:
    """Tests for --date-field=updated using Session Log timestamps or mtime fallback."""

    @pytest.fixture
    def updated_issues_dir(self, temp_project_dir: Path, sample_config: dict) -> Path:
        """Issue files with varied Session Log timestamps for date-field=updated tests."""
        import json

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config, indent=2))

        issues_base = temp_project_dir / ".issues"
        bugs_dir = issues_base / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        # Issue with session log entry in March 2026, discovered in January 2026
        (bugs_dir / "P1-BUG-010-session-march.md").write_text(
            "---\ndiscovered_date: 2026-01-01T00:00:00Z\n---\n"
            "# BUG-010: Issue with session log in March\n\n## Summary\nSome bug.\n\n"
            "## Session Log\n"
            "- `/ll:refine-issue` - 2026-03-15T10:00:00 - `/some/path.jsonl`\n"
        )

        # Issue with session log entry in January 2026, discovered in January 2026
        (bugs_dir / "P2-BUG-011-session-january.md").write_text(
            "---\ndiscovered_date: 2026-01-05T00:00:00Z\n---\n"
            "# BUG-011: Issue with session log in January\n\n## Summary\nAnother bug.\n\n"
            "## Session Log\n"
            "- `/ll:verify-issues` - 2026-01-20T12:00:00 - `/some/path.jsonl`\n"
        )

        # Issue with no session log (mtime fallback) — touch to a known recent mtime
        no_log_path = bugs_dir / "P3-BUG-012-no-session-log.md"
        no_log_path.write_text(
            "---\ndiscovered_date: 2026-01-10T00:00:00Z\n---\n"
            "# BUG-012: Issue without session log\n\n## Summary\nNo log here.\n"
        )

        return issues_base

    def test_updated_since_filters_by_session_log(
        self, temp_project_dir: Path, updated_issues_dir: Path
    ) -> None:
        code, out = _run_search(
            temp_project_dir, "--date-field", "updated", "--since", "2026-03-01"
        )
        assert code == 0
        # BUG-010 has a March session log entry — should be included
        assert "BUG-010" in out
        # BUG-011 has a January session log entry — should be excluded
        assert "BUG-011" not in out

    def test_updated_until_filters_by_session_log(
        self, temp_project_dir: Path, updated_issues_dir: Path
    ) -> None:
        code, out = _run_search(
            temp_project_dir, "--date-field", "updated", "--until", "2026-02-01"
        )
        assert code == 0
        # BUG-011 has a January session log entry — should be included
        assert "BUG-011" in out
        # BUG-010 has a March session log entry — should be excluded
        assert "BUG-010" not in out

    def test_updated_uses_last_session_log_entry(
        self, temp_project_dir: Path, sample_config: dict, updated_issues_dir: Path
    ) -> None:
        """When multiple session log entries exist, the last one wins."""

        bugs_dir = updated_issues_dir / "bugs"
        (bugs_dir / "P1-BUG-020-multi-entry.md").write_text(
            "---\ndiscovered_date: 2026-01-01T00:00:00Z\n---\n"
            "# BUG-020: Issue with multiple session entries\n\n## Summary\nMulti.\n\n"
            "## Session Log\n"
            "- `/ll:verify-issues` - 2026-01-10T08:00:00 - `/some/path.jsonl`\n"
            "- `/ll:refine-issue` - 2026-03-20T14:30:00 - `/some/path.jsonl`\n"
        )
        code, out = _run_search(
            temp_project_dir, "--date-field", "updated", "--since", "2026-03-01"
        )
        assert code == 0
        assert "BUG-020" in out

    def test_updated_differs_from_discovered_when_session_log_present(
        self, temp_project_dir: Path, updated_issues_dir: Path
    ) -> None:
        """--date-field=updated and --date-field=discovered should differ when session log exists."""
        code_upd, out_upd = _run_search(
            temp_project_dir, "--date-field", "updated", "--since", "2026-03-01"
        )
        code_disc, out_disc = _run_search(
            temp_project_dir, "--date-field", "discovered", "--since", "2026-03-01"
        )
        assert code_upd == 0
        assert code_disc == 0
        # BUG-010 discovered in Jan but session-log in March — included with updated, not with discovered
        assert "BUG-010" in out_upd
        assert "BUG-010" not in out_disc


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


class TestSearchSorting:
    def test_sort_by_priority_default(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--format", "ids", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        # P0 before P1 before P2 before P3
        assert lines.index("BUG-001") < lines.index("FEAT-010")
        assert lines.index("FEAT-010") < lines.index("BUG-002")
        assert lines.index("BUG-002") < lines.index("FEAT-011")

    def test_sort_by_title(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--sort",
                "title",
                "--format",
                "ids",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        # "Add dark mode" < "Caching problem" < "Critical crash" < "Export to CSV"
        assert lines.index("FEAT-010") < lines.index("BUG-002")
        assert lines.index("BUG-002") < lines.index("BUG-001")

    def test_sort_desc(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--sort",
                "priority",
                "--desc",
                "--format",
                "ids",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        # With desc, P3 comes before P0
        assert lines.index("FEAT-011") < lines.index("BUG-001")


# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------


class TestSearchOutputFormats:
    def test_json_output(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "search", "--type", "BUG", "--json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        ids = {item["id"] for item in data}
        assert ids == {"BUG-001", "BUG-002"}
        # Check JSON fields
        for item in data:
            assert "id" in item
            assert "priority" in item
            assert "type" in item
            assert "title" in item
            assert "path" in item
            assert "status" in item
            assert "discovered_date" in item

    def test_ids_format(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--type",
                "BUG",
                "--format",
                "ids",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = captured.out.strip().splitlines()
        assert all(re.match(r"^[A-Z]+-\d+$", ln.strip()) for ln in lines)

    def test_list_format(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--type",
                "BUG",
                "--format",
                "list",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        # list format: "filename.md  title"
        for line in captured.out.strip().splitlines():
            assert ".md" in line

    def test_limit(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--limit",
                "2",
                "--format",
                "ids",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [line for line in captured.out.strip().splitlines() if line.strip()]
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------


class TestSearchCombinedFilters:
    def test_type_and_priority(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "--type",
                "BUG",
                "--priority",
                "P2",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "BUG-002" in captured.out
        assert "BUG-001" not in captured.out  # P0

    def test_query_and_type(
        self,
        temp_project_dir: Path,
        search_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "search",
                "api",
                "--type",
                "FEAT",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        assert "FEAT-011" in captured.out
        assert "BUG-002" not in captured.out  # right query but wrong type


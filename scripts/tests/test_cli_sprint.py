"""Tests for ll-sprint CLI dispatcher (main_sprint).

Covers subcommand routing, alias resolution, --handoff-threshold validation,
and shared argument forwarding for the sprint CLI entry point.

Focuses on gaps not covered by existing tests in test_cli.py
(TestSprintArgumentParsing uses a hand-rolled parser, not the real main_sprint).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.sprint import main_sprint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_handlers(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Mock all sprint command handlers to return 0 and track calls."""
    mocks: dict[str, MagicMock] = {}
    handler_names = [
        "_cmd_sprint_create",
        "_cmd_sprint_run",
        "_cmd_sprint_list",
        "_cmd_sprint_show",
        "_cmd_sprint_edit",
        "_cmd_sprint_delete",
        "_cmd_sprint_analyze",
    ]
    for name in handler_names:
        mock = MagicMock(return_value=0)
        monkeypatch.setattr(f"little_loops.cli.sprint.{name}", mock)
        mocks[name] = mock
    return mocks


def _make_sprint_project(tmp_path: Path) -> Path:
    """Create a minimal temp project with config so main_sprint can initialize."""
    import json

    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    config = {
        "project": {"name": "test"},
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
            },
        },
    }
    (ll_dir / "ll-config.json").write_text(json.dumps(config))

    issues_dir = tmp_path / ".issues"
    for category in ["bugs", "features", "epics"]:
        (issues_dir / category).mkdir(parents=True, exist_ok=True)

    (tmp_path / ".sprints").mkdir(exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Subcommand Routing Tests
# ---------------------------------------------------------------------------


class TestMainSprintDispatch:
    """Tests for main_sprint() subcommand routing with mocked handlers."""

    def test_create_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_sprint dispatches 'create' to _cmd_sprint_create."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "create", "test-sprint", "--issues", "BUG-001"]
        ):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_create"].assert_called_once()

    def test_run_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_sprint dispatches 'run' to _cmd_sprint_run."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_run"].assert_called_once()

    def test_run_alias_r_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'r' dispatches to _cmd_sprint_run."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "r", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_run"].assert_called_once()

    def test_list_routes_to_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_sprint dispatches 'list' to _cmd_sprint_list (no project root needed)."""
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "list"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_list"].assert_called_once()

    def test_list_alias_l_routes_to_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Alias 'l' dispatches to _cmd_sprint_list."""
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "l"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_list"].assert_called_once()

    def test_show_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_sprint dispatches 'show' to _cmd_sprint_show."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "show", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_show"].assert_called_once()

    def test_show_alias_s_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 's' dispatches to _cmd_sprint_show."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "s", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_show"].assert_called_once()

    def test_edit_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_sprint dispatches 'edit' to _cmd_sprint_edit."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "edit", "test-sprint", "--add", "BUG-001"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_edit"].assert_called_once()

    def test_edit_alias_e_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'e' dispatches to _cmd_sprint_edit."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "e", "test-sprint", "--add", "BUG-001"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_edit"].assert_called_once()

    def test_delete_routes_to_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_sprint dispatches 'delete' to _cmd_sprint_delete (no project root needed)."""
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "delete", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_delete"].assert_called_once()

    def test_delete_alias_del_routes_to_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Alias 'del' dispatches to _cmd_sprint_delete."""
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "del", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_delete"].assert_called_once()

    def test_analyze_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_sprint dispatches 'analyze' to _cmd_sprint_analyze."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "analyze", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_analyze"].assert_called_once()

    def test_analyze_alias_a_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'a' dispatches to _cmd_sprint_analyze."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "a", "test-sprint"]):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_analyze"].assert_called_once()

    def test_no_command_returns_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No subcommand returns exit code 1."""
        with patch.object(sys, "argv", ["ll-sprint"]):
            result = main_sprint()

        assert result == 1


# ---------------------------------------------------------------------------
# Argument Forwarding Tests
# ---------------------------------------------------------------------------


class TestMainSprintArgForwarding:
    """Tests that shared arguments are parsed and forwarded correctly."""

    def test_run_forwards_dry_run_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--dry-run flag is parsed and handler receives args.dry_run=True."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--dry-run"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.dry_run is True

    def test_run_forwards_quiet_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--quiet flag is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--quiet"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.quiet is True

    def test_run_forwards_resume_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--resume flag is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--resume"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.resume is True

    def test_run_forwards_max_workers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--max-workers value is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--max-workers", "8"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.max_workers == 8

    def test_run_forwards_skip_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--skip argument is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--skip", "BUG-001,FEAT-002"]
        ):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.skip == "BUG-001,FEAT-002"

    def test_run_forwards_only_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--only argument is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--only", "BUG-001"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.only == "BUG-001"

    def test_run_forwards_skip_analysis(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--skip-analysis flag is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--skip-analysis"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.skip_analysis is True

    def test_run_forwards_type_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--type argument is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--type", "BUG,FEAT"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.type == "BUG,FEAT"

    def test_run_forwards_label_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--label argument is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--label", "test-coverage"]
        ):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.label == "test-coverage"

    def test_show_forwards_skip_analysis(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--skip-analysis flag on show is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "show", "test-sprint", "--skip-analysis"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_show"].call_args[0][0]
        assert call_args.skip_analysis is True

    def test_show_forwards_json_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--json flag on show is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "show", "test-sprint", "--json"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_show"].call_args[0][0]
        assert call_args.json is True

    def test_list_forwards_json_short_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """-j short form for list sets json=True."""
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "list", "-j"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_list"].call_args[0][0]
        assert call_args.json is True

    def test_analyze_forwards_format_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--format json on analyze is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "analyze", "test-sprint", "--format", "json"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_analyze"].call_args[0][0]
        assert call_args.format == "json"

    def test_create_forwards_description(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--description flag on create is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys,
            "argv",
            [
                "ll-sprint",
                "create",
                "test-sprint",
                "--issues",
                "BUG-001",
                "--description",
                "My sprint desc",
            ],
        ):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_create"].call_args[0][0]
        assert call_args.description == "My sprint desc"


# ---------------------------------------------------------------------------
# --handoff-threshold Validation Tests
# ---------------------------------------------------------------------------


class TestHandoffThresholdValidation:
    """Tests for --handoff-threshold range validation in main_sprint()."""

    def test_valid_threshold_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold 50 is accepted (within 1-100 range)."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--handoff-threshold", "50"]
        ):
            result = main_sprint()

        assert result == 0

    def test_threshold_below_1_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold 0 causes parser.error (SystemExit)."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--handoff-threshold", "0"]
        ):
            with pytest.raises(SystemExit):
                main_sprint()

    def test_threshold_above_100_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold 101 causes parser.error (SystemExit)."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--handoff-threshold", "101"]
        ):
            with pytest.raises(SystemExit):
                main_sprint()

    def test_threshold_boundary_1_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold 1 is accepted (lower bound)."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--handoff-threshold", "1"]
        ):
            result = main_sprint()

        assert result == 0

    def test_threshold_boundary_100_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold 100 is accepted (upper bound)."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-sprint", "run", "test-sprint", "--handoff-threshold", "100"]
        ):
            result = main_sprint()

        assert result == 0


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


class TestMainSprintEdgeCases:
    """Edge case and error path tests for main_sprint()."""

    def test_run_with_config_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--config flag sets project root for commands that need it."""
        project = _make_sprint_project(tmp_path)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys,
            "argv",
            ["ll-sprint", "run", "test-sprint", "--config", str(project)],
        ):
            result = main_sprint()

        assert result == 0
        mocks["_cmd_sprint_run"].assert_called_once()

    def test_list_with_verbose_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """list --verbose forwards verbose=True."""
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "list", "--verbose"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_list"].call_args[0][0]
        assert call_args.verbose is True

    def test_run_with_save_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run --save flag is parsed and forwarded."""
        project = _make_sprint_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-sprint", "run", "test-sprint", "--save"]):
            result = main_sprint()

        assert result == 0
        call_args = mocks["_cmd_sprint_run"].call_args[0][0]
        assert call_args.save is True


# ---------------------------------------------------------------------------
# Wall-clock timeout tests
# ---------------------------------------------------------------------------


class TestIssueWallClockTimeout:
    """Tests for per-issue wall-clock timeout in the sequential dispatch loop."""

    def test_exception_class_attributes(self) -> None:
        """IssueWallClockTimeout stores the issue_id and is an Exception."""
        from little_loops.cli.sprint.run import IssueWallClockTimeout

        exc = IssueWallClockTimeout("BUG-2144")
        assert exc.issue_id == "BUG-2144"
        assert "BUG-2144" in str(exc)
        assert isinstance(exc, Exception)

    def test_run_issue_with_wall_clock_timeout_returns_success_on_fast_completion(
        self,
    ) -> None:
        """Helper returns the original result when process_issue_inplace completes in time."""
        from unittest.mock import MagicMock, patch

        from little_loops.cli.sprint.run import _run_issue_with_wall_clock_timeout
        from little_loops.issue_manager import IssueProcessingResult
        from little_loops.issue_parser import IssueInfo

        mock_issue = MagicMock(spec=IssueInfo)
        mock_issue.issue_id = "BUG-001"
        mock_config = MagicMock()
        mock_logger = MagicMock()
        expected = IssueProcessingResult(success=True, duration=1.0, issue_id="BUG-001")

        with patch("little_loops.cli.sprint.run.signal") as mock_signal:
            mock_signal.SIGALRM = 14
            mock_signal.signal.return_value = None
            with patch("little_loops.cli.sprint.run.process_issue_inplace", return_value=expected):
                result = _run_issue_with_wall_clock_timeout(
                    issue=mock_issue,
                    config=mock_config,
                    logger=mock_logger,
                    dry_run=False,
                    max_seconds=2700,
                )

        assert result.success is True
        assert result.issue_id == "BUG-001"

    def test_run_issue_with_wall_clock_timeout_catches_timeout_and_returns_failure(
        self,
    ) -> None:
        """Helper catches IssueWallClockTimeout and returns a WALL_CLOCK_TIMEOUT result."""
        from unittest.mock import MagicMock, patch

        from little_loops.cli.sprint.run import (
            IssueWallClockTimeout,
            _run_issue_with_wall_clock_timeout,
        )
        from little_loops.issue_parser import IssueInfo

        mock_issue = MagicMock(spec=IssueInfo)
        mock_issue.issue_id = "BUG-2144"
        mock_config = MagicMock()
        mock_logger = MagicMock()

        def _raise_timeout(*_args, **_kwargs) -> None:
            raise IssueWallClockTimeout("BUG-2144")

        with patch("little_loops.cli.sprint.run.signal") as mock_signal:
            mock_signal.SIGALRM = 14
            mock_signal.signal.return_value = None
            with patch(
                "little_loops.cli.sprint.run.process_issue_inplace", side_effect=_raise_timeout
            ):
                result = _run_issue_with_wall_clock_timeout(
                    issue=mock_issue,
                    config=mock_config,
                    logger=mock_logger,
                    dry_run=False,
                    max_seconds=60,
                )

        assert result.success is False
        assert result.issue_id == "BUG-2144"
        assert result.failure_reason == "WALL_CLOCK_TIMEOUT"
        mock_signal.alarm.assert_called_with(0)

    def test_alarm_is_cleared_in_finally_after_timeout(self) -> None:
        """signal.alarm(0) is always called in the finally block."""
        from unittest.mock import MagicMock, call, patch

        from little_loops.cli.sprint.run import (
            IssueWallClockTimeout,
            _run_issue_with_wall_clock_timeout,
        )
        from little_loops.issue_parser import IssueInfo

        mock_issue = MagicMock(spec=IssueInfo)
        mock_issue.issue_id = "BUG-001"

        def _raise_timeout(*_args, **_kwargs) -> None:
            raise IssueWallClockTimeout("BUG-001")

        with patch("little_loops.cli.sprint.run.signal") as mock_signal:
            mock_signal.SIGALRM = 14
            mock_signal.signal.return_value = None
            with patch(
                "little_loops.cli.sprint.run.process_issue_inplace", side_effect=_raise_timeout
            ):
                _run_issue_with_wall_clock_timeout(
                    issue=mock_issue,
                    config=MagicMock(),
                    logger=MagicMock(),
                    dry_run=False,
                    max_seconds=60,
                )

        alarm_calls = mock_signal.alarm.call_args_list
        assert call(0) in alarm_calls


# ---------------------------------------------------------------------------
# Feature-branch in-place warning (ENH-2176 Option B)
# ---------------------------------------------------------------------------


class TestFeatureBranchInPlaceWarning:
    """One-time warning when use_feature_branches is set and a wave runs in-place."""

    def _make_args(self, feature_branches=None, epic_branches=None) -> MagicMock:
        args = MagicMock()
        args.sprint = "test-sprint"
        args.quiet = False
        args.dry_run = False
        args.resume = False
        args.skip = None
        args.only = None
        args.type = None
        args.label = None
        args.skip_analysis = True
        args.max_workers = 1
        args.handoff_threshold = None
        args.context_limit = None
        args.save = False
        args.feature_branches = feature_branches
        args.epic_branches = epic_branches
        return args

    def _make_config(
        self, *, use_feature_branches: bool, epic_branches_enabled: bool = False
    ) -> MagicMock:
        config = MagicMock()
        config.parallel.use_feature_branches = use_feature_branches
        config.parallel.epic_branches.enabled = epic_branches_enabled
        config.sprints.max_issue_wall_clock_time = 60
        config.issues.base_dir = ".issues"
        config.project_root = Path(".")
        return config

    def _run(
        self,
        args: MagicMock,
        config: MagicMock,
        num_waves: int = 1,
        issue_result: object | None = None,
    ) -> tuple[int, list]:
        """Call _cmd_sprint_run with enough mocking to reach the in-place wave path.

        Returns (exit_code, warning_calls) where warning_calls is a list of
        positional-arg tuples from the Logger.warning mock.
        """
        from little_loops.cli.sprint.run import _cmd_sprint_run
        from little_loops.issue_manager import IssueProcessingResult
        from little_loops.issue_parser import IssueInfo

        mock_issues = []
        for i in range(num_waves):
            issue = MagicMock(spec=IssueInfo)
            issue.issue_id = f"ENH-{100 + i}"
            issue.labels = []
            mock_issues.append(issue)

        issue_ids = [iss.issue_id for iss in mock_issues]

        mock_path = MagicMock()
        mock_path.read_text.return_value = "---\nstatus: open\n---\n"

        mock_sprint = MagicMock()
        mock_sprint.name = "test-sprint"
        mock_sprint.issues = issue_ids
        mock_sprint.options = None

        mock_manager = MagicMock()
        mock_manager.load_or_resolve.return_value = mock_sprint
        mock_manager.validate_issues.return_value = dict.fromkeys(issue_ids, mock_path)
        mock_manager.load_issue_infos.return_value = mock_issues

        waves = [[iss] for iss in mock_issues]
        contention_notes = [None] * len(waves)

        outcome = issue_result or IssueProcessingResult(
            success=True, duration=0.1, issue_id="dummy"
        )
        warning_calls: list = []
        orchestration_calls: list[dict] = []

        with (
            patch("little_loops.cli.sprint.run.signal"),
            patch("little_loops.frontmatter.parse_frontmatter", return_value={"status": "open"}),
            patch(
                "little_loops.frontmatter.update_frontmatter",
                side_effect=lambda c, _: c,
            ),
            patch("little_loops.dependency_mapper.gather_all_issue_ids", return_value=set()),
            patch("little_loops.cli.sprint.run.DependencyGraph") as mock_graph_cls,
            patch(
                "little_loops.cli.sprint.run.refine_waves_for_contention",
                return_value=(waves, contention_notes),
            ),
            patch(
                "little_loops.cli.sprint.run._run_issue_with_wall_clock_timeout",
                return_value=outcome,
            ),
            patch(
                "little_loops.cli.sprint.run.record_orchestration_run",
                side_effect=lambda _db, **kwargs: orchestration_calls.append(kwargs),
            ),
            patch("little_loops.cli.sprint.run._save_sprint_state"),
            patch("little_loops.cli.sprint.run._cleanup_sprint_state"),
            patch("little_loops.cli.sprint.run._detect_current_branch", return_value="main"),
            patch("little_loops.cli.sprint.run.use_color_enabled", return_value=False),
            patch("little_loops.cli.sprint.run.Logger") as mock_logger_cls,
        ):
            mock_graph = MagicMock()
            mock_graph.has_cycles.return_value = False
            mock_graph.get_execution_waves.return_value = waves
            mock_graph_cls.from_issues.return_value = mock_graph

            mock_logger = MagicMock()
            mock_logger_cls.return_value = mock_logger
            mock_logger.warning.side_effect = lambda msg: warning_calls.append(msg)

            exit_code = _cmd_sprint_run(args, mock_manager, config)

        self.orchestration_calls = orchestration_calls
        return exit_code, warning_calls

    def test_direct_waves_share_run_id_and_record_success(self) -> None:
        from little_loops.issue_manager import IssueProcessingResult

        args = self._make_args()
        config = self._make_config(use_feature_branches=False)
        outcome = IssueProcessingResult(success=True, duration=1.25, issue_id="ignored")
        exit_code, _ = self._run(args, config, num_waves=2, issue_result=outcome)

        assert exit_code == 0
        assert len(self.orchestration_calls) == 2
        assert {call["issue_id"] for call in self.orchestration_calls} == {
            "ENH-100",
            "ENH-101",
        }
        assert {call["status"] for call in self.orchestration_calls} == {"completed"}
        assert {call["driver"] for call in self.orchestration_calls} == {"ll-sprint"}
        assert len({call["run_id"] for call in self.orchestration_calls}) == 1

    def test_direct_timeout_and_blocked_outcomes_are_mapped(self) -> None:
        from little_loops.issue_manager import IssueProcessingResult

        args = self._make_args()
        config = self._make_config(use_feature_branches=False)
        timeout = IssueProcessingResult(
            success=False,
            duration=60.0,
            issue_id="ignored",
            failure_reason="WALL_CLOCK_TIMEOUT",
        )
        exit_code, _ = self._run(args, config, issue_result=timeout)
        assert exit_code == 1
        assert self.orchestration_calls[0]["status"] == "failed"
        assert self.orchestration_calls[0]["failure_reason"] == "WALL_CLOCK_TIMEOUT"

        blocked = IssueProcessingResult(
            success=False,
            duration=0.5,
            issue_id="ignored",
            was_blocked=True,
            failure_reason="blocked by BUG-1",
        )
        exit_code, _ = self._run(args, config, issue_result=blocked)
        assert exit_code == 0
        assert self.orchestration_calls[0]["status"] == "skipped"
        assert self.orchestration_calls[0]["failure_reason"] == "blocked by BUG-1"

    def test_warning_emitted_when_config_flag_set_and_wave_in_place(self) -> None:
        """Warning fires when use_feature_branches=True (via config) and wave runs in-place."""
        args = self._make_args(feature_branches=None)
        config = self._make_config(use_feature_branches=True)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        assert len(matching) == 1
        assert "main" in matching[0]

    def test_warning_emitted_when_cli_flag_true_and_wave_in_place(self) -> None:
        """Warning fires when --feature-branches CLI flag is True (overriding unset config)."""
        args = self._make_args(feature_branches=True)
        config = self._make_config(use_feature_branches=False)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        assert len(matching) == 1

    def test_no_warning_when_flag_unset(self) -> None:
        """No warning when use_feature_branches is False and CLI flag is absent."""
        args = self._make_args(feature_branches=None)
        config = self._make_config(use_feature_branches=False)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        assert matching == []

    def test_no_warning_when_cli_flag_explicitly_false(self) -> None:
        """No warning when --no-feature-branches overrides a True config value."""
        args = self._make_args(feature_branches=False)
        config = self._make_config(use_feature_branches=True)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        assert matching == []

    def test_warning_emitted_only_once_for_multiple_in_place_waves(self) -> None:
        """Warning fires exactly once even when multiple single-issue waves run in-place."""
        args = self._make_args(feature_branches=None)
        config = self._make_config(use_feature_branches=True)
        exit_code, warnings = self._run(args, config, num_waves=3)
        assert exit_code == 0
        matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        assert len(matching) == 1

    def test_epic_warning_emitted_when_config_flag_set_and_wave_in_place(self) -> None:
        """Epic-branch caveat fires when epic_branches.enabled=True and wave runs in-place."""
        args = self._make_args(epic_branches=None)
        config = self._make_config(use_feature_branches=False, epic_branches_enabled=True)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "epic-branch mode does not apply" in w]
        assert len(matching) == 1
        assert "main" in matching[0]
        # Existing feature-branch substring assertions must still pass unchanged.
        fb_matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        assert fb_matching == []

    def test_epic_warning_emitted_when_cli_flag_true_and_wave_in_place(self) -> None:
        """Epic-branch caveat fires when --epic-branches CLI flag is True."""
        args = self._make_args(epic_branches=True)
        config = self._make_config(use_feature_branches=False, epic_branches_enabled=False)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "epic-branch mode does not apply" in w]
        assert len(matching) == 1

    def test_no_epic_warning_when_flag_unset(self) -> None:
        """No epic-branch caveat when epic_branches.enabled is False and CLI flag is absent."""
        args = self._make_args(epic_branches=None)
        config = self._make_config(use_feature_branches=False, epic_branches_enabled=False)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "epic-branch mode does not apply" in w]
        assert matching == []

    def test_no_epic_warning_when_cli_flag_explicitly_false(self) -> None:
        """No epic-branch caveat when --no-epic-branches overrides a True config value."""
        args = self._make_args(epic_branches=False)
        config = self._make_config(use_feature_branches=False, epic_branches_enabled=True)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        matching = [w for w in warnings if "epic-branch mode does not apply" in w]
        assert matching == []

    def test_epic_warning_emitted_only_once_for_multiple_in_place_waves(self) -> None:
        """Epic-branch caveat fires exactly once across multiple single-issue in-place waves."""
        args = self._make_args(epic_branches=None)
        config = self._make_config(use_feature_branches=False, epic_branches_enabled=True)
        exit_code, warnings = self._run(args, config, num_waves=3)
        assert exit_code == 0
        matching = [w for w in warnings if "epic-branch mode does not apply" in w]
        assert len(matching) == 1

    def test_both_warnings_emitted_when_both_modes_effective(self) -> None:
        """Both caveats fire independently, preserving both substrings, when both modes are on."""
        args = self._make_args(feature_branches=True, epic_branches=True)
        config = self._make_config(use_feature_branches=False, epic_branches_enabled=False)
        exit_code, warnings = self._run(args, config)
        assert exit_code == 0
        fb_matching = [w for w in warnings if "feature-branch mode does not apply" in w]
        eb_matching = [w for w in warnings if "epic-branch mode does not apply" in w]
        assert len(fb_matching) == 1
        assert len(eb_matching) == 1


class TestSprintParallelBaseBranchDetection:
    """Multi-issue waves resolve base_branch via detect_default_branch (BUG-2323)."""

    def _make_args(self) -> MagicMock:
        args = MagicMock()
        args.sprint = "test-sprint"
        args.quiet = False
        args.dry_run = False
        args.resume = False
        args.skip = None
        args.only = None
        args.type = None
        args.label = None
        args.skip_analysis = True
        args.max_workers = 2
        args.handoff_threshold = None
        args.context_limit = None
        args.save = False
        args.feature_branches = None
        args.epic_branches = None
        return args

    def _run_multi_issue_wave(
        self, configured_base_branch: str | None
    ) -> tuple[int, MagicMock, MagicMock]:
        """Drive _cmd_sprint_run through one two-issue wave (the parallel path).

        Returns (exit_code, mock_detect, mock_config) for assertions on how the
        base branch was resolved.
        """
        from little_loops.cli.sprint.run import _cmd_sprint_run
        from little_loops.issue_parser import IssueInfo

        config = MagicMock()
        config.parallel.use_feature_branches = False
        config.parallel.base_branch = configured_base_branch
        config.sprints.max_issue_wall_clock_time = 60
        config.issues.base_dir = ".issues"
        config.project_root = Path(".")

        mock_issues = []
        for i in range(2):
            issue = MagicMock(spec=IssueInfo)
            issue.issue_id = f"ENH-{200 + i}"
            issue.labels = []
            mock_issues.append(issue)
        issue_ids = [iss.issue_id for iss in mock_issues]

        mock_path = MagicMock()
        mock_path.read_text.return_value = "---\nstatus: open\n---\n"

        mock_sprint = MagicMock()
        mock_sprint.name = "test-sprint"
        mock_sprint.issues = issue_ids
        mock_sprint.options = None

        mock_manager = MagicMock()
        mock_manager.load_or_resolve.return_value = mock_sprint
        mock_manager.validate_issues.return_value = dict.fromkeys(issue_ids, mock_path)
        mock_manager.load_issue_infos.return_value = mock_issues

        waves = [mock_issues]  # single wave of 2 issues -> parallel path
        contention_notes: list = [None]

        with (
            patch("little_loops.cli.sprint.run.signal"),
            patch("little_loops.frontmatter.parse_frontmatter", return_value={"status": "open"}),
            patch(
                "little_loops.frontmatter.update_frontmatter",
                side_effect=lambda c, _: c,
            ),
            patch("little_loops.dependency_mapper.gather_all_issue_ids", return_value=set()),
            patch("little_loops.cli.sprint.run.DependencyGraph") as mock_graph_cls,
            patch(
                "little_loops.cli.sprint.run.refine_waves_for_contention",
                return_value=(waves, contention_notes),
            ),
            patch("little_loops.cli.sprint.run._save_sprint_state"),
            patch("little_loops.cli.sprint.run._cleanup_sprint_state"),
            patch(
                "little_loops.cli.sprint.run.detect_default_branch",
                return_value="develop",
            ) as mock_detect,
            patch("little_loops.cli.sprint.run.ParallelOrchestrator") as mock_orch_cls,
            patch("little_loops.extension.wire_extensions"),
            patch("little_loops.transport.wire_transports"),
            patch("little_loops.cli.sprint.run.use_color_enabled", return_value=False),
            patch("little_loops.cli.sprint.run.Logger") as mock_logger_cls,
        ):
            mock_graph = MagicMock()
            mock_graph.has_cycles.return_value = False
            mock_graph.get_execution_waves.return_value = waves
            mock_graph_cls.from_issues.return_value = mock_graph

            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch.execution_duration = 0.2
            mock_orch.queue.completed_ids = list(issue_ids)
            mock_orch.queue.failed_ids = []
            mock_orch_cls.return_value = mock_orch

            mock_logger_cls.return_value = MagicMock()

            exit_code = _cmd_sprint_run(args=self._make_args(), manager=mock_manager, config=config)

        return exit_code, mock_detect, config

    def test_multi_issue_wave_uses_detected_default_branch(self) -> None:
        """With no configured base_branch, the wave uses detect_default_branch()."""
        exit_code, mock_detect, config = self._run_multi_issue_wave(configured_base_branch=None)
        assert exit_code == 0
        mock_detect.assert_called_once()
        _, kwargs = config.create_parallel_config.call_args
        assert kwargs["base_branch"] == "develop"

    def test_multi_issue_wave_prefers_configured_base_branch(self) -> None:
        """An explicit parallel.base_branch config value wins over auto-detection."""
        exit_code, mock_detect, config = self._run_multi_issue_wave(
            configured_base_branch="release"
        )
        assert exit_code == 0
        mock_detect.assert_not_called()
        _, kwargs = config.create_parallel_config.call_args
        assert kwargs["base_branch"] == "release"

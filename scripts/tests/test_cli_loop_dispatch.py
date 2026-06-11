"""Tests for ll-loop CLI dispatcher (main_loop).

Covers subcommand routing, alias resolution, and the auto-insert-"run"
shorthand for the loop CLI entry point.

Focuses on gaps not covered by existing tests in test_cli.py
(TestMainLoopIntegration and TestMainLoopAdditionalCoverage test a few
subcommands through main_loop, but not systematically for all 17).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.loop import main_loop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_handlers(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Mock all loop command handlers to return 0 and track calls."""
    mocks: dict[str, MagicMock] = {}
    handler_specs: list[tuple[str, list[str]]] = [
        ("little_loops.cli.loop.config_cmds", ["cmd_validate", "cmd_install"]),
        (
            "little_loops.cli.loop.info",
            [
                "cmd_list",
                "cmd_history",
                "cmd_show",
                "cmd_fragments",
                "cmd_audit_meta",
                "cmd_calibrate_budget",
                "cmd_diagnose_evaluators",
                "cmd_promote_baseline",
            ],
        ),
        (
            "little_loops.cli.loop.lifecycle",
            ["cmd_status", "cmd_stop", "cmd_resume", "cmd_monitor"],
        ),
        ("little_loops.cli.loop.next_loop", ["cmd_next_loop"]),
        ("little_loops.cli.loop.run", ["cmd_run"]),
        ("little_loops.cli.loop.testing", ["cmd_test", "cmd_simulate"]),
    ]
    for module_path, names in handler_specs:
        for name in names:
            mock = MagicMock(return_value=0)
            monkeypatch.setattr(f"{module_path}.{name}", mock)
            mocks[name] = mock
    return mocks


def _make_loop_project(tmp_path: Path) -> Path:
    """Create a minimal temp project with config so main_loop can initialize."""
    import json

    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    config = {
        "project": {"name": "test"},
        "loops": {"loops_dir": ".loops"},
    }
    (ll_dir / "ll-config.json").write_text(json.dumps(config))
    (tmp_path / ".loops").mkdir(exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Subcommand Routing Tests
# ---------------------------------------------------------------------------


class TestMainLoopDispatch:
    """Tests for main_loop() subcommand routing with mocked handlers."""

    # -- run --

    def test_run_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_loop dispatches 'run' to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()

    def test_run_alias_r_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'r' dispatches to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "r", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()

    # -- validate --

    def test_validate_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'validate' to cmd_validate."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "validate", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_validate"].assert_called_once()

    def test_validate_alias_val_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'val' dispatches to cmd_validate."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "val", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_validate"].assert_called_once()

    # -- list --

    def test_list_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_loop dispatches 'list' to cmd_list."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "list"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_list"].assert_called_once()

    def test_list_alias_l_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'l' dispatches to cmd_list."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "l"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_list"].assert_called_once()

    # -- status --

    def test_status_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'status' to cmd_status."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_status"].assert_called_once()

    def test_status_alias_st_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'st' dispatches to cmd_status."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "st", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_status"].assert_called_once()

    # -- stop --

    def test_stop_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_loop dispatches 'stop' to cmd_stop."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_stop"].assert_called_once()

    # -- resume --

    def test_resume_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'resume' to cmd_resume."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_resume"].assert_called_once()

    def test_resume_alias_res_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'res' dispatches to cmd_resume."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "res", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_resume"].assert_called_once()

    # -- history --

    def test_history_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'history' to cmd_history."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_history"].assert_called_once()

    def test_history_alias_h_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'h' dispatches to cmd_history."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "h", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_history"].assert_called_once()

    # -- test --

    def test_test_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_loop dispatches 'test' to cmd_test."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "test", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_test"].assert_called_once()

    def test_test_alias_t_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 't' dispatches to cmd_test."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "t", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_test"].assert_called_once()

    # -- simulate --

    def test_simulate_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'simulate' to cmd_simulate."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "simulate", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_simulate"].assert_called_once()

    def test_simulate_alias_sim_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 'sim' dispatches to cmd_simulate."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "sim", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_simulate"].assert_called_once()

    # -- install --

    def test_install_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'install' to cmd_install."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "install", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_install"].assert_called_once()

    # -- show --

    def test_show_routes_to_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """main_loop dispatches 'show' to cmd_show."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "show", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_show"].assert_called_once()

    def test_show_alias_s_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Alias 's' dispatches to cmd_show."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "s", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_show"].assert_called_once()

    # -- fragments --

    def test_fragments_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'fragments' to cmd_fragments."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "fragments", "lib/common.yaml"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_fragments"].assert_called_once()

    # -- next-loop --

    def test_next_loop_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'next-loop' to cmd_next_loop."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "next-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_next_loop"].assert_called_once()

    # -- audit-meta --

    def test_audit_meta_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'audit-meta' to cmd_audit_meta."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "audit-meta", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_audit_meta"].assert_called_once()

    # -- calibrate-budget --

    def test_calibrate_budget_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'calibrate-budget' to cmd_calibrate_budget."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "calibrate-budget", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_calibrate_budget"].assert_called_once()

    # -- diagnose-evaluators --

    def test_diagnose_evaluators_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'diagnose-evaluators' to cmd_diagnose_evaluators."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "diagnose-evaluators", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_diagnose_evaluators"].assert_called_once()

    # -- promote-baseline --

    def test_promote_baseline_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'promote-baseline' to cmd_promote_baseline."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "promote-baseline", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_promote_baseline"].assert_called_once()

    # -- monitor --

    def test_monitor_routes_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main_loop dispatches 'monitor' to cmd_monitor."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "monitor", "test-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_monitor"].assert_called_once()


# ---------------------------------------------------------------------------
# Shorthand (auto-insert "run") Tests
# ---------------------------------------------------------------------------


class TestMainLoopShorthand:
    """Tests for the auto-insert-'run' shorthand behavior."""

    def test_unknown_first_arg_inserts_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When first positional arg is not a subcommand, 'run' is prepended."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "my-loop"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()

    def test_flag_before_loop_name_no_shorthand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When first arg starts with '-', shorthand is not triggered."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        # --help should show help, not try to run a loop named '--help'
        with patch.object(sys, "argv", ["ll-loop", "--help"]):
            with pytest.raises(SystemExit):
                main_loop()

        # No handler should have been called
        for mock in mocks.values():
            mock.assert_not_called()

    def test_no_args_shows_help(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No arguments shows help and returns 1."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop"]):
            result = main_loop()

        assert result == 1
        # No handler should have been called
        for mock in mocks.values():
            mock.assert_not_called()


# ---------------------------------------------------------------------------
# Shared Flag Forwarding Tests
# ---------------------------------------------------------------------------


class TestMainLoopRunFlagForwarding:
    """Tests that run subcommand flags are parsed and forwarded correctly."""

    def test_max_iterations_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--max-iterations is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--max-iterations", "5"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        call_args = mocks["cmd_run"].call_args
        assert call_args[0][1].max_iterations == 5

    def test_dry_run_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--dry-run is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--dry-run"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].dry_run is True

    def test_no_llm_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--no-llm is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].no_llm is True

    def test_background_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--background/-b is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--background"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].background is True

    def test_worktree_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--worktree is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--worktree"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].worktree is True

    def test_delay_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--delay is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--delay", "2.5"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].delay == 2.5

    def test_llm_model_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--llm-model is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--llm-model", "sonnet"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].llm_model == "sonnet"

    def test_queue_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--queue/-q is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--queue"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].queue is True

    def test_context_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--context KEY=VALUE is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--context", "theme=dark"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert "theme=dark" in mocks["cmd_run"].call_args[0][1].context

    def test_baseline_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--baseline is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--baseline"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].baseline is True

    def test_handoff_threshold_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold is parsed and forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-loop", "run", "test-loop", "--handoff-threshold", "75"]
        ):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()


class TestMainLoopRunHandoffThresholdAccepted:
    """Tests that --handoff-threshold values are forwarded (no range check in dispatcher).

    Unlike the sprint dispatcher (which validates 1-100 range in main_sprint),
    the loop dispatcher passes the raw value to cmd_run for later validation.
    """

    @pytest.mark.parametrize("value", ["0", "101", "50"])
    def test_handoff_threshold_forwarded_to_handler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        """--handoff-threshold values (even out-of-range) are forwarded to cmd_run."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-loop", "run", "test-loop", "--handoff-threshold", value]
        ):
            result = main_loop()

        assert result == 0
        mocks["cmd_run"].assert_called_once()
        assert mocks["cmd_run"].call_args[0][1].handoff_threshold == int(value)


class TestMainLoopShowFlagForwarding:
    """Tests that show subcommand flags are parsed and forwarded correctly."""

    def test_show_verbose_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--verbose is parsed and forwarded to cmd_show."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "show", "test-loop", "--verbose"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_show"].assert_called_once()
        assert mocks["cmd_show"].call_args[0][1].verbose is True

    def test_show_json_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--json is parsed and forwarded to cmd_show."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "show", "test-loop", "--json"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_show"].assert_called_once()
        assert mocks["cmd_show"].call_args[0][1].json is True


class TestMainLoopListFlagForwarding:
    """Tests that list subcommand flags are parsed and forwarded correctly."""

    def test_list_running_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--running is parsed and forwarded to cmd_list."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "list", "--running"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_list"].assert_called_once()
        assert mocks["cmd_list"].call_args[0][0].running is True

    def test_list_json_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--json is parsed and forwarded to cmd_list."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "list", "--json"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_list"].assert_called_once()
        assert mocks["cmd_list"].call_args[0][0].json is True

    def test_list_category_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--category is parsed and forwarded to cmd_list."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "list", "--category", "data"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_list"].assert_called_once()
        assert mocks["cmd_list"].call_args[0][0].category == "data"


class TestMainLoopHistoryFlagForwarding:
    """Tests that history subcommand flags are parsed correctly."""

    def test_history_tail_forwarded(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--tail is parsed and forwarded to cmd_history."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "20"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_history"].assert_called_once()
        assert mocks["cmd_history"].call_args[0][2].tail == 20


class TestMainLoopSimulateFlagForwarding:
    """Tests that simulate subcommand flags are parsed correctly."""

    def test_simulate_scenario_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--scenario is parsed and forwarded to cmd_simulate."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-loop", "simulate", "test-loop", "--scenario", "all-pass"]
        ):
            result = main_loop()

        assert result == 0
        mocks["cmd_simulate"].assert_called_once()

    def test_simulate_max_iterations_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--max-iterations is parsed and forwarded to cmd_simulate."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-loop", "simulate", "test-loop", "--max-iterations", "10"]
        ):
            result = main_loop()

        assert result == 0
        mocks["cmd_simulate"].assert_called_once()


class TestMainLoopNextLoopFlagForwarding:
    """Tests that next-loop subcommand flags are parsed correctly."""

    def test_next_loop_count_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--count is parsed and forwarded to cmd_next_loop."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "next-loop", "--count", "3"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_next_loop"].assert_called_once()

    def test_next_loop_json_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--json is parsed and forwarded to cmd_next_loop."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mocks = _mock_handlers(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "next-loop", "--json"]):
            result = main_loop()

        assert result == 0
        mocks["cmd_next_loop"].assert_called_once()

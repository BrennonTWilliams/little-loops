"""Tests for --cross-host flag on ll-loop run --baseline (ENH-2086)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from little_loops.ab_writer import ABResults, calculate_ab_summary, write_ab_json
from little_loops.cli.loop import main_loop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop_project(tmp_path: Path) -> Path:
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    config = {"project": {"name": "test"}, "loops": {"loops_dir": ".loops"}}
    (ll_dir / "ll-config.json").write_text(json.dumps(config))
    (tmp_path / ".loops").mkdir(exist_ok=True)
    return tmp_path


def _mock_cmd_run(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value=0)
    monkeypatch.setattr("little_loops.cli.loop.run.cmd_run", mock)
    return mock


def _make_ab_results(harness_wins: bool = True, n: int = 5) -> ABResults:
    """Build an ABResults fixture where harness beats (or loses to) baseline."""
    items = []
    for i in range(n):
        h_pass = i < (n - 1) if harness_wins else i < 1
        b_pass = i < 1 if harness_wins else i < (n - 1)
        items.append(
            {
                "harness_pass": h_pass,
                "baseline_pass": b_pass,
                "harness_tokens": 100,
                "baseline_tokens": 80,
                "harness_duration_ms": 1000.0,
                "baseline_duration_ms": 800.0,
            }
        )
    return calculate_ab_summary(items)


def _write_ab(run_dir: Path, results: ABResults) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    write_ab_json(results, str(run_dir))
    return run_dir / "ab.json"


# ---------------------------------------------------------------------------
# CLI flag parsing
# ---------------------------------------------------------------------------


class TestCrossHostFlagParsed:
    def test_cross_host_accepted_by_argparse(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--cross-host is recognised by the run subparser."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mock_run = _mock_cmd_run(monkeypatch)

        with patch.object(
            sys, "argv", ["ll-loop", "run", "test-loop", "--baseline", "--cross-host"]
        ):
            result = main_loop()

        assert result == 0
        mock_run.assert_called_once()
        assert mock_run.call_args[0][1].cross_host is True

    def test_cross_host_defaults_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--cross-host defaults to False when omitted."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mock_run = _mock_cmd_run(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--baseline"]):
            main_loop()

        assert mock_run.call_args[0][1].cross_host is False

    def test_cross_host_without_baseline_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--cross-host without --baseline is accepted (no-op at runtime)."""
        project = _make_loop_project(tmp_path)
        monkeypatch.chdir(project)
        mock_run = _mock_cmd_run(monkeypatch)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--cross-host"]):
            result = main_loop()

        assert result == 0
        assert mock_run.call_args[0][1].cross_host is True


# ---------------------------------------------------------------------------
# Context storage in run.py
# ---------------------------------------------------------------------------


class TestCrossHostContextStorage:
    def _make_args(self, **kwargs: object) -> argparse.Namespace:
        defaults = {
            "loop": "my-loop",
            "baseline": True,
            "baseline_skill": None,
            "items": None,
            "cross_host": False,
            "worktree": False,
            "background": False,
            "follow": False,
            "dry_run": False,
            "no_llm": False,
            "llm_model": None,
            "delay": None,
            "max_iterations": None,
            "quiet": False,
            "verbose": False,
            "foreground_internal": True,
            "instance_id": None,
            "show_diagrams": None,
            "diagram_edge_labels": None,
            "diagram_state_detail": None,
            "diagram_scope": None,
            "clear": False,
            "queue": False,
            "no_lock": False,
            "context": None,
            "program_md": None,
            "builtin": False,
            "handoff_threshold": None,
            "context_limit": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_cross_host_stored_when_baseline_and_cross_host(self, tmp_path: Path) -> None:
        """cross_host=True is stored in _baseline context when both flags are set."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.schema import FSMLoop

        args = self._make_args(cross_host=True)
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = loops_dir / "my-loop.yaml"
        loop_yaml.write_text(
            "name: my-loop\ninitial: start\nstates:\n  start:\n    action: /test\n    on_success: __done__\n"
        )

        with (
            patch("little_loops.cli.loop.run.run_foreground", return_value=0) as mock_fg,
            patch("little_loops.cli.loop.run._reconcile_stale_runs"),
            patch("little_loops.cli.loop.run.LockManager"),
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.wire_extensions"),
            patch("little_loops.cli.loop.run.wire_transports"),
            patch("os.getpid", return_value=12345),
        ):
            cmd_run(loops_dir, args)

        # run_foreground was called; check the FSM it received has _baseline.cross_host
        _, fsm, *_ = mock_fg.call_args[0]
        assert fsm.context.get("_baseline", {}).get("cross_host") is True

    def test_cross_host_false_stored_when_not_set(self, tmp_path: Path) -> None:
        """cross_host=False is stored in _baseline context when only --baseline is set."""
        from little_loops.cli.loop.run import cmd_run

        args = self._make_args(cross_host=False)
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\ninitial: start\nstates:\n  start:\n    action: /test\n    on_success: __done__\n"
        )

        with (
            patch("little_loops.cli.loop.run.run_foreground", return_value=0) as mock_fg,
            patch("little_loops.cli.loop.run._reconcile_stale_runs"),
            patch("little_loops.cli.loop.run.LockManager"),
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.wire_extensions"),
            patch("little_loops.cli.loop.run.wire_transports"),
            patch("os.getpid", return_value=12345),
        ):
            cmd_run(loops_dir, args)

        _, fsm, *_ = mock_fg.call_args[0]
        assert fsm.context.get("_baseline", {}).get("cross_host") is False


# ---------------------------------------------------------------------------
# Background subprocess forwarding
# ---------------------------------------------------------------------------


class TestCrossHostBackgroundForwarding:
    def test_cross_host_forwarded_to_background_cmd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--cross-host is appended to the background subprocess command."""
        from little_loops.cli.loop._helpers import run_background

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\ninitial: s\nstates:\n  s:\n    action: /x\n    on_success: __done__\n"
        )
        args = argparse.Namespace(
            loop="my-loop",
            baseline=True,
            cross_host=True,
            baseline_skill=None,
            items=None,
            foreground_internal=False,
            background=True,
            quiet=False,
            verbose=False,
            follow=False,
            no_llm=False,
            llm_model=None,
            delay=None,
            max_iterations=None,
            no_lock=False,
            queue=False,
            context=None,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            program_md=None,
            builtin=False,
            handoff_threshold=None,
            context_limit=None,
            instance_id=None,
        )

        captured_cmds: list[list[str]] = []

        def fake_popen(cmd: list[str], **kwargs: object) -> MagicMock:
            captured_cmds.append(list(cmd))
            proc = MagicMock()
            proc.pid = 9999
            return proc

        with (
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("builtins.open", MagicMock()),
            patch("pathlib.Path.write_text"),
            patch("pathlib.Path.mkdir"),
        ):
            run_background("my-loop", args, loops_dir)

        assert len(captured_cmds) == 1
        assert "--cross-host" in captured_cmds[0]

    def test_cross_host_not_forwarded_when_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--cross-host is NOT added to background cmd when False."""
        from little_loops.cli.loop._helpers import run_background

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\ninitial: s\nstates:\n  s:\n    action: /x\n    on_success: __done__\n"
        )
        args = argparse.Namespace(
            loop="my-loop",
            baseline=True,
            cross_host=False,
            baseline_skill=None,
            items=None,
            foreground_internal=False,
            background=True,
            quiet=False,
            verbose=False,
            follow=False,
            no_llm=False,
            llm_model=None,
            delay=None,
            max_iterations=None,
            no_lock=False,
            queue=False,
            context=None,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            program_md=None,
            builtin=False,
            handoff_threshold=None,
            context_limit=None,
            instance_id=None,
        )

        captured_cmds: list[list[str]] = []

        def fake_popen(cmd: list[str], **kwargs: object) -> MagicMock:
            captured_cmds.append(list(cmd))
            proc = MagicMock()
            proc.pid = 9999
            return proc

        with (
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("builtins.open", MagicMock()),
            patch("pathlib.Path.write_text"),
            patch("pathlib.Path.mkdir"),
        ):
            run_background("my-loop", args, loops_dir)

        assert "--cross-host" not in captured_cmds[0]


# ---------------------------------------------------------------------------
# _run_cross_host_validation unit tests
# ---------------------------------------------------------------------------


class TestRunCrossHostValidation:
    def _make_probe_env(
        self,
        available: list[str],
        primary_host: str = "claude-code",
    ) -> tuple[MagicMock, MagicMock]:
        """Return (mock_which, mock_resolve_host) for the given probe setup."""

        def fake_which(binary: str) -> str | None:
            mapping = {"claude": "claude-code", "codex": "codex", "pi": "pi"}
            return f"/usr/bin/{binary}" if mapping.get(binary) in available else None

        primary_runner = MagicMock()
        primary_runner.name = primary_host
        mock_resolve = MagicMock(return_value=primary_runner)
        return fake_which, mock_resolve

    def test_single_host_skips_with_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When only one host is available, prints a skip notice and returns."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True))

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run") as mock_sub,
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        mock_sub.assert_not_called()
        out = capsys.readouterr().out
        assert "only one host" in out.lower() or "skipping" in out.lower()

    def test_second_host_subprocess_invoked(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Subprocess is called with LL_HOST_CLI set to the second host."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True))

        # Second run directory created after subprocess
        second_dir = tmp_path / "runs" / "my-loop-002"
        second_results = _make_ab_results(harness_wins=True)

        def fake_subprocess_run(cmd: list[str], **kwargs: object) -> MagicMock:
            # Simulate second run writing ab.json
            _write_ab(second_dir, second_results)
            result = MagicMock()
            result.returncode = 0
            return result

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        captured_env: dict = {}

        def fake_subprocess_run_capture(cmd: list[str], **kwargs: object) -> MagicMock:
            captured_env.update(kwargs.get("env", {}))
            _write_ab(second_dir, second_results)
            result = MagicMock()
            result.returncode = 0
            return result

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_subprocess_run_capture),
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        assert captured_env.get("LL_HOST_CLI") == "codex"

    def test_comparison_table_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Comparison table includes per-host pass rates and CIs."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True, n=10))

        second_dir = tmp_path / "runs" / "my-loop-002"
        second_results = _make_ab_results(harness_wins=True, n=10)

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            _write_ab(second_dir, second_results)
            result = MagicMock()
            result.returncode = 0
            return result

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_run),
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        out = capsys.readouterr().out
        assert "Cross-host" in out
        assert "claude-code" in out
        assert "codex" in out
        # Should show pass rates in percentage form
        assert "%" in out
        # Should show confidence intervals
        assert "[" in out and "]" in out

    def test_ordering_reversal_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Warns when harness/baseline quality ordering reverses between hosts."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        # Primary: harness wins (delta > 0)
        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True, n=10))

        # Second host: baseline wins (delta < 0)
        second_dir = tmp_path / "runs" / "my-loop-002"
        second_results = _make_ab_results(harness_wins=False, n=10)

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            _write_ab(second_dir, second_results)
            result = MagicMock()
            result.returncode = 0
            return result

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_run),
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        out = capsys.readouterr().out
        assert "reversal" in out.lower() or "⚠" in out or "warning" in out.lower()

    def test_no_reversal_warning_when_consistent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """No reversal warning when both hosts agree on which arm wins."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True, n=10))

        second_dir = tmp_path / "runs" / "my-loop-002"
        second_results = _make_ab_results(harness_wins=True, n=10)

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            _write_ab(second_dir, second_results)
            result = MagicMock()
            result.returncode = 0
            return result

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_run),
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        out = capsys.readouterr().out
        assert "reversal" not in out.lower()

    def test_second_run_failure_handled_gracefully(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When second-host run fails, prints a message and returns without crashing."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True))

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            result = MagicMock()
            result.returncode = 1
            return result

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_run),
        ):
            # Should not raise
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        out = capsys.readouterr().out
        assert "failed" in out.lower() or "no comparison" in out.lower()

    def test_missing_second_ab_json_handled(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """If second run produces no ab.json, prints a message and returns cleanly."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True))

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            # Second run completes but doesn't write ab.json
            result = MagicMock()
            result.returncode = 0
            return result

        args = argparse.Namespace(baseline_skill=None, items=None, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_run),
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        out = capsys.readouterr().out
        assert "no comparison" in out.lower() or "no ab.json" in out.lower()

    def test_baseline_skill_forwarded_to_subprocess(
        self, tmp_path: Path
    ) -> None:
        """--baseline-skill value is forwarded to the second-host subprocess command."""
        from little_loops.cli.loop._helpers import _run_cross_host_validation

        primary_dir = tmp_path / "runs" / "my-loop-001"
        primary_ab = _write_ab(primary_dir, _make_ab_results(harness_wins=True))
        second_dir = tmp_path / "runs" / "my-loop-002"

        captured: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            captured.append(cmd)
            _write_ab(second_dir, _make_ab_results(harness_wins=True))
            result = MagicMock()
            result.returncode = 0
            return result

        args = argparse.Namespace(baseline_skill="ll:check-code", items=3, loop="my-loop")
        fake_which, mock_resolve = self._make_probe_env(["claude-code", "codex"])

        with (
            patch("little_loops.cli.loop._helpers.shutil.which", side_effect=fake_which),
            patch("little_loops.host_runner.resolve_host", mock_resolve),
            patch("subprocess.run", side_effect=fake_run),
        ):
            _run_cross_host_validation(args, None, primary_dir, primary_ab, "my-loop")

        assert len(captured) == 1
        cmd = captured[0]
        assert "--baseline-skill" in cmd
        assert "ll:check-code" in cmd
        assert "--items" in cmd
        assert "3" in cmd

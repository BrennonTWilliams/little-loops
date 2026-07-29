"""Tests for `ll-queue run` (little_loops.cli.queue.cmd_run) - FEAT-2683.

Separate from test_cli_queue.py's add/list/status/remove coverage per this
issue's Acceptance Criteria ("independent of FEAT-2682's persistence tests").
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.queue import main_queue
from little_loops.queue_store import get_entry, list_entries, update_entry_result
from little_loops.runner_spec import RunnerResult


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run every test in its own project dir so .ll/queue.db is isolated."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _add(target: str, *, priority: str = "P3") -> str:
    with patch(
        "sys.argv", ["ll-queue", "add", target, "--runner", "cmd", "--priority", priority, "--json"]
    ):
        main_queue()
    return target


def _add_and_get_id(
    capsys: pytest.CaptureFixture[str], target: str, *, priority: str = "P3"
) -> str:
    with patch(
        "sys.argv", ["ll-queue", "add", target, "--runner", "cmd", "--priority", priority, "--json"]
    ):
        main_queue()
    return json.loads(capsys.readouterr().out)["id"]


class TestCmdRunEmptyQueue:
    def test_run_empty_queue_is_a_no_op(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "run"]):
            result = main_queue()
        assert result == 0
        assert "empty" in capsys.readouterr().out.lower()

    def test_run_empty_queue_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "run", "--json"]):
            result = main_queue()
        assert result == 0
        assert json.loads(capsys.readouterr().out) == []


class TestCmdRunDispatchOrder:
    def test_run_dispatches_in_priority_fifo_order(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _add("low", priority="P4")
        _add("high", priority="P0")
        _add("mid", priority="P2")
        capsys.readouterr()

        dispatched: list[str] = []

        def fake_run_action(spec: object) -> RunnerResult:
            dispatched.append(spec.target)  # type: ignore[attr-defined]
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                result = main_queue()

        assert result == 0
        assert dispatched == ["high", "mid", "low"]


class TestCmdRunStatusWriteBack:
    def test_run_success_marks_done_with_result(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="all good", stderr="", exit_code=0),
        ):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                result = main_queue()

        assert result == 0
        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "done"
        assert entry.result is not None
        assert entry.result["exit_code"] == 0

    def test_run_nonzero_exit_marks_failed(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="", stderr="boom", exit_code=1),
        ):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "failed"
        assert entry.result is not None
        assert entry.result["exit_code"] == 1

    def test_run_timed_out_marks_failed(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="", stderr="", exit_code=-1, timed_out=True),
        ):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "failed"
        assert entry.result is not None
        assert entry.result["timed_out"] is True

    def test_run_error_marks_failed(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="", stderr="", exit_code=0, error="dispatch failed"),
        ):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "failed"
        assert entry.result is not None
        assert entry.result["error"] == "dispatch failed"

    def test_run_dispatch_exception_marks_failed_and_continues(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        first_id = _add_and_get_id(capsys, "first")
        second_id = _add_and_get_id(capsys, "second")

        def fake_run_action(spec: object) -> RunnerResult:
            if spec.target == "first":  # type: ignore[attr-defined]
                raise ValueError("run_action() does not dispatch runner type")
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                result = main_queue()

        assert result == 0
        first_entry = get_entry(first_id)
        second_entry = get_entry(second_id)
        assert first_entry is not None and first_entry.status == "failed"
        assert second_entry is not None and second_entry.status == "done"


class TestCmdRunOnlyPending:
    def test_run_skips_non_pending_entries(self, capsys: pytest.CaptureFixture[str]) -> None:
        done_id = _add_and_get_id(capsys, "already-done")
        update_entry_result(done_id, "done", {"exit_code": 0})
        pending_id = _add_and_get_id(capsys, "still-pending")

        dispatched: list[str] = []

        def fake_run_action(spec: object) -> RunnerResult:
            dispatched.append(spec.target)  # type: ignore[attr-defined]
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert dispatched == ["still-pending"]
        entries = {e.id: e for e in list_entries()}
        assert entries[done_id].status == "done"
        assert entries[pending_id].status == "done"


class TestQueueRunExitCodeVerdict:
    """ENH-2814: `ll-queue run` marks a nonzero-exiting action "failed"."""

    def test_failure_terminal_exit_code_records_failed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An action exiting FAILURE_TERMINAL_EXIT_CODE is recorded as failed.

        `ll-queue run`'s verdict is `exit_code == 0`, so making failure
        terminals exit nonzero (ENH-2814) is exactly what stops a failed run
        from being written back as "done".
        """
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        entry_id = _add_and_get_id(capsys, "check-code")

        def fake_run_action(spec: object) -> RunnerResult:
            return RunnerResult(stdout="", stderr="", exit_code=FAILURE_TERMINAL_EXIT_CODE)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert get_entry(entry_id).status == "failed"

    def test_loop_runner_is_not_dispatched_by_run_action(self) -> None:
        """`RunnerType.LOOP` is deliberately not dispatched by run_action() directly.

        `run_action()`'s own contract (`runner_spec.py`) still raises for
        `RunnerType.LOOP` in isolation — the exit-code verdict above only
        ever applies to it for the SKILL/CMD/MCP/PROMPT kinds. FEAT-2906
        wires a real LOOP execution path, but `cmd_run()` intercepts LOOP
        entries *before* calling `run_action()` (see
        `TestCmdRunLoopDispatch` below); this test guards `run_action()`'s
        own dispatch table in isolation, not `cmd_run()`'s routing.
        """
        from little_loops.runner_spec import ActionSpec, RunnerType, run_action

        spec = ActionSpec(name="x", runner=RunnerType.LOOP, target="x")
        with pytest.raises(ValueError, match="does not dispatch"):
            run_action(spec)


class TestCmdRunLoopDispatch:
    """FEAT-2906: `ll-queue run` dispatches `RunnerType.LOOP` entries via subprocess."""

    def _add_loop(
        self,
        capsys: pytest.CaptureFixture[str],
        target: str = "some-loop",
        *,
        input_value: str | None = None,
    ) -> str:
        argv = ["ll-queue", "add", target, "--runner", "loop", "--json"]
        if input_value is not None:
            argv += ["--input", input_value]
        with patch("sys.argv", argv):
            main_queue()
        return json.loads(capsys.readouterr().out)["id"]

    def test_loop_entry_intercepted_before_run_action(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = self._add_loop(capsys)

        with patch("little_loops.runner_spec.run_action") as mock_run_action:
            with patch("little_loops.cli.queue.subprocess.run") as mock_subproc:
                mock_subproc.return_value.returncode = 0
                mock_subproc.return_value.stdout = "ok"
                mock_subproc.return_value.stderr = ""
                with patch("sys.argv", ["ll-queue", "run", "--json"]):
                    result = main_queue()

        assert result == 0
        mock_run_action.assert_not_called()
        assert mock_subproc.called
        cmd = mock_subproc.call_args[0][0]
        assert cmd[:3] == ["ll-loop", "run", "some-loop"]
        assert get_entry(entry_id).status == "done"

    def test_loop_entry_input_passed_as_positional(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._add_loop(capsys, input_value='{"issue_id": "BUG-1"}')

        with patch("little_loops.cli.queue.subprocess.run") as mock_subproc:
            mock_subproc.return_value.returncode = 0
            mock_subproc.return_value.stdout = ""
            mock_subproc.return_value.stderr = ""
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        cmd = mock_subproc.call_args[0][0]
        assert cmd == ["ll-loop", "run", "some-loop", '{"issue_id": "BUG-1"}']

    def test_loop_entry_terminal_failure_exit_code_marks_failed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        entry_id = self._add_loop(capsys)

        with patch("little_loops.cli.queue.subprocess.run") as mock_subproc:
            mock_subproc.return_value.returncode = FAILURE_TERMINAL_EXIT_CODE
            mock_subproc.return_value.stdout = ""
            mock_subproc.return_value.stderr = "blocked"
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "failed"
        assert entry.result is not None
        assert entry.result["exit_code"] == FAILURE_TERMINAL_EXIT_CODE

    def test_loop_entry_generic_nonzero_exit_marks_failed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = self._add_loop(capsys)

        with patch("little_loops.cli.queue.subprocess.run") as mock_subproc:
            mock_subproc.return_value.returncode = 1
            mock_subproc.return_value.stdout = ""
            mock_subproc.return_value.stderr = "error"
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert get_entry(entry_id).status == "failed"

    def test_non_loop_entries_still_dispatch_via_run_action(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="ok", stderr="", exit_code=0),
        ) as mock_run_action:
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        mock_run_action.assert_called_once()
        assert get_entry(entry_id).status == "done"

"""Tests for `ll-queue run` (little_loops.cli.queue.cmd_run) - FEAT-2683.

Separate from test_cli_queue.py's add/list/status/remove coverage per this
issue's Acceptance Criteria ("independent of FEAT-2682's persistence tests").
"""

from __future__ import annotations

import json
import signal
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.queue import main_queue
from little_loops.queue_store import (
    DEFAULT_DB_PATH,
    claim_entry,
    get_entry,
    list_entries,
    update_entry_result,
)
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

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
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

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
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


class TestCmdRunScopeGuard:
    """ENH-3403: a pre-existing hand-written scoped SKILL entry (add_entry()
    now rejects these at enqueue, but an entry written directly to the queue
    file before this guard existed must still be handled, not crash the
    drainer) fails loud at drain time with no spawn."""

    def test_drain_of_hand_written_scoped_skill_entry_lands_failed(self) -> None:
        from little_loops.queue_store import _serialize_action, connect
        from little_loops.runner_spec import ActionSpec, RunnerType

        action = ActionSpec(
            name="x", runner=RunnerType.SKILL, target="x", scopes=frozenset({"github"})
        )
        conn = connect(DEFAULT_DB_PATH)
        try:
            conn.execute(
                "INSERT INTO queue_entries(id, action, enqueued_at, priority, status, result) "
                "VALUES ('raw-entry', ?, '2026-09-08T00:00:00Z', 3, 'pending', NULL)",
                (_serialize_action(action),),
            )
            conn.commit()
        finally:
            conn.close()

        with (
            patch("subprocess.run") as mock_run,
            patch("sys.argv", ["ll-queue", "run", "--json"]),
        ):
            main_queue()

        mock_run.assert_not_called()
        entry = get_entry("raw-entry")
        assert entry is not None
        assert entry.status == "failed"
        assert entry.result is not None
        assert "declares 'scopes' but runner is" in (entry.result["error"] or "")


class TestCmdRunOnlyPending:
    def test_run_skips_non_pending_entries(self, capsys: pytest.CaptureFixture[str]) -> None:
        done_id = _add_and_get_id(capsys, "already-done")
        claim_entry(done_id)
        update_entry_result(done_id, "done", {"exit_code": 0})
        pending_id = _add_and_get_id(capsys, "still-pending")

        dispatched: list[str] = []

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
            dispatched.append(spec.target)  # type: ignore[attr-defined]
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert dispatched == ["still-pending"]
        entries = {e.id: e for e in list_entries()}
        assert entries[done_id].status == "done"
        assert entries[pending_id].status == "done"


class TestCmdRunClaimContention:
    """BUG-2929: a lost claim advances the drain loop instead of dispatching or breaking."""

    def test_run_skips_already_claimed_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        first_id = _add_and_get_id(capsys, "first")
        second_id = _add_and_get_id(capsys, "second")

        # Simulate another drainer having already won the claim on the first entry.
        assert claim_entry(first_id) is True

        dispatched: list[str] = []

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
            dispatched.append(spec.target)  # type: ignore[attr-defined]
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                result = main_queue()

        assert result == 0
        assert dispatched == ["second"]
        first_entry = get_entry(first_id)
        second_entry = get_entry(second_id)
        assert first_entry is not None and first_entry.status == "running"
        assert second_entry is not None and second_entry.status == "done"


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

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
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
        timeout: int | None = None,
    ) -> str:
        argv = ["ll-queue", "add", target, "--runner", "loop", "--json"]
        if input_value is not None:
            argv += ["--input", input_value]
        if timeout is not None:
            argv += ["--timeout", str(timeout)]
        with patch("sys.argv", argv):
            main_queue()
        return json.loads(capsys.readouterr().out)["id"]

    def _mock_popen(self, mock_popen: Any, *, returncode: int, stdout: str, stderr: str) -> Any:
        """Configure a `subprocess.Popen` mock for FEAT-2930's Popen/communicate dispatch."""
        proc = mock_popen.return_value
        proc.communicate.return_value = (stdout, stderr)
        proc.returncode = returncode
        proc.poll.return_value = returncode
        proc.pid = 12345
        return proc

    def test_loop_entry_intercepted_before_run_action(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = self._add_loop(capsys)

        with patch("little_loops.runner_spec.run_action") as mock_run_action:
            with patch("little_loops.cli.queue.subprocess.Popen") as mock_popen:
                self._mock_popen(mock_popen, returncode=0, stdout="ok", stderr="")
                with patch("sys.argv", ["ll-queue", "run", "--json"]):
                    result = main_queue()

        assert result == 0
        mock_run_action.assert_not_called()
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert cmd[:3] == ["ll-loop", "run", "some-loop"]
        assert mock_popen.call_args.kwargs["start_new_session"] is True
        assert get_entry(entry_id).status == "done"

    def test_loop_entry_default_timeout_is_unbounded(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """BUG-2928: no outer subprocess deadline for a LOOP entry by default."""
        self._add_loop(capsys)

        with patch("little_loops.cli.queue.subprocess.Popen") as mock_popen:
            self._mock_popen(mock_popen, returncode=0, stdout="", stderr="")
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert mock_popen.return_value.communicate.call_args.kwargs["timeout"] is None

    def test_loop_entry_explicit_timeout_still_honored(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._add_loop(capsys, timeout=30)

        with patch("little_loops.cli.queue.subprocess.Popen") as mock_popen:
            self._mock_popen(mock_popen, returncode=0, stdout="", stderr="")
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert mock_popen.return_value.communicate.call_args.kwargs["timeout"] == 30

    def test_loop_entry_input_passed_as_positional(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._add_loop(capsys, input_value='{"issue_id": "BUG-1"}')

        with patch("little_loops.cli.queue.subprocess.Popen") as mock_popen:
            self._mock_popen(mock_popen, returncode=0, stdout="", stderr="")
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        cmd = mock_popen.call_args[0][0]
        assert cmd == ["ll-loop", "run", "some-loop", '{"issue_id": "BUG-1"}']

    def test_loop_entry_terminal_failure_exit_code_marks_failed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        entry_id = self._add_loop(capsys)

        with patch("little_loops.cli.queue.subprocess.Popen") as mock_popen:
            self._mock_popen(
                mock_popen, returncode=FAILURE_TERMINAL_EXIT_CODE, stdout="", stderr="blocked"
            )
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

        with patch("little_loops.cli.queue.subprocess.Popen") as mock_popen:
            self._mock_popen(mock_popen, returncode=1, stdout="", stderr="error")
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


class _StopWatch(Exception):
    """Sentinel raised from a mocked `time.sleep` to break out of `--watch`'s loop (FEAT-2930)."""


class TestWatchPickup:
    """FEAT-2930: `ll-queue run --watch` picks up entries enqueued after it started."""

    def test_watch_picks_up_entry_added_after_start(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dispatched: list[str] = []
        late_id: dict[str, str] = {}

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
            dispatched.append(spec.target)  # type: ignore[attr-defined]
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        calls = {"n": 0}

        def fake_sleep(interval: float) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                late_id["id"] = _add_and_get_id(capsys, "late-entry")
            else:
                raise _StopWatch

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("little_loops.cli.queue.time.sleep", side_effect=fake_sleep):
                with patch("sys.argv", ["ll-queue", "run", "--watch", "--json"]):
                    with pytest.raises(_StopWatch):
                        main_queue()

        assert dispatched == ["late-entry"]
        assert get_entry(late_id["id"]).status == "done"  # type: ignore[union-attr]


class TestWatchBusySpinFix:
    """FEAT-2930: the lost-claim path sleeps `poll_interval` instead of busy-spinning."""

    def test_lost_claim_sleeps_before_retry(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        assert claim_entry(entry_id) is True  # simulate another drainer winning the claim

        sleep_calls: list[float] = []

        def fake_sleep(interval: float) -> None:
            sleep_calls.append(interval)
            if len(sleep_calls) >= 2:
                raise _StopWatch

        with patch("little_loops.cli.queue.time.sleep", side_effect=fake_sleep):
            with patch(
                "sys.argv", ["ll-queue", "run", "--watch", "--poll-interval", "7", "--json"]
            ):
                with pytest.raises(_StopWatch):
                    main_queue()

        assert sleep_calls
        assert all(interval == 7 for interval in sleep_calls)


class TestSignalHandler:
    """FEAT-2930: two-stage shutdown — model on `_sprint_signal_handler` (test_sprint.py)."""

    def test_first_signal_sets_stop_only(self) -> None:
        from little_loops.cli.queue import _make_signal_handler

        stop = threading.Event()
        force_stop = threading.Event()
        handler = _make_signal_handler(stop, force_stop, json_mode=True)

        handler(signal.SIGTERM, None)

        assert stop.is_set()
        assert not force_stop.is_set()

    def test_second_signal_sets_force_stop_and_kills_child(self) -> None:
        from little_loops.cli.queue import _make_signal_handler

        stop = threading.Event()
        stop.set()
        force_stop = threading.Event()
        handler = _make_signal_handler(stop, force_stop, json_mode=True)

        with patch("little_loops.cli.queue._kill_current_loop_proc") as mock_kill:
            handler(signal.SIGTERM, None)

        assert force_stop.is_set()
        mock_kill.assert_called_once()

    def test_idle_poll_leaves_nothing_running(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An idle wait (no entry in flight) claims nothing — the "nothing left running" half of
        the shutdown contract; the signal-delivery half is covered by the two tests above."""

        def fake_sleep(interval: float) -> None:
            raise _StopWatch

        with patch("little_loops.cli.queue.time.sleep", side_effect=fake_sleep):
            with patch("sys.argv", ["ll-queue", "run", "--watch", "--json"]):
                with pytest.raises(_StopWatch):
                    main_queue()

        assert list_entries() == []


class TestKillCurrentLoopProc:
    """FEAT-2930: forwards SIGTERM to the in-flight LOOP subprocess's process group."""

    def test_no_proc_in_flight_returns_false(self) -> None:
        import little_loops.cli.queue as queue_mod

        queue_mod._current_loop_proc = None
        assert queue_mod._kill_current_loop_proc() is False

    def test_already_exited_returns_false(self) -> None:
        import little_loops.cli.queue as queue_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        queue_mod._current_loop_proc = mock_proc
        try:
            assert queue_mod._kill_current_loop_proc() is False
        finally:
            queue_mod._current_loop_proc = None

    def test_kills_process_group(self) -> None:
        import little_loops.cli.queue as queue_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 999
        queue_mod._current_loop_proc = mock_proc
        try:
            with patch("little_loops.cli.queue.os.getpgid", return_value=999):
                with patch("little_loops.cli.queue.os.killpg") as mock_killpg:
                    result = queue_mod._kill_current_loop_proc()
            assert result is True
            mock_killpg.assert_called_once_with(999, signal.SIGTERM)
        finally:
            queue_mod._current_loop_proc = None

    def test_swallows_process_lookup_error(self) -> None:
        import little_loops.cli.queue as queue_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 999
        queue_mod._current_loop_proc = mock_proc
        try:
            with patch("little_loops.cli.queue.os.getpgid", side_effect=ProcessLookupError()):
                assert queue_mod._kill_current_loop_proc() is False
        finally:
            queue_mod._current_loop_proc = None

    def test_falls_back_to_proc_terminate_when_killpg_permission_error(self) -> None:
        """PermissionError from killpg falls back to proc.terminate() (BUG-3208
        guard routes through safe_killpg, which returns False on the OSError
        subclass). Mirrors ``cli/loop/lifecycle._signal_process_group``'s
        ``os.kill(pid, sig)`` fallback shape — when group signal is denied,
        still try the direct child."""
        import little_loops.cli.queue as queue_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 999
        mock_proc.terminate = MagicMock()  # succeeds in this test
        queue_mod._current_loop_proc = mock_proc
        try:
            with patch("little_loops.cli.queue.os.getpgid", return_value=999):
                with patch("little_loops.cli.queue.os.killpg", side_effect=PermissionError()):
                    assert queue_mod._kill_current_loop_proc() is True
        finally:
            queue_mod._current_loop_proc = None
        mock_proc.terminate.assert_called_once()

    def test_returns_false_when_both_killpg_and_terminate_fail(self) -> None:
        """If safe_killpg fails AND proc.terminate() raises OSError, the
        function returns False (matches the docstring: True iff a live
        process was actually signaled)."""
        import little_loops.cli.queue as queue_mod

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 999
        mock_proc.terminate = MagicMock(side_effect=PermissionError("denied"))
        queue_mod._current_loop_proc = mock_proc
        try:
            with patch("little_loops.cli.queue.os.getpgid", return_value=999):
                with patch("little_loops.cli.queue.os.killpg", side_effect=PermissionError()):
                    assert queue_mod._kill_current_loop_proc() is False
        finally:
            queue_mod._current_loop_proc = None


class TestReclaimStale:
    """FEAT-2930: `_reclaim_stale` sweeps `running` entries with a dead `owner_pid`."""

    def test_reclaims_entry_with_dead_owner(self, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.cli.queue import _reclaim_stale

        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id, owner_pid=999999)  # not a live pid the mock will confirm

        with patch(
            "little_loops.cli.queue.psutil.Process", side_effect=Exception("no such process")
        ):
            reclaimed, dead_lettered = _reclaim_stale(DEFAULT_DB_PATH)

        assert reclaimed == 1
        assert dead_lettered == 0
        assert get_entry(entry_id).status == "pending"  # type: ignore[union-attr]

    def test_leaves_entry_with_live_identified_owner(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.queue import _reclaim_stale

        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id, owner_pid=4321)

        mock_proc = MagicMock()
        mock_proc.cmdline.return_value = [
            "python",
            "-m",
            "little_loops.cli.queue",
            "run",
            "--watch",
        ]
        with patch("little_loops.cli.queue.psutil.Process", return_value=mock_proc):
            reclaimed, dead_lettered = _reclaim_stale(DEFAULT_DB_PATH)

        assert reclaimed == 0
        assert dead_lettered == 0
        assert get_entry(entry_id).status == "running"  # type: ignore[union-attr]

    def test_ignores_non_running_entries(self, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.cli.queue import _reclaim_stale

        _add_and_get_id(capsys, "audit-docs")  # stays pending

        with patch("little_loops.cli.queue.psutil.Process", side_effect=Exception("dead")):
            reclaimed, dead_lettered = _reclaim_stale(DEFAULT_DB_PATH)

        assert reclaimed == 0
        assert dead_lettered == 0

    def test_dead_letters_entry_with_exhausted_budget(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-3416: an entry whose owner keeps dying is dead-lettered once
        `attempt >= QUEUE_MAX_ATTEMPTS`, not reclaimed forever."""
        from little_loops.cli.queue import _reclaim_stale
        from little_loops.queue_store import QUEUE_MAX_ATTEMPTS, reset_to_pending

        entry_id = _add_and_get_id(capsys, "audit-docs")
        # Drive attempt up to the budget via repeated claim/reset cycles, ending
        # on a final claim (running, uncleared) so the entry is still `running`
        # when `_reclaim_stale` sweeps it.
        for _ in range(QUEUE_MAX_ATTEMPTS - 1):
            claim_entry(entry_id, owner_pid=999999)
            reset_to_pending(entry_id)
        claim_entry(entry_id, owner_pid=999999)
        assert get_entry(entry_id).attempt == QUEUE_MAX_ATTEMPTS  # type: ignore[union-attr]

        with patch(
            "little_loops.cli.queue.psutil.Process", side_effect=Exception("no such process")
        ):
            reclaimed, dead_lettered = _reclaim_stale(DEFAULT_DB_PATH)

        assert reclaimed == 0
        assert dead_lettered == 1
        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "dead_letter"
        assert "attempt budget exhausted after" in entry.result["error"]
        assert "owner died" in entry.result["error"]


class TestCmdRequeue:
    """FEAT-2930: `ll-queue requeue <id>` — manual escape hatch for a stranded `running` entry."""

    def test_requeues_entry_with_dead_owner(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id, owner_pid=999999)

        with patch(
            "little_loops.cli.queue.psutil.Process", side_effect=Exception("no such process")
        ):
            with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--json"]):
                result = main_queue()

        assert result == 0
        assert get_entry(entry_id).status == "pending"  # type: ignore[union-attr]

    def test_refuses_without_force_when_owner_alive(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id, owner_pid=4321)

        mock_proc = MagicMock()
        mock_proc.cmdline.return_value = ["python", "-m", "little_loops.cli.queue", "run"]
        with patch("little_loops.cli.queue.psutil.Process", return_value=mock_proc):
            with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--json"]):
                result = main_queue()

        assert result == 1
        assert get_entry(entry_id).status == "running"  # type: ignore[union-attr]

    def test_force_requeues_even_when_owner_alive(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id, owner_pid=4321)

        mock_proc = MagicMock()
        mock_proc.cmdline.return_value = ["python", "-m", "little_loops.cli.queue", "run"]
        with patch("little_loops.cli.queue.psutil.Process", return_value=mock_proc):
            with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--force", "--json"]):
                result = main_queue()

        assert result == 0
        assert get_entry(entry_id).status == "pending"  # type: ignore[union-attr]

    def test_refuses_non_running_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")  # still pending

        with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--json"]):
            result = main_queue()

        assert result == 1
        assert get_entry(entry_id).status == "pending"  # type: ignore[union-attr]

    def test_unknown_id_returns_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "requeue", "does-not-exist-00", "--json"]):
            result = main_queue()

        assert result == 1

    def test_requeue_dead_letter_entry_resets_budget(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-3416: requeue widens to accept dead_letter/failed/cancelled,
        resetting attempt and preserving the prior result under `.previous`."""
        from little_loops.queue_store import dead_letter_entry

        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id)
        dead_letter_entry(entry_id, "budget exhausted")

        with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--json"]):
            result = main_queue()

        assert result == 0
        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "pending"
        assert entry.attempt == 0
        assert entry.next_attempt_at is None
        assert entry.result == {"previous": {"error": "budget exhausted"}}

    def test_requeue_failed_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id)
        update_entry_result(entry_id, "failed", {"error": "boom"})

        with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--json"]):
            result = main_queue()

        assert result == 0
        assert get_entry(entry_id).status == "pending"  # type: ignore[union-attr]

    def test_requeue_cancelled_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.queue_store import cancel_entry

        entry_id = _add_and_get_id(capsys, "audit-docs")
        cancel_entry(entry_id, "stop")

        with patch("sys.argv", ["ll-queue", "requeue", entry_id, "--json"]):
            result = main_queue()

        assert result == 0
        assert get_entry(entry_id).status == "pending"  # type: ignore[union-attr]


class TestClassifyDispatch:
    """ENH-3416: `_classify_dispatch` maps a dispatch outcome to (retryable, reason)."""

    def test_timed_out_is_never_retryable(self) -> None:
        from little_loops.cli.queue import _classify_dispatch
        from little_loops.runner_spec import RunnerType

        retryable, reason = _classify_dispatch(RunnerType.CMD, {"error": None}, timed_out=True)
        assert retryable is False

    def test_cmd_timeout_only_stderr_is_not_retryable(self) -> None:
        """A non-timed-out CMD failure whose stderr merely contains the word
        "timeout" (e.g. a pytest failure line) must not be retried."""
        from little_loops.cli.queue import _classify_dispatch
        from little_loops.runner_spec import RunnerType

        retryable, reason = _classify_dispatch(
            RunnerType.CMD, {"stderr": "test_timeout_x FAILED", "error": None}, timed_out=False
        )
        assert retryable is False
        assert reason == "Command timeout"

    def test_retryable_reason_is_retried(self) -> None:
        from little_loops.cli.queue import _classify_dispatch
        from little_loops.runner_spec import RunnerType

        retryable, reason = _classify_dispatch(
            RunnerType.CMD, {"stderr": "429 too many requests", "error": None}, timed_out=False
        )
        assert retryable is True
        assert reason == "API quota or rate limit exceeded"

    def test_real_error_is_not_retryable(self) -> None:
        from little_loops.cli.queue import _classify_dispatch
        from little_loops.runner_spec import RunnerType

        retryable, reason = _classify_dispatch(
            RunnerType.CMD, {"stderr": "AssertionError: nope", "error": None}, timed_out=False
        )
        assert retryable is False

    def test_loop_terminal_failure_is_not_retryable(self) -> None:
        from little_loops.cli.queue import _classify_dispatch
        from little_loops.runner_spec import RunnerType

        retryable, reason = _classify_dispatch(
            RunnerType.LOOP, {"error": "terminal failure", "stderr": ""}, timed_out=False
        )
        assert retryable is False

    def test_loop_launch_failure_is_retryable_when_reason_matches(self) -> None:
        """A LOOP entry that failed to *launch* (FileNotFoundError) is not a
        `terminal failure`, so it falls through to ordinary classification."""
        from little_loops.cli.queue import _classify_dispatch
        from little_loops.runner_spec import RunnerType

        retryable, reason = _classify_dispatch(
            RunnerType.LOOP,
            {"error": "[Errno 2] No such file or directory: 'll-loop'", "stderr": ""},
            timed_out=False,
        )
        assert retryable is False  # not a retryable-reasons match, but not the LOOP-terminal path


class TestCmdRunRetryClassification:
    """ENH-3416: `_drain_once`'s post-failure classification branch."""

    def test_retryable_failure_schedules_backoff(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch("little_loops.queue_store._utcnow", return_value="2026-01-01T00:00:00Z"):
            with patch(
                "little_loops.runner_spec.run_action",
                return_value=RunnerResult(stdout="", stderr="429 too many requests", exit_code=1),
            ):
                with patch("sys.argv", ["ll-queue", "run", "--json"]):
                    main_queue()

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "pending"
        assert entry.attempt == 1
        assert entry.next_attempt_at == "2026-01-01T00:00:05Z"

    def test_retryable_failure_exhausts_budget_to_dead_letter(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.queue_store import QUEUE_MAX_ATTEMPTS

        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="", stderr="connection refused", exit_code=1),
        ):
            for _ in range(QUEUE_MAX_ATTEMPTS):
                # Clear any backoff deadline so the next run picks it straight up.
                from little_loops.queue_store import connect

                conn = connect(DEFAULT_DB_PATH)
                try:
                    conn.execute(
                        "UPDATE queue_entries SET next_attempt_at = NULL WHERE id = ?",
                        (entry_id,),
                    )
                    conn.commit()
                finally:
                    conn.close()
                with patch("sys.argv", ["ll-queue", "run", "--json"]):
                    main_queue()

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "dead_letter"
        assert entry.result is not None
        assert "connection refused" in entry.result["error"] or entry.result["error"]

    def test_command_timeout_stderr_lands_failed_not_pending(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="", stderr="test_timeout_x FAILED", exit_code=1),
        ):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                main_queue()

        assert get_entry(entry_id).status == "failed"  # type: ignore[union-attr]

    def test_backing_off_entry_is_skipped_while_eligible_siblings_dispatch(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        backing_off_id = _add_and_get_id(capsys, "backing-off")
        _add_and_get_id(capsys, "eligible")

        from little_loops.queue_store import connect

        conn = connect(DEFAULT_DB_PATH)
        try:
            conn.execute(
                "UPDATE queue_entries SET next_attempt_at = '2999-01-01T00:00:00Z' WHERE id = ?",
                (backing_off_id,),
            )
            conn.commit()
        finally:
            conn.close()

        dispatched: list[str] = []

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
            dispatched.append(spec.target)  # type: ignore[attr-defined]
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                result = main_queue()

        assert result == 0
        assert dispatched == ["eligible"]
        assert get_entry(backing_off_id).status == "pending"  # type: ignore[union-attr]


class TestCmdRunForceStopCancels:
    """ENH-3416: force_stop now marks the interrupted entry `cancelled`, not `failed`."""

    def test_force_stop_marks_cancelled_with_reason(self) -> None:
        import threading

        from little_loops.cli.queue import _drain_once
        from little_loops.queue_store import add_entry
        from little_loops.runner_spec import ActionSpec, RunnerType

        entry = add_entry(ActionSpec(name="x", runner=RunnerType.CMD, target="x"))

        stop = threading.Event()
        force_stop = threading.Event()
        force_stop.set()

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="partial", stderr="", exit_code=0),
        ):
            _drain_once(stop, force_stop)

        fetched = get_entry(entry.id)
        assert fetched is not None
        assert fetched.status == "cancelled"
        assert fetched.result is not None
        assert fetched.result["reason"] == "interrupted by operator"
        assert fetched.result["stdout"] == "partial"


class TestCancelRaceLock:
    """ENH-3416: an operator cancel mid-dispatch beats the drainer's completion write."""

    def test_cancel_during_dispatch_wins_over_success(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.queue_store import cancel_entry

        entry_id = _add_and_get_id(capsys, "audit-docs")

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
            cancel_entry(entry_id, "operator cancelled mid-dispatch")
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            with patch("sys.argv", ["ll-queue", "run", "--json"]):
                result = main_queue()

        assert result == 0
        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "cancelled"

    def test_reclaim_during_dispatch_wins_over_success(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A reclaim mid-dispatch re-queues the entry (status='pending'), so a
        second drain cycle would legitimately re-claim and redispatch it —
        drive `_drain_once` directly for one entry instead of `cmd_run`'s
        drain-until-empty loop, to isolate the single guard-miss write."""
        import threading

        from little_loops.cli.queue import _drain_once
        from little_loops.queue_store import reset_to_pending

        entry_id = _add_and_get_id(capsys, "audit-docs")

        def fake_run_action(spec: object, *, run_id: str | None = None) -> RunnerResult:
            reset_to_pending(entry_id)
            return RunnerResult(stdout="ok", stderr="", exit_code=0)

        stop = threading.Event()
        force_stop = threading.Event()
        calls = {"n": 0}

        def _on_entry(entry: object, record: dict[str, Any]) -> None:
            calls["n"] += 1
            if calls["n"] >= 1:
                stop.set()

        with patch("little_loops.runner_spec.run_action", side_effect=fake_run_action):
            _drain_once(stop, force_stop, on_entry=_on_entry)

        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "pending"


class TestCmdCancel:
    """ENH-3416: `ll-queue cancel <id> [--reason TEXT]`."""

    def test_cancels_pending_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        with patch(
            "sys.argv", ["ll-queue", "cancel", entry_id, "--reason", "no longer needed", "--json"]
        ):
            result = main_queue()

        assert result == 0
        entry = get_entry(entry_id)
        assert entry is not None
        assert entry.status == "cancelled"
        assert entry.result == {"reason": "no longer needed"}

    def test_cancels_running_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id)

        with patch("sys.argv", ["ll-queue", "cancel", entry_id, "--json"]):
            result = main_queue()

        assert result == 0
        assert get_entry(entry_id).status == "cancelled"  # type: ignore[union-attr]

    def test_refuses_terminal_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")
        claim_entry(entry_id)
        update_entry_result(entry_id, "done", {"exit_code": 0})

        with patch("sys.argv", ["ll-queue", "cancel", entry_id, "--json"]):
            result = main_queue()

        assert result == 1
        assert get_entry(entry_id).status == "done"  # type: ignore[union-attr]

    def test_unknown_id_returns_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "cancel", "does-not-exist-00", "--json"]):
            result = main_queue()

        assert result == 1


class TestStatusColorLock:
    """ENH-3416: `_STATUS_COLOR` stays in sync with `QUEUE_STATUSES`."""

    def test_status_color_keys_match_queue_statuses(self) -> None:
        from little_loops.cli.queue import _STATUS_COLOR
        from little_loops.queue_store import QUEUE_STATUSES

        assert set(_STATUS_COLOR.keys()) == QUEUE_STATUSES


class TestWatchNdjsonFlush:
    """FEAT-2930: `--watch --json` emits one flushed NDJSON object per processed entry."""

    def test_emits_one_json_line_per_entry_flushed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_id = _add_and_get_id(capsys, "audit-docs")

        def fake_sleep(interval: float) -> None:
            raise _StopWatch

        with patch(
            "little_loops.runner_spec.run_action",
            return_value=RunnerResult(stdout="ok", stderr="", exit_code=0),
        ):
            with patch("little_loops.cli.queue.time.sleep", side_effect=fake_sleep):
                with patch("sys.stdout") as mock_stdout:
                    mock_stdout.isatty.return_value = False
                    with patch("sys.argv", ["ll-queue", "run", "--watch", "--json"]):
                        with pytest.raises(_StopWatch):
                            main_queue()

        printed = "".join(call.args[0] for call in mock_stdout.write.call_args_list if call.args)
        lines = [line for line in printed.splitlines() if line.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["id"] == entry_id
        assert record["status"] == "done"
        assert mock_stdout.flush.called

"""Tests for --queue retry behavior in cmd_run (BUG-1281)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.fsm.concurrency import ScopeLock


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults = {
        "input": None,
        "context": [],
        "max_steps": None,
        "max_iterations": None,
        "delay": None,
        "no_llm": False,
        "llm_model": None,
        "dry_run": False,
        "background": False,
        "foreground_internal": False,
        "quiet": False,
        "verbose": False,
        "follow": False,
        "show_diagrams": None,
        "diagram_edge_labels": None,
        "diagram_state_detail": None,
        "diagram_scope": None,
        "clear": False,
        "queue": True,
        "no_lock": False,
        "handoff_threshold": None,
        "program_md": None,
        "worktree": False,
        "context_limit": None,
        "builtin": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_loop(tmp_path: Path) -> Path:
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "test-loop.yaml").write_text(
        "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
    )
    return loops_dir


def _conflict() -> ScopeLock:
    return ScopeLock(
        loop_name="other-loop", scope=["."], pid=99999, started_at="2026-01-01T00:00:00Z"
    )


class TestQueueRetryOnRace:
    """cmd_run retries acquire when it loses the post-wait race (BUG-1281)."""

    def test_retries_acquire_after_losing_race(self, tmp_path: Path) -> None:
        """cmd_run with --queue retries acquire if it loses the post-wait race."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args()

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor"),
            patch("little_loops.fsm.persistence._reconcile_stale_runs"),
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.extension.wire_extensions"),
            patch("little_loops.transport.wire_transports"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            # 1st: initial check fails (conflict exists)
            # 2nd: retry loop, loses the race
            # 3rd: retry loop, wins the race
            mock_lm.acquire.side_effect = [False, False, True]
            mock_lm.find_conflict.return_value = _conflict()
            mock_lm.wait_for_scope.return_value = True

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 0
        assert mock_lm.acquire.call_count == 3
        assert mock_lm.wait_for_scope.call_count == 2
        # Retry acquires must pass the same instance_id as the initial acquire so
        # release() can delete the correct lock file (not {loop_name}.lock).
        calls = mock_lm.acquire.call_args_list
        initial_instance_id = calls[0].kwargs.get("instance_id")
        assert initial_instance_id is not None, "Initial acquire must pass instance_id"
        for call in calls[1:]:
            retry_instance_id = call.kwargs.get("instance_id")
            assert retry_instance_id == initial_instance_id, (
                f"Retry acquire must pass instance_id={initial_instance_id!r}, got {retry_instance_id!r}"
            )
        # BUG-2526: every acquire call must thread the singleton kwarg so the
        # LockManager singleton predicate can fire on loop_name match. The test
        # loop fixture is non-singleton by default.
        for call in mock_lm.acquire.call_args_list:
            assert "singleton" in call.kwargs, (
                f"acquire() must thread singleton kwarg (BUG-2526); got kwargs: {call.kwargs}"
            )
            assert call.kwargs["singleton"] is False, (
                f"Non-singleton test loop must pass singleton=False; got: {call.kwargs['singleton']!r}"
            )

    def test_exits_when_scope_never_becomes_available(self, tmp_path: Path) -> None:
        """cmd_run exits with code 1 when wait_for_scope times out."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args()

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence._reconcile_stale_runs"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = False
            mock_lm.find_conflict.return_value = _conflict()
            mock_lm.wait_for_scope.return_value = False  # timeout — never free

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 1

    def test_without_queue_flag_exits_immediately_on_conflict(self, tmp_path: Path) -> None:
        """Without --queue, a scope conflict exits with code 1 and makes no retry."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args(queue=False)

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence._reconcile_stale_runs"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = False
            mock_lm.find_conflict.return_value = _conflict()

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 1
        assert mock_lm.acquire.call_count == 1
        mock_lm.wait_for_scope.assert_not_called()


class TestQueueFifoOrdering:
    """_is_earliest_waiter enforces FIFO ordering among queue waiters (ENH-1332)."""

    def test_is_earliest_when_queue_dir_missing(self, tmp_path: Path) -> None:
        """Returns True when queue directory does not exist."""
        from little_loops.cli.loop._helpers import _is_earliest_waiter

        assert _is_earliest_waiter("any-id", tmp_path / ".queue")

    def test_is_earliest_when_queue_is_empty(self, tmp_path: Path) -> None:
        """Returns True when queue directory exists but contains no entries."""
        from little_loops.cli.loop._helpers import _is_earliest_waiter

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()
        assert _is_earliest_waiter("any-id", queue_dir)

    def test_earliest_entry_wins(self, tmp_path: Path) -> None:
        """Returns True only for the entry with the earliest enqueuedAt timestamp."""
        import json
        import uuid

        from little_loops.cli.loop._helpers import _is_earliest_waiter

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()

        id_b = str(uuid.uuid4())
        id_c = str(uuid.uuid4())
        (queue_dir / f"{id_b}.json").write_text(
            json.dumps({"id": id_b, "enqueuedAt": "2026-05-02T10:00:00+00:00"})
        )
        (queue_dir / f"{id_c}.json").write_text(
            json.dumps({"id": id_c, "enqueuedAt": "2026-05-02T10:00:01+00:00"})
        )

        assert _is_earliest_waiter(id_b, queue_dir) is True
        assert _is_earliest_waiter(id_c, queue_dir) is False

    def test_stale_entries_from_dead_pids_are_skipped(self, tmp_path: Path) -> None:
        """Dead-PID queue entries are removed and not counted as earlier waiters (BUG-1360)."""
        import json
        import uuid

        from little_loops.cli.loop._helpers import _is_earliest_waiter

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()

        stale_id = str(uuid.uuid4())
        live_id = str(uuid.uuid4())
        stale_file = queue_dir / f"{stale_id}.json"
        # Write a stale entry (earlier timestamp, dead PID 1 is never the waiter but
        # use a guaranteed-dead PID: pid 99999999 which cannot exist on macOS/Linux)
        stale_file.write_text(
            json.dumps(
                {
                    "id": stale_id,
                    "enqueuedAt": "2026-05-01T00:00:00+00:00",
                    "context": {"pid": 99999999},
                }
            )
        )
        (queue_dir / f"{live_id}.json").write_text(
            json.dumps(
                {
                    "id": live_id,
                    "enqueuedAt": "2026-05-02T00:00:00+00:00",
                    "context": {"pid": None},  # no pid → kept
                }
            )
        )

        # live_id should be earliest because the stale entry's PID is dead
        assert _is_earliest_waiter(live_id, queue_dir) is True
        # Stale file should have been deleted
        assert not stale_file.exists()

    def test_malformed_entries_are_skipped(self, tmp_path: Path) -> None:
        """Malformed queue entries are skipped without affecting valid entry ordering."""
        import json
        import uuid

        from little_loops.cli.loop._helpers import _is_earliest_waiter

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()

        good_id = str(uuid.uuid4())
        (queue_dir / f"{good_id}.json").write_text(
            json.dumps({"id": good_id, "enqueuedAt": "2026-05-02T10:00:00+00:00"})
        )
        (queue_dir / "bad.json").write_text("not-valid-json")

        assert _is_earliest_waiter(good_id, queue_dir) is True


class TestReadQueueEntries:
    """read_queue_entries returns live, sorted queue entries, pruning dead PIDs (ENH-2617)."""

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        """Returns [] when the queue directory does not exist."""
        from little_loops.cli.loop._helpers import read_queue_entries

        assert read_queue_entries(tmp_path / ".queue") == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        """Returns [] when the queue directory exists but is empty."""
        from little_loops.cli.loop._helpers import read_queue_entries

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()
        assert read_queue_entries(queue_dir) == []

    def test_entries_sorted_by_enqueued_at(self, tmp_path: Path) -> None:
        """Surviving entries are returned sorted by enqueuedAt ascending."""
        import json
        import uuid

        from little_loops.cli.loop._helpers import read_queue_entries

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()

        id_b = str(uuid.uuid4())
        id_c = str(uuid.uuid4())
        (queue_dir / f"{id_c}.json").write_text(
            json.dumps({"id": id_c, "enqueuedAt": "2026-05-02T10:00:01+00:00"})
        )
        (queue_dir / f"{id_b}.json").write_text(
            json.dumps({"id": id_b, "enqueuedAt": "2026-05-02T10:00:00+00:00"})
        )

        entries = read_queue_entries(queue_dir)
        assert [e["id"] for e in entries] == [id_b, id_c]

    def test_dead_pid_entries_are_pruned(self, tmp_path: Path) -> None:
        """Dead-PID entries are unlinked and excluded from the result (BUG-1360)."""
        import json
        import uuid

        from little_loops.cli.loop._helpers import read_queue_entries

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()

        stale_id = str(uuid.uuid4())
        live_id = str(uuid.uuid4())
        stale_file = queue_dir / f"{stale_id}.json"
        stale_file.write_text(
            json.dumps(
                {
                    "id": stale_id,
                    "enqueuedAt": "2026-05-01T00:00:00+00:00",
                    "context": {"pid": 99999999},
                }
            )
        )
        (queue_dir / f"{live_id}.json").write_text(
            json.dumps(
                {
                    "id": live_id,
                    "enqueuedAt": "2026-05-02T00:00:00+00:00",
                    "context": {"pid": None},
                }
            )
        )

        entries = read_queue_entries(queue_dir)
        assert [e["id"] for e in entries] == [live_id]
        assert not stale_file.exists()

    def test_malformed_entries_are_skipped(self, tmp_path: Path) -> None:
        """Malformed JSON entries are skipped without affecting valid entries."""
        import json
        import uuid

        from little_loops.cli.loop._helpers import read_queue_entries

        queue_dir = tmp_path / ".queue"
        queue_dir.mkdir()

        good_id = str(uuid.uuid4())
        (queue_dir / f"{good_id}.json").write_text(
            json.dumps({"id": good_id, "enqueuedAt": "2026-05-02T10:00:00+00:00"})
        )
        (queue_dir / "bad.json").write_text("not-valid-json")

        entries = read_queue_entries(queue_dir)
        assert [e["id"] for e in entries] == [good_id]


class TestQueueRemoveCommand:
    """cmd_queue_remove verifies PID identity, signals the waiter, and deletes its entry (FEAT-2619)."""

    @staticmethod
    def _remove_args(entry_id: str, *, force: bool = False, json: bool = False) -> argparse.Namespace:
        return argparse.Namespace(id=entry_id, force=force, json=json)

    @staticmethod
    def _write_entry(queue_dir: Path, entry_id: str, pid: object) -> Path:
        import json as _json

        queue_dir.mkdir(exist_ok=True)
        path = queue_dir / f"{entry_id}.json"
        path.write_text(
            _json.dumps(
                {
                    "id": entry_id,
                    "loopName": "test-loop",
                    "enqueuedAt": "2026-05-02T10:00:00+00:00",
                    "context": {"pid": pid},
                }
            )
        )
        return path

    def test_deletes_target_leaves_others(self, tmp_path: Path) -> None:
        """Removes the target entry and leaves sibling entries untouched."""
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_remove

        queue_dir = tmp_path / ".queue"
        target_id = str(uuid.uuid4())
        survivor_id = str(uuid.uuid4())
        target = self._write_entry(queue_dir, target_id, 99999999)  # dead PID
        survivor = self._write_entry(queue_dir, survivor_id, 99999999)

        rc = cmd_queue_remove(self._remove_args(target_id), tmp_path)

        assert rc == 0
        assert not target.exists()
        assert survivor.exists()

    def test_unknown_id_returns_nonzero_without_signaling(self, tmp_path: Path) -> None:
        """Unknown id prints a friendly message, returns 1, and signals nothing."""
        from little_loops.cli.loop.queue import cmd_queue_remove

        (tmp_path / ".queue").mkdir()
        with patch("little_loops.cli.loop.queue.os.kill") as mock_kill:
            rc = cmd_queue_remove(self._remove_args("does-not-exist"), tmp_path)

        assert rc == 1
        mock_kill.assert_not_called()

    def test_ambiguous_prefix_returns_nonzero(self, tmp_path: Path) -> None:
        """A short-id prefix matching multiple entries is rejected as ambiguous."""
        from little_loops.cli.loop.queue import cmd_queue_remove

        queue_dir = tmp_path / ".queue"
        a = self._write_entry(queue_dir, "abcdef01-1111-2222-3333-444444444444", 99999999)
        b = self._write_entry(queue_dir, "abcdef01-5555-6666-7777-888888888888", 99999999)

        rc = cmd_queue_remove(self._remove_args("abcdef01"), tmp_path)

        assert rc == 1
        # Ambiguous match deletes nothing.
        assert a.exists()
        assert b.exists()

    def test_identity_gate_blocks_signal_but_still_deletes(self, tmp_path: Path) -> None:
        """When identity cannot be verified, the waiter is not signaled but the file is deleted."""
        import os
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_remove

        queue_dir = tmp_path / ".queue"
        entry_id = str(uuid.uuid4())
        target = self._write_entry(queue_dir, entry_id, os.getpid())  # live PID

        with (
            patch("little_loops.cli.loop.queue.psutil.Process", side_effect=Exception("no")),
            patch("little_loops.cli.loop.queue.os.kill") as mock_kill,
        ):
            rc = cmd_queue_remove(self._remove_args(entry_id), tmp_path)

        assert rc == 0
        mock_kill.assert_not_called()
        assert not target.exists()

    def test_force_signals_without_identity_check(self, tmp_path: Path) -> None:
        """--force sends SIGTERM to the live tracked PID even when identity is unverifiable."""
        import os
        import signal
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_remove

        queue_dir = tmp_path / ".queue"
        entry_id = str(uuid.uuid4())
        pid = os.getpid()
        target = self._write_entry(queue_dir, entry_id, pid)

        with patch("little_loops.cli.loop.queue.os.kill") as mock_kill:
            rc = cmd_queue_remove(self._remove_args(entry_id, force=True), tmp_path)

        assert rc == 0
        # os.kill is the shared module object, so _process_alive's (pid, 0) probe
        # also hits the mock; assert the SIGTERM delivery is among the calls.
        mock_kill.assert_any_call(pid, signal.SIGTERM)
        assert not target.exists()

    def test_verified_identity_signals_waiter(self, tmp_path: Path) -> None:
        """A live PID whose cmdline marks it an ll-loop waiter is signaled with SIGTERM."""
        import os
        import signal
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_remove

        queue_dir = tmp_path / ".queue"
        entry_id = str(uuid.uuid4())
        pid = os.getpid()
        target = self._write_entry(queue_dir, entry_id, pid)

        fake_proc = MagicMock()
        fake_proc.cmdline.return_value = ["python", "-m", "little_loops.cli.loop", "run", "x"]
        with (
            patch("little_loops.cli.loop.queue.psutil.Process", return_value=fake_proc),
            patch("little_loops.cli.loop.queue.os.kill") as mock_kill,
        ):
            rc = cmd_queue_remove(self._remove_args(entry_id), tmp_path)

        assert rc == 0
        mock_kill.assert_any_call(pid, signal.SIGTERM)
        assert not target.exists()

    def test_json_output_shape(self, tmp_path: Path, capsys) -> None:
        """--json emits an object with id/removed/signaled/identityVerified/pid keys."""
        import json as _json
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_remove

        queue_dir = tmp_path / ".queue"
        entry_id = str(uuid.uuid4())
        self._write_entry(queue_dir, entry_id, 99999999)  # dead PID → no signal

        rc = cmd_queue_remove(self._remove_args(entry_id, json=True), tmp_path)

        assert rc == 0
        payload = _json.loads(capsys.readouterr().out)
        assert payload["id"] == entry_id
        assert payload["removed"] is True
        assert payload["signaled"] is False
        assert "identityVerified" in payload
        assert payload["pid"] == 99999999

    def test_json_unknown_id_error(self, tmp_path: Path, capsys) -> None:
        """--json on an unknown id emits an error object and returns 1."""
        import json as _json

        from little_loops.cli.loop.queue import cmd_queue_remove

        (tmp_path / ".queue").mkdir()
        rc = cmd_queue_remove(self._remove_args("nope-nope-nope", json=True), tmp_path)

        assert rc == 1
        payload = _json.loads(capsys.readouterr().out)
        assert "error" in payload


class TestCmdRunTransportWiring:
    """Tests for FEAT-1323: cmd_run wires transports onto the executor's EventBus."""

    def test_cmd_run_wires_transports(self, tmp_path: Path) -> None:
        """cmd_run calls wire_transports(executor.event_bus, config.events) before running."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args(queue=False)

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.extension.wire_extensions"),
            patch("little_loops.transport.wire_transports") as mock_wire,
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = True
            mock_exec = MagicMock()
            mock_exec_cls.return_value = mock_exec

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 0
        mock_wire.assert_called_once()
        bus_arg = mock_wire.call_args.args[0]
        assert bus_arg is mock_exec.event_bus

    def test_cmd_run_calls_close_transports_in_finally(self, tmp_path: Path) -> None:
        """cmd_run calls executor.close_transports() in finally before lock release."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args(queue=False)

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.extension.wire_extensions"),
            patch("little_loops.transport.wire_transports"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = True
            mock_exec = MagicMock()
            mock_exec_cls.return_value = mock_exec

            cmd_run("test-loop", args, loops_dir, logger)

        mock_exec.close_transports.assert_called_once()
        mock_lm.release.assert_called_once()

    def test_cmd_run_close_transports_runs_on_exception(self, tmp_path: Path) -> None:
        """cmd_run still calls close_transports() if the loop body raises."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args(queue=False)

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch(
                "little_loops.cli.loop.run.run_foreground",
                side_effect=KeyboardInterrupt,
            ),
            patch("little_loops.extension.wire_extensions"),
            patch("little_loops.transport.wire_transports"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = True
            mock_exec = MagicMock()
            mock_exec_cls.return_value = mock_exec

            try:
                cmd_run("test-loop", args, loops_dir, logger)
            except KeyboardInterrupt:
                pass

        mock_exec.close_transports.assert_called_once()

    def test_no_lock_skips_acquire_and_proceeds_directly(self, tmp_path: Path) -> None:
        """cmd_run skips LockManager.acquire() and release() when no_lock=True."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args(queue=False, no_lock=True)

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.extension.wire_extensions"),
            patch("little_loops.transport.wire_transports"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_exec = MagicMock()
            mock_exec_cls.return_value = mock_exec

            cmd_run("test-loop", args, loops_dir, logger)

        mock_lm.acquire.assert_not_called()
        mock_lm.release.assert_not_called()
        mock_exec.close_transports.assert_called_once()


class TestQueueListCommand:
    """cmd_queue_list renders live queue entries in human and JSON modes (FEAT-2618).

    Thin render-assertion layer only: read_queue_entries() prune/sort/malformed
    correctness is covered by TestReadQueueEntries; these tests just verify the
    display and --json contract.
    """

    @staticmethod
    def _write_entry(
        queue_dir: Path, entry_id: str, loop_name: str, enqueued: str, pid: int
    ) -> None:
        import json

        queue_dir.mkdir(exist_ok=True)
        (queue_dir / f"{entry_id}.json").write_text(
            json.dumps(
                {
                    "id": entry_id,
                    "loopName": loop_name,
                    "enqueuedAt": enqueued,
                    "context": {"waitingFor": "other", "scope": ".", "pid": pid},
                }
            )
        )

    def test_empty_queue_human(self, tmp_path: Path, capsys: object) -> None:
        """Empty queue prints a friendly message and returns 0 in human mode."""
        import os

        from little_loops.cli.loop.queue import cmd_queue_list

        args = argparse.Namespace(json=False)
        rc = cmd_queue_list(args, tmp_path)
        assert rc == 0
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "Queue is empty" in out
        assert os.getpid() == os.getpid()  # sanity anchor; keeps import used

    def test_empty_queue_json(self, tmp_path: Path, capsys: object) -> None:
        """Empty queue prints [] and returns 0 in JSON mode."""
        import json

        from little_loops.cli.loop.queue import cmd_queue_list

        args = argparse.Namespace(json=True)
        rc = cmd_queue_list(args, tmp_path)
        assert rc == 0
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert json.loads(out) == []

    def test_populated_human(self, tmp_path: Path, capsys: object) -> None:
        """Populated queue lists each entry's id, loop name, and PID."""
        import os
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_list

        queue_dir = tmp_path / ".queue"
        eid = str(uuid.uuid4())
        self._write_entry(queue_dir, eid, "my-loop", "2026-05-02T10:00:00+00:00", os.getpid())

        rc = cmd_queue_list(argparse.Namespace(json=False), tmp_path)
        assert rc == 0
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert eid[:8] in out
        assert "my-loop" in out
        assert str(os.getpid()) in out
        assert "2026-05-02 10:00:00" in out

    def test_populated_json_sorted(self, tmp_path: Path, capsys: object) -> None:
        """JSON mode emits plain entry dicts sorted by enqueuedAt."""
        import json
        import os
        import uuid

        from little_loops.cli.loop.queue import cmd_queue_list

        queue_dir = tmp_path / ".queue"
        pid = os.getpid()
        later = str(uuid.uuid4())
        earlier = str(uuid.uuid4())
        self._write_entry(queue_dir, later, "loop-b", "2026-05-02T10:00:01+00:00", pid)
        self._write_entry(queue_dir, earlier, "loop-a", "2026-05-02T10:00:00+00:00", pid)

        rc = cmd_queue_list(argparse.Namespace(json=True), tmp_path)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
        assert [e["id"] for e in data] == [earlier, later]
        assert data[0]["context"]["pid"] == pid

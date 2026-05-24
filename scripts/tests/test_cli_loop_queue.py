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

"""End-to-end subprocess SIGINT integration test for ``ll-loop run``.

This module locks the user-visible contract surfaced by ENH-2514:
"kill a real ``ll-loop run`` subprocess and the audit trail survives."
The durability guarantee relies on two prior changes:

* ENH-2515 — per-event ``flush()`` + ``os.fsync()`` in
  ``StatePersistence._append_jsonl`` so every ``events.jsonl`` row is
  durable before the call returns.
* ENH-2516 — second-SIGINT branch in ``_loop_signal_handler`` calls
  ``PersistentExecutor.archive_run_only(terminated_by="interrupted_force")``
  before ``sys.exit(1)`` so the ``.history/<run_id>-<loop_name>/`` archive
  lands even when the executor has not yet exited its main loop.

The two tests below exercise both paths end-to-end via real
``subprocess.Popen`` + ``os.kill(pid, SIGINT)`` delivery — no mocking of
the signal handler, executor, or persistence layer. They are the contract
that future audits (e.g. ``/ll:audit-loop-run``) and incident post-mortems
(e.g. BUG-2501 autodev kill analysis) depend on.

See ENH-2517 for full design rationale.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

# BUG-2523: these tests spawn a real `ll-loop run` subprocess, deliver SIGINT,
# and wait on a hard `proc.wait(timeout=10.0)`. Under xdist worker contention
# the subprocess's signal handler can be starved past 10s, surfacing as
# `subprocess.TimeoutExpired`. `pytest_collection_modifyitems` in
# `scripts/tests/conftest.py` skips `no_parallel`-marked items on workers.
pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]


# ---------------------------------------------------------------------------
# Test fixtures & helpers
# ---------------------------------------------------------------------------

_LOOP_NAME = "sigint-test-loop"
# The FSM validator (scripts/little_loops/fsm/validation.py) requires at
# least one state with ``terminal: true``. The ``done`` state is unreachable
# from ``spin`` (which loops on itself), so the executor only terminates via
# SIGINT — exactly what we want. ``sleep 60`` keeps the action long enough
# that SIGINT almost always arrives while the child is still running,
# exercising the BUG-592/818 child-subprocess-kill path in the handler.
_SPIN_LOOP_YAML = """\
name: {name}
initial: spin
states:
  spin:
    action_type: shell
    action: "sleep 60"
    next: spin
  done:
    terminal: true
"""


def _build_loop(loops_dir: Path, loop_name: str) -> Path:
    """Write a minimal spin loop YAML under ``loops_dir``."""
    loops_dir.mkdir(parents=True, exist_ok=True)
    loop_file = loops_dir / f"{loop_name}.yaml"
    loop_file.write_text(_SPIN_LOOP_YAML.format(name=loop_name))
    return loop_file


def _spawn_loop(
    *,
    instance_id: str,
    cwd: Path,
    stdout: Any = subprocess.PIPE,
    stderr: Any = subprocess.PIPE,
) -> subprocess.Popen:
    """Spawn ``ll-loop run <loop> --foreground-internal --instance-id <id>``.

    ``--foreground-internal`` (consumed in
    ``scripts/little_loops/cli/loop/run.py:170-173, 311-313``) suppresses
    the child's own PID-file write and the log-file tee; the test owns the
    subprocess lifecycle.

    ``start_new_session=True`` places the child in its own process group so
    ``os.kill(pid, SIGINT)`` only targets the loop subprocess and not the
    pytest runner.

    ``--no-lock`` skips the scope-based LockManager so multiple tests can
    run concurrently against their own ``tmp_path`` without contention.
    """
    cmd = [
        sys.executable,
        "-m",
        "little_loops.cli.loop",
        "run",
        _LOOP_NAME,
        "--foreground-internal",
        "--instance-id",
        instance_id,
        "--no-llm",
        "--no-lock",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_for(predicate: Any, *, timeout: float, tick: float = 0.1) -> bool:
    """Poll ``predicate()`` until truthy or ``timeout`` expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(tick)
    return predicate()


def _terminate(proc: subprocess.Popen, *, timeout: float = 2.0) -> None:
    """Wait for clean exit; escalate to ``proc.kill()`` on timeout."""
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
    finally:
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass


def _running_events_path(loops_dir: Path, instance_id: str) -> Path:
    return loops_dir / ".running" / f"{instance_id}.events.jsonl"


def _running_state_path(loops_dir: Path, instance_id: str) -> Path:
    return loops_dir / ".running" / f"{instance_id}.state.json"


def _history_archives(loops_dir: Path) -> list[Path]:
    """Return ``.history/<run_id>-<loop_name>/`` directories (may be empty)."""
    history_dir = loops_dir / ".history"
    if not history_dir.exists():
        return []
    return [p for p in history_dir.iterdir() if p.is_dir()]


def _read_events(events_file: Path) -> list[dict[str, Any]]:
    """Read every JSONL row from ``events_file`` (empty list if missing)."""
    if not events_file.exists():
        return []
    return [json.loads(line) for line in events_file.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestSubprocessSignalIntegration:
    """End-to-end SIGINT contract for ``ll-loop run``.

    Each test spawns a real ``ll-loop run`` subprocess, delivers SIGINT,
    and asserts the audit trail (running state + .history/ archive)
    survives.
    """

    def test_sigint_archives_audit_trail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Single SIGINT → graceful shutdown → ``.history/<run_id>/`` archive.

        Exercises ENH-2515's per-event flush+fsync guarantee: every
        ``events.jsonl`` row appended before SIGINT delivery must be
        readable on disk. Also exercises ENH-2514's graceful path: the
        first Ctrl-C lets the executor exit its main loop, after which
        ``PersistentExecutor.run``'s post-block calls ``archive_run``.
        """
        monkeypatch.chdir(tmp_path)
        loops_dir = tmp_path / ".loops"
        _build_loop(loops_dir, _LOOP_NAME)

        instance_id = "sigint-single"
        proc = _spawn_loop(instance_id=instance_id, cwd=tmp_path)
        try:
            events_file = _running_events_path(loops_dir, instance_id)

            # Wait for loop_start to land in events.jsonl — proves the
            # executor is alive and the persistence layer is writing.
            assert _wait_for(
                lambda: events_file.exists() and "loop_start" in {
                    e.get("event") for e in _read_events(events_file)
                },
                timeout=10.0,
            ), "loop_start event never appeared in events.jsonl"

            # Deliver SIGINT and wait for clean exit.
            os.kill(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                pytest.fail("subprocess did not exit within 10s of SIGINT")

            # Graceful exit: returncode 0 (the FSM finished cleanly).
            assert proc.returncode == 0, (
                f"expected clean exit (0) on first SIGINT, got {proc.returncode}"
            )

            # Running state.json parses.
            state_file = _running_state_path(loops_dir, instance_id)
            assert state_file.exists(), f"missing {state_file}"
            state = json.loads(state_file.read_text())
            assert isinstance(state, dict)
            assert "status" in state, "state.json missing 'status' field"

            # events.jsonl still contains the loop_start row.
            events = _read_events(events_file)
            assert any(e.get("event") == "loop_start" for e in events), (
                "loop_start event lost after SIGINT"
            )

            # .history/<run_id>-<loop_name>/ archive exists with both files.
            archives = _history_archives(loops_dir)
            assert len(archives) >= 1, "no .history/<run_id>-<loop_name>/ archive created"
            archive = archives[0]
            assert (archive / "events.jsonl").exists(), (
                f"archive missing events.jsonl: {archive}"
            )
            assert (archive / "state.json").exists(), (
                f"archive missing state.json: {archive}"
            )

            # Archive contains at least one loop_start event.
            archived_events = _read_events(archive / "events.jsonl")
            assert any(e.get("event") == "loop_start" for e in archived_events), (
                f"archive missing loop_start event: {archive / 'events.jsonl'}"
            )
        finally:
            _terminate(proc)

    def test_second_signal_force_exit_archives(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Double SIGINT → ``sys.exit(1)`` but ``archive_run_only()`` still fires.

        Exercises ENH-2516's contract: the second-SIGINT branch in
        ``_loop_signal_handler`` calls
        ``PersistentExecutor.archive_run_only(terminated_by="interrupted_force")``
        wrapped in ``try/except OSError`` BEFORE ``sys.exit(1)``. Without
        ENH-2516 the archive would be skipped and this assertion would
        fail.
        """
        monkeypatch.chdir(tmp_path)
        loops_dir = tmp_path / ".loops"
        _build_loop(loops_dir, _LOOP_NAME)

        instance_id = "sigint-double"
        proc = _spawn_loop(instance_id=instance_id, cwd=tmp_path)
        try:
            events_file = _running_events_path(loops_dir, instance_id)

            # Wait for the loop to actually start before sending signals.
            assert _wait_for(
                lambda: events_file.exists() and "loop_start" in {
                    e.get("event") for e in _read_events(events_file)
                },
                timeout=10.0,
            ), "loop_start event never appeared in events.jsonl"

            # Send two signals of DIFFERENT types (SIGINT then SIGTERM) so
            # POSIX delivers both to the Python interpreter (duplicate
            # SIGINTs would be merged by the OS before the handler runs).
            # Both SIGINT and SIGTERM are registered to the same handler
            # (scripts/little_loops/cli/loop/_helpers.py:172-173), so
            # the first invocation flips ``_loop_shutdown_requested`` to
            # True and the second invocation hits the force-exit branch
            # that calls ``archive_run_only()`` before ``sys.exit(1)``.
            os.kill(proc.pid, signal.SIGINT)
            os.kill(proc.pid, signal.SIGTERM)

            try:
                proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "subprocess did not exit within 10s of double-SIGINT"
                )

            # Force-exit path: returncode 1 (from sys.exit(1) in handler).
            assert proc.returncode == 1, (
                f"expected force-exit code 1, got {proc.returncode}"
            )

            # CRITICAL: archive still lands despite the abrupt exit. This
            # is the ENH-2516 contract.
            archives = _history_archives(loops_dir)
            assert len(archives) >= 1, (
                "ENH-2516 contract violated: no .history/ archive after "
                "double-SIGINT force-exit"
            )
            archive = archives[0]
            assert (archive / "events.jsonl").exists(), (
                f"archive missing events.jsonl after force-exit: {archive}"
            )
            assert (archive / "state.json").exists(), (
                f"archive missing state.json after force-exit: {archive}"
            )

            # Running state.json still parses — proves archive_run_only
            # wrote the final state snapshot before sys.exit(1).
            state_file = _running_state_path(loops_dir, instance_id)
            assert state_file.exists(), (
                f"missing running state.json after force-exit: {state_file}"
            )
            state = json.loads(state_file.read_text())
            assert isinstance(state, dict)
        finally:
            _terminate(proc)

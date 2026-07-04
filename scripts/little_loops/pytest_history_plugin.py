"""Pytest plugin that records test-run results into ``.ll/history.db`` (ENH-2459).

Registered under the ``pytest11`` entry point (``scripts/pyproject.toml``) so
any pytest invocation in a little-loops project picks it up automatically.
The local suite is this project's only CI gate, so persisting per-run
pass/fail counts, duration, and failing test node IDs into
``test_run_events`` lets ``ll-history`` / ``ll-session`` answer "was the
suite green?" without a re-run, and supports flake/trend analysis.

Guard rails:

- **Opt-out**: set ``PYTEST_DISABLE_PLUGIN_LL_HISTORY=1`` (or use pytest's
  native ``-p no:ll_history``) to disable capture entirely.
- **Scoped**: capture only activates when the invocation directory already
  contains a ``.ll/`` directory or ``LL_HISTORY_DB`` is set — running pytest
  in an unrelated project never creates a history database there.
- **Best-effort**: the write is wrapped in ``contextlib.suppress(Exception)``
  per the EPIC-1707 graceful-degradation contract; a missing/locked database
  never fails a test run.
- **xdist-aware**: only the controller process (no ``workerinput``) records,
  so ``-n auto`` runs produce exactly one row.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ENV_OPT_OUT = "PYTEST_DISABLE_PLUGIN_LL_HISTORY"

# CI indicator environment variables, checked in order.
_CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "JENKINS_URL", "LL_AUTO_RUN")


def _capture_enabled() -> bool:
    """Return True when this run should be recorded into history.db."""
    if os.environ.get(_ENV_OPT_OUT):
        return False
    if os.environ.get("LL_HISTORY_DB"):
        return True
    return (Path.cwd() / ".ll").is_dir()


def _infer_env_label() -> str:
    """Classify the run environment: ``ci``, ``worktree``, or ``local``."""
    if any(os.environ.get(var) for var in _CI_ENV_VARS):
        return "ci"
    git_marker = Path.cwd() / ".git"
    # A linked git worktree has a .git *file* pointing at the parent repo.
    if git_marker.is_file():
        return "worktree"
    return "local"


def _git_output(*args: str) -> str | None:
    """Return stripped stdout of a git command, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class LLHistoryPlugin:
    """Collects per-test outcomes and writes one ``test_run_events`` row."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.started_at = _now_iso()
        self._start_monotonic = time.monotonic()
        self.passed = 0
        self.failed = 0
        self.errored = 0
        self.skipped = 0
        self.failing_names: list[str] = []

    # -- pytest hooks -------------------------------------------------------

    def pytest_sessionstart(self, session: Any) -> None:
        """Reset the wall clock at actual session start."""
        self.started_at = _now_iso()
        self._start_monotonic = time.monotonic()

    def pytest_runtest_logreport(self, report: Any) -> None:
        """Tally one test-phase report (controller receives these under xdist too)."""
        if report.when == "call":
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
                self.failing_names.append(report.nodeid)
            elif report.skipped:
                self.skipped += 1
        elif report.when in ("setup", "teardown"):
            if report.failed:
                self.errored += 1
                self.failing_names.append(report.nodeid)
            elif report.when == "setup" and report.skipped:
                self.skipped += 1

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        """Write the ``test_run_events`` row (best-effort, never raises)."""
        with contextlib.suppress(Exception):
            self._record()

    # -- internals ----------------------------------------------------------

    def _record(self) -> None:
        from little_loops.session_store import record_test_run_event, resolve_history_db

        duration_s = time.monotonic() - self._start_monotonic
        record_test_run_event(
            resolve_history_db(),
            ts=self.started_at,
            ended_at=_now_iso(),
            total=self.passed + self.failed + self.errored + self.skipped,
            passed=self.passed,
            failed=self.failed,
            errored=self.errored,
            skipped=self.skipped,
            duration_s=round(duration_s, 3),
            failing_names=self.failing_names[:100],
            env_label=_infer_env_label(),
            head_sha=_git_output("rev-parse", "HEAD"),
            branch=_git_output("rev-parse", "--abbrev-ref", "HEAD"),
            command=self.command[:500],
        )


def pytest_configure(config: Any) -> None:
    """Register the capture plugin on the xdist controller when enabled."""
    if hasattr(config, "workerinput"):  # xdist worker — controller records
        return
    if not _capture_enabled():
        return
    command = "pytest " + " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "pytest"
    config.pluginmanager.register(LLHistoryPlugin(command), "ll-history-capture")

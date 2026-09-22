"""Serial-invocation gate for the ``no_parallel`` marker (BUG-3523).

``pytest_collection_modifyitems`` in ``scripts/tests/conftest.py`` skips
``no_parallel``-marked tests on every xdist worker (BUG-2523); under the
default ``-n logical`` addopts the controller never runs a test body itself,
so a ``no_parallel`` test is otherwise collected then silently skipped
everywhere. This module is that missing serial invocation: an ordinary
(unmarked) test that shells out to a nested ``pytest -n 0`` run scoped to
the ``no_parallel`` set by marker, so it runs inside the same
``unit-tests`` CI job with no new workflow step and no hand-maintained file
list — any test newly decorated ``@pytest.mark.no_parallel`` is
automatically picked up.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest

# SSE fan-in test's own budget (180s) + the node conformance gate's
# effective budget (governed by the inner suite's --timeout=120, since that
# test carries no per-test marker) + ~30s startup/collection margin. A
# failure bound, not an expected runtime — see the BUG-3523 issue's
# Decision Rationale "Known trade-off" for the measured local baseline.
SERIAL_GATE_TIMEOUT = 330

_INNER_MARKER_EXPR = "no_parallel and not integration and not conformance"


class _Attempt(NamedTuple):
    ok: bool
    timed_out: bool
    returncode: int | None
    stdout: str
    stderr: str


def _kill_group_if_alive(proc: subprocess.Popen[str]) -> None:
    """Bounded, best-effort cleanup of ``proc``'s process group.

    ``start_new_session=True`` makes the leader's pid double as the process
    group id, so a two-stage TERM/KILL sweep here reaches descendants that
    outlive the leader (e.g. an inner pytest-timeout watchdog ``os._exit``s
    the leader but leaves a blocked grandchild alive). POSIX-only: group
    containment is not attempted on other platforms.
    """
    if os.name != "posix":
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def _run_inner_once(repo_root: Path, timeout: float) -> _Attempt:
    """Run the marker-selected inner suite once; never raises."""
    proc: subprocess.Popen[str] = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            "scripts/tests/",
            "-n",
            "0",
            "-m",
            _INNER_MARKER_EXPR,
            "-q",
            "-p",
            "no:randomly",
            "-p",
            "no:ll_history",
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group_if_alive(proc)
        stdout, stderr = proc.communicate()
    else:
        # A clean (or non-zero) leader exit can still leave descendants
        # alive in its process group.
        _kill_group_if_alive(proc)
    returncode = proc.returncode
    # Exit 5 = "no tests collected" (pytest's empty-selection code); accept
    # it as a pass so the wrapper degrades gracefully if the no_parallel
    # set is ever emptied, rather than failing on nothing to run.
    ok = (not timed_out) and returncode in (0, 5)
    return _Attempt(ok=ok, timed_out=timed_out, returncode=returncode, stdout=stdout, stderr=stderr)


def _serial_pass_with_retry(run_once: Callable[[], _Attempt], attempts: int = 2) -> list[_Attempt]:
    """Run ``run_once`` up to ``attempts`` times, stopping on the first pass."""
    results: list[_Attempt] = []
    for _ in range(attempts):
        attempt = run_once()
        results.append(attempt)
        if attempt.ok:
            break
    return results


@pytest.mark.timeout(2 * SERIAL_GATE_TIMEOUT + 30)
def test_no_parallel_serial_pass() -> None:
    """The ``no_parallel`` set, run for real, in CI (BUG-3523).

    Not itself marked ``no_parallel``/``integration``/``conformance``, so it
    runs normally under the outer ``-n logical`` suite. One bounded retry
    absorbs a transient contention timeout on the inner run (AC-W8); a
    recovered retry is reported via ``print`` so it lands in the uploaded
    JUnit artifact (``junit_logging = "system-out"`` captures passing-test
    stdout — see ``scripts/pyproject.toml``).
    """
    repo_root = Path(__file__).resolve().parents[2]
    attempts = _serial_pass_with_retry(lambda: _run_inner_once(repo_root, SERIAL_GATE_TIMEOUT))
    final = attempts[-1]
    if not final.ok:
        parts = []
        for i, attempt in enumerate(attempts, start=1):
            status = "timed out" if attempt.timed_out else f"exit {attempt.returncode}"
            parts.append(
                f"--- attempt {i} ({status}) ---\n"
                f"stdout tail:\n{attempt.stdout[-3000:]}\n"
                f"stderr tail:\n{attempt.stderr[-2000:]}"
            )
        pytest.fail(
            f"no_parallel serial gate failed after {len(attempts)} attempt(s):\n\n"
            + "\n\n".join(parts)
        )
    if len(attempts) > 1:
        first = attempts[0]
        status = "timed out" if first.timed_out else f"exit {first.returncode}"
        print(f"no_parallel serial gate recovered on retry (attempt 1 {status}; attempt 2 passed)")


def _fake_attempt(*, ok: bool, timed_out: bool = False, returncode: int | None = 0) -> _Attempt:
    return _Attempt(ok=ok, timed_out=timed_out, returncode=returncode, stdout="", stderr="")


class TestSerialPassWithRetry:
    """AC-W8: bounded retry across TimeoutExpired and non-zero/non-5 exits."""

    def test_first_attempt_success_no_retry(self) -> None:
        run_once = MagicMock(return_value=_fake_attempt(ok=True, returncode=0))

        results = _serial_pass_with_retry(run_once)

        assert len(results) == 1
        assert results[0].ok
        run_once.assert_called_once()

    def test_timeout_then_success_recovers(self) -> None:
        run_once = MagicMock(
            side_effect=[
                _fake_attempt(ok=False, timed_out=True, returncode=None),
                _fake_attempt(ok=True, returncode=0),
            ]
        )

        results = _serial_pass_with_retry(run_once)

        assert len(results) == 2
        assert results[0].timed_out and not results[0].ok
        assert results[1].ok

    def test_empty_selection_exit_5_is_a_pass(self) -> None:
        run_once = MagicMock(return_value=_fake_attempt(ok=True, returncode=5))

        results = _serial_pass_with_retry(run_once)

        assert len(results) == 1
        assert results[0].ok

    def test_two_failures_exhausts_retry_budget(self) -> None:
        run_once = MagicMock(
            side_effect=[
                _fake_attempt(ok=False, returncode=1),
                _fake_attempt(ok=False, returncode=1),
            ]
        )

        results = _serial_pass_with_retry(run_once)

        assert len(results) == 2
        assert not results[-1].ok
        assert run_once.call_count == 2  # bounded: no third attempt


@pytest.mark.skipif(os.name != "posix", reason="process-group containment is POSIX-only")
class TestKillGroupIfAlive:
    """AC-W11: bounded process-group cleanup must reap surviving descendants."""

    def test_kills_grandchild_in_same_group(self, tmp_path: Path) -> None:
        pidfile = tmp_path / "grandchild.pid"
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import subprocess, sys, time\n"
                    "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                    f"open({str(pidfile)!r}, 'w').write(str(gc.pid))\n"
                    "time.sleep(60)\n"
                ),
            ],
            text=True,
            start_new_session=True,
        )
        try:
            for _ in range(50):
                if pidfile.exists() and pidfile.read_text():
                    break
                time.sleep(0.1)
            else:
                pytest.fail("grandchild never reported its pid")
            grandchild_pid = int(pidfile.read_text())

            _kill_group_if_alive(proc)

            with pytest.raises(ProcessLookupError):
                os.kill(grandchild_pid, 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

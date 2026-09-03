"""ll-loop signal handling: SIGINT/SIGTERM graceful shutdown and SIGWINCH redraw.

Relocated from ``cli/loop/_helpers.py`` (ENH-2776). The module globals moved
together with their handlers — ``run_foreground`` (``cli/loop/_helpers.py``)
and ``StateFeedRenderer`` (``cli/loop/feed.py``) read/write them by module
attribute, not by value import, so mutation stays visible across modules.
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Any

from little_loops.cli.output import colorize

# Module-level shutdown state for signal handling
_loop_shutdown_requested: bool = False
_loop_executor: Any = None
_loop_pid_file: Path | None = None
_loop_marker_path: Path | None = None  # ENH-2522: user-stop.marker sentinel location
_using_alt_screen: bool = False
# Set by SIGWINCH handler when the terminal is resized; consumed by the
# display_progress callback to trigger a pinned-pane redraw on the next event.
_needs_redraw: bool = False
# Previous SIGWINCH handler, stashed when we install our own so it can be
# restored in run_foreground's finally block. ``None`` means "not installed".
_original_sigwinch: Any = None


def _loop_signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully for ll-loop.

    First signal: Set shutdown flag for graceful exit after current state.
    Second signal: Force immediate exit (after archiving the current run,
    ENH-2516).
    """
    global _loop_shutdown_requested, _using_alt_screen
    if _loop_shutdown_requested:
        # Second signal - force exit
        if _loop_pid_file is not None:
            _loop_pid_file.unlink(missing_ok=True)
        if _using_alt_screen:
            # Reset the DECSTBM scroll region BEFORE exiting the alt screen,
            # otherwise the main buffer is left with a restricted scroll
            # region — visible to the user as `seq 1 50` failing to scroll
            # past the previous pinned-pane height.
            print("\033[r", end="", file=sys.stderr, flush=True)
            print("\033[?1049l", end="", file=sys.stderr, flush=True)
        print(colorize("\nForce shutdown requested", "38;5;208"), file=sys.stderr)
        # ENH-2516: archive the current run before sys.exit so the audit trail
        # survives a forced exit (mirrors the first-SIGINT graceful path and
        # cmd_stop's precedent at lifecycle.py:316-375). OSError is swallowed
        # — a failed archive must not prevent exit, which is the only way to
        # break out of a stuck run (defensive coding matches lifecycle.py:116).
        if _loop_executor is not None:
            try:
                _loop_executor.archive_run_only(terminated_by="interrupted_force")
            except OSError:
                pass
        sys.exit(1)
    _loop_shutdown_requested = True
    print(colorize("\nShutdown requested, will exit after current state...", "33"), file=sys.stderr)
    if _loop_executor is not None:
        # ENH-2522: mark on the executor that our own signal handler killed the
        # subprocess, so the finish helper can attribute exit_code=-9 to the
        # user signal (interrupted) rather than a kernel/OOM kill (system_signal).
        inner = getattr(_loop_executor, "_executor", None)
        if inner is not None:
            inner._signal_handler_killed_subproc = True
        _loop_executor.request_shutdown(marker_path=_loop_marker_path)
        # Kill any child subprocess currently blocking in the action runner
        if inner is not None:
            runner = getattr(inner, "action_runner", None)
            if runner is not None:
                proc = getattr(runner, "_current_process", None)
                if proc is not None:
                    proc.kill()
            # Also kill MCP subprocesses tracked directly on FSMExecutor (_run_subprocess path)
            fsm_proc = getattr(inner, "_current_process", None)
            if fsm_proc is not None:
                fsm_proc.kill()


def register_loop_signal_handlers(
    executor: Any,
    pid_file: Path | None = None,
    marker_path: Path | None = None,
) -> None:
    """Register SIGINT/SIGTERM handlers for graceful loop shutdown.

    Sets up signal handling so that Ctrl-C triggers a graceful shutdown
    (calls executor.request_shutdown()) rather than raising KeyboardInterrupt.
    A second Ctrl-C forces immediate exit with PID file cleanup.

    Args:
        executor: The PersistentExecutor instance to request shutdown on.
        pid_file: Optional path to PID file to clean up on forced exit.
        marker_path: Optional path to a user-stop.marker sentinel; if present
            when shutdown is requested, the executor will tag the run as
            ``user_stopped`` instead of ``interrupted`` (ENH-2522).
    """
    global _loop_shutdown_requested, _loop_executor, _loop_pid_file, _loop_marker_path
    _loop_shutdown_requested = False
    _loop_executor = executor
    _loop_pid_file = pid_file
    _loop_marker_path = marker_path
    signal.signal(signal.SIGINT, _loop_signal_handler)
    signal.signal(signal.SIGTERM, _loop_signal_handler)


# ---------------------------------------------------------------------------
# SIGWINCH handler (alt-screen pinned-pane mode only)
# ---------------------------------------------------------------------------


def _sigwinch_handler(signum: int, frame: FrameType | None) -> None:
    """Mark the pinned pane as needing a redraw after a terminal resize.

    The handler does the minimum amount of work safe to perform in a signal
    context: it just sets a flag. ``display_progress`` consumes the flag
    before processing the next FSM event and triggers the actual redraw.
    """
    global _needs_redraw
    _needs_redraw = True


def _install_sigwinch_handler() -> None:
    """Install ``_sigwinch_handler`` for SIGWINCH, stashing the prior handler.

    Idempotent — re-calling while installed is a no-op so we never leak the
    chain by overwriting our own stash. No-op on platforms without SIGWINCH
    (e.g. Windows).
    """
    global _original_sigwinch
    if not hasattr(signal, "SIGWINCH"):
        return
    if _original_sigwinch is not None:
        return
    _original_sigwinch = signal.signal(signal.SIGWINCH, _sigwinch_handler)


def _restore_sigwinch_handler() -> None:
    """Restore the SIGWINCH handler stashed by ``_install_sigwinch_handler``.

    Safe to call when no handler was installed. After this returns,
    ``_original_sigwinch`` is reset to ``None`` so the install is repeatable.
    """
    global _original_sigwinch, _needs_redraw
    if not hasattr(signal, "SIGWINCH"):
        _original_sigwinch = None
        _needs_redraw = False
        return
    if _original_sigwinch is None:
        return
    signal.signal(signal.SIGWINCH, _original_sigwinch)
    _original_sigwinch = None
    _needs_redraw = False

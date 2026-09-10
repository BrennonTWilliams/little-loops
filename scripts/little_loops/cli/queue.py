"""ll-queue: persisted queue-entry store — add/list/status/remove/run commands (FEAT-2682, FEAT-2683).

Operates on a dedicated ``.ll/queue.db`` (via :mod:`little_loops.queue_store`),
distinct from ``ll-loop queue``'s PID-liveness marker mechanism
(``cli/loop/queue.py``), which FEAT-2684 preserves unchanged as a compat
shim rather than migrating.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil

from little_loops.queue_store import DEFAULT_DB_PATH as QUEUE_DB_PATH
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context
from little_loops.subprocess_utils import safe_killpg

if TYPE_CHECKING:
    from collections.abc import Callable

    from little_loops.queue_store import QueueEntry
    from little_loops.runner_spec import ActionSpec, RunnerType

# Default --poll-interval, in seconds, for `ll-queue run --watch` (FEAT-2930):
# a sleep-poll, not a busy loop. Also the sleep applied to the lost-claim
# retry path (below), which the one-shot drainer hits only in the rare case
# of a second, concurrent drainer.
_DEFAULT_POLL_INTERVAL = 3.0

# The in-flight LOOP entry's subprocess (FEAT-2930), tracked at module scope
# so the second-signal handler in `_run_watch` can forward SIGTERM to it. A
# LOOP entry's subprocess.run/Popen call does not inherit the parent's
# signals (BUG-2928 removed its outer timeout, making this the only way to
# stop a wedged loop short of killing the whole drainer).
_current_loop_proc: subprocess.Popen[str] | None = None

__all__ = ["main_queue"]

_STATUS_COLOR: dict[str, str] = {
    "pending": "33",
    "running": "36",
    "done": "32",
    "failed": "38;5;208",
    "dead_letter": "31",
    "cancelled": "2",
}

# Truncation budget for the args/timeout summary suffix (ENH-2931).
# Deliberately a constant, not shutil.get_terminal_size() — terminal
# detection makes row output environment-dependent, so assertions on it
# would pass or fail based on the harness's TTY width. --wide bypasses
# this constant rather than raising it.
_ARGS_SUMMARY_WIDTH = 40


def _format_action_summary(entry: Any, *, wide: bool = False) -> str:
    """Render ``runner:target`` plus an args/timeout/elapsed suffix (ENH-2931).

    Truncated to :data:`_ARGS_SUMMARY_WIDTH` unless *wide*. A stored
    ``ActionSpec.timeout`` of ``None`` unambiguously means "LOOP, no
    override" (see ``_classify_action``'s docstring) — rendered as
    ``timeout=∞`` rather than omitted, since "no timeout" is the fact an
    operator most needs to see post-BUG-2928.
    """
    from little_loops.cli.output import format_relative_time

    action: ActionSpec = entry.action
    base = f"{action.runner.value}:{action.target}"

    suffix_parts: list[str] = []
    loop_input = action.args.get("loop_input")
    if loop_input is not None:
        suffix_parts.append(f"input={loop_input}")
    timeout_str = "∞" if action.timeout is None else str(action.timeout)
    suffix_parts.append(f"timeout={timeout_str}")
    if entry.attempt:
        suffix_parts.append(f"attempt={entry.attempt}")
    if entry.next_attempt_at:
        try:
            next_dt = datetime.strptime(entry.next_attempt_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            remaining = (next_dt - datetime.now(UTC)).total_seconds()
        except ValueError:
            remaining = 0
        if remaining > 0:
            suffix_parts.append(f"retry in {int(remaining)}s")
    if entry.status == "running":
        elapsed = (
            datetime.now(UTC)
            - datetime.strptime(entry.enqueued_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        ).total_seconds()
        suffix_parts.append(f"queued {format_relative_time(elapsed)}")

    suffix = "  ".join(suffix_parts)
    if not wide and len(suffix) > _ARGS_SUMMARY_WIDTH:
        suffix = suffix[: _ARGS_SUMMARY_WIDTH - 1] + "…"

    return f"{base}  {suffix}"


def _default_timeout_for(runner: RunnerType) -> int | None:
    """Per-runner default subprocess timeout, in seconds (BUG-2928).

    A ``LOOP`` target already carries its own FSM budget stack (loop-level
    ``timeout:``, ``max_steps``, per-state/action timeouts), so it gets no
    outer subprocess deadline — a bound 240x shorter than a typical loop
    timeout only kills the child process before the executor's own
    termination path can flush state and write ``summary.json``. Every other
    runner has no internal budget of its own and keeps the 120s default.

    Must return a concrete ``int`` for ``CMD``/``MCP`` specifically: their
    dispatch handlers (``runner_spec._run_cmd``, ``mcp_call.call_mcp_tool``)
    do raw deadline arithmetic on ``timeout`` and raise ``TypeError`` on
    ``None``. Only ``SKILL``/``PROMPT``/``LOOP`` forward ``timeout`` straight
    to ``subprocess.run``, which tolerates ``None`` natively.
    """
    from little_loops.runner_spec import RunnerType

    if runner is RunnerType.LOOP:
        return None
    return 120


def _classify_action(
    target: str,
    *,
    runner_override: str | None,
    timeout: int | None,
    arg_pairs: list[str] | None,
    input_value: str | None = None,
) -> Any:
    """Normalize a bare *target* string into an :class:`ActionSpec` (FEAT-2682).

    With an explicit ``--runner``, the classification is skipped and *target*
    is used verbatim as that runner's target. Otherwise classifies in order:
    an FSM loop name (resolves via ``resolve_loop_path``), a skill/command
    name (resolves via ``skill_expander``'s ``skills/<name>/SKILL.md`` /
    ``commands/<name>.md`` lookup), or — the fallback — a raw CLI invocation.

    ``input_value`` (FEAT-2906's ``--input``) is stored verbatim under
    ``args["loop_input"]``, not re-interpreted here — ``ll-loop run``'s
    positional does its own ``json.loads``/context-key coercion against the
    loop's *loaded* FSM, which ``ll-queue add`` never loads.

    ``timeout`` of ``None`` means "no explicit ``--timeout``" — the per-runner
    default from :func:`_default_timeout_for` is resolved here, after the
    runner is known (BUG-2928). An explicit value always overrides.
    """
    from little_loops.config.core import BRConfig
    from little_loops.fsm.loop_paths import resolve_loop_path
    from little_loops.runner_spec import ActionSpec, RunnerType
    from little_loops.skill_expander import _find_plugin_root, _resolve_content_path

    args_dict: dict[str, str] = {}
    for pair in arg_pairs or []:
        if "=" not in pair:
            raise ValueError(f"--arg must be KEY=VALUE, got: {pair!r}")
        key, _, value = pair.partition("=")
        args_dict[key] = value
    if input_value is not None:
        args_dict["loop_input"] = input_value

    if runner_override is not None:
        runner = RunnerType(runner_override)
        resolved_timeout = timeout if timeout is not None else _default_timeout_for(runner)
        return ActionSpec(
            name=target, runner=runner, target=target, args=args_dict, timeout=resolved_timeout
        )

    loops_dir = Path(BRConfig(Path.cwd()).loops.loops_dir)
    try:
        resolve_loop_path(target, loops_dir)
        resolved_timeout = timeout if timeout is not None else _default_timeout_for(RunnerType.LOOP)
        return ActionSpec(
            name=target,
            runner=RunnerType.LOOP,
            target=target,
            args=args_dict,
            timeout=resolved_timeout,
        )
    except FileNotFoundError:
        pass

    plugin_root = _find_plugin_root()
    if _resolve_content_path(plugin_root, target) is not None:
        resolved_timeout = (
            timeout if timeout is not None else _default_timeout_for(RunnerType.SKILL)
        )
        return ActionSpec(
            name=target,
            runner=RunnerType.SKILL,
            target=target,
            args=args_dict,
            timeout=resolved_timeout,
        )

    resolved_timeout = timeout if timeout is not None else _default_timeout_for(RunnerType.CMD)
    return ActionSpec(
        name=target, runner=RunnerType.CMD, target=target, args=args_dict, timeout=resolved_timeout
    )


def cmd_add(args: argparse.Namespace) -> int:
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import add_entry

    try:
        spec = _classify_action(
            args.target,
            runner_override=args.runner,
            timeout=args.timeout,
            arg_pairs=args.arg,
            input_value=args.input,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    entry = add_entry(spec, args.priority, db_path=QUEUE_DB_PATH)

    if getattr(args, "json", False):
        print_json(entry.to_dict())
        return 0

    print(
        f"Queued {colorize(entry.id[:8], '34')}  "
        f"{entry.action.runner.value}:{entry.action.target}  "
        f"priority={entry.priority}"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import list_entries

    json_mode = getattr(args, "json", False)
    try:
        entries = list_entries(QUEUE_DB_PATH)
    except sqlite3.OperationalError as exc:
        msg = f"Could not read queue database {QUEUE_DB_PATH}: {exc}"
        if json_mode:
            print_json({"error": msg})
        else:
            print(msg, file=sys.stderr)
        return 1

    if json_mode:
        print_json([e.to_dict() for e in entries])
        return 0

    if not entries:
        print("Queue is empty")
        return 0

    wide = getattr(args, "wide", False)
    print(colorize(f"Queue entries ({len(entries)}):", "1"))
    print()
    for entry in entries:
        short_id = entry.id[:8]
        status_color = _STATUS_COLOR.get(entry.status, "0")
        print(
            f"  {colorize(short_id, '34')}  {colorize(entry.priority, '1')}  "
            f"{colorize(entry.status, status_color)}  "
            f"{_format_action_summary(entry, wide=wide)}  {entry.enqueued_at}"
        )
    return 0


def _not_found_or_ambiguous(args: argparse.Namespace) -> int | None:
    """Resolve ``args.id`` to an entry; print/return an error for 0 or >1 matches.

    Returns None (caller should proceed) if exactly one entry matched, on
    ``args._resolved_entry``. Returns an exit code (1) if it already handled
    the not-found / ambiguous case.
    """
    from little_loops.cli.output import print_json
    from little_loops.queue_store import AmbiguousEntryIdError, resolve_entry

    json_mode = getattr(args, "json", False)
    try:
        entry = resolve_entry(args.id, QUEUE_DB_PATH)
    except AmbiguousEntryIdError as exc:
        msg = str(exc)
        if json_mode:
            print_json({"error": msg, "id": args.id})
        else:
            print(msg, file=sys.stderr)
        return 1
    except sqlite3.OperationalError as exc:
        msg = f"Could not read queue database {QUEUE_DB_PATH}: {exc}"
        if json_mode:
            print_json({"error": msg, "id": args.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    if entry is None:
        msg = f"No queued entry with id '{args.id}'"
        if json_mode:
            print_json({"error": msg, "id": args.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    args._resolved_entry = entry
    return None


def cmd_status(args: argparse.Namespace) -> int:
    import json as _json

    from little_loops.cli.output import print_json, status_block

    code = _not_found_or_ambiguous(args)
    if code is not None:
        return code
    entry = args._resolved_entry

    if getattr(args, "json", False):
        print_json(entry.to_dict())
        return 0

    print(
        status_block(
            {
                "id": entry.id,
                "action": f"{entry.action.runner.value}:{entry.action.target}",
                "priority": entry.priority,
                "status": entry.status,
                "enqueuedAt": entry.enqueued_at,
                "attempt": entry.attempt,
                "nextAttemptAt": entry.next_attempt_at or "-",
                "reason": (entry.result or {}).get("reason") or "-",
                "error": (entry.result or {}).get("error") or "-",
                "result": _json.dumps(entry.result) if entry.result else "-",
            }
        )
    )
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import remove_entry

    code = _not_found_or_ambiguous(args)
    if code is not None:
        return code
    entry = args._resolved_entry
    json_mode = getattr(args, "json", False)

    if entry.status != "pending" and not getattr(args, "force", False):
        msg = f"Entry '{entry.id[:8]}' is {entry.status}, not pending; use --force to remove anyway"
        if json_mode:
            print_json({"error": msg, "id": entry.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    remove_entry(entry.id, QUEUE_DB_PATH)
    if json_mode:
        print_json({"removed": entry.id})
    else:
        print(f"Removed {colorize(entry.id[:8], '34')}")
    return 0


def _run_loop_entry(action: Any) -> Any:
    """Dispatch a ``RunnerType.LOOP`` entry via a subprocess ``ll-loop run`` shell-out.

    Mirrors the working precedent in ``worker_pool.py``/``cli/sprint/run.py``:
    process isolation sidesteps ``cmd_run_loop``'s process-global
    ``register_loop_signal_handlers``/worktree/``atexit`` setup, which is
    unsafe to invoke repeatedly within one ``ll-queue run`` process
    (FEAT-2906 Decision Rationale). ``args["loop_input"]`` (FEAT-2906's
    ``--input``) is passed through as the bare positional, matching
    ``cli/loop/next_loop.py:_build_command``'s construction pattern — the
    same coercion ``ll-loop run <loop> [input]`` already applies FSM-side.

    Launched with ``start_new_session=True`` (FEAT-2930) so the child is a
    process-group leader that ``_kill_current_loop_proc`` can target via
    ``os.killpg`` on a second shutdown signal, and tracked in the module-level
    ``_current_loop_proc`` for the duration of the call so that handler can
    find it.
    """
    global _current_loop_proc

    from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE
    from little_loops.runner_spec import RunnerResult

    cmd = ["ll-loop", "run", action.target]
    loop_input = action.args.get("loop_input")
    if loop_input is not None:
        cmd.append(loop_input)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return RunnerResult(stdout="", stderr="", exit_code=-1, error=str(exc))

    _current_loop_proc = proc
    try:
        stdout, stderr = proc.communicate(timeout=action.timeout)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return RunnerResult(stdout=stdout or "", stderr=stderr or "", exit_code=-1, timed_out=True)
    finally:
        _current_loop_proc = None

    error = "terminal failure" if returncode == FAILURE_TERMINAL_EXIT_CODE else None
    return RunnerResult(stdout=stdout, stderr=stderr, exit_code=returncode, error=error)


def _kill_current_loop_proc() -> bool:
    """Forward SIGTERM to the in-flight LOOP subprocess's process group, if any (FEAT-2930).

    Returns True iff a live process was actually signaled. Safe to call when
    no LOOP entry is in flight (returns False). Mirrors
    ``cli/loop/lifecycle.py``'s ``_kill_with_timeout``/``_signal_process_group``
    escalation shape, minus the SIGKILL escalation wait — the drainer exits
    right after this on a second signal rather than babysitting the kill.

    Routes through ``subprocess_utils.safe_killpg`` (BUG-3208 single guard)
    so the kill(-1, SIGTERM) broadcast trap is rejected here too: a
    ``MagicMock`` ``proc.pid`` resolves to ``getpgid(...) = 1``, and
    ``os.killpg(1, SIGTERM)`` is ``kill(-1, SIGTERM)`` — a same-UID
    broadcast that signals the drainer itself. On invalid pgid or any
    OSError, the fallback is ``proc.terminate()`` (the drainer has the
    Popen object directly).
    """
    proc = _current_loop_proc
    if proc is None or proc.poll() is not None:
        return False
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return False
    if safe_killpg(pgid, signal.SIGTERM):
        return True
    try:
        proc.terminate()
    except OSError:
        return False
    return True


def _classify_dispatch(
    runner: RunnerType, result_dict: dict[str, Any], timed_out: bool
) -> tuple[bool, str]:
    """Classify a failed dispatch as retryable or not, with its reason (ENH-3416).

    Order: an explicit timeout is never retryable — a command that hit its
    own timeout will hit it again with identical input, so it is not a
    retry-eligible failure regardless of stderr text. A ``LOOP`` entry that
    exhausted its own internal 429/overload retry budget
    (``error == "terminal failure"``, see ``fsm/executor.py``) is not retried
    a second time by the queue. Otherwise falls through to
    :func:`little_loops.issue_lifecycle.classify_failure`, gated on its
    ``reason`` string against :data:`~little_loops.queue_store.QUEUE_RETRYABLE_REASONS`
    (not on ``FailureType`` alone — see ENH-3416 Design Decisions for why a
    queue entry's stderr, arbitrary program output, needs a narrower
    allowlist than the host-CLI-stderr classifier's broad substrings).
    """
    from little_loops.issue_lifecycle import classify_failure
    from little_loops.queue_store import QUEUE_RETRYABLE_REASONS
    from little_loops.runner_spec import RunnerType as _RunnerType

    if timed_out:
        return False, "Command timeout"

    if runner is _RunnerType.LOOP and result_dict.get("error") == "terminal failure":
        return False, "terminal failure"

    error_output = result_dict.get("stderr") or result_dict.get("error") or ""
    returncode = result_dict.get("exit_code")
    if returncode is None:
        returncode = -1

    _failure_type, reason = classify_failure(error_output, returncode)
    return reason in QUEUE_RETRYABLE_REASONS, reason


def _drain_once(
    stop: threading.Event,
    force_stop: threading.Event,
    *,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    on_entry: Callable[[QueueEntry, dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Drain currently-eligible entries once; the shared body for one-shot and ``--watch``.

    Returns ``(processed, backing_off)`` — the dispatch records, and the
    count of pending entries left behind whose ``next_attempt_at`` is still
    in the future (ENH-3416).

    ``RunnerType.LOOP`` entries are intercepted before ``run_action()`` (which
    deliberately never dispatches them, see ``runner_spec.py``) and driven
    via a subprocess ``ll-loop run`` shell-out instead (FEAT-2906). All other
    runner kinds continue through ``run_action()`` unchanged.

    *stop* is checked before each claim, so a graceful shutdown (first
    signal) stops claiming new work without interrupting an entry already in
    flight. The lost-claim path (every currently-eligible entry claimed by
    another drainer between the read and the claim) sleeps *poll_interval*
    before retrying instead of busy-spinning — a rare race for the one-shot
    drainer, routine once ``--watch`` makes concurrent drainers normal.

    A failed dispatch is classified via :func:`_classify_dispatch`
    (ENH-3416): non-retryable lands on ``failed`` (unchanged from
    pre-ENH-3416 behavior); retryable with budget remaining is returned to
    ``pending`` with a backoff ``next_attempt_at``; retryable with the budget
    exhausted lands on terminal ``dead_letter``.

    *force_stop*, when set by a second shutdown signal mid-entry, marks that
    entry ``cancelled`` with ``reason: "interrupted by operator"`` regardless
    of its actual result, then stops draining further entries even if more
    are pending. Every post-dispatch write is guarded (only a row this
    drainer still owns as ``running`` is a valid target) — on a guard miss
    (the entry was cancelled or reclaimed out from under the drainer),
    ``_drain_once`` re-reads the row and reports its actual status.
    """
    from little_loops import queue_store
    from little_loops.queue_store import (
        QUEUE_MAX_ATTEMPTS,
        cancel_entry,
        claim_entry,
        compute_backoff_s,
        dead_letter_entry,
        get_entry,
        list_entries,
        schedule_retry,
        update_entry_result,
    )
    from little_loops.runner_spec import RunnerType, run_action

    def _reread_status(entry_id: str) -> str:
        fetched = get_entry(entry_id, db_path=QUEUE_DB_PATH)
        return fetched.status if fetched is not None else "unknown"

    def _add_seconds(timestamp: str, seconds: int) -> str:
        dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return (dt + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    processed: list[dict[str, Any]] = []
    backing_off = 0

    while not stop.is_set():
        now = queue_store._utcnow()
        pending = [e for e in list_entries(QUEUE_DB_PATH) if e.status == "pending"]
        if not pending:
            break
        eligible = [e for e in pending if e.next_attempt_at is None or e.next_attempt_at <= now]
        if not eligible:
            backing_off = len(pending)
            break

        claimed = next(
            (e for e in eligible if claim_entry(e.id, db_path=QUEUE_DB_PATH, now=now)), None
        )
        if claimed is None:
            # Every currently-eligible entry lost its claim to another drainer;
            # re-read on the next iteration rather than treating this as drained.
            time.sleep(poll_interval)
            continue
        entry = get_entry(claimed.id, db_path=QUEUE_DB_PATH) or claimed

        try:
            if entry.action.runner is RunnerType.LOOP:
                result = _run_loop_entry(entry.action)
            else:
                result = run_action(entry.action, run_id=entry.id)
        except Exception as exc:
            result_dict: dict[str, Any] = {"exit_code": None, "timed_out": False, "error": str(exc)}
        else:
            result_dict = {
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "error": result.error,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        timed_out = bool(result_dict.get("timed_out"))
        succeeded = (
            not timed_out and result_dict.get("error") is None and result_dict.get("exit_code") == 0
        )

        if force_stop.is_set():
            wrote = cancel_entry(
                entry.id, "interrupted by operator", db_path=QUEUE_DB_PATH, extra=result_dict
            )
            status = "cancelled" if wrote else _reread_status(entry.id)
        elif succeeded:
            wrote = update_entry_result(entry.id, "done", result_dict, db_path=QUEUE_DB_PATH)
            status = "done" if wrote else _reread_status(entry.id)
        else:
            retryable, reason = _classify_dispatch(entry.action.runner, result_dict, timed_out)
            error_text = result_dict.get("error") or result_dict.get("stderr") or reason
            if not retryable:
                wrote = update_entry_result(entry.id, "failed", result_dict, db_path=QUEUE_DB_PATH)
                status = "failed" if wrote else _reread_status(entry.id)
            elif entry.attempt < QUEUE_MAX_ATTEMPTS:
                next_attempt_at = _add_seconds(
                    queue_store._utcnow(), compute_backoff_s(entry.attempt)
                )
                wrote = schedule_retry(entry.id, error_text, next_attempt_at, db_path=QUEUE_DB_PATH)
                status = "pending" if wrote else _reread_status(entry.id)
            else:
                wrote = dead_letter_entry(entry.id, error_text, db_path=QUEUE_DB_PATH)
                status = "dead_letter" if wrote else _reread_status(entry.id)

        record = {"id": entry.id, "status": status, "result": result_dict}
        processed.append(record)
        if on_entry is not None:
            on_entry(entry, record)

        if force_stop.is_set():
            break

    return processed, backing_off


def _verify_owner_alive(pid: int | None, claimed_at: str | None) -> bool:
    """Return True if *pid* is alive and identifiably an ``ll-queue`` drainer (FEAT-2930).

    Parallels ``cli/loop/queue.py``'s ``_verify_queue_pid_identity`` (a
    separate, untouched mechanism per that module's docstring), parameterized
    for this store's own process markers instead of ``ll-loop``'s — a bare
    ``os.kill(pid, 0)`` liveness check would risk resurrecting work under a
    recycled PID. Any psutil error or unparseable timestamp yields False, so
    the caller (``_reclaim_stale``) treats an unverifiable owner as dead.
    """
    if pid is None:
        return False
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline())
        if "ll-queue" in cmdline or "little_loops.cli.queue" in cmdline:
            return True
        if claimed_at:
            claimed_ts = (
                datetime.strptime(claimed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
            )
            if proc.create_time() <= claimed_ts:
                return True
        return False
    except Exception:
        return False


def _reclaim_stale(db_path: Path | str) -> tuple[int, int]:
    """Return ``running`` entries whose ``owner_pid`` is dead to ``pending`` (FEAT-2930).

    Run on watcher startup and on each idle poll — a long-lived drainer makes
    a ``SIGKILL``ed/OOM-killed/rebooted owner the normal failure mode rather
    than a rare one a human is present to witness.

    An entry whose ``attempt`` has already reached
    :data:`~little_loops.queue_store.QUEUE_MAX_ATTEMPTS` is dead-lettered
    instead of reclaimed again (ENH-3416) — ``attempt`` is shared between
    transient dispatch failures and owner deaths, so an entry that reliably
    kills its own drainer does not get reclaimed forever. ``next_attempt_at``
    is never touched here: an owner death is not a backoff-eligible failure,
    it is a slot to refill.

    Returns ``(reclaimed, dead_lettered)``.
    """
    from little_loops.queue_store import (
        QUEUE_MAX_ATTEMPTS,
        dead_letter_entry,
        list_entries,
        reset_to_pending,
    )

    running = [e for e in list_entries(db_path) if e.status == "running"]
    reclaimed = 0
    dead_lettered = 0
    for entry in running:
        if _verify_owner_alive(entry.owner_pid, entry.claimed_at):
            continue
        if entry.attempt >= QUEUE_MAX_ATTEMPTS:
            error = f"attempt budget exhausted after {entry.attempt} attempts; last: owner died"
            if dead_letter_entry(entry.id, error, db_path=db_path):
                dead_lettered += 1
        elif reset_to_pending(entry.id, db_path=db_path):
            reclaimed += 1
    return reclaimed, dead_lettered


def cmd_run(args: argparse.Namespace) -> int:
    """Dequeue pending entries in priority/FIFO order and dispatch each entry.

    Without ``--watch``: drain what's pending, then exit (unchanged one-shot
    behavior). With ``--watch``: drain, then sleep-poll for new work
    indefinitely (FEAT-2930) — see ``_run_watch``.
    """
    from little_loops.cli.output import colorize, print_json

    json_mode = getattr(args, "json", False)
    poll_interval = getattr(args, "poll_interval", _DEFAULT_POLL_INTERVAL)

    if getattr(args, "watch", False):
        return _run_watch(json_mode, poll_interval)

    stop = threading.Event()
    force_stop = threading.Event()

    def _print_line(entry: QueueEntry, record: dict[str, Any]) -> None:
        if json_mode:
            return
        status_color = _STATUS_COLOR.get(record["status"], "0")
        print(
            f"  {colorize(entry.id[:8], '34')}  {colorize(record['status'], status_color)}  "
            f"{entry.action.runner.value}:{entry.action.target}"
        )

    processed, backing_off = _drain_once(
        stop, force_stop, poll_interval=poll_interval, on_entry=_print_line
    )

    if json_mode:
        print_json(processed)
        return 0

    if not processed:
        print("Queue is empty")
    else:
        plural = "y" if len(processed) == 1 else "ies"
        print(colorize(f"Processed {len(processed)} entr{plural}", "1"))
    if backing_off:
        plural = "y" if backing_off == 1 else "ies"
        print(colorize(f"{backing_off} entr{plural} backing off, not yet eligible for retry", "33"))
    return 0


def _make_signal_handler(
    stop: threading.Event, force_stop: threading.Event, *, json_mode: bool
) -> Callable[[int, Any], None]:
    """Build the two-stage shutdown signal handler for ``--watch`` (FEAT-2930).

    First call: sets *stop* so the drain loop stops claiming new work after
    the in-flight entry finishes. Second call (``stop`` already set): sets
    *force_stop* and forwards SIGTERM to any in-flight LOOP subprocess via
    :func:`_kill_current_loop_proc`. A standalone function (not a closure
    over ``_run_watch``) so it can be exercised directly in tests, mirroring
    ``cli/sprint/run.py``'s ``_sprint_signal_handler``.
    """

    def _handle_signal(signum: int, frame: Any) -> None:
        if stop.is_set():
            force_stop.set()
            _kill_current_loop_proc()
            if not json_mode:
                print("\nForce shutdown: terminating in-flight entry", file=sys.stderr)
        else:
            stop.set()
            if not json_mode:
                print("\nShutdown requested: finishing current entry, will exit", file=sys.stderr)

    return _handle_signal


def _run_watch(json_mode: bool, poll_interval: float) -> int:
    """Long-lived drainer: drain, then sleep-poll for new work indefinitely (FEAT-2930).

    Shutdown semantics: a first ``SIGINT``/``SIGTERM`` lets the in-flight
    entry finish and records its real result, then exits 0 without claiming
    further work. A second signal forwards ``SIGTERM`` to an in-flight LOOP
    child's process group, marks that entry ``cancelled`` with
    ``reason: "interrupted by operator"``, and exits 0. An idle wait (no entry
    in flight) exits 0 immediately on either signal — nothing is left
    ``running``.

    ``--json`` emits NDJSON (one compact object per processed entry, flushed
    immediately) rather than the one-shot's single accumulated array, since a
    watcher never reaches a natural end-of-list.
    """
    from little_loops.cli.output import colorize

    stop = threading.Event()
    force_stop = threading.Event()
    handler = _make_signal_handler(stop, force_stop, json_mode=json_mode)

    prev_int = signal.signal(signal.SIGINT, handler)
    prev_term = signal.signal(signal.SIGTERM, handler)

    def _emit(entry: QueueEntry, record: dict[str, Any]) -> None:
        if json_mode:
            print(json.dumps(record), flush=True)
        else:
            status_color = _STATUS_COLOR.get(record["status"], "0")
            print(
                f"  {colorize(entry.id[:8], '34')}  {colorize(record['status'], status_color)}  "
                f"{entry.action.runner.value}:{entry.action.target}",
                flush=True,
            )

    def _report_reclaim(reclaimed: int, dead_lettered: int) -> None:
        if not (reclaimed or dead_lettered) or json_mode:
            return
        plural = "y" if reclaimed == 1 else "ies"
        print(
            colorize(
                f"Reclaimed {reclaimed} stale entr{plural}, dead-lettered {dead_lettered}", "33"
            )
        )

    try:
        _report_reclaim(*_reclaim_stale(QUEUE_DB_PATH))

        while not stop.is_set():
            _drain_once(stop, force_stop, poll_interval=poll_interval, on_entry=_emit)
            if stop.is_set():
                break
            time.sleep(poll_interval)
            _report_reclaim(*_reclaim_stale(QUEUE_DB_PATH))
    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)

    return 0


def cmd_requeue(args: argparse.Namespace) -> int:
    """Return a stranded ``running`` entry to ``pending``, or revive a terminal one (ENH-3416).

    For a ``running`` entry (FEAT-2930's original manual escape hatch):
    without ``--force``, refuses (with a clear message) when the entry's
    ``owner_pid`` still looks alive — that's the automatic ``_reclaim_stale``
    sweep's job, and a live owner is presumably still working the entry.
    ``--force`` is for the case the sweep can't decide: owner still alive but
    wedged, per the operator's own judgement.

    Widened (ENH-3416) to also accept ``dead_letter``/``failed``/``cancelled``
    entries, reviving them via :func:`~little_loops.queue_store.revive_entry`
    with a fresh attempt budget — no owner-liveness check applies to a
    terminal entry.
    """
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import reset_to_pending, revive_entry

    code = _not_found_or_ambiguous(args)
    if code is not None:
        return code
    entry = args._resolved_entry
    json_mode = getattr(args, "json", False)
    force = getattr(args, "force", False)

    if entry.status == "running":
        if not force and _verify_owner_alive(entry.owner_pid, entry.claimed_at):
            msg = (
                f"Entry '{entry.id[:8]}' owner (pid {entry.owner_pid}) appears alive; "
                "use --force to requeue anyway"
            )
            if json_mode:
                print_json({"error": msg, "id": entry.id})
            else:
                print(msg, file=sys.stderr)
            return 1
        reset_to_pending(entry.id, db_path=QUEUE_DB_PATH)
    elif entry.status in ("dead_letter", "failed", "cancelled"):
        revive_entry(entry.id, db_path=QUEUE_DB_PATH)
    else:
        msg = (
            f"Entry '{entry.id[:8]}' is {entry.status}, not running/dead_letter/failed/"
            "cancelled; nothing to requeue"
        )
        if json_mode:
            print_json({"error": msg, "id": entry.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    if json_mode:
        print_json({"requeued": entry.id})
    else:
        print(f"Requeued {colorize(entry.id[:8], '34')}")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    """Move a ``pending`` or ``running`` entry to terminal ``cancelled`` (ENH-3416).

    Does not signal an in-flight process — cancelling a ``running`` entry is
    a status-only mark; the drainer's guarded completion write then no-ops
    and the entry stays ``cancelled`` (see ``_drain_once``'s guard-miss
    re-read). Killing arbitrary runner subprocesses from a second CLI process
    is out of scope (only the drainer holds the ``Popen``).
    """
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import cancel_entry

    code = _not_found_or_ambiguous(args)
    if code is not None:
        return code
    entry = args._resolved_entry
    json_mode = getattr(args, "json", False)
    reason = getattr(args, "reason", None) or "cancelled by operator"

    if entry.status not in ("pending", "running"):
        msg = f"Entry '{entry.id[:8]}' is {entry.status}, not pending/running; nothing to cancel"
        if json_mode:
            print_json({"error": msg, "id": entry.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    cancel_entry(entry.id, reason, db_path=QUEUE_DB_PATH)
    if json_mode:
        print_json({"cancelled": entry.id, "reason": reason})
    else:
        print(f"Cancelled {colorize(entry.id[:8], '34')}")
    return 0


def main_queue() -> int:
    """CLI handler for ll-queue subcommands."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-queue", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-queue",
            description="Persisted work-item queue: add/list/status/remove/run/requeue commands",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-queue add audit-docs
  ll-queue add "pytest scripts/tests/" --runner cmd --priority P1
  ll-queue list --json
  ll-queue status abcd1234
  ll-queue remove abcd1234 --force
  ll-queue run
  ll-queue run --watch --poll-interval 5
  ll-queue requeue abcd1234
  ll-queue cancel abcd1234 --reason "no longer needed"
""",
        )

        subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
        subparsers.required = True

        add_parser = subparsers.add_parser(
            "add",
            help="Enqueue a work item (FSM loop, skill/command, or raw CLI invocation)",
            description="Classify and persist a new queue entry",
        )
        add_parser.add_argument(
            "target", help="Loop name, skill/command name, or raw CLI invocation"
        )
        add_parser.add_argument(
            "--priority",
            default="P3",
            choices=["P0", "P1", "P2", "P3", "P4", "P5"],
            help="Priority tier (default: P3)",
        )
        add_parser.add_argument(
            "--runner",
            default=None,
            choices=["skill", "cmd", "mcp", "prompt", "loop"],
            help="Force a specific runner kind instead of classifying the target",
        )
        add_parser.add_argument(
            "--arg",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Extra ActionSpec arg (repeatable)",
        )
        add_parser.add_argument(
            "--timeout",
            type=int,
            default=None,
            help="Timeout in seconds (default: 120, unbounded for --runner loop)",
        )
        add_parser.add_argument(
            "--input",
            default=None,
            help="Input for a LOOP-runner target, same semantics as `ll-loop run <loop> [input]` "
            "(JSON object unpacks into matching context keys, else stored under fsm.input_key)",
        )
        add_parser.add_argument("--json", action="store_true", default=False, help="JSON output")

        list_parser = subparsers.add_parser(
            "list", help="List all queue entries", description="List persisted queue entries"
        )
        list_parser.add_argument("--json", action="store_true", default=False, help="JSON output")
        list_parser.add_argument(
            "--wide",
            action="store_true",
            default=False,
            help="Show untruncated args/timeout summary",
        )

        status_parser = subparsers.add_parser(
            "status",
            help="Show a single entry's state and result",
            description="Show a queue entry by full id or 8+-char prefix",
        )
        status_parser.add_argument("id", help="Entry id (full uuid or 8+-char prefix)")
        status_parser.add_argument("--json", action="store_true", default=False, help="JSON output")

        remove_parser = subparsers.add_parser(
            "remove",
            help="Delete a pending entry",
            description="Delete a queue entry by full id or 8+-char prefix",
        )
        remove_parser.add_argument("id", help="Entry id (full uuid or 8+-char prefix)")
        remove_parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Remove even if the entry is not pending",
        )
        remove_parser.add_argument("--json", action="store_true", default=False, help="JSON output")

        run_parser = subparsers.add_parser(
            "run",
            help="Dequeue and execute pending entries in priority/FIFO order",
            description="Serially dispatch each pending entry: SKILL/CMD/MCP/PROMPT through "
            "run_action(), LOOP entries via a subprocess `ll-loop run` shell-out",
        )
        run_parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="JSON output. Under --watch, emits NDJSON (one object per line per "
            "processed entry) instead of a single array.",
        )
        run_parser.add_argument(
            "--watch",
            action="store_true",
            default=False,
            help="Long-lived drainer: after draining, sleep-poll for new entries "
            "instead of exiting. Ctrl-C once for a graceful drain, twice to force-stop "
            "the in-flight entry.",
        )
        run_parser.add_argument(
            "--poll-interval",
            type=float,
            default=_DEFAULT_POLL_INTERVAL,
            help=f"Seconds between polls under --watch (default: {_DEFAULT_POLL_INTERVAL})",
        )

        requeue_parser = subparsers.add_parser(
            "requeue",
            help="Return a stranded `running` entry to `pending`",
            description="Manual escape hatch for a running entry whose owner process "
            "is gone or wedged; a --watch drainer's stale-entry sweep already "
            "handles the common dead-owner case automatically on startup/idle poll",
        )
        requeue_parser.add_argument("id", help="Entry id (full uuid or 8+-char prefix)")
        requeue_parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Requeue even if the owner process still appears alive",
        )
        requeue_parser.add_argument(
            "--json", action="store_true", default=False, help="JSON output"
        )

        cancel_parser = subparsers.add_parser(
            "cancel",
            help="Move a pending or running entry to terminal `cancelled`",
            description="Operator cancel; does not signal an in-flight process "
            "(the drainer's guarded completion write no-ops on a cancelled row)",
        )
        cancel_parser.add_argument("id", help="Entry id (full uuid or 8+-char prefix)")
        cancel_parser.add_argument("--reason", default=None, help="Reason recorded on the entry")
        cancel_parser.add_argument("--json", action="store_true", default=False, help="JSON output")

        parsed = parser.parse_args()

        if parsed.command == "add":
            return cmd_add(parsed)
        elif parsed.command == "list":
            return cmd_list(parsed)
        elif parsed.command == "status":
            return cmd_status(parsed)
        elif parsed.command == "remove":
            return cmd_remove(parsed)
        elif parsed.command == "run":
            return cmd_run(parsed)
        elif parsed.command == "requeue":
            return cmd_requeue(parsed)
        elif parsed.command == "cancel":
            return cmd_cancel(parsed)
        else:
            parser.print_help()
            return 1

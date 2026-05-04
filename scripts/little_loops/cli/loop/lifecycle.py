"""ll-loop lifecycle subcommands: status, stop, resume."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import time
from pathlib import Path

from little_loops.cli.loop._helpers import (
    EXIT_CODES,
    load_loop,
    register_loop_signal_handlers,
    run_background,
)
from little_loops.fsm.concurrency import _process_alive
from little_loops.fsm.persistence import LoopState, _find_instances
from little_loops.logger import Logger


def _format_relative_time(seconds: float) -> str:
    """Format seconds as a human-readable relative time string (e.g., '3m ago').

    Delegates to the shared ``format_relative_time`` in ``cli.output``.
    """
    from little_loops.cli.output import format_relative_time

    return format_relative_time(seconds)


def _read_pid_file(pid_file: Path) -> int | None:
    """Read and validate a PID file.

    Returns:
        The PID as an integer, or None if the file doesn't exist or is invalid.
    """
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def _kill_with_timeout(pid: int, label: str, logger: Logger) -> None:
    """Send SIGTERM to pid; escalate to SIGKILL after 10 s if still alive."""
    os.kill(pid, signal.SIGTERM)
    for _ in range(10):
        time.sleep(1)
        if not _process_alive(pid):
            return
    try:
        os.kill(pid, signal.SIGKILL)
        logger.warning(f"Sent SIGKILL to {label} (PID: {pid})")
    except OSError:
        pass


def _status_single(
    instance_id: str | None,
    state: LoopState,
    loop_name: str,
    running_dir: Path,
    args: argparse.Namespace | None,
) -> int:
    """Render status for one instance (human-readable or JSON)."""
    from little_loops.cli.output import print_json

    stem = instance_id or loop_name
    pid_file = running_dir / f"{stem}.pid"
    pid = _read_pid_file(pid_file)
    pid_source: str | None = "pid_file" if pid is not None else None

    if pid is None:
        lock_file_path = running_dir / f"{stem}.lock"
        if lock_file_path.exists():
            try:
                with open(lock_file_path) as _lf:
                    lock_data = json.load(_lf)
                pid = lock_data.get("pid")
                if pid is not None:
                    pid_source = "lock_file"
            except (json.JSONDecodeError, KeyError, OSError):
                pass

    log_file = running_dir / f"{stem}.log"
    log_file_str: str | None = None
    log_updated_ago: str | None = None
    last_event: str | None = None
    if log_file.exists():
        log_file_str = str(log_file)
        age_seconds = time.time() - log_file.stat().st_mtime
        log_updated_ago = _format_relative_time(age_seconds)
        try:
            lines = log_file.read_text().splitlines()
            non_empty = [ln for ln in lines if ln.strip()]
            last_event = non_empty[-1] if non_empty else None
        except OSError:
            last_event = None

    if getattr(args, "json", False):
        d = state.to_dict()
        d["pid"] = pid
        d["pid_source"] = pid_source
        d["log_file"] = log_file_str
        d["log_updated_ago"] = log_updated_ago
        d["last_event"] = last_event
        print_json(d)
        return 0

    print(f"Loop: {state.loop_name}")
    print(f"Status: {state.status}")
    print(f"Current state: {state.current_state}")
    print(f"Iteration: {state.iteration}")
    print(f"Started: {state.started_at}")
    print(f"Updated: {state.updated_at}")

    if pid is not None:
        if _process_alive(pid):
            print(f"PID: {pid} (running)")
        else:
            print(f"PID: {pid} (not running - stale PID file)")

    if log_file_str is not None:
        print(f"Log: {log_file_str}")
        print(f"Log updated: {log_updated_ago}")
        if last_event:
            print(f"Last event: {last_event}")
    else:
        print("Log: (not found)")

    if state.continuation_prompt:
        prompt_preview = state.continuation_prompt[:200]
        if len(state.continuation_prompt) > 200:
            prompt_preview += "..."
        print(f"Continuation context: {prompt_preview}")
    return 0


def cmd_status(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
    args: argparse.Namespace | None = None,
) -> int:
    """Show loop status."""
    from little_loops.cli.output import print_json

    running_dir = loops_dir / ".running"
    instances = _find_instances(loop_name, running_dir)

    if not instances:
        logger.error(f"No state found for: {loop_name}")
        return 1

    if len(instances) == 1:
        instance_id, state = instances[0]
        return _status_single(instance_id, state, loop_name, running_dir, args)

    # Multiple instances: aggregate display
    if getattr(args, "json", False):
        result_list = []
        for instance_id, state in instances:
            stem = instance_id or loop_name
            pid_file = running_dir / f"{stem}.pid"
            pid = _read_pid_file(pid_file)
            pid_source: str | None = "pid_file" if pid is not None else None
            if pid is None:
                lock_file_path = running_dir / f"{stem}.lock"
                if lock_file_path.exists():
                    try:
                        with open(lock_file_path) as _lf:
                            lock_data = json.load(_lf)
                        pid = lock_data.get("pid")
                        if pid is not None:
                            pid_source = "lock_file"
                    except (json.JSONDecodeError, KeyError, OSError):
                        pass
            log_file = running_dir / f"{stem}.log"
            d = state.to_dict()
            d["instance_id"] = instance_id
            d["pid"] = pid
            d["pid_source"] = pid_source
            if log_file.exists():
                d["log_file"] = str(log_file)
                d["log_updated_ago"] = _format_relative_time(
                    time.time() - log_file.stat().st_mtime
                )
            else:
                d["log_file"] = None
                d["log_updated_ago"] = None
            result_list.append(d)
        print_json(result_list)
        return 0

    print(f"{len(instances)} instances of '{loop_name}':")
    for i, (instance_id, state) in enumerate(instances, 1):
        stem = instance_id or loop_name
        pid_file = running_dir / f"{stem}.pid"
        pid = _read_pid_file(pid_file)
        if pid is None:
            lock_file_path = running_dir / f"{stem}.lock"
            if lock_file_path.exists():
                try:
                    with open(lock_file_path) as _lf:
                        lock_data = json.load(_lf)
                    pid = lock_data.get("pid")
                except (json.JSONDecodeError, KeyError, OSError):
                    pass
        log_file = running_dir / f"{stem}.log"

        print()
        print(f"[{i}] {stem}")
        print(f"  Status: {state.status}")
        print(f"  Current state: {state.current_state}")
        print(f"  Iteration: {state.iteration}")
        if pid is not None:
            if _process_alive(pid):
                print(f"  PID: {pid} (running)")
            else:
                print(f"  PID: {pid} (not running - stale PID file)")
        if log_file.exists():
            age_seconds = time.time() - log_file.stat().st_mtime
            print(f"  Log: {log_file}")
            print(f"  Log updated: {_format_relative_time(age_seconds)}")
        else:
            print("  Log: (not found)")
    return 0


def cmd_stop(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Stop a running loop."""
    from little_loops.fsm.persistence import StatePersistence

    running_dir = loops_dir / ".running"
    instances = _find_instances(loop_name, running_dir)

    if not instances:
        logger.error(f"No state found for: {loop_name}")
        return 1

    running_instances = [(iid, s) for iid, s in instances if s.status == "running"]

    if not running_instances:
        # Secondary check: an orphaned lock-file with a live PID blocks scope
        # acquisition even when state is not "running". Kill the holder and release.
        for instance_id, state in instances:
            stem = instance_id or loop_name
            lock_file = running_dir / f"{stem}.lock"
            if lock_file.exists():
                lock_pid: int | None = None
                try:
                    with open(lock_file) as _lf:
                        lock_data = json.load(_lf)
                    lock_pid = lock_data.get("pid")
                except (json.JSONDecodeError, KeyError, OSError):
                    pass
                if lock_pid and _process_alive(lock_pid):
                    logger.warning(
                        f"Loop state is '{state.status}' but lock file holds live PID {lock_pid}. "
                        "Killing orphaned lock holder..."
                    )
                    _kill_with_timeout(lock_pid, stem, logger)
                    lock_file.unlink(missing_ok=True)
                    logger.success(f"Released orphaned scope lock for {stem}")
                    return 0
                elif lock_pid is not None:
                    # Dead PID: stale lock file, just remove it
                    lock_file.unlink(missing_ok=True)
                    logger.info(f"Removed stale lock file for {stem}")
                    return 0
        _, state = instances[0]
        logger.error(f"Loop not running: {loop_name} (status: {state.status})")
        return 1

    for instance_id, state in running_instances:
        persistence = StatePersistence(loop_name, loops_dir, instance_id=instance_id)
        stem = instance_id or loop_name
        pid_file = running_dir / f"{stem}.pid"
        pid = _read_pid_file(pid_file)

        if pid is not None:
            if _process_alive(pid):
                _kill_with_timeout(pid, stem, logger)
                state.status = "interrupted"
                persistence.save_state(state)
                pid_file.unlink(missing_ok=True)
                logger.success(f"Stopped {stem} (PID: {pid})")
            else:
                # Process already exited: preserve its final status, only clean up PID file
                logger.info(f"Process {pid} not running, cleaning up PID file")
                pid_file.unlink(missing_ok=True)
        else:
            # No PID file: no background process tracked, update state only
            state.status = "interrupted"
            persistence.save_state(state)
            logger.success(f"Marked {stem} as interrupted")

    return 0


def cmd_resume(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Resume an interrupted loop."""
    from little_loops.fsm.persistence import PersistentExecutor

    # Background mode: spawn detached process and return
    if getattr(args, "background", False):
        return run_background(loop_name, args, loops_dir, subcommand="resume")

    # Register PID file for all foreground runs so cmd_stop can send SIGTERM (BUG-639).
    # Background-spawned processes (foreground_internal=True) have their PID written by the
    # parent in run_background(); plain foreground runs must write their own PID here.
    import os

    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    # Discover all instances and resolve to a single resumable one.
    instances = _find_instances(loop_name, running_dir)
    resumable = [
        (iid, s) for iid, s in instances if s.status in ("running", "awaiting_continuation")
    ]
    if len(resumable) > 1:
        print(f"Multiple instances of '{loop_name}' are resumable:")
        for iid, _ in resumable:
            print(f"  {iid or loop_name}")
        print("Use --instance-id to select one.")
        return 1

    # Use discovered instance_id (or fall back to args / None for no-state case)
    if resumable:
        instance_id: str | None = resumable[0][0]
        state_for_display = resumable[0][1]
    else:
        instance_id = getattr(args, "instance_id", None)
        state_for_display = None

    pid_file = running_dir / f"{instance_id or loop_name}.pid"
    foreground_pid_file: Path | None = pid_file

    if not getattr(args, "foreground_internal", False):
        pid_file.write_text(str(os.getpid()))

    def _cleanup_pid() -> None:
        pid_file.unlink(missing_ok=True)

    atexit.register(_cleanup_pid)

    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1

    for kv in getattr(args, "context", None) or []:
        if "=" not in kv:
            raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
        key, _, value = kv.partition("=")
        fsm.context[key.strip()] = value.strip()

    if getattr(args, "delay", None) is not None:
        fsm.backoff = args.delay

    # Apply YAML loop config env-var overrides (CLI flags below overwrite these)
    if fsm.config is not None and isinstance(fsm.config.handoff_threshold, int):
        os.environ["LL_HANDOFF_THRESHOLD"] = str(fsm.config.handoff_threshold)

    if getattr(args, "handoff_threshold", None) is not None:
        if not (1 <= args.handoff_threshold <= 100):
            raise SystemExit("--handoff-threshold must be between 1 and 100")
        os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)

    # Show context if resuming from a handoff
    if state_for_display and state_for_display.status == "awaiting_continuation":
        print(f"Resuming from context handoff (iteration {state_for_display.iteration})...")
        if state_for_display.continuation_prompt:
            prompt_preview = state_for_display.continuation_prompt[:500]
            if len(state_for_display.continuation_prompt) > 500:
                prompt_preview += "..."
            print(f"Context: {prompt_preview}")
            print()

    from little_loops.config import BRConfig
    from little_loops.extension import wire_extensions
    from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
    from little_loops.transport import wire_transports

    config = BRConfig(Path.cwd())
    circuit = (
        RateLimitCircuit(Path(config.commands.rate_limits.circuit_breaker_path))
        if config.commands.rate_limits.circuit_breaker_enabled
        else None
    )
    executor = PersistentExecutor(fsm, loops_dir=loops_dir, circuit=circuit, instance_id=instance_id)

    # Register signal handlers for graceful shutdown (same as cmd_run)
    register_loop_signal_handlers(executor, pid_file=foreground_pid_file)

    wire_extensions(executor.event_bus, config.extensions, executor=executor)
    wire_transports(executor.event_bus, config.events)

    try:
        result = executor.resume()

        if result is None:
            logger.warning(f"Nothing to resume for: {loop_name}")
            return 1

        duration_sec = result.duration_ms / 1000
        if duration_sec < 60:
            duration_str = f"{duration_sec:.1f}s"
        else:
            minutes = int(duration_sec // 60)
            seconds = duration_sec % 60
            duration_str = f"{minutes}m {seconds:.0f}s"

        logger.success(
            f"Resumed and completed: {result.final_state} "
            f"({result.iterations} iterations, {duration_str})"
        )
        return EXIT_CODES.get(result.terminated_by, 1)
    finally:
        executor.close_transports()

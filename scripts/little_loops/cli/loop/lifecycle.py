"""ll-loop lifecycle subcommands: status, stop, resume."""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import signal
import time
from pathlib import Path

from little_loops.cli.loop._helpers import (
    load_loop,
    register_loop_signal_handlers,
    resolve_loop_path,
    run_background,
)
from little_loops.fsm.concurrency import _process_alive
from little_loops.fsm.persistence import (
    LoopState,
    StatePersistence,
    _find_instances,
    _read_pid_file,
    _reconcile_stale_running,
)
from little_loops.logger import Logger


def _format_relative_time(seconds: float) -> str:
    """Format seconds as a human-readable relative time string (e.g., '3m ago').

    Delegates to the shared ``format_relative_time`` in ``cli.output``.
    """
    from little_loops.cli.output import format_relative_time

    return format_relative_time(seconds)


def _format_log_label(running_dir: Path, stem: str) -> str:
    """Return one of three Log: labels based on run-mode signals.

    - log exists → path string (background run, normal)
    - no log, no pid → foreground run (output went to terminal)
    - no log, pid exists → background run whose log was deleted (something wrong)
    """
    log_file = running_dir / f"{stem}.log"
    if log_file.exists():
        return str(log_file)
    pid_file = running_dir / f"{stem}.pid"
    if pid_file.exists():
        return f"(expected {log_file}, missing)"
    return "(foreground run — output went to terminal)"


def _get_events_info(running_dir: Path, stem: str) -> tuple[str | None, str | None]:
    """Return (events_file_str, formatted_detail_line) for the events.jsonl file.

    Returns (None, None) if the file doesn't exist.
    Detail line format: 'Events: <path>  (N events, last Xm ago)'
    """
    events_file = running_dir / f"{stem}.events.jsonl"
    if not events_file.exists():
        return None, None
    try:
        lines = [ln for ln in events_file.read_text().splitlines() if ln.strip()]
        count = len(lines)
        detail = f"({count} events)"
        if lines:
            try:
                last_entry = json.loads(lines[-1])
                last_ts = last_entry.get("ts")
                if last_ts is not None:
                    from datetime import UTC, datetime

                    dt = datetime.fromisoformat(last_ts)
                    age = (datetime.now(tz=UTC) - dt).total_seconds()
                    detail = f"({count} events, last {_format_relative_time(age)})"
            except (json.JSONDecodeError, AttributeError, ValueError, OverflowError):
                pass
        return str(events_file), f"Events: {events_file}  {detail}"
    except OSError:
        return str(events_file), f"Events: {events_file}"


def _kill_with_timeout(pid: int, label: str, logger: Logger) -> None:
    """Kill pid and all descendants via process group; SIGTERM first, escalate to SIGKILL.

    Uses os.killpg to atomically signal the entire process group, closing the
    race window inherent in the old _get_descendant_pids() snapshot approach.
    Since run_background and run_claude_command both launch with
    start_new_session=True, the PID is a session leader with PGID == PID.
    All children inherit this PGID unless they explicitly call setsid().

    Falls back to os.kill on the root PID when os.killpg is unavailable (Windows).
    """
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return  # Already dead — nothing to do

    # Atomically signal the entire process group
    _signal_process_group(pgid, pid, signal.SIGTERM, label)

    for _ in range(10):
        time.sleep(1)
        if not _process_alive(pid):
            return

    # Escalate to SIGKILL on the process group
    _signal_process_group(pgid, pid, signal.SIGKILL, label)
    logger.warning(f"Sent SIGKILL to {label} (PID: {pid})")


def _signal_process_group(pgid: int, pid: int, sig: int, label: str) -> None:
    """Send a signal to the process group, falling back to single-PID kill."""
    try:
        os.killpg(pgid, sig)
    except AttributeError:
        # os.killpg not available (Windows) — fall back to single-PID kill
        try:
            os.kill(pid, sig)
        except OSError:
            pass
    except (ProcessLookupError, PermissionError):
        pass  # Group already gone or no permission — not actionable


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
    persistence = StatePersistence(loop_name, running_dir.parent, instance_id=instance_id)
    state = _reconcile_stale_running(state, persistence, running_dir, stem)

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

    events_file_str, events_detail_line = _get_events_info(running_dir, stem)

    if getattr(args, "json", False):
        d = state.to_dict()
        d["pid"] = pid
        d["pid_source"] = pid_source
        d["log_file"] = log_file_str
        d["log_updated_ago"] = log_updated_ago
        d["last_event"] = last_event
        d["events_file"] = events_file_str
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

    log_label = _format_log_label(running_dir, stem)
    print(f"Log: {log_label}")
    if log_file_str is not None:
        print(f"Log updated: {log_updated_ago}")
        if last_event:
            print(f"Last event: {last_event}")

    if events_detail_line is not None:
        print(events_detail_line)

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
            persistence = StatePersistence(loop_name, loops_dir, instance_id=instance_id)
            state = _reconcile_stale_running(state, persistence, running_dir, stem)
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
                d["log_updated_ago"] = _format_relative_time(time.time() - log_file.stat().st_mtime)
            else:
                d["log_file"] = None
                d["log_updated_ago"] = None
            events_file_str, _ = _get_events_info(running_dir, stem)
            d["events_file"] = events_file_str
            result_list.append(d)
        print_json(result_list)
        return 0

    print(f"{len(instances)} instances of '{loop_name}':")
    for i, (instance_id, state) in enumerate(instances, 1):
        stem = instance_id or loop_name
        persistence = StatePersistence(loop_name, loops_dir, instance_id=instance_id)
        state = _reconcile_stale_running(state, persistence, running_dir, stem)
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
        log_label = _format_log_label(running_dir, stem)
        print(f"  Log: {log_label}")
        if log_file.exists():
            age_seconds = time.time() - log_file.stat().st_mtime
            print(f"  Log updated: {_format_relative_time(age_seconds)}")
        _, events_detail_line = _get_events_info(running_dir, stem)
        if events_detail_line is not None:
            print(f"  {events_detail_line}")
    return 0


def cmd_stop(
    loop_name: str,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Stop a running loop."""
    from little_loops.fsm.persistence import StatePersistence  # noqa: PLC0415

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
    import os

    from little_loops.fsm.persistence import RESUMABLE_STATUSES, PersistentExecutor

    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    # Discover all instances and resolve to a single resumable one.
    instances = _find_instances(loop_name, running_dir)
    resumable = [(iid, s) for iid, s in instances if s.status in RESUMABLE_STATUSES]

    explicit_instance_id = getattr(args, "instance_id", None)
    if explicit_instance_id:
        filtered: list[tuple[str | None, LoopState]] = [
            (iid, s) for iid, s in resumable if iid == explicit_instance_id
        ]
        if not filtered:
            print(
                f"Instance '{explicit_instance_id}' not found among resumable instances of '{loop_name}'."
            )
            if resumable:
                print("Resumable instances:")
                for iid, _ in resumable:
                    print(f"  {iid or loop_name}")
            return 1
        resumable = filtered
    elif len(resumable) > 1:
        # Auto-select the most recent instance by sorted filename (matches cmd_monitor()).
        selected_id = resumable[-1][0]
        print(f"Auto-selected latest instance: {selected_id}")
        resumable = [resumable[-1]]

    # Use discovered instance_id (or fall back to args / None for no-state case)
    if resumable:
        instance_id: str | None = resumable[0][0]
        state_for_display = resumable[0][1]
    else:
        instance_id = None
        state_for_display = None

    # Background mode: spawn detached process and return
    if getattr(args, "background", False):
        if instance_id is None:
            print(f"No resumable instances of '{loop_name}'.")
            return 1
        return run_background(
            loop_name, args, loops_dir, subcommand="resume", instance_id=instance_id
        )

    # Register PID file for all foreground runs so cmd_stop can send SIGTERM (BUG-639).
    # Background-spawned processes (foreground_internal=True) have their PID written by the
    # parent in run_background(); plain foreground runs must write their own PID here.
    if instance_id is None:
        instance_id = getattr(args, "instance_id", None)

    pid_file = running_dir / f"{instance_id or loop_name}.pid"
    foreground_pid_file: Path | None = pid_file

    if not getattr(args, "foreground_internal", False):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
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

    if getattr(args, "baseline", False):
        logger.error(
            "--baseline is not supported with resume. Start a fresh run with 'll-loop run'."
        )
        return 1

    try:
        loop_path = resolve_loop_path(loop_name, loops_dir)
    except FileNotFoundError:
        loop_path = None

    for kv in getattr(args, "context", None) or []:
        if "=" not in kv:
            raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
        key, _, value = kv.partition("=")
        fsm.context[key.strip()] = value.strip()

    # Re-inject run_dir using the same instance_id as the original run so resumed
    # loops write artifacts to the same directory they started with.
    if "run_dir" not in fsm.context and instance_id is not None:
        fsm.context["run_dir"] = str(loops_dir / "runs" / instance_id) + "/"

    # Re-inject input hash for checkpoint fingerprinting during resumed runs.
    if "input_hash" not in fsm.context and isinstance(fsm.context.get("input"), str):
        fsm.context["input_hash"] = hashlib.sha256(fsm.context["input"].encode()).hexdigest()[:12]

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
    from little_loops.design_tokens import load_design_tokens, render_as_prompt_context
    from little_loops.extension import wire_extensions
    from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
    from little_loops.transport import wire_transports

    config = BRConfig(Path.cwd())

    if not fsm.context.get("design_tokens_context"):
        _tokens = load_design_tokens(config)
        fsm.context["design_tokens_context"] = render_as_prompt_context(_tokens) if _tokens else ""

    circuit = (
        RateLimitCircuit(Path(config.commands.rate_limits.circuit_breaker_path))
        if config.commands.rate_limits.circuit_breaker_enabled
        else None
    )
    executor = PersistentExecutor(
        fsm, loops_dir=loops_dir, circuit=circuit, instance_id=instance_id
    )

    # Register signal handlers for graceful shutdown (same as cmd_run)
    register_loop_signal_handlers(executor, pid_file=foreground_pid_file)

    wire_extensions(executor.event_bus, config.extensions, executor=executor)
    wire_transports(executor.event_bus, config.events)

    # Route through run_foreground (BUG-1645) so the resume path shares the
    # display-callback wiring that cmd_run gets via run_foreground. Without this
    # the FSM event bus has no subscriber on a resumed run, leaving the terminal
    # silent for the entire duration (no per-iteration lines, no FSM diagram).
    from little_loops.cli.loop._helpers import run_foreground

    _edge_label_colors = config.cli.colors.fsm_edge_labels.to_dict()
    _highlight_color = config.cli.colors.fsm_active_state
    _badges = config.loops.glyphs.to_dict()

    try:
        return run_foreground(
            executor,
            fsm,
            args,
            highlight_color=_highlight_color,
            edge_label_colors=_edge_label_colors,
            badges=_badges,
            mode="resume",
            instance_id=instance_id,
            running_dir=running_dir,
            loop_path=loop_path,
            model=fsm.llm.model,
        )
    finally:
        executor.close_transports()


def _print_last_state(state: LoopState) -> None:
    """Print last-known state (used when not actively tailing)."""
    print(f"Loop: {state.loop_name}")
    print(f"Status: {state.status}")
    print(f"Current state: {state.current_state}")
    print(f"Iteration: {state.iteration}")


def cmd_monitor(args: argparse.Namespace, loops_dir: Path) -> int:
    """Attach to a running loop and render its FSM state in realtime.

    Read-only attach: tails ``<stem>.events.jsonl`` and forwards events to a
    ``StateFeedRenderer``. Ctrl-C detaches without sending any signal to the
    loop process (FEAT-1764).
    """
    loop_name = args.loop
    running_dir = loops_dir / ".running"
    instances = _find_instances(loop_name, running_dir)

    if not instances:
        print(f"No instances of '{loop_name}' found")
        return 1

    instance_id, state = instances[-1]
    stem = instance_id or loop_name

    pid = _read_pid_file(running_dir / f"{stem}.pid")
    if pid is None:
        pid = getattr(state, "pid", None)

    if pid is None or not _process_alive(pid):
        _print_last_state(state)
        return 0

    # Fabricate missing Namespace attrs that StateFeedRenderer reads.
    for attr, default in (
        ("quiet", False),
        ("verbose", False),
        ("show_diagrams", None),
        ("clear", True),
        ("diagram_edge_labels", None),
        ("diagram_state_detail", None),
        ("diagram_scope", None),
        ("follow", False),
    ):
        if not hasattr(args, attr):
            setattr(args, attr, default)

    try:
        fsm = load_loop(loop_name, loops_dir, Logger())
    except (FileNotFoundError, ValueError) as e:
        print(f"Cannot load loop '{loop_name}': {e}")
        return 1

    try:
        loop_path = resolve_loop_path(loop_name, loops_dir)
    except FileNotFoundError:
        loop_path = None

    # Late import: tests patch StateFeedRenderer at its module-of-origin
    # (little_loops.cli.loop._helpers.StateFeedRenderer); using a function-local
    # import ensures the patch takes effect at call time.
    from little_loops.cli.loop._helpers import (
        StateFeedRenderer,
        _install_sigwinch_handler,
        _restore_sigwinch_handler,
    )

    renderer = StateFeedRenderer(
        fsm, args, loops_dir=loops_dir, loop_path=loop_path, model=fsm.llm.model
    )

    events_file = running_dir / f"{stem}.events.jsonl"

    if not events_file.exists():
        _print_last_state(state)
        return 0

    sigwinch_installed = False
    if renderer.in_pinned_mode:
        _install_sigwinch_handler()
        sigwinch_installed = True

    try:
        with open(events_file, encoding="utf-8") as ev_f:
            ev_f.seek(0, 2)
            while True:
                progressed = False
                try:
                    line = ev_f.readline()
                except FileNotFoundError:
                    break
                if line:
                    progressed = True
                    stripped = line.strip()
                    if stripped:
                        try:
                            event = json.loads(stripped)
                        except json.JSONDecodeError:
                            event = None
                        if event is not None:
                            renderer.handle_event(event)
                if not progressed:
                    if not _process_alive(pid):
                        break
                    if not events_file.exists():
                        break
                    time.sleep(0.1)
    except KeyboardInterrupt:
        return 0
    finally:
        if sigwinch_installed:
            _restore_sigwinch_handler()

    return 0

"""Shared helpers for ll-loop CLI subcommands."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli.loop import signals
from little_loops.cli.loop.feed import StateFeedRenderer, _format_history_event
from little_loops.cli.loop.header import _artifact_lines, _effort_code, _relativize_to_cwd
from little_loops.cli.output import colorize, strip_ansi, terminal_width
from little_loops.fsm.concurrency import LockManager, resolve_scope
from little_loops.fsm.loop_paths import load_loop
from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE
from little_loops.host_runner import project_child_env
from little_loops.logger import Logger

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop


# Exit code mapping for terminated_by values
EXIT_CODES: dict[str, int] = {
    "terminal": 0,
    "interrupted": 0,
    "handoff": 0,
    "max_steps": 1,
    "timeout": 1,
    "cycle_detected": 1,
    "stall_detected": 1,
    # ENH-2522: user_stopped (clean ll-loop stop) and system_signal (kernel/SIGKILL)
    # are non-zero so callers can distinguish them from graceful paths.
    "user_stopped": 1,
    "system_signal": 1,
    # BUG-3375: failure_terminal is False for this abort (it isn't a "terminal"
    # arrival), so FAILURE_TERMINAL_EXIT_CODE doesn't apply — make the exit
    # code an explicit 1 rather than relying on the .get(..., 1) default.
    "workdir_vanished": 1,
}


class _TeeWriter:
    """Wraps a stream, writing to both the original and a log file (ANSI stripped on log)."""

    def __init__(self, stream: Any, log_fh: Any) -> None:
        self._stream = stream
        self._log_fh = log_fh

    def write(self, data: str) -> int:
        n = self._stream.write(data)
        self._log_fh.write(strip_ansi(data))
        return n

    def flush(self) -> None:
        self._stream.flush()
        self._log_fh.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def print_execution_plan(fsm: FSMLoop, edge_label_colors: dict[str, str] | None = None) -> None:
    """Print dry-run execution plan."""
    _elc = edge_label_colors or {}
    _yes_color = _elc.get("yes", "32")
    tw = terminal_width()
    print(colorize(f"Execution plan for: {fsm.name}", "1"))
    print()
    print("States:")
    for name, state in fsm.states.items():
        terminal_marker = colorize(" [TERMINAL]", _yes_color) if state.terminal else ""
        print(f"  {colorize(f'[{name}]', '1')}{terminal_marker}")
        if state.action:
            if state.action_type == "prompt":
                lines = state.action.strip().splitlines()
                preview = "\n      ".join(lines[:3])
                if len(lines) > 3 or len(state.action) > 200:
                    preview += " ..."
                print(f"    action: |\n      {preview}")
            else:
                max_action = tw - 16
                action_display = (
                    state.action[:max_action] + "..."
                    if len(state.action) > max_action
                    else state.action
                )
                print(f"    action: {action_display}")
        if state.evaluate:
            print(f"    evaluate: {state.evaluate.type}")
        if state.on_yes:
            print(f"    on_yes {colorize('->', '2')} {colorize(state.on_yes, '2')}")
        if state.on_no:
            print(f"    on_no {colorize('->', '2')} {colorize(state.on_no, '2')}")
        if state.on_error:
            print(f"    on_error {colorize('->', '2')} {colorize(state.on_error, '2')}")
        if state.next:
            print(f"    next {colorize('->', '2')} {colorize(state.next, '2')}")
        if state.route:
            print("    route:")
            for verdict, target in state.route.routes.items():
                print(f"      {verdict} {colorize('->', '2')} {colorize(target, '2')}")
            if state.route.default:
                print(f"      _ {colorize('->', '2')} {colorize(state.route.default, '2')}")
    print()
    print(f"Initial state: {fsm.initial}")
    print(f"Max steps: {fsm.max_steps}")
    if fsm.max_iterations is not None:
        print(f"Max iterations: {fsm.max_iterations}")
    if fsm.timeout:
        print(f"Timeout: {fsm.timeout}s")
    if fsm.context:
        print("Context:")
        for key, value in fsm.context.items():
            print(f"  {key}: {value!r}")


def _make_instance_id(loop_name: str) -> str:
    """Generate a unique instance ID for a loop run."""
    return f"{loop_name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"


def run_background(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    subcommand: str = "run",
    instance_id: str | None = None,
) -> int:
    """Launch loop as a detached background process.

    Spawns a new process with start_new_session=True that re-executes
    the loop with --foreground-internal. The parent writes the PID file
    and returns immediately.

    Args:
        subcommand: The ll-loop subcommand to spawn ("run" or "resume").
        instance_id: Pre-resolved instance ID. When provided, skips
            _make_instance_id() allocation. Used by cmd_resume() to pass
            an already-discovered resumable instance.

    Returns:
        Exit code (0 = launched successfully).
    """
    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    # Pre-flight scope conflict check — detect conflicts before spawning the child
    # so the user gets immediate feedback instead of a silent child failure.
    logger = Logger()
    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading loop '{loop_name}': {e}", file=sys.stderr)
        return 1

    lock_manager = LockManager(loops_dir)
    # Build context for scope resolution: YAML defaults + CLI --context overrides.
    # CLI --context is only forwarded to the child process (line ~1018); we parse
    # it locally so resolve_scope() can use it for the pre-flight conflict check.
    scope_context = dict(fsm.context)
    for kv in getattr(args, "context", None) or []:
        key, _, value = kv.partition("=")
        scope_context[key.strip()] = value.strip()
    scope = resolve_scope(fsm.scope or ["."], scope_context)
    conflict = lock_manager.find_conflict(
        scope,
        caller_loop_name=fsm.name,
        caller_singleton=fsm.singleton,
    )
    if conflict and not getattr(args, "queue", False) and not getattr(args, "no_lock", False):
        print(f"Scope conflict with running loop: {conflict.loop_name}", file=sys.stderr)
        print(f"  Conflicting scope: {conflict.scope}", file=sys.stderr)
        print("  Use --queue to wait for it to finish", file=sys.stderr)
        return 1

    if instance_id is None:
        instance_id = _make_instance_id(loop_name)
    pid_file = running_dir / f"{instance_id}.pid"
    log_file = running_dir / f"{instance_id}.log"

    # Build re-exec command with --foreground-internal instead of --background
    cmd = [
        sys.executable,
        "-m",
        "little_loops.cli.loop",
        subcommand,
        loop_name,
    ]
    input_val = getattr(args, "input", None)
    if input_val is not None:
        cmd.append(input_val)
    cmd.append("--foreground-internal")
    cmd.extend(["--instance-id", instance_id])

    # Forward relevant args
    max_steps = getattr(args, "max_steps", None)
    if max_steps:
        cmd.extend(["--max-steps", str(max_steps)])
    max_iter = getattr(args, "max_iterations", None)
    if max_iter:
        cmd.extend(["--max-iterations", str(max_iter)])
    if getattr(args, "no_llm", False):
        cmd.append("--no-llm")
    run_model = getattr(args, "run_model", None)
    if run_model:
        cmd.extend(["--model", run_model])
    run_effort = getattr(args, "run_effort", None)
    if run_effort:
        cmd.extend(["--effort", run_effort])
    llm_model = getattr(args, "llm_model", None)
    if llm_model:
        cmd.extend(["--llm-model", llm_model])
    if getattr(args, "verbose", False):
        cmd.append("--verbose")
    show_diagrams_raw = getattr(args, "show_diagrams", None)
    if show_diagrams_raw is not None:
        if show_diagrams_raw is True:
            cmd.append("--show-diagrams")
        else:
            cmd.extend(["--show-diagrams", show_diagrams_raw])
    diagram_edge_labels = getattr(args, "diagram_edge_labels", None)
    if diagram_edge_labels is not None:
        cmd.extend(["--diagram-edge-labels", diagram_edge_labels])
    diagram_state_detail = getattr(args, "diagram_state_detail", None)
    if diagram_state_detail is not None:
        cmd.extend(["--diagram-state-detail", diagram_state_detail])
    diagram_scope = getattr(args, "diagram_scope", None)
    if diagram_scope is not None:
        cmd.extend(["--diagram-scope", diagram_scope])
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    if getattr(args, "queue", False):
        cmd.append("--queue")
    if getattr(args, "no_lock", False):
        cmd.append("--no-lock")
    for kv in getattr(args, "context", None) or []:
        cmd.extend(["--context", kv])
    program_md = getattr(args, "program_md", None)
    if program_md is not None:
        cmd.extend(["--program-md", str(program_md)])
    delay = getattr(args, "delay", None)
    if delay is not None:
        cmd.extend(["--delay", str(delay)])
    if getattr(args, "no_host_guard", False):
        cmd.append("--no-host-guard")
    host_guard_budget_mb = getattr(args, "host_guard_budget_mb", None)
    if host_guard_budget_mb is not None:
        cmd.extend(["--host-guard-budget-mb", str(host_guard_budget_mb)])
    handoff_threshold = getattr(args, "handoff_threshold", None)
    if handoff_threshold is not None:
        cmd.extend(["--handoff-threshold", str(handoff_threshold)])
    context_limit = getattr(args, "context_limit", None)
    if context_limit is not None:
        cmd.extend(["--context-limit", str(context_limit)])
    if getattr(args, "baseline", False):
        cmd.append("--baseline")
    baseline_skill = getattr(args, "baseline_skill", None)
    if baseline_skill is not None:
        cmd.extend(["--baseline-skill", baseline_skill])
    items = getattr(args, "items", None)
    if items is not None:
        cmd.extend(["--items", str(items)])
    if getattr(args, "cross_host", False):
        cmd.append("--cross-host")
    cost_output_json = getattr(args, "cost_output_json", None)
    if cost_output_json is not None:
        cmd.extend(["--cost-output-json", str(cost_output_json)])

    # ENH-3184 AC5: this re-exec'd `ll-loop` child re-derives its own environment
    # from scratch at each of its own spawn sites — projecting here carries no
    # guarantee across the execve boundary. Fine for today's full-inheritance
    # default; ENH-3203's deny-by-default must carry policy across explicitly.
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w") as log_fh:
        process = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
            env=project_child_env(),
        )

    pid_file.write_text(str(process.pid))
    print(
        f"Loop {colorize(loop_name, '1')} started in background (PID: {colorize(str(process.pid), '2')})"
    )
    print(f"  Log: {colorize(str(log_file), '2')}")
    print(f"  Status: {colorize(f'll-loop status {loop_name}', '2')}")
    print(f"  Stop:   {colorize(f'll-loop stop {loop_name}', '2')}")
    return 0


def run_foreground(
    executor: Any,
    fsm: FSMLoop,
    args: argparse.Namespace,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    mode: str = "run",
    instance_id: str | None = None,
    running_dir: Path | None = None,
    loop_path: Path | None = None,
    model: str | None = None,
    effort: str | None = None,
    show_input: bool = True,
    cost_output_json: Path | None = None,
) -> int:
    """Run loop with progress display.

    Args:
        highlight_color: ANSI SGR code for the active FSM state highlight in verbose mode.
        edge_label_colors: Optional label→SGR-code mapping for transition edge labels.
        badges: Optional glyph-key→string mapping for state type badges in FSM diagrams.
        mode: ``"run"`` (default) calls ``executor.run()``; ``"resume"`` calls
            ``executor.resume()`` so a resumed loop reuses the same display-wiring
            path as a fresh run (BUG-1645). In ``"resume"`` mode a ``None`` result
            from ``executor.resume()`` is treated as "nothing to resume": a warning
            is logged and exit code 1 is returned before any alt-screen sequences
            are emitted.

        instance_id: When provided and not a background-spawned child
            (``foreground_internal=False``), stdout/stderr are teed to
            ``{running_dir}/{instance_id}.log`` with ANSI sequences stripped.
        running_dir: Directory for the log file. Defaults to ``.running``
            alongside the loops directory.
    Returns:
        Exit code (0 = success).
    """
    if mode not in ("run", "resume"):
        raise ValueError(f"run_foreground: invalid mode {mode!r}; expected 'run' or 'resume'")

    # FEAT-3116: task-identity env contract. Set process-wide (not threaded
    # through project_child_env's extra=) so every downstream host spawn in
    # this loop run — evaluators.py, runners.py, handoff_handler.py — picks
    # it up via project_child_env()'s default os.environ.copy() inheritance,
    # without threading a new kwarg through every one of those call sites.
    if instance_id is not None:
        os.environ["LL_LOOP_RUN_ID"] = instance_id

    _orig_stdout = sys.stdout
    _orig_stderr = sys.stderr
    _log_fh: Any = None
    if instance_id is not None and not getattr(args, "foreground_internal", False):
        _log_path = (running_dir or Path(".running")) / f"{instance_id}.log"
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(_log_path, "w")
        sys.stdout = _TeeWriter(_orig_stdout, _log_fh)  # type: ignore[assignment]
        sys.stderr = _TeeWriter(_orig_stderr, _log_fh)  # type: ignore[assignment]

    try:
        # Create the state feed renderer — encapsulates display state and event handling.
        renderer = StateFeedRenderer(
            fsm,
            args,
            highlight_color=highlight_color,
            edge_label_colors=edge_label_colors,
            badges=badges,
            loops_dir=getattr(executor, "loops_dir", Path(".")),
            loop_path=loop_path,
            model=model,
            effort=effort,
            show_input=show_input,
        )
        if not renderer.quiet:
            print(f"Running loop: {colorize(fsm.name, '1')}")
            print(f"Max steps: {colorize(str(fsm.max_steps), '2')}")
            if fsm.max_iterations is not None:
                print(f"Max iterations: {colorize(str(fsm.max_iterations), '2')}")
            for key, value in _artifact_lines(fsm, loop_path):
                print(f"  {key}: {colorize(value, '2')}")
            if model is not None:
                model_line = model if effort is None else f"{model} {_effort_code(effort)}"
                print(f"  model: {colorize(model_line, '2')}")
            print()

        # Wire progress display via the EventBus on PersistentExecutor
        if not renderer.quiet or renderer.show_diagrams:
            if hasattr(executor, "event_bus"):
                executor.event_bus.register(renderer.handle_event)
            else:
                executor._on_event = renderer.handle_event

        # Capture the last failure-relevant message from the event stream so the
        # completion summary can surface *why* a run failed. This is the only reliable
        # source: on on_error / exception routes the executor leaves prev_result and
        # captured empty, and alt-screen teardown or non-verbose mode hide the live
        # output. action_error carries interpolation/exception reasons; a non-zero
        # action_complete carries the failing state's stdout.
        _failure_capture: dict[str, str] = {}

        def _capture_failure(event: dict[str, Any]) -> None:
            ev = event.get("event")
            if ev == "action_error" and event.get("error"):
                _failure_capture["error"] = str(event["error"])
            elif ev == "action_complete" and event.get("exit_code") not in (0, None):
                out = event.get("output") or event.get("output_preview") or ""
                if out:
                    _failure_capture["output"] = str(out)

        if not renderer.quiet:
            if hasattr(executor, "event_bus"):
                executor.event_bus.register(_capture_failure)
            else:
                _prev_capture_cb = executor._on_event

                def _chained_capture(event: dict[str, Any]) -> None:
                    if _prev_capture_cb:
                        _prev_capture_cb(event)
                    _capture_failure(event)

                executor._on_event = _chained_capture

        # Wire follow mode — streams history-formatted events independently of quiet
        if getattr(args, "follow", False):
            tw = terminal_width()
            _verbose = renderer.verbose

            def _follow_callback(event: dict[str, Any]) -> None:
                line = _format_history_event(event, verbose=_verbose, width=tw)
                if line is not None:
                    print(line, flush=True)

            if hasattr(executor, "event_bus"):
                executor.event_bus.register(_follow_callback)
            else:
                _prev_on_event = executor._on_event

                def _chained(event: dict[str, Any]) -> None:
                    if _prev_on_event:
                        _prev_on_event(event)
                    _follow_callback(event)

                executor._on_event = _chained

        # Enter alternate screen buffer when showing diagrams with clear to prevent
        # scrollback contamination from diagrams taller than the terminal height.
        if renderer.show_diagrams and renderer.clear_screen and sys.stdout.isatty():
            signals._using_alt_screen = True
            print("\033[?1049h\033[H", end="", flush=True)
            signals._install_sigwinch_handler()

        try:
            if mode == "resume":
                result = executor.resume()
                # "Nothing to resume" path: no run actually executed, so don't fall
                # through to completion-line formatting. Exit cleanly with code 1.
                if result is None:
                    Logger().warning(f"Nothing to resume for: {fsm.name}")
                    return 1
            else:
                result = executor.run()
        finally:
            # Remember whether we were in the alt-screen so the summary block can
            # decide whether the failing state's output still needs re-printing
            # (alt-screen teardown wipes it from scrollback).
            _was_alt_screen = signals._using_alt_screen
            if signals._using_alt_screen:
                # Reset DECSTBM scroll region BEFORE exiting alt-screen, otherwise
                # the main buffer is left with a restricted scroll region (one of
                # the Success Metrics for ENH-1642).
                print("\033[r", end="", flush=True)
                print("\033[?1049l", end="", flush=True)
                signals._using_alt_screen = False
            signals._restore_sigwinch_handler()

        # FEAT-3309: deliberately unguarded — --quiet suppresses live decoration,
        # not the one line naming the file the run's loop→artifact handoff produced.
        promoted_artifact = fsm.context.get("promoted_artifact")
        if promoted_artifact:
            print(
                f"Promoted artifact: {colorize(_relativize_to_cwd(str(promoted_artifact)), '32')}"
            )

        if not renderer.quiet:
            print()
            duration_sec = result.duration_ms / 1000
            if duration_sec < 60:
                duration_str = f"{duration_sec:.1f}s"
            else:
                minutes = int(duration_sec // 60)
                seconds = duration_sec % 60
                duration_str = f"{minutes}m {seconds:.0f}s"
            # ENH-2814: colour only genuine success green. Failure-ness comes
            # from the terminal state's own `failure:` flag (ExecutionResult
            # .failure_terminal), not from re-testing the state's name.
            _is_success = (
                result.terminated_by in ("terminal", "interrupted", "handoff")
                and not result.failure_terminal
            )
            if _is_success:
                state_colored = colorize(result.final_state, "32")
            else:
                state_colored = colorize(result.final_state, "38;5;208")

            # Surface the failing state's output as the failure reason. It is otherwise
            # invisible: the alt-screen wipes it on teardown, and in non-verbose mode the
            # per-state stdout is never printed inline at all. Skip only the verbose
            # non-alt-screen case, where the live renderer already echoed it.
            if not _is_success and (_was_alt_screen or not renderer.verbose):
                reason_text = (
                    _failure_capture.get("error")
                    or _failure_capture.get("output")
                    or result.error
                    or ""
                ).strip()
                if reason_text:
                    print()
                    print(colorize("Failure reason:", "1"))
                    for _line in reason_text.splitlines()[-40:]:  # cap to bound scrollback
                        print(colorize("│ " + _line, "90"))

            completion_prefix = "Resumed and completed" if mode == "resume" else "Loop completed"
            rejection_count = 0
            for _t in getattr(getattr(executor, "event_bus", None), "_transports", []):
                if hasattr(_t, "get_stats"):
                    rejection_count += _t.get_stats().get("client_rejections", 0)
            suffix = f", {rejection_count} client rejections" if rejection_count > 0 else ""

            # Print per-state token/cost table if usage data was collected
            run_dir = fsm.context.get("run_dir", "")
            if run_dir:
                try:
                    _print_usage_summary(
                        Path(run_dir) / "usage.jsonl",
                        cost_output_json=cost_output_json,
                    )
                except Exception:
                    pass  # Non-fatal: display failure shouldn't block exit

            print(
                f"{completion_prefix}: {state_colored} ({result.iterations} iterations, {duration_str}{suffix})"
            )

            # FEAT-1822: Print A/B summary if baseline was enabled
            if run_dir:
                ab_path = Path(run_dir) / "ab.json"
                if ab_path.exists():
                    try:
                        _print_ab_summary(ab_path)
                    except Exception:
                        pass  # Non-fatal: display failure shouldn't block exit

                    # ENH-2086: Cross-host validation when --cross-host was requested
                    baseline_ctx = fsm.context.get("_baseline") or {}
                    if baseline_ctx.get("cross_host"):
                        loop_name = getattr(args, "loop", "")
                        try:
                            _run_cross_host_validation(
                                args,
                                loop_path,
                                Path(run_dir),
                                ab_path,
                                loop_name,
                            )
                        except Exception:
                            pass  # Non-fatal

        if result.failure_terminal:
            return FAILURE_TERMINAL_EXIT_CODE
        return EXIT_CODES.get(result.terminated_by, 1)
    finally:
        sys.stdout = _orig_stdout
        sys.stderr = _orig_stderr
        if _log_fh is not None:
            _log_fh.close()


def _print_usage_summary(usage_path: Path, cost_output_json: Path | None = None) -> None:
    """Print per-state token usage summary from usage.jsonl.

    Args:
        usage_path: Path to usage.jsonl written by PersistentExecutor
        cost_output_json: Optional path to also write the stable-JSON
            report (ENH-2477). Write failures are non-fatal: a missing
            parent dir or unwritable path must not block the run's
            normal exit path.
    """
    from little_loops.fsm.cost_graph import CostReport

    if not usage_path.exists():
        return
    report = CostReport.from_usage_jsonl(usage_path)
    if not report.states:
        return

    print()
    print(report.table())

    if cost_output_json is not None:
        try:
            report.write_json(cost_output_json)
        except OSError:
            pass  # Non-fatal: a failed write shouldn't block the run


def _print_ab_summary(ab_path: Path) -> None:
    """Print A/B comparison summary from ab.json.

    Args:
        ab_path: Path to ab.json file written by the executor
    """
    from little_loops.ab_writer import read_ab_json
    from little_loops.stats import paired_direction, wilson_ci

    results = read_ab_json(str(ab_path.parent))
    if results is None or not results.per_item:
        return

    n = len(results.per_item)
    harness_pct = results.harness_pass_rate * 100
    baseline_pct = results.baseline_pass_rate * 100
    delta_pct = results.delta * 100

    k_harness = sum(1 for item in results.per_item if item.get("harness_pass", False))
    k_baseline = sum(1 for item in results.per_item if item.get("baseline_pass", False))
    h_lo, h_hi = wilson_ci(k_harness, n)
    b_lo, b_hi = wilson_ci(k_baseline, n)

    tokens_ratio = (
        results.median_tokens_harness / results.median_tokens_baseline
        if results.median_tokens_baseline > 0
        else 0
    )
    dur_ratio = (
        results.median_duration_harness / results.median_duration_baseline
        if results.median_duration_baseline > 0
        else 0
    )

    def _fmt_dur(ms: float) -> str:
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        else:
            return f"{ms / 60000:.1f}m"

    tokens_dir = "+" if tokens_ratio > 1 else "-"
    dur_dir = "+" if dur_ratio > 1 else "-"

    print()
    print(f"A/B Summary (n={n})")
    print(f"  Harness pass-rate:  {harness_pct:.0f}%  [{h_lo:.2f}, {h_hi:.2f}]")
    print(f"  Baseline pass-rate: {baseline_pct:.0f}%  [{b_lo:.2f}, {b_hi:.2f}]")
    print(f"  Delta:              {delta_pct:+.0f}%")
    print()
    print(
        f"  Median tokens:      harness={results.median_tokens_harness}  "
        f"baseline={results.median_tokens_baseline}  "
        f"({tokens_dir}{abs(tokens_ratio - 1) * 100:.0f}%)"
    )
    print(
        f"  Median duration:    harness={_fmt_dur(results.median_duration_harness)}  "
        f"baseline={_fmt_dur(results.median_duration_baseline)}  "
        f"({dur_dir}{abs(dur_ratio - 1) * 100:.0f}%)"
    )

    # Verdict line — paired sign test on discordant items (ENH-3298); the raw
    # delta sign asserts a winner even when the two Wilson CIs overlap almost
    # entirely, so the direction must instead be established by the CI on
    # the discordant split itself.
    direction, b, c = paired_direction(results.per_item)
    discordant = b + c
    if direction == "inconclusive":
        quality_verdict = f"inconclusive at n={n} ({discordant} discordant pairs)"
    else:
        favor = b if direction == "harness" else c
        quality_verdict = (
            f"{direction} wins on quality ({favor}/{discordant} discordant pairs favor {direction})"
        )
    cost_verdict = (
        f"costs ~{abs(tokens_ratio - 1) * 100:.0f}% more tokens"
        if tokens_ratio > 1
        else (
            f"costs ~{abs(tokens_ratio - 1) * 100:.0f}% fewer tokens"
            if tokens_ratio < 1
            else "same token cost"
        )
    )
    print(f"  Verdict:            {quality_verdict}, {cost_verdict}")
    print()
    print(f"Per-item: {ab_path}")


def _run_cross_host_validation(
    args: argparse.Namespace,
    loop_path: Path | None,
    primary_run_dir: Path,
    primary_ab_path: Path,
    loop_name: str,
) -> None:
    """Re-run the loop on a second available host and print a cross-host comparison.

    Identifies a second host via _PROBE_ORDER, runs the same baseline trial with
    LL_HOST_CLI overridden, then calls _print_cross_host_table if both ab.json
    files are available.
    """
    import shutil

    from little_loops.host_runner import _PROBE_ORDER, HostNotConfigured, resolve_host

    # Identify the current (primary) host
    try:
        primary_host = resolve_host().name
    except HostNotConfigured:
        primary_host = None

    # Find a second available host different from the primary
    second_host: str | None = None
    for host_name, binary in _PROBE_ORDER:
        if host_name == primary_host:
            continue
        if shutil.which(binary) is not None:
            second_host = host_name
            break

    if second_host is None:
        print("\nCross-host: only one host available — skipping cross-host validation.")
        return

    print(f"\nCross-host: running {loop_name!r} on {second_host}...")

    # Build the second-host command
    cmd = ["ll-loop", "run", "--baseline"]
    baseline_skill = getattr(args, "baseline_skill", None)
    if baseline_skill is not None:
        cmd.extend(["--baseline-skill", baseline_skill])
    items = getattr(args, "items", None)
    if items is not None:
        cmd.extend(["--items", str(items)])
    cmd.append(loop_name)

    env = project_child_env(extra={"LL_HOST_CLI": second_host})

    before = time.time()
    result = subprocess.run(cmd, env=env)

    if result.returncode != 0:
        print(
            f"\nCross-host: second-host run ({second_host}) failed "
            f"(exit {result.returncode}) — no comparison available."
        )
        return

    # Find the second run's ab.json: newest file under the same runs directory
    # that appeared after the second run started and differs from the primary.
    runs_dir = primary_run_dir.parent
    candidates = sorted(
        runs_dir.glob("*/ab.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    second_ab_path = next(
        (p for p in candidates if p != primary_ab_path and p.stat().st_mtime >= before),
        None,
    )

    if second_ab_path is None:
        print(
            "\nCross-host: second-host run completed but no ab.json found — "
            "no comparison available."
        )
        return

    from little_loops.ab_writer import read_ab_json

    primary_results = read_ab_json(str(primary_run_dir))
    second_results = read_ab_json(str(second_ab_path.parent))

    if primary_results is None or second_results is None:
        return

    _print_cross_host_table(primary_host or "primary", primary_results, second_host, second_results)


def _print_cross_host_table(
    host1: str,
    results1: Any,
    host2: str,
    results2: Any,
) -> None:
    """Print a cross-host pass-rate comparison table with Wilson 95% CIs."""
    from little_loops.stats import paired_direction, wilson_ci

    def _host_stats(results: Any) -> tuple[int, int, float, float, float]:
        n = len(results.per_item)
        k = sum(1 for item in results.per_item if item.get("harness_pass", False))
        rate = results.harness_pass_rate * 100
        lo, hi = wilson_ci(k, n) if n > 0 else (0.0, 0.0)
        return n, k, rate, lo, hi

    n1, _k1, rate1, lo1, hi1 = _host_stats(results1)
    n2, _k2, rate2, lo2, hi2 = _host_stats(results2)

    print()
    print("Cross-host Comparison")
    print(f"  {'Host':<20}  {'Pass rate':>10}  {'95% CI':>18}  {'n':>5}")
    print(f"  {'-' * 20}  {'-' * 10}  {'-' * 18}  {'-' * 5}")
    print(f"  {host1:<20}  {rate1:>9.0f}%  [{lo1:.2f}, {hi1:.2f}]  {n1:>5}")
    print(f"  {host2:<20}  {rate2:>9.0f}%  [{lo2:.2f}, {hi2:.2f}]  {n2:>5}")

    # Warn on ordering reversal only when both runs independently establish a
    # direction (ENH-3298) — otherwise a noisy disagreement between two
    # inconclusive runs prints identically to a genuine host-specific effect.
    direction1, _b1, _c1 = paired_direction(results1.per_item)
    direction2, _b2, _c2 = paired_direction(results2.per_item)
    print()
    if direction1 != "inconclusive" and direction2 != "inconclusive" and direction1 != direction2:
        print(
            f"  ⚠ Ordering reversal: {host1} shows {direction1} ahead, "
            f"{host2} shows {direction2} ahead. "
            "Improvement may be host-specific."
        )
    elif direction1 != direction2:
        print(
            f"  Note: ordering differs between hosts, but neither run separates from "
            f"chance (n={n1}, n={n2}) — not evidence of a host-specific effect."
        )
    print()

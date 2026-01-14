# FEAT-047: ll-loop CLI Tool

## Summary

Implement the `ll-loop` command-line tool for running, managing, and debugging FSM loops.

## Priority

P1 - Primary user interface for loop execution

## Dependencies

- FEAT-040: FSM Schema Definition and Validation
- FEAT-041: Paradigm Compilers
- FEAT-045: FSM Executor Core
- FEAT-046: State Persistence and Events

## Blocked By

- FEAT-045, FEAT-046

## Description

The `ll-loop` CLI is the primary interface for executing FSM loops. It supports:

1. **Running loops** - `ll-loop fix-types` or `ll-loop run fix-types`
2. **Validation** - `ll-loop validate fix-types`
3. **Compilation** - `ll-loop compile convergence.yaml`
4. **Management** - `ll-loop list`, `ll-loop status`, `ll-loop stop`, `ll-loop resume`
5. **History** - `ll-loop history fix-types`

### Files to Create

```
scripts/little_loops/cli/
└── ll_loop.py
```

## Technical Details

### CLI Structure

```bash
# Primary usage - loop name resolves to .loops/<name>.yaml
ll-loop test-analyze-fix
ll-loop fix-types --max-iterations 5
ll-loop lint-cycle --background

# Explicit run subcommand
ll-loop run fix-types --dry-run
ll-loop run .loops/fix-types.yaml    # Full path also works

# Compile paradigm to FSM
ll-loop compile convergence.yaml -o .loops/convergence.fsm.yaml

# Validate loop definition
ll-loop validate fix-types

# Manage running loops
ll-loop list
ll-loop list --running
ll-loop status fix-types
ll-loop stop fix-types
ll-loop resume fix-types

# History
ll-loop history fix-types
```

### Implementation

```python
# ll_loop.py
import argparse
import sys
from pathlib import Path

from little_loops.fsm.schema import FSMLoop, load_and_validate
from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.persistence import (
    PersistentExecutor,
    StatePersistence,
    list_running_loops,
    get_loop_history,
)


def main():
    parser = argparse.ArgumentParser(
        prog="ll-loop",
        description="Execute FSM-based automation loops",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Default: run (positional loop name without subcommand)
    parser.add_argument(
        "loop",
        nargs="?",
        help="Loop name or path to run (shorthand for 'll-loop run <loop>')",
    )

    # Run subcommand
    run_parser = subparsers.add_parser("run", help="Run a loop")
    run_parser.add_argument("loop", help="Loop name or path")
    run_parser.add_argument("--background", "-b", action="store_true", help="Run as daemon")
    run_parser.add_argument("--dry-run", action="store_true", help="Show execution plan")
    run_parser.add_argument("--queue", action="store_true", help="Wait for conflicting loops")
    run_parser.add_argument("--max-iterations", "-n", type=int, help="Override iteration limit")
    run_parser.add_argument("--no-llm", action="store_true", help="Disable LLM evaluation")
    run_parser.add_argument("--llm-model", help="Override LLM model")

    # Compile subcommand
    compile_parser = subparsers.add_parser("compile", help="Compile paradigm to FSM")
    compile_parser.add_argument("input", help="Input paradigm YAML")
    compile_parser.add_argument("-o", "--output", help="Output FSM YAML")

    # Validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Validate loop definition")
    validate_parser.add_argument("loop", help="Loop name or path")

    # List subcommand
    list_parser = subparsers.add_parser("list", help="List loops")
    list_parser.add_argument("--running", action="store_true", help="Only show running loops")

    # Status subcommand
    status_parser = subparsers.add_parser("status", help="Show loop status")
    status_parser.add_argument("loop", help="Loop name")

    # Stop subcommand
    stop_parser = subparsers.add_parser("stop", help="Stop a running loop")
    stop_parser.add_argument("loop", help="Loop name")

    # Resume subcommand
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted loop")
    resume_parser.add_argument("loop", help="Loop name")

    # History subcommand
    history_parser = subparsers.add_parser("history", help="Show loop execution history")
    history_parser.add_argument("loop", help="Loop name")
    history_parser.add_argument("--tail", "-n", type=int, default=50, help="Last N events")

    # Add common flags to run-like commands
    for p in [parser, run_parser]:
        p.add_argument("--max-iterations", "-n", type=int, help="Override iteration limit")

    args = parser.parse_args()

    # Handle default run case (no subcommand)
    if args.command is None and args.loop:
        return cmd_run(args.loop, args)

    # Dispatch to subcommand
    commands = {
        "run": lambda: cmd_run(args.loop, args),
        "compile": lambda: cmd_compile(args),
        "validate": lambda: cmd_validate(args.loop),
        "list": lambda: cmd_list(args),
        "status": lambda: cmd_status(args.loop),
        "stop": lambda: cmd_stop(args.loop),
        "resume": lambda: cmd_resume(args.loop),
        "history": lambda: cmd_history(args.loop, args.tail),
    }

    if args.command in commands:
        return commands[args.command]()

    parser.print_help()
    return 1


def resolve_loop_path(name_or_path: str) -> Path:
    """Resolve loop name to path."""
    path = Path(name_or_path)
    if path.exists():
        return path
    # Try .loops/<name>.yaml
    loops_path = Path(".loops") / f"{name_or_path}.yaml"
    if loops_path.exists():
        return loops_path
    raise FileNotFoundError(f"Loop not found: {name_or_path}")


def cmd_run(loop: str, args) -> int:
    """Run a loop."""
    try:
        path = resolve_loop_path(loop)
        fsm = load_and_validate(path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        return 1

    # Apply overrides
    if hasattr(args, "max_iterations") and args.max_iterations:
        fsm.max_iterations = args.max_iterations
    if hasattr(args, "no_llm") and args.no_llm:
        fsm.llm.enabled = False
    if hasattr(args, "llm_model") and args.llm_model:
        fsm.llm.model = args.llm_model

    # Dry run
    if hasattr(args, "dry_run") and args.dry_run:
        print_execution_plan(fsm)
        return 0

    # Execute
    executor = PersistentExecutor(fsm)

    if hasattr(args, "background") and args.background:
        return run_background(executor)

    return run_foreground(executor)


def run_foreground(executor: PersistentExecutor) -> int:
    """Run loop with progress display."""
    fsm = executor.fsm

    print(f"Running loop: {fsm.name}")
    print(f"Max iterations: {fsm.max_iterations}")
    print()

    # Custom event callback for progress display
    def display_progress(event: dict):
        event_type = event["event"]

        if event_type == "state_enter":
            iteration = event["iteration"]
            state = event["state"]
            print(f"[{iteration}/{fsm.max_iterations}] {state}", end="")

        elif event_type == "action_start":
            action = event["action"]
            print(f" → {action[:60]}...")

        elif event_type == "evaluate":
            verdict = event["verdict"]
            confidence = event.get("confidence")
            if confidence:
                print(f"       ✓ {verdict} (confidence: {confidence:.2f})")
            else:
                symbol = "✓" if verdict == "success" else "✗"
                print(f"       {symbol} {verdict}")

        elif event_type == "route":
            print(f"       → {event['to']}")

    # Wrap persistence callback
    original_callback = executor._handle_event
    def combined_callback(event):
        original_callback(event)
        display_progress(event)
    executor._handle_event = combined_callback

    result = executor.run()

    print()
    print(f"Loop completed: {result.final_state} ({result.iterations} iterations, {result.duration_ms}ms)")

    return 0 if result.terminated_by == "terminal" else 1


def cmd_compile(args) -> int:
    """Compile paradigm YAML to FSM."""
    import yaml

    with open(args.input) as f:
        spec = yaml.safe_load(f)

    fsm = compile_paradigm(spec)

    output = args.output or args.input.replace(".yaml", ".fsm.yaml")
    with open(output, "w") as f:
        yaml.dump(fsm, f, default_flow_style=False)

    print(f"Compiled to: {output}")
    return 0


def cmd_validate(loop: str) -> int:
    """Validate a loop definition."""
    try:
        path = resolve_loop_path(loop)
        fsm = load_and_validate(path)
        print(f"✓ {loop} is valid")
        print(f"  States: {', '.join(fsm.states.keys())}")
        print(f"  Initial: {fsm.initial}")
        print(f"  Max iterations: {fsm.max_iterations}")
        return 0
    except Exception as e:
        print(f"✗ {loop} is invalid: {e}", file=sys.stderr)
        return 1


def cmd_list(args) -> int:
    """List loops."""
    loops_dir = Path(".loops")

    if args.running:
        states = list_running_loops(loops_dir)
        if not states:
            print("No running loops")
            return 0
        print("Running loops:")
        for state in states:
            print(f"  {state.loop_name}: {state.current_state} (iteration {state.iteration})")
        return 0

    # List all loop files
    if not loops_dir.exists():
        print("No .loops/ directory found")
        return 1

    yaml_files = list(loops_dir.glob("*.yaml"))
    if not yaml_files:
        print("No loops defined")
        return 0

    print("Available loops:")
    for path in sorted(yaml_files):
        print(f"  {path.stem}")
    return 0


def cmd_status(loop: str) -> int:
    """Show loop status."""
    persistence = StatePersistence(loop)
    state = persistence.load_state()

    if state is None:
        print(f"No state found for: {loop}")
        return 1

    print(f"Loop: {state.loop_name}")
    print(f"Status: {state.status}")
    print(f"Current state: {state.current_state}")
    print(f"Iteration: {state.iteration}")
    print(f"Started: {state.started_at}")
    print(f"Updated: {state.updated_at}")
    return 0


def cmd_stop(loop: str) -> int:
    """Stop a running loop."""
    # This would require inter-process communication
    # For now, just mark the state as interrupted
    persistence = StatePersistence(loop)
    state = persistence.load_state()

    if state is None or state.status != "running":
        print(f"Loop not running: {loop}")
        return 1

    state.status = "interrupted"
    persistence.save_state(state)
    print(f"Marked {loop} as interrupted")
    return 0


def cmd_resume(loop: str) -> int:
    """Resume an interrupted loop."""
    try:
        path = resolve_loop_path(loop)
        fsm = load_and_validate(path)
    except Exception as e:
        print(f"Error loading loop: {e}", file=sys.stderr)
        return 1

    executor = PersistentExecutor(fsm)
    result = executor.resume()

    if result is None:
        print(f"Nothing to resume for: {loop}")
        return 1

    print(f"Resumed and completed: {result.final_state}")
    return 0


def cmd_history(loop: str, tail: int) -> int:
    """Show loop history."""
    events = get_loop_history(loop)

    if not events:
        print(f"No history for: {loop}")
        return 1

    # Show last N events
    for event in events[-tail:]:
        ts = event.get("ts", "")[:19]  # Truncate to seconds
        event_type = event["event"]
        details = {k: v for k, v in event.items() if k not in ("event", "ts")}
        print(f"{ts} {event_type}: {details}")

    return 0


def print_execution_plan(fsm: FSMLoop):
    """Print dry-run execution plan."""
    print(f"Execution plan for: {fsm.name}")
    print()
    print("States:")
    for name, state in fsm.states.items():
        print(f"  [{name}]")
        if state.action:
            print(f"    action: {state.action}")
        if state.evaluate:
            print(f"    evaluate: {state.evaluate.type}")
        if state.on_success:
            print(f"    on_success → {state.on_success}")
        if state.on_failure:
            print(f"    on_failure → {state.on_failure}")
        if state.next:
            print(f"    next → {state.next}")
        if state.terminal:
            print(f"    [TERMINAL]")
    print()
    print(f"Initial state: {fsm.initial}")
    print(f"Max iterations: {fsm.max_iterations}")
    if fsm.timeout:
        print(f"Timeout: {fsm.timeout}s")


if __name__ == "__main__":
    sys.exit(main())
```

### Progress Display

```
$ ll-loop fix-types
Running loop: fix-types
Max iterations: 20

[1/20] check → mypy src/...
       ✗ failure
       → fix
[1/20] fix → /ll:manage_issue bug fix...
       ✓ success (confidence: 0.92)
       → verify
[1/20] verify → pytest tests/...
       ✓ success
       → done

Loop completed: done (1 iteration, 2m 34s)
```

## Acceptance Criteria

- [ ] `ll-loop <name>` runs loop from `.loops/<name>.yaml`
- [ ] `ll-loop run <name>` explicit run subcommand works
- [ ] `ll-loop run <path>` accepts full path to YAML
- [ ] `--background` runs loop as daemon (basic implementation)
- [ ] `--dry-run` shows execution plan without running
- [ ] `--max-iterations` overrides loop limit
- [ ] `--no-llm` disables LLM evaluation
- [ ] `ll-loop compile` compiles paradigm YAML to FSM
- [ ] `ll-loop validate` checks loop definition
- [ ] `ll-loop list` shows all loops in `.loops/`
- [ ] `ll-loop list --running` shows only running loops
- [ ] `ll-loop status <name>` shows current state
- [ ] `ll-loop stop <name>` marks loop as interrupted
- [ ] `ll-loop resume <name>` continues from saved state
- [ ] `ll-loop history <name>` shows event log
- [ ] Progress display shows iteration, state, verdict, routing
- [ ] Exit code 0 on terminal state, 1 on error/max_iterations

## Testing Requirements

```python
# tests/cli/test_ll_loop.py
class TestLLLoopCLI:
    def test_run_simple_loop(self, tmp_path, mock_action_runner):
        """ll-loop <name> executes loop."""
        # Create test loop
        loop_yaml = tmp_path / ".loops" / "test.yaml"
        loop_yaml.parent.mkdir()
        loop_yaml.write_text("""
name: test
initial: check
states:
  check:
    action: "true"
    on_success: done
  done:
    terminal: true
""")

        result = run_cli(["test"], cwd=tmp_path)
        assert result.exit_code == 0

    def test_dry_run(self, tmp_path):
        """--dry-run shows plan without executing."""
        # ...

    def test_validate_valid_loop(self, tmp_path):
        """validate command succeeds for valid loop."""
        # ...

    def test_validate_invalid_loop(self, tmp_path):
        """validate command fails for invalid loop."""
        # ...

    def test_list_loops(self, tmp_path):
        """list shows all loops."""
        # ...

    def test_history(self, tmp_path):
        """history shows event log."""
        # ...
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "CLI Interface"

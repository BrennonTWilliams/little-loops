# FEAT-047: ll-loop CLI Tool - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-047-ll-loop-cli-tool.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The FSM infrastructure is fully implemented and tested:
- `scripts/little_loops/fsm/executor.py` - FSMExecutor with event callbacks (line 172-541)
- `scripts/little_loops/fsm/persistence.py` - PersistentExecutor, StatePersistence, list_running_loops, get_loop_history (line 1-394)
- `scripts/little_loops/fsm/validation.py` - load_and_validate function (line 301-354)
- `scripts/little_loops/fsm/compilers.py` - compile_paradigm function (line 51-90)
- `scripts/little_loops/fsm/schema.py` - FSMLoop and StateConfig dataclasses

### Key Discoveries
- Entry points defined in `scripts/pyproject.toml:35-38` following pattern `ll-<cmd> = "little_loops.cli:main_<cmd>"`
- Existing CLI pattern in `scripts/little_loops/cli.py` uses argparse with RawDescriptionHelpFormatter and epilog examples
- Logger and logo utilities available at `little_loops.logger` and `little_loops.logo`
- PersistentExecutor handles all state persistence via event callbacks (persistence.py:239-261)
- ExecutionResult contains final_state, iterations, terminated_by, duration_ms, captured, error fields

## Desired End State

A fully functional `ll-loop` CLI tool that can:
1. Run FSM loops from `.loops/<name>.yaml`
2. Compile paradigm YAML to FSM
3. Validate loop definitions
4. List available and running loops
5. Show loop status, history, and manage execution (stop/resume)
6. Display real-time progress during execution

### How to Verify
- `ll-loop --help` shows all commands with examples
- `ll-loop validate <name>` validates a loop definition
- `ll-loop list` shows available loops in `.loops/`
- `ll-loop <name> --dry-run` shows execution plan without running
- Tests pass: `python -m pytest scripts/tests/test_ll_loop.py`

## What We're NOT Doing

- **Not implementing `--background` daemon mode** - Basic implementation only (flag recognized but runs foreground)
- **Not implementing `--queue` mode** - Concurrency/locking deferred to future
- **Not creating `.loops/` directory or example loops** - User creates their own
- **Not adding signal handlers** - Graceful shutdown deferred (Ctrl+C kills process)

## Solution Approach

Add `main_loop()` function to existing `cli.py` following the established pattern. Use argparse subparsers for the various commands (run, compile, validate, list, status, stop, resume, history). Import and use the existing FSM modules directly.

## Implementation Phases

### Phase 1: CLI Structure and Entry Point

#### Overview
Set up the argparse structure, entry point registration, and basic infrastructure.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Changes**: Add entry point for ll-loop

```toml
[project.scripts]
ll-auto = "little_loops.cli:main_auto"
ll-parallel = "little_loops.cli:main_parallel"
ll-messages = "little_loops.cli:main_messages"
ll-loop = "little_loops.cli:main_loop"
```

**File**: `scripts/little_loops/cli.py`
**Changes**: Add main_loop function with argparse structure

```python
def main_loop() -> int:
    """Entry point for ll-loop command.

    Execute FSM-based automation loops.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        prog="ll-loop",
        description="Execute FSM-based automation loops",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fix-types              # Run loop from .loops/fix-types.yaml
  %(prog)s run fix-types --dry-run  # Show execution plan
  %(prog)s validate fix-types     # Validate loop definition
  %(prog)s compile paradigm.yaml  # Compile paradigm to FSM
  %(prog)s list                   # List available loops
  %(prog)s list --running         # List running loops
  %(prog)s status fix-types       # Show loop status
  %(prog)s stop fix-types         # Stop a running loop
  %(prog)s resume fix-types       # Resume interrupted loop
  %(prog)s history fix-types      # Show execution history
""",
    )

    subparsers = parser.add_subparsers(dest="command")
    # ... subcommand setup
```

#### Success Criteria

**Automated Verification**:
- [ ] `pip install -e "./scripts[dev]"` succeeds
- [ ] `ll-loop --help` displays help text with examples
- [ ] `ll-loop run --help` displays run subcommand help

---

### Phase 2: Core Commands (run, validate, list)

#### Overview
Implement the main functionality: running loops, validating definitions, and listing loops.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Implement resolve_loop_path, cmd_run, cmd_validate, cmd_list functions

Key implementation details:

1. **resolve_loop_path(name_or_path: str) -> Path**:
   - If path exists directly, return it
   - Otherwise try `.loops/<name>.yaml`
   - Raise FileNotFoundError if neither exists

2. **cmd_run(args) -> int**:
   - Resolve loop path
   - Call `load_and_validate()` from fsm.validation
   - Apply CLI overrides (max_iterations, no_llm, llm_model)
   - Handle `--dry-run` with print_execution_plan()
   - Create PersistentExecutor and run with progress display
   - Return 0 if terminal, 1 otherwise

3. **cmd_validate(args) -> int**:
   - Resolve loop path
   - Call load_and_validate()
   - Print validation result with state summary
   - Return 0 on valid, 1 on invalid

4. **cmd_list(args) -> int**:
   - If `--running`: use list_running_loops()
   - Otherwise: glob `.loops/*.yaml` and print

5. **print_execution_plan(fsm: FSMLoop)**:
   - Print states with actions, evaluators, routing
   - Show initial state and max_iterations

6. **run_foreground(executor: PersistentExecutor, fsm: FSMLoop) -> int**:
   - Create progress display callback
   - Wrap executor's event callback to add progress display
   - Call executor.run()
   - Return based on result.terminated_by

#### Success Criteria

**Automated Verification**:
- [ ] `ll-loop validate <test-loop>` returns 0 for valid loop
- [ ] `ll-loop validate <invalid-loop>` returns 1 with error message
- [ ] `ll-loop list` shows loops in `.loops/` directory
- [ ] `ll-loop <name> --dry-run` prints execution plan without running

---

### Phase 3: Management Commands (status, stop, resume, history)

#### Overview
Implement loop state management commands.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Implement cmd_status, cmd_stop, cmd_resume, cmd_history functions

1. **cmd_status(args) -> int**:
   - Create StatePersistence for loop name
   - Call load_state()
   - Print status, current state, iteration, timestamps
   - Return 1 if no state found

2. **cmd_stop(args) -> int**:
   - Load state, check status is "running"
   - Update status to "interrupted"
   - Save state
   - Return 0 on success, 1 if not running

3. **cmd_resume(args) -> int**:
   - Resolve loop path, load and validate FSM
   - Create PersistentExecutor
   - Call executor.resume()
   - Return based on result (None means nothing to resume)

4. **cmd_history(args) -> int**:
   - Call get_loop_history() with loop name
   - Print last N events (--tail flag)
   - Format timestamp and event details

#### Success Criteria

**Automated Verification**:
- [ ] `ll-loop status <name>` shows state when state file exists
- [ ] `ll-loop history <name>` shows event log
- [ ] `ll-loop resume <name>` returns None message when no state

---

### Phase 4: Compile Command

#### Overview
Add paradigm compilation support.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Implement cmd_compile function

1. **cmd_compile(args) -> int**:
   - Read input YAML file
   - Call compile_paradigm()
   - Determine output path (input.replace(".yaml", ".fsm.yaml") or -o flag)
   - Write compiled FSM as YAML
   - Print success message

#### Success Criteria

**Automated Verification**:
- [ ] `ll-loop compile paradigm.yaml` creates .fsm.yaml file
- [ ] `ll-loop compile paradigm.yaml -o output.yaml` uses custom output path
- [ ] Invalid paradigm type returns error with exit code 1

---

### Phase 5: Progress Display and Polish

#### Overview
Implement the progress display during loop execution matching the design doc format.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Implement display_progress callback function

Progress format from design doc:
```
Running loop: fix-types
Max iterations: 20

[1/20] check → mypy src/...
       ✗ failure
       → fix
[1/20] fix → /ll:manage_issue bug fix...
       ✓ success (confidence: 0.92)
       → verify

Loop completed: done (1 iteration, 2m 34s)
```

Implementation:
- Track iteration and max_iterations
- On `state_enter`: print `[iteration/max] state_name`
- On `action_start`: print ` → action[:60]...`
- On `evaluate`: print verdict with checkmark/x and confidence if present
- On `route`: print ` → next_state`
- On `loop_complete`: print final summary

#### Success Criteria

**Automated Verification**:
- [ ] Progress output shows iteration counter
- [ ] Actions are truncated to reasonable length
- [ ] Final summary shows state, iterations, duration

---

### Phase 6: Tests

#### Overview
Create test file for ll-loop CLI following existing test patterns.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Create test file with argument parsing and integration tests

```python
"""Tests for ll-loop CLI command."""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLoopArgumentParsing:
    """Tests for ll-loop argument parsing."""

    def test_default_run(self) -> None:
        """Loop name without subcommand runs the loop."""
        # ...

    def test_run_with_dry_run(self) -> None:
        """--dry-run flag works."""
        # ...

    def test_validate_subcommand(self) -> None:
        """validate subcommand parses correctly."""
        # ...


class TestResolveLoopPath:
    """Tests for resolve_loop_path function."""

    def test_direct_path(self, tmp_path: Path) -> None:
        """Direct path returns as-is."""
        # ...

    def test_loop_name_resolution(self, tmp_path: Path) -> None:
        """Loop name resolves to .loops/<name>.yaml."""
        # ...

    def test_not_found_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError for missing loop."""
        # ...


class TestCmdValidate:
    """Tests for validate command."""

    def test_valid_loop(self, tmp_path: Path) -> None:
        """Valid loop returns 0."""
        # ...

    def test_invalid_loop(self, tmp_path: Path) -> None:
        """Invalid loop returns 1 with error."""
        # ...


class TestCmdList:
    """Tests for list command."""

    def test_list_available_loops(self, tmp_path: Path) -> None:
        """Lists YAML files in .loops/."""
        # ...

    def test_list_running_loops(self, tmp_path: Path) -> None:
        """--running shows loops with state files."""
        # ...
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_ll_loop.py -v` passes
- [ ] Tests cover argument parsing, path resolution, and main commands
- [ ] No type errors: `python -m mypy scripts/little_loops/cli.py`

---

## Testing Strategy

### Unit Tests
- Argument parsing for all subcommands
- resolve_loop_path function behavior
- Progress display callback formatting

### Integration Tests
- End-to-end validation of loops
- List command with real directory structure
- Compile command with paradigm files

## References

- Original issue: `.issues/features/P1-FEAT-047-ll-loop-cli-tool.md`
- Design doc: `docs/generalized-fsm-loop.md` section "CLI Interface"
- Existing CLI pattern: `scripts/little_loops/cli.py:21-110` (main_auto)
- FSM modules: `scripts/little_loops/fsm/`

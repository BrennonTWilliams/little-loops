# FEAT-345: Add `ll-loop show` command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-345-ll-loop-show-command.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

`ll-loop` has 11 subcommands but no `show` command. The closest existing functionality is `print_execution_plan()` (loop.py:196-230) which shows states/transitions for dry-run mode, and `cmd_validate()` (loop.py:418-444) which shows basic metadata.

## Desired End State

`ll-loop show <loop-name>` displays:
1. Metadata (name, description, paradigm, max_iterations, timeout, etc.)
2. States table with transitions and evaluators
3. ASCII FSM diagram
4. Ready-to-run `ll-loop run` command

## What We're NOT Doing
- Not adding color/rich formatting beyond what Logger already provides
- Not updating docs/API.md (separate task)
- Not adding `--format json` output option

## Solution Approach

Add `cmd_show()` function following the `cmd_validate()` pattern for loading and the `print_execution_plan()` pattern for display. Generate ASCII diagram by tracing transitions from initial state.

## Implementation Phases

### Phase 1: Add `show` subcommand and `cmd_show()` function

**Changes to `scripts/little_loops/cli/loop.py`**:

1. Add `"show"` to `known_subcommands` set (line 38-50)
2. Add show subparser after install subparser (after line 161)
3. Add `cmd_show()` function (before dispatch block)
4. Add dispatch entry for `show` (in dispatch block at line 870+)

The `cmd_show()` function will:
- Resolve and load the loop (reusing pattern from cmd_validate)
- Print metadata section
- Print states/transitions section (enhanced version of print_execution_plan)
- Generate and print ASCII FSM diagram
- Print run command

### Phase 2: Add tests

Add tests to `scripts/tests/test_ll_loop_commands.py` covering:
- Show valid FSM loop
- Show valid paradigm loop
- Show nonexistent loop (error)
- ASCII diagram generation

### Success Criteria
- [ ] `ll-loop show <name>` works for FSM and paradigm loops
- [ ] Tests pass: `python -m pytest scripts/tests/ -v -k test_show`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

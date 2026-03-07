---
discovered_date: 2026-03-07T00:00:00Z
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 79
---

# FEAT-637: Show FSM Box Diagram with Active State Highlighted During `ll-loop run --verbose`

## Summary

When `ll-loop run ... --verbose` executes, at each FSM step the terminal output should include the Box Diagram (as produced by `ll-loop show ...`) with the current state rendered using a green fill color, giving the user a live visual of where the loop is in its state machine.

## Current Behavior

`ll-loop run --verbose` prints step-level output (state name, action taken, evaluator result) as plain text. The Box Diagram is only available via `ll-loop show` as a separate command; it is never displayed inline during execution.

## Expected Behavior

At each FSM step during `ll-loop run --verbose`, the terminal prints the Box Diagram for the loop with the current state's box filled in green (e.g., using ANSI background/foreground color codes or Rich panel styling). All other states render with their normal appearance. The diagram is printed before or after the step's action output.

## Motivation

Verbose mode is the primary observability interface for running loops. Text-only step output requires the user to mentally map state names to the FSM diagram. Embedding the diagram with the active state highlighted provides immediate spatial context — users can see not just *what* state they are in but *where* it sits in the overall flow and which transitions come next. This is especially valuable for complex loops with many states.

## Use Case

A developer is debugging a loop that seems to be cycling unexpectedly. They run `ll-loop run myloop --verbose` and watch the terminal. Instead of seeing a stream of state names, they see the full FSM box diagram reprinted at each step with the active state highlighted green. They immediately spot that the loop is re-entering an earlier state on every iteration instead of progressing toward the terminal state.

## Acceptance Criteria

- [ ] `ll-loop run --verbose` prints the Box Diagram at each FSM step transition
- [ ] The current state's box renders with a green fill (ANSI or Rich styling)
- [ ] All other state boxes render normally (no color change)
- [ ] Diagram output is identical to `ll-loop show` output except for the active-state color
- [ ] `ll-loop run` without `--verbose` is unaffected (no diagram output)
- [ ] Works for all paradigm types that support `ll-loop show`

## Proposed Solution

TBD - requires investigation

The `ll-loop show` path goes through `cmd_show()` → `_render_fsm_diagram()` in `scripts/little_loops/cli/loop/info.py`. The run executor lives in `scripts/little_loops/cli/loop/run.py` (or similar). At each state transition in verbose mode, call a variant of `_render_fsm_diagram()` that accepts a `current_state: str` parameter and applies green ANSI styling to that state's box characters.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- `_render_fsm_diagram()` in `scripts/little_loops/cli/loop/info.py` — existing diagram renderer to extend

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A

## Implementation Steps

1. Add a `highlight_state: str | None = None` parameter to `_render_fsm_diagram()` in `info.py`
2. Apply green ANSI/Rich styling to the highlighted state's box in the diagram renderer
3. In the verbose run path, call the diagram renderer with `highlight_state=current_state` at each step transition
4. Add tests verifying green-highlighted output for a known state
5. Verify `ll-loop run` without `--verbose` is unaffected

## Impact

- **Priority**: P3 - Meaningful UX improvement for loop debugging; verbose mode is the primary observability tool
- **Effort**: Medium - Requires extending `_render_fsm_diagram()` with ANSI color support and wiring it into the run executor verbose path
- **Risk**: Low - Additive change; existing diagram output and non-verbose run paths are unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `ll-loop`, `ux`, `verbose`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`

## Verification Notes
- **Verdict**: VALID
- `_render_fsm_diagram()` confirmed at `scripts/little_loops/cli/loop/info.py:356` with signature `(fsm: FSMLoop, verbose: bool = False)` — no `highlight_state` parameter exists yet
- `cmd_show()` confirmed at `info.py:1019`, calls `_render_fsm_diagram()` at line 1102
- `ll-loop run --verbose` flag confirmed at `scripts/little_loops/cli/loop/__init__.py:113`
- `run_foreground()` in `scripts/little_loops/cli/loop/_helpers.py:276` uses `verbose` flag but does not call `_render_fsm_diagram()` — feature gap is real
- Run executor is `scripts/little_loops/cli/loop/run.py` → `run_foreground()` in `_helpers.py` — file path in issue is accurate

---

## Status

**Open** | Created: 2026-03-07 | Priority: P3

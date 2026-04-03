---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# BUG-940: FSM `on_error` is dead code when `next` is also defined on the same state

## Summary

In FSM loop states, defining both `next` and `on_error` on the same state makes `on_error` unreachable for normal shell failures. When `next` is set, the executor always follows `next` for any non-negative exit code — `on_error` is only checked for negative exit codes (kill signals like SIGINT). This makes a common-looking pattern silently incorrect, since loop authors naturally write `on_error` expecting it to catch exit-code-1 failures.

## Steps to Reproduce

1. Write an FSM state with both `next` and `on_error`:
   ```yaml
   my_state:
     action: "exit 1"  # or any failing shell command
     action_type: shell
     next: success_state
     on_error: error_state
   ```
2. Run the loop
3. Observe: FSM goes to `success_state` despite the failure — `on_error` is never triggered

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `_execute_state()` at line 342 — the `next` short-circuit branch at lines 364-378
- **Cause**: The executor short-circuits evaluation when `state.next` is set. It runs the action, then returns `state.next` unconditionally for any exit code ≥ 0. `on_error` is only consulted for negative exit codes (process killed by signal).

```python
# executor.py:364–378 — current behavior
if state.next:
    if state.action:
        result = self._run_action(state.action, state, ctx)
        self.prev_result = { ... }
        if result.exit_code is not None and result.exit_code < 0:  # line 374 — SIGKILL only
            if state.on_error:
                return interpolate(state.on_error, ctx)
            self.request_shutdown()
            return None
    return interpolate(state.next, ctx)  # line 378 — always, for exit codes 0, 1, 2, ...
```

The `on_error` only fires for signal kills (exit < 0), not ordinary shell failures (exit 1). The `_route()` method at lines 629-674 — which properly handles `on_error` for verdict == "error" — is **never called** when `state.next` is set; `_execute_state()` returns early at line 378.

## Current Behavior

- States with `next` + `on_error` silently ignore shell failures (exit 1)
- `on_error` never fires unless the process is killed by a signal
- No warning is emitted to help loop authors diagnose the dead code
- The `prompt-across-issues` `prepare_prompt` state is broken by exactly this pattern

## Expected Behavior

Either:
1. **Option A (strict)**: `on_error` fires on any non-zero exit code when defined alongside `next`, making `next` the "success path" and `on_error` the "failure path"
2. **Option B (warn)**: Emit a warning at loop load time (validation) when a state defines both `next` and `on_error`, since `on_error` will be unreachable for exit codes ≥ 0
3. **Option C (document)**: Make this behavior explicit in the loop authoring docs and add a lint check in `ll:review-loop`

## Motivation

This is a silent trap. Loop authors who write `next: X` + `on_error: Y` reasonably expect the error path to activate on shell failure. The current behavior silently routes to `next` no matter what, making error handling dead code. `prompt-across-issues` was written with this pattern and the bug was only discovered via debug output analysis.

## Proposed Solution

**Recommended: Option A** — When `on_error` is defined alongside `next`, treat `next` as the success path and `on_error` as the failure path. This preserves backward compatibility for states without `on_error` (they still unconditionally follow `next`).

```python
# executor.py — proposed behavior
if state.next:
    result = self._run_action(state.action, state, ctx)
    if result.exit_code is not None and result.exit_code < 0:
        if state.on_error:
            return interpolate(state.on_error, ctx)
        self.request_shutdown()
        return None
    # NEW: if on_error is defined, treat next as success path only
    if result.exit_code != 0 and state.on_error:
        return interpolate(state.on_error, ctx)
    return interpolate(state.next, ctx)
```

Additionally, update `prompt-across-issues.yaml` `prepare_prompt` to replace `next: execute` with `on_yes: execute` (cleaner — removes the ambiguity entirely).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_state()` at line 342; `next` short-circuit block at lines 364-378 (add `exit_code != 0 and on_error` guard before the final `return state.next`)
- `scripts/little_loops/loops/prompt-across-issues.yaml:59-73` — `prepare_prompt` state: `next: execute` + `on_error: advance` (1 affected state)
- `scripts/little_loops/loops/general-task.yaml` — 4 states using `next` + `on_error`: lines 23-24, 43-44, 56-57, 89-90
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — 4 states using `next` + `on_error`: lines 18-19, 24-25, 30-31, 100-101

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py:213-284` — `_validate_state_routing()`: `has_next` is computed at line 248 but never compared against `has_shorthand`; validation warning for `next` + `on_error` co-presence should be added here

### Similar Patterns
- `on_yes`/`on_no`/`on_error` shorthand branching handled in `_route()` at `executor.py:663-673` — the proposed fix mirrors this pattern inside the `next` branch
- Example of correct conditional branching: `general-task.yaml:75-77` uses `on_yes`/`on_no`/`on_error` without `next`

### Tests
- `scripts/tests/test_fsm_executor.py:2244` — `test_sigkill_on_next_state_routes_via_on_error_if_configured` is the closest existing test (uses `exit_code=-9`); new test should mirror this with `exit_code=1`
- New test class: `TestSignalHandling` at line 1997+ is the correct location; use `MockActionRunner` pattern from lines 26-86

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide; clarify `next` vs `on_yes` semantics
- `docs/generalized-fsm-loop.md` — FSM loop architecture documentation

### Configuration
- N/A

## Implementation Steps

1. In `executor.py:374-378` (`_execute_state()` `next` branch), after the `exit_code < 0` signal-kill check, insert: `if result.exit_code != 0 and state.on_error: return interpolate(state.on_error, ctx)` — exactly as shown in the Proposed Solution
2. Add test to `scripts/tests/test_fsm_executor.py` in `TestSignalHandling` class (after line 2266): `test_shell_failure_on_next_state_routes_via_on_error_when_configured` — mirror `test_sigkill_on_next_state_routes_via_on_error_if_configured` (line 2244) but use `exit_code=1` instead of `-9`
3. Audit and fix 9 affected states across 3 loops:
   - `loops/general-task.yaml`: 4 states at lines 23-24, 43-44, 56-57, 89-90 — determine which intended error routing vs unconditional advance
   - `loops/refine-to-ready-issue.yaml`: 4 states at lines 18-19, 24-25, 30-31, 100-101 — same determination
   - `loops/prompt-across-issues.yaml:71-72`: `prepare_prompt` — replace `next: execute` with `on_yes: execute` (cleaner: removes ambiguity)
4. (Optional) Add validation warning in `validation.py:248` (`_validate_state_routing()`): when `has_next` is true and `state.on_error` is also set, emit a deprecation-style warning

## Impact

- **Priority**: P3 — Impacts loop correctness but only for states combining `next` + `on_error`; most loops use one or the other
- **Effort**: Small — logic change in one function + YAML audit of built-in loops
- **Risk**: Low — backward compatible if framed as "on_error now activates on non-zero exit when defined"; no loop depends on `on_error` silently not firing
- **Breaking Change**: Technically yes — but only for the broken pattern, which no correct loop relies on

## Related

- BUG-939: `prompt-across-issues` trailing newline bug — the companion issue discovered at the same time
- `scripts/little_loops/fsm/executor.py` — `_transition()` unconditional next block
- `scripts/little_loops/loops/prompt-across-issues.yaml` — affected loop YAML

## Labels

`bug`, `fsm`, `loops`, `captured`

---

## Session Log
- `/ll:refine-issue` - 2026-04-03T22:16:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a85d9d85-aa09-48cc-87d7-2dd3a055329b.jsonl`
- `/ll:capture-issue` - 2026-04-03T22:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1745900e-c050-4c53-81d7-10a084dba4e9.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P3

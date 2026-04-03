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
- **Anchor**: `_transition()` — the unconditional `next` handling block
- **Cause**: The executor short-circuits evaluation when `state.next` is set. It runs the action, then returns `state.next` unconditionally for any exit code ≥ 0. `on_error` is only consulted for negative exit codes (process killed by signal).

```python
# executor.py — current behavior
if state.next:
    result = self._run_action(state.action, state, ctx)
    if result.exit_code is not None and result.exit_code < 0:
        if state.on_error:
            return interpolate(state.on_error, ctx)
        self.request_shutdown()
        return None
    return interpolate(state.next, ctx)  # ← always, for exit codes 0, 1, 2, ...
```

The `on_error` only fires for signal kills (exit < 0), not ordinary shell failures (exit 1). This is undocumented and counterintuitive.

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
- `scripts/little_loops/fsm/executor.py` — `_transition()` unconditional next block
- `scripts/little_loops/loops/prompt-across-issues.yaml` — fix `prepare_prompt` to use `on_yes`/`on_error` instead of `next`/`on_error`

### Dependent Files (Callers/Importers)
- All FSM loop YAML files that use `next` + `on_error` on the same state — audit needed
- `scripts/little_loops/fsm/validation.py` — may want a new validation warning for this pattern

### Similar Patterns
- Search for loop files with both `next:` and `on_error:` on same state: `grep -l "on_error" scripts/little_loops/loops/`

### Tests
- `scripts/tests/` — add test: state with `next` + `on_error` should route to `on_error` when shell exits 1
- Existing FSM routing tests for unconditional transition

### Documentation
- `docs/` loop authoring guide — clarify `next` vs `on_yes` semantics

### Configuration
- N/A

## Implementation Steps

1. In `executor.py` `_transition()`, after the signal-kill check, add: if exit code != 0 and `on_error` defined, route to `on_error`
2. Audit all built-in loops in `scripts/little_loops/loops/` for states with `next` + `on_error` — fix any that intended error routing
3. Update `prompt-across-issues.yaml` `prepare_prompt` to use `on_yes: execute` instead of `next: execute`
4. Add FSM executor test covering `next` + `on_error` with failing shell command
5. (Optional) Add validation warning in `validation.py` for ambiguous `next` + `on_error` patterns

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
- `/ll:capture-issue` - 2026-04-03T22:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1745900e-c050-4c53-81d7-10a084dba4e9.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P3

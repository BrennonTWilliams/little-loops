---
discovered_date: 2026-04-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-1017: FSM sub-loop outcome resolves by termination reason, not terminal state name

## Summary

The FSM executor routes sub-loop outcomes using `terminated_by` ("terminal" vs "error") instead of the terminal state name ("done" vs "failed"). Any loop that cleanly reaches a `failed` terminal is treated as success, routing to `on_success`/`on_yes` instead of `on_failure`/`on_no`.

## Context

User description: "FSM engine — map terminal state names to success/failure"

## Current Behavior

When a sub-loop FSM reaches a terminal state, `_execute_sub_loop()` in `executor.py` checks only `child_result.terminated_by == "terminal"` to determine success. Any clean termination — regardless of whether the terminal state is `done` or `failed` — is treated as success and routes to `on_yes`/`on_success`. A sub-loop that legitimately fails (reaches `failed` terminal) is indistinguishable from one that succeeds.

## Expected Behavior

The outer loop should route sub-loop outcomes based on the terminal state **name**, not just termination reason:
- `terminated_by == "terminal"` + `final_state == "done"` → route to `on_success`/`on_yes`
- `terminated_by == "terminal"` + `final_state != "done"` (e.g., `"failed"`) → route to `on_failure`/`on_no`
- `terminated_by == "error"` (no terminal reached) → route to `on_error` (if defined), else `on_no`/`on_failure`

## Steps to Reproduce

1. Create an FSM loop configuration with a sub-loop state (`type: sub_loop`) referencing a loop that has both `done` and `failed` terminal states.
2. Configure the outer loop's sub-loop state with `on_yes` and `on_no` routing targets.
3. Execute the outer loop such that the inner sub-loop reaches the `failed` terminal state (e.g., by failing a condition check in `confidence_check`).
4. Observe: outer loop routes to `on_yes`/`on_success` path instead of `on_no`/`on_failure`.
5. Confirm via event log that `child_result.terminated_by == "terminal"` and `child_result.final_state == "failed"`.

## Root Cause

`scripts/little_loops/fsm/executor.py:368` — `_execute_sub_loop()` checks only `child_result.terminated_by == "terminal"` and routes to `on_yes`, ignoring `child_result.final_state`:

```python
# Route based on child termination reason
if child_result.terminated_by == "terminal":
    return interpolate(state.on_yes, ctx) if state.on_yes else None
else:
    # error, max_iterations, timeout, signal — all are failure
    return interpolate(state.on_no, ctx) if state.on_no else None
```

The fix should resolve the **terminal state name** to determine success vs failure:
- `terminated_by == "terminal"` + `final_state == "done"` → `on_success`/`on_yes`
- `terminated_by == "terminal"` + `final_state != "done"` (e.g., "failed") → `on_failure`/`on_no`
- `terminated_by == "error"` (no terminal reached) → `on_error`

## Motivation

Production impact: outer loops that orchestrate sub-loops (e.g., `auto-refine-and-implement`) route `failed` sub-loops to `implement_issue` instead of `skip_issue`, wasting compute and potentially acting on failed refinement.

## Evidence

| Sub-loop outcome | terminated_by | Outer route | Correct? |
|---|---|---|---|
| Reaches `done` terminal | "terminal" | on_success → implement_issue | Yes |
| Reaches `failed` terminal | "terminal" | on_success → implement_issue | **NO** — should be on_failure → skip_issue |
| Crashes/errors mid-state | "error" | on_error → skip_issue | Yes (coincidentally) |

Event log examples:
- FEAT-042: `{"event": "loop_complete", "final_state": "confidence_check", "terminated_by": "error"}` → correctly skipped (by luck)
- ENH-043: `{"event": "loop_complete", "final_state": "failed", "terminated_by": "terminal"}` → wrongly routed to `implement_issue`

## Implementation Steps

1. **Modify `_execute_sub_loop()` at `executor.py:367–372`** — replace the routing block:
   ```python
   # NEW routing logic
   if child_result.terminated_by == "terminal":
       if child_result.final_state == "done":
           return interpolate(state.on_yes, ctx) if state.on_yes else None
       else:
           # Reached a non-done terminal (e.g. "failed") → failure
           return interpolate(state.on_no, ctx) if state.on_no else None
   elif child_result.terminated_by == "error":
       if state.on_error:
           return interpolate(state.on_error, ctx)
       return interpolate(state.on_no, ctx) if state.on_no else None
   else:
       # max_iterations, timeout, signal — all failure
       return interpolate(state.on_no, ctx) if state.on_no else None
   ```

2. **Add 3 tests to `TestSubLoopExecution` in `test_fsm_executor.py:3395`**:
   - `test_sub_loop_terminal_done_routes_to_on_yes` — child has `done: terminal: true`; assert parent `final_state == "success"`
   - `test_sub_loop_terminal_failed_routes_to_on_no` — child has `failed: terminal: true` as initial state; assert parent `final_state == "failure"` (this is the bug path — **no existing test covers it**)
   - `test_sub_loop_error_routes_to_on_error_when_set` — child crashes (error); assert parent routes to `on_error` target

3. **Run tests**: `python -m pytest scripts/tests/test_fsm_executor.py::TestSubLoopExecution -v`

4. **Update `skills/create-loop/reference.md:675–677`** — revise the sub-loop routing semantics table to reflect: (a) `on_success` requires both `terminated_by=="terminal"` and `final_state=="done"`; (b) `on_failure` also fires when `terminated_by=="terminal"` and `final_state != "done"` (any non-`done` terminal like `"failed"`); (c) `on_error` now covers runtime child failures (`terminated_by=="error"`) in addition to YAML load failures

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `skills/create-loop/reference.md` — adjust `on_success`, `on_failure`, and `on_error` semantic definitions for sub-loop states to match the new routing logic

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py:367–372` — `_execute_sub_loop()` routing decision: add `final_state` check and `on_error` routing for `terminated_by == "error"`

### Dependent Files (No Changes Required)
- `scripts/little_loops/fsm/types.py:15–38` — `ExecutionResult` dataclass already has both `terminated_by` (line 32) and `final_state` (line 30) fields — no changes needed
- `scripts/little_loops/fsm/schema.py:295–297` — `on_success`→`on_yes`, `on_failure`→`on_no` alias collapse at load time — no changes needed; `state.on_error` already available
- `scripts/little_loops/fsm/executor.py:386–393` — `_execute_state()` already catches file-load errors and routes to `on_error`; this fix adds `on_error` routing for runtime child failures inside `_execute_sub_loop()` itself

### Impacted Loops (All Route Incorrectly Today)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:35–40` — `refine_issue` sub-loop state: `on_success: implement_issue`, `on_failure: skip_issue`, `on_error: skip_issue`
- `scripts/little_loops/loops/recursive-refine.yaml:88–97` — `run_refine` sub-loop state: comment explicitly documents intended `done`/`failed` semantics; currently silently broken
- `scripts/little_loops/loops/issue-refinement.yaml:28–32` — `run_refine_to_ready` sub-loop state with `on_yes`/`on_no` routing

### Child Loop with Both Terminal States
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:197–201` — `done: terminal: true` and `failed: terminal: true` (primary child loop subject to this bug)

### Additional Loops Using Sub-Loop States (Informational)

_Wiring pass added by `/ll:wire-issue`:_

These loops also use `loop:` states (sub-loop execution) but their child loops do not expose a `failed: terminal: true` state — so they are not misrouted today. Listed for completeness:
- `scripts/little_loops/loops/greenfield-builder.yaml:162,179` — two sub-loop states; children are `issue-refinement` and `eval-driven-development` (no `failed` terminal)
- `scripts/little_loops/loops/eval-driven-development.yaml:85` — child is `issue-refinement` (no `failed` terminal)
- `scripts/little_loops/loops/prompt-regression-test.yaml:90` — child is `apo-textgrad`; already has `on_success`/`on_failure`/`on_error` set correctly
- `scripts/little_loops/loops/examples-miner.yaml:137` — child is `apo-textgrad`; already has `on_success`/`on_failure` set
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml:12` — self-recursive sub-loop; no `failed` terminal

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `skills/create-loop/reference.md:675–677` — defines sub-loop routing semantics for `on_success`, `on_failure`, and `on_error`; all three definitions become inaccurate after the fix:
  - Current: `on_success` = child reached any terminal state (`terminated_by: "terminal"`)
  - Current: `on_failure` = child ended via max_iterations/timeout/signal/error
  - Current: `on_error` = child loop YAML not found or invalid
  - After fix: `on_success` = `terminated_by=="terminal"` **and** `final_state=="done"`; `on_failure` also fires when `terminated_by=="terminal"` and `final_state != "done"` (e.g., `"failed"`); `on_error` now also fires for runtime child errors (`terminated_by=="error"`), not just YAML load failures

### Tests
- `scripts/tests/test_fsm_executor.py:3395–3641` — `TestSubLoopExecution` class: add new tests here for the exact bug path
  - **Critical gap**: `test_sub_loop_failure_routes_to_on_failure` (line 3419) triggers `terminated_by == "max_iterations"` via exhaustion — it does NOT test `terminated_by == "terminal"` + `final_state == "failed"`; that exact path has **no existing test**
  - Need: child YAML with `failed: terminal: true` state that the child naturally reaches

### Existing Test Setup Pattern (from `TestSubLoopExecution`)
```python
def test_sub_loop_<name>(self, tmp_path: Path) -> None:
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "child.yaml").write_text(
        "name: child\ninitial: start\nstates:\n"
        "  start:\n    on_yes: done\n    on_no: failed\n    action: '...'\n"
        "  done:\n    terminal: true\n"
        "  failed:\n    terminal: true"
    )
    parent_fsm = FSMLoop(
        name="parent",
        initial="run_child",
        states={
            "run_child": StateConfig(loop="child", on_yes="ok", on_no="fail", on_error="err"),
            "ok": StateConfig(terminal=True),
            "fail": StateConfig(terminal=True),
            "err": StateConfig(terminal=True),
        },
    )
    executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
    result = executor.run()
    assert result.final_state == "fail"  # or "ok" or "err"
```

## API/Interface

No public API change. The `ExecutionResult` dataclass already has both `terminated_by` and `final_state` fields — this is purely a routing logic fix.

### `on_error` Scope Clarification

The issue describes routing to `on_error` when `terminated_by == "error"`. This requires a change **inside `_execute_sub_loop()`** — the existing `on_error` handling in `_execute_state()` (lines 390–393) only catches `FileNotFoundError`/`ValueError` from child YAML loading, not runtime child failures. The fix must add an `on_error` check inside `_execute_sub_loop()` itself at lines 367–372.

## Impact

- **Priority**: P2 - Production outer loops (e.g., `auto-refine-and-implement`) silently misroute `failed` sub-loops to success paths, wasting compute and potentially acting on failed refinements
- **Effort**: Small - Single function change in `_execute_sub_loop()` with no public API changes; `ExecutionResult` already carries both `terminated_by` and `final_state`
- **Risk**: Low - Well-isolated routing logic; fix is additive (adds `final_state` check after existing `terminated_by` check); loops using only `done`/`error` outcomes are unaffected
- **Breaking Change**: No - routing becomes more semantically correct; any loop that previously relied on incorrect success-on-`failed` routing was already broken

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM executor component, event model |
| architecture | docs/reference/API.md | FSMExecutor, ExecutionResult, on_success/on_failure aliases |

## Labels

`bug`, `captured`, `fsm`

---

## Resolution

**Fixed** | Resolved: 2026-04-10 | Priority: P2

### Changes Made

- `scripts/little_loops/fsm/executor.py:367–381` — Updated `_execute_sub_loop()` to check `child_result.final_state == "done"` alongside `terminated_by == "terminal"`. Added `on_error` routing for `terminated_by == "error"` runtime child failures.
- `scripts/tests/test_fsm_executor.py` — Added 3 tests to `TestSubLoopExecution`: `test_sub_loop_terminal_done_routes_to_on_yes`, `test_sub_loop_terminal_failed_routes_to_on_no` (the exact bug path), `test_sub_loop_error_routes_to_on_error_when_set`.
- `skills/create-loop/reference.md:674–677` — Updated routing semantics docs for `on_success`/`on_failure`/`on_error` to reflect `final_state`-aware logic.

## Status

**Completed** | Created: 2026-04-09 | Resolved: 2026-04-10 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-04-10T20:16:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca31b15a-6ef7-4f39-aa93-068dc752e472.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19597425-49e5-447f-bb3f-9ca833b862ee.jsonl`
- `/ll:wire-issue` - 2026-04-10T20:00:00 - `(session path not recorded)`
- `/ll:refine-issue` - 2026-04-10T19:35:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/56c62f8e-8b66-415a-92b3-b2823d040481.jsonl`
- `/ll:format-issue` - 2026-04-10T19:31:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9108ce5-78c3-402d-a7e5-6b95c72aaaa4.jsonl`
- `/ll:capture-issue` - 2026-04-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1a28894-156c-4356-8250-5c68db5a469d.jsonl`

---
discovered_date: 2026-04-09
discovered_by: capture-issue
---

# BUG-1017: FSM sub-loop outcome resolves by termination reason, not terminal state name

## Summary

The FSM executor routes sub-loop outcomes using `terminated_by` ("terminal" vs "error") instead of the terminal state name ("done" vs "failed"). Any loop that cleanly reaches a `failed` terminal is treated as success, routing to `on_success`/`on_yes` instead of `on_failure`/`on_no`.

## Context

User description: "FSM engine — map terminal state names to success/failure"

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

1. In `_execute_sub_loop()` at `executor.py:367-372`, add terminal state name check
2. When `terminated_by == "terminal"`: check `child_result.final_state`
   - `"done"` → route to `on_yes`/`on_success`
   - any other value → route to `on_no`/`on_failure`
3. When `terminated_by == "error"` → route to `on_error` (if defined), else `on_no`/`on_failure`
4. Add tests for all three outcome paths

## API/Interface

No public API change. The `ExecutionResult` dataclass already has both `terminated_by` and `final_state` fields — this is purely a routing logic fix.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM executor component, event model |
| architecture | docs/reference/API.md | FSMExecutor, ExecutionResult, on_success/on_failure aliases |

## Labels

`bug`, `captured`, `fsm`

---

## Status

**Open** | Created: 2026-04-09 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-04-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1a28894-156c-4356-8250-5c68db5a469d.jsonl`

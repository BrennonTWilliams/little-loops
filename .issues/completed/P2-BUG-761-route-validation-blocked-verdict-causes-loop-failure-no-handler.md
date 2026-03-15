---
discovered_date: 2026-03-15
discovered_by: analyze-loop
source_loop: sprint-build-and-validate
source_state: route_validation
---

# BUG-761: route_validation blocked verdict causes loop failure (no on_blocked handler)

## Summary

In the `sprint-build-and-validate` loop, the `route_validation` `llm_structured` evaluate returned a `blocked` verdict at iteration 7. The FSM only defines `on_yes`, `on_no`, and `on_error` routes — there is no `on_blocked` handler. When the engine encountered the unhandled verdict, it transitioned the loop to `failed` status with no recovery path. The loop terminated prematurely without reaching `review_sprint` or `commit`.

## Loop Context

- **Loop**: `sprint-build-and-validate`
- **State**: `route_validation`
- **Signal type**: fatal_error (unhandled verdict)
- **Occurrences**: 1 (iteration 7, loop status: failed)
- **Last observed**: 2026-03-15T22:48:44+00:00

## History Excerpt

Events leading to this signal:

```json
[
  {
    "event": "evaluate",
    "state": "route_validation",
    "verdict": "blocked",
    "confidence": 0.9,
    "reason": "No active sprint is loaded. Cannot determine readiness without knowing which sprint or issues to check."
  },
  {
    "event": "loop_complete",
    "terminated_by": "error",
    "final_state": "route_validation",
    "iterations": 7,
    "status": "failed"
  }
]
```

## Expected Behavior

An `llm_structured` evaluate that returns `blocked` should have a defined recovery path. Either:
1. `route_validation` should define `on_blocked: fix_issues` (treat blocked same as "issues need fixing"), or
2. The FSM engine should fall through to `on_error` when `blocked` is returned and no `on_blocked` handler exists, rather than failing the loop.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `_route()` at line 867 — `return None` fallthrough
- **Cause**: `_route()` handles only four shorthand verdicts: `on_yes` (line 858), `on_no` (line 860), `on_error` (line 862), `on_partial` (line 864). When `verdict == "blocked"`, none of these branches match and the method returns `None`. The caller at `executor.py:523-524` treats `None` as fatal: `self._finish("error", error="No valid transition")` → `terminated_by="error"`.
- **Contributing factor**: `evaluators.py:54-79` — `DEFAULT_LLM_SCHEMA` explicitly includes `"blocked"` in the verdict enum sent to the LLM on every `llm_structured` call. The engine invites the LLM to return `"blocked"` but has no field on `StateConfig` to receive it. `on_blocked` is absent from `schema.py:215-225` while `on_partial` was previously added as a field at line 218.

## Proposed Fix

Two-part fix:
1. Add `on_blocked: fix_issues` to `route_validation` (and `route_review`) in `sprint-build-and-validate.yaml` so a blocked evaluate retries the fix path.
2. Add `on_blocked` as a first-class shorthand field on `StateConfig` (like `on_partial`) — this is the systemic engine fix.
3. Audit and patch other built-in loops' `llm_structured` evaluate states for missing `on_blocked` handlers.

## Affected States (Systemic Audit)

All `llm_structured` evaluate states in built-in loops that lack `on_blocked`:

| Loop | State | `on_blocked`? | Recommended fix |
|---|---|---|---|
| `sprint-build-and-validate.yaml:49` | `route_validation` | No | `on_blocked: fix_issues` |
| `sprint-build-and-validate.yaml:86` | `route_review` | No | `on_blocked: fix_issues` |
| `issue-staleness-review.yaml:35` | `triage` | No | `on_blocked: find_stale` (retry) |
| `issue-size-split.yaml:19` | `route_large` | No | `on_blocked: done` (safe exit) |

## Integration Map

### Files to Modify

**Engine — add `on_blocked` shorthand field:**
- `scripts/little_loops/fsm/schema.py:218` — add `on_blocked: str | None = None` to `StateConfig` dataclass (parallel to `on_partial`)
- `scripts/little_loops/fsm/schema.py:247` — add `on_blocked` to `to_dict()` (parallel to `on_partial` block)
- `scripts/little_loops/fsm/schema.py:286` — add `on_blocked=data.get("on_blocked")` to `from_dict()`
- `scripts/little_loops/fsm/schema.py:310` — add `on_blocked` to `get_referenced_states()`
- `scripts/little_loops/fsm/executor.py:864` — add `if verdict == "blocked" and state.on_blocked:` branch in `_route()` after `on_partial` check

**Loop YAMLs — add `on_blocked` handlers:**
- `loops/sprint-build-and-validate.yaml:55` — add `on_blocked: fix_issues` after `on_error: review_sprint` in `route_validation`
- `loops/sprint-build-and-validate.yaml:93` — add `on_blocked: fix_issues` after `on_error: commit` in `route_review`
- `loops/issue-staleness-review.yaml:44` — add `on_blocked: find_stale` (retry) in `triage`
- `loops/issue-size-split.yaml:27` — add `on_blocked: done` (safe exit) in `route_large`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/validation.py` — validates state route references; `on_blocked` must be included in its reachability check
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for YAML configs; `on_blocked` should be added as an optional string property on state objects

### Similar Patterns

- `scripts/little_loops/fsm/schema.py:218` — `on_partial: str | None = None` is the exact precedent to replicate for `on_blocked`
- `scripts/little_loops/fsm/executor.py:864-865` — `on_partial` branch is the template for the new `on_blocked` branch
- `loops/fix-quality-and-tests.yaml:9` — only built-in loop with `on_partial` defined; demonstrates correct multi-verdict shorthand usage

### Tests

- `scripts/tests/test_fsm_schema.py:283-339` — six `on_partial` tests to mirror exactly for `on_blocked` (field, from_dict, to_dict, absent when None, get_referenced_states, roundtrip)
- `scripts/tests/test_fsm_executor.py:997-1063` — three `on_partial` routing tests to mirror for `on_blocked` (routes correctly, shorthand works, missing falls through to error)
- `scripts/tests/test_builtin_loops.py` — add test asserting each audited loop state now has `on_blocked` defined

## Implementation Steps

1. **`schema.py` — add `on_blocked` field** (4 locations, mirror `on_partial` at lines 218, 247, 286, 310)
2. **`executor.py:864` — add routing branch** — insert `if verdict == "blocked" and state.on_blocked: return self._resolve_route(state.on_blocked, ctx)` after the `on_partial` check
3. **`fsm-loop-schema.json`** — add `"on_blocked": {"type": "string"}` to state object properties
4. **`validation.py`** — confirm `on_blocked` is picked up via `get_referenced_states()` (automatic if step 1 is done correctly)
5. **Loop YAMLs** — add `on_blocked` handlers to the 4 affected states listed in the Affected States table above
6. **Tests — schema** — add 6 tests to `test_fsm_schema.py` mirroring `on_partial` tests at lines 283-339
7. **Tests — executor** — add 3 tests to `test_fsm_executor.py` mirroring `on_partial` tests at lines 997-1063
8. **Tests — built-in loops** — extend `test_builtin_loops.py` to assert no `llm_structured` state is missing `on_blocked`
9. **Verify** — `python -m pytest scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_executor.py scripts/tests/test_builtin_loops.py -v`

## Acceptance Criteria

- [ ] `route_validation` has an `on_blocked` route that prevents loop failure
- [ ] Loop does not transition to `failed` when evaluate returns `blocked`
- [ ] Other built-in loops are audited for missing `on_blocked` handlers
- [ ] `on_blocked` is a first-class `StateConfig` field (schema + executor + JSON schema)
- [ ] Tests added for `on_blocked` in schema and executor (mirroring `on_partial` test suite)

## Labels

`bug`, `loops`, `captured`

## Resolution

**Fixed** | Resolved: 2026-03-15 | Priority: P2

### Changes Made

1. **`scripts/little_loops/fsm/schema.py`** — Added `on_blocked: str | None = None` field to `StateConfig` dataclass; updated `to_dict()`, `from_dict()`, and `get_referenced_states()` to include `on_blocked` (mirroring `on_partial`)
2. **`scripts/little_loops/fsm/executor.py`** — Added `if verdict == "blocked" and state.on_blocked:` branch in `_route()` after the `on_partial` check
3. **`scripts/little_loops/fsm/fsm-loop-schema.json`** — Added `"on_blocked"` as an optional string property in the `stateConfig` definition
4. **`loops/sprint-build-and-validate.yaml`** — Added `on_blocked: fix_issues` to `route_validation` and `route_review` states
5. **`loops/issue-staleness-review.yaml`** — Added `on_blocked: find_stale` to `triage` state
6. **`loops/issue-size-split.yaml`** — Added `on_blocked: done` to `route_large` state
7. **`scripts/tests/test_fsm_schema.py`** — Added 6 `on_blocked` tests mirroring the `on_partial` test suite; fixed pre-existing `TestLLMConfig::test_defaults` assertion (30→1800 after timeout raise in 9fda9ca)
8. **`scripts/tests/test_fsm_executor.py`** — Added 2 `on_blocked` routing tests mirroring `on_partial` tests
9. **`scripts/tests/test_builtin_loops.py`** — Added `TestBuiltinLoopOnBlockedCoverage` class asserting all 4 audited states define `on_blocked`

### Verification

All 3529 tests pass (`python -m pytest scripts/tests/ --no-cov -q`).

## Status

**Resolved** | Created: 2026-03-15 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-03-15T23:17:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c2267ab-ffdb-4f12-b274-1fb55704ed47.jsonl`
- `/ll:refine-issue` - 2026-03-15T23:05:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/346718bd-e365-4d89-b1b7-2c6df93e57b0.jsonl`

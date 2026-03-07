---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# FEAT-635: `compile_convergence` hard-codes `stall → done` with no user override

## Summary

The `convergence` paradigm compiler hard-codes both `"target"` and `"stall"` routes to `"done"`. A user who wants to handle a stall differently (e.g., route to a recovery state that tries a different approach when progress stops) must abandon the `convergence` paradigm and write raw FSM syntax. Unlike `compile_goal` (which accepts a custom `name`) and `compile_invariants` (which supports `maintain`), `compile_convergence` has no `on_stall` override.

## Location

- **File**: `scripts/little_loops/fsm/compilers.py`
- **Line(s)**: 308–316 (at scan commit: 12a6af0)
- **Anchor**: `in function compile_convergence()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/compilers.py#L308-L316)
- **Code**:
```python
route=RouteConfig(
    routes={
        "target": "done",
        "progress": "apply",
        "stall": "done",   # hard-coded — no override possible
    }
),
```

## Current Behavior

Any `convergence`-paradigm loop that stalls terminates silently with `done` status. The user cannot differentiate a successful convergence from a stall without inspecting loop history.

## Expected Behavior

The paradigm spec should accept an optional `on_stall` field that overrides the `stall` route target. When omitted, behavior defaults to current (`stall → done`).

## Use Case

A developer builds a convergence loop for iterative code optimization. When the optimizer stalls (no improvement across iterations), they want to route to a `"reset"` state that tries a different optimization strategy rather than terminating. They write:
```yaml
paradigm: convergence
apply: /ll:optimize-code
check: /ll:measure-quality
on_stall: reset   # new field — routes to user-defined "reset" state
```

## Acceptance Criteria

- `on_stall: <state_name>` is accepted in `convergence` paradigm YAML
- When `on_stall` is set, the compiled `evaluate` state's `stall` route targets `on_stall` value
- When `on_stall` is absent, defaults to `"done"` (backward compatible)
- Validation catches dangling `on_stall` references

## API/Interface

```yaml
paradigm: convergence
apply: /ll:apply-step
check: /ll:evaluate-progress
target: 95.0
on_stall: recovery        # optional — overrides stall → done
```

## Proposed Solution

```python
def compile_convergence(spec: dict) -> FSMLoop:
    on_stall_target = spec.get("on_stall", "done")
    ...
    route=RouteConfig(
        routes={
            "target": "done",
            "progress": "apply",
            "stall": on_stall_target,   # use override or default
        }
    ),
```

If `on_stall_target` is not `"done"`, the user is responsible for defining the target state in `extra_states` or similar.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/compilers.py` — `compile_convergence()`

### Tests
- `scripts/tests/test_fsm_compilers.py` — add test for `on_stall` override

### Documentation
- Loop paradigm YAML documentation

### Configuration
- N/A

## Implementation Steps

1. Add `on_stall = spec.get("on_stall", "done")` in `compile_convergence()`
2. Use `on_stall` value in the `"stall"` route instead of hard-coded `"done"`
3. Add test with and without `on_stall` field

## Impact

- **Priority**: P3 — Exposes useful control over stall behavior; currently forces paradigm users to raw FSM for this common case
- **Effort**: Small — One-line change to `compile_convergence()` plus a test
- **Risk**: Low — Additive and backward compatible; existing configs without `on_stall` are unaffected
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `compiler`, `paradigm`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P3

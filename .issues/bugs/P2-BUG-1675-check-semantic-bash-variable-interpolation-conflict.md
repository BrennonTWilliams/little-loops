---
discovered_commit: 941d81c
discovered_branch: main
discovered_date: 2026-05-24T00:00:00Z
discovered_by: audit-loop-run
status: open
---

# BUG-1675: `check_semantic` bash variable interpolation conflicts with FSM template engine

## Summary

The `check_semantic` state's action script uses bash variables `${HEAD_PART}` and `${TAIL_PART}` that the FSM template engine incorrectly resolves as context variable references (`context.HEAD_PART`), causing "Invalid variable: ${HEAD_PART} (expected namespace.path)" errors. BUG-691 fixed the same issue in the `advance` state using `$$` escaping, but `check_semantic` was not updated, making it a regression / incomplete fix.

## Location

- **File**: `loops/harness-exploratory-user-eval.yaml`
- **State**: `check_semantic`
- **Lines**: action script, `${HEAD_PART}` and `${TAIL_PART}` references

## Root Cause

- **File**: `loops/harness-exploratory-user-eval.yaml`
- **Anchor**: `check_semantic` state action script
- **Cause**: The action script uses bare `${HEAD_PART}` and `${TAIL_PART}` bash variable syntax. The FSM template engine intercepts single-dollar `${...}` references and attempts to resolve them as `context.*` variables, raising "Invalid variable: ${HEAD_PART} (expected namespace.path)". BUG-691 fixed the same pattern in the `advance` state by escaping to `$${}`, but `check_semantic` was not updated.

## Steps to Reproduce

1. Run `harness-exploratory-user-eval` loop
2. Wait for first pass to complete `execute` state
3. `check_semantic_vision` times out (720s)
4. Loop falls through to `check_semantic` as fallback
5. `check_semantic` action fails with: "Invalid variable: ${HEAD_PART} (expected namespace.path)"
6. Error routes to `check_semantic_retry_count` → `advance` → retry cycle

## Impact

When `check_semantic_vision` times out, the loop falls through to `check_semantic` as the LM Studio fallback. But `check_semantic` also fails due to this bug, meaning **both** evaluation paths are broken and the convergence contract is structurally unreachable. The loop burns all `max_iterations` on failed evaluation cycles without ever completing a semantic pass.

## Proposed Solution

Apply the same `$$` escaping used in BUG-691's fix for the `advance` state:

```bash
# In check_semantic action, change:
TRUNCATED="${HEAD_PART}"$'\n...\n'"${TAIL_PART}"
# To:
TRUNCATED="$${HEAD_PART}"$'\n...\n'"$${TAIL_PART}"
```

Also audit ALL shell actions in `harness-exploratory-user-eval.yaml` for unescaped `${...}` bash variables that could conflict with the FSM template engine.

## Implementation Steps

1. In `loops/harness-exploratory-user-eval.yaml`, apply `$$` escaping to `${HEAD_PART}` and `${TAIL_PART}` in the `check_semantic` state action script (matching the BUG-691 fix pattern used in `advance`)
2. Audit all other shell action scripts in `harness-exploratory-user-eval.yaml` for unescaped `${...}` bash variables that could trigger the same interpolation error
3. Apply `$$` escaping to any additional unescaped variables found in the audit
4. Run `ll-loop validate harness-exploratory-user-eval` to confirm no template resolution errors remain
5. Verify the loop can execute through `check_semantic` without routing to the retry cycle

## Integration Map

### Files to Modify
- `loops/harness-exploratory-user-eval.yaml` — escape `${HEAD_PART}` → `$${HEAD_PART}` and `${TAIL_PART}` → `$${TAIL_PART}` in `check_semantic` action script; audit remaining shell actions

### Dependent Files (Callers/Importers)
- TBD — `grep -r "harness-exploratory-user-eval" loops/` to find any orchestrator references

### Similar Patterns
- Reference BUG-691 fix in `advance` state: `grep -n "\$\$" loops/harness-exploratory-user-eval.yaml`
- Reference BUG-671 fix in `capture` state for same escaping pattern

### Tests
- TBD — check `scripts/tests/` for loop yaml tests covering template variable resolution

### Documentation
- N/A

### Configuration
- N/A

## Related

- BUG-691: Original fix for `advance` state variable interpolation
- BUG-671: Double-dollar shell escape in capture state


## Session Log
- `/ll:format-issue` - 2026-05-24T13:39:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c29e127-5f7b-421f-9734-c94217103bba.jsonl`

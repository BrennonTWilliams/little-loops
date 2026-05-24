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

## Reproduction

1. Run `harness-exploratory-user-eval` loop
2. Wait for first pass to complete `execute` state
3. `check_semantic_vision` times out (720s)
4. Loop falls through to `check_semantic` as fallback
5. `check_semantic` action fails with: "Invalid variable: ${HEAD_PART} (expected namespace.path)"
6. Error routes to `check_semantic_retry_count` → `advance` → retry cycle

## Impact

When `check_semantic_vision` times out, the loop falls through to `check_semantic` as the LM Studio fallback. But `check_semantic` also fails due to this bug, meaning **both** evaluation paths are broken and the convergence contract is structurally unreachable. The loop burns all `max_iterations` on failed evaluation cycles without ever completing a semantic pass.

## Fix

Apply the same `$$` escaping used in BUG-691's fix for the `advance` state:

```bash
# In check_semantic action, change:
TRUNCATED="${HEAD_PART}"$'\n...\n'"${TAIL_PART}"
# To:
TRUNCATED="$${HEAD_PART}"$'\n...\n'"$${TAIL_PART}"
```

Also audit ALL shell actions in `harness-exploratory-user-eval.yaml` for unescaped `${...}` bash variables that could conflict with the FSM template engine.

## Related

- BUG-691: Original fix for `advance` state variable interpolation
- BUG-671: Double-dollar shell escape in capture state

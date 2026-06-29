---
discovered_date: 2026-06-29T16:16:34Z
discovered_by: manual
status: done
completed_at: 2026-06-29T16:16:34Z
---

# BUG-2394: `re_enqueue_unblocked` in `rn-implement` missing `on_error:` route (MR-10)

## Summary

`ll-loop validate` (and `ll-loop run`) emitted an MR-10 WARNING for the `re_enqueue_unblocked`
state in `rn-implement.yaml`. The state's inline Python block calls `json.loads`, catches bare
`Exception`, and calls `sys.exit(0)` on failure — but the state declared only `next: dequeue_next`
with no `on_error:` route. The validator flags this pattern because the FSM sees exit 0 on a
parse failure and treats the state as successful, silently discarding the error.

## Location

- **File**: `scripts/little_loops/loops/rn-implement.yaml`
- **State**: `re_enqueue_unblocked` (ENH-2195 feature — re-enqueues deferred issues whose
  `blocked_by` deps are now done after a successful implementation)
- **Trigger**: MR-10 rule in `ll-loop validate` / `ll-loop run` pre-flight check

## Root Cause

The fail-open behavior in `re_enqueue_unblocked` is intentional: if the done-set cannot be
queried (JSON parse error, `ll-issues` failure, etc.), the affected issue stays deferred rather
than being incorrectly re-enqueued. The Python code prints explicit sentinel strings
(`DONE_SET_ERROR`, `PARSE_ERROR`, `UNRESOLVED`) that the outer shell checks for a non-empty
`$UNMET` variable — so the logic was correct all along. The missing piece was an explicit
`on_error:` route at the FSM state level, which the validator requires to confirm the error
path is intentionally handled.

## Fix

Added `on_error: dequeue_next` to `re_enqueue_unblocked` alongside the existing
`next: dequeue_next`. This routes any hard shell-level crash (e.g., Python interpreter
failure before sentinels are written) to `dequeue_next`, matching the fail-open intent, and
satisfies MR-10 by making the error route explicit.

```yaml
# rn-implement.yaml — re_enqueue_unblocked (after fix)
    next: dequeue_next
    on_error: dequeue_next   # fail-open: if the shell itself crashes, move on
```

## Verification

```
ll-loop validate rn-implement
# → rn-implement is valid  (no MR-10 WARNING)
```


## Session Log
- `hook:posttooluse-status-done` - 2026-06-29T16:17:22 - `d0fdbe7b-1ba1-430d-8e13-0dbd1b02f0ce.jsonl`

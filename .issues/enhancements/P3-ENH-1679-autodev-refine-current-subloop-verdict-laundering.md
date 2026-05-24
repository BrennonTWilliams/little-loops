---
discovered_date: 2026-05-24
discovered_by: audit-loop-run
status: open
---

# ENH-1679: Fix sub-loop verdict laundering in autodev `refine_current` state

## Summary

The `refine_current` state in `loops/autodev.yaml` invokes `refine-to-ready-issue` as a sub-loop
but sets `on_yes`, `on_no`, and `on_error` identically to `copy_broke_down`. The FSM verdict from
the sub-loop is silently discarded. A sub-loop that exits via its `failed` terminal (after
`diagnose → failed`) is treated identically to one that exits via `done`, because both produce
`on_yes` routing in the parent. The flag-file mechanism (`.loops/tmp/recursive-refine-broke-down`)
partially compensates, but if the sub-loop reaches `failed` without executing `write_broke_down`,
no flag is written and autodev proceeds as if refinement succeeded.

## Current Behavior

```yaml
refine_current:
  loop: refine-to-ready-issue
  on_yes: copy_broke_down    # sub-loop reached done terminal
  on_no: copy_broke_down     # sub-loop never started / queue empty
  on_error: copy_broke_down  # signal or executor crash
```

All three routes lead to `copy_broke_down`, which copies `.loops/tmp/recursive-refine-broke-down`
to `.loops/tmp/autodev-broke-down`. If the sub-loop exits via `failed` without writing the flag
file (e.g. an early `diagnose → failed` path), `autodev-broke-down` is absent or stale and
`check_broke_down` routes via `recheck_scores` as if refinement was attempted normally.

## Expected Behavior

The parent loop should distinguish:
- Sub-loop `done` terminal (successful refinement or broke-down) → proceed to `copy_broke_down` (current)
- Sub-loop `failed` terminal (unrecoverable error in `diagnose`) → write a failure sentinel and route to `dequeue_next` or a dedicated error state, skipping `implement_current`
- `on_error` (signal/executor crash) → same skip path

One clean approach: ensure `refine-to-ready-issue`'s `diagnose → failed` path always writes a
distinct failure flag (e.g. `.loops/tmp/refine-failed-hard`) so `copy_broke_down` can detect it.
An alternative: add a `write_refine_failed` state in `autodev` that the `on_error` path hits,
setting a flag before routing to `dequeue_next`.

## Discovered Via

`/ll:audit-loop-run autodev` on run `2026-05-24T140508` — sub-loop terminated by SIGKILL at
`confidence_check` (depth=1, iteration 7). The laundering defect was flagged during the sub-loop
verdict laundering check step.

## Proposed Fix

Option A — write a hard-failure flag in the sub-loop before `failed` terminal:

```yaml
# In loops/refine-to-ready-issue.yaml (or _subloop definition)
diagnose:
  action_type: prompt
  action: "..."
  next: write_diagnose_failed    # NEW

write_diagnose_failed:           # NEW
  action: printf '1' > .loops/tmp/refine-failed-hard
  action_type: shell
  on_error: failed
  next: failed

failed:
  terminal: true
```

Then in `autodev.yaml`, `copy_broke_down` reads the new flag and routes differently.

Option B — route `on_error` in `refine_current` to a dedicated state:

```yaml
refine_current:
  loop: refine-to-ready-issue
  on_yes: copy_broke_down
  on_no: dequeue_next      # sub-loop queue was empty — skip this issue
  on_error: skip_inflight  # signal or crash — mark inflight as skipped, move on

skip_inflight:             # NEW
  action: |
    echo "${captured.input.output}" >> .loops/tmp/autodev-skipped.txt
    rm -f .loops/tmp/autodev-inflight
  action_type: shell
  on_error: dequeue_next
  next: dequeue_next
```

## Acceptance Criteria

- [ ] If `refine-to-ready-issue` exits via `failed` terminal, `autodev` does NOT route the issue to `implement_current`
- [ ] If `refine_current` receives `on_error` (signal/crash), the in-flight issue is recorded as skipped and the queue continues
- [ ] Existing behavior for the `on_yes` (done terminal) path is unchanged
- [ ] `autodev` tests updated to cover `refine_current on_error → dequeue_next` path

## Labels

`enhancement`, `loops`, `autodev`, `refine-to-ready-issue`, `verdict-laundering`

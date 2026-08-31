---
id: ENH-3366
type: ENH
priority: P3
status: open
captured_at: '2026-08-30T23:30:00Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- ENH-1679
- ENH-2005
decision_needed: false
---

# ENH-3366: `delegate`(autodev) verdict is laundered through `recheck_set`

## Summary

In `scripts/little_loops/loops/auto-refine-and-implement.yaml`, the
`delegate` state that invokes the `autodev` sub-loop (line 299) routes both
outcomes to the same next state:

```
on_success: recheck_set   # line 320
on_failure: recheck_set   # line 321
```

`recheck_set` (line 324) only re-resolves the sprint/EPIC's current issue
list to look for newly-added descendants to re-dispatch — it never reads any
`subloop_outcome_autodev`-style sidecar, so it cannot tell whether `autodev`
actually reached a successful terminal or crashed/failed. This is the same
verdict-laundering shape [[ENH-1679]] fixed for `refine_current`'s sub-loop,
but on this different state, and it does not qualify for the ENH-2005 sidecar
exemption `/ll:audit-loop-run` checks for (the shared next state's action
does not contain `subloop_outcome_`).

## Expected Behavior

`autodev`'s real terminal verdict should be recoverable downstream — either
by giving `on_success`/`on_failure` distinct next states, or by having
`autodev`'s own finalize write a `subloop_outcome_autodev.txt` sidecar that
`recheck_set` (or a new intermediate state) reads before deciding whether to
re-dispatch, following the same artifact-channel pattern already used for
`auto-refine-and-implement`'s own outcome (`subloop_outcome_auto-refine-and-implement.txt`,
read by `sprint-refine-and-implement.yaml`'s `read_outcome` state).

## Impact

- **Priority**: P3 — matches [[ENH-1679]]'s severity class (same defect
  shape, different state); doesn't block the run today since `recheck_set`'s
  own `on_error` already routes to `verify` regardless, but a genuine
  `autodev` crash currently produces no distinguishable signal from a clean
  success at this join point.

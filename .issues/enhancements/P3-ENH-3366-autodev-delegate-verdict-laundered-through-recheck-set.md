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

## Current Behavior

`delegate`'s `on_success` and `on_failure` both route to `recheck_set` (lines
320-321). `recheck_set` only re-resolves the sprint/EPIC's descendant set to
find newly-added children; it never reads any `autodev` outcome sidecar, so
whether `autodev` reached a clean terminal or crashed/failed is indistinguishable
by the time execution reaches `recheck_set` — both paths look identical.

## Expected Behavior

`autodev`'s real terminal verdict should be recoverable downstream — either
by giving `on_success`/`on_failure` distinct next states, or by having
`autodev`'s own finalize write a `subloop_outcome_autodev.txt` sidecar that
`recheck_set` (or a new intermediate state) reads before deciding whether to
re-dispatch, following the same artifact-channel pattern already used for
`auto-refine-and-implement`'s own outcome (`subloop_outcome_auto-refine-and-implement.txt`,
read by `sprint-refine-and-implement.yaml`'s `read_outcome` state).

## Scope Boundaries

- Does not change `recheck_set`'s re-dispatch semantics for EPIC descendant
  resolution (ENH-2615) — only how it (or an intermediate state) learns
  `autodev`'s prior verdict before deciding to re-dispatch.
- Does not add a new terminal-verdict enum value beyond what's needed to
  distinguish an `autodev` crash from a clean pass at this join point; it
  reuses the existing sidecar-file pattern rather than inventing new
  `summary.json` fields.
- Does not touch `refine_current`'s sub-loop join, which [[ENH-1679]]
  already fixed.

## Program Design

### Signatures

- `subloop_outcome_autodev.txt: str` — new sidecar artifact `autodev`'s own `finalize` state writes under `${context.run_dir}`, mirroring the existing `subloop_outcome_auto-refine-and-implement.txt` convention `sprint-refine-and-implement.yaml`'s `read_outcome` state already reads.
- `recheck_set(RUN_DIR)` (`auto-refine-and-implement.yaml:324`) — extend to read `subloop_outcome_autodev.txt` before deciding on re-dispatch, or route through a new intermediate state that does so first.

### Call Path

`delegate` -> `autodev`'s `finalize` -> `subloop_outcome_autodev.txt` -> `recheck_set` -> distinct downstream routing instead of the current unconditional fan-in from both `on_success` and `on_failure`.

## Impact

- **Priority**: P3 — matches [[ENH-1679]]'s severity class (same defect
  shape, different state); doesn't block the run today since `recheck_set`'s
  own `on_error` already routes to `verify` regardless, but a genuine
  `autodev` crash currently produces no distinguishable signal from a clean
  success at this join point.

## Status

**Open** | Created: 2026-08-30 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`

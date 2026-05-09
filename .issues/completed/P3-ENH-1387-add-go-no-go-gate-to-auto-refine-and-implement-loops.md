---
discovered_date: 2026-05-09
discovered_by: conversation
---

# ENH-1387: Add go-no-go Gate to auto-refine-and-implement Loops

## Summary

Add `/ll:go-no-go` as an adversarial gate step between issue selection and implementation in both `auto-refine-and-implement` and `sprint-refine-and-implement` loops. Issues that pass refinement but receive a NO-GO verdict are skipped back to the queue rather than being sent to the expensive `ll-auto` implementation step.

## Motivation

The `auto-refine-and-implement` and `sprint-refine-and-implement` loops previously had no checkpoint between refinement and implementation. Any issue that survived `recursive-refine` would be implemented unconditionally, even if the issue had marginal value or poor timing relative to other work. Adding a go-no-go gate before `implement_issue` — the most expensive step in the loop — lets the adversarial review filter out low-value work before committing implementation cost.

## Changes Made

### `scripts/little_loops/loops/auto-refine-and-implement.yaml`

- Added `go_no_go` state between `implement_next` and `implement_issue`
- Updated `implement_next.on_yes` to route to `go_no_go` (was `implement_issue`)
- Updated NOTE comment to include `go_no_go` in the mirrored-state list

### `scripts/little_loops/loops/sprint-refine-and-implement.yaml`

- Same three changes, mirroring the auto loop

### New State (both files)

```yaml
go_no_go:
  fragment: shell_exit
  action: "ll-action go-no-go \"${captured.impl_id.output} --check --auto\""
  on_yes: implement_issue
  on_no: implement_next
  on_error: implement_issue
```

## Design Decisions

- **`fragment: shell_exit`**: The `--check` flag on `go-no-go` exits 0 (GO) or 1 (NO-GO), mapping cleanly to `on_yes`/`on_no` exit-code routing.
- **`--auto` flag**: Suppresses interactive prompts; required in automation context.
- **`on_error: implement_issue`** (fail open): A go-no-go error (e.g. transient Claude failure) does not silently drop a valid issue — the loop proceeds to implement rather than skip.
- **`on_no: implement_next`**: A NO-GO verdict returns to the impl queue for the next issue. The issue is already in the skip file from `get_passed_issues`, so it won't be retried in this run.
- **Placement**: Option B (post-refinement, pre-implementation) was chosen over pre-refinement because go-no-go yields a more meaningful verdict on a fully refined issue, and refinement is cheaper than implementation.

## Status

**Completed** | Created: 2026-05-09 | Completed: 2026-05-09 | Priority: P3

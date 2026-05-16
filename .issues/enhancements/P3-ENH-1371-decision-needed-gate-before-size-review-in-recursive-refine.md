---
id: ENH-1371
type: ENH
priority: P3
status: completed
discovered_date: 2026-05-05
discovered_by: audit
testable: true
confidence_score: 95
outcome_confidence: 90
---

# ENH-1371: Add decision_needed Gate Before Size-Review in recursive-refine

## Summary

`recursive-refine` was calling `/ll:issue-size-review --auto` on issues that still had `decision_needed: true` — meaning competing implementation options were unresolved. Sizing/decomposing an issue before its implementation path is selected produces meaningless child issues. This adds a `check_decision_needed` gate state that skips size-review for undecided issues and surfaces them in the run summary.

## Current Behavior

The path from `check_depth` jumped directly to `run_size_review` with no check for `decision_needed: true`. An issue waiting on `/ll:decide-issue` would be decomposed prematurely with the wrong implementation scope.

## Expected Behavior

Before running `/ll:issue-size-review --auto`, the loop checks whether the issue file contains `decision_needed: true`. If it does, the issue is written to a new `skipped-decision.txt` category and skipped; the loop moves on to the next queued issue. The final summary and decomposition tree both label these issues as `decision-needed`.

## Acceptance Criteria

- [x] New `check_decision_needed` state inserted between `check_depth` and `run_size_review`
- [x] Issues with `decision_needed: true` are written to `recursive-refine-skipped-decision.txt` and the shared `recursive-refine-skipped.txt`
- [x] Issues without `decision_needed: true` (or whose file is missing) proceed normally to `run_size_review`
- [x] `parse_input` initialises `recursive-refine-skipped-decision.txt` alongside the other skip-category files
- [x] `done` summary prints a `Decision (%d): <ids>` row
- [x] Decomposition tree renderer labels skipped decision-needed issues as `(skipped: decision-needed)`

## Proposed Solution

### New state

```yaml
check_decision_needed:
  action: |
    ISSUE_FILE=$(find .issues -name "*-${captured.input.output}-*" \
      ! -path "*/completed/*" 2>/dev/null | head -1)
    if [ -n "$ISSUE_FILE" ] && grep -q "decision_needed: true" "$ISSUE_FILE"; then
      echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped-decision.txt
      echo "${captured.input.output}" >> .loops/tmp/recursive-refine-skipped.txt
      exit 1
    fi
    exit 0
  fragment: shell_exit
  on_yes: run_size_review
  on_no: dequeue_next
  on_error: run_size_review   # missing file → don't block
```

`on_error` routes to `run_size_review` so a file-not-found condition (e.g. issue already moved to completed mid-run) does not silently skip the size-review step.

## Impact

- **Priority**: P3 — prevents meaningless decompositions that produce child issues scoped to the wrong implementation option
- **Effort**: Small — one new state, minor wiring and summary updates
- **Risk**: None — additive gate; issues without `decision_needed` are unaffected
- **Breaking Change**: No

## Status

**Completed** | Created: 2026-05-05 | Resolved: 2026-05-05 | Priority: P3

## Resolution

Implemented directly in `scripts/little_loops/loops/recursive-refine.yaml` in a single session.

### Changes Made

- **Modified**: `scripts/little_loops/loops/recursive-refine.yaml`
  - `parse_input`: added `printf '' > .loops/tmp/recursive-refine-skipped-decision.txt` initialisation
  - `check_depth`: `on_yes`/`on_error` redirected from `run_size_review` → `check_decision_needed`
  - **New state** `check_decision_needed` inserted between `check_depth` and `run_size_review`
  - `done` summary: added `DECISION_SKIPPED_IDS` variable, count, list, and `printf 'Decision (%d): ...'` row
  - `done` tree renderer: added `decision_skipped` set; `get_skip_reason` returns `'decision-needed'` for matching IDs

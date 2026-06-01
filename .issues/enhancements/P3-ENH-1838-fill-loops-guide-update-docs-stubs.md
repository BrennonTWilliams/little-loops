---
id: ENH-1838
type: ENH
priority: P3
title: Fill update-docs stubs in LOOPS_GUIDE.md
status: done
testable: false
created: 2026-05-31
updated: 2026-05-31
completed_at: '2026-06-01T02:39:19Z'
---

## Summary

`LOOPS_GUIDE.md` has 8 unfilled `<!-- TODO: update-docs stub -->` blocks left
open since May 2026. Each block marks a section where the feature was added
but its documentation was deferred.

## Stubs to Fill

Approximate line numbers at time of audit (2026-05-31):

| ~Line | Section |
|-------|---------|
| 71 | Safety limits section (marked Stub) |
| 548 | `rn-refine` write-back + apply commands |
| 768 | `scan-and-implement` expansion (marked Stub) |
| 1165 | Base64 image embedding in `hitl-compare` |
| 1416 | `cli-anything-bootstrap` FSM flow, context variables, and examples (marked Stub) |
| 1472 | BUG-1815 exit-code short-circuit for non-exit-code evaluators |
| 1645 | `retryable_exit_codes` field description |
| 2584 | Server-error automatic retry section (marked Stub) |

## Acceptance Criteria

- [ ] All 8 stubs are replaced with real documentation content
- [ ] No `<!-- TODO: update-docs stub -->` comments remain in LOOPS_GUIDE.md
- [ ] Each filled section is consistent with the implemented feature behaviour
      (verified by reading the corresponding YAML / Python source)

## Implementation Notes

- Grep for `TODO: update-docs stub` in `docs/guides/LOOPS_GUIDE.md` to find
  exact current line numbers (they shift as other edits land)
- For BUG-1815 exit-code short-circuit: read `scripts/little_loops/loops/runner.py`
  around the `exit_code` evaluator path
- For `retryable_exit_codes`: read loop schema in
  `scripts/little_loops/loops/schema.py`
- For `rn-refine` write-back: read `loops/rn-refine.yaml` + any apply commands
  in the runner
- For `cli-anything-bootstrap`: read
  `scripts/little_loops/loops/cli-anything-bootstrap.yaml`


## Session Log
- `/ll:ready-issue` - 2026-06-01T02:39:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3a21d8c-f37e-4427-96a3-e58b86566be2.jsonl`


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-05-31
- **Reason**: already_fixed
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.

---
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# BUG-912: `refine-to-ready-issue` loop missing `/ll:verify-issues` step causes infinite NEEDS_VERIFY cycle

## Summary

The `refine-to-ready-issue` sub-loop never calls `/ll:verify-issues`, but `ll-issues next-action` gates advancement on that command appearing in an issue's `session_commands`. As a result, after the sub-loop completes successfully (confidence check passes), `next-action` still returns `NEEDS_VERIFY <id>` and the outer `issue-refinement` loop re-processes the same issue indefinitely. Issues 8972–8974 (queued behind 8975) are never reached.

## Current Behavior

1. `issue-refinement` loop calls `ll-issues next-action` → `NEEDS_VERIFY ENH-8975`
2. Delegates to `refine-to-ready-issue` sub-loop: runs `format_issue`, `refine_issue`, `confidence_check` (passes at 0.97–1.00)
3. Sub-loop exits as `done`
4. `issue-refinement` calls `ll-issues next-action` again → **still** `NEEDS_VERIFY ENH-8975`
5. Steps 2–4 repeat forever (observed 3+ full cycles within one run before truncation)

## Expected Behavior

After `confidence_check` passes, the sub-loop should run `/ll:verify-issues <id>` so that `next-action` can advance the issue to the next stage (or to `ALL_DONE` if all issues pass). The outer loop should then move on to the remaining queued issues.

## Motivation

This bug causes the entire `issue-refinement` automation to stall indefinitely on the first `NEEDS_VERIFY` issue it encounters. All subsequent issues (passed via `ll-loop run issue-refinement 8972,8973,8974,8975`) are never processed. The loop will run until it hits `max_iterations: 200`, consuming substantial API budget (each iteration costs ~10 minutes of LLM time) with zero net progress after the first cycle.

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchor**: `confidence_check` state (transitions to `done` on yes)
- **Cause**: The `done` terminal state is reached immediately after `confidence_check` passes, with no intervening step to call `/ll:verify-issues`. Meanwhile, `next-action` (`scripts/little_loops/cli/issues/next_action.py`, function `cmd_next_action`, line 38) checks `"/ll:verify-issues" not in issue.session_commands` and returns `NEEDS_VERIFY` whenever that command hasn't been run — which it never is in the current sub-loop.

## Steps to Reproduce

1. Run `ll-loop run issue-refinement <issue-ids>` where at least one issue needs verification
2. Observe: `ll-issues next-action` repeatedly returns `NEEDS_VERIFY <same-id>` across loop iterations
3. Observe: `refine-to-ready-issue` sub-loop completes with confidence ≥ thresholds but issue never advances

## Proposed Solution

Add a `verify_issue` state to `refine-to-ready-issue.yaml` between `confidence_check` (on_yes) and `done`:

```yaml
confidence_check:
  ...
  on_yes: verify_issue   # was: done
  on_no: refine_issue
  on_error: failed

verify_issue:
  action: "/ll:verify-issues ${captured.issue_id.output}"
  action_type: slash_command
  next: done
  on_error: failed
```

This ensures `session_commands` contains `/ll:verify-issues` before the sub-loop exits, satisfying `next-action`'s gate condition.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add `verify_issue` state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/issue-refinement.yaml` — invokes the sub-loop via `loop: refine-to-ready-issue`
- `scripts/little_loops/cli/issues/next_action.py` — `cmd_next_action()` reads `session_commands` to gate NEEDS_VERIFY

### Similar Patterns
- `scripts/little_loops/loops/issue-refinement.yaml` — verify that the outer loop's state machine handles the new terminal state correctly

### Tests
- `scripts/tests/` — search for tests covering `refine-to-ready-issue` loop or `next-action` NEEDS_VERIFY logic

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `verify_issue` state to `refine-to-ready-issue.yaml` after `confidence_check` on_yes path
2. Update `confidence_check.on_yes` to point to `verify_issue` instead of `done`
3. Verify `next-action` returns `ALL_DONE` (or moves to next issue) after a successful sub-loop run in tests or a dry-run

## Impact

- **Priority**: P2 — Blocks entire `issue-refinement` loop from making progress; wastes significant API budget per run
- **Effort**: Small — One-line YAML change to add a state and redirect a transition
- **Risk**: Low — Additive change; only affects sub-loop exit path when confidence check passes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `issue-refinement`, `refine-to-ready`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eaf73d5c-81eb-45a4-a5e6-b157f77ba059.jsonl`

---

**Open** | Created: 2026-04-01 | Priority: P2

---
discovered_date: 2026-03-06
discovered_by: capture-issue
---

# BUG-617: Sprint sequential retry proceeds to Phase 2 implementation despite open blocker warnings from `ready-issue`

## Summary

During `ll-sprint run` sequential retry, after `ready-issue` completes Phase 1, the sprint runner unconditionally proceeds to Phase 2 (implementation) for any verdict that is not `CLOSE`. It does not check for a `BLOCKED` verdict (or inspect blocker warnings in the output body), so issues with open dependencies get implemented prematurely.

## Steps to Reproduce

1. Run `ll-sprint run <sprint>` where a wave contains an issue with an open blocker
2. The issue fails parallel processing (e.g. merge conflict) and enters sequential retry
3. `ready-issue` runs and returns `CORRECTED` (or, after BUG-616 is fixed, `BLOCKED`) with a warning about an open blocker
4. Sprint runner proceeds to Phase 2: implementation runs immediately
5. Implementation modifies files that the open blocker also targets → merge conflict risk or incorrect output

## Actual Behavior

Sequential retry logic (in `scripts/little_loops/cli/sprint/run.py` or equivalent orchestrator) branches only on `CLOSE` verdict to skip implementation. Any other verdict (`PASS`, `CORRECTED`, and eventually `BLOCKED`) falls through to Phase 2.

Observed in `ll-sprint-cli-polish.log` at lines 421–424:
```
[20:32:16] Issue ENH-552 corrected and ready for implementation
[20:32:16] Phase 1 (ready-issue) completed in 2.2 minutes
[20:32:16] Phase 2: Implementing ENH-552...   ← should have stopped here
[20:32:16] Running: claude ... /ll:manage-issue enhancement improve ENH-552
```

## Expected Behavior

When `ready-issue` returns `BLOCKED` (once BUG-616 is fixed), the sprint runner sequential retry must:
1. Log the blocker reason
2. Mark the issue as `skipped_blocked` in sprint state (not `failed`)
3. Continue to the next issue without running Phase 2 or Phase 3

Additionally, as a defense-in-depth measure, if the `ready-issue` output body contains an open blocker warning even under a non-`BLOCKED` verdict, the runner should log a warning. The hard gate should be the verdict enum once BUG-616 is fixed.

## Root Cause

**File**: `scripts/little_loops/cli/sprint/run.py`
**Anchor**: sequential retry loop / Phase 1 verdict dispatch

The verdict dispatch only handles `CLOSE`:
```python
if verdict == "CLOSE":
    # skip implementation
else:
    # proceed to Phase 2  ← no BLOCKED branch
```

There is no `BLOCKED` branch because `ready-issue` never emitted that verdict (see BUG-616).

## Proposed Fix

1. After BUG-616 adds `BLOCKED` verdict: add a branch in the verdict dispatch:
   ```python
   elif verdict == "BLOCKED":
       log(f"{issue_id} skipped — open blocker detected by ready-issue")
       state.mark_skipped_blocked(issue_id)
       continue
   ```
2. Add `skipped_blocked` to sprint state schema so it surfaces in the wave summary
3. Wave summary should report blocked issues separately from failed issues

## Impact

- **Priority**: P2 — causes incorrect automation behavior; depends on BUG-616 being fixed first for the full fix, but the branch should be added proactively
- **Effort**: Low — one new `elif` branch + state schema update
- **Risk**: Low — additive; existing behavior unchanged for `PASS` / `CORRECTED` / `CLOSE`
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `automation`, `ready-issue`

## Status

Open

## Blocked By

- BUG-616 (`ready-issue` must emit `BLOCKED` verdict before this fix is meaningful)

## Session Log
- `/ll:capture-issue` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec3d1ef8-aeec-4ccb-bd08-ffee1f74e5ef.jsonl`

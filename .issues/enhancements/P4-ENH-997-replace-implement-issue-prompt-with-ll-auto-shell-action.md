---
discovered_date: 2026-04-08
discovered_by: manual
completed_date: 2026-04-08
---

# ENH-997: Replace implement_issue prompt with ll-auto shell action

## Summary

Refactored the `auto-refine-and-implement` loop to replace the `implement_issue` prompt state (which invoked `/ll:manage-issue` via Claude) with a direct `ll-auto --only <issue_id>` shell invocation.

## Context

The `implement_issue` state in `auto-refine-and-implement.yaml` previously used `action_type: prompt` to ask Claude to run `/ll:manage-issue`. This approach routes implementation through a Claude prompt rather than using the existing `ll-auto` CLI directly, which is the canonical automation entrypoint for issue implementation.

The `auto-issue-processor.yaml` (an untracked scratch file at the repo root) already demonstrated this shell-based pattern.

## Changes Made

**File:** `scripts/little_loops/loops/auto-refine-and-implement.yaml`

Replaced `implement_issue` state:

```yaml
# Before
implement_issue:
  action: "Run /ll:manage-issue to implement issue ${captured.input.output}."
  action_type: prompt
  capture: implement_result
  next: get_next_issue

# After
implement_issue:
  action: "ll-auto --only ${captured.input.output}"
  action_type: shell
  next: get_next_issue
```

- `action_type: prompt` → `action_type: shell`
- Action changed to direct CLI invocation: `ll-auto --only ${captured.input.output}`
- Removed unused `capture: implement_result` (nothing downstream referenced it)

## Files Modified

- `scripts/little_loops/loops/auto-refine-and-implement.yaml`

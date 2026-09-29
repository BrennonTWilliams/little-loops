---
id: ENH-3654
type: ENH
title: 'refine-to-ready workflow: hand reconcile off to the user instead of reading
  the command file'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T04:19:37Z'
---

# ENH-3654: refine-to-ready workflow: hand reconcile off to the user instead of reading the command file

## Summary

`/ll:reconcile-issue` carries `disable-model-invocation: true` because it rewrites an issue's directive sections in place, so the user runs it. The `refine-to-ready` workflow (`.claude/workflows/refine-to-ready.js`) reaches its reconcile step, and when the command cannot be invoked as a skill it falls back to reading `commands/reconcile-issue.md` by hand and following it. That routes around the flag: the model performs the in-place rewrite the flag exists to keep with the user.

## Current Behavior

When the reconcile step is needed, the workflow reads the command file directly and executes its instructions, bypassing `disable-model-invocation`. Found during FEAT-3535 refinement; a session that removed the flag to work around it was reverted, and the flag was kept.

## Expected Behavior

The workflow's reconcile step hands off to the user: it stops with a clear message naming the issue and the exact command to run (`/ll:reconcile-issue <ID>`), records the pending reconcile in its result, and resumes when re-run after the user has reconciled. The flag stays in place.

## Motivation

`disable-model-invocation` is a deliberate guard on an in-place rewrite. A workflow fallback that reads the file and does the work anyway defeats it silently, and the rewritten directive sections are what confidence scoring and implementation then trust.

## Proposed Solution

Replace the read-the-command-file fallback in the reconcile step of `.claude/workflows/refine-to-ready.js` with a handoff result (`needs_user_reconcile` plus the command to run). Mirror the same behavior in `loops/refine-to-ready-issue.yaml` if it has the same fallback, and add a test that the workflow never opens `commands/reconcile-issue.md`.

## Integration Map

### Files to Modify
- `.claude/workflows/refine-to-ready.js` (reconcile step)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (check for the same fallback)

### Tests
- A test asserting the reconcile step returns a handoff result and does not read the command file.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3.
- **Effort**: Small.
- **Risk**: Low; changes only what happens when reconcile is required.

## Acceptance Criteria

- [ ] The workflow's reconcile step never reads or executes `commands/reconcile-issue.md` itself.
- [ ] When reconcile is needed the workflow ends with a handoff result naming `/ll:reconcile-issue <ID>`.
- [ ] `commands/reconcile-issue.md` keeps `disable-model-invocation: true`.

## Related

- FEAT-3535 refinement session (the flag experiment that was reverted).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-29T04:19:44 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`

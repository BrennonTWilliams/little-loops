---
id: BUG-895
title: "GETTING_STARTED.md lists stale status values inconsistent with ISSUE_MANAGEMENT_GUIDE"
status: open
priority: P3
blocked_by: []
---

## Summary

`GETTING_STARTED.md` documents a different set of issue `status` field values than the authoritative table in `ISSUE_MANAGEMENT_GUIDE.md`, leaving users with incorrect expectations about valid status values.

## Current Behavior

`docs/guides/GETTING_STARTED.md:178` says:
> The `status` field inside the issue file tracks where the issue is in the workflow: `open`, `backlog`, `active`, `in-progress`, `blocked`, or `completed`.

## Expected Behavior

The values should match the authoritative table in `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`:

| Value | Meaning |
|-------|---------|
| `open` | Newly captured, not yet triaged |
| `backlog` | Triaged, queued for a later sprint |
| `active` | Currently being worked on |
| `completed` | Work finished and committed |
| `resolved` | Closed without a code change |
| `wont_do` | Decided not to implement |
| `superseded` | Replaced by another issue |

`in-progress` and `blocked` in GETTING_STARTED appear to be phase names from the lifecycle diagram (not frontmatter `status` values), and are not part of the ISSUE_MANAGEMENT_GUIDE's canonical table.

## Root Cause

`GETTING_STARTED.md` was not updated when the canonical status value set was finalized in `ISSUE_MANAGEMENT_GUIDE.md`. The `in-progress` and `blocked` values look like they were copied from the lifecycle workflow diagram rather than the frontmatter schema.

## Integration Map

- `docs/guides/GETTING_STARTED.md` — line 178, the sentence describing status values
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — lines 107–117, the authoritative status value table

## Implementation Steps

1. Verify that the ISSUE_MANAGEMENT_GUIDE table is indeed canonical (check `scripts/little_loops/` for any enforcement of these values)
2. Update `GETTING_STARTED.md:178` to list the correct set: `open`, `backlog`, `active`, `completed`, `resolved`, `wont_do`, `superseded`
3. Remove `in-progress` and `blocked` from the GETTING_STARTED description (these are lifecycle phases, not status field values)

## Impact

**Priority**: P3 — Medium
**Effort**: Low (single sentence change)
**Risk**: Low

New users reading GETTING_STARTED will expect `in-progress` and `blocked` to be valid status values and be confused when they don't appear in the authoritative reference.

---

**Status**: open | Captured: 2026-03-26 | Source: /ll:audit-docs docs/guides/

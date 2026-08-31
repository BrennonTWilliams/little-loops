---
id: BUG-3369
type: BUG
title: Epic auto-merge gate treats any cancelled child as a permanent block instead
  of resolving it like done
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-31'
captured_at: '2026-08-31T21:19:28Z'
---

# BUG-3369: Epic auto-merge gate treats any cancelled child as a permanent block instead of resolving it like done

## Summary

The epic-merge completion gate (`merge_epic_branch` state in `scripts/little_loops/loops/auto-refine-and-implement.yaml`, roughly lines 610-716) computes `all_done` from `ll-issues epic-progress <EPIC-ID>` as:

```
total > 0 and done_count == total and blocked_count == 0 and cancelled_count == 0
```

If `all_done` is false, the state prints `held_open` and the epic branch is never merged to the base branch — the gate never even reaches the `epic_cfg.verify_before_merge` check that would otherwise decide whether to gate the merge on the verify verdict.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Not prescriptive, but the natural fix mirrors how `done`/`cancelled` are already treated as the two terminal states elsewhere (dependency-edge resolution): change the completion condition from `done_count == total` to `(done_count + cancelled_count) == total`, keeping the `blocked_count == 0` requirement as-is so genuinely blocked children still hold the branch open.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 — doesn't block any specific in-flight work today (this instance was worked around by hand), but silently strands every future epic with a cancelled child, and the failure mode (branch just never merges, no error) is easy to miss.
- **Breaking Change**: No — loosens an over-strict gate condition.

## Root Cause

`cancelled` is documented as one of the two normal terminal statuses for an issue (`.claude/CLAUDE.md`'s Issue File Format section lists `done`/`cancelled` as the pair that resolve `blocked_by`/`depends_on` edges elsewhere in the codebase). But this gate's `done_count == total` condition implicitly requires every child to specifically be `done` — any `cancelled` child makes `all_done` permanently false, with no path to ever becoming true, regardless of how many other children complete or what the verify gate reports.

## Discovered via

`EPIC-1463` (`ll-loop run sprint-refine-and-implement EPIC-1463`, run dir `.loops/runs/sprint-refine-and-implement-20260831T135628/`): `ll-issues epic-progress EPIC-1463` reported 30 children — 20 done, 5 cancelled, 3 open, 2 deferred. Because `cancelled_count = 5 > 0`, the merge gate held the branch open (`summary.json`: `"epic_merge_verdict":"held_open"`) even after a child issue (ENH-1718) completed and verified cleanly in isolation. The branch was merged to main by hand (commit 6e158e703) since the automated gate can never fire for this epic as currently constituted.

This is a general defect, not specific to EPIC-1463 — any epic with at least one legitimately cancelled child (a normal, common outcome of refinement/tradeoff-review) is permanently unable to auto-merge.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-31 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-31T21:19:35 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`

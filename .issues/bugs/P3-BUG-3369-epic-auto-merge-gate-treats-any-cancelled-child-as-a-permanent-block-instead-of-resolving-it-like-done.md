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

The `merge_epic_branch` completion gate computes `all_done` as `total > 0 and done_count == total and blocked_count == 0 and cancelled_count == 0`. Any epic with even one `cancelled` child (a normal, common outcome of refinement/tradeoff-review) has `cancelled_count > 0`, so `all_done` is permanently false — the epic branch is never merged to the base branch, and the gate never even reaches the `epic_cfg.verify_before_merge` check. This happened silently for EPIC-1463 (20 done, 5 cancelled, 3 open, 2 deferred), which required a manual merge (commit 6e158e703).

## Expected Behavior

`cancelled` children should resolve the completion gate the same way `done` children do, since `.claude/CLAUDE.md`'s Issue File Format section documents `done`/`cancelled` as the two terminal statuses elsewhere (dependency-edge resolution). An epic whose remaining children are all `done` or `cancelled`, with none `blocked`, should be eligible to auto-merge — not permanently stuck.

## Motivation

This is a general defect, not specific to EPIC-1463: any epic with at least one legitimately cancelled child is permanently unable to auto-merge, with no error and no path to ever becoming eligible. The failure mode (branch just never merges) is silent and easy to miss, and it forces manual intervention on every affected epic.

## Proposed Solution

Not prescriptive, but the natural fix mirrors how `done`/`cancelled` are already treated as the two terminal states elsewhere (dependency-edge resolution): change the completion condition from `done_count == total` to `(done_count + cancelled_count) == total`, keeping the `blocked_count == 0` requirement as-is so genuinely blocked children still hold the branch open.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `merge_epic_branch` state's `all_done` condition (roughly lines 610-716)

### Dependent Files (Callers/Importers)
- Any FSM loop that reuses the same `merge_epic_branch` completion-gate pattern (grep for `done_count == total` and `cancelled_count == 0` in `scripts/little_loops/loops/*.yaml`)

### Similar Patterns
- Dependency-edge resolution already treats `done`/`cancelled` as the two terminal statuses (`.claude/CLAUDE.md` § Issue File Format) — this fix brings the completion gate in line with that existing convention

### Tests
- `scripts/tests/test_builtin_loops.py` (or the FSM/loop test module covering `merge_epic_branch`) — add a case with a mix of `done` and `cancelled` children asserting `all_done` resolves true

### Documentation
- N/A

### Configuration
- N/A

## Program Design

### Types

- (none — this is a condition-expression fix, no new types)

### Signatures

- `compute_all_done(done_count: int, cancelled_count: int, blocked_count: int, total: int) -> bool` — returns `total > 0 and (done_count + cancelled_count) == total and blocked_count == 0`

### Call Path

`ll-issues epic-progress <EPIC-ID>` -> `merge_epic_branch` state (`scripts/little_loops/loops/auto-refine-and-implement.yaml`) `all_done` condition -> `epic_cfg.verify_before_merge` check

## Implementation Steps

1. Change the `all_done` condition in `merge_epic_branch` from `done_count == total` to `(done_count + cancelled_count) == total`, keeping `blocked_count == 0` as-is.
2. Add a test covering an epic with a mix of `done` and `cancelled` children (and none `blocked`) asserting `all_done` resolves true and the branch reaches the `verify_before_merge` check.
3. Verify existing tests for the fully-`done` and any-`blocked` cases still pass unchanged.

## Impact

- **Priority**: P3 — doesn't block any specific in-flight work today (this instance was worked around by hand), but silently strands every future epic with a cancelled child, and the failure mode (branch just never merges, no error) is easy to miss.
- **Effort**: Small — a one-line condition change plus a test case; the fix is already fully specified in Proposed Solution.
- **Risk**: Low — narrows a false-negative gate condition to match an existing terminal-status convention (`done`/`cancelled`) used elsewhere in the codebase; does not change behavior for epics with no cancelled children.
- **Breaking Change**: No — loosens an over-strict gate condition.

## Steps to Reproduce

1. Create (or use) an EPIC whose children include at least one `cancelled` issue alongside `done` children, with no `blocked` children (e.g. EPIC-1463: 20 done, 5 cancelled, 3 open, 2 deferred).
2. Run an FSM loop that reaches the `merge_epic_branch` state (e.g. `ll-loop run sprint-refine-and-implement <EPIC-ID>`).
3. Observe the state prints `held_open` and the epic branch is never merged, even though the `all_done` condition should reasonably be satisfied once `blocked_count == 0` — check `summary.json` for `"epic_merge_verdict":"held_open"`.

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
- `/ll:format-issue` - 2026-08-31T21:28:22 - `24eb8111-3a52-4364-98e0-699548ae82fc.jsonl`
- `/ll:capture-issue` - 2026-08-31T21:19:35 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`

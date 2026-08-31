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
decision_needed: true
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

**Option A**: Apply the fix as proposed — change `merge_epic_branch`'s `all_done` condition from `done_count == total` to `(done_count + cancelled_count) == total`, keeping `blocked_count == 0` as-is. This brings the FSM-loop epic-merge gate in line with the `done`/`cancelled`-terminal convention used by dependency-edge resolution (`_TERMINAL_STATUSES`, `issue_progress.py:14`) and the `ll-issues epic-progress`/`list_cmd.py` progress badges.

**Option B**: Do not change the condition alone — or change it together with `ParallelOrchestrator._maybe_complete_epic` (`orchestrator.py:1472-1479`). The sibling non-FSM implementation of this same epic-merge-completion feature (FEAT-2449, `done`) intentionally excludes `cancelled` from its done-count, with an explicit code comment ("a cancelled child must NOT trigger a merge into base") and a passing regression test (`test_orchestrator.py::test_cancelled_child_does_not_trigger_merge`). `merge_epic_branch`'s current shape matches that intentional design, not a stray duplicate bug. Applying Option A to `merge_epic_branch` alone would make the FSM-loop and `ll-parallel` orchestrator paths behave differently for the identical epic-completion scenario — the same epic could auto-merge via one runner and stay held open via the other.

**Recommended**: Undetermined from the code alone — resolving this requires deciding whether FEAT-2449's "cancelled must not trigger merge" design is still intended policy, or should be revisited given how common post-refinement cancellation has turned out to be (per this issue's own Motivation). Whichever way it resolves, `merge_epic_branch` and `_maybe_complete_epic` should end up consistent with each other.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` (`scripts/little_loops/issue_progress.py:14`) is the canonical definition backing the done/cancelled-terminal convention this issue cites; consumers treating the two as equivalent include `issue_lifecycle.py:1051`, `issue_lifecycle.py:4091`, `cli/sprint/edit.py:76` (`--prune`), `cli/issues/list_cmd.py:247` (epic progress badge), `cli/issues/epic_progress.py:72-76` (`ll-issues epic-progress` CLI display), and FSM defer-guard states asserted by `test_builtin_loops.py:6803,7728`.
- A second, deliberately divergent implementation exists: `ParallelOrchestrator._maybe_complete_epic()` (`scripts/little_loops/parallel/orchestrator.py:1416-1512`, condition at `:1472-1479`) computes the same `done_count == total and cancelled_count == 0` shape as `merge_epic_branch` — but per that function's own code comment and FEAT-2449's design record (`.issues/features/P3-FEAT-2449-per-epic-integration-branch-completion-flow.md:139-165,496-506`, status `done`), excluding `cancelled` from the epic-branch-merge done-count is intentional: "a cancelled child must NOT trigger a merge into base." Covered by `scripts/tests/test_orchestrator.py:1633-1643` `test_cancelled_child_does_not_trigger_merge`, which asserts no merge call fires for a cancelled-plus-done child mix.
- `compute_epic_progress()` (`scripts/little_loops/issue_progress.py:120-184`) is the single function both `merge_epic_branch` and `_maybe_complete_epic` call for `EpicProgress.by_status` — a plain `dict[str, int]` keyed by raw status string; it exposes no separate `done_count`/`cancelled_count`/`total` fields, so both callers independently recompute their own numerator from `by_status.get(...)`.
- `merge_epic_branch`'s own header comment (`auto-refine-and-implement.yaml`, near line 610) documents it as "the FSM-loop-side equivalent of `ParallelOrchestrator._maybe_complete_epic`" — the two are meant to mirror each other's behavior for the same underlying feature, which is the crux of the Proposed Solution decision point below.
- No `merge_epic_branch`-covering test in `scripts/tests/test_builtin_loops.py` (class beginning ~line 5860) currently exercises a `cancelled` child status — the two existing cases (`test_merges_when_all_children_done`, `test_held_open_when_child_not_done`) use only `done`/`in_progress`. A new test would use the same `_setup_repo`/`_write_issues`/`_run`/`_branches` helpers already defined in that class.
- No other loop YAML under `scripts/little_loops/loops/*.yaml` reuses this `done_count == total` / `cancelled_count == 0` gate shape — `orchestrator.py` is the only other site with the same pattern (repo-wide grep, unfiltered).

## Program Design

### Types

- (none — this is a condition-expression fix, no new types)

### Signatures

- `compute_all_done(done_count: int, cancelled_count: int, blocked_count: int, total: int) -> bool` — returns `total > 0 and (done_count + cancelled_count) == total and blocked_count == 0`

### Call Path

`ll-issues epic-progress <EPIC-ID>` -> `merge_epic_branch` state (`scripts/little_loops/loops/auto-refine-and-implement.yaml`) `all_done` condition -> `epic_cfg.verify_before_merge` check

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- `compute_epic_progress()` (`scripts/little_loops/issue_progress.py:120-184`) returns `EpicProgress.by_status: dict[str, int]`; its internal `done_count` (line 158) already sums `_TERMINAL_STATUSES` but that sum is used only for `percent_done`, not exposed as a queryable field — the fix's `done_count`/`cancelled_count` inputs are `prog.by_status.get("done", 0)` / `prog.by_status.get("cancelled", 0)`, matching the shape `merge_epic_branch` already reads today (`auto-refine-and-implement.yaml:707-710`).

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
- `/ll:refine-issue` - 2026-08-31T21:40:32 - `a39b473b-2472-40a4-90ee-2531e40475f9.jsonl`
- `/ll:format-issue` - 2026-08-31T21:28:22 - `24eb8111-3a52-4364-98e0-699548ae82fc.jsonl`
- `/ll:capture-issue` - 2026-08-31T21:19:35 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`

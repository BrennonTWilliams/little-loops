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
decision_needed: false
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

Per the Decision Rationale below (Option B selected): change the completion condition from `done_count == total` to `(done_count + cancelled_count) == total` — keeping the `blocked_count == 0` requirement as-is so genuinely blocked children still hold the branch open — in **both** `merge_epic_branch` (`auto-refine-and-implement.yaml:707-713`) and `ParallelOrchestrator._maybe_complete_epic` (`orchestrator.py:1472-1479`), not `merge_epic_branch` alone, so the FSM-loop and `ll-parallel` paths stay consistent with each other.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

**Option A**: Apply the fix as proposed — change `merge_epic_branch`'s `all_done` condition from `done_count == total` to `(done_count + cancelled_count) == total`, keeping `blocked_count == 0` as-is. This brings the FSM-loop epic-merge gate in line with the `done`/`cancelled`-terminal convention used by dependency-edge resolution (`_TERMINAL_STATUSES`, `issue_progress.py:14`) and the `ll-issues epic-progress`/`list_cmd.py` progress badges.

**Option B**: Do not change the condition alone — or change it together with `ParallelOrchestrator._maybe_complete_epic` (`orchestrator.py:1472-1479`). The sibling non-FSM implementation of this same epic-merge-completion feature (FEAT-2449, `done`) intentionally excludes `cancelled` from its done-count, with an explicit code comment ("a cancelled child must NOT trigger a merge into base") and a passing regression test (`test_orchestrator.py::test_cancelled_child_does_not_trigger_merge`). `merge_epic_branch`'s current shape matches that intentional design, not a stray duplicate bug. Applying Option A to `merge_epic_branch` alone would make the FSM-loop and `ll-parallel` orchestrator paths behave differently for the identical epic-completion scenario — the same epic could auto-merge via one runner and stay held open via the other.

> **Selected:** Option B — both gates change together, keeping `merge_epic_branch` and `_maybe_complete_epic` consistent with each other; see Decision Rationale below.

**Recommended**: Undetermined from the code alone — resolving this requires deciding whether FEAT-2449's "cancelled must not trigger merge" design is still intended policy, or should be revisited given how common post-refinement cancellation has turned out to be (per this issue's own Motivation). Whichever way it resolves, `merge_epic_branch` and `_maybe_complete_epic` should end up consistent with each other.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-31.

**Selected**: Option B — change `merge_epic_branch` and `ParallelOrchestrator._maybe_complete_epic` together (not `merge_epic_branch` alone).

**Reasoning**: The two gates are documented as an intentionally mirrored pair — `auto-refine-and-implement.yaml`'s own header comment self-describes `merge_epic_branch` as "the FSM-loop-side equivalent of `ParallelOrchestrator._maybe_complete_epic`," and both compute a byte-identical `done_count == total and cancelled_count == 0` predicate. Fixing `merge_epic_branch` alone would leave that mirroring broken: the identical epic-completion scenario (one `done` child, one `cancelled` child) would auto-merge via the FSM-loop runner but stay held open via `ll-parallel` — a silent, undocumented cross-runner divergence, per both evidence agents' findings. Options tied on raw total (8/12 each); Consistency was the deciding dimension (Option B 3/3 vs. Option A 1/3), per the scoring rubric's explicit tiebreak rule.

Note: this does not fully resolve the issue's own "Recommended: Undetermined" note — whether `cancelled` should count as done for merge purposes at all remains a product/policy call (FEAT-2449's design record states the exclusion as a semantic conclusion, not a safety rationale, and doesn't address the operational frequency this issue raises). What codebase evidence *does* settle is that whichever way that policy resolves, both call sites must change together, not one in isolation.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (fix `merge_epic_branch` alone) | 1/3 | 3/3 | 3/3 | 1/3 | 8/12 |
| Option B (fix both gates together) | 3/3 | 1/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**: The rejected single-file change reuses `compute_epic_progress()`/`by_status` directly and has zero existing FSM-side test coverage of the cancelled case, so it would have been a purely additive one-line change (`auto-refine-and-implement.yaml:707-713`) — but it contradicts the state's own header comment framing it as `_maybe_complete_epic`'s mirror, and leaves `test_orchestrator.py::test_cancelled_child_does_not_trigger_merge` (`:1633-1643`) green while the FSM path would behave oppositely for the same scenario. The selected both-gates change preserves the documented mirroring between `merge_epic_branch` and `_maybe_complete_epic` (`orchestrator.py:1472-1479`), but requires rewriting that existing regression test and auditing ~15 sibling gate tests in `test_orchestrator.py` (lines 1598-1952) for interaction effects, since `_maybe_complete_epic` has a live production call site (`orchestrator.py:1287`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `merge_epic_branch` state's `all_done` condition (roughly lines 610-716)

### Dependent Files (Callers/Importers)
- Any FSM loop that reuses the same `merge_epic_branch` completion-gate pattern (grep for `done_count == total` and `cancelled_count == 0` in `scripts/little_loops/loops/*.yaml`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/worktree_utils.py:613` (`merge_epic_branch_to_base()`) — the shared git-merge helper (extracted under BUG-2614) that both `merge_epic_branch` and `_maybe_complete_epic` invoke once their respective `all_done` gates pass. Not modified by this fix, but confirmed as the common downstream consumer of both gates' verdicts.
- Confirmed no third production site shares this gate's `done_count == total ... cancelled_count == 0` shape: repo-wide grep for `cancelled_count`/`done_count` found only `orchestrator.py:1478-1479` and `auto-refine-and-implement.yaml:710-712`, plus a deliberately different display-only computation in `scripts/little_loops/cli/issues/epic_progress.py:73-76` (`done_count = done_only + cancelled_count` for the progress-bar badge) that is unrelated to the merge gate and needs no change.

### Similar Patterns
- Dependency-edge resolution already treats `done`/`cancelled` as the two terminal statuses (`.claude/CLAUDE.md` § Issue File Format) — this fix brings the completion gate in line with that existing convention

### Tests
- `scripts/tests/test_builtin_loops.py` (or the FSM/loop test module covering `merge_epic_branch`) — add a case with a mix of `done` and `cancelled` children asserting `all_done` resolves true

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:1633-1643` (`test_cancelled_child_does_not_trigger_merge`) is the **only** test in `TestEpicCompletionMerge`/`TestEpicBranchVerifyGate` (lines 1564-1955, 16 tests audited) whose fixture includes a `cancelled` child status — confirmed the sole rewrite target; no other test in that range needs auditing for interaction effects. Model the rewrite on the sibling `test_merges_epic_branch_when_all_children_done` (`:1590-1606`), asserting a merge now fires for `{"FEAT-010": "done", "FEAT-020": "cancelled"}`.
- `scripts/tests/test_builtin_loops.py::TestMergeEpicBranchConfigReadShell` (class starts `:5861`) has zero existing `cancelled`-status coverage — add `test_merges_when_done_and_cancelled_mix`, modeled on `test_merges_when_all_children_done` (`:6002-6016`), asserting `epic-merge-verdict.txt` reads `"merged"`.
- `scripts/tests/test_orchestrator.py:1621-1631` (`test_blocked_child_holds_branch_open`) — confirmed unaffected (`{"FEAT-010": "done", "FEAT-020": "blocked"}`, no `cancelled` in its fixture); re-run only, no rewrite, to guard that `blocked_count == 0` stays strict.
- `scripts/tests/test_issue_progress.py` — the `issue_progress` module's own primary test file for `compute_epic_progress`/`EpicProgress`; not previously listed as known coverage.
- `scripts/tests/test_worktree_utils.py:612-765` (`TestMergeEpicBranchToBase`) — exercises the shared merge helper both gates call; unaffected by the condition change but worth re-running.
- No existing three-way `done`+`cancelled`+`blocked` fixture exists in either test file (confirmed via targeted search) — not required by the issue's Implementation Steps, but worth adding if defense-in-depth coverage is wanted for the `blocked_count == 0` term staying independent of the `cancelled` fold-in.

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/features/P3-FEAT-2449-per-epic-integration-branch-completion-flow.md` (status `done`) — the design record whose stated intent ("a cancelled child must NOT trigger a merge into base") this fix knowingly reverses. No `relates_to` link exists in either direction today (confirmed: BUG-3369's frontmatter has no `relates_to` field; `.ll/decisions.yaml`/`.ll/decisions.d/` have zero `FEAT-2449` cross-reference fragments). No doc/CLI/config text elsewhere asserts the cancelled-exclusion as current fact, so this is the only stale-record touchpoint found.

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

1. Change the `all_done` condition from `done_count == total` to `(done_count + cancelled_count) == total` (keeping `blocked_count == 0` as-is) in **both** `merge_epic_branch` (`auto-refine-and-implement.yaml:707-713`) and `ParallelOrchestrator._maybe_complete_epic` (`orchestrator.py:1472-1479`) — per Option B, not `merge_epic_branch` alone.
2. Add a test covering an epic with a mix of `done` and `cancelled` children (and none `blocked`) asserting `all_done` resolves true and the branch reaches the `verify_before_merge` check, for the FSM side (`test_builtin_loops.py`). Rewrite `test_orchestrator.py::test_cancelled_child_does_not_trigger_merge` (`:1633-1643`) to assert a merge now fires for the same done+cancelled mix, since its current assertion locks in the opposite (pre-fix) behavior.
3. Verify existing tests for the fully-`done` and any-`blocked` cases still pass unchanged in both test modules, and audit the other epic-gate tests in `test_orchestrator.py` (lines ~1598-1952) for interaction effects.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/parallel/orchestrator.py:1417-1433` (`_maybe_complete_epic`'s docstring) and `:1473-1475` (inline comment) — both currently state the pre-fix "cancelled excluded" rationale as fact ("cancelled children do NOT count", "a cancelled child must NOT trigger a merge into base"); must be rewritten alongside the condition change, not left as stale rationale text.
- Rewrite `scripts/tests/test_orchestrator.py::test_cancelled_child_does_not_trigger_merge` (`:1633-1643`) to assert a merge now fires for a done+cancelled mix — its current docstring/assertion locks in the pre-fix behavior.
- Add `test_merges_when_done_and_cancelled_mix` to `scripts/tests/test_builtin_loops.py::TestMergeEpicBranchConfigReadShell` (model: `test_merges_when_all_children_done`, `:6002-6016`).
- Add a cross-reference between this issue and `.issues/features/P3-FEAT-2449-per-epic-integration-branch-completion-flow.md`, whose design intent this fix reverses — no existing link exists in either direction.

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
- `/ll:wire-issue` - 2026-08-31T22:11:28 - `c4a9442e-319b-44f7-a243-d71188c2e525.jsonl`
- `/ll:decide-issue` - 2026-08-31T22:01:17 - `37ee9921-5737-4ac0-9e3a-27926a3278f3.jsonl`
- `/ll:refine-issue` - 2026-08-31T21:40:32 - `a39b473b-2472-40a4-90ee-2531e40475f9.jsonl`
- `/ll:format-issue` - 2026-08-31T21:28:22 - `24eb8111-3a52-4364-98e0-699548ae82fc.jsonl`
- `/ll:capture-issue` - 2026-08-31T21:19:35 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`

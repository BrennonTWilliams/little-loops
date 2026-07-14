---
id: BUG-2637
title: merge_epic_branch reads final-child status from base tree, so the completing
  run can never auto-merge
type: BUG
priority: P2
status: done
labels:
- loops
- fsm
- epic-branches
- merge-coordinator
discovered_date: '2026-07-14'
completed_at: '2026-07-14T17:15:56Z'
discovered_by: manual
relates_to:
- BUG-2614
- EPIC-2575
confidence_score: 95
outcome_confidence: 81
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
decision_needed: false
---

# BUG-2637: merge_epic_branch reads final-child status from the base tree, so the run that completes an EPIC can never auto-merge

## Summary

The `merge_epic_branch` state in
`scripts/little_loops/loops/auto-refine-and-implement.yaml` decides whether to
merge the epic branch back to base by computing epic progress from issue files
in the **current working tree (base branch)**. When the loop completes the
**final** child of an EPIC, that child's `status: done` was written and
committed **inside the epic-branch worktree** — it does not exist on the base
tree. So the all-children-done gate reads the final child as still `open`,
prints `held_open`, and the auto-merge never fires. No later run can fix it:
nothing brings the `done` status back to base while the merge is held, so the
EPIC deadlocks in `held_open` and requires a manual merge. This is a sibling of
BUG-2614 (which fixed the multi-run "committed but never merged" case) — the
final-child vantage-point gap was left open.

## Current Behavior

On the run that completes the last open child of an EPIC, `merge_epic_branch`
evaluates child status against the checked-out base tree, where the just-
completed child still reads `open`. `all_done` is `False`, verdict is
`held_open`, and the epic branch is left unmerged indefinitely.

Observed in run `auto-refine-and-implement-20260714T103349`
(`--context scope=EPIC-2575`): `summary.json` shows
`"epic_merge_verdict":"held_open"` even though ENH-2578 (the last child) was
verified `done` on the epic branch (commit `158f2181`).

## Expected Behavior

When the loop completes the final child and `merge_to_base_on_complete: true`
with a passing verify gate, the run should resolve `all_done == True` and merge
the epic branch to base (`epic_merge_verdict=merged`). A branch with a genuinely
still-open sibling child should still report `held_open`.

## Steps to Reproduce

1. Configure `parallel.epic_branches.merge_to_base_on_complete: true`.
2. Create an EPIC whose children are all `done` except one still-open child.
3. Run `ll-loop run auto-refine-and-implement --context scope=EPIC-<n>` so the
   loop completes that final child (writing `status: done` on the epic branch).
4. Observe: `summary.json` reports `"epic_merge_verdict":"held_open"` and the
   epic branch is not merged, despite all children being effectively done.
5. Confirm the split:
   `git show <epic-branch>:<child-path> | grep status` → `done`, but
   `grep status <child-path>` (base tree) → `open`.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- **Anchor**: `merge_epic_branch` state (~lines 525–546)
- **Cause**: The gate computes progress from the base working tree:
  ```python
  all_issues = find_issues(cfg, status_filter={...})   # reads base tree
  prog = compute_epic_progress(epic_id, all_issues)
  all_done = (total > 0 and done_count == total and blocked_count == 0 and cancelled_count == 0)
  if not all_done:
      print("held_open"); raise SystemExit(0)
  ```
  `find_issues` reads the checked-out (base) tree, but the completing child's
  `done` status lives only on the epic-branch tip — so the deciding status is
  invisible to the very gate that needs it.

## Proposed Solution

Evaluate child status against the **epic branch tip** (where completions land)
rather than the base working tree:

1. Read each child's frontmatter via `git show <epic-branch>:<issue-path>`
   before computing `all_done` (lowest-risk, no worktree checkout).

> **Selected:** Option 1 (git-show/git-grep tip-read, replacing the base scan) — mirrors the `finalize` state's existing `git grep -lE '^status: *done' <branch>` tip-read idiom in the same file; simplest and most consistent.

2. Or union base-tree status with epic-branch-tip status (a child counts as
   `done` if done on either side) so already-merged siblings and the just-
   completed final child both count.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-14.

**Selected**: Option 1 — read child status from the epic-branch tip (via `git show <epic-branch>:<issue-path>` / `git grep -lE '^status: *done' <branch> -- .issues`), replacing the base-tree scan for the `all_done` gate.

**Reasoning**: The `finalize` state in the *same* `auto-refine-and-implement.yaml` already reads status from the epic-branch tip via `git ls-tree`/`git grep <branch>` with a disk fallback (ENH-2609, ~lines 653–703) — an if/else *substitution* between vantage points, exactly the shape Option 1 needs. `parse_frontmatter(content: str)` accepts a raw blob so `git show` stdout pipes straight in with no new YAML infra. Option 2's per-child union has **no existing primitive** (Agent 2 confirmed nothing in the codebase unions base⊕tip status), requires building `IssueInfo` objects from blobs (which `find_issues`/`parse_file` are `Path`-only and cannot do), and adds more surface for equal risk.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (git-show/git-grep tip-read, replace) | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Option 2 (union base ⊕ tip status) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Option 1: Mirrors the in-file `finalize` tip-read precedent (`auto-refine-and-implement.yaml:653–703`); `parse_frontmatter` already parses raw strings; `epic_branch` is already resolved in the same action body — no new plumbing. (reuse score: 1)
- Option 2: Additive/safer semantics, but no per-child union primitive exists; needs a new `git show` + status-override loop and `IssueInfo`-from-blob construction that `find_issues`/`parse_file` don't support. (reuse score: 1)

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the
  `merge_epic_branch` state's `action` body (verified ~lines 525–546). The
  `all_done` gate at `find_issues(...)` → `compute_epic_progress(...)` reads the
  checked-out base tree. Insert an epic-branch-tip status read (via
  `git show <epic_branch>:<issue-path>`) before computing `all_done`, unioning
  tip status over base status. `epic_branch` is already resolved earlier in the
  same action from `run_dir / "epic-branch-name.txt"` — reuse it (no new plumbing).

### Reuse Points (no change needed)
- `little_loops.issue_progress.compute_epic_progress` (`issue_progress.py:120`) —
  keep as the counting primitive; feed it issue records whose status has been
  overridden with the epic-branch-tip value. Signature is unchanged by this fix;
  only the `all_issues` it receives is post-processed. Confirmed no other consumer
  (`cli/issues/epic_progress.py`, `sprint.py`, `cli/issues/list_cmd.py`) is
  affected — they read the base/post-merge tree by design.
- `little_loops.issue_parser.find_issues` — still the base-tree enumerator that
  yields the child set + paths to `git show` against the tip. No branch parameter
  exists; the tip-status override happens inside the YAML heredoc, not in this fn.
- BUG-2614 already established the `run_dir / "base-branch-name.txt"` +
  `epic-branch-name.txt` convention and `git show <branch>:<path>` reads
  elsewhere in this file — follow that idiom.

_Wiring pass added by `/ll:wire-issue`:_
- **Style precedent — the `finalize` state already reads status from the tip.**
  In the *same* `auto-refine-and-implement.yaml`, the `finalize` state (ENH-2609,
  ~lines 581–619) already resolves child status against the epic-branch tip, not
  the base tree: `git ls-tree -r --name-only "$EPIC_BRANCH" -- .issues/completed/`
  (~line 591) and a `git grep -lE '^status: *done' <branch> -- .issues` inside its
  embedded Python heredoc (~line 616). Mirror this idiom in `merge_epic_branch`
  rather than inventing a new one — it is the closest in-file precedent for the
  tip-status read the fix needs. [Agent 3 finding]
- **Corrected anchors (issue text is slightly stale):** the buggy gate is at
  `auto-refine-and-implement.yaml:486–493` (the `find_issues(...)` →
  `compute_epic_progress(...)` block inside `merge_epic_branch.action`), and the
  test class is `test_builtin_loops.py:2772` — verify against these before
  editing. [Agent 1 + Agent 3 findings]

### Tests (regression home)
- `scripts/tests/test_builtin_loops.py` → class
  `TestMergeEpicBranchConfigReadShell` (line 2937). This class extracts the
  state's raw `action`, substitutes FSM placeholders, and runs it via `bash -c`
  against a real git repo — the exact harness the AC-2 regression test needs.
- Key helper `_write_issues()` (~line 2960) currently writes every child's
  status to the **base tree** only. The new test must instead commit the
  completing child's `status: done` onto `self._EPIC_BRANCH` tip (mirroring how
  `_setup_repo()` commits `feature.txt` on the epic branch) while the base tree
  still reads `open`, then assert `epic-merge-verdict.txt == "merged"`.
- Guard tests to keep green: `test_merges_when_all_children_done`,
  `test_held_open_when_child_not_done` (must still hold for a genuinely-open
  sibling — AC-3).

_Wiring pass added by `/ll:wire-issue`:_
- **Fuller guard-test list.** `TestMergeEpicBranchConfigReadShell` has **8** tests
  that must all stay green, not just the 2 named above. The others:
  `test_skipped_when_merge_to_base_on_complete_false`,
  `test_skipped_when_no_epic_branch_file`,
  `test_idempotent_when_branch_already_merged` (the BUG-2614 idempotency
  regression), plus three ENH-2630 verify-verdict-reuse tests that also exercise
  this same state's action and must not regress:
  `test_reuses_fresh_verify_verdict_and_skips_rerun`,
  `test_reruns_when_verify_sha_is_stale`, and
  `test_reruns_when_verify_verdict_missing`. Run the whole class after the fix.
  [Agent 1 + Agent 3 findings]
- **Reusable class helpers (no new fixtures needed).** `_setup_repo` (~line 2780)
  already does the `git init -b main` → create `self._EPIC_BRANCH` → commit
  `feature.txt` on it → checkout `main` dance; `_run` (~line 2810) extracts the
  state `action`, substitutes `${context.scope}`/`${context.run_dir}`, and runs
  it via `bash -c`. The new BUG-2637 test should extend this class: commit the
  completing child's `status: done` **onto `self._EPIC_BRANCH`** (base tree still
  reads `open`), then assert `epic-merge-verdict.txt == "merged"` and the branch
  is deleted from `git branch --list`. No `git show <branch>:<path>` content-read
  test pattern exists elsewhere in `scripts/tests/` — this will be a new pattern,
  but composes directly from `_setup_repo`. [Agent 3 finding]

### Out of Scope (advisory)

_Wiring pass added by `/ll:wire-issue`:_
- **Possible sibling bug in the orchestrator path (do NOT fix here).** The
  `ll-parallel` orchestrator has its own, *separate* epic-completion path —
  `parallel/orchestrator.py::_maybe_complete_epic` (~lines 1227–1351) →
  `_merge_epic_branch_to_base` (~lines 1352–1360) →
  `worktree_utils.merge_epic_branch_to_base` (~line 327) — that also calls
  `compute_epic_progress` over a base-tree issue scan. It may share the same
  vantage-point gap, but it is a distinct code path from the FSM YAML state this
  bug targets. Keep this fix FSM-scoped; if the orchestrator path is confirmed to
  have the same defect, file a separate issue rather than widening BUG-2637.
  Its regression home is `scripts/tests/test_orchestrator.py`
  (`test_merges_epic_branch_when_all_children_done`,
  `test_no_merge_when_epic_branches_disabled`, ~lines 1357+) — do NOT touch it
  here; noted only so a future sibling-bug issue knows where its coverage lives.
  [Agent 1 finding]
- **Free-function siblings share `merge_epic_branch`'s call sequence but need no
  change.** The state's action also calls `verify_epic_branch_before_merge`,
  `merge_epic_branch_to_base`, and `open_pr_for_epic_branch` from
  `worktree_utils.py` (unit-tested in `scripts/tests/test_worktree_utils.py`).
  The fix only alters the `all_issues` fed into `compute_epic_progress` upstream
  of these calls — their signatures and behavior are untouched, so
  `test_worktree_utils.py` needs no update. [Agent 1 finding]
- **Documentation needs no change.** `config-schema.json` (the
  `merge_to_base_on_complete` description, ~line 412), `docs/guides/LOOPS_REFERENCE.md`
  (the `merge_epic_branch` flow note, ~lines 932–949), and
  `docs/development/MERGE-COORDINATOR.md` all describe the *intended* "merge once
  all children are done" behavior — which is what this fix restores. No doc text
  is currently wrong, so none is required to change. [Agent 2 finding]

## Impact

- **Priority**: P2 — silently strands verified epic work on an unmerged branch;
  every single-remaining-child EPIC hits it, and it masquerades as a clean
  `success` verdict.
- **Effort**: Small — localized to one FSM state's status computation; reuses
  `git show` + existing `compute_epic_progress`.
- **Risk**: Medium — merge-gate logic; must not introduce false merges when a
  sibling is genuinely open. Covered by the AC regression tests.
- **Breaking Change**: No.

## Acceptance Criteria

- [x] A single `auto-refine-and-implement --context scope=EPIC-<n>` run that
      completes the final child produces `epic_merge_verdict=merged` (not
      `held_open`), given `merge_to_base_on_complete: true` and a passing verify.
- [x] Regression test (`scripts/tests/test_builtin_loops.py` or merge-coordinator
      test) simulating a final child whose `done` status exists only on the epic
      branch, asserting `all_done == True`.
- [x] A branch with a genuinely-open sibling child still reports `held_open`.
- [x] `python -m pytest scripts/tests/` green.

## Notes

Discovered while manually reconciling EPIC-2575. Separately, that epic branch had
gone **stale** (base advanced 17 commits and independently re-implemented the
codequery providers), so its only unique content was the wire-issue Phase 3.6
delta (`158f2181`). The merge coordinator arguably should also surface staleness,
but that is out of scope here.

## Resolution

**Fixed** — 2026-07-14. Implemented Option 1 (epic-branch-tip status read).

In `merge_epic_branch`'s action (`auto-refine-and-implement.yaml`), after
`find_issues()` scans the base tree, a `git grep -lE '^status: *done'
<epic_branch> -- .issues` reads the set of children marked `done` on the epic
branch tip and unions that over each `IssueInfo.status` before
`compute_epic_progress` counts them. The completing final child — whose `done`
status was committed only inside the epic-branch worktree — now counts toward
`all_done`, so the run that finishes an EPIC auto-merges instead of dead-locking
in `held_open`. Mirrors the `finalize` state's existing tip-read idiom (ENH-2609)
in the same file; `compute_epic_progress` and the `worktree_utils` merge helpers
are unchanged.

Regression coverage added to `TestMergeEpicBranchConfigReadShell` in
`scripts/tests/test_builtin_loops.py`:
`test_merges_when_final_child_done_only_on_branch_tip` (final child `done` only
on the tip → `merged`) and `test_held_open_when_sibling_open_on_both_base_and_tip`
(genuinely-open sibling → still `held_open`). The `_run` helper gained a
`branch_statuses` hook that commits a divergent status tree onto the epic branch
tip. Full suite green (14915 passed, 36 skipped).

## Status

**Done** | Created: 2026-07-14 | Completed: 2026-07-14 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-07-14T17:00:33 - `eeaa0ec6-e5d7-4847-acae-30f8cd9a9572.jsonl`
- `/ll:confidence-check` - 2026-07-14T00:00:00 - `95cfa7e3-adb7-4c79-9b1f-7d6df28de748.jsonl`
- `/ll:wire-issue` - 2026-07-14T16:57:48 - `445ecbda-8a65-49b5-bfef-52483642d613.jsonl`
- `/ll:decide-issue` - 2026-07-14T16:53:26 - `6d63838c-2c72-46dd-98ad-d531150e2119.jsonl`
- `/ll:wire-issue` - 2026-07-14T16:29:37 - `14e6c704-1828-445b-9e28-faa64c757395.jsonl`
- `/ll:refine-issue` - 2026-07-14T16:22:20 - `f0c466dd-f07b-4901-b0d6-36e20bba511a.jsonl`
- `/ll:manage-issue` - 2026-07-14T17:15:05 - `a9325ce6-6adc-4b61-94ff-f0397e3f3ba3.jsonl`

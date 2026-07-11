---
id: ENH-2603
type: enhancement
status: open
priority: P3
parent: ENH-2600
relates_to:
- ENH-2601
- ENH-2602
---

# ENH-2603: Run test/lint gate before epic-branch merge-to-base and surface failures

## Summary

Before `_maybe_complete_epic()` (`scripts/little_loops/parallel/orchestrator.py:1208-1295`)
merges an EPIC-branch to `base_branch` or opens a PR, check out the epic
branch tip in a scratch worktree, run `project.test_cmd` (and
`project.lint_cmd` if configured) against it, and block the merge/PR-open on
failure — surfacing the block as a structured, resumable failure record
rather than a `logger.warning`-only side effect. Gated by
`epic_branches.verify_before_merge` (added in [[ENH-2602]]).

## Parent Issue

Decomposed from ENH-2600: Verify epic-branch tests/lint before merge-to-base
or PR-open

## Current Behavior

EPIC-branch completion (`epic_branches.merge_to_base_on_complete: true`, the
default) merges/opens-PR based solely on `_maybe_complete_epic`'s
changed-files-adjacent checks (config flags enabled, all children `done`, no
unresolved failures, not already merged this run) — no test/lint command runs
anywhere in this path. Neither `_merge_epic_branch_to_base()`
(`orchestrator.py:1297-1336`) nor `_open_pr_for_epic_branch()`
(`orchestrator.py:1338-1390`) write into `self._worker_errors` or
`state.failed_issues` on failure today; they only `logger.warning(...)`.

## Expected Behavior

When `epic_branches.verify_before_merge` is `True`, before the merge/PR-open
dispatch: run the project's configured `test_cmd` (and optionally
`lint_cmd`) against the epic branch tip. On failure, block the merge (or
PR-open), leave the epic branch as-is, and surface the failure in the run
summary / `_report_results()` output so it's visibly blocked and requires
manual attention rather than silently merged or silently logged.

## Proposed Solution

1. Add a helper `_verify_epic_branch_before_merge(epic_id, epic_branch) ->
   bool`, modeled on `_run_per_worktree_proof_first_gate()`
   (`worker_pool.py:63-132`): config short-circuit (`return True` if
   `verify_before_merge` is `False`) → checkout the epic branch tip in a
   scratch worktree → run `project.test_cmd`/`project.lint_cmd` with
   `cwd=<worktree_path>` via `GitLock`-adjacent subprocess conventions →
   always `cleanup_worktree(...)` regardless of outcome → return bool.
2. Insert the call in `_maybe_complete_epic` between the idempotency gate
   (line 1287-1290) and the merge/PR dispatch (line 1292-1295) — verify once
   per branch, matching the existing `self._merged_epic_branches` dedup.
3. On failure, `return` before the merge/PR dispatch and populate a
   structured failure record that `_report_results()`
   (`orchestrator.py:1463-1553`) actually surfaces. `self._worker_errors[epic_id]`
   alone is not sufficient — `_report_results()` only reports failures
   present in `self.queue.failed_ids` (~1496-1500) and there's no existing
   epic-branch-keyed reporting block; either add `epic_id` to
   `queue.failed_ids` or add a new dedicated report block modeled on the
   existing `stash_warnings` pattern (`self.merge_coordinator.stash_pop_failures`,
   ~1564-1575).

### Checkout mechanism

`setup_worktree()` (`worktree_utils.py:63-159`) always creates a *new*
branch (`git worktree add -b <new-branch> <path> [<base_branch>]`) — no
existing call site checks out an *already-existing* branch in place. This
gate needs either a bare `git worktree add <path> <epic_branch>` (no `-b`)
or `base_branch=epic_branch` with a disposable branch name, then
`cleanup_worktree()` to tear it down. `test_worktree_utils.py` currently
covers only `detect_default_branch()`, so the new tests here are original
rather than adapted from a working example.

## Implementation Steps

1. Implement `_verify_epic_branch_before_merge()` in
   `scripts/little_loops/parallel/orchestrator.py`.
2. Add the checkout-existing-branch mechanism (new `setup_worktree`
   parameter or a bare `git worktree add <path> <existing-branch>` call).
3. Wire the call into `_maybe_complete_epic` between the idempotency gate
   and the merge/PR dispatch.
4. Populate a structured failure record that `_report_results()` surfaces
   (either via `queue.failed_ids` or a new dedicated report block).
5. Update `docs/development/MERGE-COORDINATOR.md` (epic completion path,
   lines 149-158), `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`,
   and `docs/ARCHITECTURE.md` (~463-470) to document the new gate.

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — `_maybe_complete_epic`
  (1208-1295), `_merge_epic_branch_to_base` (1297-1336),
  `_open_pr_for_epic_branch` (1338-1390)
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` (63-159),
  `cleanup_worktree()` (161-201)

### Reusable Utilities

- `scripts/little_loops/worktree_utils.py` — `setup_worktree()`,
  `cleanup_worktree()`
- `scripts/little_loops/parallel/git_lock.py` — `GitLock.run(...)`, the
  thread-safe subprocess wrapper already used by
  `_merge_epic_branch_to_base`; any new git operation (e.g. `rev-parse` to
  resolve the epic branch tip) should go through this, not bare
  `subprocess.run`

### Tests

- `scripts/tests/test_orchestrator.py` — `TestEpicCompletionMerge` class
  (~1329-1527) and its `make_epic_orchestrator` fixture (~149-230): add
  cases for the verify-gate blocking a merge on a failing `test_cmd`, and
  for idempotent-single-verify-per-branch behavior (existing
  `test_idempotent_across_calls` pattern, ~1505-1517). Extend
  `make_epic_orchestrator`'s kwargs with `verify_before_merge`/`test_cmd`/
  `lint_cmd`. Note `test_opens_pr_when_open_pr_true` (~1465) already patches
  `little_loops.parallel.orchestrator.subprocess.run` with a `gh`-only fake
  returning `returncode=1` for anything else — the new verify-gate
  subprocess call goes through the same patch target, so account for the
  collision.
- `scripts/tests/test_worker_pool.py` (~3170-3409) —
  `TestPerWorktreeProofFirstGate`: model new verify-gate unit tests after
  this class's conventions, patching `subprocess.run` at
  `little_loops.parallel.orchestrator.subprocess.run` (this gate lives in
  `orchestrator.py`, not `worker_pool.py`), asserting on `call_args[0][0]`
  for the constructed command and the boolean gate return value.
- `scripts/tests/test_worktree_utils.py` — write new tests for whichever
  checkout-existing-branch mechanism is chosen; no existing precedent to
  extend.

### Documentation

- `docs/development/MERGE-COORDINATOR.md` (epic completion path,
  lines 149-158)
- `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`
- `docs/ARCHITECTURE.md` (~463-470) — prose describing epic-branch
  completion flow should mention the new verify gate.

## Impact

- **Priority**: P3 — real correctness gap in a mechanism designed to be the
  trusted integration surface for EPIC work.
- **Effort**: Medium — new worktree-checkout mechanism with no existing
  precedent, plus failure-surfacing wiring through `_report_results()`.
- **Risk**: Low — additive gate behind [[ENH-2602]]'s default-`False` flag;
  failure mode is block-don't-auto-fix.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/development/MERGE-COORDINATOR.md | Epic completion / merge-to-base flow this gate slots into |
| docs/guides/SPRINT_GUIDE.md | Per-EPIC integration branch user-facing docs |

## Session Log
- `/ll:issue-size-review` - 2026-07-11 - `2385c5ce-bdf9-4918-95d8-8118da444ec1.jsonl`

---

## Status

- [ ] Not started

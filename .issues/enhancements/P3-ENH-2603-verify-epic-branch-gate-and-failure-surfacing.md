---
id: ENH-2603
type: enhancement
status: open
priority: P3
parent: ENH-2600
relates_to:
- ENH-2601
- ENH-2602
confidence_score: 100
outcome_confidence: 79
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
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

   > ⚠ Codebase research findings below (see `### Codebase Research
   > Findings` under Implementation Steps) identify the *correct* insertion
   > point as **before** line 1287, not between 1287-1290 and 1292-1295 —
   > verify carefully before implementing.
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add a `verify_before_merge` kwarg to the `make_epic_orchestrator` fixture
   factory (`test_orchestrator.py:164-170`) and thread it into the
   `EpicBranchesConfig(...)` construction (~209-213).
7. Update `TestEpicCompletionMerge._capture_git`'s stub
   (`test_orchestrator.py:1339-1353`) to return a differentiated `stdout` for
   `rev-parse` calls (currently blank for every git subcommand).
8. Re-verify `test_idempotent_across_calls` (~1505-1517) against the
   corrected verify-gate insertion point; add `subprocess.run` patching to
   any `TestEpicCompletionMerge` test that reaches the new verify step if it
   shells out via `subprocess.run`.
9. Update `docs/reference/CONFIGURATION.md` (~368) and `docs/reference/API.md`
   (`EpicBranchesConfig`, ~3310) to remove the "inert until ENH-2603"
   language, and add a sentence to `docs/reference/CLI.md`'s "Config tip
   (epic branches)" block (~381) describing the new gate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Precise insertion point (corrects step 3 above)**: `_maybe_complete_epic`
  (`orchestrator.py:1208-1295`) runs, in order: config short-circuit (1230-1231)
  → epic-ancestor resolve (1237-1258) → all-children-done check (1264-1273) →
  partial-failure gate (1275-1285, `return`s on unresolved child failures,
  **no state mutation**) → idempotency gate (1287-1290, unconditionally
  `self._merged_epic_branches.add(epic_branch)`) → dispatch (1292-1295). The
  verify-gate call must go **between line 1285's `return` and line 1287's
  `if epic_branch in self._merged_epic_branches` check** — i.e. *before* the
  idempotency-set add, not after it as originally scoped. Inserting after the
  add (the issue's original plan) would permanently silence retries: neither
  `_merge_epic_branch_to_base` nor `_open_pr_for_epic_branch` ever clear
  `_merged_epic_branches` on failure today, so a verify failure recorded
  after the add would never get another chance to verify in the same run.
- **`epic_branches.verify_before_merge` is already fully plumbed and inert**
  (confirms ENH-2602 landed): `EpicBranchesConfig.verify_before_merge: bool
  = False` (`parallel/types.py:311-338`, docstring explicitly says "inert
  until ENH-2603 reads it"), `config/automation.py:52,62`,
  `config/core.py:534,610`, `config-schema.json:436`. No orchestrator code
  path reads it yet. Follow the existing sibling-flag read convention at
  `orchestrator.py:1227`: `cfg = self.parallel_config.epic_branches` once at
  the top of the method, then plain attribute access — `if
  cfg.verify_before_merge: ...` off that same local.
- **`_run_per_worktree_proof_first_gate` (worker_pool.py:63-132) is a
  partial model only** — it does NOT provision a worktree itself; it
  receives an already-set-up `worktree_path` from its caller
  (`_process_issue`, which already ran `setup_worktree()` for that issue's
  own branch earlier in the pipeline). It also uses plain `subprocess.run(cmd,
  capture_output=True, text=True, cwd=worktree_path)` (not
  `self._git_lock.run`, since the command isn't git), passes no `timeout`,
  and performs no cleanup itself (worktree teardown happens later in the
  caller's lifecycle). ENH-2603's helper needs to both provision *and* tear
  down its own scratch worktree, since there's no existing per-issue
  worktree tied to the EPIC branch.
- **`project.test_cmd`/`project.lint_cmd` access path**: confirmed
  `self.br_config` is available on `ParallelOrchestrator`
  (`orchestrator.py:98`, `self.br_config = br_config`, already used at
  1245, 1407, 1643, 1679). Read as `self.br_config.project.test_cmd` /
  `self.br_config.project.lint_cmd` (`ProjectConfig` at
  `config/core.py:136-164`, defaults `"pytest"` / `"ruff check ."`). No
  existing orchestrator/worker_pool call site reads these fields directly
  today — `_run_per_worktree_proof_first_gate` invokes `ll-loop run
  proof-first-task` instead of `test_cmd`, so this will be the first direct
  read of `project.test_cmd`/`lint_cmd` at this layer.
- **Failure-surfacing channel choice**: research supports the `stash_pop_failures`
  pattern (`merge_coordinator.py:73,265-271,1117-1126`) over `queue.failed_ids`
  as the better analog. `queue.failed_ids` is a per-*issue*-ID set consumed
  by `PriorityQueue.mark_failed()` and is *also* read back into this same
  method's partial-failure gate (`orchestrator.py:1279`,
  `epic_child_ids & (set(self.queue.failed_ids) | set(self.state.failed_issues))`)
  — folding an epic-branch-level verify failure into it would make the EPIC
  ID collide with that child-ID set-intersection logic. `stash_pop_failures`
  is a clean structural precedent instead: a private `dict[str, str]`
  (`_stash_pop_failures`, keyed by ID → free-text message), a read-only
  `@property` mirror on the orchestrator, and its own titled block in
  `_report_results()` (`orchestrator.py:1564-1575`) alongside — but
  independent of — the existing `failed_ids` block (1496-1500).
- **Test-patch collision detail confirmed**: `test_opens_pr_when_open_pr_true`
  (`test_orchestrator.py:1465-1503`) patches
  `little_loops.parallel.orchestrator.subprocess.run` with a `fake_run` that
  special-cases `gh auth`/`gh pr` and returns `returncode=1` for anything
  else — any new verify-gate subprocess call in this test must either be
  patched separately or added as another branch in that `fake_run`.
  `TestEpicCompletionMerge._capture_git` (`test_orchestrator.py`, static
  helper) shows the alternate pattern for git-only calls: monkeypatch
  `orch._git_lock.run` directly with a closure appending to a `calls: list`.

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — `_maybe_complete_epic`
  (1208-1295), `_merge_epic_branch_to_base` (1297-1336),
  `_open_pr_for_epic_branch` (1338-1390)
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` (63-159),
  `cleanup_worktree()` (161-201)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._setup_worktree()`
  (684-709) is the sole wrapper around `worktree_utils.setup_worktree()`,
  called once (~379). If the new checkout-existing-branch mechanism is added
  as a new keyword parameter on `setup_worktree()`, this wrapper does not
  need edits (default-safe) *unless* the verify-gate helper is routed through
  it rather than calling `worktree_utils.setup_worktree()` directly from
  `orchestrator.py` — decide the call path before implementing.
- `scripts/little_loops/cli/loop/run.py` (~441) — second production call
  site of `setup_worktree()` (FSM loop worktree-mode execution). Confirmed
  source-compatible with a new keyword-only parameter; no edit forced, but
  flagged so a future signature change doesn't silently break it unnoticed.

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

_Wiring pass added by `/ll:wire-issue`:_
- `make_epic_orchestrator` fixture factory (`test_orchestrator.py:164-170`,
  signature `(child_statuses, *, enabled=True, merge_to_base=True,
  open_pr=False)`) has **no `verify_before_merge` parameter** — add one and
  thread it into the `EpicBranchesConfig(...)` construction (~209-213) so new
  gate-specific tests can configure it. Existing `TestEpicCompletionMerge`
  tests that don't pass this kwarg are unaffected (dataclass default is
  `False`).
- `TestEpicCompletionMerge._capture_git` stub (`test_orchestrator.py:1339-1353`)
  always returns `returncode=0`/blank `stdout` regardless of git subcommand.
  The new `rev-parse` call to resolve the epic branch tip will need a
  differentiated stub (dict-keyed `side_effect` on `args[0]`, or per-call
  branching) to supply a realistic SHA — no existing test exercises consuming
  `rev-parse` stdout downstream.
- `test_idempotent_across_calls` (`test_orchestrator.py:1505-1517`) is a
  likely-break candidate: it depends on `_merged_epic_branches` being added
  to on the first `_maybe_complete_epic` call. Verify this test's semantics
  once the verify-gate is inserted at the corrected insertion point (before
  the idempotency-set add per the Codebase Research Findings above) — a
  verify failure should leave the branch retryable, not permanently marked
  merged.
- All `TestEpicCompletionMerge` tests except `test_opens_pr_when_open_pr_true`
  (~1465) currently do **not** patch `subprocess.run` — if the verify-gate's
  `test_cmd`/`lint_cmd` execution shells out via `subprocess.run` (not
  `self._git_lock.run`), every other test in the class needs that patch added
  or it will attempt a real subprocess call.
- New `_report_results()` tests for the failure-surfacing block should be
  modeled on `test_report_results_feature_branch_local_only`/`_pushed`/
  `_pr_opened` (`test_orchestrator.py:2637-2697`, which assert specific
  `mock_logger.info` call-arg substrings) rather than the looser
  `test_report_results_outputs_summary`/`test_report_results_calculates_speedup`
  (`TestReportResults`, ~3216-3260, which only assert `.called`). No existing
  test asserts on the `stash_pop_failures`-block's rendered content in
  `_report_results` — this shape is the closest analog for the new dict.
- `scripts/tests/test_merge_coordinator.py` — `test_tracks_stash_pop_failure`,
  `test_stash_pop_failures_property_is_thread_safe`,
  `test_no_tracking_without_current_issue_id` (~541-616) are the structural
  precedent for unit-testing a new structured-failure property (thread
  safety, defensive-copy return) if the new failure channel follows the
  `stash_pop_failures` pattern as recommended above.

### Documentation

- `docs/development/MERGE-COORDINATOR.md` (epic completion path,
  lines 149-158)
- `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`
- `docs/ARCHITECTURE.md` (~463-470) — prose describing epic-branch
  completion flow should mention the new verify gate.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` (~368) — the `epic_branches.verify_before_merge`
  row currently reads "Config plumbing only — no behavior yet; the actual
  verify gate lands in ENH-2603." Update once this issue lands.
- `docs/reference/API.md` (`EpicBranchesConfig` dataclass section, ~3310) —
  field comment `# ... inert until ENH-2603` needs updating to describe
  actual behavior.
- `docs/reference/CLI.md` (~381, "Config tip (epic branches)" prose block) —
  currently describes `merge_to_base_on_complete`/`open_pr` only; add a
  sentence about the new pre-merge verify gate so users discover it in the
  same place they learn about epic-branch completion.

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
- `/ll:ready-issue` - 2026-07-11T15:28:27 - `8b5d1710-736b-4893-91d3-68a6de917d42.jsonl`
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `9f42b1ff-96aa-4d2d-93f2-f2080ae556a4.jsonl`
- `/ll:wire-issue` - 2026-07-11T15:24:01 - `fe6c7bbd-c486-4fcd-9471-7f6c7355a636.jsonl`
- `/ll:refine-issue` - 2026-07-11T15:17:30 - `706d6654-db64-40df-b677-8a48bde3af79.jsonl`
- `/ll:issue-size-review` - 2026-07-11 - `2385c5ce-bdf9-4918-95d8-8118da444ec1.jsonl`

---

## Status

- [ ] Not started

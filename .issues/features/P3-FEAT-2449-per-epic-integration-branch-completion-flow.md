---
id: FEAT-2449
title: per-EPIC integration branch — EPIC-completion merge + orchestrator/sprint awareness
type: FEAT
priority: P3
status: open
captured_at: '2026-07-02T22:30:00Z'
discovered_date: 2026-07-02
discovered_by: issue-size-review
labels:
- parallel
- sprint
- epics
- git
- merge
- completion
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2450
blocked_by:
- FEAT-2448
decision_needed: false
confidence_score: 95
outcome_confidence: 55
score_complexity: 7
score_test_coverage: 18
score_ambiguity: 6
score_change_surface: 0
---

# FEAT-2449: per-EPIC integration branch — EPIC-completion merge + orchestrator/sprint awareness

## Summary

Third of four sequenced children decomposed from FEAT-2339. This child
implements **EPIC-completion detection** (when all children of an EPIC
reach `done`, merge the `epic/<EPIC-ID>-<slug>` integration branch
into `base_branch` or open one PR), and threads epic-branch awareness
through the remaining cross-module sites: orchestrator inspection,
sprint-runner in-place warning, and the partial-failure gate that
blocks the completion-merge when any child has failed.

Depends on FEAT-2448 (worker_pool + merge_coordinator wiring +
`WorkerResult.epic_branch` field).

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

1. **EPIC-completion detection** — in the orchestrator's
   post-merge flow, call
   `compute_epic_progress(epic_id, all_issues)` from
   `scripts/little_loops/issue_progress.py:83` (walks the `parent:`
   chain transitively per commit `4887c87c`). When
   `prog.done_count == prog.total_count` and there are no failed
   children (gate per Decision Rationale #2 — "Block until all
   children are done"), merge the epic branch to `base_branch` (or
   open one PR via `gh pr create --base base_branch --head epic/<id>`,
   analogous to the existing `orchestrator._open_pr_for_branch()`
   pattern). Then delete the epic branch (explicit deletion only —
   **not** via `_is_ll_branch()` or `_cleanup_worktree()`; see
   FEAT-2339 Decision Rationale #3).
2. **`_open_pr_for_branch()` epic-child PR target** — when a
   `WorkerResult.epic_branch` is set, the per-child PR created during
   normal merge flow lands on the epic branch
   (`--base epic/<id>` instead of `--base base_branch`). This
   completes the FEAT-2448 consumer-site change at
   `orchestrator.py:1142` to a fully-functional epic-child PR
   target.
3. **Orchestrator `_inspect_worktree()` epic-awareness**
   (`scripts/little_loops/parallel/orchestrator.py`) — the
   `rev-list --count base_branch..branch_name` call at line 415
   (drifted from ~400 per FEAT-2339 anchor corrections) must compare
   against the epic branch when the inspected worktree is an EPIC
   child. Update
   `test_cleanup_orphaned_worktrees` (line 509) and
   `test_inspect_worktree_with_feature_branch` (line 1001) for
   epic-prefix handling.
4. **`cli/sprint/run.py` in-place/contention-subwave warning**
   (lines 485, 518–528) — add a parallel `effective_epic_branches`
   check (identical shape to `effective_feature_branches`) and append
   to the existing warning message rather than replacing it,
   preserving the `"feature-branch mode does not apply"` substring
   that `scripts/tests/test_cli_sprint.py:TestFeatureBranchInPlaceWarning`
   asserts on (per FEAT-2339 Decision Rationale #4).
5. **Partial-failure gate** — completion-merge is blocked until
   **ALL** children reach `done`; a failed/blocked child holds the
   epic branch open (unmerged, undeleted). Reuse the existing
   `Orchestrator.run()` precedent for group-failure gating
   (`failed_count == 0` all-or-nothing cleanup gate at
   `orchestrator.py:827-831`). Cross-reference
   `state.failed_issues` / `queue.failed_ids` against the EPIC's
   child-ID set (computed via the depth-aware helper from FEAT-2447)
   — no existing structure already scopes these dicts by EPIC.
6. **Tests** —
   - `scripts/tests/test_sprint.py:TestSprintManagerLoadOrResolve`
     (~lines 2329–2540, "FEAT-1737") — add nested-EPIC test
     (grandchild with intermediate sub-EPIC parent) to cover the
     run-construction depth-mismatch (sprint.py still does direct-only
     `info.parent == epic_id` resolution — confirms and tests the
     known gap, independent of the branch-routing flatten-to-nearest
     decision).
   - `scripts/tests/test_cli_sprint.py:TestFeatureBranchInPlaceWarning`
     — add an `epic_branches` counterpart once the in-place warning
     is made epic-aware (must not break the existing
     `"feature-branch mode does not apply"` substring assertion).
   - `scripts/tests/test_orchestrator.py` — new tests for
     `_inspect_worktree` epic-branch comparison and
     `_open_pr_for_branch()` `--base epic/<id>` epic-child PR target.
   - `scripts/tests/test_worker_pool.py` —
     `test_inspect_worktree_with_feature_branch` (line 1001) audit
     and update for `epic/*` prefix handling.
   - Partial-failure gate: test that EPIC-completion-merge is
     blocked when any child is `failed` or `blocked`, not just when
     `done_count < total_count`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`compute_epic_progress()` predicate shape (CRITICAL — affects Step 1)**
- The function does NOT expose `done_count` / `total` as fields on
  `EpicProgress`. The actual predicate to use is:
  ```python
  prog = compute_epic_progress(epic_id, all_issues)
  if prog is not None:
      done_count = prog.by_status.get("done", 0)            # NOTE: not "cancelled"
      total = len(prog.children)
      blocked_count = prog.by_status.get("blocked", 0)
      cancelled_count = prog.by_status.get("cancelled", 0)
      all_done = (done_count == total
                  and blocked_count == 0
                  and cancelled_count == 0)
  ```
- `scripts/little_loops/issue_progress.py:14` defines
  `_TERMINAL_STATUSES = frozenset({"done", "cancelled"})` — the
  function's INTERNAL "done" computation (line 121) sums both. **The
  EPIC-completion-merge gate MUST check `by_status.get("done", 0)`
  alone, NOT the internal sum, to avoid triggering a merge when a
  child was cancelled.**
- Canonical completion-check precedent:
  `scripts/little_loops/cli/issues/list_cmd.py:236-241` — does
  `done = prog.by_status.get("done", 0) + prog.by_status.get("cancelled", 0)`.
  That consumer treats cancelled as terminal-done (correct for a
  progress badge); FEAT-2449 must explicitly diverge from this
  pattern because a cancelled child should NOT trigger an
  epic-branch merge into `base_branch`.

**`EpicProgress` dataclass shape** (`scripts/little_loops/issue_progress.py:17-48`)
- Fields: `epic_id`, `epic_title`, `children: list[IssueInfo]`,
  `by_status: dict[str, int]`, `percent_done: float`,
  `percent_blocked: float`, `oldest_open: IssueInfo | None`,
  `oldest_open_age_days: int | None`.
- `to_dict()` (lines 30-48) adds `"total"` (= `len(children)`).
- Transitive child walk via `_issue_descends_to()` (lines 67-80),
  cycle-guarded; `parent_map` built at line 106.

**`_is_ll_branch()` / `_cleanup_worktree()` — explicit deletion rationale**
- `_is_ll_branch()` at `scripts/little_loops/worktree_utils.py:213-223`
  only matches `parallel/*` and `^\d{8}-\d{6}-` branches. Explicitly
  rejects `HEAD`, `main`, `master`, empty strings.
  **Do NOT extend to `epic/*`** (FEAT-2339 Decision Rationale #3).
- `cleanup_worktree()` at `scripts/little_loops/worktree_utils.py:161-201`
  deletes whatever branch the worktree was on (no `_is_ll_branch`
  gate) — would silently delete an `epic/*` branch if a worker
  worktree happened to be checked out on it.
  **Do NOT route epic children through this.**
- `MergeCoordinator._cleanup_worktree()` at
  `scripts/little_loops/parallel/merge_coordinator.py:1061-1093`
  hardcodes `branch_name.startswith("parallel/")` (line 1088) — epic
  branches won't match this prefix, so deletion is silently skipped.
  Correct behavior by accident.

**Branch-deletion precedent (closest to FEAT-2449's completion-merge step)**
- `scripts/little_loops/parallel/orchestrator.py:557-561` —
  `_merge_pending_worktrees()` has an inline `branch -D` AFTER
  successful merge, gated only on `returncode == 0` (NO
  `_is_ll_branch` gate). This is the closest precedent for the
  EPIC branch deletion:
  ```python
  self._git_lock.run(
      ["branch", "-D", info.branch_name],
      cwd=self.repo_path,
      timeout=10,
  )
  ```
- Lift this shape for the EPIC-completion-merge branch-deletion,
  gated on `(a) merge succeeded AND (b) EPIC-completion detected
  (no failed/blocked children)`.

**`_inspect_worktree()` issue-ID parsing** (`orchestrator.py:410`)
- `re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", worktree_path.name)` —
  parses the issue ID from the worktree directory name. FEAT-2449
  needs to map this issue ID to its parent EPIC to pick the right
  comparison base.
- The `rev-list --count` call at line 415
  (`{self.parallel_config.base_branch}..{branch_name}`) must be
  replaced with
  `{epic_branch or base_branch}..{branch_name}` when the inspected
  worktree is an EPIC child.

**`_open_pr_for_branch()` PR creation pattern** (`orchestrator.py:1109-1160`)
- 3-tier graceful-degradation: `gh auth status` → `gh pr create
  --title ... --body "Closes {id}" --base <base> --draft --head
  <branch>` → catch `FileNotFoundError`/`TimeoutExpired`.
- `--base` hardcoded at line 1142 to
  `self.parallel_config.base_branch` — FEAT-2448 wires
  `result.epic_branch or self.config.base_branch` here, then
  FEAT-2449 completes the consumer-site change.
- For the EPIC-completion-merge PR (Step 1), the `--head` becomes
  `epic/<EPIC-ID>-<slug>` and `--base` becomes `base_branch`.

**Partial-failure gate cross-reference anchors**
- `self.queue.failed_count` at `orchestrator.py:716, 1249, 1252`.
- `self.queue.failed_ids` at `orchestrator.py:1269`.
- `self.state.failed_issues` at `orchestrator.py:622, 624`
  (`dict[str, str]` mapping `issue_id → failure_reason`,
  resumption-side).
- All three are flat across the entire run (no per-EPIC scoping).
  FEAT-2449's gate must intersect with the EPIC's child-ID set
  (computed via the depth-aware helper from FEAT-2447).

**Test patterns to model after**
- `TestFeatureBranchInPlaceWarning` at
  `scripts/tests/test_cli_sprint.py:732-879` — uses
  `mock_logger.warning.side_effect = lambda msg: warning_calls.append(msg)`
  capture pattern; asserts on the literal substring
  `"feature-branch mode does not apply"` (lines 841, 851, 861,
  870, 878). FEAT-2449's epic-counterpart test must mirror this
  shape while preserving the existing substring assertion.
- `test_on_worker_complete_feature_branch_open_pr` at
  `scripts/tests/test_orchestrator.py:2008-2052` — uses
  `args[0] == "gh" and args[1] == "pr"` discriminator; does NOT
  currently assert on `--base` value (FEAT-2448 adds this
  assertion; FEAT-2449 then tests the `epic/<id>` target via
  `args[args.index("--head") + 1]` containing `epic/`).
- `_make_issue` test helper at
  `scripts/tests/test_issue_progress.py:12-64` — canonical pattern
  for synthesizing `IssueInfo` with `parent` chains; reuse this
  in the nested-EPIC test for `TestSprintManagerLoadOrResolve`.

**`_find_epic_ancestor()` precedent**
(`scripts/little_loops/cli/issues/list_cmd.py:195-203`)
- Cycle-guarded walk up `parent_map` looking for `EPIC-*` prefix.
  This is the precedent shape for FEAT-2447's
  `_resolve_branch_targets()` resolver.
- **Known gap**: `scripts/little_loops/sprint.py:326` does
  direct-only `info.parent == epic_id` resolution (NOT transitive),
  creating a depth-mismatch between run-construction (direct) and
  `compute_epic_progress` (transitive). The nested-EPIC test in
  `TestSprintManagerLoadOrResolve` confirms and tests this gap
  independently of the branch-routing flatten-to-nearest decision.

**`_pr_ready_branches` dict** (`orchestrator.py:134`,
populated at `:1044-1045`)
- Currently tracks feature-branch state only. FEAT-2449 needs a
  parallel `_completed_epic_branches: dict[str, dict]` keyed by
  `epic_id` (or derive on-the-fly from `_issue_info_by_id` +
  `_pr_ready_branches`).

## Out of Scope (deferred to follow-on child)

- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs (ARCHITECTURE, API, CONFIGURATION, CLI, SPRINT_GUIDE), 9
  templates parity, prune_merged_feature_branches docstring — **FEAT-2450**.

## Acceptance Criteria

- [ ] When all children of an EPIC reach `done` (and no children are
      failed/blocked), the orchestrator triggers a merge of
      `epic/<EPIC-ID>-<slug>` into `base_branch` (or opens one PR
      per `epic_branches.open_pr` config).
- [ ] When any child is failed/blocked, the epic branch is held
      open (no merge, no delete) — verified by partial-failure gate
      test.
- [ ] Per-child PRs (in normal merge flow, not completion merge)
      target the epic branch (`--base epic/<id>`) when
      `WorkerResult.epic_branch` is set.
- [ ] `_inspect_worktree()` correctly compares against the epic
      branch for EPIC children.
- [ ] `cli/sprint/run.py` in-place warning fires an
      epic-branches-aware variant; existing
      `"feature-branch mode does not apply"` substring test still
      passes.
- [ ] Nested-EPIC test in `TestSprintManagerLoadOrResolve` covers
      grandchild-via-sub-EPIC.
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `scripts/little_loops/parallel/orchestrator.py`
  (EPIC-completion trigger, `_open_pr_for_branch()` epic-child PR
  target, `_inspect_worktree()` epic-awareness)
- `scripts/little_loops/cli/sprint/run.py` (in-place warning
  epic-awareness at lines 485, 518–528)

**Tests:**
- `scripts/tests/test_sprint.py` (nested-EPIC test)
- `scripts/tests/test_cli_sprint.py`
  (`TestFeatureBranchInPlaceWarning` epic counterpart)
- `scripts/tests/test_orchestrator.py` (epic-completion merge +
  epic-child PR target + inspect epic-awareness)
- `scripts/tests/test_worker_pool.py` (epic/* prefix audit)

**Estimated file count:** 2 implementation + 4 test = **6 files**.

## Additional Wiring Findings

_Wiring pass added by `/ll:wire-issue` — integration gaps discovered during
caller/importer + side-effect + test-gap analysis:_

### Tests to Update (not previously listed)

- `scripts/tests/test_orchestrator.py` — `TestInspectWorktree` (lines 909-1082)
  contains 6 tests that mock `git rev-list --count` and assert on its
  arguments. The orchestrator.py:415 change to
  `{epic_branch or base_branch}..{branch_name}` will affect:
  - `test_returns_actual_branch_for_feature_branch_mode` (~line 998-1024)
  - 5 other `TestInspectWorktree` tests at lines 912, 941, 974, 995, 1022,
    1054 — audit each for rev-list mock-arg compatibility.
  **NOTE**: The issue's reference to `test_inspect_worktree_with_feature_branch`
  at `test_worker_pool.py:1001` is **stale** — the actual test is
  `test_returns_actual_branch_for_feature_branch_mode` at
  `test_orchestrator.py:~998` (the test_worker_pool.py:1001 reference is
  unrelated worktree-setup code, not the feature-branch audit target).
- `scripts/tests/test_orchestrator.py` — `TestOrphanedWorktreeCleanup`
  (lines 319-516), specifically `test_deletes_branch_via_rev_parse`
  (line 485): hardcodes `parallel/`-prefixed branches in
  `rev_parse_result.stdout`. Add an epic/* assertion to verify
  `epic/<EPIC-ID>-<slug>` branches are NOT deleted by
  `_cleanup_orphaned_worktrees` (FEAT-2339 Decision Rationale #3 —
  explicit deletion only).
- `scripts/tests/test_orchestrator.py` — `TestOnWorkerComplete`
  (lines 1687-1921) covers success/failure/corrected/interrupted paths.
  FEAT-2449's epic-completion hook triggered from `_on_worker_complete`
  needs at least one integration test in this class (currently no
  coverage for the epic-completion trigger path).
- `scripts/tests/test_orchestrator.py` — `_pr_ready_branches` test
  accessor sites at lines 1962, 2004, 2050, 2087, 2119, 2130, 2151,
  2171 (8 sites). If FEAT-2449 introduces a parallel
  `_completed_epic_branches` dict, add an analogous helper/setup
  pattern at the same sites.

### Test Pattern to Model New Class After

- `scripts/tests/test_orchestrator.py` — `TestMergePendingWorktrees`
  (lines 1085-1162) is the closest precedent for the new
  `TestEpicCompletionMerge` class. Specifically
  `test_attempts_merge_with_commits_ahead` (line 1122-1162) shows the
  `_git_lock.run` mock pattern that captures `git merge --no-ff <branch>`
  invocations. The new EPIC-completion-merge test should follow this
  shape (mock `_git_lock.run`, capture `merge_called`, assert on
  `--no-ff` and the `epic/<EPIC-ID>-<slug>` branch name).

### Substring Assertions to Preserve

- `scripts/tests/test_orchestrator.py:2164` — `"pushed (PR skipped)"`
- `scripts/tests/test_orchestrator.py:2188` — `"pushed + PR opened"`
  Any new EPIC-completion log line emitted from `_report_results()` (or
  the new epic-completion-merge step) must NOT match these substrings.
  Suggested log lines that would conflict: `"Epic branch X merged into
  base"` (safe), `"EPIC X complete"` (safe), but `"pushed"` or
  `"PR"` in an EPIC completion message could collide — avoid those
  substrings.

### Files Explicitly NOT to Modify (boundary preservation)

- `scripts/little_loops/worktree_utils.py` — `_is_ll_branch()`
  (lines 213-223) and `cleanup_worktree()` (lines 161-201) MUST NOT be
  extended to match `epic/*` (FEAT-2339 Decision Rationale #3,
  ARCHITECTURE-094).
- `scripts/little_loops/parallel/merge_coordinator.py` —
  `MergeCoordinator._cleanup_worktree()` (lines 1061-1093) hardcodes
  `branch_name.startswith("parallel/")` at line 1088. Epic branches
  silently skip the `-D` deletion — this is correct behavior by
  accident, do NOT touch this method.
- `scripts/tests/test_merge_coordinator.py` — TestMergeCoordinatorCleanupWorktree
  (lines 2180-2208) covers the boundary; do NOT add assertions that
  change the existing `parallel/`-prefix-only behavior.

### Cross-Consumer Reference (no change needed)

- `scripts/little_loops/cli/issues/list_cmd.py:236-241` — the
  existing canonical completion-check precedent treats `cancelled`
  as terminal-done (`done + cancelled`). FEAT-2449 must EXPLICITLY
  diverge from this pattern (as the issue already notes) because a
  cancelled child should NOT trigger an epic-branch merge.
- `scripts/little_loops/cli/issues/epic_progress.py:54` — another
  consumer of `compute_epic_progress()` for reference; uses
  `by_status.get("done",0) + cancelled` for the badge (different
  semantics, not a conflict).

### Wiring Phase (Implementation Steps)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

7. Audit `TestInspectWorktree` (6 tests at `test_orchestrator.py:909-1082`)
   for `rev-list --count` mock-arg compatibility with the new
   `{epic_branch or base_branch}..{branch_name}` shape.
8. Add `epic/*` branch audit to `TestOrphanedWorktreeCleanup` (around
   `test_deletes_branch_via_rev_parse` at `test_orchestrator.py:485`) to
   verify `epic/<EPIC-ID>-<slug>` is NOT deleted by
   `_cleanup_orphaned_worktrees`.
9. Add an epic-completion-hook integration test to `TestOnWorkerComplete`
   (`test_orchestrator.py:1687-1921`) covering both success and
   partial-failure cases.
10. Model the new `TestEpicCompletionMerge` class after
    `TestMergePendingWorktrees.test_attempts_merge_with_commits_ahead`
    (`test_orchestrator.py:1122-1162`) — capture `git merge --no-ff
    <epic/<id>>` invocations via `_git_lock.run` mock.
11. Verify any new EPIC-completion log lines avoid the substrings
    `"pushed (PR skipped)"` and `"pushed + PR opened"` to preserve
    `test_orchestrator.py:2164, 2188` substring assertions.

## Session Log
- `/ll:wire-issue` - 2026-07-06T23:30:02 - `6b9899f6-bce4-48ec-86fb-922a81ba2170.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:22:03 - `b455d593-e617-47e1-8dd2-6121f588fada.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

## Blocks

- FEAT-2450

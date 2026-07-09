---
id: FEAT-2449
title: "per-EPIC integration branch \u2014 EPIC-completion merge + orchestrator/sprint\
  \ awareness"
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
- FEAT-2561
- FEAT-2562
- FEAT-2563
blocked_by:
- FEAT-2448
- FEAT-2561
decision_needed: false
confidence_score: 95
outcome_confidence: 83
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-2449: per-EPIC integration branch — EPIC-completion merge + orchestrator/sprint awareness

## Summary

**Unit A** of the per-EPIC integration branch completion work (re-scoped on
2026-07-09 via `/ll:confidence-check`). This child owns the **stateful core**:
**EPIC-completion detection** (when all children of an EPIC reach `done`, merge
the `epic/<EPIC-ID>-<slug>` integration branch into `base_branch` or open one
PR), the **config-branch wiring** that gates that trigger
(`merge_to_base_on_complete` / `open_pr`), and the **partial-failure gate** that
holds the epic branch open until every child is `done`.

Two sibling units were split out of the original FEAT-2449 to shrink its blast
radius (they became immediately actionable peers under EPIC-2451):
- **FEAT-2562** — `_inspect_worktree()` epic-branch comparison.
- **FEAT-2563** — `cli/sprint/run.py` in-place warning epic-awareness.

The original Scope item #2 (`_open_pr_for_branch()` epic-child PR target) was
**already delivered by FEAT-2448** and is no longer remaining work here.

Depends on FEAT-2448 (worker_pool + merge_coordinator wiring +
`WorkerResult.epic_branch` field) and on **FEAT-2561** (the shared
`find_nearest_epic_ancestor` / `build_parent_map` helper the partial-failure
gate uses to scope failure dicts by EPIC without reaching into WorkerPool
internals).

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

1. **EPIC-completion detection + completion merge/PR** — in the
   orchestrator's post-merge flow, call
   `compute_epic_progress(epic_id, all_issues)` from
   `scripts/little_loops/issue_progress.py:83` (walks the `parent:`
   chain transitively per commit `4887c87c`). When all children are
   terminally `done` (see the completion-predicate note below —
   `by_status.get("done")` **alone**, cancelled children do NOT count)
   and no children are failed/blocked, merge the epic branch to
   `base_branch` (or open one PR via
   `gh pr create --base base_branch --head epic/<id>`, analogous to the
   existing `orchestrator._open_pr_for_branch()` pattern). Then delete
   the epic branch (explicit deletion only — lift the inline
   `branch -D` shape from `orchestrator.py:557-561`; **not** via
   `_is_ll_branch()` or `_cleanup_worktree()`; see FEAT-2339 Decision
   Rationale #3).
2. **Config-branch wiring (closes the dead-read gap)** —
   `EpicBranchesConfig.merge_to_base_on_complete` (default `True`) and
   `EpicBranchesConfig.open_pr` (default `False`) at
   `scripts/little_loops/parallel/types.py:311–334` are currently
   **read nowhere** in orchestrator/worker_pool/merge_coordinator. The
   Step 1 trigger MUST branch on them: `merge_to_base_on_complete` gates
   the direct merge; `open_pr` selects the "open one PR" path instead.
   Add an AC/test asserting the merge is **skipped** when
   `merge_to_base_on_complete is False`.
3. **Partial-failure gate** — completion-merge is blocked until
   **ALL** children reach `done`; a failed/blocked child holds the
   epic branch open (unmerged, undeleted). Reuse the existing
   `Orchestrator.run()` precedent for group-failure gating
   (`failed_count == 0` all-or-nothing cleanup gate at
   `orchestrator.py:827-831`). Cross-reference
   `state.failed_issues` / `queue.failed_ids` against the EPIC's
   child-ID set — **computed via the FEAT-2561 shared helper**
   (`find_nearest_epic_ancestor` + `compute_epic_progress().children`,
   using the orchestrator's `self._issue_info_by_id`), NOT a reach into
   `worker_pool._find_nearest_epic_ancestor`. No existing structure
   already scopes these flat dicts by EPIC.
4. **Tests** —
   - `scripts/tests/test_orchestrator.py` — new `TestEpicCompletionMerge`
     class modeled on
     `TestMergePendingWorktrees.test_attempts_merge_with_commits_ahead`
     (`:1122-1162`): mock `_git_lock.run`, capture `merge_called`,
     assert on `git merge --no-ff epic/<id>` and the subsequent
     `branch -D`.
   - `scripts/tests/test_orchestrator.py::TestOnWorkerComplete`
     (`:1687-1921`) — at least one epic-completion-hook integration
     test covering both the success (all-done → merge) and
     partial-failure (one child failed → held open) cases.
   - Config-branch: test that EPIC-completion-merge is **skipped** when
     `merge_to_base_on_complete is False`, and takes the PR path when
     `open_pr is True`.
   - Partial-failure gate: test that completion-merge is blocked when
     any child is `failed` or `blocked`, not just when
     `done_count < total_count`.
   - `scripts/tests/test_sprint.py:TestSprintManagerLoadOrResolve`
     (~lines 2329–2540, "FEAT-1737") — add nested-EPIC test
     (grandchild with intermediate sub-EPIC parent) to cover the
     run-construction depth-mismatch (sprint.py still does direct-only
     `info.parent == epic_id` resolution — confirms and tests the known
     gap, and guards the transitive-walk semantics the completion gate
     relies on).

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

### Post-FEAT-2448 Anchor Refresh

_Added by `/ll:refine-issue` (2026-07-09) — FEAT-2448 has since landed
(commits `749b8096`, `5ada5e63`), shifting anchors in `orchestrator.py`
and **completing Scope item #2 ahead of this issue**. The refreshed
current-state facts below supersede the pre-FEAT-2448 anchors above
where they conflict; original findings are preserved verbatim for
provenance._

> ⚠ **Scope item #2 (`_open_pr_for_branch()` epic-child PR target) is
> already implemented and tested — it is NOT remaining work for
> FEAT-2449.** FEAT-2448 landed the epic-aware `--base`; the pre-FEAT-2448
> claim that `--base` is "hardcoded at line 1142 to
> `self.parallel_config.base_branch`" is now factually wrong.

- **`_open_pr_for_branch()` — `--base` is epic-aware (DONE).** Current
  `orchestrator.py:1146` reads
  `branch_state.get("epic_branch") or self.parallel_config.base_branch`.
  The epic branch is threaded via a `branch_state["epic_branch"]`
  dict-mutation at `orchestrator.py:1009` (set from `result.epic_branch`
  in `_on_worker_complete()`), NOT a new `_open_pr_for_branch()` kwarg —
  the signature is still `(issue_id, branch_name, branch_state)`. Already
  covered by `test_orchestrator.py`
  `test_on_worker_complete_feature_branch_pr_base_is_epic_branch`
  (~lines 2062–2116) and the `--base == "main"` fallback test
  `test_on_worker_complete_feature_branch_open_pr` (~lines 2008–2060).
  → **FEAT-2449 remaining PR work is only the EPIC-*completion*-merge PR
  (Step 1: `--head epic/<id> --base base_branch`), not the per-child PR.**

- **`_completed_epic_branches` dict is unnecessary — reuse the landed
  carrier.** No separate dict was introduced; epic-branch state rides on
  the existing per-issue `branch_state` dict stored in
  `_pr_ready_branches` via the `branch_state["epic_branch"]` key. Prefer
  deriving completion on-the-fly from `_pr_ready_branches` +
  `compute_epic_progress()` over adding a parallel dict.

- **NEW GAP — config fields are dead-read.**
  `EpicBranchesConfig.merge_to_base_on_complete` (default `True`) and
  `EpicBranchesConfig.open_pr` (default `False`) at
  `scripts/little_loops/parallel/types.py:311–334` are read **nowhere**
  in `orchestrator.py` / `worker_pool.py` / `merge_coordinator.py` (zero
  grep hits outside `types.py`, `config/core.py`, `config/automation.py`,
  `config-schema.json`, and their tests). Step 1's completion trigger
  MUST branch on these: `merge_to_base_on_complete` gates the direct
  merge; `open_pr` selects the "open one PR" path instead. Add an
  AC/test asserting the merge is skipped when
  `merge_to_base_on_complete is False`.

- **Line-anchor drift (orchestrator.py), current values:**
  | Anchor | Cited | Current | Note |
  |--------|-------|---------|------|
  | `_open_pr_for_branch()` body | 1109–1160 | **1113–1164** | +4 |
  | `--base` argument | 1142 | **1146** | +4, now epic-aware |
  | `branch_state["epic_branch"]` set | — | **1009** | new (FEAT-2448) |
  | `_pr_ready_branches` population | 1044–1045 | **1048–1049** | +4 |
  | `Failed: {failed_count}` log | 1249 | **1256** | +7 |
  | `if self.queue.failed_ids:` | 1252 | **1270** | drift |
  | `for issue_id in failed_ids` | 1269 | **1273** | +4 |

- **Anchors CONFIRMED unchanged (no edit needed):**
  `_inspect_worktree()` issue-ID regex (410) and `rev-list --count` (415)
  — still base-branch-only, epic-awareness genuinely remains FEAT-2449
  work; `_merge_pending_worktrees()` inline `branch -D` (557–561);
  group-failure gate `failed_count == 0` (827–831); `_pr_ready_branches`
  declaration (134); early `failed_issues`/`failed_ids` refs (622, 624,
  716). All of `issue_progress.py` (14, 17–48, 83) is unchanged.

- **`cli/sprint/run.py` anchor correction.** The in-place warning block
  is at **lines 517, 519–523, 524–529** (not 485/518–528 — cited line
  485 is unrelated `total_waves = len(waves)` scaffolding). No
  `effective_epic_branches` exists here yet — confirmed greenfield for
  FEAT-2449 (Scope #4).

## Out of Scope (split into sibling / follow-on children)

- **`_inspect_worktree()` epic-branch comparison** (former Scope #3) —
  **FEAT-2562** (peer under EPIC-2451).
- **`cli/sprint/run.py` in-place warning epic-awareness** (former
  Scope #4) — **FEAT-2563** (peer under EPIC-2451).
- **`_open_pr_for_branch()` epic-child PR target** (former Scope #2) —
  **already delivered by FEAT-2448** (`orchestrator.py:1146` is epic-aware;
  covered by `test_on_worker_complete_feature_branch_pr_base_is_epic_branch`).
- **Shared `find_nearest_epic_ancestor` / `build_parent_map` helper
  extraction** — **FEAT-2561** (this issue's declared blocker; consumed by the
  partial-failure gate).
- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs (ARCHITECTURE, API, CONFIGURATION, CLI, SPRINT_GUIDE), 9
  templates parity, prune_merged_feature_branches docstring — **FEAT-2450**.

## Acceptance Criteria

- [ ] When all children of an EPIC reach `done` (`by_status.get("done")`
      alone; cancelled children do NOT count) and no children are
      failed/blocked, the orchestrator triggers a merge of
      `epic/<EPIC-ID>-<slug>` into `base_branch` (or opens one PR
      per `epic_branches.open_pr` config), then deletes the epic branch.
- [ ] The completion merge is **skipped** when
      `epic_branches.merge_to_base_on_complete is False`, and takes the
      PR path when `epic_branches.open_pr is True` (config dead-read gap
      closed).
- [ ] When any child is failed/blocked, the epic branch is held
      open (no merge, no delete) — verified by partial-failure gate
      test that scopes `failed_ids` to the EPIC's child set via the
      FEAT-2561 helper.
- [ ] Nested-EPIC test in `TestSprintManagerLoadOrResolve` covers
      grandchild-via-sub-EPIC.
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `scripts/little_loops/parallel/orchestrator.py`
  (EPIC-completion trigger + merge/PR + `branch -D`, config-branch
  gating, partial-failure gate scoped via the FEAT-2561 helper)

**Tests:**
- `scripts/tests/test_orchestrator.py` (`TestEpicCompletionMerge` +
  `TestOnWorkerComplete` epic-completion hook + config-skip +
  partial-failure gate)
- `scripts/tests/test_sprint.py` (nested-EPIC test)

**Estimated file count:** 1 implementation + 2 test = **3 files**.

_(Down from 6: `_inspect_worktree`/`test_worker_pool` → FEAT-2562;
`cli/sprint/run.py`/`test_cli_sprint` → FEAT-2563; `_open_pr_for_branch`
already landed in FEAT-2448.)_

## Additional Wiring Findings

> ⚠ **Post-split redirect (2026-07-09):** the `_inspect_worktree` /
> `TestInspectWorktree` / `TestOrphanedWorktreeCleanup` findings below moved to
> **FEAT-2562**, and the `cli/sprint/run.py` / `TestFeatureBranchInPlaceWarning`
> findings moved to **FEAT-2563**. They are retained here as provenance (both
> new issues cite these anchors). The items that remain in FEAT-2449's scope are
> the `TestEpicCompletionMerge` / `TestOnWorkerComplete` / substring-collision
> findings.

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

## Confidence Check Notes

_Re-estimated by `/ll:confidence-check` on 2026-07-09 after the decomposition
below. The prior 70/100 pass (retained for provenance) covered the pre-split
6-file surface._

**Readiness Score**: 95/100 → PROCEED (one open prerequisite: FEAT-2561)
**Outcome Confidence**: 83/100 → HIGH

### Decomposition (2026-07-09)
Original FEAT-2449 (outcome 70/100, MODERATE) was split to shrink its blast
radius. The two breadth-heavy, loosely-coupled units became immediately
actionable peers, and the cross-module reach was lifted into a prerequisite
helper:
- **FEAT-2561** (prerequisite) — shared `find_nearest_epic_ancestor` /
  `build_parent_map` in `issue_progress.py`; removes the partial-failure gate's
  reach into `WorkerPool` internals.
- **FEAT-2562** (peer) — `_inspect_worktree()` epic-branch comparison + its
  `TestInspectWorktree` / `TestOrphanedWorktreeCleanup` audits.
- **FEAT-2563** (peer) — `cli/sprint/run.py` in-place warning + its
  `TestFeatureBranchInPlaceWarning` counterpart.

Result: FEAT-2449 now touches **1 impl file** (`orchestrator.py`) + 2 test
files, down from 2 impl + 4 test. Complexity 10→15, Change-surface 10→18.

### Residual Outcome Risk Factors
- The partial-failure gate is still the stateful core: it intersects the EPIC's
  child-ID set against `queue.failed_ids` / `state.failed_issues`. The
  cross-module reach is gone (FEAT-2561 supplies the mapping), but the
  gate + config-branch trigger (`merge_to_base_on_complete` / `open_pr`) are
  genuinely new control flow — the `TestEpicCompletionMerge` and config-skip
  tests are the ones to write first.
- Depends on FEAT-2561 landing first (declared `blocked_by`); it is a small,
  behavior-preserving extraction, so the prerequisite risk is low.

## Session Log
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl`
- `/ll:refine-issue` - 2026-07-09T21:00:17 - `38d1eded-7bd0-495b-aaf4-15a72cd44334.jsonl`
- `/ll:wire-issue` - 2026-07-06T23:30:02 - `6b9899f6-bce4-48ec-86fb-922a81ba2170.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:22:03 - `b455d593-e617-47e1-8dd2-6121f588fada.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

## Blocks

- FEAT-2450

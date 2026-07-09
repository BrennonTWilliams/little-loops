---
id: FEAT-2452
title: "per-EPIC integration branch \u2014 WorkerPool + WorkerResult dataclass wiring"
type: FEAT
priority: P3
status: done
captured_at: '2026-07-07T19:55:00Z'
completed_at: '2026-07-09T18:58:36Z'
discovered_date: 2026-07-07
discovered_by: confidence-check-decomposition
labels:
- parallel
- sprint
- epics
- git
- worktree
- merge
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
- FEAT-2453
blocked_by: []
unblocks:
- FEAT-2453
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# FEAT-2452: per-EPIC integration branch — WorkerPool + WorkerResult dataclass wiring

## Summary

First of two sequenced children of FEAT-2448 (decomposed via
`/ll:confidence-check` on 2026-07-07). This child lands the
`WorkerResult.epic_branch` field and threads the resolver's
output through `_process_issue` so that downstream consumers
(MergeCoordinator, Orchestrator) have a typed source of truth for
"what the worker forked from / merges into". Carries the broad
fanout (12 `WorkerResult(...)` returns + 4 `types.py` edits +
2 method-body updates) that drove FEAT-2448's
`score_change_surface = 10`.

The shallow read-site substitutions at
`merge_coordinator.py:624, :875` and `orchestrator.py:1142` are
**deferred to FEAT-2453** so this issue stays focused on the
dataclass and WorkerPool mechanics where the implementation risk
lives.

For full research context (anchors, scope rationale, FEAT-2447
resolver details, FEAT-2339 decision rationale), see FEAT-2448.
This child carries only the scope items, ACs, and verification
surface relevant to its reduced footprint.

## Parent Issue

Decomposed from FEAT-2448: per-EPIC integration branch —
worker_pool + merge_coordinator wiring. Decomposed on 2026-07-07
via `/ll:confidence-check` (outcome 74/100 → split into
FEAT-2452 + FEAT-2453 to lift the downstream piece to
HIGH outcome confidence without losing aggregate tractability).

EPIC-2451 (Per-EPIC integration branch strategy) is the parent
EPIC and remains the coordination container.

## Use Case

As a maintainer running `ll-parallel` with `epic_branches.enabled=True`, when
EPIC children are processed I need each `WorkerResult` to carry a typed
`epic_branch` so downstream consumers (MergeCoordinator, Orchestrator) can
distinguish EPIC children from standalone issues and diff/rebase against the
correct integration branch instead of always against `base_branch`. This issue
lands that typed source of truth plus the WorkerPool git-mechanics wiring
(`_get_changed_files` / `_update_branch_base` epic-mode variants); the read-site
consumers land in FEAT-2453. With `epic_branches.enabled=False` (default),
behavior is byte-for-byte identical to today.

## Current Behavior

`_resolve_branch_targets()` (`worker_pool.py:1564`, landed in
FEAT-2447) computes the fork/merge branch for an EPIC child, but its
output is discarded: `WorkerResult` has no field to carry it, so
downstream consumers (MergeCoordinator, Orchestrator) have no typed
source of truth for "what the worker forked from / merges into".
`_get_changed_files()` (`worker_pool.py:1078`) and
`_update_branch_base()` (`worker_pool.py:1100`) always diff/rebase
against `self.parallel_config.base_branch`, ignoring the epic branch
even when `epic_branches.enabled` is True. With the field absent, EPIC
children are indistinguishable from standalone issues downstream.

## Expected Behavior

`WorkerResult.epic_branch: str | None` carries the resolver's
fork/merge target, computed once at the head of `_process_issue()` and
threaded through all 12 `WorkerResult(...)` returns (`None` for
standalone issues). `_get_changed_files()` diffs against the epic
branch and `_update_branch_base()` rebases against it whenever
`self._worker_epic_branches[<issue_id>]` is set. With
`epic_branches.enabled` False (the default), behavior is byte-for-byte
identical to today. Downstream consumers gain a typed signal; their
read-site substitutions land separately in FEAT-2453.

## Scope

1. **`WorkerResult.epic_branch` field + 4-edit pattern**
   (`scripts/little_loops/parallel/types.py:91`) — add
   `epic_branch: str | None = None` after `interrupted: bool = False`
   at line 90. The 4-edit pattern (per Phase 2 finding at
   FEAT-2448:551-557) is:
   - (a) field declaration with default at `types.py:91`
   - (b) `Attributes:` docstring row at `types.py:71` (after the
     `interrupted:` line)
   - (c) `to_dict()` row at `types.py:111` (after the `interrupted`
     row at line 110)
   - (d) `from_dict()` row at `types.py:134` (after the `interrupted`
     row at line 133)
   Mirror the `was_blocked` / `interrupted` precedent at `types.py:89-90`
   exactly — both are bool defaults; `epic_branch` uses
   `str | None = None` (None = "use `base_branch`").

2. **12-return kwarg threading in `_process_issue()`**
   (`scripts/little_loops/parallel/worker_pool.py:326-646`) —
   compute `epic_branch` **once** at the top of `_process_issue`
   (immediately after `branch_name` / `worktree_path` are assigned
   at lines 333-345) via
   `epic_branch, _ = self._resolve_branch_targets(issue)` (the fork
   point; the merge target is the same string by construction per
   FEAT-2339 Decision Rationale #1). Pass `epic_branch=epic_branch`
   as a kwarg to **all 12** `WorkerResult(...)` returns in
   `_process_issue` (lines 384, 398, 414, 429, 456, 476, 519, 571,
   585, 606, 619, 635 — verified at FEAT-2448:417-419). The single
   `_handle_completion` return at `worker_pool.py:302` receives
   `worker_result: WorkerResult` so the new field flows through
   transparently — no edit needed at that site beyond ensuring the
   upstream `WorkerResult` has `epic_branch=` populated.

3. **`self._worker_epic_branches` instance-state dict**
   (`scripts/little_loops/parallel/worker_pool.py`) — populate
   `self._worker_epic_branches: dict[str, str | None] = {}`
   alongside `self._epic_branches_created: set[str]` at
   `worker_pool.py:189-190`. Set
   `self._worker_epic_branches[issue.issue_id] = epic_branch`
   immediately after the compute in step 2. Used by step 4.

4. **`_get_changed_files()` epic-mode variant**
   (`scripts/little_loops/parallel/worker_pool.py:1078-1098`) —
   when `self._worker_epic_branches.get(... )` returns a non-None
   value for the current issue, swap
   `self.parallel_config.base_branch` in the `git diff` command at
   line 1086 for the epic branch. The function does NOT receive
   `IssueInfo` (signature is `(self, worktree_path: Path)`), so
   the look-up key needs to be threaded via the calling site
   (lines 534 and 562) — extend the signature to accept
   `issue_id: str | None = None` OR use an alternative lookup
   keyed on `worktree_path`. The Decision Rationale (line 1144)
   prefers the instance-state pattern for symmetry with step 5.

5. **`_update_branch_base()` epic-mode variant**
   (`scripts/little_loops/parallel/worker_pool.py:1100-`) — when
   `self._worker_epic_branches.get(issue_id)` returns a non-None
   value, rebase against the epic branch instead of
   `<remote>/<base_branch>`. The existing function signature
   `(self, worktree_path: Path, issue_id: str) -> tuple[bool, str]`
   (lines 1100-1112) already takes `issue_id`; no signature change
   needed — the lookup is direct. Three existing tests at
   `scripts/tests/test_worker_pool.py:1711-1794` in `TestUpdateBranchBase`
   set `worker_pool.parallel_config.base_branch = "main"` before
   calling `_update_branch_base()`; add 3 epic-mode counterparts
   mirroring that fixture shape with
   `worker_pool._worker_epic_branches[issue_id] = "epic/EPIC-2451-..."`
   and `parallel_config.epic_branches.enabled = True`.

6. **Tests** —
   - `scripts/tests/test_parallel_types.py:161-359` — `TestWorkerResult`
     class needs `epic_branch is None` default assertion
     (`test_default_values` line 178-198), field round-trip coverage
     in 4 test methods (`test_creation_with_all_fields`,
     `test_to_dict`, `test_from_dict`, `test_roundtrip_serialization`),
     and matching `to_dict()` / `from_dict()` assertions. Per Phase 1
     wiring-pass item 7 at FEAT-2448:235-254.
   - `scripts/tests/test_worker_pool.py:120-149` — `TestWorkerResult`
     compact 2-test class needs 2 epic-branch counterparts
     (`test_epic_branch_can_be_set`, `test_epic_branch_serialization`).
     Per Phase 2 finding at FEAT-2448:672-685.
   - `scripts/tests/test_worker_pool.py:1711-1794` —
     `TestUpdateBranchBase` class needs 3 epic-mode counterparts
     modeled on the existing inline-`captured_cmds` pattern.
   - `scripts/tests/test_worker_pool.py:2191-2236` —
     `test_process_issue_uses_feature_branch_name_when_enabled`
     needs explicit `issue.parent = None` (per FEAT-2339 second-pass
     Tests finding at FEAT-2448:104-106 — a MagicMock without
     `parent` would have a truthy auto-attribute once epic-mode
     branch-naming checks `issue.parent`).
   - `scripts/tests/test_subprocess_mocks.py:615-663` —
     `test_setup_worktree_with_base_branch_appends_commit_ish`
     needs an epic-branch-substitution counterpart asserting that
     the worker forked from `epic/EPIC-2451-...` when
     `_resolve_branch_targets` returns the epic branch.

## Out of Scope (deferred)

- 2 `merge_coordinator.py` read-site substitutions
  (`merge_coordinator.py:624, :875`) — **FEAT-2453**.
- Orchestrator `branch_state` mutation at `orchestrator.py:1005`
  and `--base` read-site at `orchestrator.py:1142` —
  **FEAT-2453**.
- `_open_pr_for_branch()` signature/threading (the PR-target
  decision lands in FEAT-2449; read-site fanout lands in
  FEAT-2453) — **FEAT-2453 / FEAT-2449**.
- `test_merge_coordinator.py` and `test_orchestrator.py`
  modifications — **FEAT-2453**.
- ENH-2492 SQLite `orchestration_runs.epic_branch` column —
  **paired PR with ENH-2492** (FEAT-2492 owns the schema;
  coordinate at implementation time per FEAT-2448:794-829).
- `site/` published HTML regeneration (6 files) — **FEAT-2450
  (docs slice)** per FEAT-2448:832-859.
- `IssueProcessingResult.epic_branch` symmetric field
  (out-of-scope for FEAT-2448 line; relevant only if
  FEAT-2449/2450 extend the in-place path) — **deferred**.
- `docs/reference/API.md:3211-3235` WorkerResult field listing —
  pair with the `types.py` change; coordinate with
  **FEAT-2450 (docs)** for broader `docs/` updates.

## Acceptance Criteria

- [ ] `WorkerResult.epic_branch` is populated for EPIC children
      and `None` for standalone issues (verified in
      `TestWorkerResult.test_creation_with_all_fields` plus
      `_process_issue` integration tests).
- [ ] All 12 `WorkerResult(...)` returns in `_process_issue`
      receive `epic_branch=epic_branch` as a kwarg; full
      `python -m pytest scripts/tests/test_worker_pool.py` exits 0.
- [ ] `_get_changed_files()` diffs against the epic branch when
      `self._worker_epic_branches[<issue_id>]` is set (verified
      via inline `captured_cmds` assertion at line ~1086).
- [ ] `_update_branch_base()` rebases against the epic branch
      when `self._worker_epic_branches[issue_id]` is set
      (verified via 3 new `TestUpdateBranchBase` epic-mode
      tests).
- [ ] `test_process_issue_uses_feature_branch_name_when_enabled`
      sets `issue.parent = None` explicitly.
- [ ] With `epic_branches.enabled=False` (default), behavior is
      byte-for-byte identical to today (regression-tested via
      `_update_branch_base` and `_process_issue` test suite).
- [ ] Full `python -m pytest scripts/tests/` exits 0.
- [ ] `types.py:91`, `types.py:71`, `types.py:111`, `types.py:134`
      all updated in 4-edit pattern (mirrors `was_blocked` /
      `interrupted` precedent).
- [ ] `test_parallel_types.py:161-359` `TestWorkerResult` class
      passes with new field round-trip coverage.

## Files Touched

**Implementation (3 files):**
- `scripts/little_loops/parallel/worker_pool.py` — steps 2, 3,
  4, 5
- `scripts/little_loops/parallel/types.py` — step 1
  (4-edit pattern)

**Tests (4 files):**
- `scripts/tests/test_worker_pool.py` — TestWorkerResult
  (120-149), TestUpdateBranchBase (1711-1794),
  test_process_issue_uses_feature_branch_name_when_enabled
  (2191-2236)
- `scripts/tests/test_parallel_types.py` — TestWorkerResult
  (161-359)
- `scripts/tests/test_subprocess_mocks.py` —
  test_setup_worktree_with_base_branch_appends_commit_ish
  (615-663)

**Docs (paired with FEAT-2450):**
- `docs/reference/API.md:3211-3235` WorkerResult field listing
  (block when this lands; full update belongs to FEAT-2450).

**Estimated file count:** 3 implementation + 4 test + 1 docs = **8 files**.

## Impact

**Priority: P3** — Enabling scaffolding for the EPIC integration-branch
strategy (EPIC-2451). Not user-facing on its own; blocks FEAT-2453 (the
read-site consumer slice) and coordinates with FEAT-2449/2450. Correctly
sequenced after FEAT-2447 (resolver foundation, already landed on `main`
as `32ebdebb`).

**Effort: Medium** — 8 files (3 implementation + 4 test + 1 docs). The
change surface is broad but mechanical: a 4-edit dataclass pattern plus
12-return kwarg threading (`score_change_surface = 10`,
`score_complexity = 14`). No new architecture; mirrors the `was_blocked`
/ `interrupted` precedent exactly.

**Risk: Moderate** (outcome confidence 76/100). Primary risk is 12-return
kwarg discipline — a missed site falls back to `base_branch` silently;
mitigated by TDD on the `_process_issue` epic-branch capture. Secondary:
instance-state dict (`self._worker_epic_branches`) key collisions on
retry/resume paths. The default path (`epic_branches.enabled=False`) is
regression-guarded byte-for-byte.

## Decision Rationale

Two threading choices were locked in by `/ll:decide-issue` on
2026-07-07 (FEAT-2448:1108-1152) and are inherited verbatim by
this child:

### Decision 1 — `_open_pr_for_branch()` epic-branch threading

**Selected (carried to FEAT-2453):** Option (b) — mutate
`branch_state["epic_branch"] = result.epic_branch` at
`_on_worker_complete` before invocation; read `--base` from
`branch_state.get("epic_branch") or self.parallel_config.base_branch`
at `orchestrator.py:1142`.

**Why:** `branch_state` is the existing carrier for cross-call
worker state; mutating in place matches the established
`branch_state["pushed"] = True` pattern. Avoids a signature
change on `_open_pr_for_branch`.

### Decision 2 — `_get_changed_files()` / `_update_branch_base()` epic-branch threading

**Selected:** Option (a) — store per-issue epic branch on
`WorkerPool` instance via
`self._worker_epic_branches: dict[str, str | None]`, populated
once in `_process_issue()`, and look it up in `_get_changed_files()`
and `_update_branch_base()` via `self._worker_epic_branches.get(...)`.

**Why:** Neither helper receives `IssueInfo` so they cannot call
`_resolve_branch_targets(issue)` directly. The instance-state dict
keeps the fork/merge branch a single source of truth computed once
at `_process_issue` head, with no signature churn across the 3
existing callers and their inline-`captured_cmds` tests.

### ARCHITECTURE-095 — do NOT extend cleanup gates

Per `.ll/decisions.yaml:3803-3810`, the implementer must NOT add
epic-awareness to `prune_merged_feature_branches()` at
`worker_pool.py:1772-1790` or to the CLI mode at
`cli/parallel.py:267-287`. Epic `/*` lifecycle is owned exclusively
by FEAT-2449's `delete_epic_branch()` step.

## Codebase Research Findings

_Anchor and state verification (2026-07-07). Full research
context at FEAT-2448 § Codebase Research Findings._

- **`_resolve_branch_targets()` exists** at
  `worker_pool.py:1564-1590`. Returns `(fork_point, merge_target)`
  — both currently the same string per FEAT-2339 Decision
  Rationale #1 (flatten to nearest). No-op returns
  `(base_branch, base_branch)` when `epic_branches.enabled` is
  False or `issue.parent` is None.

- **`_setup_worktree` does NOT need modification.** At
  `worker_pool.py:650-678` the function delegates to
  `setup_worktree()` threading `base_branch` through verbatim;
  `base_branch` is `Optional[str]` (`None` = "fork from HEAD" per
  the docstring at lines 654-658). The existing
  `base_branch=` kwarg threading is sufficient because the
  resolver returns a non-None string when epic mode is active.

- **`WorkerPool.__init__` constructs no MergeCoordinator.**
  `ParallelOrchestrator.__init__` at `orchestrator.py:113-118`
  constructs both — no constructor signature change propagates
  from FEAT-2452.

- **`_handle_completion` at `worker_pool.py:302-310`** receives
  `worker_result: WorkerResult` and returns it unchanged in the
  worker-future-failed fallback. The new `epic_branch` field
  flows through transparently — no edit needed at this site
  beyond ensuring the upstream `WorkerResult` already has
  `epic_branch=` populated (a precondition of step 2).

- **`_get_changed_files` callers in `_process_issue`** at
  `worker_pool.py:534` (first call, before verification gate)
  and `worker_pool.py:562` (after
  `_recover_committed_leaks`). Both call sites use the standard
  `worker_pool._get_changed_files(worktree_path)` shape — step 4
  epic-mode threading must apply to BOTH call sites.

- **`_update_branch_base` single caller in `_process_issue`** at
  `worker_pool.py:602`:
  `base_updated, base_error = self._update_branch_base(worktree_path, issue.issue_id)`
  followed by `WorkerStage.MERGING` (line 605) and a
  `WorkerResult` return (lines 608-619) when `base_updated` is
  False. Step 5 update applies at this one caller; the 3 existing
  tests in `TestUpdateBranchBase` (lines 1714, 1743, 1774)
  directly invoke `_update_branch_base` and need parallel
  epic-mode counterparts.

- **`test_process_issue_uses_feature_branch_name_when_enabled`**
  at `test_worker_pool.py:2191-2236` uses a MagicMock for `issue`
  that has no explicit `parent` attribute. A MagicMock auto-
  attribute is truthy, so without `issue.parent = None` set,
  epic-mode branch-naming would attempt to walk a mock parent.
  Per FEAT-2339 second-pass Tests finding at FEAT-2448:104-106.

- **`WorkerResult(...)` constructions all use kwargs.** Verified
  at 73+ sites (test_parallel_types.py:65, 167, 181, 203, 248,
  273, 293, 307, 324 [9 sites]; test_worker_pool.py:125, 139,
  408, 428, 452, 483, 559, 586 [8 sites]; test_subprocess_mocks.py
  [2 sites]; test_merge_coordinator.py [17 sites]; test_orchestrator.py
  [37 sites]). **No test asserts on a literal full
  `WorkerResult.to_dict()` dict** — the field addition is safe for
  the existing suite, only the new tests assert on the new key
  (mirrors `was_blocked` / `interrupted` precedent at ENH-036).

- **No `to_dict()` ripple breaks** — `MergeRequest.to_dict()` at
  `types.py:217` nests `worker_result.to_dict()`; existing tests
  at `test_parallel_types.py:418-468` use field-level assertions
  only (`result["worker_result"]["issue_id"] == "BUG-001"`), not
  strict-shape. Adding `epic_branch` is safe.

### Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-07-09 — anchor re-verification against
current `main` (only the FEAT-2447 foundation commit `32ebdebb` landed since
2026-07-07 capture):_

- **All function/class anchors confirmed exact**: `_resolve_branch_targets`
  (`worker_pool.py:1564`), `_get_changed_files` (`:1078`, callers `:534` and
  `:562`), `_update_branch_base` (`:1100`, single caller `:602`),
  `_process_issue` (`:326`), `_epic_branches_created` init (`:190`). Test
  anchors also exact: `test_worker_pool.py` `TestWorkerResult:120`,
  `TestUpdateBranchBase:1711`,
  `test_process_issue_uses_feature_branch_name_when_enabled:2191`;
  `test_parallel_types.py` `TestWorkerResult:162`; `test_subprocess_mocks.py`
  `test_setup_worktree_with_base_branch_appends_commit_ish:615`.
- **`epic_branch` field confirmed absent** — `git grep epic_branch
  scripts/little_loops/parallel/` matches only `EpicBranchesConfig`
  (FEAT-2447), never `WorkerResult.epic_branch`. Feature is unimplemented as
  expected.
- ⚠ **12-return line numbers drifted +2**: the `WorkerResult(...)` returns in
  `_process_issue` are now at **386, 400, 416, 431, 458, 478, 521, 573, 587,
  608, 621, 637** (Scope item 2 and AC #2 list 384, 398, 414, 429, 456, 476,
  519, 571, 585, 606, 619, 635). Count is still exactly **12**. Key off the
  `_process_issue` function boundary + `git grep -n 'return WorkerResult('`,
  not the literal line numbers.
- ⚠ **`types.py` 4-edit anchors drifted +1**: current `interrupted` rows are
  field `:90`, docstring `:71`, `to_dict` `:111`, `from_dict` `:134` — so the
  new `epic_branch` rows insert at `:91`, `:72`, `:112`, `:135` respectively
  (Scope item 1 lists 91/71/111/134). The "insert after the `interrupted`
  line" instruction remains correct regardless of exact number.

### Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-07-09 (second pass, `--full-rewrite`) —
re-verification against current `main` (now includes the `add8a463` lint/format
commit on top of the FEAT-2447 foundation `32ebdebb`):_

- **Zero drift since the earlier 2026-07-09 pass.** All 12 `return
  WorkerResult(...)` sites in `_process_issue` remain at **386, 400, 416, 431,
  458, 478, 521, 573, 587, 608, 621, 637** (exactly as the prior note recorded;
  `grep -c 'return WorkerResult(' worker_pool.py` = 12).
- **All function anchors still exact**: `_process_issue` (`:326`),
  `_get_changed_files` (`:1078`, callers `:534` and `:562`),
  `_update_branch_base` (`:1100`, single caller `:602` —
  `self._update_branch_base(worktree_path, issue.issue_id)`),
  `_resolve_branch_targets` (`:1564`), `_epic_branches_created` init (`:190`).
  `types.py` `interrupted` rows still field `:90` / docstring `:71` / `to_dict`
  `:111` / `from_dict` `:134` (new `epic_branch` rows insert at 91/72/112/135).
- **All test anchors still exact**: `test_parallel_types.py` `TestWorkerResult`
  (`:162`); `test_worker_pool.py` `TestWorkerResult` (`:120`),
  `TestUpdateBranchBase` (`:1711`),
  `test_process_issue_uses_feature_branch_name_when_enabled` (`:2191`);
  `test_subprocess_mocks.py`
  `test_setup_worktree_with_base_branch_appends_commit_ish` (`:615`).
- **Dependency gate satisfied**: `FEAT-2447` (blocker) is **Completed** on
  `main`; `FEAT-2453` (unblocks) is **Open** and correctly waiting. `epic_branch`
  remains absent from `WorkerResult` — feature unimplemented as expected.
- No new gaps surfaced. The issue is implementation-ready; all Scope, AC, and
  Files-Touched references resolve against current `main`.

## Wiring Pass — 2026-07-07

### Configuration

- **No `config-schema.json` changes** in FEAT-2452. The
  `parallel.epic_branches` block landed in FEAT-2447.
  FEAT-2452 only consumes the resolver output and reads
  `result.epic_branch` downstream.

- **No template changes** in `scripts/little_loops/templates/*.json`
  (9 templates). FEAT-2447 stamped `epic_branches: {enabled: false}`
  explicitly; FEAT-2452 inherits.

### Test files NOT requiring update (verified)

- `scripts/tests/test_cli.py:479-484, 1638-1642` — hardcoded
  `"parallel"` dict fixtures. These are FEAT-2447's concern;
  FEAT-2452 does not modify config schema.

- `scripts/tests/test_cli_loop_worktree.py:527-554` — instantiates
  `WorkerPool` with `ParallelConfig`. Constructor signature
  unchanged; no update needed.

- `scripts/tests/test_cli_sprint.py:883-1004` — exercises
  `parallel.base_branch` config directly. Not affected.

### Internal sibling import lines (no code change)

- `scripts/little_loops/parallel/orchestrator.py:30` — imports
  from `parallel.types`. `WorkerResult.epic_branch` flows through
  transparently.
- `scripts/little_loops/parallel/merge_coordinator.py:18-23` —
  imports `MergeRequest`, `MergeStatus`, `ParallelConfig`,
  `WorkerResult`. Same.
- `scripts/little_loops/parallel/worker_pool.py:26` — imports
  `ParallelConfig`, `WorkerResult`, `WorkerStage`. Same.

### Verification surface (post-implementation)

- Full `python -m pytest scripts/tests/` exits 0.
- `git grep 'epic_branch' scripts/little_loops/` returns 13+ new
  hits (1 field declaration + 1 docstring + 2 to_dict/from_dict +
  12 _process_issue returns + 1 _worker_epic_branches dict).
- `git grep -E 'epic_branch.*None' scripts/little_loops/`
  matches the field declaration default + `result.epic_branch or
  self.config.base_branch` in FEAT-2453 (which uses this issue's
  field declaration as the canonical no-op signal).

## Confidence Check Notes

_Re-validated by `/ll:confidence-check` on 2026-07-09 (post
`/ll:refine-issue` anchor re-verification; `FEAT-2447` confirmed
Completed on `main` as `32ebdebb`)._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE
_(corrected from 76 — the four Phase 2b criterion scores
(14+25+25+10) sum to 74, not 76; frontmatter now matches.)_

_Original assessment, added by `/ll:confidence-check` on 2026-07-07
(decomposition re-validation after FEAT-2448 split)._

### Outcome Risk Factors
- **12-return kwarg discipline**: All 12 `WorkerResult(...)` returns
  in `_process_issue()` must receive `epic_branch=epic_branch`
  uniformly. A missed kwarg site falls back to `base_branch`
  silently. Mitigate by writing the `TestWorkerResult` and
  `_process_issue` tests first (TDD) and asserting the epic branch
  appears in `_setup_worktree(base_branch=...)` capture.
- **Instance-state dict key collisions**: `self._worker_epic_branches`
  is a new dict on `WorkerPool`. If the same issue is processed
  twice (retry path, pause/resume), the dict accumulates stale
  entries. The `_handle_completion` worker-future-failed fallback at
  `worker_pool.py:302-310` returns the upstream `WorkerResult`
  unchanged — verify the dict key remains in scope.
- **Downstream ENH-2492 SQLite coordination**: the proposed
  `orchestration_runs` schema at ENH-2492:274-292 does not yet
  declare an `epic_branch` column; if ENH-2492 lands before
  FEAT-2452, `record_orchestration_run()` silently drops the
  field. Sequence the landings or extend ENH-2492's DDL as a
  paired PR.
- **WorkerPool-wide impact of instance-state**: introducing
  `self._worker_epic_branches` is a new `WorkerPool` field. Any
  future test that constructs a `WorkerPool` and calls
  `_get_changed_files` or `_update_branch_base` without seeding
  the dict will hit the default empty-dict no-op path — assert
  on this with `assert _worker_epic_branches == {} or
  _worker_epic_branches[issue_id] == "epic/..."` in epic-mode
  tests.

## Decomposition Rationale

FEAT-2448 was split into FEAT-2452 + FEAT-2453 on 2026-07-07 via
`/ll:confidence-check`. The split lift:

| Issue | A | B | C | D | Total | Tier |
|---|---|---|---|---|---|---|
| FEAT-2448 (unsplit) | 14 | 25 | 25 | 10 | 74 | MODERATE |
| **FEAT-2452** (this) | 14 | 25 | 25 | 10 | **74** | MODERATE |
| FEAT-2453 (sibling) | 18 | 25 | 25 | 18 | 86 | **HIGH** |

FEAT-2452 retains the broad-fanout piece (`WorkerResult`
dataclass ripple + 12-return threading + instance-state dict).
The 3 read-site substitutions (the clean piece) move to
FEAT-2453 and achieve HIGH outcome confidence. Aggregate risk is
similar; per-issue tractability jumps dramatically.

## Confidence Check Notes

_Re-validated by `/ll:confidence-check --auto` on 2026-07-09 (post second
`/ll:refine-issue --full-rewrite` pass; HEAD `a9caae05`)._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE (unchanged)

All 12 `WorkerResult(...)` return-site line numbers, the `types.py` 4-edit
anchors, and test anchors were re-verified directly against `worker_pool.py`
at HEAD `a9caae05` and match the prior 2026-07-09 pass exactly — zero drift.
`epic_branch` remains absent from `WorkerResult` (unimplemented, as expected).
Scores and Outcome Risk Factors are unchanged from the prior check; see the
original **Confidence Check Notes** and **Decomposition Rationale** sections
above for the full risk-factor list (12-return kwarg discipline,
instance-state dict collisions, ENH-2492 SQLite coordination, WorkerPool-wide
instance-state impact). No new gaps found.

## Confidence Check Notes

_Re-validated by `/ll:confidence-check --auto` on 2026-07-09 (HEAD unchanged
at `a9caae05`)._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE (unchanged)

Zero drift since the prior 2026-07-09 pass: all 12 `return WorkerResult(...)`
sites confirmed at lines 386, 400, 416, 431, 458, 478, 521, 573, 587, 608,
621, 637; blocker `FEAT-2447` confirmed `done` on `main`. No new gaps.

### Outcome Risk Factors
- **12-return kwarg discipline**: deep per-site complexity — a missed
  `epic_branch=epic_branch` kwarg on any of the 12 `WorkerResult(...)`
  returns falls back to `base_branch` silently. See the original
  **Confidence Check Notes** section above for the full risk-factor list
  (instance-state dict collisions, ENH-2492 SQLite coordination,
  WorkerPool-wide instance-state impact) — unchanged.

## Resolution

Implemented 2026-07-09. All 8 acceptance criteria satisfied; full
`python -m pytest scripts/tests/` exits 0 (14411 passed, 36 skipped).

**Changes:**
- `types.py` — added `WorkerResult.epic_branch: str | None = None` via the
  4-edit pattern (field, `Attributes:` docstring, `to_dict`, `from_dict`),
  mirroring the `interrupted` precedent.
- `worker_pool.py`:
  - New `self._worker_epic_branches: dict[str, str | None]` instance state
    alongside `_epic_branches_created`.
  - `_process_issue` computes `epic_branch` once at the head via
    `_resolve_branch_targets(issue)`, normalizing the resolver's no-op
    `base_branch` return to `None`; populates the dict; threads
    `epic_branch=epic_branch` into all 12 `WorkerResult(...)` returns; and
    forks the worktree from the epic branch when set.
  - `_get_changed_files(worktree_path, issue_id=None)` diffs against the epic
    branch when the dict has a non-None entry.
  - `_update_branch_base` rebases directly onto the local epic branch (no
    remote fetch) when set; standalone path unchanged.
- Tests: `test_parallel_types.py` `TestWorkerResult` round-trip coverage;
  `test_worker_pool.py` 2 `TestWorkerResult` + 3 `TestUpdateBranchBase`
  epic-mode counterparts, `issue.parent = None` on the feature-branch test,
  and a `*args`-tolerant `mock_get_changed_files`; `test_subprocess_mocks.py`
  epic-fork counterpart.
- Docs: `docs/reference/API.md` `WorkerResult` listing gains the field
  (broader `docs/` sweep remains with FEAT-2450).

With `epic_branches.enabled=False` (default), behavior is byte-for-byte
identical to prior. Read-site consumers (MergeCoordinator / Orchestrator)
remain deferred to **FEAT-2453**, now unblocked.

## Session Log
- `/ll:manage-issue` - 2026-07-09T18:57:49Z - `45a56f3e-99e2-425b-9d74-8bc8e49aa086.jsonl`
- `/ll:ready-issue` - 2026-07-09T18:39:22 - `7384e9b7-3a22-411a-a727-ca3b027573b8.jsonl`
- `/ll:refine-issue` - 2026-07-09T18:17:13 - `e402cd57-22c6-4b4a-a9ad-45a538419eb4.jsonl`
- `/ll:refine-issue` - 2026-07-09T18:14:30 - `0c3a3e3c-e9de-428f-862c-1b10b893567a.jsonl`
- `/ll:refine-issue` - 2026-07-09T18:11:19 - `04a77baa-c61a-4825-817f-993caeca72dc.jsonl`
- `/ll:format-issue` - 2026-07-09T18:08:42 - `52677662-fb7d-4637-9d1e-bd07e2701cc6.jsonl`
- `/ll:confidence-check` - 2026-07-09T06:24:13Z - `0786b08c-9316-4bd6-8316-0d20701ee90c.jsonl`
- `/ll:refine-issue` - 2026-07-09T06:22:00 - `52075df2-c325-49ce-8fc7-103a442bdc6d.jsonl`
- `/ll:confidence-check` - 2026-07-09T06:20:04Z - `2bcdfc9d-08e7-44a5-8c16-655e68b1a3cb.jsonl`
- `/ll:refine-issue` - 2026-07-09T06:18:08 - `3340fe3f-5975-4f39-865d-fd195dac2e64.jsonl`
- `/ll:refine-issue` - 2026-07-09T06:14:37 - `d0dede05-f894-417a-9212-83f694958c89.jsonl`
- `/ll:refine-issue` - 2026-07-09T06:14:13 - `d0dede05-f894-417a-9212-83f694958c89.jsonl`
- `/ll:confidence-check` - 2026-07-09T06:11:36 - `cceb71c9-78d9-4aa9-a775-4ee8f0490e78.jsonl`
- `/ll:format-issue` - 2026-07-09T06:08:56 - `31178140-4c59-4c58-81af-2c64fc94ef8d.jsonl`
- `/ll:refine-issue` - 2026-07-09T05:14:25 - `bd469245-20a5-4329-84fa-c42291a847a7.jsonl`

- `/ll:confidence-check` - 2026-07-07T19:55:00 - `51846f72-c135-4aae-98df-cfb6f2d84afe.jsonl` (decomposition re-validation)
- `/ll:confidence-check-decomposition` - 2026-07-07T19:55:00 - `51846f72-c135-4aae-98df-cfb6f2d84afe.jsonl`

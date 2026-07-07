---
id: FEAT-2448
title: per-EPIC integration branch — worker_pool + merge_coordinator wiring
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
- worktree
- merge
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2447
- FEAT-2449
- FEAT-2450
blocked_by:
- FEAT-2447
decision_needed: false
confidence_score: 95
outcome_confidence: 60
score_complexity: 7
score_test_coverage: 18
score_ambiguity: 6
score_change_surface: 0
---

# FEAT-2448: per-EPIC integration branch — worker_pool + merge_coordinator wiring

## Summary

Second of four sequenced children decomposed from FEAT-2339. This child
**wires the resolver into worker_pool and merge_coordinator** so that
when epic mode is active, an EPIC child's branch forks from and merges
into the shared `epic/<EPIC-ID>-<slug>` branch instead of
`base_branch`. Carries the cross-module state threading
(`WorkerPool` → `MergeCoordinator`) flagged as the load-bearing risk
in FEAT-2339's Confidence Check Notes.

Depends on FEAT-2447 (config + `_resolve_branch_targets` resolver).

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

1. **Branch-naming + worktree setup**
   (`scripts/little_loops/parallel/worker_pool.py:334-360`) — when
   epic mode active and `issue.parent` resolves to an EPIC, name the
   worker's branch per today's `feature/<id>-<slug>` /
   `parallel/<id>-<timestamp>` convention (decision: epic mode
   changes only the fork point and merge target, **not** the child's
   branch name — see FEAT-2339 Decision Rationale #3). Pass the
   resolver's fork point as `base_branch` to
   `_setup_worktree(base_branch=...)` instead of
   `self.parallel_config.base_branch`.
2. **`WorkerResult.epic_branch` field** — add
   `epic_branch: str | None = None` to `WorkerResult` in
   `scripts/little_loops/parallel/types.py` with matching
   `to_dict()` / `from_dict()` rows, mirroring how `was_blocked`
   (ENH-036) and `interrupted` were added. Populate **once** in
   `WorkerPool._process_issue()` at the same site as `branch_name` /
   `worktree_path`, immediately above the
   `_setup_worktree(base_branch=...)` call. The fork point and merge
   target are the same string per Decision Rationale #1 (flatten to
   nearest), so the same `_resolve_branch_targets()` return value
   threads through both.
3. **Three downstream consumer sites** — replace
   `base = self.config.base_branch` with
   `base = result.epic_branch or self.config.base_branch` at:
   - `scripts/little_loops/parallel/merge_coordinator.py:624`
     (checkout in `_process_single_merge()`)
   - `scripts/little_loops/parallel/merge_coordinator.py:875`
     (fetch + rebase in same method)
   - `scripts/little_loops/parallel/orchestrator.py:1142` — note:
     `_open_pr_for_branch()` itself stays untouched here; only the
     `--base <value>` read site switches to the epic branch (the full
     PR target decision is FEAT-2449's "child PR lands on epic
     branch" step).
4. **`_get_changed_files()` epic-mode variant**
   (`scripts/little_loops/parallel/worker_pool.py`) — when an issue
   has `epic_branch` set, diff against the epic branch
   (`git diff --name-only <epic_branch> HEAD`) for accurate
   changed-file detection when children share the epic branch.
5. **`_update_branch_base()` epic-mode variant**
   (`scripts/little_loops/parallel/worker_pool.py:_update_branch_base`) —
   when epic mode active, rebase against the epic branch instead of
   `<remote>/<base_branch>`. Three existing tests at
   `scripts/tests/test_worker_pool.py:1714–1791` set
   `worker_pool.parallel_config.base_branch = "main"` before calling
   `_update_branch_base()`; add epic-mode counterparts.
6. **Tests** —
   - `scripts/tests/test_worker_pool.py:test_process_issue_uses_feature_branch_name_when_enabled`
     (lines 2191–2236) — add explicit `issue.parent = None` when this
     area is touched (per FEAT-2339 second-pass Tests finding: a
     MagicMock without `parent` would have a truthy auto-attribute once
     epic-mode branch-naming checks `issue.parent`).
   - `scripts/tests/test_worker_pool.py` — new epic-mode variants of
     `_update_branch_base` tests asserting rebase target is the epic
     branch when `epic_branches.enabled=True` and `issue.parent` is
     set.
   - `scripts/tests/test_merge_coordinator.py` — new
     `test_*_epic_branch_*` tests verifying that `MergeCoordinator`
     routes the merge target to the epic branch (not `base_branch`)
     when the issue has a parent EPIC and
     `epic_branches.enabled=True`. Modeled on the existing
     `test_*_untracked_files_error` / `test_*_local_changes_error`
     patterns.
   - `scripts/tests/test_orchestrator.py:test_on_worker_complete_feature_branch_open_pr`
     (lines 2008–2052) — add an assertion on the actual `--base`
     value so a silent regression in `_open_pr_for_branch()`'s
     `--base` target switching would be caught.
   - `scripts/tests/test_subprocess_mocks.py:test_setup_worktree_with_base_branch_appends_commit_ish`
     (~line 615) plus the two assertions at ~838 and ~892 — add
     epic-branch-substitution counterparts covering the new path.

## Out of Scope (deferred to follow-on children)

- EPIC-completion → epic-branch merge logic — **FEAT-2449**.
- Orchestrator `_inspect_worktree()` rev-list comparison against
  epic branch — **FEAT-2449**.
- `cli/sprint/run.py` in-place warning epic-awareness — **FEAT-2449**.
- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs, 9 templates parity, prune_merged_feature_branches docstring
  — **FEAT-2450**.

## Acceptance Criteria

- [ ] When `epic_branches.enabled=True` and an issue has an EPIC
      parent, the worker's branch forks from
      `epic/<EPIC-ID>-<slug>` (verified in
      `_setup_worktree(base_branch=...)` capture in
      `test_subprocess_mocks.py`).
- [ ] `WorkerResult.epic_branch` is populated for EPIC children and
      None for standalone issues.
- [ ] `_process_single_merge()` checks out and rebases against
      `result.epic_branch or self.config.base_branch` at
      `merge_coordinator.py:624` and `:875`.
- [ ] `_open_pr_for_branch()` reads `--base` from
      `result.epic_branch or self.config.base_branch` at
      `orchestrator.py:1142`.
- [ ] `_get_changed_files()` diffs against `epic_branch` when set.
- [ ] `_update_branch_base()` rebases against the epic branch when
      epic mode active.
- [ ] With `epic_branches.enabled=False` (default), behavior is
      byte-for-byte identical to today (regression-tested via the
      updated `_update_branch_base` and `_process_issue` tests).
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `scripts/little_loops/parallel/worker_pool.py` (branch naming,
  worktree setup, `_get_changed_files`, `_update_branch_base`,
  `_process_issue`)
- `scripts/little_loops/parallel/merge_coordinator.py` (two consumer
  sites at :624 and :875)
- `scripts/little_loops/parallel/orchestrator.py` (one consumer site
  at :1142 — read only; full PR-target logic is FEAT-2449)
- `scripts/little_loops/parallel/types.py` (`WorkerResult.epic_branch`
  field + `to_dict`/`from_dict`)

**Tests:**
- `scripts/tests/test_worker_pool.py`
- `scripts/tests/test_merge_coordinator.py`
- `scripts/tests/test_orchestrator.py`
- `scripts/tests/test_subprocess_mocks.py`

**Estimated file count:** 4 implementation + 4 test = **8 files**.

## Wiring Pass

_Wiring pass added by `/ll:wire-issue` — fills gaps found by Phase 4 caller/side-effect/test-gap agents (2026-07-06)._

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/parallel/__init__.py:18-49` — re-exports `WorkerResult`,
  `WorkerPool`, `MergeCoordinator`, `ParallelConfig` in `__all__`. **No code
  change needed** — the new `WorkerResult.epic_branch` field flows through
  transparently because all exports are by name. Verified via Agent 1.
- `scripts/little_loops/cli/parallel.py:197, 271` — constructs
  `WorkerPool(parallel_config, ...)` at cleanup and prune paths. **No code
  change needed** — constructor signature unchanged by FEAT-2448. Verified
  via Agent 1.
- `scripts/little_loops/cli/sprint/run.py:20-21` — imports
  `ParallelOrchestrator`, `SprintWorkerContext`. **No code change needed.**
- `scripts/little_loops/config/core.py:37, 461, 501-504` —
  `BRConfig.create_parallel_config` and `self._parallel.base_branch`. **No
  code change needed** (FEAT-2447 owns the `epic_branches` block here).
- `scripts/little_loops/config/automation.py:63, 98` —
  `ParallelAutomationConfig.base_branch` read/write. **No code change
  needed.** Verified via Agent 1.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/API.md:3211-3235` — `WorkerResult` dataclass listing must
  add `epic_branch: str | None = None` after `interrupted: bool = False` to
  mirror the dataclass field added in `types.py:91`. The `Attributes:`
  docstring block at `types.py:55-72` gets a matching row, but the API.md
  listing needs the same update. **(Direct FEAT-2448 wiring point — Agent 2
  finding.)**
- (Out of scope here, deferred to FEAT-2447) `docs/reference/API.md:3177` —
  `ParallelConfig` field listing for `epic_branches`. Agent 2 deferred to
  FEAT-2447; verifying here so FEAT-2448's reviewer knows.
- (Out of scope here, deferred to FEAT-2450)
  `docs/reference/CONFIGURATION.md:360` — config table needs
  `epic_branches` row (FEAT-2450 owns per FEAT-2450:84-87).
- (Out of scope here, deferred to FEAT-2450) `docs/guides/SPRINT_GUIDE.md:305`
  — note that `epic/*` branches are out of scope for prune (FEAT-2450 owns).
- (Out of scope here, deferred to FEAT-2450) `docs/ARCHITECTURE.md:529-536,
  360-364` — sequence diagrams need optional `epic_branch` annotation
  (FEAT-2450 owns).
- `.claude/CLAUDE.md` — verified no relevant references (Agent 2); no update
  needed.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

#### New test file to update (5th file, not in original 4-file scope)

- `scripts/tests/test_parallel_types.py:161-359` — `TestWorkerResult` class
  MUST be updated for the new `epic_branch` field. The class has 9 test
  methods that exercise `WorkerResult` directly:
  - `test_default_values` (line 178-198) — add
    `assert result.epic_branch is None` after the `interrupted is False`
    assertion.
  - `test_creation_with_all_fields` (line 200-232) — add
    `epic_branch="epic/EPIC-2451-..."` to the constructor and assert the
    field round-trips.
  - `test_to_dict` (line 234-243) — add
    `assert result["epic_branch"] is None` after the `interrupted` assertion
    at line 243.
  - `test_from_dict` (line 259-281) — include
    `"epic_branch": "epic/EPIC-2451-..."` in the input dict and assert
    `result.epic_branch` matches.
  - `test_roundtrip_serialization` (line 321-359) — set/assert
    `epic_branch` to verify round-trip integrity.
  - Mirror the existing `was_blocked`/`interrupted` precedent at
    `types.py:89-90`.

#### Test files that may break silently (FEAT-2447 dependency)

These hardcoded `"parallel"` dict fixtures may fail schema validation when
FEAT-2447 lands `epic_branches` if the schema is strict on missing keys
(`additionalProperties: false` at `config-schema.json:408`). Verify (and add
`"epic_branches": {"enabled": false}` if needed) after FEAT-2447 lands:

- `scripts/tests/conftest.py:284-296` — `sample_config["parallel"]`
- `scripts/tests/test_cli.py:479-484` — hardcoded `"parallel"` block
- `scripts/tests/test_cli.py:1642-1647` — second hardcoded `"parallel"` block
- `scripts/tests/test_cli_e2e.py:105-110` — hardcoded `"parallel"` block
- `scripts/tests/test_issue_workflow_integration.py:197-202` — hardcoded
  `"parallel"` block

These are FEAT-2447's concern (the schema change), but FEAT-2448's
implementation must run `python -m pytest scripts/tests/` end-to-end after
FEAT-2447 lands and update any fixtures that fail.

#### Test files that don't need updating (verified)

- `scripts/tests/test_cli_loop_worktree.py:527-554`
  (`TestWorkerPoolCleanupBranchGuard`) — instantiates `WorkerPool` with
  `ParallelConfig` fixture. **No update needed** (constructor signature
  unchanged; verified by Agent 1).
- `scripts/tests/test_cli_sprint.py:883-1004` — exercises
  `parallel.base_branch` config directly. Not affected by FEAT-2448's
  per-WorkerResult `epic_branch` field. (May be affected by FEAT-2447's
  `base_branch` auto-detection default change — out of scope here.)
- `scripts/tests/test_config.py:850, 2324` — `create_parallel_config` and
  `test_from_dict_parallel_override`. Not affected by FEAT-2448.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- No `config-schema.json` changes for FEAT-2448. Verified by Agent 1 and
  Agent 2: the `parallel.epic_branches` block is FEAT-2447's responsibility.
  FEAT-2448 only consumes the resolver's output via
  `_resolve_branch_targets(issue)[0]` and reads `result.epic_branch`
  downstream.
- `scripts/little_loops/templates/*.json` (9 templates: typescript,
  python-generic, javascript, java-maven, java-gradle, rust, go, dotnet,
  generic) — confirmed by Agent 1 that none currently contain
  `epic_branches` keys. Per `.ll/decisions.yaml:3822-3842`
  (ARCHITECTURE-096), FEAT-2447 stamps `epic_branches: {enabled: false}`
  explicitly into templates. **Out of scope here; FEAT-2447 / FEAT-2450
  own.**
- `scripts/little_loops/config/automation.py:172-194` — `CommandsConfig.confidence_gate`
  and `CommandsConfig.rate_limits` are the precedent for the nested
  `field(default_factory=Cls)` shape that FEAT-2447's
  `ParallelAutomationConfig.epic_branches` mirrors. **FEAT-2448 inherits; no
  change.**

### CRITICAL: Standalone Implementation Blocker

_Wiring pass added by `/ll:wire-issue`:_

Both Agent 2 (side-effect tracer) and Agent 3 (test-gap finder) flagged
`_resolve_branch_targets(issue)` as **NOT YET PRESENT** in the codebase.
Verified by Agent 1: zero matches outside `.issues/` docs
(FEAT-2447, FEAT-2448, FEAT-2449, FEAT-2450, EPIC-2451, FEAT-2339,
`.ll/decisions.yaml`).

**Implication:** FEAT-2448 cannot be implemented standalone. The
implementation either:

1. **Lands bundled with FEAT-2447** (typical sequenced child execution via
   `ll-sprint` multi-issue wave).
2. **Uses a temporary `if hasattr(self, '_resolve_branch_targets')` shim**
   that returns `(self.parallel_config.base_branch, self.parallel_config.base_branch)`
   until FEAT-2447 lands. This keeps behavior byte-for-byte identical when
   epic mode is disabled (the default) and lets FEAT-2448's tests pass.
3. **Reads `self.parallel_config.epic_branches.enabled` and `issue.parent`
   directly inside `_process_issue`** without a resolver (departs from the
   FEAT-2448 spec).

The `blocked_by: [FEAT-2447]` frontmatter (line 24) makes the dependency
explicit. **Recommended:** Option 1 (bundle with FEAT-2447). If FEAT-2448 is
picked up by `ll-auto` before FEAT-2447, fall back to Option 2 (shim) to
avoid blocking the queue.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

7. **Update `scripts/tests/test_parallel_types.py:161-359`** —
   `TestWorkerResult` class needs `epic_branch is None` default assertion
   (line 198), field round-trip coverage in 4 test methods, and matching
   `to_dict()`/`from_dict()` assertions. Follow the
   `was_blocked`/`interrupted` precedent at `types.py:89-90`. **[Agent 3
   finding — NEW 5th test file]**
8. **Update `docs/reference/API.md:3211-3235`** — Add
   `epic_branch: str | None = None` to the `WorkerResult` dataclass field
   listing, after the `interrupted: bool = False` line. Mirror the field
   declaration order from `types.py:91`. **[Agent 2 finding — direct
   FEAT-2448 wiring point]**
9. **Verify hardcoded `"parallel"` dict fixtures** — After FEAT-2447 lands,
   run `python -m pytest scripts/tests/` and update any failing fixtures in
   `conftest.py:284-296`, `test_cli.py:479-484, 1642-1647`,
   `test_cli_e2e.py:105-110`, `test_issue_workflow_integration.py:197-202`
   to include `"epic_branches": {"enabled": false}` if schema validation
   enforces it. **[Agent 3 finding — may not trigger depending on schema
   strictness]**
10. **Resolve implementation choices** (restated from existing Codebase
    Research Findings at lines 242-286 for clarity):
    - `_open_pr_for_branch()` threading: pass via
      `branch_state["epic_branch"] = result.epic_branch` (preferred per
      Agent 2) OR add a new `epic_branch` kwarg to the function signature
      at `orchestrator.py:1109-1114`.
    - `_get_changed_files()` and `_update_branch_base()` epic-mode
      threading: use option (a) instance-state dict
      `self._worker_epic_branches: dict[str, str | None]` populated in
      `_process_issue()` (preferred per Agent 2 — less invasive) OR option
      (b) add a new parameter and update the 3 callers + 3 tests.
11. **Set `issue.parent = None` explicitly** at `test_worker_pool.py:2211`
    (inside `test_process_issue_uses_feature_branch_name_when_enabled`) per
    FEAT-2339's MagicMock truthy-auto-attribute finding. The Scope item #6
    already cites this at lines 105-106; restated here as a wiring-pass
    requirement to ensure it isn't dropped.

## Cross-Module State Threading

This child carries the cross-module state threading risk flagged in
FEAT-2339's Confidence Check Notes. The chosen shape (`WorkerResult.epic_branch`
field, populated once at the same site as `branch_name`) keeps
"what the worker forked from" and "where the merge should land" as the
same string by construction — no synchronization point where merge
target can disagree with fork point.

## Codebase Research Findings

_Added by `/ll:refine-issue` — anchor drift corrections, state-threading
precision, and configuration-namespace clarifications from codebase
analysis:_

- **Anchor drift — `_process_single_merge` does not exist, and the
  two consumer sites are in different methods.** The issue cites this
  method name at `merge_coordinator.py:624` and `:875`. The actual
  methods are:
  - `_process_merge()` at `merge_coordinator.py:577` contains the
    line 624 site (`base = self.config.base_branch` for checkout,
    called from the stash-then-checkout-pre-merge flow).
  - `_handle_conflict()` at `merge_coordinator.py:808` contains the
    line 875 site (`base = self.config.base_branch` for the
    fetch+rebase retry flow).
  Both methods rebind `result = request.worker_result` at their head
  (line 586 and line 816 respectively), so `result.epic_branch` is
  in scope at both consumer sites without any signature change on
  `MergeCoordinator`. The exact `or` idiom
  `base = result.epic_branch or self.config.base_branch` is byte-for-
  byte identical to today's behavior when `epic_branch is None`.
- **Anchor drift — `worker_pool.py:334-360` range is approximate.**
  The branch-naming + worktree-setup block the issue points to is
  inside `_process_issue()`, which actually starts at
  `worker_pool.py:324`. The branch-naming block (lines 333–345) and
  the `_setup_worktree(base_branch=...)` call (lines 358–364) are
  inside this range, so the issue's 334–360 anchor is functionally
  correct but slightly shifted — refer to the `_process_issue`
  signature at line 324 for the canonical anchor.
- **State-threading precision — 12 `WorkerResult` returns in `_process_issue`.**
  Direct verification shows `_process_issue()` (lines 324–646) has
  **12 `return WorkerResult(...)` call sites** (lines 384, 398, 414,
  429, 456, 476, 519, 571, 585, 606, 619, 635), plus 1 in
  `_handle_completion` at line 302. The issue's "Populate **once** at
  the same site as `branch_name`/`worktree_path`" wording is
  misleading — the correct pattern is:
  1. **Compute** `epic_branch` **once** at the top of `_process_issue`
     (immediately after `branch_name`/`worktree_path` are assigned at
     lines 333–345), via
     `epic_branch = self._resolve_branch_targets(issue)[0]` (the fork
     point; the merge target is the same string by construction per
     Decision Rationale #1).
  2. **Pass** `epic_branch=epic_branch` as a kwarg to **all 12**
     `WorkerResult(...)` returns in `_process_issue`, and to the
     single return in `_handle_completion` (which receives
     `worker_result: WorkerResult` — the new field flows through via
     the existing param).
  This keeps "what the worker forked from" as a single source of
  truth, threaded once rather than recomputed at every consumer.
- **`_open_pr_for_branch` threading path — `WorkerResult` not in scope.**
  The function signature at `orchestrator.py:1109-1114` is
  `def _open_pr_for_branch(self, issue_id: str, branch_name: str, branch_state: dict[str, Any]) -> None`
  — it does **not** receive a `WorkerResult` object. The current
  implementation reads `self.parallel_config.base_branch` directly
  at line 1142. For the epic-mode switch to work, the caller chain
  (the worker-complete handler that invokes `_open_pr_for_branch`)
  must pass `epic_branch` into the function — either as a new
  parameter, or by storing it in `branch_state` (e.g.,
  `branch_state["epic_branch"] = result.epic_branch`) before
  invocation. The current caller should be located by searching for
  `_open_pr_for_branch(` calls and threading the value through.
  (The full PR-target decision — when to open the PR against the
  epic branch vs. the base — is FEAT-2449's scope; this child only
  switches the `--base` argument when `epic_branch` is set.)
- **`_update_branch_base()` signature — `issue_id: str`, not `IssueInfo`.**
  At `worker_pool.py:1098-1111`, the function takes
  `(self, worktree_path: Path, issue_id: str) -> tuple[bool, str]`.
  It does **not** receive an `IssueInfo` and so cannot call
  `self._resolve_branch_targets(issue)`. Two viable threading paths:
  (a) store `epic_branch` on the `WorkerPool` instance per-issue
  (e.g., `self._worker_epic_branches: dict[str, str | None]`
  populated in `_process_issue`), and look it up in
  `_update_branch_base` via `self._worker_epic_branches.get(issue_id)`;
  (b) add a third parameter to `_update_branch_base` and update the
  3 existing callers + new tests. Option (a) is less invasive but
  introduces instance state; option (b) is more explicit. The
  pattern-finder results for sibling ENH-036 (`was_blocked`) and
  `interrupted` fields should be checked for precedent on which
  shape to mirror.
- **`_get_changed_files()` epic-mode threading.** At
  `worker_pool.py:1076-1096`, the function takes
  `(self, worktree_path: Path) -> list[str]` and uses
  `self.parallel_config.base_branch` directly in the `git diff`
  command at line 1086. Same threading problem as
  `_update_branch_base` — it doesn't receive `issue` info. The
  same option (a) instance-state pattern, or option (b) extra-param
  pattern, applies. The 3 existing tests at
  `test_worker_pool.py:1714-1791` (verified
  `test_update_branch_base_uses_configured_remote` at 1714,
  `_fetch_failure_falls_back_to_local` at 1743,
  `_default_remote_is_origin` at 1774) set
  `worker_pool.parallel_config.base_branch = "main"` directly
  before calling `_update_branch_base` — the epic-mode
  counterparts can use the same fixture pattern with
  `parallel_config.epic_branches.enabled = True` plus
  `_worker_epic_branches[issue_id] = "epic/EPIC-2451-..."`.
- **WorkerResult field placement — verified pattern.** The
  `WorkerResult` dataclass at `types.py:52-135` has `was_blocked`
  at line 89 and `interrupted` at line 90, with matching rows in
  `to_dict()` (lines 92-112) and `from_dict()` (lines 114-135).
  The new `epic_branch: str | None = None` field should be added
  at line 91 (after `interrupted`), with the matching row in
  `to_dict()` after the `interrupted` row at line 111, and the
  matching `data.get("epic_branch")` row in `from_dict()` after
  `interrupted` at line 134. The pattern is identical to
  `was_blocked` and `interrupted` — both are bool defaults, but
  `epic_branch` uses `str | None = None` (None is the no-op signal
  meaning "use `base_branch`").
- **Configuration namespace difference — `self.config` vs. `self.parallel_config`.**
  The two `base = self.config.base_branch` reads in
  `merge_coordinator.py:624` and `:875` access `MergeConfig`
  (not `ParallelConfig`). The two `self.parallel_config.base_branch`
  reads in `worker_pool.py:361, 1086, 1113` and
  `orchestrator.py:1142` access `ParallelConfig`. The issue's
  Specification 3 already correctly preserves these namespaces
  (using `self.config.base_branch` in `merge_coordinator.py` and
  `self.parallel_config.base_branch` in `orchestrator.py`), so this
  is a confirmation, not a change.
- **Lazy branch creation lives in FEAT-2447, not here.** The
  `_resolve_branch_targets()` method that FEAT-2448 calls is
  defined in FEAT-2447 and is responsible for the lazy creation of
  `epic/<EPIC-ID>-<slug>` off `base_branch` on first call per
  `epic_id` (and the idempotency check on subsequent calls). This
  child just consumes the resolver's `(fork_point, merge_target)`
  tuple — no branch-creation logic is added to `worker_pool.py` or
  `merge_coordinator.py` in FEAT-2448.
- **Cross-EPIC flattening is a resolver concern, not a wiring
  concern.** Per FEAT-2339 Decision Rationale #1 and FEAT-2447's
  resolver design, the "flatten to nearest EPIC ancestor" walk
  happens inside `_resolve_branch_targets()`. FEAT-2448's wiring
  treats the resolver as a black box and just threads the returned
  fork point through `_setup_worktree` and the returned merge
  target through the consumer sites — no parent-walk logic is
  added to `worker_pool.py`, `merge_coordinator.py`, or
  `orchestrator.py`.
- **Test anchor verification — all test anchors in the issue are
  accurate.** Direct verification confirmed:
  - `test_worker_pool.py:2191` → `test_process_issue_uses_feature_branch_name_when_enabled` ✅
  - `test_worker_pool.py:1714-1791` → 3 `_update_branch_base_*` tests
    at lines 1714 (`_uses_configured_remote`), 1743
    (`_fetch_failure_falls_back_to_local`), 1774
    (`_default_remote_is_origin`) ✅
  - `test_orchestrator.py:2008-2052` → `test_on_worker_complete_feature_branch_open_pr` ✅
  - `test_subprocess_mocks.py:615` → `test_setup_worktree_with_base_branch_appends_commit_ish` ✅
  - `test_subprocess_mocks.py:838` → assertion
    `[c for c in captured_commands if "checkout" in c and config.base_branch in c]` ✅
  - `test_subprocess_mocks.py:892` → assertion
    `if cmd[:3] == ["git", "checkout", config.base_branch]:` ✅
- **`TestUpdateBranchBase` is a class, not three standalone tests.**
  The 3 existing `_update_branch_base` tests at
  `test_worker_pool.py:1714-1791` are members of class
  `TestUpdateBranchBase` (lines 1711-1794). The class name matters
  for the epic-mode counterparts: add them as additional methods
  inside the same class (e.g.,
  `test_update_branch_base_uses_epic_branch_when_enabled`,
  `test_update_branch_base_epic_mode_falls_back_to_local`,
  `test_update_branch_base_epic_mode_uses_default_origin`). All
  three existing tests share the same fixture shape — `worker_pool:
  WorkerPool`, `temp_repo_with_config: Path`,
  `captured_cmds: list[list[str]]`, and
  `with patch("subprocess.run", side_effect=mock_run)` — and assert
  on the literal full command list (e.g.,
  `["git", "rebase", "upstream/main"]`). Mirror that exact shape
  for the epic-mode counterparts.
- **`WorkerResult` field addition is a 4-edit pattern (not 3).**
  The `WorkerResult` field addition requires edits in 4 places, not
  3: (a) the field declaration with default, (b) the
  `Attributes:` docstring block (lines 55-72), (c) the `to_dict()`
  method, and (d) the `from_dict()` classmethod. The
  `Attributes:` docstring entry for `epic_branch` should be added
  after the `interrupted:` line at line 71 of `types.py`.
- **`TestWorkerResult` precedent at `test_worker_pool.py:120-149`.**
  The class `TestWorkerResult` contains
  `test_interrupted_can_be_set_true` (lines 123-135) and
  `test_interrupted_serialization` (lines 137-149) as the canonical
  test shape for any new `WorkerResult` field. The epic-branch
  equivalent adds: (a) a constructor test asserting
  `WorkerResult(..., epic_branch="epic/EPIC-2451-test")` retains
  the value, and (b) a serialization test asserting
  `to_dict()["epic_branch"] == "epic/EPIC-2451-test"` and
  `from_dict(to_dict())` round-trips the field. Both follow the
  same fixture pattern as the `interrupted` tests.
- **`IssueInfo.parent` anchor — `issue_parser.py:439`.** The
  `IssueInfo.parent` attribute that FEAT-2447's resolver walks is
  defined at `scripts/little_loops/issue_parser.py:439` (not at
  line 251 as the FEAT-2339 anchor originally cited; the
  `parent:` field was promoted during the file's evolution). The
  resolver's `current.split("-", 1)[0] == "EPIC"` check
  (per FEAT-2447) operates on this string-typed `parent` attribute.
- **Config schema — `parallel.*` block boundaries verified.** The
  `parallel` block in `config-schema.json` runs lines 305-408 and
  closes with `"additionalProperties": false` at line 408. The
  existing `base_branch` field is at lines 397-401 (with `default:
  "main"`). The new `epic_branches` block from FEAT-2447 must be
  inserted inside the `parallel` `properties` block before line
  408. This is a FEAT-2447 concern but is verified here as
  context — FEAT-2448 itself does not modify the schema.
- **Nested config precedent at `automation.py:172-194`.** The
  closest precedent for the `ParallelConfig.epic_branches` field
  composition is `CommandsConfig.confidence_gate` and
  `CommandsConfig.rate_limits` in
  `scripts/little_loops/config/automation.py:172-194`. Both use
  `field(default_factory=Cls)` for the nested field and
  `SubConfig.from_dict(data.get("sub", {}))` in the parent's
  `from_dict()` classmethod. FEAT-2447 mirrors this exact shape
  for `ParallelConfig.epic_branches`; FEAT-2448 inherits the
  result and does not need its own config plumbing.
- **`ParallelConfig.base_branch` at `types.py:386`.** The
  `ParallelConfig` dataclass declares `base_branch` at line 386,
  with `to_dict()` (line 467) and `from_dict()` (line 513) entries
  following the same pattern. FEAT-2448 does not touch
  `ParallelConfig` directly — the `epic_branches` field is added
  in FEAT-2447, and the wiring this child adds only reads
  `self.parallel_config.epic_branches.enabled` (via the resolver)
  and writes `result.epic_branch` to `WorkerResult`.

## Session Log
- `/ll:wire-issue` - 2026-07-06T23:20:17 - `f3fff147-d97f-42e2-945a-790e562c6c5b.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:21:42 - `ad8ca7f6-66d7-4f8c-ae58-3ea979d78b4d.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

## Blocks

- FEAT-2449

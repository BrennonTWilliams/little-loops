---
id: FEAT-2448
title: "per-EPIC integration branch \u2014 worker_pool + merge_coordinator wiring"
type: FEAT
priority: P3
status: done
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
- FEAT-2452
- FEAT-2453
blocked_by:
- FEAT-2447
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
completed_at: '2026-07-09T20:54:42Z'
---

# FEAT-2448: per-EPIC integration branch — worker_pool + merge_coordinator wiring

## Summary

> **Coordination container — split on 2026-07-07.**
> This issue is decomposed into two sequenced children:
> **[FEAT-2452](./P3-FEAT-2452-workerpool-and-dataclass-wiring.md)** —
> WorkerPool + `WorkerResult` dataclass wiring (broad fanout: 12-return
> kwarg threading, instance-state dict, `_get_changed_files` /
> `_update_branch_base` variants, `types.py` 4-edit pattern).
> **[FEAT-2453](./P3-FEAT-2453-downstream-consumer-read-sites.md)** —
> Downstream consumer read-sites (3 `or` substitutions at
> `merge_coordinator.py:624 / :875` and `orchestrator.py:1142`,
> plus `branch_state["epic_branch"]` mutation).
> Land **FEAT-2452 first**, then **FEAT-2453**; both must complete
> before **FEAT-2449**. See `## Decomposition` below for the
> rationale and outcome-confidence table.

Second of four sequenced children decomposed from FEAT-2339. This issue
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

## Decomposition

Decomposed into two sequenced children on 2026-07-07 via
`/ll:confidence-check` (this issue scored 74/100 outcome,
MODERATE tier). The split was driven by the **shape asymmetry**
in this issue's scope: the broad-fanout dataclass piece
(`WorkerResult` ripple + 12-return kwarg threading +
WorkerPool-side methods) sat awkwardly alongside three
clean read-site substitutions at `merge_coordinator.py:624,
:875` and `orchestrator.py:1142`.

### Children

- **[FEAT-2452](./P3-FEAT-2452-workerpool-and-dataclass-wiring.md)** —
  WorkerPool + `WorkerResult` dataclass wiring (steps 1-6 of the
  Scope section). Lands the `epic_branch` field, populates it
  once at `_process_issue` head, threads it as a kwarg to all
  12 `WorkerResult(...)` returns, and reads it back via the
  `_worker_epic_branches` instance-state dict in
  `_get_changed_files` and `_update_branch_base`. Carries the
  irreducible broad fanout — `score_change_surface = 10` is
  inherent to the dataclass change.
- **[FEAT-2453](./P3-FEAT-2453-downstream-consumer-read-sites.md)** —
  Downstream consumer read-sites. Four 1-2 line mechanical
  substitutions: two `or` idioms in `merge_coordinator.py`, the
  `branch_state["epic_branch"] = result.epic_branch` mutation
  in `orchestrator.py:1005`, and the `--base` read at
  `orchestrator.py:1142`. Ships with `outcome_confidence = 86
  → HIGH` once FEAT-2452 lands.

### Outcome Confidence Table

| Issue | A | B | C | D | Total | Tier |
|---|---|---|---|---|---|---|
| FEAT-2448 (this, unsplit) | 14 | 25 | 25 | 10 | 74 | MODERATE |
| **FEAT-2452** (WorkerPool + dataclass) | 14 | 25 | 25 | 10 | 74 | MODERATE |
| **FEAT-2453** (downstream consumers) | 18 | 25 | 25 | 18 | **86** | **HIGH** |

The aggregate risk profile is similar to the unsplit issue;
per-issue tractability jumps dramatically — the clean piece no
longer carries the broad-fanout burden.

### Execution Pattern

`blocked_by: [FEAT-2447]` is satisfied (FEAT-2447 is landed).
Land **FEAT-2452 first**, then **FEAT-2453** in the same
sprint wave. Both must complete before FEAT-2449 (orchestrator
EPIC-completion flow). The orchestrator-side end-to-end test
surface for FEAT-2449 depends on FEAT-2453's `--base` switching
having landed.

### What moved and why

| Scope item from this issue (Section 1-6) | Now lives in |
|---|---|
| §1 `WorkerResult.epic_branch` field + 4-edit pattern | FEAT-2452 step 1 |
| §2 12-return kwarg threading in `_process_issue` | FEAT-2452 step 2 |
| (new in FEAT-2452) `self._worker_epic_branches` instance-state dict | FEAT-2452 step 3 |
| §4 `_get_changed_files()` epic-mode variant | FEAT-2452 step 4 |
| §5 `_update_branch_base()` epic-mode variant | FEAT-2452 step 5 |
| §6 tests (WorkerPool-side) | FEAT-2452 step 6 |
| §3 merge_coordinator.py read-sites (2 sites) | FEAT-2453 steps 1-2 |
| §3 orchestrator.py `branch_state` mutation + `--base` | FEAT-2453 steps 3-4 |
| §6 tests (merge_coordinator, orchestrator) | FEAT-2453 step 5 |

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

### Phase 2 Research Findings — Refinement Pass (2026-07-07)

_Added by second `/ll:refine-issue` pass — codebase state has moved since
the Phase 1 pass (FEAT-2447 is now landed). Verified all anchors against
current source._

- **FEAT-2447 is fully landed — Standalone Implementation Blocker
  is OBSOLETE.** Verified at `worker_pool.py:1564-1699` and
  `types.py:305-328, 415-423, 504-509, 556`: the resolver
  `_resolve_branch_targets()` returns `(fork_point, merge_target)`
  tuple, with helpers `_find_nearest_epic_ancestor` (line 1592),
  `_build_parent_map` (line 1611), `_load_epic_slug` (line 1638),
  `_ensure_epic_branch` (line 1663), and the
  `self._epic_branches_created: set[str]` instance cache at
  `worker_pool.py:189-190`. The schema block landed at
  `config-schema.json:407-433`. FEAT-2448 can now be implemented
  standalone — Options 1, 2, 3 in the existing
  `### CRITICAL: Standalone Implementation Blocker` section are no
  longer required; the resolver is callable. **The original blocker
  note (lines 309-335) is preserved verbatim per additive-only
  contract; this finding supersedes it for implementer purposes.**
- **`_setup_worktree` is a thin wrapper at
  `worker_pool.py:650-678`.** The function delegates to
  `setup_worktree()` from `little_loops.worktree_utils`,
  threading `repo_path`, `worktree_path`, `branch_name`,
  `parallel_config.worktree_copy_files`, `logger`, `git_lock`, and
  the `base_branch` kwarg through verbatim. `base_branch` is
  `Optional[str]` — `None` means "fork from HEAD" per the
  docstring at lines 654-658. The `_detect_worktree_model_via_api`
  follow-up at lines 672-678 is unrelated to base-branch wiring
  and is not in the FEAT-2448 scope. The function currently does
  not need modification for epic mode — the existing
  `base_branch=` kwarg threading is sufficient because the
  resolver returns a non-None string when epic mode is active.
- **`_get_changed_files` callers in `_process_issue`.** The
  function at `worker_pool.py:1078-1098` is called from two sites
  in `_process_issue()`: line 534 (first call, before the
  verification gate) and line 562 (after `_recover_committed_leaks`
  returns). Both call sites use the standard
  `worker_pool._get_changed_files(worktree_path)` shape — the
  epic-mode threading via either option (a) instance-state dict
  or option (b) extra-param pattern applies to both call sites.
- **`_update_branch_base` single caller is `_process_issue:602`.**
  The single call site is
  `base_updated, base_error = self._update_branch_base(worktree_path, issue.issue_id)`
  at line 602, followed by the `WorkerStage.MERGING` stage update
  at line 605 and a `WorkerResult` return at lines 608-619 when
  `base_updated` is False. Adding a third parameter (option b) only
  requires updating this one caller; the 3 existing tests in
  `TestUpdateBranchBase` use direct method invocation and would
  need parallel updates for option (b), or seed
  `worker_pool._worker_epic_branches[issue_id]` for option (a).
- **Orchestrator caller chain for `_open_pr_for_branch`.** The
  function is called once from `_on_worker_complete` at
  `orchestrator.py:1006`, inside the
  `if self.parallel_config.open_pr_for_feature_branches:` block at
  line 1005. The `branch_state` dict is constructed at lines
  980-984 as
  `{"branch_name": ..., "pushed": False, "pr_url": None}`.
  `ParallelOrchestrator.__init__` constructs `WorkerPool` and
  `MergeCoordinator` at lines 113-118 — no constructor signature
  change needed for FEAT-2448. The two viable threading paths for
  the epic-mode switch: (a) new kwarg
  `_open_pr_for_branch(self, issue_id, branch_name, branch_state, epic_branch=None)`,
  or (b) mutate `branch_state["epic_branch"] = result.epic_branch`
  at line 1005 before the call. Option (b) is preferred per the
  existing wiring-pass decision (FEAT-2448:362-365) and matches
  the existing `branch_state["pushed"] = True` mutation pattern.
- **Two `TestWorkerResult` classes exist — both need `epic_branch`
  coverage.** Phase 1 wiring-pass item 7 (FEAT-2448:235-254)
  identified only `test_parallel_types.py:161-359`. The
  pattern-finder agent also verified a compact
  `TestWorkerResult` class at `test_worker_pool.py:120-149` with
  two tests (`test_interrupted_can_be_set_true` at 123-135 and
  `test_interrupted_serialization` at 137-149) — both tests
  follow the canonical `interrupted` precedent shape and must
  receive epic-branch counterparts
  (`test_epic_branch_can_be_set` and
  `test_epic_branch_serialization`). Total `WorkerResult` test
  surface for `epic_branch` spans 4 test files (test_worker_pool.py
  at 120-149, test_parallel_types.py at 161-359, plus the existing
  test_merge_coordinator.py and test_orchestrator.py tests
  exercising `WorkerResult` construction).
- **Existing `_resolve_branch_targets` tests at
  `test_worker_pool.py:3296-3482`.** FEAT-2447's tests use the
  `mock_issue` fixture (lines 110-117) with explicit
  `mock_issue.parent = "EPIC-XXXX"` assignment (e.g., line 3334).
  These tests confirm the parent-walking behavior and serve as
  the canonical reference for the issue-side threading pattern.
  New `_process_issue` epic-mode tests can borrow the same
  fixture shape.
- **Existing `EpicBranchesConfig` and `ParallelConfig.epic_branches`
  test coverage.** `test_parallel_types.py:757-761` covers
  `EpicBranchesConfig` defaults; `test_parallel_types.py:1034-1051`
  covers `ParallelConfig` `to_dict`/`from_dict` round-trip with the
  new `epic_branches` block. These tests confirm FEAT-2447's
  config wiring works end-to-end. FEAT-2448 does not add new
  config tests — it inherits these as ground truth.
- **`test_cli.py` hardcoded `"parallel"` block at 1638-1642** (not
  1642-1647 as the FEAT-2447 wiring pass cited). The block ends
  at line 1642. The end-of-fixture closing brace sits at 1642, so
  any `epic_branches` addition would be inside this range.
- **`test_cli_e2e.py` block at 105-111** (not 105-110).
- **`test_issue_workflow_integration.py` block at 197-205** (not
  197-202).
- **`config-schema.json:402-406` — `parallel.remote_name` block**
  sits between `base_branch` (397-401) and the new
  `epic_branches` block (407-433). The `epic_branches` block
  closes with `additionalProperties: false` at **line 432** (not
  line 408 — that is the outer `parallel` properties close).
- **Docstring on `ParallelConfig.base_branch` at `types.py:407-412`**
  describes the BUG-2323 auto-detection fallback chain
  (`origin/HEAD` → current branch → `"main"`). The new
  `epic_branches` field at line 415-416 follows immediately after
  this docstring. No docstring conflict — both are independently
  documented.
- **`_resolve_branch_targets` exists — confirmed at
  `worker_pool.py:1564-1590`.** The resolver returns
  `(fork_point, merge_target)` — both currently the same string
  per FEAT-2339 Decision Rationale #1 (flatten to nearest).
  When `epic_branches.enabled` is False or `issue.parent` is
  None, returns `(base_branch, base_branch)` no-op. When enabled
  and an EPIC ancestor exists, returns
  `(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)` after
  `_ensure_epic_branch()` idempotent create. This confirms
  FEAT-2448 can call `epic_branch, _ = self._resolve_branch_targets(issue)`
  directly inside `_process_issue` — no shim needed.
- **`ParallelOrchestrator.__init__` constructs WorkerPool +
  MergeCoordinator at `orchestrator.py:113-118`.** Verified no
  signature changes propagate to the orchestrator for
  FEAT-2448. The `MergeCoordinator.__init__` signature at
  `merge_coordinator.py:44` similarly takes
  `(self, *, config, repo_path, git_lock, logger, ...)` — no
  `WorkerResult.epic_branch` threading needed at construction
  time because `WorkerResult` is passed at merge-request time via
  `MergeRequest.worker_result` (built at `merge_coordinator.py:119`).
- **`WorkerResult` callers in `_handle_completion` at
  `worker_pool.py:304-310`.** Phase 1 (FEAT-2448:431-433) cites
  the single `_handle_completion` return as receiving
  `worker_result: WorkerResult` parameter. Verified: the
  function takes `worker_result: WorkerResult` and returns it
  unchanged in the worker-future-failed fallback. The new
  `epic_branch` field flows through transparently — no edit
  needed at this site beyond ensuring the original
  `WorkerResult` constructed upstream in `_process_issue`
  already has `epic_branch=` populated.
- **`_open_pr_for_branch` test fixture needs args-capture
  enhancement.** The existing
  `test_on_worker_complete_feature_branch_open_pr` at
  `test_orchestrator.py:2008-2052` uses an inline
  `fake_subprocess_run` that does NOT capture args (returns
  a `CompletedProcess` per command but discards the args).
  For the FEAT-2448 wiring to assert on the actual `--base`
  value (per Phase 1 wiring-pass item 6 at FEAT-2448:118-121),
  the test needs a `captured_args: list[list[str]] = []`
  accumulator and an `args` append inside `fake_subprocess_run`.
  Pattern is the same as the `TestUpdateBranchBase` tests'
  inline `captured_cmds` list at `test_worker_pool.py:1714-1794`.
- **`MergeCoordinator` signature unchanged.** Both consumer
  sites at `_process_merge` (line 624) and `_handle_conflict`
  (line 875) receive `result = request.worker_result` at the
  method head (lines 586 and 816 respectively). The
  `or` idiom
  `base = result.epic_branch or self.config.base_branch` is
  byte-for-byte identical to today's behavior when
  `epic_branch is None` (the default for non-EPIC issues), so
  no behavioral change for the no-op case. Verified by direct
  read of both methods.

### Test Surface Summary (Phase 2 verified)

For FEAT-2448's epic-branch test coverage, the canonical test
locations and patterns are:

| Test class / file | Lines | Pattern | Status |
|---|---|---|---|
| `TestWorkerResult` (`test_worker_pool.py`) | 120-149 | 2-test compact (`test_*_can_be_set` + `test_*_serialization`) | Needs 2 epic-branch tests |
| `TestWorkerResult` (`test_parallel_types.py`) | 161-359 | 5+ test broad coverage (`test_default_values`, `test_creation_with_all_fields`, `test_to_dict`, `test_from_dict`, `test_roundtrip_serialization`) | Needs 5 epic-branch updates |
| `TestUpdateBranchBase` (`test_worker_pool.py`) | 1711-1794 | 3-test inline-captured-cmds class | Needs 3 epic-mode counterparts |
| `test_process_issue_uses_feature_branch_name_when_enabled` (`test_worker_pool.py`) | 2191-2236 | Single-process-issue integration test | Needs `issue.parent = None` (Phase 1, line 105-106) |
| `test_setup_worktree_with_base_branch_appends_commit_ish` (`test_subprocess_mocks.py`) | 615-663 | Inline tempdir + captured_commands | Needs epic-branch variant |
| `test_process_merge_uses_merge_request` (`test_subprocess_mocks.py`) | 801-844 | Mock run + checkout assertion at 838 | Needs epic-branch variant |
| `test_restash_after_pull_with_local_changes` (`test_subprocess_mocks.py`) | 846-918 | Mock run + command-prefix check at 892 | Needs epic-branch variant |
| `test_on_worker_complete_feature_branch_open_pr` (`test_orchestrator.py`) | 2008-2052 | Fake subprocess without args capture | Needs args capture + `--base` assertion |

## Wiring Pass Round 2 — 2026-07-07

_Added by second `/ll:wire-issue` pass — three parallel agents re-traced the
wiring surface after FEAT-2447 landed and the Phase 2 research pass found new
codebase state. Anchors verified against current source (2026-07-07)._

### Critical: ENH-2492 SQLite Schema Coordination

_Wiring pass added by `/ll:wire-issue`:_

The `WorkerResult.to_dict()` shape becomes **load-bearing for SQLite round-trip**
when ENH-2492 lands (proposed SQLite table `orchestration_runs` will store per-worker
results per issue). The proposed DDL at
`.issues/enhancements/P2-ENH-2492-capture-orchestration-run-outcomes-into-history-db.md:274-292`
**does not include an `epic_branch` column** — only `branch` at line 287:

```sql
CREATE TABLE IF NOT EXISTS orchestration_runs (
    ...
    branch TEXT,                    -- line 287 (per-worker branch_name)
    ...
);
```

If ENH-2492 lands BEFORE FEAT-2448, the orchestrator's per-worker flush site
(`scripts/little_loops/parallel/orchestrator.py:_run_issue`) will silently drop
`result.epic_branch` when calling `record_orchestration_run()` because the
function signature at ENH-2492:301-303 does not expose an `epic_branch` kwarg.

**Two coordination options:**

1. **Sequenced landing** — land FEAT-2448 first, then update ENH-2492's DDL +
   `record_orchestration_run()` signature to include `epic_branch` (mirroring
   `branch`). Add a follow-on coordination note to ENH-2492's Acceptance
   Criteria referencing FEAT-2448.
2. **Symmetric addition now** — when FEAT-2448 lands, also add `epic_branch` to
   ENH-2492's schema migration as part of the same PR (off-FEAT-2448 path but
   prevents the silent-drop regression).

**[Agent 2 finding — CRITICAL downstream coordination miss; FEAT-2448's
implementation is correct but the persistence layer needs a paired update.]**

### Critical: `site/` HTML Files Embed `WorkerResult` Listing

_Wiring pass added by `/ll:wire-issue`:_

The `site/` directory contains git-tracked rendered HTML that mirrors the
source docs. Updates to `docs/reference/API.md:3211-3235` do **not** auto-
regenerate the HTML. The implementer must either regenerate the doc site or
manually mirror the new `epic_branch: str | None = None` row in the HTML:

- `site/reference/API/index.html:11556-11634` — `<h3 id="workerresult">WorkerResult</h3>`
  block with the dataclass field listing at lines 11558-11576 (the FEAT-2448
  wiring point).
- `site/reference/API/index.html:11247-11251` — code example using `WorkerResult`.
- `site/reference/API/index.html:11420` — table cell "Generic handling via
  WorkerResult flags" (no field edit, but the surrounding dataclass signature
  reference must stay in sync).
- `site/reference/API/index.html:12302` — re-export block listing `WorkerResult`
  in `__all__`.
- `site/ARCHITECTURE/index.html:2282, 2289` — sequence diagram arrows labelled
  `Pool: WorkerResult` (no field edit, but the dataclass shape reference must
  stay in sync).
- `site/development/MERGE-COORDINATOR/index.html:2263, 2537` — `worker_result`
  in code examples.

If the doc-site generator (`ll-artifact` or equivalent) is run, these HTML
files will auto-update. If not, the implementer needs to manually patch the
dataclass listing at `site/reference/API/index.html:11558-11576` to add the
`epic_branch` row after the `interrupted` row, matching the source-doc
ordering.

**[Agent 2 finding — site regeneration is conventional, but worth flagging so
the implementer doesn't ship a stale published site.]**

### ARCHITECTURE-095 Decision Anchor — DO NOT Make `prune_merged_feature_branches` Epic-Aware

_Wiring pass added by `/ll:wire-issue`:_

The implementer reading only this issue may be tempted to add epic-awareness to
`prune_merged_feature_branches()` at `worker_pool.py:1772-1790` or to the CLI
mode at `cli/parallel.py:267-287`. The decision rule explicitly **forbids** this
(cited but not anchored in the prior wiring pass). Anchored at
`.ll/decisions.yaml:3803-3810` (ARCHITECTURE-095):

> "Branch-prefix cleanup-gate ownership: no changes to the three existing gates
> (`_is_ll_branch()`, `_cleanup_worktree()`'s `parallel/` check,
> `prune_merged_feature_branches()`'s `feature/` check); epic/* lifecycle is
> owned exclusively by the new `delete_epic_branch()` step."

The new `delete_epic_branch()` step is **FEAT-2449's** responsibility. FEAT-2448
must NOT touch any of the three existing cleanup gates. Surface this in the
implementation PR description so a reviewer catching a stray `if epic_branch:`
in `prune_merged_feature_branches` knows it's intentional to omit.

**[Agent 2 finding — decision anchor missed by prior wiring pass; high-value
context for implementer + reviewer.]**

### `MergeRequest.to_dict()` Ripple Effect

_Wiring pass added by `/ll:wire-issue`:_

`scripts/little_loops/parallel/types.py:217` directly nests `WorkerResult.to_dict()`:

```python
"worker_result": self.worker_result.to_dict(),
```

The `MergeRequest` shape is part of the JSON-serializable contract and is
re-exported from `scripts/little_loops/parallel/__init__.py:41`. Adding
`epic_branch` to `WorkerResult.to_dict()` will surface as a new
`worker_result.epic_branch` key in any `MergeRequest.to_dict()` consumer.

**Verified safe today:** Existing tests at `test_parallel_types.py:418-468` use
the `sample_worker_result` fixture and only assert
`result["worker_result"]["issue_id"] == "BUG-001"` (field-level, not strict-
shape). No test asserts on the literal full `MergeRequest.to_dict()` shape.

**Future risk:** Any future strict-contract test (e.g., snapshot test of
`MergeRequest.to_dict()`) will need to include the new `worker_result.epic_branch`
key. Worth noting in the test-design pattern for follow-on work.

**[Agent 2 finding — not breaking, but a ripple to record so future test
authors know the new key exists.]**

### Mock-Patch Test Files (Verification Only, No Code Change)

_Wiring pass added by `/ll:wire-issue`:_

Three test files monkey-patch `ParallelOrchestrator` / `WorkerPool` for CLI /
sprint integration testing. **No FEAT-2448 code change required**, but they
should be re-run after FEAT-2448 lands to verify the epic-branch threading
doesn't break their assertions:

- `scripts/tests/test_parallel_cli.py:59, 85, 120, 150, 188, 210, 234, 269` —
  patches `little_loops.parallel.ParallelOrchestrator` and
  `little_loops.parallel.WorkerPool`.
- `scripts/tests/test_sprint.py:2282, 2292, 2317` — imports `ParallelConfig`;
  patches `little_loops.cli.sprint.run.ParallelOrchestrator`.
- `scripts/tests/test_sprint_integration.py:296, 323, 400, 420, 471, 492, 538,
  656, 929, 1005, 1072, 1137, 1407` — extensive `ParallelOrchestrator`
  patching across sprint integration scenarios.

These tests use mocks at the class boundary, so constructor signature changes
(there are none) wouldn't affect them; only behavioral changes would. The
epic-branch `WorkerResult` field is opaque to mocks at this layer, but verify
the full suite passes after FEAT-2448 lands per the Acceptance Criterion
"`python -m pytest scripts/tests/` exits 0".

**[Agent 1 finding — verification surface, not new wiring.]**

### FEAT-2447 Verification Tests (Re-Run After FEAT-2448 Lands)

_Wiring pass added by `/ll:wire-issue`:_

Two tests verify FEAT-2447's `epic_branches` config wiring landed correctly.
They are FEAT-2447's test surface, but they implicitly verify the config
plumbing that FEAT-2448 reads via `_resolve_branch_targets`. Run them after
FEAT-2448 lands to confirm no regression:

- `scripts/tests/test_init_core.py:2630-2659` —
  `test_all_project_type_templates_have_epic_branches_stamp` — verifies all 9
  templates have `epic_branches: {enabled: false}`.
- `scripts/tests/test_config_schema.py:686-702` —
  `test_parallel_epic_branches_in_schema` — verifies `config-schema.json`
  declares `parallel.epic_branches`.

**[Agent 1 finding — not new wiring, but verification surface to include in
the post-implementation test run.]**

### Second `_open_pr_for_branch` Test — Args-Capture Enhancement

_Wiring pass added by `/ll:wire-issue`:_

The Phase 2 research pass (line 750-760) flagged `test_orchestrator.py:2008-2052`
(`test_on_worker_complete_feature_branch_open_pr`) as needing a `captured_args`
accumulator to assert on the actual `--base` value. **A second test at
`test_orchestrator.py:2260-2321` (`test_on_worker_complete_feature_branch_pr_url_idempotency`)
has the same fake_subprocess_run shape and is a natural second place to assert
on the `--base` value.** The idempotency test preserves an existing `pr_url`;
adding a `assert base == "epic/EPIC-XXXX-..."` assertion on the `gh pr create`
call would catch a regression where epic mode accidentally re-targets an
existing PR's base branch.

The gh-missing test at `test_orchestrator.py:2090-2123` (`test_on_worker_complete_feature_branch_gh_missing`)
does **not** exercise `--base` (gh is missing before `pr create` is reached),
so args-capture there is lower priority — listed as optional.

**Recommended:** Add args-capture to both the open-pr test (2008-2052) and
the idempotency test (2260-2321). Same `captured_args: list[list[str]] = []`
accumulator pattern, same `args` append inside `fake_subprocess_run`.

**[Agent 3 finding — Phase 2 missed this; same enhancement opportunity.]**

### Anchor Drift Corrections

_Wiring pass added by `/ll:wire-issue`:_

Verified against current source (2026-07-07). Most anchors are accurate; the
following minor drifts were found (all within the existing wiring pass's
expected tolerance, but worth recording):

| Cited anchor | Current line | Delta | Impact |
|---|---|---|---|
| `worker_pool.py:324` (`_process_issue` def) | 326 | +2 | None — function-by-name lookup |
| `worker_pool.py:1098` (`_update_branch_base` def) | 1100 | +2 | None — function-by-name lookup |
| `test_config.py:850` (`test_create_parallel_config`) | 893 | +43 | Verify reference still accurate |
| `test_config.py:2324` (`test_from_dict_parallel_override`) | 2423 | +99 | Verify reference still accurate |
| `test_cli.py:1642-1647` (second `"parallel"` block) | 1638-1642 | -4 to -5 | Phase 2 anchor is correct |
| `test_cli_e2e.py:105-110` | 105-111 | +1 | Phase 2 anchor is correct |
| `test_issue_workflow_integration.py:197-202` | 197-205 | +3 | Phase 2 anchor is correct |

The `test_config.py:850` and `:2324` citations appear in the prior wiring
pass's "Test files that don't need updating (verified)" section (lines 284-285)
as references to existing tests that should keep passing — the line drift does
not change the conclusion (those tests are unaffected by FEAT-2448), but the
specific line numbers cited are stale.

**All implementation-file anchors (`worker_pool.py:190, 290, 326, 602, 650,
1078, 1100, 1564, 1592, 1611, 1638, 1663`; `merge_coordinator.py:577, 624,
808, 875`; `orchestrator.py:914, 1006, 1109, 1142`; `types.py:52, 89-90, 91
[empty], 306, 332, 416, 504-509, 556`; `config/core.py:38-39, 439, 510, 513,
528-529`; `config/automation.py:40, 54, 91, 127`; `config-schema.json:407-433`)
verified accurate.**

**[Agent 1 finding — minor drift, low priority but worth recording so the
implementer doesn't chase stale line numbers.]**

### Internal Sibling Import Lines

_Wiring pass added by `/ll:wire-issue`:_

Three import lines that were not anchored in the prior wiring pass (the files
are in the "4 implementation files" scope, but the specific import statements
that pull in `WorkerResult` / `ParallelConfig` are listed here for the
implementer's reference):

- `scripts/little_loops/parallel/orchestrator.py:30` — imports from `parallel.types`
- `scripts/little_loops/parallel/merge_coordinator.py:18-23` — imports
  `MergeRequest`, `MergeStatus`, `ParallelConfig`, `WorkerResult`
- `scripts/little_loops/parallel/worker_pool.py:26` — imports `ParallelConfig`,
  `WorkerResult`, `WorkerStage`

No code change required — these imports are by name and the new
`WorkerResult.epic_branch` field flows through transparently. Anchored here
so the implementer can find them if a stale-lint warning fires.

**[Agent 1 finding — anchor completeness, not new wiring.]**

### Confirmed Non-Breakage — All `WorkerResult(...)` Constructions Use Kwargs

_Wiring pass added by `/ll:wire-issue`:_

**All 40+ `WorkerResult(...)` constructions across the test suite use kwargs
only** (no positional args). Verified at:

- `test_parallel_types.py:65, 167, 181, 203, 248, 273, 293, 307, 324` (9 sites)
- `test_worker_pool.py:125, 139, 408, 428, 452, 483, 559, 586` (8 sites)
- `test_subprocess_mocks.py:817, 862` (2 sites)
- `test_merge_coordinator.py:702, 735, 773, 815, 902, 1089, 1177, 1224, 1291,
  1350, 1450, 1551, 1575, 1687, 1768, 2150, 2350` (17 sites)
- `test_orchestrator.py:1670, 1694, 1714, 1733, 1760, 1786, 1810, 1832, 1873,
  1904, 1926, 1947, 1977, 2019, 2063, 2099, 2214, 2246, 2305, 2468, 2551, 2583,
  2602, 2621, 3059, 3224, 3347, 3375, 3398, 3417, 3629, 3756, 3888, 3907,
  3926, 3945, 3965` (37 sites)

**No test asserts on a literal full `WorkerResult.to_dict()` dict** (no `==`
against a complete expected dict). The single closest pattern in
`test_parallel_types.py:235-244` only asserts individual fields. Adding
`epic_branch` to the dict output is **safe** for the existing test suite.

**No test will break from the `WorkerResult.epic_branch` field addition alone.**
The `was_blocked` (ENH-036) and `interrupted` field additions are the
precedent — each was a no-op on existing tests, and only the new tests
assert on the new key. Same shape applies for `epic_branch`.

**[Agent 3 finding — high-value confirmation; the implementer can proceed with
confidence that no existing test will break from the dataclass change.]**

### Follow-On: `IssueProcessingResult` Symmetric Field (OUT OF SCOPE for FEAT-2448)

_Wiring pass added by `/ll:wire-issue`:_

`IssueProcessingResult` at `scripts/little_loops/issue_manager.py:545-557`
mirrors the `WorkerResult.was_blocked` / `interrupted` pattern with its own
`was_closed: bool = False, was_blocked: bool = False, failure_reason: str = ""`
fields. It is used by `ll-auto` and sprint sequential-retry.

**It is NOT on FEAT-2448's critical path:**

- `_process_issue` in `WorkerPool` produces `WorkerResult`, not
  `IssueProcessingResult` (verified at `worker_pool.py:326-644`).
- `merge_coordinator.py` consumes `WorkerResult` only (via `MergeRequest`).
- `_run_issue_with_wall_clock_timeout` at `cli/sprint/run.py:44-88` returns
  `IssueProcessingResult` for the wall-clock-timeout path (out of FEAT-2448
  scope per the issue's "Out of Scope" line 131).

If FEAT-2449 or FEAT-2450 extend the in-place path with epic-branch awareness,
this dataclass will need an analogous `epic_branch: str | None = None` field.
Flagged here as a follow-on consideration.

**[Agent 2 finding — out of scope for FEAT-2448; recorded so the implementer
knows not to add it here.]**

### Summary of Round 2 Additions

| Category | Count | Action |
|---|---|---|
| Critical downstream coordination (ENH-2492 schema) | 1 | Coordinate with ENH-2492 implementation |
| Published site HTML update | 6 files | Regenerate `site/` or manual patch |
| Decision-anchor citation (ARCHITECTURE-095) | 1 | Cite in PR description |
| Ripple-effect documentation | 1 | Recorded for future test authors |
| Mock-patch test files (verification) | 3 files | Re-run after FEAT-2448 lands |
| FEAT-2447 verification tests | 2 files | Re-run after FEAT-2448 lands |
| Test enhancement (args-capture) | +1 test | Add to `_open_pr_for_branch` test surface |
| Anchor drift corrections | 7 anchors | Recorded, low priority |
| Internal sibling imports | 3 lines | Recorded for implementer reference |
| Non-breakage confirmation | 73+ `WorkerResult(...)` sites | Confidence-building |
| Follow-on consideration (out of scope) | 1 | Flag for FEAT-2449 / FEAT-2450 |

## Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

Two orthogonal epic-branch threading choices carried expressed preferences
across the refinement and wiring passes but were never locked into a single
callout. This section formalizes both so the implementer does not re-litigate
them. (The earlier "Standalone Implementation Blocker" options 1/2/3 are not
included here — they are OBSOLETE now that FEAT-2447 has landed and the
resolver is callable; see the Phase 2 finding at lines 609–623.)

### Decision 1 — `_open_pr_for_branch()` epic-branch threading

**Selected**: Option (b) — mutate `branch_state["epic_branch"] = result.epic_branch`
at the `_on_worker_complete` call site (`orchestrator.py:1005`) before invoking
`_open_pr_for_branch()`; read `--base` from `branch_state.get("epic_branch") or
self.parallel_config.base_branch` at `orchestrator.py:1142`.

**Rejected**: Option (a) — add a new `epic_branch=None` kwarg to the
`_open_pr_for_branch(self, issue_id, branch_name, branch_state)` signature.

**Reasoning**: `branch_state` is the existing carrier for cross-call worker
state; the codebase already mutates it in place (`branch_state["pushed"] = True`),
so routing `epic_branch` the same way matches the established pattern and avoids
a signature change on `_open_pr_for_branch`. Confirmed preferred per Agent 2 and
the Phase 2 research (lines 665–670).

### Decision 2 — `_get_changed_files()` / `_update_branch_base()` epic-branch threading

**Selected**: Option (a) — store per-issue epic branch on the `WorkerPool`
instance via `self._worker_epic_branches: dict[str, str | None]`, populated once
in `_process_issue()`, and look it up in `_get_changed_files()` and
`_update_branch_base()` via `self._worker_epic_branches.get(issue_id)`.

**Rejected**: Option (b) — add a new parameter to both functions and update the
3 existing callers + their tests.

**Reasoning**: Neither `_get_changed_files(self, worktree_path)` nor
`_update_branch_base(self, worktree_path, issue_id)` receives `IssueInfo`, so
they cannot call `_resolve_branch_targets(issue)` directly. The instance-state
dict is the less-invasive threading path (no signature churn across the 3
callers and their inline-captured-cmds tests) and keeps the fork/merge branch a
single source of truth computed once at the `_process_issue` head. Confirmed
preferred per Agent 2 (lines 368–370, 457–465).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- Wide but bounded file surface: 4 implementation + 4 test files modified; ~12 internal `WorkerResult(...)` return sites in `_process_issue` must thread the new kwarg; 6 `site/` HTML files need regeneration or manual patch to mirror the `WorkerResult` field addition in published docs.
- Cross-module state threading risk: `WorkerPool` → `MergeCoordinator` handoff requires kwarg consistency across all `WorkerResult` construction sites — the typed-field shape (populated once at `_process_issue` head, read downstream via `result.epic_branch or self.config.base_branch`) eliminates fork/merge divergence by construction but demands the 12-return kwarg discipline.
- Downstream ENH-2492 SQLite coordination: the proposed `orchestration_runs` schema at ENH-2492:274-292 does not yet declare an `epic_branch` column; if ENH-2492 lands before FEAT-2448, the orchestrator's per-worker flush site will silently drop `result.epic_branch` when calling `record_orchestration_run()`. Sequence the landings or extend ENH-2492's DDL as a paired PR.
- `site/` doc regeneration: `site/reference/API/index.html:11556-11634` (WorkerResult dataclass listing) must mirror the `epic_branch: str | None = None` row; either regenerate via `ll-artifact` or manual-patch the published site.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Cross-module state threading: 12 `WorkerResult(...)` return sites in `_process_issue` must receive the new `epic_branch=` kwarg uniformly; failure to thread at any site would silently fall back to `base_branch` in downstream consumers (`merge_coordinator`, `orchestrator`). Mitigate via explicit args-capture tests in `TestUpdateBranchBase` (`test_worker_pool.py:1711-1794`) and the new orchestrator args-capture test.
- Downstream ENH-2492 SQLite coordination: the proposed `orchestration_runs` schema at ENH-2492:274-292 does not yet declare an `epic_branch` column; if ENH-2492 lands before FEAT-2448, `record_orchestration_run()` will silently drop the field. Sequence the landings or extend ENH-2492's DDL as a paired PR.
- Published site HTML updates: `site/reference/API/index.html:11556-11634` (WorkerResult dataclass listing) must mirror the new field; 5 additional `site/` HTML pages reference WorkerResult shape and need regeneration via `ll-artifact` or manual patch.
- Two `TestWorkerResult` classes require parallel updates: `test_worker_pool.py:120-149` (compact 2-test class) and `test_parallel_types.py:161-359` (broad 5+ test class) both need `epic_branch` field updates; missing either location breaks round-trip serialization coverage.

## Session Log
- `/ll:refine-issue` - 2026-07-09T20:47:24 - `a20618f0-ba1b-45b7-a585-3fe9e0f3b21c.jsonl`
- `/ll:confidence-check` - 2026-07-07T19:55:00 - `51846f72-c135-4aae-98df-cfb6f2d84afe.jsonl`
- `/ll:decide-issue` - 2026-07-07T16:50:34 - `c4211e5f-e844-40e5-b3a9-7fd3a3605a2b.jsonl`
- `/ll:confidence-check` - 2026-07-07T<time>TBD - `69f38caf-6f0f-4b3d-8e25-94fe51f2fc37.jsonl`
- `/ll:wire-issue` - 2026-07-07T16:39:15 - `9d6a4cb1-d0a9-4055-9756-6b047ca62f08.jsonl`
- `/ll:wire-issue` - 2026-07-07T<time>TBD - `82c7969d-268c-405c-871c-89861eb8d1cd.jsonl`
- `/ll:refine-issue` - 2026-07-07T15:26:46 - `82c7969d-268c-405c-871c-89861eb8d1cd.jsonl`
- `/ll:wire-issue` - 2026-07-06T23:20:17 - `f3fff147-d97f-42e2-945a-790e562c6c5b.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:21:42 - `ad8ca7f6-66d7-4f8c-ae58-3ea979d78b4d.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`

## Implementation Status — Refine Pass (2026-07-09)

_Added by `/ll:refine-issue --auto` — codebase verification against current
source. Additive only; supersedes nothing above._

**All six scope items are verified LANDED in current source.** This
coordination container's full scope shipped via its two `status: done`
children ([FEAT-2452](./P3-FEAT-2452-workerpool-and-dataclass-wiring.md),
[FEAT-2453](./P3-FEAT-2453-downstream-consumer-read-sites.md)). Direct
grep verification (2026-07-09):

| Scope item | Landed anchor (current source) |
|---|---|
| §1 fork point → `_setup_worktree(base_branch=…)` | `worker_pool.py:382` (`base_branch=epic_branch`) |
| §2 `WorkerResult.epic_branch` field + 4-edit pattern | `types.py:72` (docstring), `:94` (field), `:116` (`to_dict`), `:140` (`from_dict`) |
| §2 `epic_branch` computed once + threaded to all returns | `worker_pool.py:360-364` (compute), `:409/:424/:441/:457/:485/:506/:550/:603/:618/:640/:654` (12 return-site kwargs) |
| §2 instance-state dict (Decision 2, option a) | `worker_pool.py:194` (`self._worker_epic_branches`), populated at `:364` |
| §3 merge_coordinator `or` idiom (2 sites) | `merge_coordinator.py:626` (`_process_merge`), `:880` (`_handle_conflict`) |
| §3 orchestrator `branch_state` mutation + `--base` read (Decision 1, option b) | `orchestrator.py:1009` (mutation), `:1146` (read) |
| §4/§5 `_get_changed_files` / `_update_branch_base` epic-mode | resolver cache `_epic_branches_created` at `worker_pool.py:190`; `_resolve_branch_targets` callable (FEAT-2447 landed) |

**No implementation work remains.** The `_resolve_branch_targets` resolver
(FEAT-2447) is landed and callable, so the "Standalone Implementation
Blocker" section (lines 390-416) is OBSOLETE (already noted in the Phase 2
finding). The two orthogonal threading decisions in `## Decision Rationale`
both match what shipped: Decision 1 → `branch_state["epic_branch"]`
mutation (orchestrator.py:1009), Decision 2 → `_worker_epic_branches`
instance dict (worker_pool.py:194).

**Recommended next step:** FEAT-2448 is a fully-implemented coordination
container. Close it as `done` (its scope is delivered via FEAT-2452 +
FEAT-2453) rather than sending it to `/ll:manage-issue` — there is nothing
left to implement. Outstanding *coordination* items (ENH-2492 SQLite
`epic_branch` column, `site/` HTML regeneration) are downstream of this
issue's code scope and tracked in their own sections above.

## Blocks

- FEAT-2449

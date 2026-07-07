---
id: FEAT-2447
title: per-EPIC integration branch — config schema, dataclasses, resolver, and serialization
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
- config
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2448
- FEAT-2449
- FEAT-2450
decision_needed: false
confidence_score: 95
outcome_confidence: 60
score_complexity: 6
score_test_coverage: 18
score_ambiguity: 6
score_change_surface: 0
---

# FEAT-2447: per-EPIC integration branch — config schema, dataclasses, resolver, and serialization

## Summary

First of four sequenced children decomposed from FEAT-2339. This child
introduces the **config surface** (schema entry, dataclass, automation
mirror, `BRConfig` passthrough) and the **epic-branch resolver** that
maps an `IssueInfo` to a `(fork_point, merge_target)` pair. No
worker_pool, merge_coordinator, orchestrator, CLI, TUI, or template
changes — those land in FEAT-2448 / FEAT-2449 / FEAT-2450.

Children of one EPIC share a single integration branch
`epic/<EPIC-ID>-<slug>` (fork point **and** merge target — same string
by construction, per Decision Rationale #1 in FEAT-2339: "flatten to
nearest EPIC ancestor"). Standalone (parentless) issues retain today's
behavior unchanged. Default OFF.

## Current Behavior

When `ll-parallel` or `ll-sprint` processes multiple children of a single
EPIC, each child issue creates an independent worker worktree that:

1. **Branches** off `parallel.base_branch` directly (typically `main`).
2. **Merges** its worktree changes back to `parallel.base_branch` on
   completion.

For a 4-child EPIC this produces four separate merge commits on the base
branch with no intermediate integration surface — there is no way to
inspect the in-progress EPIC as a coherent unit before its pieces land
on `main`.

The existing config schema (`config-schema.json` `parallel.*`) has no
epic-branch concept. `ParallelConfig`, `ParallelAutomationConfig`, and
`BRConfig` round-trip only flat per-worker settings (max_workers,
base_branch, host_cli, auto_resume, learning_test_gate). `WorkerPool`
has no notion of a parent EPIC at branch-creation time, and
`merge_coordinator.py` resolves merge targets from per-worker worktrees
only.

## Expected Behavior

When `parallel.epic_branches.enabled=true` and an issue has a parent EPIC:

- All children of that EPIC share a single integration branch
  `epic/<EPIC-ID>-<slug>` (fork point **and** merge target — same string
  by construction per Decision Rationale #1 in FEAT-2339: "flatten to
  nearest EPIC ancestor").
- For nested EPICs, children flatten to the **nearest** EPIC ancestor's
  branch (a grandchild of EPIC-A through sub-EPIC-B uses EPIC-B's
  branch, not EPIC-A's).
- The branch is created lazily off `base_branch` on first call per
  `epic_id`; subsequent calls are idempotent (skip if the branch
  exists locally or on remote).
- Default behavior is **OFF** (`enabled: false`) and parentless issues
  fall back to today's `(base_branch, base_branch)` no-op return, so
  existing `merge_coordinator.py` consumer sites remain unchanged.

No public API changes outside the new `EpicBranchesConfig` dataclass and
the new `WorkerPool._resolve_branch_targets()` private method. No new
CLI flags, no TUI changes, no template changes (all deferred to
FEAT-2448/2449/2450).

## Motivation

- **Coherent EPIC review surface**: A 4-child EPIC today produces 4
  independent merge commits on the base branch with no intermediate
  branch to inspect. An EPIC integration branch gives reviewers one
  branch/PR to review per EPIC rather than 4 unrelated commits.
- **Safer partial-failure recovery**: If the 3rd child of an EPIC
  fails, the EPIC branch carries the first 2 children's work and can
  be merged, branched from, or rebased without losing their progress
  to ephemeral worktrees.
- **Sprint/PR granularity matches epic granularity**: Today
  `ll-sprint`'s "one PR per issue" rule forces reviewers to mentally
  assemble an EPIC from N sibling PRs; the EPIC branch realigns that
  boundary.
- **Foundation for future automation**: A stable EPIC branch is the
  prerequisite for in-place progress checks, EPIC-completion merge
  coordination (FEAT-2449), and rev-list deltas in the orchestrator.

Trade-off accepted: default OFF keeps the change fully opt-in; no
existing user behavior changes until `epic_branches.enabled=true` is
explicitly set.

## Use Case

**Who**: A project maintainer running `ll-parallel` (or `ll-sprint`)
against a multi-child EPIC.

**Context**: They have an EPIC with 4 children (FEAT-2447, FEAT-2448,
FEAT-2449, FEAT-2450) decomposed from FEAT-2339. They want all 4 to
land on a single integration branch so they can review the EPIC's
progress in one place before merging to `main`, instead of four
scattered merge commits.

**Goal**: Coalesce the EPIC's work onto
`epic/EPIC-2451-per-epic-integration-branch-strategy` so the
integration surface is one branch, one PR, one merge.

**Outcome**: Each child worker worktree branches off
`epic/EPIC-2451-...` instead of `main`, and merges back to
`epic/EPIC-2451-...` on completion. After the last child finishes, the
EPIC branch is itself merged to `main` (FEAT-2449).

**Setup**: Set `parallel.epic_branches.enabled: true` in
`.ll/ll-config.json` (default OFF preserves today's behavior).

## Proposed Solution

Build the **foundation only** (no `worker_pool._setup_worktree()`
wiring, no `merge_coordinator` consumption, no CLI/TUI surface —
those land in FEAT-2448/2449/2450):

1. Add `parallel.epic_branches` block to `config-schema.json` (4
   sub-keys: `enabled`, `prefix`, `merge_to_base_on_complete`,
   `open_pr`).
2. Add `EpicBranchesConfig` dataclass to
   `scripts/little_loops/parallel/types.py`, mirror in
   `ParallelAutomationConfig`, wire keyword passthrough in
   `BRConfig.create_parallel_config()` and serialization in
   `BRConfig.to_dict()`.
3. Export `EpicBranchesConfig` from
   `scripts/little_loops/parallel/__init__.py` (`__all__`).
4. Add `WorkerPool._resolve_branch_targets(issue) -> tuple[str, str]`
   private method that returns `(base_branch, base_branch)` for
   parentless or epic-off cases, and
   `(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)` otherwise. Uses
   `IssueInfo.parent` and depth-aware nearest-EPIC-ancestor resolution
   (cycle-guarded, modeled on the shape of `_issue_descends_to()` in
   `scripts/little_loops/issue_progress.py:67-80`).

See **Scope** below for the full 5-item implementation breakdown and
**Files Touched** for the 8-file change list. The **API/Interface**
section documents the resulting public-surface additions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — anchor drift and pattern corrections from codebase analysis:_

- **Anchor drift — `commands.py` does not exist.** This issue cites
  `ConfidenceGateConfig` as living in
  `scripts/little_loops/config/commands.py`. That file does not exist.
  `ConfidenceGateConfig` is actually declared in
  `scripts/little_loops/config/automation.py` at line 103 (with
  `from_dict` at line 111). `CommandsConfig` (which composes it as a
  field) also lives there. The new `EpicBranchesConfig` should follow
  the pattern at `automation.py:103-119`, not in a non-existent
  `commands.py`.
- **Anchor drift — `BRConfig.create_parallel_config()` line.** The
  issue says "around line 496". The actual signature starts at line
  413; the `ParallelConfig(...)` constructor body runs lines 461–507.
  The natural insertion point for `epic_branches=self._parallel.epic_branches`
  is the `feature_branches`/`base_branch` cluster around lines 488–506.
- **Anchor drift — `BRConfig.to_dict()` parallel block.** The issue
  cites lines 555–574; the actual `parallel` dict literal runs lines
  557–576 (off by 2 lines).
- **Anchor drift — `test_to_dict_parallel_schema_aligned_keys` line.**
  The issue cites lines 776–797; the test is at line 750 (ends ~772).
  Lines 776–797 are actually `test_to_dict_confidence_gate_schema_aligned_keys`
  (the precedent for the new assertion).
- **Anchor drift — `test_roundtrip_serialization` constructor block.**
  The issue cites 1017–1059; the actual constructor call runs
  lines 998–1028 and assertions run lines 1030–1059.
- **Better pattern match discovered.** The issue models the resolver's
  nearest-EPIC-ancestor walk on `_issue_descends_to()` in
  `scripts/little_loops/issue_progress.py:67-80`, which returns a
  *boolean*. A closer precedent already exists:
  `_find_epic_ancestor()` in
  `scripts/little_loops/cli/issues/list_cmd.py:195-203` walks the
  same parent chain with the same cycle-guard but **returns the
  matching ancestor's ID** (`current.split("-", 1)[0] == "EPIC"` →
  `return current`). The new `_resolve_branch_targets()` should
  mirror this exact shape — it already returns the ID rather than a
  boolean.
- **`ParallelConfig` has no existing nested-dataclass field** (only
  flat fields and lists). The closest precedent for nested composition
  is `CommandsConfig.confidence_gate` /
  `CommandsConfig.rate_limits` in `automation.py:172-194`, using
  `field(default_factory=Cls)` and `SubConfig.from_dict(data.get("sub", {}))`
  in the parent's `from_dict()`.
- **`test_roundtrip_serialization` precedent for nested config.** No
  existing nested-dataclass field in `ParallelConfig`, so the new test
  assertion can model on
  `test_to_dict_confidence_gate_schema_aligned_keys`
  (`scripts/tests/test_config.py:773`) — a flat key check on a
  parent-dict that contains a nested sub-dict.

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

This child covers the **foundation** only:

1. **Config schema + dataclasses (4-location pattern)** — add
   `parallel.epic_branches.*` nested object to `config-schema.json`
   inside the `"parallel"` properties block (before
   `additionalProperties: false` at line 408). Sub-keys: `enabled` (bool,
   default false), `prefix` (string, default `"epic/"`),
   `merge_to_base_on_complete` (bool, default true), `open_pr` (bool,
   default false). Add matching dataclass field + `to_dict()` +
   `from_dict()` to `scripts/little_loops/parallel/types.py:ParallelConfig`.
   Mirror in `scripts/little_loops/config/automation.py:ParallelAutomationConfig`
   and its `from_dict()`. Add explicit keyword passthrough in
   `scripts/little_loops/config/core.py:BRConfig.create_parallel_config()`
   (~line 496).
2. **`EpicBranchesConfig` dataclass** — modeled on
   `ConfidenceGateConfig` in `commands.*`. Export from
   `scripts/little_loops/parallel/__init__.py` (mirrors how
   `ConfidenceGateConfig` is re-exported from `config/__init__.py`):
   add the import + `__all__` entry alongside `ParallelConfig`.
3. **`BRConfig.to_dict()` serialization** — add `epic_branches`
   sub-object to the explicit `parallel` key enumeration in
   `scripts/little_loops/config/core.py:555-574`. Omitting it causes
   `ll-issues decisions sync` / config round-trip to silently lose the
   setting.
4. **Epic-branch resolver** — add
   `_resolve_branch_targets(issue: IssueInfo) -> tuple[str, str]`
   (fork_point, merge_target) to `WorkerPool` (in
   `scripts/little_loops/parallel/worker_pool.py`). Uses
   `issue.parent` (from `scripts/little_loops/issue_parser.py:IssueInfo.parent`,
   line ~437, drifted from 251 per FEAT-2339 anchor corrections) and
   `self.parallel_config.epic_branches.enabled`. Resolves to the
   **nearest EPIC ancestor** via a depth-aware helper (reuses the
   `_issue_descends_to()` cycle-guard shape from `issue_progress.py:67-80`,
   but returns the nearest ancestor ID, not just a boolean). Lazily
   creates `epic/<EPIC-ID>-<slug>` off `base_branch` on first call
   per epic_id (idempotent: skip if branch already exists locally or
   on remote). Returns `(self.parallel_config.base_branch,
   self.parallel_config.base_branch)` (i.e. today-equivalent no-op) when
   epic mode is disabled or `issue.parent` is None — keeps
   `merge_coordinator.py` consumer sites trivially unchanged.
5. **Tests** —
   - `scripts/tests/test_parallel_types.py:test_roundtrip_serialization`
     (lines 1017–1059) — add `epic_branches=EpicBranchesConfig(enabled=True, ...)`
     to constructor and assert.
   - `scripts/tests/test_config_schema.py` — add
     `test_parallel_epic_branches_in_schema()` asserting
     `"epic_branches" in parallel["properties"]` with sub-properties
     `enabled`/`prefix`/`merge_to_base_on_complete`/`open_pr`.
   - `scripts/tests/test_config.py:TestParallelAutomationConfig`
     (lines 340–412) — add `epic_branches` counterpart test modeled on
     `TestConfidenceGateConfig` (lines 415–443).
   - `scripts/tests/test_config.py:test_to_dict_parallel_schema_aligned_keys`
     (lines 776–797) — add `"epic_branches" in parallel` assertion.
   - `scripts/tests/test_worker_pool.py` — new
     `test_resolve_branch_targets_*` tests modeled on the
     `_make_issue(tmp_path, issue_id, parent=...)` helper from
     `scripts/tests/test_issue_progress.py:12-64`. Cover:
     - epic_mode off → returns `(base_branch, base_branch)`
     - epic_mode on, parentless issue → returns `(base_branch, base_branch)`
     - epic_mode on, issue with EPIC parent → returns
       `(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)`
     - nested-EPIC flatten-to-nearest (grandchild with intermediate
       sub-EPIC parent) → returns nearest ancestor's branch, not
       grandchild's direct parent.
     - idempotent lazy creation: second call for same epic_id does
       not error if branch already exists.

## Out of Scope (deferred to follow-on children)

- `worker_pool.py:_setup_worktree()` actually using the resolver's
  fork point — **FEAT-2448**.
- `merge_coordinator.py` using the resolver's merge target — **FEAT-2448**.
- `WorkerResult.epic_branch` field threading — **FEAT-2448**.
- `_get_changed_files()` / `_update_branch_base()` epic-mode variants
  — **FEAT-2448**.
- EPIC-completion → epic-branch merge logic — **FEAT-2449**.
- Orchestrator / sprint-runner epic-branch awareness (rev-list
  comparison, in-place warning) — **FEAT-2449**.
- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs (ARCHITECTURE, API, CONFIGURATION, CLI, SPRINT_GUIDE), 9
  templates parity — **FEAT-2450**.

## Acceptance Criteria

- [ ] `EpicBranchesConfig` dataclass exists in `parallel/types.py`
      with the 4 documented sub-fields and correct defaults.
- [ ] `ParallelConfig` carries `epic_branches: EpicBranchesConfig`
      with `to_dict()` / `from_dict()` roundtrip preservation.
- [ ] `ParallelAutomationConfig` mirrors the same field with
      `from_dict()` parsing.
- [ ] `BRConfig.create_parallel_config()` passes the new field through
      (~line 496).
- [ ] `BRConfig.to_dict()` serializes `epic_branches` inside
      `parallel` (lines 555–574).
- [ ] `EpicBranchesConfig` is exported from
      `scripts/little_loops/parallel/__init__.py` (`__all__` entry).
- [ ] `WorkerPool._resolve_branch_targets(issue)` exists with the
      documented semantics (parentless / epic-off → no-op return;
      epic-on with EPIC parent → nearest ancestor branch tuple;
      nested-EPIC flatten-to-nearest; idempotent lazy creation).
- [ ] All new tests pass; full
      `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `config-schema.json` (add `parallel.epic_branches` block)
- `scripts/little_loops/parallel/types.py` (`EpicBranchesConfig` +
  `ParallelConfig` field + `to_dict`/`from_dict`)
- `scripts/little_loops/parallel/__init__.py` (export)
- `scripts/little_loops/config/automation.py`
  (`ParallelAutomationConfig` mirror)
- `scripts/little_loops/config/core.py` (`BRConfig.create_parallel_config`
  + `BRConfig.to_dict`)
- `scripts/little_loops/parallel/worker_pool.py`
  (`_resolve_branch_targets` method)

**Tests:**
- `scripts/tests/test_parallel_types.py`
- `scripts/tests/test_config_schema.py`
- `scripts/tests/test_config.py` (`TestParallelAutomationConfig` +
  `test_to_dict_parallel_schema_aligned_keys`)
- `scripts/tests/test_worker_pool.py` (new `_resolve_branch_targets_*`
  block, modeled on `_make_issue` helper from `test_issue_progress.py`)

**Estimated file count:** 4 implementation + 4 test = **8 files**.

## Implementation Steps

1. **Config surface** — add `parallel.epic_branches` to
   `config-schema.json` (sub-keys: `enabled`, `prefix`,
   `merge_to_base_on_complete`, `open_pr`); add `EpicBranchesConfig`
   dataclass to `parallel/types.py`; mirror in
   `ParallelAutomationConfig`; wire `BRConfig.create_parallel_config()`
   keyword passthrough and `BRConfig.to_dict()` serialization.
2. **Export** — add `EpicBranchesConfig` to `parallel/__init__.py`
   `__all__` alongside `ParallelConfig`.
3. **Resolver** — implement `WorkerPool._resolve_branch_targets(issue)`
   with nearest-EPIC-ancestor flattening, idempotent lazy branch
   creation off `base_branch`, and no-op fallback for parentless or
   epic-off paths. Cycle-guard modeled on the
   `_issue_descends_to()` shape from
   `scripts/little_loops/issue_progress.py`.
4. **Tests** — extend `test_parallel_types.py` roundtrip case, add
   `test_parallel_epic_branches_in_schema()` to `test_config_schema.py`,
   add `epic_branches` counterpart to `TestParallelAutomationConfig`
   and `test_to_dict_parallel_schema_aligned_keys`, and add a new
   `_resolve_branch_targets_*` block to `test_worker_pool.py` (5 cases:
   no-op, parentless, EPIC-parent, nested-EPIC flatten, idempotent
   re-call).
5. **Verify** — `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation:_

6. **Re-export `EpicBranchesConfig` from `config/__init__.py`** — mirror
   the `parallel/__init__.py` re-export. Without this,
   `from little_loops.config import EpicBranchesConfig` will
   `ImportError` even though `parallel/__init__.py` exposes the class.
7. **Resolve the template-parity scope conflict** — pick option
   (A) stamp the 9 project-type templates in this child per
   `ARCHITECTURE-096` (small mechanical edits) **or** option (B)
   land them in FEAT-2450 alongside the TUI/configure surface. The
   rationale for option (A) is consistency: the schema accepts
   `epic_branches` from day 1, so init-using projects get the same
   defaults as config-file users. The rationale for (B) is keeping
   this child strictly "foundation only" with no init template
   coupling. The current "Out of Scope" deferral matches (B); the
   decision rule mandates (A). Resolve before implementation.
8. **Verify `init/core.py` schema-default parity** —
   `scripts/tests/test_init_core.py:707` asserts schema-default ↔
   literal parity; either add `parallel.epic_branches: {enabled:
   false}` to `init/core.py:build_config()` defaults, OR confirm
   the test is schema-permissive on missing keys (Agent 1 finding).
9. **Verify hardcoded `"parallel"` test fixtures against new
   schema** — if any of the 5 fixtures listed under
   `Tests → Hardcoded "parallel" test fixtures` reject the new
   schema, add `"epic_branches": {"enabled": false}` to each.
10. **Audit `feature_config = ParallelConfig(**...to_dict(),
    "use_feature_branches": True)` at
    `scripts/tests/test_worker_pool.py:2201`** — the new
    `epic_branches` field will appear in `to_dict()`. Either set
    it explicitly on both configs in the diff or rely on
    `default_factory` equality.

## Integration Map

### Files to Modify
See **Files Touched** for the 8-file breakdown (4 implementation + 4
test). Implementation files: `config-schema.json`,
`scripts/little_loops/parallel/types.py`,
`scripts/little_loops/parallel/__init__.py`,
`scripts/little_loops/config/automation.py`,
`scripts/little_loops/config/core.py`,
`scripts/little_loops/parallel/worker_pool.py`. Test files:
`scripts/tests/test_parallel_types.py`,
`scripts/tests/test_config_schema.py`, `scripts/tests/test_config.py`,
`scripts/tests/test_worker_pool.py`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` —
  `WorkerPool.__init__` / `_setup_worktree` (FEAT-2448 will consume
  `_resolve_branch_targets`; this child only adds the method).
- `scripts/little_loops/parallel/merge_coordinator.py` —
  `_get_changed_files()` / `_update_branch_base()` (FEAT-2448 will
  consume; this child does not).
- `scripts/little_loops/parallel/orchestrator.py` —
  sprint/epic-aware comparison paths (FEAT-2449).
- `scripts/little_loops/cli/parallel.py` and `cli/sprint.py` — CLI
  flag surface (FEAT-2450).
- `.ll/ll-config.json` consumers via `ll-config validate` —
  schema-driven round-trip; `decisions sync` writes the new key
  automatically once the schema entry exists.
- `scripts/little_loops/config/__init__.py` — [Agent 1 finding] re-exports
  `ParallelAutomationConfig` and the new `EpicBranchesConfig` must be
  re-exported alongside it (mirrors the `parallel/__init__.py`
  re-export of `EpicBranchesConfig`).
- `scripts/little_loops/config/features.py:593` — [Agent 1 finding]
  reads `self.parallel`; verify it round-trips the nested
  `epic_branches` sub-dict if this file already exposes a parallel
  accessor (no direct call-site change likely needed beyond
  `BRConfig.to_dict()` plumbing).

### Similar Patterns
- `ConfidenceGateConfig` in `scripts/little_loops/config/automation.py:103-119`
  is the precedent for the nested config-object pattern (issue
  originally cited `commands.py` which does not exist — see Codebase
  Research Findings under **Proposed Solution** for the correction);
  mirror its `to_dict()` / `from_dict()` shape.
- `_issue_descends_to()` in
  `scripts/little_loops/issue_progress.py:67-80` is the cycle-guard
  shape for the nearest-EPIC-ancestor traversal.
- `_find_epic_ancestor()` in
  `scripts/little_loops/cli/issues/list_cmd.py:195-203` is the **closer
  precedent** for the resolver — it returns the nearest EPIC
  ancestor's ID (not a boolean), using the same `seen` cycle-guard
  and `parent_map.get(current)` walk. Mirror its `current.split("-", 1)[0] == "EPIC"`
  → `return current` shape.
- `_make_issue()` helper in `scripts/tests/test_issue_progress.py:12-64`
  is the test-fixture pattern for synthesizing `IssueInfo` with parent
  links (used for parsed-issue-semantics tests).
- `mock_issue` MagicMock fixture in
  `scripts/tests/test_worker_pool.py:110-117` is sufficient for
  `_resolve_branch_targets` unit tests since the resolver only needs
  `.issue_id` and `.parent`.

### Tests
See **Files Touched** — 4 test files, ~5 new test cases total.
The existing `mock_issue` MagicMock fixture at
`test_worker_pool.py:110-117` can be reused for `_resolve_branch_targets_*`
tests since the resolver only consumes `.issue_id` and `.parent`
(no filesystem-dependent semantics). For nested-EPIC flatten tests
requiring real parent_chain semantics, use `_make_issue()` from
`test_issue_progress.py:12-64` (it synthesizes an `IssueInfo` with a
real `parent` field that the resolver can traverse).

#### Hardcoded `"parallel"` test fixtures — verify under new schema

_Wiring pass added by `/ll:wire-issue` — Agent 1 surfaced these test
fixtures that hard-code a `"parallel"` dict block. Once the schema
adds the nested `epic_branches` sub-object under
`additionalProperties: false` (config-schema.json `parallel` block),
each fixture must continue to validate. Verify during implementation
by re-running the affected test files after the schema edit:

- `scripts/tests/conftest.py:284-296` — `sample_config["parallel"]`
  fixture (the docstring below notes no change needed unless the
  schema is strict on missing keys).
- `scripts/tests/test_cli.py:479` — hardcoded `"parallel": {...}` block.
- `scripts/tests/test_cli.py:1642` — hardcoded `"parallel": {...}` block.
- `scripts/tests/test_cli_e2e.py:105` — hardcoded `"parallel": {...}` block.
- `scripts/tests/test_issue_workflow_integration.py:197` — hardcoded
  `"parallel": {...}` block.

If any of these are rejected by the new schema (`additionalProperties:
false` is strict on missing keys), add `"epic_branches": {"enabled":
false}` to each. None of these existing fixtures should need the
nested key for behavior reasons — the addition is purely a
schema-parity stamp.

#### `feature_config = ParallelConfig(**default_parallel_config.to_dict(), "use_feature_branches": True)` pattern

_Wiring pass added by `/ll:wire-issue` — Agent 2 flagged
`scripts/tests/test_worker_pool.py:2201` which diffs `to_dict()` output
across two configs. With the new `epic_branches` field included in
`to_dict()`, this pattern will compare the full nested dict. Either
the test must explicitly set `epic_branches=` to both configs for
equality, or rely on `default_factory` producing equal defaults.
Verify during implementation; the natural fix is to ensure both
configs omit or both configs set `epic_branches` identically.


### Documentation
No doc updates in this child. ARCHITECTURE, API, CONFIGURATION, CLI,
and SPRINT_GUIDE updates are deferred to FEAT-2450.

#### Doc placeholders for FEAT-2450 (wiring-pass flagged)

_Wiring pass added by `/ll:wire-issue` — these files mention the
`parallel` config surface or `WorkerPool` and will need
`epic_branches.*` mentions in FEAT-2450 (Agent 2 findings — audit-only,
no edits in this child):_

- `docs/reference/CONFIGURATION.md:53-69, 338-361` — `parallel` JSON
  example + field-table; will need an `epic_branches.*` block.
- `docs/reference/API.md:251-278, 300-310, 447-491, 4365` —
  `create_parallel_config` signature/parameters/example + `ParallelConfig`
  class table; will need an `epic_branches` row.
- `docs/reference/COMMANDS.md:45` — `parallel` listed as config area.
- `docs/ARCHITECTURE.md:803` — `+create_parallel_config()` narrative
  (low-priority).
- `CONTRIBUTING.md:39` — `ll-parallel --help` snippet; may want to
  forward-reference `--epic-branches` (FEAT-2450).
- `docs/development/TROUBLESHOOTING.md:271, 698` — parallel config
  examples.
- `skills/configure/SKILL.md:14, 103, 136, 221` — `parallel` area
  registration table.
- `skills/configure/areas.md:184-269` — Round-2 question on
  `feature_branches` is the shape-mirror to copy for an epic-branches
  round.
- `skills/configure/show-output.md:38-56` — `--show parallel`
  output listing.
- `commands/describe-pr.md:3`, `commands/open-pr.md:48`,
  `commands/resume.md:185`, `commands/review-sprint.md` —
  `ll-parallel`/`ll-sprint` cross-refs.
- `CHANGELOG.md` — once shipped, an entry under the next
  released version (NOT `[Unreleased]`, per
  `feedback_changelog_no_unreleased.md` rule) following the
  `feat(parallel): ...` convention.

### Configuration
`config-schema.json` (additive — `parallel.epic_branches.*`) and
`.ll/ll-config.json` (opt-in `parallel.epic_branches.enabled: true`
when the user wants EPIC integration branches).

#### Template parity (Decision ARCHITECTURE-096)

_Wiring pass added by `/ll:wire-issue` — Decision
`ARCHITECTURE-096` (`.ll/decisions.yaml:3829-3843`) mandates stamping
`parallel.epic_branches: {enabled: false}` explicitly in all 9
project-type templates, matching the existing `use_feature_branches:
false` convention. NOTE: this contradicts the **Out of Scope**
deferral above (which assigns templates to FEAT-2450). Pick one of:

- (A) Land the template stamps in this child (FEAT-2447) per the
  decision rule — 9 small mechanical edits.
- (B) Land in FEAT-2450 with the rest of the TUI/configure surface —
  accepts that init/TUI parity will lag schema acceptance by one
  child._

The 9 templates (Agent 2 findings):

- `scripts/little_loops/templates/typescript.json:69-70`
- `scripts/little_loops/templates/python-generic.json:71-72`
- `scripts/little_loops/templates/javascript.json:71-72`
- `scripts/little_loops/templates/java-maven.json:64-65`
- `scripts/little_loops/templates/java-gradle.json:66-67`
- `scripts/little_loops/templates/rust.json:63-64`
- `scripts/little_loops/templates/go.json:64-65`
- `scripts/little_loops/templates/dotnet.json:67-68`
- `scripts/little_loops/templates/generic.json:39-40`

#### `init/core.py` schema-default parity guard

_Wiring pass added by `/ll:wire-issue` —_ `scripts/tests/test_init_core.py:707`
enforces schema-default ↔ `init/core.py` literal parity. Adding
`parallel.epic_branches` defaults to `config-schema.json` without
matching `init/core.py` literals (or vice-versa) will fail this guard.
Verify during implementation that the `init/core.build_config` defaults
include `parallel.epic_branches: {enabled: false}` (or are tolerant
of the absence — depends on whether the test is schema-strict).

#### `sample_config` fixture (`scripts/tests/conftest.py:284-296`)

_Wiring pass added by `/ll:wire-issue` —_ `sample_config["parallel"]`
exerts no new key (only `use_feature_branches` and friends), so with
`default_factory=EpicBranchesConfig()` semantics it will accept the
default and round-trip fine. No fixture change required **unless** the
schema's `additionalProperties: false` is strict on missing keys
(verify by running
`python -m pytest scripts/tests/test_config_schema.py` after the schema
edit).

## API/Interface

### Config schema (`config-schema.json` — `parallel.epic_branches`)

```json
{
  "epic_branches": {
    "type": "object",
    "description": "Per-EPIC integration branch configuration for ll-parallel/ll-sprint",
    "properties": {
      "enabled": { "type": "boolean", "default": false },
      "prefix": { "type": "string", "default": "epic/" },
      "merge_to_base_on_complete": { "type": "boolean", "default": true },
      "open_pr": { "type": "boolean", "default": false }
    }
  }
}
```

### Dataclass (`scripts/little_loops/parallel/types.py`)

```python
@dataclass
class EpicBranchesConfig:
    enabled: bool = False
    prefix: str = "epic/"
    merge_to_base_on_complete: bool = True
    open_pr: bool = False


@dataclass
class ParallelConfig:
    # ... existing fields ...
    epic_branches: EpicBranchesConfig = field(default_factory=EpicBranchesConfig)
```

### Resolver (`scripts/little_loops/parallel/worker_pool.py`)

```python
def _resolve_branch_targets(self, issue: IssueInfo) -> tuple[str, str]:
    """Return (fork_point, merge_target) for ``issue``.

    - epic-off (``self.parallel_config.epic_branches.enabled is False``)
      or parentless (``issue.parent is None``) → returns
      ``(base_branch, base_branch)`` — no-op, identical to today's
      behavior so ``merge_coordinator.py`` consumer sites are unchanged.
    - epic-on with an EPIC parent → returns
      ``(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)``, flattened to
      the nearest EPIC ancestor (cycle-guarded).
    - The branch is created lazily off ``base_branch`` on first call per
      ``epic_id``; subsequent calls are idempotent.
    """
```

### Public API impact
- **New**: `EpicBranchesConfig` dataclass (exported from
  `scripts/little_loops/parallel/__init__.py`).
- **New field**: `ParallelConfig.epic_branches` (default factory
  `EpicBranchesConfig()`, backward compatible).
- **New field**: `ParallelAutomationConfig.epic_branches` (default
  factory `EpicBranchesConfig()`, backward compatible).
- **New private method**: `WorkerPool._resolve_branch_targets()`
  (leading underscore — internal API, no public surface change).

## Impact

- **Priority**: P3 — enhancement with no current user-visible
  breakage; existing per-worker merge flow is functional, this adds
  a cohesion surface for EPICs. Frontmatter `priority: P3` and
  `outcome_confidence: 60` agree: bounded value, modest payoff.
- **Effort**: Medium — 4 implementation files + 4 test files, but
  each change is localized (single field addition, single private
  method, single schema block). `score_complexity: 6` per
  frontmatter. Reuses existing patterns (`ConfidenceGateConfig`,
  `_issue_descends_to()`, `_make_issue()`), so no green-field design.
- **Risk**: Low — default OFF (`enabled: false`); parentless or
  epic-off paths are explicit no-op returns; no consumer site in
  `merge_coordinator.py` is touched until FEAT-2448.
  `score_change_surface: 0` per frontmatter (additive only).
- **Breaking Change**: No — additive config key, additive dataclass
  field with safe defaults, additive private method.


## Blocks

- FEAT-2448

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-07-06T23:09:05 - `21cbc8bc-ce15-4912-bb93-e3574c91e49c.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:14:35 - `a621374e-67ee-4d36-8474-5106e009ded9.jsonl`
- `/ll:format-issue` - 2026-07-03T02:25:51 - `4b4fed19-776f-4701-9732-113c091c2f49.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`
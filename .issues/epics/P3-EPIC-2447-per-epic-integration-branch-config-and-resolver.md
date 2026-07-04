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

### Similar Patterns
- `ConfidenceGateConfig` in `scripts/little_loops/config/commands.py`
  is the precedent for the nested 4-key config-object pattern; mirror
  its `to_dict()` / `from_dict()` shape.
- `_issue_descends_to()` in
  `scripts/little_loops/issue_progress.py:67-80` is the cycle-guard
  shape for the nearest-EPIC-ancestor traversal.
- `_make_issue()` helper in `scripts/tests/test_issue_progress.py:12-64`
  is the test-fixture pattern for synthesizing `IssueInfo` with parent
  links.

### Tests
See **Files Touched** — 4 test files, ~5 new test cases total.

### Documentation
No doc updates in this child. ARCHITECTURE, API, CONFIGURATION, CLI,
and SPRINT_GUIDE updates are deferred to FEAT-2450.

### Configuration
`config-schema.json` (additive — `parallel.epic_branches.*`) and
`.ll/ll-config.json` (opt-in `parallel.epic_branches.enabled: true`
when the user wants EPIC integration branches).

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

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-07-03T02:25:51 - `4b4fed19-776f-4701-9732-113c091c2f49.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`
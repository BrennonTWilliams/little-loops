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
parent: FEAT-2339
relates_to:
- FEAT-2339
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

## Session Log
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`
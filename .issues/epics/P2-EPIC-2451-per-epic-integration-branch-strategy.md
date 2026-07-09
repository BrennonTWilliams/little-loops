---
id: EPIC-2451
title: Per-EPIC integration branch strategy (decomposed from FEAT-2339)
type: EPIC
priority: P2
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
- meta
parent: FEAT-2339
relates_to:
- FEAT-2339
- FEAT-2447
- FEAT-2448
- FEAT-2449
- FEAT-2450
- FEAT-2452
- FEAT-2453
- FEAT-2561
- FEAT-2562
- FEAT-2563
decision_needed: false
confidence_score: 95
outcome_confidence: 60
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
---

# EPIC-2451: Per-EPIC integration branch strategy (decomposed from FEAT-2339)

## Summary

Parent EPIC grouping the four sequenced children decomposed from
FEAT-2339 on 2026-07-02 by `/ll:issue-size-review`. FEAT-2339 scored
11/11 (Very Large — ~5500 words, 26 implementation steps, 30+ files)
and was split along natural sequential seams: config → wiring →
completion → polish. This EPIC tracks group-level progress; each
child is independently shippable once its predecessor lands.

## Parent Issue

Decomposed from FEAT-2339 (now `status: done`): Per-EPIC integration
branch strategy for ll-parallel/ll-sprint.

## Children

### FEAT-2447 — config schema, dataclasses, resolver, serialization
- **Status**: open
- **Priority**: P3
- **Unblocks**: FEAT-2448
- **Scope**: 4-location config extension (`parallel.epic_branches.*`),
  `EpicBranchesConfig` dataclass, `BRConfig.to_dict()` serialization,
  `WorkerPool._resolve_branch_targets()` (with depth-aware nearest-
  ancestor lookup and idempotent lazy branch creation), unit tests.
- **Estimated files**: 8 (4 impl + 4 test)
- **Outcome confidence**: 60

### FEAT-2448 — worker_pool + merge_coordinator wiring (coordination container)
- **Status**: open (blocked by FEAT-2447)
- **Priority**: P3
- **Unblocks**: FEAT-2449 (via decomposed children FEAT-2452 → FEAT-2453)
- **Decomposed on**: 2026-07-07 via `/ll:confidence-check`
  (outcome 74/100 → split into FEAT-2452 + FEAT-2453)
- **Outcome confidence**: 74 (parent container)
- **Children**:
  - **FEAT-2452** — WorkerPool + WorkerResult dataclass wiring
    (broad fanout: 12-return kwarg threading, instance-state dict,
    `_get_changed_files` / `_update_branch_base` variants,
    `types.py` 4-edit pattern). Lands first.
    **Outcome**: 74 / MODERATE.
    **Estimated files**: 7 (3 impl + 4 test).
  - **FEAT-2453** — Downstream consumer read-sites
    (3 read-site `or` substitutions at `merge_coordinator.py:624 / :875`
    and `orchestrator.py:1142`, plus `branch_state["epic_branch"]`
    mutation at `orchestrator.py:1005`). Lands after FEAT-2452.
    **Outcome**: 86 / **HIGH**.
    **Estimated files**: 4 (2 impl + 2 test).
- **Cross-module risk**: carries the WorkerPool → MergeCoordinator
  state-threading risk flagged in FEAT-2339's Confidence Check Notes.
  Lifted out into FEAT-2452 (WorkerPool-side) and FEAT-2453
  (downstream consumers) by the 2026-07-07 split.

### FEAT-2449 — EPIC-completion merge + partial-failure gate (Unit A, re-scoped)
- **Status**: open (blocked by FEAT-2448, FEAT-2561)
- **Priority**: P3
- **Decomposed on**: 2026-07-09 via `/ll:confidence-check`
  (outcome 70/100 → split out FEAT-2561/2562/2563 to shrink blast radius)
- **Unblocks**: FEAT-2450
- **Scope (Unit A core only)**: EPIC-completion detection via
  `compute_epic_progress()` (transitive walk per commit `4887c87c`),
  epic-branch → base merge or single PR on completion + `branch -D`,
  config-branch gating (`merge_to_base_on_complete` / `open_pr` dead-read
  fix), partial-failure gate (block until all children `done`, scoped via
  the FEAT-2561 helper), nested-EPIC sprint test.
- **Estimated files**: 3 (1 impl + 2 test)
- **Outcome confidence**: 70 (pre-split; expected to rise on re-check)

### FEAT-2561 — shared EPIC-ancestor helper (prerequisite)
- **Status**: open (actionable now — no blocker)
- **Priority**: P3
- **Unblocks**: FEAT-2449, FEAT-2562
- **Scope**: promote `find_nearest_epic_ancestor` + `build_parent_map` to
  module-level fns in `issue_progress.py`; `WorkerPool` delegates
  (behavior-preserving); DRY the inline parent-map build in
  `compute_epic_progress`. Removes the orchestrator's reach into the private
  `WorkerPool._find_nearest_epic_ancestor`.
- **Estimated files**: 3 (2 impl + 1 test)
- **Outcome confidence**: ~85 (mechanical extraction + delegation)

### FEAT-2562 — `_inspect_worktree()` epic-branch comparison (Unit B)
- **Status**: open (blocked by FEAT-2561)
- **Priority**: P3
- **Scope**: orchestrator `_inspect_worktree()` `rev-list --count` compares
  against `epic/<id>` for EPIC children (`orchestrator.py:415`); maps
  worktree issue-ID → EPIC via the FEAT-2561 helper. Audits
  `TestInspectWorktree` (6 tests) + `TestOrphanedWorktreeCleanup` epic/*
  NOT-deleted audit.
- **Estimated files**: 2 (1 impl + 1 test)
- **Outcome confidence**: ~85

### FEAT-2563 — sprint in-place warning epic-awareness (Unit C)
- **Status**: open (independent — no blocker)
- **Priority**: P3
- **Scope**: `cli/sprint/run.py` in-place / contention-subwave warning adds
  an `effective_epic_branches` check mirroring `effective_feature_branches`,
  appended to the existing warning (preserving the
  `"feature-branch mode does not apply"` substring). Reads config/args flags
  only — no issue→EPIC mapping.
- **Estimated files**: 2 (1 impl + 1 test)
- **Outcome confidence**: ~88

### FEAT-2450 — CLI flags, TUI surface, docs, templates parity
- **Status**: open (blocked by FEAT-2449)
- **Priority**: P3
- **Final child.**
- **Scope**: `--epic-branches` CLI flag (ll-parallel + ll-sprint), TUI
  surface (init/tui.py:343,378,664), `/ll:configure` skill updates,
  `prune_merged_feature_branches()` docstring update, 9 templates
  parity stamp, all docs (CONFIGURATION, CLI, SPRINT_GUIDE, ARCHITECTURE,
  API), end-to-end CLI tests.
- **Estimated files**: 21 (17 impl + 4 test)
- **Outcome confidence**: 70

## Execution Pattern

**Mostly sequential with a parallel tail.** Each early child consumes
artifacts from the prior child (config → resolver → wiring → completion).
After the 2026-07-07 decomposition, the wiring step has two sequenced
children (FEAT-2452 → FEAT-2453) that must both land before the completion
work. The 2026-07-09 decomposition then split FEAT-2449's completion work
into a prerequisite helper (FEAT-2561) plus three peers, so the spine is now:

```
2447 → (2452 → 2453) → 2561 → { 2449, 2562 }  ‖  2563  →  2450
```

- **FEAT-2561** (helper) gates both FEAT-2449 (partial-failure gate) and
  FEAT-2562 (`_inspect_worktree`). It is actionable as soon as FEAT-2453 lands
  (its `blocked_by` is empty; the dependency is only that the epic-branch
  machinery it serves is already wired).
- **FEAT-2449** and **FEAT-2562** can run in parallel once FEAT-2561 lands.
- **FEAT-2563** (sprint warning) is fully independent — no helper dependency —
  and can land any time.
- **FEAT-2450** (CLI/TUI/docs/templates polish) is the final child; it waits on
  all functional work (FEAT-2449 + FEAT-2562 + FEAT-2563).

The cross-module state threading (FEAT-2452 + FEAT-2453) and the EPIC-completion
+ partial-failure semantics (FEAT-2449) still carry the bulk of the
implementation risk; FEAT-2561/2562/2563 are each single-session, high-outcome
slices.

## Total Scope

- **Files touched across all children**: ~45 (24 implementation + 21 test) — up from ~43 with FEAT-2452 (3 impl + 4 test = 7) + FEAT-2453 (2 impl + 2 test = 4) replacing the original 8-file FEAT-2448.
- **Steps from FEAT-2339 Implementation Steps**: all 26 covered
- **Word count reduction**: from ~5500 words in FEAT-2339 to
  ~1200 (FEAT-2447), ~1100 (FEAT-2452), ~700 (FEAT-2453), ~1100 (FEAT-2449), ~1300 (FEAT-2450) — each child is a single-session-sized chunk.

## Acceptance Criteria

- [ ] FEAT-2447 lands and unlocks FEAT-2452.
- [ ] FEAT-2452 lands and unlocks FEAT-2453.
- [ ] FEAT-2453 lands and unlocks FEAT-2561.
- [ ] FEAT-2561 lands (shared helper) and unlocks FEAT-2449 + FEAT-2562.
- [ ] FEAT-2449, FEAT-2562, FEAT-2563 all land (completion core +
      inspect-worktree + sprint warning) and collectively unlock FEAT-2450.
- [ ] FEAT-2450 lands — EPIC complete; full
      `python -m pytest scripts/tests/` exits 0.
- [ ] All 6 acceptance criteria from FEAT-2339 are satisfied by the
      collective work of the children (default-off regression,
      EPIC-child fork/merge into shared branch, lazy branch creation,
      completion merge or single PR, nested-EPIC behavior, config
      documentation and surfaces).

## Out of Scope

- A separate, parallel work-stream on the codebase research
  findings from FEAT-2339 (transitive-walk in `issue_progress.py`,
  `sprint.py` grandchild-drop gap, etc.) — these are pre-existing
  issues independent of this EPIC.

## Session Log
- `/ll:confidence-check` - 2026-07-09 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl` - Decomposed FEAT-2449 (outcome 70/100): split out FEAT-2561 (shared EPIC-ancestor helper, prerequisite), FEAT-2562 (`_inspect_worktree` epic-awareness), FEAT-2563 (sprint in-place warning) as peers; FEAT-2449 re-scoped to the completion/merge/partial-failure Unit-A core. FEAT-2450 `blocked_by` widened to [FEAT-2449, FEAT-2562, FEAT-2563].
- Audit - 2026-07-06 - Corrected mistyped children: EPIC-2447/EPIC-2449 retyped to FEAT-2447/FEAT-2449 (id, type, filename moved to `features/`), cross-references updated across all five issues. Body text had referenced them as FEAT throughout since decomposition.
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`
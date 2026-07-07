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

### FEAT-2449 — EPIC-completion merge + orchestrator/sprint awareness
- **Status**: open (blocked by FEAT-2448)
- **Priority**: P3
- **Unblocks**: FEAT-2450
- **Scope**: EPIC-completion detection via
  `compute_epic_progress()` (transitive walk per commit `4887c87c`),
  epic-branch → base merge or single PR on completion, partial-failure
  gate (block until all children `done`), orchestrator `_inspect_worktree`
  epic-awareness, `cli/sprint/run.py` in-place warning epic-awareness,
  nested-EPIC sprint test.
- **Estimated files**: 6 (2 impl + 4 test)
- **Outcome confidence**: 55

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

**Strictly sequential with shared scope.** Each child consumes
artifacts from the prior child (config → resolver → wiring →
completion → polish). After the 2026-07-07 decomposition, the
wiring step has two sequenced children (FEAT-2452 → FEAT-2453)
that must both land before FEAT-2449 — the spine is now
1→(2a→2b)→3→4. Parallelism is possible on tests/docs/templates
within FEAT-2450 once FEAT-2449 lands, but the cross-module
state threading (FEAT-2452 + FEAT-2453) and EPIC-completion
semantics (FEAT-2449) carry the bulk of the implementation
risk. FEAT-2453 ships with HIGH outcome confidence (86/100)
once FEAT-2452 lands; FEAT-2452 inherits the broad-fanout
burden inherent to the dataclass change.

## Total Scope

- **Files touched across all children**: ~45 (24 implementation + 21 test) — up from ~43 with FEAT-2452 (3 impl + 4 test = 7) + FEAT-2453 (2 impl + 2 test = 4) replacing the original 8-file FEAT-2448.
- **Steps from FEAT-2339 Implementation Steps**: all 26 covered
- **Word count reduction**: from ~5500 words in FEAT-2339 to
  ~1200 (FEAT-2447), ~1100 (FEAT-2452), ~700 (FEAT-2453), ~1100 (FEAT-2449), ~1300 (FEAT-2450) — each child is a single-session-sized chunk.

## Acceptance Criteria

- [ ] FEAT-2447 lands and unlocks FEAT-2452.
- [ ] FEAT-2452 lands and unlocks FEAT-2453.
- [ ] FEAT-2453 lands and unlocks FEAT-2449.
- [ ] FEAT-2449 lands and unlocks FEAT-2450.
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
- Audit - 2026-07-06 - Corrected mistyped children: EPIC-2447/EPIC-2449 retyped to FEAT-2447/FEAT-2449 (id, type, filename moved to `features/`), cross-references updated across all five issues. Body text had referenced them as FEAT throughout since decomposition.
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`
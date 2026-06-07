---
id: FEAT-1992
title: "rn-build — Core Loop YAML, Loaders, and Integration"
type: FEAT
priority: P3
status: open
parent: FEAT-1990
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: Large
blocked_by: [FEAT-1988, FEAT-1991]
relates_to:
- FEAT-1990
- FEAT-1988
labels:
- loops
- orchestration
- built-in
- greenfield
---

# FEAT-1992: `rn-build` — Core Loop YAML, Loaders, and Integration

## Summary

Author `scripts/little_loops/loops/rn-build.yaml` (the capstone loop from
FEAT-1990), reusing `greenfield-builder`'s front-half phases, wiring the
`scope-epic → goal-cluster → rn-implement(value_ranked)` composition, adding the
`eval_gate` re-entry, registering the loop in the builtin catalog and router
exclusions, and writing all core tests.

## Parent Issue

Decomposed from FEAT-1990: `rn-build` — Recursive Spec-to-Project Builder.

## Prerequisites

- **FEAT-1988** (`goal-cluster.yaml` core) merged — `cluster_execute` delegates to it.
- **FEAT-1991** (`rn-implement` `value_ranked` mode) merged — the per-batch
  dispatch passes `schedule_mode=value_ranked`.

## Proposed Solution

### 1. Create loop YAML

Author `scripts/little_loops/loops/rn-build.yaml` per the FEAT-1990 state graph:

1. **`init`** — validate spec path(s) exist, read contents (port from
   `greenfield-builder.yaml:init`). Write to `${context.run_dir}/`.
2. **`tech_research`** — port `greenfield-builder` phase 2 → `docs/research.md`.
3. **`design_artifacts`** — port phase 3 → `docs/data-model.md`, `docs/contracts/`,
   `docs/quickstart.md`.
4. **`commit_design`** — `/ll:commit`.
5. **`scope_project`** — invoke `scope-epic` against spec + design artifacts to
   produce an EPIC + epic/feature child stubs. Capture the EPIC ID.
6. **`refine_seed`** — `loop: issue-refinement` over the seed issues
   (`context_passthrough: true`), as `greenfield-builder` phase 8 does.
7. **`eval_harness`** — install + customize an as-a-user harness (port phases 5/6);
   capture `harness_name`.
8. **`cluster_execute`** — `loop: goal-cluster` with `input=<EPIC-ID>`,
   `propagate_context=true`. goal-cluster dispatches each batch to
   `loop: rn-implement` with `schedule_mode=value_ranked`. (See §2 for the
   handoff contract.)
9. **`eval_gate`** — run the harness loop; on failure, `/ll:capture-issue` for the
   failing scenarios and re-enter `cluster_execute` (bounded retry counter under
   `${context.run_dir}/`).
10. **`synthesize_result`** — cluster-wide summary: accomplished / still-open /
    recommended next batch. Structured JSON.
11. **`done`** / **`failed`** terminals.

All intermediate artifacts under `${context.run_dir}/` (MR-3). Category:
`orchestration` (not `harness` — see FEAT-1990 Open Question 1).

### 2. goal-cluster → rn-implement handoff contract

Confirm/define how `goal-cluster`'s per-batch dispatch selects `rn-implement` as
the downstream loop and passes `schedule_mode=value_ranked`. Options:
- `goal-cluster` batch dispatch already routes via `loop-router`/chosen loop;
  pin the chosen loop to `rn-implement` for issue-shaped goals and thread the
  `schedule_mode` knob through `with:`.
- If goal-cluster cannot thread arbitrary context to its child loop, add a
  minimal passthrough in goal-cluster's execute state (coordinate with FEAT-1988).

### 3. Register in catalogs / exclusions

- Add `rn-build` to `scripts/tests/test_builtin_loops.py::test_expected_loops_exist`
  `expected` set.
- Add `rn-build` to the hard-exclude set in `loop-router.yaml::discover_loops`
  and `lib/composer.yaml::discover_loops` (a top-level builder must not be
  offered as a candidate sub-loop, same treatment as `loop-composer`/`goal-cluster`).

### 4. Tests

Create `scripts/tests/test_rn_build.py` following `test_loop_composer.py` /
`test_goal_cluster.py`:
- File-exists, YAML parse, FSM validate, required states, description field.
- Delegation assertions: `cluster_execute` targets `goal-cluster`; per-batch
  dispatch targets `rn-implement` with `schedule_mode=value_ranked`.
- `eval_gate` re-entry bounded (retry counter present).
- Router/composer exclusion tests for `rn-build`.

## Files to Modify

- `scripts/little_loops/loops/rn-build.yaml` (new)
- `scripts/little_loops/loops/loop-router.yaml` (exclusion)
- `scripts/little_loops/loops/lib/composer.yaml` (exclusion)
- `scripts/little_loops/loops/README.md` (append `rn-build` entry)
- `scripts/tests/test_rn_build.py` (new)
- `scripts/tests/test_builtin_loops.py` (expected set)
- `docs/guides/LOOPS_GUIDE.md` (rn-build vs greenfield-builder section)

## Acceptance Criteria

- `ll-loop validate rn-build.yaml` passes (no MR-1/MR-3 errors).
- `ll-loop list` includes `rn-build`.
- `cluster_execute` delegates to `goal-cluster`; per-batch to `rn-implement`
  (`value_ranked`).
- `eval-driven-development` is NOT in the dispatch path.
- `loop-router`/`loop-composer` never offer `rn-build` as a candidate.
- `python -m pytest scripts/tests/test_rn_build.py scripts/tests/test_builtin_loops.py -v` passes.

## Status

- **State**: open
- **Created**: 2026-06-06

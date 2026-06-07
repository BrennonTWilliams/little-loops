---
id: FEAT-1992
title: "rn-build \u2014 Core Loop YAML, Loaders, and Integration"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
discovered_date: 2026-06-06
discovered_by: capture-issue
size: Large
blocked_by:
- FEAT-1988
- FEAT-1991
relates_to:
- FEAT-1990
- FEAT-1988
labels:
- loops
- orchestration
- built-in
- greenfield
confidence_score: 92
outcome_confidence: 84
score_complexity: 16
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1992: `rn-build` — Core Loop YAML, Loaders, and Integration

## Summary

Author `scripts/little_loops/loops/rn-build.yaml` (the capstone loop from
FEAT-1990), reusing `greenfield-builder`'s front-half phases, wiring the
`scope-epic → goal-cluster → rn-implement(value_ranked)` composition, adding the
`eval_gate` re-entry, registering the loop in the builtin catalog and router
exclusions, and writing all core tests.

## Current Behavior

`rn-build.yaml` does not exist. The phases it would orchestrate (spec parsing →
tech research → design → scope epic → issue refinement → eval harness →
cluster execute → eval gate → synthesize) can only be run manually by invoking
each sub-loop individually with no automation between them.

## Expected Behavior

`ll-loop run rn-build --spec <path>` executes the full recursive project build
pipeline automatically:

- Parses spec, researches tech landscape, generates design artifacts
- Scopes an EPIC + feature stubs; refines seed issues
- Installs an as-a-user eval harness
- Dispatches to `goal-cluster` (which dispatches batches to `rn-implement` with
  `schedule_mode=value_ranked`)
- Runs `eval_gate` with bounded re-entry on failure
- Synthesizes a structured JSON result (accomplished / still-open / recommended
  next batch)

## Motivation

`rn-build` is the capstone loop of the FEAT-1990 feature tree. Without it, the
`scope-epic → goal-cluster → rn-implement` pipeline requires manual invocation of
each loop in sequence with no automated handoff. This loop enables fully automated
spec-to-implementation project generation — the primary user-facing value of the
recursive builder system. It also validates that the three upstream loops
(FEAT-1988, FEAT-1991) compose correctly end-to-end.

## Use Case

A developer has a spec document (`specs/my-project.md`) describing a new tool.
They run `ll-loop run rn-build --spec specs/my-project.md`. The loop handles all
phases end-to-end: tech research, architecture design, issue scoping, incremental
implementation via goal-cluster, and harness-driven quality gates — delivering a
code-complete project without manual orchestration between phases.

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

End-to-end smoke test (step 9): run `ll-loop run rn-build` against a sample spec
and confirm the dispatch path is `goal-cluster → rn-implement` (grep loop logs for
`eval-driven-development` — must not appear) and the harness eval exits 0.

### 5. Design Notes — Batch Sizing

Keep `max_batch_size: 5` (goal-cluster default) for `cluster_execute`. A greenfield
project benefits from whole-project visibility within a batch, but batches of 5 are
large enough to carry meaningful cross-feature context while keeping each
`rn-implement` invocation focused. Users who need larger batches can override via
`orchestration.cluster.max_batch_size` in `.ll/ll-config.json`. This resolves
FEAT-1990 Open Question 2.

## Implementation Steps

1. Port `init`, `tech_research`, `design_artifacts`, `commit_design` phases from `greenfield-builder.yaml`
2. Add `scope_project` (`scope-epic`) and `refine_seed` (`issue-refinement` loop) phases
3. Add `eval_harness` phase (install + customize as-a-user harness; port from `greenfield-builder` phases 5/6)
4. Implement `cluster_execute` → `goal-cluster` handoff; confirm/add `schedule_mode=value_ranked` passthrough for `rn-implement`; set `max_batch_size: 5` (keep default — see Design Notes)
5. Add `eval_gate` with bounded retry counter under `${context.run_dir}/`; re-enter `cluster_execute` on failure
6. Add `synthesize_result` and `done`/`failed` terminals
7. Register `rn-build` in builtin catalog and hard-exclude from `loop-router` + `lib/composer`
8. Write `test_rn_build.py` and update `test_builtin_loops.py`
9. Run `rn-build` against a sample spec (e.g. `specs/sample.md`) and verify harness eval passes and the dispatch path is `goal-cluster → rn-implement` (not `eval-driven-development`)

## Integration Map

### Files to Create
- `scripts/little_loops/loops/rn-build.yaml` — new capstone loop
- `scripts/tests/test_rn_build.py` — test suite following `test_goal_cluster.py` pattern

### Files to Modify
- `scripts/little_loops/loops/loop-router.yaml` — add `rn-build` to hard-exclude set
- `scripts/little_loops/loops/lib/composer.yaml` — add `rn-build` to hard-exclude set
- `scripts/little_loops/loops/README.md` — append `rn-build` entry
- `scripts/tests/test_builtin_loops.py` — add `rn-build` to `expected` set
- `docs/guides/LOOPS_GUIDE.md` — add `rn-build` vs `greenfield-builder` comparison section

### Callers/Importers
- N/A — top-level orchestration loop; excluded from `loop-router` and `lib/composer`; not imported by other loops

### Similar Patterns
- `scripts/little_loops/loops/greenfield-builder.yaml` — shares init/tech_research/design_artifacts phases (port from here)
- `scripts/little_loops/loops/goal-cluster.yaml` (FEAT-1988) — upstream dependency; `cluster_execute` delegates to it
- `scripts/little_loops/loops/loop-composer.yaml` — same router/composer exclusion treatment

### Configuration
- N/A

## Acceptance Criteria

- `ll-loop validate rn-build.yaml` passes (no MR-1/MR-3 errors).
- `ll-loop list` includes `rn-build`.
- `cluster_execute` delegates to `goal-cluster`; per-batch to `rn-implement`
  (`value_ranked`).
- `eval-driven-development` is NOT in the dispatch path.
- `loop-router`/`loop-composer` never offer `rn-build` as a candidate.
- `python -m pytest scripts/tests/test_rn_build.py scripts/tests/test_builtin_loops.py -v` passes.
- End-to-end smoke: `ll-loop run rn-build specs/sample.md` completes with harness eval exit 0 and no `eval-driven-development` in the dispatch log.
- `cluster_execute` passes `max_batch_size: 5` to goal-cluster (default kept; config-overridable).

## Impact

- **Priority**: P3 — orchestration capstone; blocked by FEAT-1988 and FEAT-1991 so not on critical path yet
- **Effort**: Large — 11-state loop YAML, bounded retry logic, cross-loop handoff contract, full test suite
- **Risk**: Medium — depends on two upstream loops; `goal-cluster → rn-implement` handoff contract requires coordination with FEAT-1988 author
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-06 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-07T04:23:02 - `5683ead4-15c0-47d5-b180-859e88eabdf1.jsonl`
- `/ll:format-issue` - 2026-06-07T01:12:10 - `cd798629-9859-4c97-9a7d-e737ade5c9fa.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `2a99295f-12a5-41e0-8be2-477bd51f898c.jsonl`

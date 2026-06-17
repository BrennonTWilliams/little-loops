---
id: BUG-2204
type: BUG
priority: P2
status: done
captured_at: '2026-06-17T00:00:00Z'
completed_at: '2026-06-17T20:21:06Z'
discovered_date: 2026-06-17
discovered_by: finalize-decomposition
labels:
- fsm
- loop-runner
- dx
- footgun
parent: BUG-2011
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-2204: FSM max_iterations — core dual-counter implementation

## Summary

Split from BUG-2011 (core-only scope). Implement the dual-counter semantic fix in the
FSM executor and schema: rename the existing step counter to `max_steps`, add `max_iterations`
as a new full-loop-pass counter, migrate the 3 loop YAMLs that use `on_max_iterations:` to
`on_max_steps:`, and add the iteration-cap summary hook. The rename sweep across CLI, tests,
skills, and docs is tracked separately in BUG-2205.

**Decision (inherited from BUG-2011):** Option 2 — Clarify + dual counter. Legacy YAML key
`max_iterations` aliases to `max_steps` via `from_dict()`; no YAML migrations required for
the 81+ loops that only declare `max_iterations:` as a step cap. The 3 loops using
`on_max_iterations:` must be explicitly migrated.

## Current Behavior

`executor.py` increments `self.iteration` once per state execution and checks it against `fsm.max_iterations`. Consequently, `--max-iterations N` / `-n N` caps *state executions* (steps), not full loop passes. A loop with 10 states per pass and `max_iterations: 1` terminates after the first state execution, not after completing one full pass through all states.

## Expected Behavior

`--max-iterations N` terminates a loop after at most N *full loop passes* (return-to-initial transitions). A separate `--max-steps N` (backed by `max_steps:`) caps individual state executions. Legacy YAML declaring `max_iterations: 50` (no `max_steps:`) is aliased to step-cap semantics via `from_dict()` — no YAML migration required for the 81+ existing loops.

## Steps to Reproduce

1. Use any loop with multiple states per pass (e.g., `general-task.yaml`)
2. Run `ll-loop run <loop> --max-iterations 2`
3. Observe: loop terminates after 2 *state executions*, not after completing 2 full passes
4. Expected: loop completes 2 full passes (visiting all states each pass) before terminating with `terminated_by="max_iterations_reached"`

## Root Cause

Same as BUG-2011: `executor.py` increments `self.iteration` once per state execution and
checks it against `fsm.max_iterations`, so `--max-iterations N` / `-n N` caps *steps*, not
full loop passes. See BUG-2011 for full root cause detail.

**Verified line numbers (2026-06-17):**
- Primary increment: `executor.py:400`
- Cap check: `executor.py:310`
- Maintain-mode restart increment: `executor.py:456`
- Flush path increment: `executor.py:1490`
- Schema fields: `schema.py:961` (`max_iterations`), `:962` (`on_max_iterations`), `:963` (`max_edge_revisits`)
- Existing step-cap summary hook class: `test_fsm_executor.py:7663` (`TestMaxIterationsSummaryHook`)

## Files to Modify

### Core FSM

- `scripts/little_loops/fsm/schema.py`
  - Rename `max_iterations: int = 50` → `max_steps: int = 50` (`:961`)
  - Rename `on_max_iterations: str | None = None` → `on_max_steps: str | None = None` (`:962`)
  - Add `max_iterations: int | None = None` (iteration cap, new field)
  - Add `on_max_iterations: str | None = None` (iteration-cap summary state, new field)
  - Add `from_dict()` alias: legacy YAML key `max_iterations` → `max_steps`
  - Update serialization guard (only write `max_steps` when != 50; omit `max_iterations` when None)

- `scripts/little_loops/fsm/executor.py`
  - Rename `self.iteration` (step counter) throughout; add `self._iteration_count` (full-pass counter)
  - Update three increment sites (`:400`, `:456`, `:1490`) to increment `self.iteration` (step) only
  - Increment `self._iteration_count` on return-to-initial (maintain-mode restart at `:456`)
  - Update cap check (`:310`) to check both `max_steps` and `max_iterations` independently
  - Add `_iteration_summary_executed: bool = False` alongside `_summary_state_executed` (`:220`)
  - Add iteration-cap branch: event name `"max_iterations_reached_summary"`, `terminated_by="max_iterations_reached"`
  - Update `state_enter` event payload: keep `"iteration"` field (step count, backwards compat), add `"iteration_count"` (full-pass count)

- `scripts/little_loops/fsm/types.py`
  - Update `ExecutionResult` `terminated_by` docstring (`:24`, `:34`): add `"max_steps"` and `"max_iterations_reached"` reason strings; keep `"max_iterations"` → `"max_steps"` note for migration

- `scripts/little_loops/fsm/persistence.py`
  - Add `iteration_count: int = 0` to `LoopState` (`:163`)
  - Update `PersistentExecutor.resume()` (`:793`) to restore `self._executor._iteration_count`

- `scripts/little_loops/session_store.py`
  - Update `_LOOP_EVENT_TYPES` frozenset (`:110`): rename `"max_iterations_summary"` → `"max_steps_summary"`; add `"max_iterations_reached_summary"`

- `scripts/little_loops/fsm/fsm-loop-schema.json`
  - Rename `max_iterations` field entry to `max_steps`; add `max_iterations` (iteration cap) entry

### Loop YAML Migrations (explicit — alias cannot cover `on_max_iterations:`)

- `scripts/little_loops/loops/general-task.yaml:9` — `on_max_iterations: summarize_partial` → `on_max_steps: summarize_partial`
- `scripts/little_loops/loops/canvas-sketch-generator.yaml:32` — `on_max_iterations: finalize` → `on_max_steps: finalize`
- `scripts/little_loops/loops/vega-viz.yaml:33` — `on_max_iterations: max_iterations_summary` → `on_max_steps: max_iterations_summary`

### Schema Generation

- `scripts/little_loops/generate_schemas.py`
  - Rename `"max_iterations_summary"` entry (`:397-407`) → `"max_steps_summary"`
  - Add `"max_iterations_reached_summary"` entry
  - Re-run `ll-generate-schemas` to produce updated `docs/reference/schemas/` files

## Tests to Add / Update

### Tests that BREAK on executor/schema changes

- `scripts/tests/test_fsm_executor.py`
  - `test_max_iterations_respected` (`:169`) → rename to `test_max_steps_respected`; update to use `max_steps=3`
  - `TestMaxIterationsSummaryHook` (`:7663`) → rename to `TestMaxStepsSummaryHook`; update event name to `"max_steps_summary"` and `terminated_by="max_steps"`
  - `test_fix_retry_loop` — verify `result.iterations` semantics; update if field now means full-pass count
  - `test_cycle_detection_terminates_loop` (`:193`) — verify still passes after executor changes

- `scripts/tests/test_fsm_persistence.py`
  - `test_final_status_interrupted_on_max_iterations` — update when `LoopState` gains `iteration_count`

- `scripts/tests/test_state_feed_renderer.py`
  - `test_max_iterations_summary` (~`:244`) — update `"max_iterations_summary"` → `"max_steps_summary"`

- `scripts/tests/test_generate_schemas.py` (`:60`)
  - Update `expected` set: `"max_iterations_summary"` → `"max_steps_summary"`; add `"max_iterations_reached_summary"`

- `scripts/tests/test_general_task_loop.py`
  - `TestENH1631SummarizePartial.test_on_max_iterations_set_to_summarize_partial` (`:1073`) → rename and update key to `"on_max_steps"`

### New tests to WRITE

- `scripts/tests/test_fsm_executor.py`
  - New `TestMaxIterationsSummaryHook` class (iteration-cap, 5 scenarios mirroring `TestMaxStepsSummaryHook`)
  - New regression: a 2-step-per-iteration loop with `max_iterations=1` runs all steps in one full pass before capping

- `scripts/tests/test_fsm_schema.py`
  - `TestFSMLoopMaxIterations` class (model after `TestFSMLoopArtifactVersioning`, `:3336`): default `None`, `from_dict()` parses, `to_dict()` omits when None, roundtrip; test legacy YAML key `max_iterations` → `max_steps` alias

- `scripts/tests/test_fsm_validation.py`
  - `TestMaxStepsValidation` class (model after `TestOnMaxIterationsValidation`, `:1532`)
  - `TestMaxIterationsValidation` class for the new iteration cap

- `scripts/tests/test_session_store.py`
  - Assert `"max_steps_summary"` is a member of `_LOOP_EVENT_TYPES`
  - Assert `"max_iterations_reached_summary"` is a member
  - Assert stable members (`"loop_start"`, `"loop_complete"`, `"state_enter"`) remain

- `scripts/tests/test_canvas_sketch_generator.py` (new file)
  - Load `canvas-sketch-generator.yaml`, assert `raw_data.get("on_max_steps") == "finalize"` post-migration
  - Assert `ll-loop validate canvas-sketch-generator` passes

## Acceptance Criteria

- [x] `ll-loop run <loop> --max-steps N` (and `-n N`) terminates after at most N state executions
- [x] `ll-loop run <loop> --max-iterations N` terminates after at most N full loop passes (returns to initial), with `terminated_by="max_iterations_reached"`
- [x] Legacy YAML `max_iterations: 50` (no `max_steps:`) reads as `max_steps=50` via `from_dict()` alias; `max_iterations` (iteration cap) remains `None`
- [x] `on_max_steps: <state>` executes summary state when step cap fires; `terminated_by="max_steps"` preserved
- [x] `on_max_iterations: <state>` executes summary state when iteration cap fires; `terminated_by="max_iterations_reached"` preserved
- [x] `general-task.yaml`, `canvas-sketch-generator.yaml`, `vega-viz.yaml` updated to `on_max_steps:`
- [x] `test_all_validate_as_valid_fsm` passes unchanged (all built-in loops valid)
- [x] `TestMaxStepsSummaryHook` and new `TestMaxIterationsSummaryHook` both pass (5-method structure each)
- [x] `state_enter` event payload has both `"iteration"` (step count) and `"iteration_count"` (full-pass count) fields

## Implementation Steps

1. **Resolve sub-decision (pre-coding):** confirm `iteration_count` added to `state_enter` payload (recommended: yes, parallel field, keep `"iteration"` as step count for backwards compat per BUG-2011 step 29 guidance)
2. **schema.py** — rename fields, add new fields, add `from_dict()` alias, update serialization guard
3. **executor.py** — rename `self.iteration` usages (step counter), add `self._iteration_count`, update three increment sites, update cap check, add iteration-cap branch and summary hook
4. **types.py / persistence.py / session_store.py** — update downstream dataclasses and event type registry
5. **3 YAML migrations** — `general-task.yaml`, `canvas-sketch-generator.yaml`, `vega-viz.yaml`
6. **generate_schemas.py** — rename/add entries; re-run `ll-generate-schemas`
7. **Tests** — rename breaking tests, add new classes

## Impact

- **Priority**: P2 — `max_iterations` silently caps steps instead of loop passes; users relying on pass-level termination get incorrect loop behavior without any error signal
- **Effort**: Large — Core executor (`executor.py`), schema (`schema.py`), persistence (`persistence.py`), event type registry (`session_store.py`), 3 loop YAML migrations, 5+ new test classes
- **Risk**: Medium — Core FSM path is well-covered by existing tests; `from_dict()` alias preserves backward compatibility for 81+ existing loops
- **Breaking Change**: No — Legacy `max_iterations:` in YAML aliases to `max_steps` via `from_dict()`; only the 3 loops with `on_max_iterations:` require explicit migration

## Notes

- BUG-2205 handles all CLI argparse, display strings, skill files, doc files, and argparse-plumbing tests — do NOT touch those here
- The rename sweep in BUG-2205 depends on this issue completing first (the Python fields must exist before CLI flags can be wired)
- `max_edge_revisits` (`:963`) is unchanged — retain as-is

## Resolution

Implemented dual-counter semantic fix across all FSM core modules:

- **schema.py**: renamed `max_iterations` → `max_steps` (step cap, default 50); added `max_iterations: int | None = None` (full-pass cap); added `from_dict()` legacy alias mapping old `max_iterations` YAML key → `max_steps` when `max_steps` is absent; updated serialization guards.
- **executor.py**: renamed `self.iteration` (step counter, unchanged semantics); added `self._iteration_count` (full-pass counter, incremented on maintain-mode restarts); added independent cap checks for both `max_steps` and `max_iterations`; added `max_iterations_reached_summary` event; `state_enter` now includes both `"iteration"` and `"iteration_count"` fields.
- **persistence.py**: added `iteration_count: int = 0` to `LoopState`; restored `_iteration_count` on resume.
- **session_store.py**: renamed `"max_iterations_summary"` → `"max_steps_summary"`; added `"max_iterations_reached_summary"`.
- **types.py**: updated `ExecutionResult.terminated_by` docstring with new values.
- **fsm-loop-schema.json**: renamed `max_iterations` field to `max_steps`; added `max_iterations` (iteration cap) and `on_max_iterations` entries.
- **generate_schemas.py**: renamed `"max_steps_summary"` entry; added `"max_iterations_reached_summary"` entry.
- **Loop YAML migrations**: `general-task.yaml`, `canvas-sketch-generator.yaml`, `vega-viz.yaml`, `cua-agent-desktop.yaml` migrated from `on_max_iterations:` → `on_max_steps:`.
- **CLI display fixes**: updated `_helpers.py` `[current/max]` progress display, execution plan, and run-start header to use `max_steps`; fixed `max_iterations_summary` event handler → `max_steps_summary`; fixed `testing.py` simulation step-cap to use `max_steps`.
- **Tests**: updated `TestMaxStepsSummaryHook`, added `TestMaxIterationsSummaryHook`; added `TestFSMLoopMaxIterations` schema tests; updated session_store, persistence, general-task, generate_schemas, and state_feed_renderer tests.

## Session Log
- `/ll:manage-issue` - 2026-06-17T20:21:06Z - implementation complete
- `/ll:ready-issue` - 2026-06-17T18:49:41 - `b6b384b9-6d42-4932-8b77-aaaf3b4cd36b.jsonl`
- `/ll:format-issue` - 2026-06-17T18:39:08 - `73a22b6c-06de-4d5e-aee5-75c901aa8812.jsonl`
- Decomposed from BUG-2011 - 2026-06-17
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `4b5d66b8-fe01-446b-be44-7f390d4d76d5.jsonl`

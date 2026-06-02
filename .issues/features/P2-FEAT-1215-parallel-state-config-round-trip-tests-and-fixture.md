---
id: FEAT-1215
priority: P2

discovered_date: "2026-04-21"
discovered_by: issue-size-review
confidence_score: 78
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
size: Very Large
parent: FEAT-1213
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1215: Parallel State Config Round-Trip Tests and Fixture

## Summary

Add `TestParallelStateConfig` class to `test_fsm_schema.py` and create the `parallel-loop.yaml` fixture. Scoped to round-trip serialization and fixture-load validation.

## Parent Issue

Decomposed from FEAT-1213: Parallel Schema Tests and Fixture

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `ParallelStateConfig` is added to `StateConfig`, these tests verify round-trips and the fixture loads cleanly.

**Goal**: Add `TestParallelStateConfig` to `test_fsm_schema.py` and create `parallel-loop.yaml`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema.py -x -k "TestParallelStateConfig or test_load_valid_parallel_yaml"` passes green.

## Proposed Solution

### test_fsm_schema.py — Add TestParallelStateConfig class

Model after `TestSubLoopStateConfig:1817`:

- Round-trip `to_dict()` / `from_dict()` with all fields
- `from_dict()` with only required fields (defaults applied)
- `StateConfig` with `parallel:` serializes `parallel` key; without, key absent
- `from_dict()` deserialization of aliased routing fields (`on_partial`, etc.) if FEAT-1074 uses aliases — mirror `TestSubLoopStateConfig`'s alias test at line 1857
- No-spurious-error guard: assert a `parallel` state does not trigger a "no transition" validation error (mirror `test_sub_loop_state_no_transition_error:1884`)
- Explicit fixture-load test added to `TestLoadAndValidate` as `test_load_valid_parallel_yaml`: accept `fsm_fixtures: Path` parameter, use `fsm_fixtures / "parallel-loop.yaml"`, assert `warnings == []`

Import: Add `ParallelStateConfig` to the import block at `scripts/tests/test_fsm_schema.py:16-24` (from `little_loops.fsm.schema`). If FEAT-1074 does NOT create a standalone class (instead uses fields on `StateConfig`), drop this import and test via `StateConfig` directly.

### New fixture: scripts/tests/fixtures/fsm/parallel-loop.yaml

```yaml
name: parallel-loop
initial: fan_out
states:
  fan_out:
    parallel:
      items: "${captured.queue.output}"
      loop: refine-to-ready-issue
      max_workers: 2
      isolation: thread
      fail_mode: collect
      context_passthrough: false
    route:
      on_yes: done
      on_partial: done
      on_no: done
  done:
    next: ~
```

Note: `name:` and `initial:` are required top-level fields for `FSMLoop` — match the concision of `valid-loop.yaml`.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` (after `TestSubLoopStateConfig:1817`); add `test_load_valid_parallel_yaml` to `TestLoadAndValidate` (mirrors `test_load_valid_yaml:1544`)

### Files to Create
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture

### Dependent Files
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` and `StateConfig.parallel` field (FEAT-1074)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — FEAT-1074 must add `parallel` under `stateConfig.properties` for fixture load test to pass
- `scripts/tests/conftest.py:31-33` — defines a parallel `fsm_fixtures` fixture (same name, same resolved path as the local fixture at `test_fsm_schema.py:33-36`). Pytest resolves the module-local fixture first within `test_fsm_schema.py`, so `test_load_valid_parallel_yaml` will use the local definition — no conflict, but both must remain consistent if the fixture directory ever moves.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:115` — hardcoded fixture count (`"8 files"`) is already stale (9 files exist); adding `parallel-loop.yaml` makes it 10. **FEAT-1214 owns this update** — not in scope for FEAT-1215, but FEAT-1215 must ship before FEAT-1214's count update is accurate.

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1817` — `TestSubLoopStateConfig` — round-trip pattern
- `scripts/tests/test_fsm_schema.py:1544` — `TestLoadAndValidate.test_load_valid_yaml` — fixture-load pattern
- `scripts/tests/test_fsm_schema.py:1884` — `test_sub_loop_state_no_transition_error` — no-spurious-error guard
- `scripts/tests/test_fsm_schema.py:33-36` — `fsm_fixtures` pytest fixture

### Validation Entry Points
- `load_and_validate(path: Path) -> tuple[FSMLoop, list[ValidationError]]` at `validation.py:517` — returns `(loop, warnings)`, raises `ValueError` on ERROR-severity issues. Assert `warnings == []`.

### Regression Surfaces
- `scripts/tests/test_fsm_schema.py:780` (`TestFSMValidation`) — `len(error_list) == 0` assertions; `ParallelStateConfig` must not emit errors for non-parallel loops

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` schema, `StateConfig.parallel` field, JSON schema update)

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified 2026-04-21 against current tree:_

- All cited line numbers are exact matches at the time of refinement:
  - `TestSubLoopStateConfig` → `test_fsm_schema.py:1817`
  - `test_sub_loop_state_no_transition_error` → `test_fsm_schema.py:1884` (constructs `FSMLoop` directly, calls `validate_fsm(fsm)`, asserts `not any("no transition" in m.lower() for m in error_messages)`)
  - `test_load_valid_yaml` → `test_fsm_schema.py:1544` (inside `TestLoadAndValidate` opening at line 1541)
  - `fsm_fixtures` fixture → `test_fsm_schema.py:34` (def line; covers lines 33-36)
  - `load_and_validate` → `validation.py:517`, signature `def load_and_validate(path: Path) -> tuple[FSMLoop, list[ValidationError]]`
  - `TestFSMValidation` → `test_fsm_schema.py:780`; representative zero-error assertion at line 789 (`error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]; assert len(error_list) == 0`)
- Current import block (`test_fsm_schema.py:16-24`) from `little_loops.fsm.schema`: `DEFAULT_LLM_MODEL`, `EvaluateConfig`, `FSMLoop`, `LLMConfig`, `LoopConfigOverrides`, `RouteConfig`, `StateConfig`. `ParallelStateConfig` is not yet imported anywhere — must be added when FEAT-1074 lands.
- **FEAT-1074 status (blocking)**: `ParallelStateConfig` does not exist in `scripts/little_loops/fsm/schema.py`; `StateConfig` has no `parallel` field; `scripts/little_loops/fsm/fsm-loop-schema.json` has no `parallel` entry under `stateConfig.properties`. FEAT-1215 cannot begin until FEAT-1074 merges.
- **Fixture convention note**: existing `valid-loop.yaml` terminates via `done: {terminal: true}` (not `next: ~`). For stylistic consistency with the established fixture, consider rendering the `done` state in `parallel-loop.yaml` as `done: {terminal: true}` unless FEAT-1074 requires the explicit `next: ~` form. Confirm against the JSON schema once FEAT-1074 lands. `valid-loop.yaml` is 8 lines; `parallel-loop.yaml` should stay similarly concise.
- Other fixtures in `scripts/tests/fixtures/fsm/`: `incomplete-loop.yaml`, `invalid-initial-state.yaml`, `invalid-yaml-syntax.yaml`, `non-dict-root.yaml`, `missing-name.yaml`, `missing-states.yaml`, `loop-with-unreachable-state.yaml`, `custom-on-routing.yaml` — none currently exercise a `parallel:` block.
- **`TestSubLoopStateConfig` shape (test-coverage template)**: the class at `test_fsm_schema.py:1817-1901` contains 9 test methods — not a single round-trip. `TestParallelStateConfig` should follow the same granularity. Ordered list:
  1. `test_state_config_with_loop_field` — field setting
  2. `test_state_config_context_passthrough` — secondary field setting
  3. `test_state_config_loop_defaults_to_none` — default value / backward compat
  4. `test_to_dict_includes_loop_when_set` — serialization emits key
  5. `test_to_dict_excludes_loop_when_none` — serialization omits default
  6. `test_from_dict_with_loop` — deserialization + one alias (`on_success` → `on_yes`) at line 1857
  7. `test_from_dict_without_loop` — deserialization defaults
  8. `test_loop_and_action_mutual_exclusion` — mutex validation (**FEAT-1216 owns parallel analogue; NOT in FEAT-1215 scope**)
  9. `test_sub_loop_state_no_transition_error` — no-spurious-error guard
- **Alias test clarification**: line 1857 tests the `on_success` → `on_yes` alias (legacy field name mapping), not `on_partial`. The issue's reference to `on_partial` as an example alias is aspirational — apply the same legacy-name → canonical-name pattern to whichever aliases FEAT-1074 exposes on `ParallelStateConfig`. If FEAT-1074 introduces no new aliases, this test can be skipped.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema.py -x -k "TestParallelStateConfig or test_load_valid_parallel_yaml"` passes green
- `parallel-loop.yaml` fixture round-trips without validation errors (`warnings == []`)
- `TestParallelStateConfig` includes the no-spurious-error guard mirroring `test_sub_loop_state_no_transition_error:1884`
- Existing `TestFSMValidation` error-count assertions stay green (no regressions)

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 78/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 is a hard blocker in practice.** Despite the high readiness score (driven by excellent specification quality), no code can be written until FEAT-1074 lands. `ParallelStateConfig` does not exist, `StateConfig` has no `parallel` field, and the JSON schema has no `parallel` entry.
- **Fixture done-state style is unresolved.** The issue defers `terminal: true` vs `next: ~` to post-FEAT-1074 JSON schema inspection — trivial to resolve once FEAT-1074 lands.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1217: Parallel Loop YAML Fixture and Fixture-Load Test
- FEAT-1218: TestParallelStateConfig Test Class

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `59852d6e-fcd5-41f5-b554-577001c3b013.jsonl`
- `/ll:refine-issue` - 2026-04-21T06:42:53 - `84668414-fc0f-424f-92fc-efc6f07976b3.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `8e7c40d7-bfd7-48ef-a3bf-2ee5b46f5ff7.jsonl`
- `/ll:wire-issue` - 2026-04-21T06:39:15 - `ad90cf92-c999-44b0-a656-cc334f48100e.jsonl`
- `/ll:refine-issue` - 2026-04-21T06:33:33 - `4735ac39-1844-4597-bab6-b9a416970e4d.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `7b6f3646-002b-4241-b60d-d6d09e155cee.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `3602700c-68f5-4249-826d-6c2ed2f1d25e.jsonl`

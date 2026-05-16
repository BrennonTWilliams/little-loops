---
discovered_date: "2026-04-20"
discovered_by: issue-size-review

size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1077
---

# FEAT-1200: Parallel State Schema, Validation, and Fuzz Tests

## Summary

Extend `test_fsm_schema.py`, `test_fsm_validation.py`, and `test_fsm_schema_fuzz.py` with `parallel:` state coverage, and create the `parallel-loop.yaml` fixture. Depends only on FEAT-1074 (schema/validation implementation).

## Parent Issue

Decomposed from FEAT-1077: Parallel State Tests

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `ParallelStateConfig` is added to `StateConfig`, these tests verify round-trips, mutual exclusion rules, the no-transition guard exemption, and fuzz coverage.

**Goal**: Add tests to three existing test files and create one new fixture, all scoped to the schema/validation layer.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema_fuzz.py -x` passes green.

## Proposed Solution

### test_fsm_schema.py — Add TestParallelStateConfig class

Model after `TestSubLoopStateConfig:1817`:

- Round-trip `to_dict()` / `from_dict()` with all fields
- `from_dict()` with only required fields (defaults applied)
- `StateConfig` with `parallel:` serializes `parallel` key; without, key absent
- Explicit fixture load test for `parallel-loop.yaml`: accept `fsm_fixtures: Path` parameter, use `fsm_fixtures / "parallel-loop.yaml"` — no auto-discovery occurs; must be explicitly named in a test method within `TestLoadAndValidate`

### test_fsm_schema.py — Add TestParallelMutualExclusion class

Model after `test_loop_and_action_mutual_exclusion:1866`:

- `parallel` + `action` → validation error
- `parallel` + `loop` → validation error
- `parallel` + `next` → validation error
- `max_workers: 0` → validation error
- `isolation: "invalid"` → validation error
- `fail_mode: "invalid"` → validation error

### test_fsm_validation.py — Add no-transition guard test

Add one test (file is currently 266 lines with two classes: `TestExtraRoutesReachability:18`, `TestRateLimitFieldValidation:69`):

- Assert that a `parallel:` state with routing does NOT trigger the no-transition guard (the guard at `validation.py:271` gains `and not has_parallel` as part of FEAT-1074)

### test_fsm_schema_fuzz.py — Add parallel key

Insert after the `route` block ending at line 173 (line 174 is blank), before `# Add unexpected fields` at line 175:

```python
# Add parallel config
if draw(st.booleans()):
    state["parallel"] = draw(
        st.one_of(
            st.fixed_dictionaries({
                "items": st.text(min_size=1, max_size=100),
                "loop": st.text(min_size=1, max_size=50),
            }),
            st.integers(),
            st.text(),
            st.none(),
        )
    )
```

### New fixture: scripts/tests/fixtures/fsm/parallel-loop.yaml

```yaml
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

After creating the fixture, update `docs/development/TESTING.md:115` which hardcodes `"FSM YAML fixtures (8 files)"` — the current file count is 9 (the doc is already stale by one), and the new fixture makes it 10. Update to `"FSM YAML fixtures (10 files)"` (not "9 → 10", but "8 → 10").

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` (after `TestSubLoopStateConfig:1817`) and `TestParallelMutualExclusion` (after `test_loop_and_action_mutual_exclusion:1866`)
- `scripts/tests/test_fsm_validation.py` — Add one `parallel:` no-transition-guard test
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy after the route block (ends at line 173), before line 175 `# Add unexpected fields`
- `docs/development/TESTING.md:115` — Update fixture count from 9 to 10

### Files to Create
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture

### Dependent Files
- `scripts/little_loops/fsm/schema.py:180` — `ParallelStateConfig`, `StateConfig.parallel` field (FEAT-1074; added after existing `StateConfig` field block around `schema.py:233`)
- `scripts/little_loops/fsm/validation.py:271` — No-transition guard; gains `and not has_parallel` (FEAT-1074)
- `scripts/little_loops/fsm/fsm-loop-schema.json:175-320` — `stateConfig` definition uses `"additionalProperties": false`; loading `parallel-loop.yaml` via `load_and_validate` will fail until FEAT-1074 adds `parallel` to `stateConfig.properties` — **blocker for fixture validation** (FEAT-1074 scope, but a hard runtime dependency for this issue's fixture round-trip test)

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1817` — `TestSubLoopStateConfig` — round-trip pattern
- `scripts/tests/test_fsm_schema.py:1866` — `test_loop_and_action_mutual_exclusion` — mutual exclusion template
- `scripts/tests/test_fsm_schema.py:1884` — `test_sub_loop_state_no_transition_error` — direct template for the `test_fsm_validation.py` no-transition guard test (asserts no "no transition" error fires for a `loop:` state with routing)
- `scripts/tests/test_fsm_schema_fuzz.py:173` — `route` block end in `malformed_state_config` strategy (insertion point is between this and line 175 `# Add unexpected fields`)

### Regression Surfaces
- `scripts/tests/test_fsm_schema.py:780` (`TestFSMValidation`) — `len(error_list) == 0` assertions on minimal valid FSMs; `ParallelStateConfig` added to `StateConfig` must not emit validation errors for non-parallel loops

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Add `ParallelStateConfig` to the import block at `scripts/tests/test_fsm_schema.py:16-24` — the new `TestParallelStateConfig` class constructs `ParallelStateConfig` directly from `little_loops.fsm.schema` (not via `little_loops.fsm.__init__`, which deliberately excludes it)
2. Add `ParallelStateConfig` to the import block at `scripts/tests/test_fsm_validation.py:9` — the no-transition guard test must construct a `StateConfig(parallel=ParallelStateConfig(...), route=...)` object
3. Verify `scripts/little_loops/fsm/fsm-loop-schema.json` has `parallel` in `stateConfig.properties` before running the fixture load test — if FEAT-1074 is not yet complete, the `TestLoadAndValidate` fixture test for `parallel-loop.yaml` will fail with an `additionalProperties` schema validation error
4. `test_fsm_schema.py:1884` (`test_sub_loop_state_no_transition_error`) — use this as the direct template when writing the no-transition guard test in `test_fsm_validation.py`; mirror its pattern but substitute `parallel=ParallelStateConfig(...)` for `loop="child"`
5. The new fuzz strategy block does not introduce a new test method, so no `@pytest.mark.slow` change is needed — the parallel block is inserted into the existing `malformed_state_config()` strategy function, which is consumed by tests already marked `@pytest.mark.slow` at lines 299, 324, 348, 378, 406, 432

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` schema, `StateConfig.parallel` field, `validation.py` no-transition guard update)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema_fuzz.py -x` passes green
- `parallel-loop.yaml` fixture round-trips without validation errors
- `TestParallelMutualExclusion` covers all 6 invalid combinations
- Fuzz test includes `parallel` key in `malformed_state_config` strategy
- `docs/development/TESTING.md:115` updated to reflect new fixture count
- Existing `TestFSMValidation` error-count assertions stay green (no regressions)

## Labels

`fsm`, `parallel`, `tests`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 incomplete (hard blocker for passing tests)**: `ParallelStateConfig` does not yet exist in `schema.py`, the `has_parallel` guard is absent from `validation.py:271`, and `parallel` is not in `fsm-loop-schema.json`. Tests can be written in advance but will not pass until FEAT-1074 ships.
- **TESTING.md fixture count already stale**: `docs/development/TESTING.md:115` says "8 files" but 9 fixtures already exist — verify count is 9 before updating to 10.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session

### Decomposed Into
- FEAT-1213: Parallel Schema Tests and Fixture
- FEAT-1214: Parallel Validation, Fuzz, and Doc Tests

## Session Log
- `/ll:refine-issue` - 2026-04-21T06:05:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a265903-88c7-42fb-834d-7570e407e2f1.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c673dd08-c18f-45ea-8b10-ac013e832de1.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/703c068c-80d2-438e-af63-fd69424ac458.jsonl`
- `/ll:wire-issue` - 2026-04-21T06:01:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c807f52-c768-4ac1-8191-d75a4df290fc.jsonl`
- `/ll:refine-issue` - 2026-04-21T05:55:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62089722-1f5f-490c-8649-3eeea573c9bc.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb2a4d4b-681c-4336-8ebc-dacfae9712d8.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc287f64-ac41-4ff3-967d-f2d38642710b.jsonl`

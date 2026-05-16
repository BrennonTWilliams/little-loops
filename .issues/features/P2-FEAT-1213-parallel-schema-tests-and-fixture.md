---
id: FEAT-1213
priority: P2

discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 72
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
parent: FEAT-1200
status: done
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1213: Parallel Schema Tests and Fixture

## Summary

Add `TestParallelStateConfig` and `TestParallelMutualExclusion` classes to `test_fsm_schema.py`, and create the `parallel-loop.yaml` fixture file. Scoped to the schema round-trip and mutual-exclusion layer.

## Parent Issue

Decomposed from FEAT-1200: Parallel State Schema, Validation, and Fuzz Tests

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `ParallelStateConfig` is added to `StateConfig`, these tests verify round-trips, mutual exclusion rules, and the fixture load.

**Goal**: Add two test classes to `test_fsm_schema.py` and create `parallel-loop.yaml`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema.py -x -k "Parallel"` passes green.

## Proposed Solution

### test_fsm_schema.py — Add TestParallelStateConfig class

Model after `TestSubLoopStateConfig:1817`:

- Round-trip `to_dict()` / `from_dict()` with all fields
- `from_dict()` with only required fields (defaults applied)
- `StateConfig` with `parallel:` serializes `parallel` key; without, key absent
- Explicit fixture load test for `parallel-loop.yaml`: accept `fsm_fixtures: Path` parameter, use `fsm_fixtures / "parallel-loop.yaml"` — no auto-discovery occurs; must be explicitly named in a test method within `TestLoadAndValidate`

Import: Add `ParallelStateConfig` to the import block at `scripts/tests/test_fsm_schema.py:16-24` (from `little_loops.fsm.schema`, not `little_loops.fsm.__init__`).

### test_fsm_schema.py — Add TestParallelMutualExclusion class

Model after `test_loop_and_action_mutual_exclusion:1866`:

- `parallel` + `action` → validation error
- `parallel` + `loop` → validation error
- `parallel` + `next` → validation error
- `max_workers: 0` → validation error
- `isolation: "invalid"` → validation error
- `fail_mode: "invalid"` → validation error

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

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelStateConfig` (after `TestSubLoopStateConfig:1817`) and `TestParallelMutualExclusion` (after `test_loop_and_action_mutual_exclusion:1866`)

### Files to Create
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — New fixture

### Dependent Files
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` and `StateConfig.parallel` field (FEAT-1074). `StateConfig` begins at line 180; `ParallelStateConfig` does not yet exist and will be inserted near `SubLoopStateConfig` — locate at implementation time.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — 473 lines total; no `parallel` token present. FEAT-1074 must add `parallel` under `stateConfig.properties` for fixture load test to pass. Locate `stateConfig.properties` block at implementation time (prior estimate of lines 175-320 is unverified).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py` — `validate_fsm`, `load_and_validate`, `ValidationError` live here. `_validate_state_action` is a **free function at line 195** (not a method) that currently emits `"'loop' and 'action' are mutually exclusive — a sub-loop state cannot also have an action"` at lines 217-225. FEAT-1074 must extend this (or add a sibling `_validate_state_parallel`) so the parallel mutual-exclusion errors contain substrings like `"parallel"` and `"action"` — this is what `TestParallelMutualExclusion` will `any("parallel" in m and "action" in m for m in error_messages)` against.

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1817` — `TestSubLoopStateConfig` — round-trip pattern
- `scripts/tests/test_fsm_schema.py:1866` — `test_loop_and_action_mutual_exclusion` — mutual exclusion template
- `scripts/tests/test_fsm_schema.py:1884` — `test_sub_loop_state_no_transition_error` — "no spurious error" guard; mirror for `TestParallelStateConfig` to assert a `parallel` state does not trigger a "no transition" validation error
- `scripts/tests/test_fsm_schema.py:33-36` — `fsm_fixtures` pytest fixture (resolves to `Path(__file__).parent / "fixtures" / "fsm"`); required parameter for the fixture-load test

### Validation Entry Points
- Inline-construction tests (mutual exclusion, round-trip) use `validate_fsm(fsm) -> list[ValidationError]` — returns errors without raising
- Fixture-load test should use `load_and_validate(path: Path) -> tuple[FSMLoop, list[ValidationError]]` (defined at `validation.py:517`; returns `(loop, warnings)` — raises `ValueError` on ERROR-severity issues). Assert `warnings == []`; see `TestLoadAndValidate.test_load_valid_yaml` at `test_fsm_schema.py:1544`
- Errors are compared via `[str(e) for e in errors]` then `any("<field_a>" in m and "<field_b>" in m for m in error_messages)` — follow this string-match convention for the 3 mutual-exclusion cases

### Regression Surfaces
- `scripts/tests/test_fsm_schema.py:780` (`TestFSMValidation`) — `len(error_list) == 0` assertions; `ParallelStateConfig` must not emit errors for non-parallel loops
- `TestSubLoopStateConfig` currently contains 8 methods (lines 1820–1901); `TestParallelStateConfig` will add a parallel class of similar shape rather than extending this one

### Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-04-21 — verified against current repo state:_

- **Existing fixture style to match** — `scripts/tests/fixtures/fsm/valid-loop.yaml` is ~10 lines (`name/initial/states` only). `parallel-loop.yaml` should match this concision; the current draft in Proposed Solution omits `name` and `initial` at the top level — add those for fixture validity.
- **`load_and_validate` contract** — defined at `validation.py:517` with signature `(path: Path) -> tuple[FSMLoop, list[ValidationError]]`. Returns `(loop, warnings)` — ERROR-severity issues raise `ValueError`, so fixture-load test should only need `assert warnings == []`.
- **Idiomatic integration test** — Consider adding `test_load_valid_parallel_yaml` to `TestLoadAndValidate` (mirrors `test_load_valid_yaml` at `test_fsm_schema.py:1544`). This is the conventional place for fixture-load tests in this file; the acceptance-criteria "fixture load test" can live here rather than inside `TestParallelStateConfig`.
- **Error-message substring convention** — `test_loop_and_action_mutual_exclusion:1866-1882` uses `error_messages = [str(e) for e in validate_fsm(fsm)]` then `any("loop" in m and "action" in m for m in error_messages)`. `TestParallelMutualExclusion` should follow this exact shape for each of its 3 field-conflict cases; the 3 value-invalid cases (`max_workers=0`, bad `isolation`, bad `fail_mode`) follow the same `any(...)` pattern but match on the offending field + value.
- **`on_success` alias** — `TestSubLoopStateConfig` tests `from_dict` deserialization of the `on_success` alias (line 1857). If FEAT-1074's parallel routing uses an aliased field (`on_partial`, etc.), `TestParallelStateConfig.from_dict` tests should exercise the alias path similarly.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` schema, `StateConfig.parallel` field, JSON schema update)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema.py -x -k "Parallel"` passes green
- `parallel-loop.yaml` fixture round-trips without validation errors (asserted via `load_and_validate(...)` returning `warnings == []`)
- `TestParallelMutualExclusion` covers all 6 invalid combinations (parallel+action, parallel+loop, parallel+next, max_workers=0, invalid isolation, invalid fail_mode)
- `TestParallelStateConfig` includes the no-spurious-error guard mirroring `test_sub_loop_state_no_transition_error:1884`
- Existing `TestFSMValidation` error-count assertions stay green (no regressions)

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 72/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 95/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 is the only blocker, but it's a hard one**: until `ParallelStateConfig` exists in `schema.py` and `parallel` appears in `fsm-loop-schema.json`, the test file will fail at import time. Queue this issue immediately after FEAT-1074 ships.
- **Fixture YAML needs `name:` and `initial:`**: The draft in Proposed Solution omits top-level required fields for `FSMLoop`. Fix at implementation time before running `load_and_validate`.
- **ParallelStateConfig import assumption**: `SubLoopStateConfig` is NOT a separate class — sub-loop uses fields directly on `StateConfig`. If FEAT-1074 takes the same approach, the `from little_loops.fsm.schema import ParallelStateConfig` import must be dropped and tests rewritten to use `StateConfig` directly.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-21T06:31:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b6f3646-002b-4241-b60d-d6d09e155cee.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7177f923-7f11-42d0-95ca-9b715fe7bee8.jsonl`
- `/ll:refine-issue` - 2026-04-21T06:25:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dca4cd60-015e-4132-aa53-eea350eb8cac.jsonl`
- `/ll:wire-issue` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5fcdde7-c7de-41ca-ad67-62169e9eacc7.jsonl`
- `/ll:refine-issue` - 2026-04-21T06:14:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5fcdde7-c7de-41ca-ad67-62169e9eacc7.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc287f64-ac41-4ff3-967d-f2d38642710b.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d866e943-cc77-406c-8d4d-e66fbb334ef7.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b6f3646-002b-4241-b60d-d6d09e155cee.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session (score: 11/11 Very Large)

### Decomposed Into
- FEAT-1215: Parallel State Config Round-Trip Tests and Fixture
- FEAT-1216: Parallel Mutual Exclusion Validation Tests

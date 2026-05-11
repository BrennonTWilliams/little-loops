---
id: FEAT-1219
priority: P2

discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1214
---

# FEAT-1219: Add Parallel State No-Transition Guard and Fuzz Tests

## Summary

Add a no-transition guard test for `parallel:` states to `test_fsm_validation.py` and extend the `malformed_state_config` fuzz strategy in `test_fsm_schema_fuzz.py` with a `parallel` key.

## Parent Issue

Decomposed from FEAT-1214: Parallel Validation, Fuzz, and Doc Tests

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `validation.py:271` gains `and not has_parallel`, the guard test verifies it fires correctly. The fuzz extension adds parallel-shaped malformed inputs to existing coverage.

**Goal**: Add one test to `test_fsm_validation.py` and one fuzz block to `test_fsm_schema_fuzz.py`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema_fuzz.py -x` passes green.

## Proposed Solution

### test_fsm_validation.py — Add no-transition guard test

Add one test (file currently 266 lines with two classes: `TestExtraRoutesReachability:18`, `TestRateLimitFieldValidation:69`):

- Assert that a `parallel:` state with routing does NOT trigger the no-transition guard (the guard at `validation.py:271` gains `and not has_parallel` as part of FEAT-1074)

Import: Add `ParallelStateConfig` to the import block at `scripts/tests/test_fsm_validation.py:9`.

Use `scripts/tests/test_fsm_schema.py:1884` (`test_sub_loop_state_no_transition_error`) as the direct template — mirror its pattern but substitute `parallel=ParallelStateConfig(...)` for `loop="child"`.

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

Note: No `@pytest.mark.slow` change needed — this block is inserted into the existing `malformed_state_config()` strategy, consumed by tests already marked at lines 299, 324, 348, 378, 406, 432.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_validation.py` — Add one `parallel:` no-transition-guard test
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy after the route block (ends at line 173), before line 175 `# Add unexpected fields`

### Dependent Files
- `scripts/little_loops/fsm/validation.py:271` — No-transition guard; gains `and not has_parallel` (FEAT-1074)
- `scripts/little_loops/fsm/fsm-loop-schema.json:289-320` — Must add `parallel` to `stateConfig.properties` before `additionalProperties: false` at line 320 (FEAT-1074 scope, gating this issue)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py:881-893` — `test_state_with_no_transition` — positive assertion (`"no transition defined"` fires for a plain non-routing state); must not break after FEAT-1074 adds `has_parallel` to the guard
- `scripts/tests/test_fsm_schema.py:895-907` — `test_on_partial_only_shorthand_is_valid` — negative assertion (`"no transition defined"` does not fire for `on_partial` routing); regression baseline
- `scripts/tests/test_review_loop.py:127-137` — `test_v9_state_with_no_transition` — V-9 guard test asserts by path; must not break
- `scripts/tests/test_builtin_loops.py:36-44` — `test_all_validate_as_valid_fsm` — runs `validate_fsm` for every built-in loop YAML; full regression check (include in the test run: `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema_fuzz.py scripts/tests/test_fsm_schema.py::TestStateTransitionValidation scripts/tests/test_builtin_loops.py -x`)

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1884` — `test_sub_loop_state_no_transition_error` — direct template for the no-transition guard test
- `scripts/tests/test_fsm_schema_fuzz.py:173` — `route` block end (insertion point)

### Codebase Research Findings

**Current no-transition guard** (`validation.py:266–278`):

```python
has_next = state.next is not None
has_terminal = state.terminal
has_loop = state.loop is not None

if not has_shorthand and not has_route and not has_next and not has_terminal and not has_loop:
    errors.append(
        ValidationError(
            message="State has no transition defined. Add routing, 'next', "
            "or mark as 'terminal: true'",
            path=path,
        )
    )
```

FEAT-1074 must add `has_parallel = state.parallel is not None` and extend the guard with `and not has_parallel`. `ParallelStateConfig` is **not yet present** in `scripts/little_loops/fsm/schema.py` — introduced by FEAT-1074.

**Template test to mirror** (`test_fsm_schema.py:1884–1901`):

```python
def test_sub_loop_state_no_transition_error(self) -> None:
    """A state with loop: set should not trigger 'no transition' error."""
    fsm = FSMLoop(
        name="test",
        initial="run_child",
        states={
            "run_child": StateConfig(
                loop="child",
                on_yes="done",
                on_no="error",
            ),
            "done": StateConfig(terminal=True),
            "error": StateConfig(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    error_messages = [str(e) for e in errors]
    assert not any("no transition" in m.lower() for m in error_messages)
```

Mirror this in `test_fsm_validation.py`, substituting `parallel=ParallelStateConfig(items="...", loop="...")` for `loop="child"`.

**test_fsm_validation.py structure** (verified):
- Imports at lines 9–10: `FSMLoop, StateConfig` from `schema`; `ValidationSeverity, validate_fsm` from `validation`. Add `ParallelStateConfig` to the schema import on line 9.
- Classes: `TestExtraRoutesReachability` (line 18, 3 methods) and `TestRateLimitFieldValidation` (line 69, 9 methods, ends at line 266).
- Neither existing class fits thematically. Add a new class `TestParallelStateValidation` at line 267 (EOF), containing the single no-transition guard test method. Follow the one-class-per-feature convention already used in this file.

**Fuzz strategy context** (`test_fsm_schema_fuzz.py`):
- `malformed_state_config` strategy spans lines 134–186 (the draw function)
- Route block: `if draw(st.booleans()): state["route"] = draw(malformed_route_config())` ends at line 173
- Blank line 174; `# Add unexpected fields` at line 175 — insert the `parallel` block between these
- All six `@pytest.mark.slow` consumer lines (299, 324, 348, 378, 406, 432) verified — no marker changes needed

## Dependencies

- **FEAT-1074** must be complete (`validation.py` no-transition guard update; adds `ParallelStateConfig` to `schema.py`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema_fuzz.py -x` passes green
- No-transition guard test confirms `parallel:` states with routing skip the guard
- Fuzz test includes `parallel` key in `malformed_state_config` strategy
- No regressions in existing fuzz or validation tests

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 not implemented**: `ParallelStateConfig` does not exist in `schema.py` and `has_parallel` is absent from `validation.py:271`. The test imports `ParallelStateConfig` which doesn't exist yet, and the guard it verifies hasn't been added. FEAT-1074 must land before this issue can be coded.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session (score: 9/11 — Very Large)

### Decomposed Into
- FEAT-1221: Add Parallel State No-Transition Guard Test
- FEAT-1222: Add Parallel Key to Malformed State Config Fuzz Strategy

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-21T08:09:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98f68405-0917-4592-af11-ba9a9de2ae0c.jsonl`
- `/ll:confidence-check` - 2026-04-21T08:06:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/33ed9b0f-1167-43a4-850b-b3ea1425d729.jsonl`
- `/ll:refine-issue` - 2026-04-21T08:04:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3f95c32f-351e-411d-8879-140d98abfbcf.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0daebbf5-b603-4a5a-a9ad-268f97be413c.jsonl`
- `/ll:wire-issue` - 2026-04-21T08:01:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d28c60a-3107-44ef-969e-3bf12e3b0b01.jsonl`
- `/ll:refine-issue` - 2026-04-21T07:56:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/93b68d88-8ad1-4514-8c72-354021bd9311.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e25ed049-cee1-4c7f-a922-d725b2ff5c2f.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98f68405-0917-4592-af11-ba9a9de2ae0c.jsonl`

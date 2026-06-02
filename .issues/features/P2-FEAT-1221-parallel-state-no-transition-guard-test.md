---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
id: FEAT-1221
priority: P2
parent_issue: FEAT-1219
discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 80
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1221: Add Parallel State No-Transition Guard Test

## Summary

Add a single test to `test_fsm_validation.py` that verifies `parallel:` states with routing do NOT trigger the no-transition guard in `validation.py`.

## Parent Issue

Decomposed from FEAT-1219: Add Parallel State No-Transition Guard and Fuzz Tests

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `validation.py:271` gains `and not has_parallel`, this test verifies the guard fires correctly (i.e., is skipped) for parallel states.

**Goal**: Add one test class `TestParallelStateValidation` with one method to `test_fsm_validation.py`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_validation.py -x` passes green.

## Proposed Solution

Add `ParallelStateConfig` to the import block at `scripts/tests/test_fsm_validation.py:9` (alongside `FSMLoop, StateConfig`).

Add a new class `TestParallelStateValidation` at EOF (line 267), containing one test method that mirrors `test_fsm_schema.py:1884` (`test_sub_loop_state_no_transition_error`) but substitutes `parallel=ParallelStateConfig(items="...", loop="...")` for `loop="child"`.

```python
class TestParallelStateValidation:
    def test_parallel_state_no_transition_error(self) -> None:
        """A state with parallel: set should not trigger 'no transition' error."""
        fsm = FSMLoop(
            name="test",
            initial="run_parallel",
            states={
                "run_parallel": StateConfig(
                    parallel=ParallelStateConfig(items="items", loop="child"),
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

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_validation.py` — Add `ParallelStateConfig` import; add `TestParallelStateValidation` class at EOF

### Dependent Files
- `scripts/little_loops/fsm/validation.py:271` — Guard must have `and not has_parallel` (FEAT-1074)
- `scripts/little_loops/fsm/schema.py` — Must define `ParallelStateConfig` and add `parallel` field on `StateConfig` (FEAT-1074)

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1884` — `test_sub_loop_state_no_transition_error` — direct template
- `scripts/tests/test_fsm_schema.py:1866` — `test_loop_and_action_mutual_exclusion` — companion idiom using `str(e)` + substring-intersection assertion

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py` — primary target; adding `ParallelStateConfig` to the line 9 import before FEAT-1074 ships causes an `ImportError` at pytest collection time, silently breaking all 12 existing tests — implement only after FEAT-1074 is merged
- `scripts/tests/test_fsm_schema.py:881-907` — contains `test_state_with_no_transition` (positive guard assertion) and `test_on_partial_only_shorthand_is_valid` (negative guard assertion); both must stay green after FEAT-1074's `has_parallel` guard change — run as regression check
- `scripts/tests/test_review_loop.py:127-137` — `test_v9_state_with_no_transition` asserts by `e.path` (not message string); must stay green after FEAT-1074 — run as regression check

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

- `test_fsm_validation.py` is 266 lines; append the new class after the current EOF. Existing classes: `TestExtraRoutesReachability` (line 18), `TestRateLimitFieldValidation` (line 69).
- Current imports at `test_fsm_validation.py:9-10` already bring in `FSMLoop`, `StateConfig`, `ValidationSeverity`, and `validate_fsm`. Only `ParallelStateConfig` needs to be added to the `schema` import on line 9:
  ```python
  from little_loops.fsm.schema import FSMLoop, ParallelStateConfig, StateConfig
  ```
- Current guard at `validation.py:266-278` (FEAT-1074 must insert `has_parallel` and extend the condition):
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
- Pre-conditions (both from FEAT-1074, not yet shipped):
  - `ParallelStateConfig` is not defined in `schema.py`; the word "parallel" does not appear there.
  - `StateConfig` (`schema.py:180`, fields at `schema.py:229-255`) has no `parallel` field.
- Minimum constructor that satisfies the planned `ParallelStateConfig` dataclass (per FEAT-1074): `ParallelStateConfig(items="items", loop="child")` — the two required fields; all other fields have defaults.
- Assertion idiom to mirror (from template): `assert not any("no transition" in m.lower() for m in error_messages)` — case-insensitive, negated substring check after `[str(e) for e in errors]`. Matches the style already established in `test_fsm_schema.py`.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`; `has_parallel` guard in `validation.py`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_validation.py -x` passes green
- New test confirms `parallel:` states with routing skip the no-transition guard
- No regressions in existing validation tests

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 unmerged**: `ParallelStateConfig` does not exist in `schema.py` and the `has_parallel` guard does not exist in `validation.py`. Adding the import before FEAT-1074 ships causes an `ImportError` at pytest collection time, silently breaking all 12 existing tests. Implement FEAT-1221 only after FEAT-1074 is merged.

## Session Log
- `/ll:refine-issue` - 2026-04-21T08:19:15 - `ac81633f-8dd4-4c59-b4e1-39b1c9bb4c42.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `9d5b214e-7d4b-4f96-9dba-46554e3858ed.jsonl`
- `/ll:wire-issue` - 2026-04-21T08:16:53 - `f4e120d3-8b95-4146-b649-3e4aac714e9a.jsonl`
- `/ll:refine-issue` - 2026-04-21T08:11:55 - `efd4be50-b8ce-4404-8ce2-235d9bf2aede.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `98f68405-0917-4592-af11-ba9a9de2ae0c.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `4d71efca-20a3-4b26-b77d-e5c5e5ba00ca.jsonl`

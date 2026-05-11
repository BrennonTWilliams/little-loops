---
id: FEAT-1214
priority: P2

discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 80
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: FEAT-1200
---

# FEAT-1214: Parallel Validation, Fuzz, and Doc Tests

## Summary

Add the no-transition guard test to `test_fsm_validation.py`, extend the `malformed_state_config` fuzz strategy in `test_fsm_schema_fuzz.py` with a `parallel` key, and update `docs/development/TESTING.md` fixture count.

## Parent Issue

Decomposed from FEAT-1200: Parallel State Schema, Validation, and Fuzz Tests

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `validation.py:271` gains `and not has_parallel`, this test verifies the guard fires correctly. The fuzz extension adds parallel-shaped malformed inputs to existing coverage.

**Goal**: Add one test to `test_fsm_validation.py`, one fuzz block to `test_fsm_schema_fuzz.py`, and update the TESTING.md fixture count.

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

### docs/development/TESTING.md — Update fixture count

Update line 115 from `"FSM YAML fixtures (8 files)"` to `"FSM YAML fixtures (10 files)"` (accounts for 9 existing + 1 new `parallel-loop.yaml` from FEAT-1213; verify current count is 9 before editing).

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_validation.py` — Add one `parallel:` no-transition-guard test
- `scripts/tests/test_fsm_schema_fuzz.py` — Add `parallel` to `malformed_state_config` strategy after the route block (ends at line 173), before line 175 `# Add unexpected fields`
- `docs/development/TESTING.md:115` — Update fixture count from 9 to 10

### Dependent Files
- `scripts/little_loops/fsm/validation.py:271` — No-transition guard; gains `and not has_parallel` (FEAT-1074)
- `scripts/tests/fixtures/fsm/parallel-loop.yaml` — Created by FEAT-1213

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1884` — `test_sub_loop_state_no_transition_error` — direct template for the no-transition guard test
- `scripts/tests/test_fsm_schema_fuzz.py:173` — `route` block end (insertion point)

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified 2026-04-21 via codebase analysis:_

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
- Imports at lines 1–11: `FSMLoop, StateConfig` from `schema`; `ValidationSeverity, validate_fsm` from `validation`. Add `ParallelStateConfig` to the schema import.
- Classes: `TestExtraRoutesReachability` (line 18, 3 methods) and `TestRateLimitFieldValidation` (line 69, 9 methods, ends ~line 266).
- Insert the new test either in a new class after line 266, or add to an existing class if thematically appropriate.

**Fuzz strategy context** (`test_fsm_schema_fuzz.py`):
- `malformed_state_config` strategy spans lines 134–186 (the draw function)
- Route block: `if draw(st.booleans()): state["route"] = draw(malformed_route_config())` ends at line 173
- Blank line 174; `# Add unexpected fields` at line 175 — insert the `parallel` block between these
- All six `@pytest.mark.slow` consumer lines (299, 324, 348, 378, 406, 432) verified — no marker changes needed

**Fixture count status**:
- Filesystem currently has **9** YAML fixtures in `scripts/tests/fixtures/fsm/` (not 8)
- `docs/development/TESTING.md:115` currently reads `# FSM YAML fixtures (8 files)` — already stale by one
- After FEAT-1213 adds `parallel-loop.yaml`, count will be **10**; update docs `(8 files)` → `(10 files)` in a single edit

## Dependencies

- **FEAT-1074** must be complete (`validation.py` no-transition guard update; adds `ParallelStateConfig` to `schema.py`)
- **FEAT-1213** must be complete (provides `parallel-loop.yaml` fixture; needed to verify the fixture count update is accurate)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema_fuzz.py -x` passes green
- No-transition guard test confirms `parallel:` states with routing skip the guard
- Fuzz test includes `parallel` key in `malformed_state_config` strategy
- `docs/development/TESTING.md:115` updated to reflect 10 fixture files
- No regressions in existing fuzz or validation tests

## Labels

`fsm`, `parallel`, `tests`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 not complete**: `ParallelStateConfig` does not exist in `schema.py`; `has_parallel` absent from `validation.py:271`. The no-transition guard test imports this class and will fail to import until FEAT-1074 ships.
- **FEAT-1213 artifact missing**: `parallel-loop.yaml` not present on disk despite FEAT-1213 being marked completed. Updating TESTING.md to "10 files" before this fixture lands would introduce an inaccuracy.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Heuristic score 11/11 (Very Large); tests and docs update have different prerequisite issues (FEAT-1074 vs FEAT-1213), making separate tracking appropriate

### Decomposed Into
- FEAT-1219: Add Parallel State No-Transition Guard and Fuzz Tests
- FEAT-1220: Update TESTING.md Fixture Count

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-21T07:54:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e25ed049-cee1-4c7f-a922-d725b2ff5c2f.jsonl`
- `/ll:refine-issue` - 2026-04-21T07:49:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d202033-3783-448c-ae64-14b44a059d6a.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/602b7591-5779-4c5a-855e-643bcb13015e.jsonl`
- `/ll:wire-issue` - 2026-04-21T07:46:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ceed0c55-0d9f-42fd-bcaf-cbed6a6d4aba.jsonl`
- `/ll:refine-issue` - 2026-04-21T07:39:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce17ca14-afc4-4f56-a7e9-cb0ae0a60adb.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc287f64-ac41-4ff3-967d-f2d38642710b.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/380dd82a-3df4-4ad4-a4df-7f6a43e31339.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e25ed049-cee1-4c7f-a922-d725b2ff5c2f.jsonl`

---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
id: FEAT-1222
priority: P2
parent_issue: FEAT-1219
discovered_date: "2026-04-21"
discovered_by: issue-size-review
size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1222: Add Parallel Key to Malformed State Config Fuzz Strategy

## Summary

Insert a `parallel` config draw block into the `malformed_state_config` Hypothesis strategy in `test_fsm_schema_fuzz.py`, extending fuzz coverage to parallel-shaped inputs.

## Parent Issue

Decomposed from FEAT-1219: Add Parallel State No-Transition Guard and Fuzz Tests

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once `fsm-loop-schema.json` defines the `parallel` key, fuzz tests should include malformed `parallel` values to exercise schema rejection paths.

**Goal**: Add one draw block (~12 lines) after the `route` block in `malformed_state_config()`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema_fuzz.py -x` passes green.

## Proposed Solution

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

No `@pytest.mark.slow` changes are needed — this block is inserted into the existing `malformed_state_config()` strategy, consumed by tests already marked `@pytest.mark.slow`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **What the consuming fuzz tests actually exercise**: They call `StateConfig.from_dict()` (`scripts/little_loops/fsm/schema.py:319`) and `FSMLoop.from_dict()` — the Python-layer deserializers — not the JSON Schema validator. Unknown keys are silently ignored by `from_dict`, so the `parallel` block only exercises the rejection path once FEAT-1074 adds a `parallel: ParallelStateConfig | None` field to `StateConfig` and wires `from_dict` to deserialize it. Tolerated exception types per test: `KeyError`, `TypeError`, `ValueError`, `AttributeError`.
- **Consumers of `malformed_state_config()`** (subset of the six `@pytest.mark.slow` markers):
  - `TestStateConfigFuzz.test_from_dict_handles_malformed` — direct use at `test_fsm_schema_fuzz.py:349` (class marked at line 348)
  - `TestFSMLoopFuzz.test_from_dict_handles_malformed` — indirect via `malformed_fsm_loop()` which calls `malformed_state_config()` at `test_fsm_schema_fuzz.py:223` (class marked at line 378)
  - `TestFSMLoopFuzz.test_large_state_dicts` — direct use at `test_fsm_schema_fuzz.py:440` (class marked at line 432)
  - Lines 299, 324, 406 are `@pytest.mark.slow` but consume *other* strategies (`malformed_evaluate_config`, `malformed_route_config`, raw YAML) — not affected by this change.
- **`st.fixed_dictionaries` is novel to this file**: zero other occurrences in `scripts/tests/`. Proposed shape is internally consistent with sibling wrong-type arms (`name` field at lines 138–145, `action` at lines 149–155).
- **Current `stateConfig.properties` in `fsm-loop-schema.json`** (lines 178–313) contains no `parallel` key and closes with `"additionalProperties": false` at line 320 — FEAT-1074 must add `parallel` there before this block produces any "accepted-then-rejected-downstream" coverage.
- **`ParallelStateConfig` does not yet exist**: grep across `scripts/` returns zero hits. The `ParallelConfig` class at `scripts/little_loops/parallel/types.py` is the orchestrator-level config and is unrelated to the FSM state key.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_schema_fuzz.py:135–186` — `malformed_state_config()` strategy; insert `parallel` draw block after line 173 (end of route block), before line 175 (`# Add unexpected fields`)

### Dependent Files (Blocking)
- `scripts/little_loops/fsm/fsm-loop-schema.json:175–320` — `stateConfig` definition; FEAT-1074 must add `parallel` to `properties`
- `scripts/little_loops/fsm/schema.py:229–375` — `StateConfig` dataclass and `from_dict`; FEAT-1074 must add `parallel: ParallelStateConfig | None = None` field and wire `from_dict` to deserialize it

### Consumers (Automatically Exercised)
- `scripts/tests/test_fsm_schema_fuzz.py:348` — `TestStateConfigFuzz.test_from_dict_handles_malformed`
- `scripts/tests/test_fsm_schema_fuzz.py:378` — `TestFSMLoopFuzz.test_from_dict_handles_malformed` (via `malformed_fsm_loop()` at line 223)
- `scripts/tests/test_fsm_schema_fuzz.py:432` — `TestFSMLoopFuzz.test_large_state_dicts`

### Similar Patterns (Templates)
- `scripts/tests/test_fsm_schema_fuzz.py:171–173` — `route` block; direct template for the new `parallel` block (comment + guarded `state[key] = draw(...)`)
- `scripts/tests/test_fsm_schema_fuzz.py:167–169` — `evaluate` block; same guard shape with a sub-strategy
- `scripts/tests/test_fsm_schema_fuzz.py:33–95` — `malformed_evaluate_config()`; shows the established wrong-type-arms convention (`st.sampled_from`, `st.text()`, `st.integers()`, `st.none()`)

### Regression Targets
- `scripts/tests/test_fsm_schema.py` — full schema test suite (`TestSubLoopStateConfig:1817`, `test_sub_loop_state_no_transition_error:1884` patterns to mirror in parallel work)
- `scripts/tests/test_fsm_fragments.py`, `scripts/tests/test_builtin_loops.py` — validate existing loops still pass after FEAT-1074 schema additions land

### Related Issues
- **Sibling** FEAT-1221 — adds parallel no-transition guard test to `test_fsm_validation.py` (decomposed alongside FEAT-1222 from FEAT-1219)
- **Parent** FEAT-1219 — carries the shared rationale and the same proposed block at lines 53–65

## Implementation Steps

1. Verify FEAT-1074 has landed: `grep -n "parallel" scripts/little_loops/fsm/fsm-loop-schema.json` returns a `parallel` key under `stateConfig.properties`, and `scripts/little_loops/fsm/schema.py` defines `ParallelStateConfig` with a `parallel` field on `StateConfig`. If absent, stop — FEAT-1222 cannot be implemented until the dependency lands.
2. Open `scripts/tests/test_fsm_schema_fuzz.py` and navigate to `malformed_state_config()` at line 135. Insert the 12-line `parallel` draw block (from the Proposed Solution) between line 173 and line 175, preserving the existing blank line pattern used between sibling blocks.
3. Run the targeted fuzz suite: `python -m pytest scripts/tests/test_fsm_schema_fuzz.py -x -v`. All six `@pytest.mark.slow` classes should pass; specifically `TestStateConfigFuzz`, `TestFSMLoopFuzz::test_from_dict_handles_malformed`, and `TestFSMLoopFuzz::test_large_state_dicts` will exercise the new block.
4. Run regression checks to ensure no collateral damage: `python -m pytest scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -x`.
5. If any new failure surfaces, inspect whether `StateConfig.from_dict` raises an exception type not in the tolerated set (`KeyError`, `TypeError`, `ValueError`, `AttributeError`) — that indicates FEAT-1074's `from_dict` handling of `parallel` needs hardening rather than a fuzz-block change.

## Dependencies

- **FEAT-1074** must be complete (`parallel` added to `fsm-loop-schema.json`)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema_fuzz.py -x` passes green
- Fuzz strategy includes `parallel` key with malformed value variants
- No regressions in existing fuzz tests

## Labels

`fsm`, `parallel`, `tests`, `fuzz`

## Confidence Check Notes

_Last updated by `/ll:confidence-check` on 2026-04-21 (re-run; scores unchanged)_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 unresolved**: The `parallel` key is absent from `fsm-loop-schema.json` and `ParallelStateConfig` does not yet exist in `schema.py`. Until that dependency lands, the new draw block is inert — `StateConfig.from_dict` silently ignores unknown keys, so no rejection paths are exercised. Implementation Step 1 correctly flags this as a stop condition; hold this issue until FEAT-1074 merges.

## Session Log
- `/ll:refine-issue` - 2026-04-21T08:34:37 - `912edf79-dc25-49f7-aed4-de81c93c3bcd.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `fed5e14f-7ef3-4359-b8ec-b0e9e9d90d64.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `6cd1442f-806d-4a64-b181-233de7991e0b.jsonl`
- `/ll:wire-issue` - 2026-04-21T08:31:15 - `fed5e14f-7ef3-4359-b8ec-b0e9e9d90d64.jsonl`
- `/ll:refine-issue` - 2026-04-21T08:26:36 - `87e85cf1-1284-40fb-b75d-fa0a68277e9d.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `98f68405-0917-4592-af11-ba9a9de2ae0c.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `66880b0b-393c-4d21-819b-64abdc9eb645.jsonl`

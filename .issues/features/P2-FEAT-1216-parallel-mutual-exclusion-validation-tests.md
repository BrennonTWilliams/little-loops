---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
id: FEAT-1216
priority: P2
parent_issue: FEAT-1213
discovered_date: "2026-04-21"
discovered_by: issue-size-review
confidence_score: 86
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
size: Very Large
---

# FEAT-1216: Parallel Mutual Exclusion Validation Tests

## Summary

Add `TestParallelMutualExclusion` class to `test_fsm_schema.py`. Scoped to validation error coverage for invalid `parallel` field combinations.

## Parent Issue

Decomposed from FEAT-1213: Parallel Schema Tests and Fixture

## Use Case

**Who**: Developer completing FEAT-1074 (`ParallelStateConfig` schema and validation)

**Context**: Once FEAT-1074 extends `_validate_state_action` (or adds `_validate_state_parallel`) to emit mutual-exclusion errors for `parallel`, these tests verify all 6 invalid combinations are caught.

**Goal**: Add `TestParallelMutualExclusion` to `test_fsm_schema.py`.

**Outcome**: `python -m pytest scripts/tests/test_fsm_schema.py -x -k "TestParallelMutualExclusion"` passes green.

## Proposed Solution

### test_fsm_schema.py — Add TestParallelMutualExclusion class

Model after `test_loop_and_action_mutual_exclusion:1866`. Place the new class **after `TestSubLoopStateConfig` closes at line 1901** and **before `class TestLoopConfigOverrides:` at line 1904** (i.e., insert at the blank line at 1902–1903).

Cover every invalid combination that FEAT-1074's "Tests (owned by this issue)" section assigns to `TestParallelMutualExclusion`:

**ERROR-level mutual exclusion:**
- `parallel` + `action` → error message contains `"parallel"` and `"action"`
- `parallel` + `loop` (top-level `loop:` on the same state) → error message contains `"parallel.loop"` (the message directs authors to use `parallel.loop` for fan-out; see FEAT-1074 Implementation Notes for exact wording)
- `parallel` + `next` → error message contains `"parallel"` and `"next"`

**ERROR-level range/enum validation:**
- `max_workers: 0` → error contains `"max_workers"` and `">= 1"`
- `timeout_seconds: 0` → error contains `"timeout_seconds"` and `">= 1"`
- `max_items: 0` → error contains `"max_items"` and `">= 1"`
- `max_total_seconds: 0` → error contains `"max_total_seconds"` and `">= 1"`
- `isolation: "invalid"` → error contains `"isolation"` and `"thread"` (or `"worktree"`)
- `fail_mode: "invalid"` → error contains `"fail_mode"` and `"collect"` (or `"fail_fast"`)

**WARN-level cross-field sanity check:**
- `max_workers=4, timeout_seconds=60, max_total_seconds=120` → a WARN-severity `ValidationError` contains `"max_total_seconds"` and `"max_workers"` (cumulative cap dominated by per-worker timeouts — see FEAT-1074 line 103 and validation error message at FEAT-1074 Implementation Notes line 351–352). Filter by `severity == ValidationSeverity.WARNING` to distinguish from ERRORs.

**Nested parallel (forbidden):**
- A `parallel:` state whose `parallel.loop` names a loop that itself contains a `parallel:` state → error message contains `"nested parallel"` or `"nested"`. This validation runs across all loaded loops; construct a two-loop FSM fixture (outer loop + inner loop that both have `parallel:` states) to exercise it. See FEAT-1074 line 105 for the exact error wording.

Error-message assertion pattern (follow exactly):

```python
errors = validate_fsm(fsm)
error_messages = [str(e) for e in errors]
assert any("parallel" in m and "action" in m for m in error_messages)
```

For the `parallel.loop` case, assert on the sub-field name (not just `"loop"`) to confirm the error message correctly points authors to the `parallel.loop` location:

```python
assert any("parallel.loop" in m for m in error_messages)
```

For the WARN case, filter by severity:

```python
warnings = [e for e in validate_fsm(fsm) if e.severity == ValidationSeverity.WARNING]
assert any("max_total_seconds" in str(w) and "max_workers" in str(w) for w in warnings)
```

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_schema.py` — Add `TestParallelMutualExclusion` at line 1902–1903 (after `TestSubLoopStateConfig` closes at :1901, before `class TestLoopConfigOverrides:` at :1904)

### Dependent Files
- `scripts/little_loops/fsm/validation.py` — `_validate_state_action` is a free function at line 195 (verified 2026-04-21). FEAT-1074 extends it (or adds `_validate_state_parallel`) to emit errors for `parallel` mutual-exclusion, range, and enum cases. The existing `loop`/`action` check at `:217–225` establishes the error shape: `ValidationError(message=..., path=f"states.{state_name}")`.
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` dataclass and `StateConfig.parallel: ParallelStateConfig | None = None` field (FEAT-1074). Nine fields: `items`, `loop`, `max_workers` (default 4), `isolation` (default `"thread"`), `fail_mode` (default `"collect"`), `context_passthrough` (default `False`), `timeout_seconds` (default `None`), `max_items` (default `1000`), `max_total_seconds` (default `None`).

### Similar Patterns
- `scripts/tests/test_fsm_schema.py:1866` — `test_loop_and_action_mutual_exclusion` — mutual exclusion template (confirms `errors = validate_fsm(fsm)` + `any("x" in m and "y" in m for m in [str(e) for e in errors])` pattern)
- `scripts/tests/test_fsm_schema.py:780` — `TestFSMValidation` — error-list assertions (15 methods use `any(substring in e.message for e in errors)` or `len(filtered) == 0` — no total-count assertions, so adding new rules is safe)
- `scripts/tests/test_fsm_schema.py:1817` — `TestSubLoopStateConfig` — parent class pattern for state-type-specific validation tests

### Imports Required
```python
from little_loops.fsm.schema import FSMLoop, StateConfig, ParallelStateConfig
from little_loops.fsm.validation import validate_fsm, ValidationSeverity
```
`ParallelStateConfig` is added by FEAT-1074 — import it from `schema.py`, not from `fsm/__init__.py` (precedent: `LoopConfigOverrides` is not re-exported through `__init__.py`; see FEAT-1074 line 170).

### Validation Entry Points
- `validate_fsm(fsm: FSMLoop) -> list[ValidationError]` at `validation.py:372` — returns errors without raising; use for all mutual exclusion + value-invalid cases
- `ValidationError.severity` field is `ValidationSeverity.ERROR` by default; WARN cases (cross-field sanity) must be filtered explicitly via `e.severity == ValidationSeverity.WARNING`

### Regression Surfaces
- `scripts/tests/test_fsm_schema.py:780` (`TestFSMValidation`) — confirmed: no `len(errors) == N` count assertions — adding new parallel rules is safe (see FEAT-1074 line 285)
- `scripts/tests/test_fsm_fragments.py` + `scripts/tests/test_builtin_loops.py` — call `validate_fsm` across all 33+ built-in loops; none of them use `parallel:`, so new parallel-specific rules cannot emit false positives against them
- `scripts/tests/test_fsm_validation.py` — **alternative home**: dedicated validation test file (FEAT-1074 line 191 and line 380 note). New class can live here instead of `test_fsm_schema.py`; keep in `test_fsm_schema.py` per this issue's title to stay consistent with `TestParallelStateConfig` in FEAT-1215 (completed) which lands in the same file.
- `scripts/tests/test_fsm_schema_fuzz.py` — exercises `StateConfig.from_dict()` with random inputs; after FEAT-1074 adds `ParallelStateConfig`, the fuzz strategy may encounter `parallel` fields — monitor for false positives on new mutual-exclusion rules. [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_ll_loop_commands.py` — 8 inline `load_and_validate` calls exercising the CLI `validate` subcommand end-to-end; new parallel-specific rules must not fire on real loop files (none use `parallel:`) [Wiring pass added by `/ll:wire-issue`]

### Additional Patterns

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py::TestRateLimitFieldValidation` — closest existing analog for range/enum validation cases (`max_workers: 0`, `timeout_seconds: 0`, etc.); see `test_max_less_than_one_fails` for assertion style: `assert any("field_name" in e.message and ">= 1" in e.message for e in errors)`. Note: that file uses `.message` attribute directly; the mutual-exclusion template at `:1866` uses `str(e)` — pick one consistently within `TestParallelMutualExclusion`.

### Wiring Constraints

_Wiring pass added by `/ll:wire-issue`:_

**Critical constraint — nested parallel test**: `validate_fsm()` at `validation.py:372` currently accepts a single `FSMLoop`. The nested-parallel case (outer + inner loop both with `parallel:` states) requires cross-loop validation that does not yet exist. FEAT-1074 must expose a multi-loop validation mechanism (e.g., a `loops` dict parameter or a `validate_fsm_set()` function) before this test can be written. The test implementation must match whatever interface FEAT-1074 chooses — do not assume `validate_fsm` will accept a second argument.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` schema, validation extended for parallel mutual exclusion)
- **FEAT-1215** is independent — can be implemented in either order

## Acceptance Criteria

- `python -m pytest scripts/tests/test_fsm_schema.py -x -k "TestParallelMutualExclusion"` passes green
- Mutual exclusion (ERROR): `parallel`+`action`, `parallel`+`loop` (assert on `"parallel.loop"` substring), `parallel`+`next`
- Range validation (ERROR): `max_workers: 0`, `timeout_seconds: 0`, `max_items: 0`, `max_total_seconds: 0`
- Enum validation (ERROR): `isolation: "invalid"`, `fail_mode: "invalid"`
- Cross-field sanity (WARN): `max_workers=4, timeout_seconds=60, max_total_seconds=120` emits a WARN-severity `ValidationError` — filter via `severity == ValidationSeverity.WARNING`
- Nested parallel (ERROR): a `parallel:` state whose `parallel.loop` names a loop containing another `parallel:` state emits an error with `"nested"` in the message
- Existing `TestFSMValidation` error-list assertions stay green (confirmed no total-count assertions — adding new rules is safe)
- `scripts/tests/test_fsm_fragments.py` and `scripts/tests/test_builtin_loops.py` stay green (no built-in loop uses `parallel:`, so new parallel-specific rules cannot emit false positives)

## Codebase Research Findings

_Added by `/ll:refine-issue` (auto, 2026-04-21) — based on codebase and cross-issue analysis:_

**Verified line references** (all current as of 2026-04-21):
- `_validate_state_action` — `scripts/little_loops/fsm/validation.py:195` ✓
- `validate_fsm` — `scripts/little_loops/fsm/validation.py:372` ✓
- `test_loop_and_action_mutual_exclusion` — `scripts/tests/test_fsm_schema.py:1866` ✓ (inside `TestSubLoopStateConfig` at :1817, which ends at :1901)
- `TestFSMValidation` — `scripts/tests/test_fsm_schema.py:780` ✓
- Insertion point for `TestParallelMutualExclusion`: between `TestSubLoopStateConfig` end (:1901) and `TestLoopConfigOverrides` start (:1904)

**Scope correction — case count is 10, not 6**: The Summary and original Proposed Solution list 6 invalid combinations, but FEAT-1074's "Tests (owned by this issue)" section (line 250) assigns 10+ cases to `TestParallelMutualExclusion`: parallel+action, parallel+loop, parallel+next, `max_workers: 0`, `max_items: 0`, `max_total_seconds: 0`, `timeout_seconds: 0`, `isolation: "invalid"`, `fail_mode: "invalid"`, plus the cumulative-cap WARN. Nested-parallel is defined in FEAT-1074 line 105 as a cross-loop check and belongs in this class for authoring-error coverage. Updated Proposed Solution and Acceptance Criteria reflect the full set.

**Exact error message substrings** (from FEAT-1074 Implementation Notes, `validation.py` emits):
- `parallel`+`action`: `"'parallel' and 'action' are mutually exclusive — a parallel state cannot also have an action"` → assert `"parallel"` AND `"action"`
- `parallel`+`loop`: `"'parallel' and 'loop' are mutually exclusive at the state level — use 'parallel.loop' to name the sub-loop to fan out; do not set a top-level 'loop:' field on the same state"` → assert `"parallel.loop"` (not just `"loop"`)
- `parallel`+`next`: `"'parallel' and 'next' are mutually exclusive — parallel state transitions are managed by the parallel runner"` → assert `"parallel"` AND `"next"`
- `max_workers: 0`: `f"'max_workers' must be >= 1, got {value}"`
- `timeout_seconds: 0`: `f"'timeout_seconds' must be >= 1 when set, got {value}"`
- `max_items: 0`: `f"'max_items' must be >= 1, got {value}"`
- `max_total_seconds: 0`: `f"'max_total_seconds' must be >= 1 when set, got {value}"`
- Invalid `isolation`: `f"'isolation' must be one of {{'worktree', 'thread'}}, got {repr(value)}"`
- Invalid `fail_mode`: `f"'fail_mode' must be one of {{'collect', 'fail_fast'}}, got {repr(value)}"`
- Cumulative-cap WARN: `f"'max_total_seconds' ({X}s) is <= max_workers * timeout_seconds ({W} * {T}s); cumulative cap may be unreachable"`
- Nested parallel: `"parallel.loop '<name>' contains a nested parallel state at <state>; nested parallel states are not supported. Decompose into separate top-level parallel states or flatten the sub-loop."` (FEAT-1074 line 105)

**Error path format**: `path = f"states.{state_name}"` (from `validation.py:217–225`) — use this to filter by state if a test builds multi-state FSMs.

**`ValidationSeverity` location**: imported from `little_loops.fsm.validation` (same module as `validate_fsm` and `ValidationError`). All WARN-level assertions must filter explicitly; `validate_fsm` returns both ERROR and WARN entries mixed in one list.

**Sibling scope boundary**:
- FEAT-1215 (completed) owns `TestParallelStateConfig` (round-trip, defaults, fixture loading) — do NOT duplicate round-trip assertions here.
- FEAT-1214 (parallel-validation-fuzz-and-doc-tests) owns the hypothesis fuzz strategy for `parallel` — do NOT add fuzz cases here.
- This issue owns only authoring-error coverage via `validate_fsm`.

## Labels

`fsm`, `parallel`, `tests`, `validation`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-21 (score improved 76→86 after refine/wire passes)_

**Readiness Score**: 86/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1074 is the blocking dependency and remains open.** `ParallelStateConfig` does not yet exist in `scripts/little_loops/fsm/schema.py`, and `_validate_state_parallel` (or the extended `_validate_state_action`) has not been written. The test class can be fully authored now, but will fail on import (`ImportError: cannot import name 'ParallelStateConfig'`) until FEAT-1074 ships. The acceptance criteria requires green tests, so FEAT-1216 cannot be marked complete independently.
- **Nested-parallel test case (1/11) has a deferred API dependency.** `validate_fsm()` currently accepts a single `FSMLoop`; the nested-parallel test requires a cross-loop validation interface that FEAT-1074 must define first. Stub or skip this case until FEAT-1074's API is settled.

## Session Log
- `/ll:refine-issue` - 2026-04-21T07:32:47 - `6feb5576-8fea-4e0c-8c0c-321bf450c70a.jsonl`
- `/ll:wire-issue` - 2026-04-21T00:00:00 - `5e1c12cf-d8f2-462d-9a3e-06276aa95e4c.jsonl`
- `/ll:refine-issue` - 2026-04-21T07:23:55 - `5e1c12cf-d8f2-462d-9a3e-06276aa95e4c.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `7b6f3646-002b-4241-b60d-d6d09e155cee.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `5e1c12cf-d8f2-462d-9a3e-06276aa95e4c.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `433437e6-196c-4090-b28d-f3683677a675.jsonl`

---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 100
outcome_confidence: 86
---

# FEAT-1074: Parallel State Schema and Validation

## Summary

Add `ParallelStateConfig` dataclass to `schema.py`, extend `StateConfig` with a `parallel:` field, update `fsm-loop-schema.json`, and add mutual exclusion validation rules to `validation.py`.

## Current Behavior

No `ParallelStateConfig` dataclass exists in `schema.py`. States with a `parallel:` key will trigger "unknown key" validation warnings. There are no mutual exclusion checks to prevent conflicting configurations (e.g., a state with both `parallel:` and `action:`).

## Expected Behavior

- `ParallelStateConfig` dataclass exists in `schema.py` with 6 fields and correct round-trip serialization (`to_dict` / `from_dict`)
- `StateConfig.parallel` deserializes correctly — `None` when absent, `ParallelStateConfig` when present
- `"parallel"` is in `KNOWN_TOP_LEVEL_KEYS` — no unknown-key warnings on loops using `parallel:` states
- Mutual exclusion rules in `validation.py` reject `parallel:` + `action:`, `parallel:` + `loop:`, `parallel:` + `next:` with clear error messages
- `fsm-loop-schema.json` enforces field types and constraints for IDE/lint validation

## Motivation

This feature would:
- Provide the data model and validation backbone required by FEAT-1072 (parallel FSM state type) — downstream modules (FEAT-1075 parallel runner, FEAT-1076 executor dispatch) depend on `ParallelStateConfig` existing in `schema.py`
- Ensure schema correctness at parse time: mutual exclusion rules catch malformed loop configs (e.g., `parallel:` + `action:`) with clear errors before execution
- Maintain backward compatibility: adding `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` ensures existing loops continue to pass validation without spurious unknown-key warnings

## Use Case

**Who**: FSM loop author writing a loop YAML that fans out sub-loop execution across dynamic items

**Context**: Authoring a `parallel:` state in a loop YAML (e.g., `items: "{{ issue_list }}"`, `loop: "manage-issue"`)

**Goal**: Define a `parallel:` state with all supported fields (`items`, `loop`, `max_workers`, `isolation`, `fail_mode`) without triggering unknown-key validation warnings

**Outcome**: The FSM parser accepts the `parallel:` state, serializes/deserializes round-trip correctly, and rejects malformed configs (bad enum values, conflicting fields) with actionable error messages

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### schema.py

Add `ParallelStateConfig` dataclass following the `LoopConfigOverrides` pattern at `schema.py:419`:

```python
@dataclass
class ParallelStateConfig:
    items: str                    # interpolated expression resolving to newline-delimited list
    loop: str                     # sub-loop name to run per item
    max_workers: int = 4
    isolation: str = "worktree"   # "worktree" | "thread"
    fail_mode: str = "collect"    # "collect" | "fail_fast"
    context_passthrough: bool = False

    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, data: dict) -> "ParallelStateConfig":
        ...
```

Add `parallel: ParallelStateConfig | None = None` to `StateConfig`. Follow the `loop` field pattern in `to_dict()` (skip if None, lines ~316) and `from_dict()` (use `data.get("parallel")`, lines ~288–338).

### validation.py

- Add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` frozenset at `validation.py:77–99`
- Add mutual exclusion checks: `parallel` + `action`, `parallel` + `loop`, `parallel` + `next`
- Add range validation: `max_workers >= 1`
- Add enum checks: `isolation` in `{"worktree", "thread"}`, `fail_mode` in `{"collect", "fail_fast"}`

### fsm-loop-schema.json

Add `parallel:` as a valid state-level key with sub-fields matching `ParallelStateConfig` fields and their types/constraints.

## API/Interface

```python
@dataclass
class ParallelStateConfig:
    items: str                    # interpolated expression resolving to newline-delimited list
    loop: str                     # sub-loop name to run per item
    max_workers: int = 4
    isolation: str = "worktree"   # "worktree" | "thread"
    fail_mode: str = "collect"    # "collect" | "fail_fast"
    context_passthrough: bool = False

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "ParallelStateConfig": ...

# StateConfig extension (new field)
parallel: ParallelStateConfig | None = None
```

## Implementation Steps

1. Add `ParallelStateConfig` dataclass to `schema.py` following the `LoopConfigOverrides` pattern at `schema.py:419` — implement `to_dict()` and `from_dict()` using the same guard/cast idioms
2. Extend `StateConfig` with `parallel: ParallelStateConfig | None = None`; update `to_dict()` to skip if None (follow `loop` field pattern at ~line 316) and `from_dict()` to hydrate via `ParallelStateConfig.from_dict()` when key present
3. Update `validation.py`: add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` (lines 77–99); add mutual exclusion checks (`parallel` + `action`, `parallel` + `loop`, `parallel` + `next`); add `max_workers >= 1`, enum checks for `isolation` and `fail_mode`
4. Update `fsm-loop-schema.json`: add `parallel:` as a valid state-level key with sub-field types and constraints matching `ParallelStateConfig`
5. Fix `_validate_state_routing` no-transition guard in `validation.py:271` — add `has_parallel = state.parallel is not None` to the guard condition so valid `parallel:` states are not falsely flagged as having "no transition defined" (model after the existing `has_loop` exemption at the same line; test with `test_parallel_state_no_transition_not_flagged`)
6. Run `test_fsm_schema.py`, `test_fsm_schema_fuzz.py`, `test_fsm_validation.py`, `test_fsm_fragments.py`, and `test_builtin_loops.py` to verify no regressions from the new mutual-exclusion rules

## Files to Modify

- `scripts/little_loops/fsm/schema.py` — Add `ParallelStateConfig`, extend `StateConfig` (follow `to_dict`/`from_dict` pattern at lines ~288–338)
- `scripts/little_loops/fsm/validation.py` — Add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` (lines 77–99); add mutual exclusion and value-range checks
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `parallel:` object schema

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — Add `ParallelStateConfig` dataclass (flat structure — simpler than `LoopConfigOverrides`); extend `StateConfig` with `parallel: ParallelStateConfig | None = None` field placed after the `loop` field (~line 233); update `to_dict()` (~line 275) and `from_dict()` (~line 315)
- `scripts/little_loops/fsm/validation.py` — Add mutual exclusion + range/enum checks in `_validate_state_action()` (~line 225 area); see correction note in Implementation Notes about `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `parallel` to `stateConfig.properties` (currently `additionalProperties: false` at line 292 will reject any loop file using `parallel:` states without this addition)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — imports `StateConfig` and `LoopConfigOverrides`; dispatcher for FEAT-1076 will add `parallel` handling here
- `scripts/little_loops/fsm/runners.py` — FSM runner that invokes executor; no changes needed for this issue
- `scripts/little_loops/fsm/fragments.py` — shared fragment library using `from_dict`/`to_dict`; no changes needed
- `scripts/little_loops/fsm/persistence.py` — state persistence using `from_dict`/`to_dict`; `parallel` field will round-trip transparently once added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:113-184` — re-exports `StateConfig` via `__all__`; `LoopConfigOverrides` precedent = **do not export** `ParallelStateConfig` through `__init__.py` (import it directly from `schema.py` like `LoopConfigOverrides`); no change needed but decision must be deliberate
- `scripts/little_loops/cli/loop/layout.py:118-133` — `_get_state_badge()` switches on `state.loop`, `state.action`, `state.route`; no `parallel` branch — parallel states render with no badge (out of scope; address in FEAT-1078)
- `scripts/little_loops/cli/loop/info.py:556-563` — `_print_state_overview_table` Type column has no `parallel` branch (FEAT-1078 scope)
- `scripts/little_loops/cli/loop/run.py:107-115` — context variable pre-scan checks `state.action` but not `state.parallel.items`; `{{ issue_list }}`-style expressions in `items` won't be caught (FEAT-1078 scope)

### Similar Patterns (Exact Code References)
- `schema.py:438-481` — `LoopConfigOverrides.to_dict/from_dict`: shows skip-if-None pattern, but uses nested dict remapping; **`ParallelStateConfig` is flat so skip the nesting complexity**
- `schema.py:246-248` — `StateConfig.to_dict()` for `evaluate`/`route` nested dataclass fields: `if self.evaluate is not None: result["evaluate"] = self.evaluate.to_dict()` — use this exact pattern for `parallel`
- `schema.py:290-296` — `StateConfig.from_dict()` for nested dataclass hydration: `parallel = None; if "parallel" in data: parallel = ParallelStateConfig.from_dict(data["parallel"])` — use this exact pattern
- `schema.py:555-558` — `FSMLoop.to_dict()` double-guard pattern (check non-None AND non-empty dict before writing); not needed for `ParallelStateConfig` since it always has required fields
- `validation.py:217-225` — existing `loop`/`action` mutual exclusion: `if state.loop is not None and state.action is not None: errors.append(ValidationError(message="'loop' and 'action' are mutually exclusive — ...", path=f"{path}"))`
- `validation.py:281-301` — range validation pattern: `f"'max_retries' must be >= 1, got {state.max_retries}"` — follow for `max_workers` check
- `test_fsm_schema.py:1722-1757` — `test_loop_and_action_mutual_exclusion`: shows ERROR-level mutual exclusion test pattern using `str(e)` and `any()`
- `test_fsm_schema.py:1693-1720` — loop field triplet: `test_to_dict_includes_loop_when_set`, `test_to_dict_excludes_loop_when_none`, `test_from_dict_with_loop`, `test_from_dict_without_loop` — model parallel field tests after these

### Tests
- `scripts/tests/test_fsm_schema.py` — primary test file; `TestFSMValidation` at line 636 (15 methods, none assert total error counts — safe to add new validation rules)
- `scripts/tests/test_fsm_validation.py` — **separate validation-specific test file** not mentioned in the issue; new parallel mutual exclusion tests may fit here instead of `test_fsm_schema.py`
- `scripts/tests/test_fsm_fragments.py` — calls `validate_fsm` across built-in loops; new rules must not reject existing loops
- `scripts/tests/test_builtin_loops.py` — same concern; all 33+ built-in loops must continue to pass

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema_fuzz.py` — `TestStateConfigFuzz` exercises `StateConfig.from_dict()` with random inputs; include in regression run alongside `test_fsm_schema.py` to catch unexpected `parallel` field interactions
- New tests to write (add `TestParallelStateConfig` class to `test_fsm_schema.py` following `TestLoopConfigOverrides` at line 1760):
  - `test_parallel_state_no_transition_not_flagged` — **critical**: verifies a valid `parallel:` state does NOT trigger the "no transition defined" error after the `_validate_state_routing` fix (model after `test_sub_loop_state_no_transition_error` at `test_fsm_schema.py:1740`)
  - `test_parallel_and_action_mutual_exclusion` — parallel + action → ERROR with both words in message (model after `test_loop_and_action_mutual_exclusion` at `test_fsm_schema.py:1722`)
  - `test_parallel_and_loop_mutual_exclusion` — parallel + loop → ERROR
  - `test_parallel_and_next_mutual_exclusion` — parallel + next → ERROR
  - `test_to_dict_includes_parallel_when_set` / `test_to_dict_excludes_parallel_when_none` — assert `"parallel" not in d` when `parallel=None` (model after `test_to_dict_excludes_loop_when_none` at line 1700)
  - `test_from_dict_with_parallel` / `test_from_dict_without_parallel`
  - `test_parallel_state_config_roundtrip` — `ParallelStateConfig.from_dict(original.to_dict())` lossless for all 6 fields
  - Enum/range validation: `max_workers=0` → ERROR; `isolation="invalid"` → ERROR; `fail_mode="invalid"` → ERROR

### Documentation

_Wiring pass added by `/ll:wire-issue`:_ (out of scope for FEAT-1074 — address in FEAT-1078)
- `docs/reference/API.md:3779-3795` — `StateConfig` dataclass block lists all fields; new `parallel: ParallelStateConfig | None = None` field is absent
- `docs/generalized-fsm-loop.md:241-273` — state-level YAML key listing does not include `parallel:` key
- `skills/create-loop/loop-types.md:978-1014` — documents `loop:` state type; no `parallel:` state type entry
- `skills/create-loop/reference.md:684-730` — `loop` field reference lists its mutual exclusions; no `parallel` field entry
- `skills/review-loop/reference.md:21-38` — V-series check table; new parallel mutual-exclusion checks (V-series IDs) not yet listed

### Configuration / Schema
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `stateConfig` definition at line 175; `additionalProperties: false` at line 292; `patternProperties` for `^on_` at lines 286-291

## Acceptance Criteria

- `ParallelStateConfig` dataclass exists with all 6 fields and `to_dict`/`from_dict`
- `StateConfig.parallel` field serializes/deserializes round-trip correctly (None when absent)
- `"parallel"` present in `KNOWN_TOP_LEVEL_KEYS` — no unknown-key warnings on loops using `parallel:`
- Mutual exclusion: state with `parallel:` + `action:` fails validation with a clear error
- Mutual exclusion: state with `parallel:` + `loop:` fails validation
- Mutual exclusion: state with `parallel:` + `next:` fails validation
- `max_workers: 0` fails validation
- `isolation: "invalid"` fails validation
- `fail_mode: "invalid"` fails validation
- `fsm-loop-schema.json` reflects all constraints

## Implementation Notes

- Follow `LoopConfigOverrides.to_dict()` / `from_dict()` at `schema.py:419` as the serialization template
- `test_fsm_schema.py:636` `TestFSMValidation` may assert specific error counts — review for regressions after adding new mutual-exclusion rules
- `test_fsm_fragments.py` + `test_builtin_loops.py` call `validate_fsm` across all 33 built-in loops — new rules must not reject existing loops

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CORRECTION — `KNOWN_TOP_LEVEL_KEYS` is wrong target**: `KNOWN_TOP_LEVEL_KEYS` at `validation.py:77` holds top-level YAML keys (`name`, `states`, `context`, etc.). The `parallel:` key lives inside a state config (`states.my_state.parallel`), NOT at the top level. Adding `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` has no effect on state-level validation. The actual fix for IDE unknown-key warnings is adding `parallel` to `stateConfig.properties` in `fsm-loop-schema.json` (where `additionalProperties: false` at line 292 enforces the constraint). Drop the `KNOWN_TOP_LEVEL_KEYS` step from Implementation Steps 3.

**`TestFSMValidation` does NOT assert total error counts**: Research confirmed all 15 test methods use `any("substring" in e.message for e in errors)` or `len(filtered_list) == 0` patterns — adding new parallel mutual-exclusion rules will not break any existing error count assertions.

**Exact `to_dict`/`from_dict` patterns for `ParallelStateConfig`** (flat dataclass — simpler than `LoopConfigOverrides`):
```python
# to_dict: skip-if-default for booleans; always include required fields
def to_dict(self) -> dict[str, Any]:
    result: dict[str, Any] = {"items": self.items, "loop": self.loop}
    if self.max_workers != 4:
        result["max_workers"] = self.max_workers
    if self.isolation != "worktree":
        result["isolation"] = self.isolation
    if self.fail_mode != "collect":
        result["fail_mode"] = self.fail_mode
    if self.context_passthrough:
        result["context_passthrough"] = self.context_passthrough
    return result

# from_dict: data.get with defaults for optional fields
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "ParallelStateConfig":
    return cls(
        items=data["items"],
        loop=data["loop"],
        max_workers=data.get("max_workers", 4),
        isolation=data.get("isolation", "worktree"),
        fail_mode=data.get("fail_mode", "collect"),
        context_passthrough=data.get("context_passthrough", False),
    )
```

**Exact StateConfig extension pattern** (follow `evaluate`/`route` at `schema.py:246-248`, `290-296`):
```python
# In StateConfig.to_dict() (~line 275, after loop field):
if self.parallel is not None:
    result["parallel"] = self.parallel.to_dict()

# In StateConfig.from_dict() (~line 290, before the cls(...) call):
parallel = None
if "parallel" in data:
    parallel = ParallelStateConfig.from_dict(data["parallel"])
# Then pass parallel=parallel to cls(...)
```

**Exact validation error message formats** (follow established patterns in `validation.py:217-225`, `281-301`):
```python
# Mutual exclusion errors (ERROR severity, path = f"states.{state_name}")
"'parallel' and 'action' are mutually exclusive — a parallel state cannot also have an action"
"'parallel' and 'loop' are mutually exclusive — a parallel state cannot also be a sub-loop state"
"'parallel' and 'next' are mutually exclusive — parallel state transitions are managed by the parallel runner"

# Range validation
f"'max_workers' must be >= 1, got {state.parallel.max_workers}"

# Enum validation  
f"'isolation' must be one of {{'worktree', 'thread'}}, got {repr(state.parallel.isolation)}"
f"'fail_mode' must be one of {{'collect', 'fail_fast'}}, got {repr(state.parallel.fail_mode)}"
```

**`fsm-loop-schema.json` parallel property structure** (add to `stateConfig.properties` before `additionalProperties: false` at line 292):
```json
"parallel": {
  "type": "object",
  "description": "Configuration for parallel sub-loop fan-out",
  "required": ["items", "loop"],
  "additionalProperties": false,
  "properties": {
    "items": {"type": "string"},
    "loop": {"type": "string"},
    "max_workers": {"type": "integer", "minimum": 1, "default": 4},
    "isolation": {"type": "string", "enum": ["worktree", "thread"], "default": "worktree"},
    "fail_mode": {"type": "string", "enum": ["collect", "fail_fast"], "default": "collect"},
    "context_passthrough": {"type": "boolean", "default": false}
  }
}
```

**Test file for mutual exclusion tests**: `test_fsm_validation.py` is a dedicated validation test file (not listed in the issue). New parallel mutual exclusion tests belong there (or in `TestFSMValidation` at `test_fsm_schema.py:636`). Follow the `test_loop_and_action_mutual_exclusion` pattern at `test_fsm_schema.py:1722`: build an `FSMLoop` with conflicting fields, call `validate_fsm(fsm)`, assert `any("parallel" in m and "action" in m for m in [str(e) for e in errors])`.

## Impact

- **Priority**: P2 — Blocks FEAT-1075 (parallel runner) and FEAT-1076 (executor dispatch); no workaround without this schema foundation
- **Effort**: Small — Pure additive schema/validation code; clear patterns to follow (`LoopConfigOverrides` in `schema.py:419`); no new algorithms
- **Risk**: Low — Additive changes only; existing loops unaffected; new validation rules apply exclusively to states using `parallel:` key
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `schema`, `validation`

---

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dde26ebe-176b-4ecd-907d-cdda6cf9667d.jsonl`
- `/ll:wire-issue` - 2026-04-12T21:23:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ac6a699-fe93-4fc5-bb86-1ef76e8c42f2.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:16:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/deffc1f6-3d06-45f7-8667-df4243e14b0f.jsonl`
- `/ll:format-issue` - 2026-04-12T21:08:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/751c4dab-a709-4fca-88d5-86efedd1b15c.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2

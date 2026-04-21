---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 90
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
---

# FEAT-1074: Parallel State Schema and Validation

## Blockers & Folded Criteria

**MUST land in this PR, not as follow-ups:**

- **ENH-1166 — review-loop V-series check rows** (folded 2026-04-20). Three new V-series rows for `parallel`+`action`, `parallel`+`loop`, `parallel`+`next` mutual exclusions must appear in `skills/review-loop/reference.md`; add `parallel:` to the State Type quick-reference table if present. See Acceptance Criteria "V-series check table updated (folded from ENH-1166)". Do NOT defer to a later issue — `/ll:review-loop` diverges from runtime validation otherwise.
- **`_validate_state_routing` no-transition guard fix** is a hard prerequisite for FEAT-1076. A valid `parallel:` state currently triggers the "no transition defined" error because the guard at `validation.py:271` has no `has_parallel` exemption (current condition: `if not has_shorthand and not has_route and not has_next and not has_terminal and not has_loop`). Ship the `has_parallel = state.parallel is not None` guard addition in this PR alongside the dataclass — FEAT-1076 cannot merge without it.

**Cross-reference**: v1 scope and explicit post-v1 "won't do" list lives in **P3-ENH-1186** (parallel-state v1 scope & limitations).

## Summary

Add `ParallelStateConfig` dataclass to `schema.py`, extend `StateConfig` with a `parallel:` field, update `fsm-loop-schema.json`, and add mutual exclusion validation rules to `validation.py`.

The dataclass has **9 fields** (`items`, `loop`, `max_workers`, `isolation`, `fail_mode`, `context_passthrough`, `timeout_seconds`, `max_items`, `max_total_seconds`) with `isolation` defaulting to `"thread"`, `timeout_seconds` defaulting to `None` (no per-worker timeout), `max_items` defaulting to `1000`, and `max_total_seconds` defaulting to `None` (no cumulative timeout).

> **Note on `max_items` / `max_total_seconds`** (added 2026-04-20): these two fields were originally proposed in **ENH-1176** (parallel-state resource limits). They are pulled forward into this issue so the schema is internally consistent from v1 day one — downstream issues (FEAT-1075 runner, FEAT-1076 dispatch) can read the fields off `ParallelStateConfig` without a schema churn. ENH-1176 retains ownership of runtime *enforcement* (rejecting oversized fan-outs before spawning workers, wall-clock timer, worktree-count warnings, `try/finally` audit). This issue owns only the fields and basic range validation.

## Current Behavior

No `ParallelStateConfig` dataclass exists in `schema.py`. States with a `parallel:` key will trigger "unknown key" validation warnings. There are no mutual exclusion checks to prevent conflicting configurations (e.g., a state with both `parallel:` and `action:`).

## Expected Behavior

- `ParallelStateConfig` dataclass exists in `schema.py` with 9 fields and correct round-trip serialization (`to_dict` / `from_dict`)
- `StateConfig.parallel` deserializes correctly — `None` when absent, `ParallelStateConfig` when present
- `parallel` is present in `stateConfig.properties` in `fsm-loop-schema.json` — no IDE/lint "additional property" errors on loops using `parallel:` states (NOTE: `KNOWN_TOP_LEVEL_KEYS` is not involved; see Implementation Notes CORRECTION)
- Mutual exclusion rules in `validation.py` reject `parallel:` + `action:`, `parallel:` + `loop:`, `parallel:` + `next:` with clear error messages
- `isolation` defaults to `"thread"` (fast, read-safe); `"worktree"` is opt-in for sub-loops that write files concurrently
- `timeout_seconds` provides an optional per-worker timeout; `None` means no timeout
- `fsm-loop-schema.json` enforces field types and constraints for IDE/lint validation

## Motivation

This feature would:
- Provide the data model and validation backbone required by FEAT-1072 (parallel FSM state type) — downstream modules (FEAT-1075 parallel runner, FEAT-1076 executor dispatch) depend on `ParallelStateConfig` existing in `schema.py`
- Ensure schema correctness at parse time: mutual exclusion rules catch malformed loop configs (e.g., `parallel:` + `action:`) with clear errors before execution
- Maintain backward compatibility: additive-only changes to `fsm-loop-schema.json` (new `parallel` object under `stateConfig.properties`) ensure existing loops continue to pass validation without spurious "additional property" errors

## Use Case

**Who**: FSM loop author writing a loop YAML that fans out sub-loop execution across dynamic items

**Context**: Authoring a `parallel:` state in a loop YAML (e.g., `items: "{{ issue_list }}"`, `loop: "manage-issue"`)

**Goal**: Define a `parallel:` state with all supported fields (`items`, `loop`, `max_workers`, `isolation`, `fail_mode`, `context_passthrough`, `timeout_seconds`, `max_items`, `max_total_seconds`) without triggering unknown-key validation warnings

**Outcome**: The FSM parser accepts the `parallel:` state, serializes/deserializes round-trip correctly, and rejects malformed configs (bad enum values, conflicting fields) with actionable error messages

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### schema.py

Add `ParallelStateConfig` dataclass following the `LoopConfigOverrides` pattern at `schema.py:459` (`to_dict` at `:477`, `from_dict` at `:498`):

```python
@dataclass
class ParallelStateConfig:
    items: str                       # interpolated expression resolving to newline-delimited list
    loop: str                        # sub-loop name to run per item
    max_workers: int = 4
    isolation: str = "thread"        # "thread" (default) | "worktree"
    fail_mode: str = "collect"       # "collect" | "fail_fast"
    context_passthrough: bool = False
    timeout_seconds: int | None = None  # per-worker timeout; None = no timeout
    max_items: int = 1000            # hard cap on fan-out size; enforcement in ENH-1176
    max_total_seconds: int | None = None  # cumulative wall-clock cap; enforcement in ENH-1176

    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, data: dict) -> "ParallelStateConfig":
        ...
```

Add `parallel: ParallelStateConfig | None = None` to `StateConfig` (place after `loop` field at `schema.py:251`). Follow the `loop` field pattern in `to_dict()` (skip if None; `StateConfig.to_dict` spans `schema.py:257–316`) and `from_dict()` (use `data.get("parallel")`; `StateConfig.from_dict` spans `schema.py:319–375`).

### validation.py

- Add mutual exclusion + range/enum checks in `_validate_state_action()` at `validation.py:195–227` (alongside existing `loop`/`action` check at `:217–225`)
- NOTE: despite earlier drafts, do NOT add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` at `:77–99` — that frozenset is for YAML document-root keys only (`name`, `states`, `context`, etc.); state-level key filtering is handled by `additionalProperties: false` in the JSON Schema (`fsm-loop-schema.json:320`) and by `data.get()` in `StateConfig.from_dict()` (which silently ignores unknown state-level keys)
- Add mutual exclusion checks: `parallel` + `action`, `parallel` + `loop`, `parallel` + `next`
- Add range validation: `max_workers >= 1`; `timeout_seconds is None or timeout_seconds >= 1`; `max_items >= 1`; `max_total_seconds is None or max_total_seconds >= 1`
- Add cross-field check: if both `max_total_seconds` and `timeout_seconds` are set, emit a WARN (not ERROR) when `max_total_seconds <= max_workers * timeout_seconds`, since the cumulative cap would be dominated by per-worker timeouts and effectively unreachable (see ENH-1176 rationale)
- Add enum checks: `isolation` in `{"worktree", "thread"}`, `fail_mode` in `{"collect", "fail_fast"}`
- **Forbid nested parallel**: after parsing, check that the loop named in `parallel.loop` does not itself contain any state with a `parallel:` field. Nesting multiplies concurrency uncontrollably (`max_workers` × `max_workers` → 16+ concurrent workers with no upper bound) and there is no concrete use case for it in the scoped orchestrator loops (ENH-1073). Error message: `"parallel.loop '<name>' contains a nested parallel state at <state>; nested parallel states are not supported. Decompose into separate top-level parallel states or flatten the sub-loop."` This check runs at validation time (across all loaded loops), not at execution time, so authors catch it before running.

### Schema version marker

Add a version note at the top of `fsm-loop-schema.json` indicating when `parallel:` support was added. External validators that pin to an older version of the schema will continue to work against pre-`parallel` loops. Suggested marker: a top-level `"x-fsm-features"` object (ignored by JSON Schema validators) listing `{"parallel": "added in v<plugin-version>"}`. This is purely informational — the schema remains strictly additive — but gives external tools a single place to check feature availability without diffing schemas.

### fsm-loop-schema.json

Add `parallel:` as a valid state-level key with sub-fields matching `ParallelStateConfig` fields and their types/constraints.

## API/Interface

```python
@dataclass
class ParallelStateConfig:
    items: str                       # interpolated expression resolving to newline-delimited list
    loop: str                        # sub-loop name to run per item
    max_workers: int = 4
    isolation: str = "thread"        # "thread" (default) | "worktree"
    fail_mode: str = "collect"       # "collect" | "fail_fast"
    context_passthrough: bool = False
    timeout_seconds: int | None = None  # per-worker timeout; None = no timeout
    max_items: int = 1000            # hard cap on fan-out size; runtime enforcement in ENH-1176
    max_total_seconds: int | None = None  # cumulative wall-clock cap; runtime enforcement in ENH-1176

    def to_dict(self) -> dict: ...

    @classmethod
    def from_dict(cls, data: dict) -> "ParallelStateConfig": ...

# StateConfig extension (new field)
parallel: ParallelStateConfig | None = None
```

## Implementation Steps

1. Add `ParallelStateConfig` dataclass to `schema.py` following the `LoopConfigOverrides` pattern at `schema.py:459` — implement `to_dict()` (model after `:477`) and `from_dict()` (model after `:498`) using the same guard/cast idioms
2. Extend `StateConfig` with `parallel: ParallelStateConfig | None = None` (place after `loop` at `schema.py:251`); update `to_dict()` to skip if None (follow `evaluate`/`route` pattern at `schema.py:267–270`) and `from_dict()` to hydrate via `ParallelStateConfig.from_dict()` when key present (follow hydration block at `schema.py:321–327`)
3. Update `validation.py`: add mutual exclusion checks in `_validate_state_action()` at `:195–227` (`parallel` + `action`, `parallel` + `loop`, `parallel` + `next`); add `max_workers >= 1`, `timeout_seconds is None or timeout_seconds >= 1`, `max_items >= 1`, `max_total_seconds is None or max_total_seconds >= 1`, enum checks for `isolation` and `fail_mode`; add WARN when both `max_total_seconds` and `timeout_seconds` are set and `max_total_seconds <= max_workers * timeout_seconds`. Do NOT add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` — that frozenset is for YAML document-root keys; state-level unknown keys are silently ignored via `data.get()` in `from_dict()`
4. Update `fsm-loop-schema.json`: add `parallel:` as a valid state-level key with sub-field types and constraints matching `ParallelStateConfig`
5. Fix `_validate_state_routing` no-transition guard in `validation.py:271` — add `has_parallel = state.parallel is not None` to the guard condition (current guard: `if not has_shorthand and not has_route and not has_next and not has_terminal and not has_loop`) so valid `parallel:` states are not falsely flagged as having "no transition defined" (model after the existing `has_loop` exemption at `:269`; test with `test_parallel_state_no_transition_not_flagged`)
6. Run `test_fsm_schema.py`, `test_fsm_schema_fuzz.py`, `test_fsm_validation.py`, `test_fsm_fragments.py`, `test_builtin_loops.py`, `test_review_loop.py`, `test_outer_loop_eval.py`, and `test_ll_loop_commands.py` to verify no regressions from the new mutual-exclusion rules and the `_validate_state_routing` fix (the last three were identified by wiring analysis as exercising `validate_fsm` against all built-in loops and existing CLI fixtures)
7. Update `skills/review-loop/reference.md` V-series check table with three new rows (`parallel`+`action`, `parallel`+`loop`, `parallel`+`next` → ERROR) using the next available V-series IDs; add `parallel:` to State Type quick-reference table if one exists (folded from ENH-1166)

## Files to Modify

- `scripts/little_loops/fsm/schema.py` — Add `ParallelStateConfig`, extend `StateConfig` (follow `to_dict`/`from_dict` pattern at `:257–316` and `:319–375`)
- `scripts/little_loops/fsm/validation.py` — Add mutual exclusion and value-range checks in `_validate_state_action()` at `:195–227` (see CORRECTION note — do NOT add `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` at `:77–99`; that frozenset covers top-level YAML keys only)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `parallel:` object schema
- `skills/review-loop/reference.md` — Add three V-series rows for parallel mutual exclusions; add `parallel:` to State Type quick-reference if present (folded from ENH-1166)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — Add `ParallelStateConfig` dataclass (flat structure — simpler than `LoopConfigOverrides`); extend `StateConfig` with `parallel: ParallelStateConfig | None = None` field placed after the `loop` field at `:251`; update `to_dict()` at `:257–316` and `from_dict()` at `:319–375`
- `scripts/little_loops/fsm/validation.py` — Add mutual exclusion + range/enum checks in `_validate_state_action()` at `:195–227`; see correction note in Implementation Notes about `KNOWN_TOP_LEVEL_KEYS`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `parallel` to `stateConfig.properties` (currently `additionalProperties: false` at `:320` will reject any loop file using `parallel:` states without this addition)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — imports `StateConfig` and `LoopConfigOverrides`; dispatcher for FEAT-1076 will add `parallel` handling here
- `scripts/little_loops/fsm/runners.py` — FSM runner that invokes executor; no changes needed for this issue
- `scripts/little_loops/fsm/fragments.py` — shared fragment library using `from_dict`/`to_dict`; no changes needed
- `scripts/little_loops/fsm/persistence.py` — state persistence using `from_dict`/`to_dict`; `parallel` field will round-trip transparently once added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:113-184` — re-exports `StateConfig` via `__all__`; `LoopConfigOverrides` precedent = **do not export** `ParallelStateConfig` through `__init__.py` (import it directly from `schema.py` like `LoopConfigOverrides`); no change needed but decision must be deliberate
- `scripts/little_loops/cli/loop/layout.py:118-133` — `_get_state_badge()` switches on `state.loop`, `state.action`, `state.route`; no `parallel` branch — parallel states render with no badge (out of scope; address in FEAT-1078)
- `scripts/little_loops/cli/loop/info.py:556-563` — `_print_state_overview_table` Type column has no `parallel` branch (FEAT-1078 scope)
- `scripts/little_loops/cli/loop/run.py:107-115` — context variable pre-scan checks `state.action` but not `state.parallel.items`; `{{ issue_list }}`-style expressions in `items` won't be caught. Tracked as **ENH-1173** (see `.issues/enhancements/P3-ENH-1173-extend-unresolved-context-variable-pre-scan-to-cover-parallel-items.md`) — follow-up after FEAT-1074 lands.

_Wiring pass added by `/ll:wire-issue` (2026-04-20 pass):_
- `scripts/little_loops/cli/loop/_helpers.py` — imports `load_and_validate` inline; used by CLI dispatch layer. No code changes needed for FEAT-1074 but must pass regression run.
- `scripts/little_loops/cli/loop/config_cmds.py` — imports `load_and_validate` inline for the `validate` subcommand. No code changes needed for FEAT-1074 but must pass regression run.

### Similar Patterns (Exact Code References)
- `schema.py:477-520` — `LoopConfigOverrides.to_dict/from_dict`: shows skip-if-None pattern, but uses nested dict remapping; **`ParallelStateConfig` is flat so skip the nesting complexity**
- `schema.py:267-270` — `StateConfig.to_dict()` for `evaluate`/`route` nested dataclass fields: `if self.evaluate is not None: result["evaluate"] = self.evaluate.to_dict()` — use this exact pattern for `parallel`
- `schema.py:321-327` — `StateConfig.from_dict()` for nested dataclass hydration: `parallel = None; if "parallel" in data: parallel = ParallelStateConfig.from_dict(data["parallel"])` — use this exact pattern
- `schema.py:590-597` — `FSMLoop.to_dict()` double-guard pattern (check non-None AND non-empty dict before writing); not needed for `ParallelStateConfig` since it always has required fields
- `validation.py:217-225` — existing `loop`/`action` mutual exclusion: `"'loop' and 'action' are mutually exclusive — a sub-loop state cannot also have an action"` (path = `f"{path}"`, i.e., `states.<state_name>`)
- `validation.py:295-301` — range validation pattern: `f"'max_retries' must be >= 1, got {state.max_retries}"` — follow for `max_workers` check
- `test_fsm_schema.py:1866` — `test_loop_and_action_mutual_exclusion`: shows ERROR-level mutual exclusion test pattern using `str(e)` and `any()`
- `test_fsm_schema.py:1837, 1844, 1851, 1859` — loop field quartet: `test_to_dict_includes_loop_when_set` (:1837), `test_to_dict_excludes_loop_when_none` (:1844), `test_from_dict_with_loop` (:1851), `test_from_dict_without_loop` (:1859) — model parallel field tests after these

### Tests
- `scripts/tests/test_fsm_schema.py` — primary test file; `TestFSMValidation` at `:780` (15 methods, none assert total error counts — safe to add new validation rules)
- `scripts/tests/test_fsm_validation.py` — **separate validation-specific test file** not mentioned in the issue; new parallel mutual exclusion tests may fit here instead of `test_fsm_schema.py`
- `scripts/tests/test_fsm_fragments.py` — calls `validate_fsm` across built-in loops; new rules must not reject existing loops
- `scripts/tests/test_builtin_loops.py` — same concern; all 33+ built-in loops must continue to pass

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema_fuzz.py` — `TestStateConfigFuzz` exercises `StateConfig.from_dict()` with random inputs; include in regression run alongside `test_fsm_schema.py` to catch unexpected `parallel` field interactions

_Wiring pass added by `/ll:wire-issue` (2026-04-20 pass):_
- `scripts/tests/test_review_loop.py` — **include in regression run**: parametrizes `validate_fsm` over all `loops/*.yaml` built-in loops; if the `_validate_state_routing` fix changes what errors are emitted for any existing loop, this will surface it
- `scripts/tests/test_outer_loop_eval.py` — **include in regression run**: calls `load_and_validate` + `validate_fsm` against `outer-loop-eval.yaml` specifically
- `scripts/tests/test_ll_loop_commands.py` — **include in regression run**: 8 inline `load_and_validate` calls exercising the CLI `validate` subcommand end-to-end; may expose fixture-level regressions if new validation rules fire on existing test YAML

- New tests to write (add `TestParallelStateConfig` class to `test_fsm_schema.py` following `TestLoopConfigOverrides` at `:1904`):
  - `test_parallel_state_no_transition_not_flagged` — **critical**: verifies a valid `parallel:` state does NOT trigger the "no transition defined" error after the `_validate_state_routing` fix (model after `test_sub_loop_state_no_transition_error` at `test_fsm_schema.py:1884`)
  - `test_parallel_and_action_mutual_exclusion` — parallel + action → ERROR with both words in message (model after `test_loop_and_action_mutual_exclusion` at `test_fsm_schema.py:1866`)
  - `test_parallel_and_loop_mutual_exclusion` — parallel + loop → ERROR
  - `test_parallel_and_next_mutual_exclusion` — parallel + next → ERROR
  - `test_to_dict_includes_parallel_when_set` / `test_to_dict_excludes_parallel_when_none` — assert `"parallel" not in d` when `parallel=None` (model after `test_to_dict_excludes_loop_when_none` at `:1844`)
  - `test_from_dict_with_parallel` / `test_from_dict_without_parallel`
  - `test_parallel_state_config_roundtrip` — `ParallelStateConfig.from_dict(original.to_dict())` lossless for all 6 fields
  - Enum/range validation: `max_workers=0` → ERROR; `isolation="invalid"` → ERROR; `fail_mode="invalid"` → ERROR
  - `test_fsm_loop_schema_contains_parallel` — load `fsm-loop-schema.json` as JSON, assert `"parallel"` in `stateConfig.properties`; no existing test validates schema structural correctness (follow `test_config_schema.py` pattern: load JSON, assert structural keys)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_ (out of scope for FEAT-1074 — address in FEAT-1078)
- `docs/reference/API.md:3779-3795` — `StateConfig` dataclass block lists all fields; new `parallel: ParallelStateConfig | None = None` field is absent
- `docs/generalized-fsm-loop.md:241-273` — state-level YAML key listing does not include `parallel:` key
- `skills/create-loop/loop-types.md:978-1014` — documents `loop:` state type; no `parallel:` state type entry
- `skills/create-loop/reference.md:684-730` — `loop` field reference lists its mutual exclusions; no `parallel` field entry
- `skills/review-loop/reference.md:21-38` — V-series check table; new parallel mutual-exclusion checks (V-series IDs) not yet listed

### Configuration / Schema
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `stateConfig` definition at `:175`; `additionalProperties: false` at `:320`; `patternProperties` for `^on_` at `:314–319`

## Acceptance Criteria

- `ParallelStateConfig` dataclass exists with all 9 fields (`items`, `loop`, `max_workers`, `isolation`, `fail_mode`, `context_passthrough`, `timeout_seconds`, `max_items`, `max_total_seconds`) and `to_dict`/`from_dict`
- `StateConfig.parallel` field serializes/deserializes round-trip correctly (None when absent)
- `"parallel"` present in `KNOWN_TOP_LEVEL_KEYS` — no unknown-key warnings on loops using `parallel:`
- `isolation` defaults to `"thread"` in the dataclass, the JSON schema, and all example snippets
- `timeout_seconds` defaults to `None`; round-trips through `to_dict`/`from_dict`; `timeout_seconds=0` fails validation; `timeout_seconds=None` is permitted (no timeout)
- Mutual exclusion: state with `parallel:` + `action:` fails validation with a clear error
- Mutual exclusion: state with `parallel:` + `loop:` fails validation — error message names the `parallel.loop` sub-field as the correct way to declare a sub-loop for fan-out
- Mutual exclusion: state with `parallel:` + `next:` fails validation
- `max_workers: 0` fails validation
- `max_items: 0` fails validation; `max_items` defaults to `1000` and round-trips through `to_dict`/`from_dict`
- `max_total_seconds: 0` fails validation; `max_total_seconds: None` is permitted (no cumulative cap); defaults to `None` and round-trips through `to_dict`/`from_dict`
- A state with `max_workers: 4`, `timeout_seconds: 60`, `max_total_seconds: 120` emits a WARN that the cumulative cap is dominated by per-worker timeouts (cross-field sanity check)
- `isolation: "invalid"` fails validation
- `fail_mode: "invalid"` fails validation
- `fsm-loop-schema.json` reflects all constraints
- **V-series check table updated (folded from ENH-1166)**: `skills/review-loop/reference.md:21-38` V-series check table has three new rows covering `parallel`+`action`, `parallel`+`loop`, `parallel`+`next` mutual exclusions at ERROR severity, each with an invalid-YAML example. If a "State type quick reference" table exists in the same file, `parallel:` is added alongside `action:`, `loop:`, and `shell:` entries. This closes the gap between runtime validation (added by this issue) and `/ll:review-loop` authoring-time guidance.

## Tests (owned by this issue)

Moved from FEAT-1077 (2026-04-20) to break the circular dependency where FEAT-1077 gated on FEAT-1075 but FEAT-1076 needed schema tests passing before it could merge. Unit tests for the schema now land with this issue:

- **`test_fsm_schema.py::TestParallelStateConfig`** — round-trip `to_dict()`/`from_dict()`, defaults applied on minimal construction, `StateConfig` serializes/omits `parallel` key correctly
- **`test_fsm_schema.py::TestParallelMutualExclusion`** — follows `test_loop_and_action_mutual_exclusion:1722` pattern; covers `parallel`+`action`, `parallel`+`loop`, `parallel`+`next`, `max_workers: 0`, `max_items: 0`, `max_total_seconds: 0`, `isolation: "invalid"`, `fail_mode: "invalid"`, and the cumulative-cap-dominated-by-per-worker-timeout WARN
- **`test_fsm_validation.py`** — one test asserting a `parallel:` state with routing does NOT trigger the no-transition guard (the guard at `validation.py:271` gains `and not has_parallel` in this issue)
- **`test_fsm_schema_fuzz.py`** — add `parallel` block to `malformed_state_config` hypothesis strategy (defined at `:134`); insertion point is inside the body, before the `# Add unexpected fields` block at `:175`

`test_fsm_schema.py:636` `TestFSMValidation` may assert specific error counts — review for regressions after adding new mutual-exclusion rules.

## Implementation Notes

- Follow `LoopConfigOverrides.to_dict()` / `from_dict()` at `schema.py:459` as the serialization template
- `test_fsm_schema.py:780` `TestFSMValidation` may assert specific error counts — review for regressions after adding new mutual-exclusion rules
- `test_fsm_fragments.py` + `test_builtin_loops.py` call `validate_fsm` across all 33 built-in loops — new rules must not reject existing loops

### Why `isolation` defaults to `"thread"` (not `"worktree"`)

`thread` is sufficient and much faster for the common sub-loop shapes we expect to fan out: read-heavy analyses (lint, review, scan), evaluations, and classifiers. These sub-loops either don't write files or scope their writes to non-conflicting paths. Worktree isolation costs a `git worktree add` plus a working-copy checkout per worker, which dominates wall-clock time for small-to-medium loops. Making `thread` the default keeps the common case fast.

`worktree` remains the correct choice — and must be opted into — whenever sub-loops:
- Write the same files concurrently (e.g., two workers both editing `CHANGELOG.md`)
- Need an isolated working tree to run tests or build artifacts
- Change branch state or stage/unstage files

Authors who need worktree isolation set `isolation: "worktree"` explicitly; there is no magic auto-detection.

### Per-worker timeouts (`timeout_seconds`)

`timeout_seconds` caps a single worker's wall-clock time. `None` (the default) means no timeout. The runner spec in FEAT-1075 honors this via `future.result(timeout=timeout_seconds)` on each worker's future; a timed-out worker records a timeout verdict and is aggregated under `fail_mode` like any other failure. Keep the field optional — most loops will not need per-worker timeouts, and adding one by default would mask slow but valid sub-loops.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

_Re-verified 2026-04-20: all line-number references in this issue updated to match current file state (extensive drift since 2026-04-12 refinement — `schema.py` grew ~40 lines, `test_fsm_schema.py` grew ~144 lines, `fsm-loop-schema.json` grew ~28 lines in `stateConfig`)._

**CORRECTION — `KNOWN_TOP_LEVEL_KEYS` is wrong target**: `KNOWN_TOP_LEVEL_KEYS` at `validation.py:77` holds top-level YAML keys (`name`, `states`, `context`, etc. — 18 keys total, confirmed 2026-04-20). The `parallel:` key lives inside a state config (`states.my_state.parallel`), NOT at the top level. Adding `"parallel"` to `KNOWN_TOP_LEVEL_KEYS` has no effect on state-level validation. Further confirmed 2026-04-20: there is no state-level unknown-key frozenset check at all — unknown state-level keys are silently ignored because `StateConfig.from_dict()` uses `data.get("key")` for every field. The actual fix for IDE unknown-key warnings is adding `parallel` to `stateConfig.properties` in `fsm-loop-schema.json` (where `additionalProperties: false` at `:320` enforces the constraint). Drop the `KNOWN_TOP_LEVEL_KEYS` step from Implementation Steps 3.

**`TestFSMValidation` does NOT assert total error counts**: Research confirmed all 15 test methods use `any("substring" in e.message for e in errors)` or `len(filtered_list) == 0` patterns — adding new parallel mutual-exclusion rules will not break any existing error count assertions.

**Exact `to_dict`/`from_dict` patterns for `ParallelStateConfig`** (flat dataclass — simpler than `LoopConfigOverrides`):
```python
# to_dict: skip-if-default for booleans; always include required fields
def to_dict(self) -> dict[str, Any]:
    result: dict[str, Any] = {"items": self.items, "loop": self.loop}
    if self.max_workers != 4:
        result["max_workers"] = self.max_workers
    if self.isolation != "thread":
        result["isolation"] = self.isolation
    if self.fail_mode != "collect":
        result["fail_mode"] = self.fail_mode
    if self.context_passthrough:
        result["context_passthrough"] = self.context_passthrough
    if self.timeout_seconds is not None:
        result["timeout_seconds"] = self.timeout_seconds
    if self.max_items != 1000:
        result["max_items"] = self.max_items
    if self.max_total_seconds is not None:
        result["max_total_seconds"] = self.max_total_seconds
    return result

# from_dict: data.get with defaults for optional fields
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "ParallelStateConfig":
    return cls(
        items=data["items"],
        loop=data["loop"],
        max_workers=data.get("max_workers", 4),
        isolation=data.get("isolation", "thread"),
        fail_mode=data.get("fail_mode", "collect"),
        context_passthrough=data.get("context_passthrough", False),
        timeout_seconds=data.get("timeout_seconds"),
        max_items=data.get("max_items", 1000),
        max_total_seconds=data.get("max_total_seconds"),
    )
```

**Exact StateConfig extension pattern** (follow `evaluate`/`route` at `schema.py:267-270`, `:321-327`):
```python
# In StateConfig.to_dict() (insert near the evaluate/route skip-if-None guards at :267-270):
if self.parallel is not None:
    result["parallel"] = self.parallel.to_dict()

# In StateConfig.from_dict() (insert near the evaluate/route hydration block at :321-327, before the cls(...) call):
parallel = None
if "parallel" in data:
    parallel = ParallelStateConfig.from_dict(data["parallel"])
# Then pass parallel=parallel to cls(...)
```

**Exact validation error message formats** (follow established patterns in `validation.py:217-225`, `281-301`):
```python
# Mutual exclusion errors (ERROR severity, path = f"states.{state_name}")
"'parallel' and 'action' are mutually exclusive — a parallel state cannot also have an action"
"'parallel' and 'loop' are mutually exclusive at the state level — use 'parallel.loop' to name the sub-loop to fan out; do not set a top-level 'loop:' field on the same state"
"'parallel' and 'next' are mutually exclusive — parallel state transitions are managed by the parallel runner"

# Range validation
f"'max_workers' must be >= 1, got {state.parallel.max_workers}"
f"'timeout_seconds' must be >= 1 when set, got {state.parallel.timeout_seconds}"
f"'max_items' must be >= 1, got {state.parallel.max_items}"
f"'max_total_seconds' must be >= 1 when set, got {state.parallel.max_total_seconds}"

# Cross-field sanity (WARN, not ERROR)
f"'max_total_seconds' ({state.parallel.max_total_seconds}s) is <= max_workers * timeout_seconds "
f"({state.parallel.max_workers} * {state.parallel.timeout_seconds}s); cumulative cap may be unreachable"

# Enum validation
f"'isolation' must be one of {{'worktree', 'thread'}}, got {repr(state.parallel.isolation)}"
f"'fail_mode' must be one of {{'collect', 'fail_fast'}}, got {repr(state.parallel.fail_mode)}"
```

**`fsm-loop-schema.json` parallel property structure** (add to `stateConfig.properties` before `additionalProperties: false` at `:320`):
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
    "isolation": {"type": "string", "enum": ["worktree", "thread"], "default": "thread"},
    "fail_mode": {"type": "string", "enum": ["collect", "fail_fast"], "default": "collect"},
    "context_passthrough": {"type": "boolean", "default": false},
    "timeout_seconds": {"type": ["integer", "null"], "minimum": 1, "default": null},
    "max_items": {"type": "integer", "minimum": 1, "default": 1000},
    "max_total_seconds": {"type": ["integer", "null"], "minimum": 1, "default": null}
  }
}
```

**Test file for mutual exclusion tests**: `test_fsm_validation.py` is a dedicated validation test file (not listed in the issue). New parallel mutual exclusion tests belong there (or in `TestFSMValidation` at `test_fsm_schema.py:780`). Follow the `test_loop_and_action_mutual_exclusion` pattern at `test_fsm_schema.py:1866`: build an `FSMLoop` with conflicting fields, call `validate_fsm(fsm)`, assert `any("parallel" in m and "action" in m for m in [str(e) for e in errors])`.

## Impact

- **Priority**: P2 — Blocks FEAT-1075 (parallel runner) and FEAT-1076 (executor dispatch); no workaround without this schema foundation
- **Effort**: Small — Pure additive schema/validation code; clear patterns to follow (`LoopConfigOverrides` in `schema.py:419`); no new algorithms
- **Risk**: Low — Additive changes only; existing loops unaffected; new validation rules apply exclusively to states using `parallel:` key
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `schema`, `validation`

---

## Session Log
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc3e3d8e-1c7e-467c-8219-ec0095654dc3.jsonl`
- `/ll:wire-issue` - 2026-04-21T01:13:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b0e731e-20eb-4f30-a674-0a436f2d8692.jsonl`
- `/ll:refine-issue` - 2026-04-21T01:07:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cdc2857-a6c9-41f4-9e21-dba00a1cd48c.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dde26ebe-176b-4ecd-907d-cdda6cf9667d.jsonl`
- `/ll:wire-issue` - 2026-04-12T21:23:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ac6a699-fe93-4fc5-bb86-1ef76e8c42f2.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:16:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/deffc1f6-3d06-45f7-8667-df4243e14b0f.jsonl`
- `/ll:format-issue` - 2026-04-12T21:08:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/751c4dab-a709-4fca-88d5-86efedd1b15c.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2

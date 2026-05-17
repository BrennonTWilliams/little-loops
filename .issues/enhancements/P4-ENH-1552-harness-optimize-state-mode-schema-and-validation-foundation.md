---
id: ENH-1552
type: ENH
priority: P4
status: done
parent: ENH-1535
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-17T10:07:25Z
---

# ENH-1552: harness-optimize State-Mode — Schema & Validation Foundation

## Summary

Add the Python dataclass schema (`TargetStateSpec`, `TargetFileSpec`) and validation rules that enable `harness-optimize` to accept a per-FSM-state targeting spec. Registers the new types in the public FSM API and the hand-maintained JSON Schema. This child is independently shippable — it introduces typed structures and tests with no change to any loop YAML.

## Current Behavior

`FSMLoop` has no `targets:` field and no `TargetStateSpec`/`TargetFileSpec` dataclasses. Any loop YAML containing a top-level `targets:` key triggers a spurious "Unknown top-level key" warning at load time. `from little_loops.fsm import TargetFileSpec` raises `ImportError`. The hand-maintained `fsm-loop-schema.json` has no `targets` property, so IDE/editor tooling reports schema validation errors for any YAML that attempts to use the new key.

## Expected Behavior

After implementation: `FSMLoop.from_dict()` parses an optional `targets:` array into `list[TargetFileSpec]`, defaulting to `[]` when absent. `TargetStateSpec` and `TargetFileSpec` are importable from `little_loops.fsm`. Validation rejects any `targets[].states[]` entry whose sibling `file:` value is not a `.yaml` extension. `fsm-loop-schema.json` accepts `targets:` without schema errors. No existing loop YAMLs are affected.

## Scope Boundaries

- No changes to any loop YAML (including `harness-optimize.yaml`) — that is ENH-1554
- No changes to FSM executor behavior — the `targets` field is parsed and stored but not consumed until ENH-1554
- CLI changes limited to `FSMLoop.to_dict()` serialization so `ll-loop show --json` emits the field
- No new CLI commands or flags

## Impact

- **Priority**: P4 — Foundation for ENH-1554; no user-visible behavior change on its own
- **Effort**: Small — Additive dataclass + validation + JSON Schema entries; follows established patterns (`ThrottleConfig`, `LearningConfig`)
- **Risk**: Low — New optional field with `[]` default; all existing loop YAMLs omit `targets:` and will default gracefully
- **Breaking Change**: No

## Labels

`schema`, `fsm`, `harness-optimize`, `dataclass`, `validation`

## Parent Issue

Decomposed from ENH-1535: Meta-APO — Per-FSM-State Targeting for harness-optimize

## Covers (from ENH-1535 Implementation Steps)

- Step 2: Extend schema dataclasses in `scripts/little_loops/fsm/schema.py`
- Step 3: Extend schema validation in `scripts/little_loops/fsm/validation.py`
- Step 10 (wiring): Export new dataclasses from `fsm/__init__.py`
- Step 11 (wiring): Update `fsm/fsm-loop-schema.json`
- Step 13 (wiring): Add `TargetStateSpec`/`TargetFileSpec` tests to `test_fsm_schema.py`
- `test_fsm_validation.py` new test (from Integration Map → Tests)

## Implementation Steps

1. **`scripts/little_loops/fsm/schema.py`**:
   - Add `TargetStateSpec(name: str, examples_file: str, eval_fragment: str)` dataclass with `from_dict()` classmethod
   - Add `TargetFileSpec(file: str | None, glob: str | None, states: list[TargetStateSpec])` dataclass with `from_dict()` classmethod
   - Extend `FSMLoop.from_dict()` to parse optional top-level `targets:` array into `list[TargetFileSpec]`; default to `[]` when absent

2. **`scripts/little_loops/fsm/validation.py`**:
   - Add `"targets"` to the `KNOWN_TOP_LEVEL_KEYS` frozenset (removes spurious `WARNING` for the new key)
   - In `load_and_validate()`, add a validation pass: reject any `targets[].states[]` entry where the sibling `file:` value is not a `.yaml` extension

3. **`scripts/little_loops/fsm/__init__.py`**:
   - Add `TargetStateSpec` and `TargetFileSpec` to the import block from `little_loops.fsm.schema`
   - Add both to the `__all__` list so `from little_loops.fsm import TargetFileSpec` does not raise `ImportError`

4. **`scripts/little_loops/fsm/fsm-loop-schema.json`**:
   - Add a `targets` property definition (has `"additionalProperties": false` at root — line 200)
   - Schema structure: `targets` is an array of objects with `file` (string, optional), `glob` (string, optional), `states` (array of objects with `name`, `examples_file`, `eval` — all strings)
   - IDE/editor tooling only; not enforced at runtime, but blocks editor validation without this change

5. **`scripts/tests/test_fsm_schema.py`**:
   - `TargetStateSpec.from_dict()` round-trip test
   - `TargetFileSpec.from_dict()` round-trip test
   - `FSMLoop.from_dict()` with a `targets:` key populates the new field
   - `FSMLoop.from_dict()` without `targets:` defaults to `[]`
   - `test_known_keys_no_warning`-style test confirming a YAML with `targets:` produces zero unknown-key warnings after the frozenset update — follow the pattern of `TestLoadAndValidateIntegration.test_commands_key_no_warning` (line 1636)

6. **`scripts/tests/test_fsm_validation.py`**:
   - New test: validation rejects a `targets[].states[]` entry where the sibling `file:` is not a `.yaml` extension

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **`scripts/little_loops/fsm/schema.py`** — Extend `FSMLoop.to_dict()` to serialize the `targets` field: emit `"targets": [t.to_dict() for t in self.targets]` only when `self.targets` is non-empty (follow the same skip-if-empty pattern used for other optional list fields). Required for `ll-loop show --json` via `cli/loop/info.py:664`.

8. **`docs/reference/API.md`** — In the `#### FSMLoop` dataclass listing (~line 3869), add `targets: list[TargetFileSpec] = []`. After the `#### LearningConfig` subsection (~line 4012), add `#### TargetStateSpec` and `#### TargetFileSpec` subsections. Update the import block example (~line 3836) to include `TargetFileSpec` and `TargetStateSpec`.

## Files to Modify

- `scripts/little_loops/fsm/schema.py`
- `scripts/little_loops/fsm/validation.py`
- `scripts/little_loops/fsm/__init__.py`
- `scripts/little_loops/fsm/fsm-loop-schema.json`
- `scripts/tests/test_fsm_schema.py`
- `scripts/tests/test_fsm_validation.py`
- `docs/reference/API.md` — FSMLoop field listing + new TargetStateSpec/TargetFileSpec subsections [wiring pass]

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Insertion Points (with Line Numbers)

- `scripts/little_loops/fsm/schema.py:794` — `FSMLoop.from_dict()` starts here; insert `TargetStateSpec` and `TargetFileSpec` dataclasses **before** this line. Add `targets: list[TargetFileSpec] = field(default_factory=list)` to `FSMLoop` fields and parse via `[TargetFileSpec.from_dict(t) for t in data.get("targets", [])]` inside `FSMLoop.from_dict()`.
- `scripts/little_loops/fsm/validation.py:78` — `KNOWN_TOP_LEVEL_KEYS` frozenset defined here; add `"targets"` to this set. The new validation pass (reject non-`.yaml` sibling `file:` values) should be added as a new `_validate_targets(fsm)` helper called from `validate_fsm()` (lines 616–750), following the accumulator pattern (`errors.extend(_validate_targets(fsm))`). The `path` convention to use: `"targets[N].file"`.
- `scripts/little_loops/fsm/__init__.py:124–135` — `from little_loops.fsm.schema import (...)` block; add `TargetFileSpec` and `TargetStateSpec` here. Also add both as string entries in `__all__` (lines 151–210), maintaining alphabetical order.
- `scripts/little_loops/fsm/fsm-loop-schema.json:8–199` — root `properties` block ends before `"additionalProperties": false` at line 200; insert `"targets"` property here. Add `targetFileSpec` and `targetStateSpec` definitions to the `definitions` section (after `llmConfig`, currently ending ~line 583). Note: `commands` (despite being in `FSMLoop.from_dict()`) is **not yet in the JSON schema** — there is no existing array-of-objects root property to copy from. Model the nested object inline or via `$ref` to new definitions.

#### Similar Patterns to Follow (file:line)

- `schema.py:227–267` — `ThrottleConfig` — model `TargetStateSpec` after this: all-optional fields, `from_dict()` uses `.get()` for every field, `to_dict()` skips `None` values
- `schema.py:270–305` — `LearningConfig` — model the `states: list[TargetStateSpec]` field after this: use `field(default_factory=list)` on the dataclass and `list(data.get("states") or [])` in `from_dict()`, calling `TargetStateSpec.from_dict()` on each element
- `schema.py:466–537` — `StateConfig.from_dict()` — pattern for conditionally calling nested `from_dict()` (presence-check before instantiation)
- `test_fsm_schema.py:2481–2486` — `ThrottleConfig.test_round_trip` — round-trip test pattern to follow
- `test_fsm_schema.py:2462–2472` — absent-field default tests (`test_from_dict_partial_fields`, `test_from_dict_empty`)
- `test_fsm_schema.py:1636` — `test_commands_key_no_warning` — **exact** no-warning test pattern; copy and adapt for `targets:` key
- `test_fsm_validation.py:136–154` — `test_max_without_on_fails` — validation-rejection test pattern: construct `FSMLoop` with invalid data, call `validate_fsm()`, assert `any("..." in e.message for e in errors)`

#### Dependent File (read-only reference)
- `scripts/little_loops/loops/harness-optimize.yaml` — built-in loop that will use `targets:` in ENH-1554; not modified by this issue

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — calls `fsm.to_dict()` at line 664 inside `_print_state_overview_table()` for `ll-loop show --json`; surfaces missing `FSMLoop.to_dict()` extension (see Implementation Steps Wiring Phase below) [Agent 1 / Agent 2 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — calls `load_and_validate()` via `load_loop()` on every loop YAML at startup; regression surface if `FSMLoop.from_dict()` does not default `targets=[]` when key is absent [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — imports `FSMLoop` from `schema`; read-only for this issue, no changes needed [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### FSMLoop` dataclass listing (~line 3869) currently ends at `commands: list[CommandEntry] = []`; add `targets: list[TargetFileSpec] = []` field. Add `#### TargetStateSpec` and `#### TargetFileSpec` subsections after the existing `#### LearningConfig` section (~line 4012), following the same format. Import block example (~line 3836) should include `TargetFileSpec` and `TargetStateSpec` [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_harness_optimize.py` — `TestHarnessOptimizeFile.test_validates_as_fsm` calls `load_and_validate(LOOP_FILE)` on `harness-optimize.yaml`; will fail if `FSMLoop.from_dict()` does not default `targets=[]` when key is absent — regression watch [Agent 2 / Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` iterates every loop YAML through `load_and_validate()`; same `targets=[]` default requirement — regression watch [Agent 2 / Agent 3 finding]
- `scripts/tests/test_review_loop.py` — top-level `from little_loops.fsm import validate_fsm` at line 19; fails at pytest-collection time if `fsm/__init__.py` export is broken — `__init__.py` integrity watch [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — `test_rate_limit_*_event_constant_exported` (lines 4806–4822) import event constants directly from `little_loops.fsm`; fail if `__init__.py` import block breaks existing re-exports — `__init__.py` integrity watch [Agent 3 finding]

## Acceptance Criteria

- [ ] `TargetStateSpec` and `TargetFileSpec` dataclasses parse correctly from dict and default gracefully
- [ ] `FSMLoop.from_dict()` with `targets:` populates the list; without it defaults to `[]`
- [ ] Validation rejects `states:` on a non-`.yaml` sibling file
- [ ] `"targets"` in `KNOWN_TOP_LEVEL_KEYS` produces zero spurious warnings
- [ ] `from little_loops.fsm import TargetFileSpec` does not raise `ImportError`
- [ ] All new tests pass; no regressions in existing `test_fsm_schema.py` or `test_fsm_validation.py`

## Ordering

Can be worked in parallel with ENH-1553 (YAML round-trip helper). ENH-1554 depends on this child.

## Status

**Open** | Created: 2026-05-17 | Priority: P4

## Resolution

Implemented all steps from the issue:

- Added `TargetStateSpec` and `TargetFileSpec` dataclasses to `fsm/schema.py` following the `ThrottleConfig`/`LearningConfig` patterns
- Extended `FSMLoop` with `targets: list[TargetFileSpec]` field; `from_dict` parses `targets:`, `to_dict` emits it when non-empty
- Added `"targets"` to `KNOWN_TOP_LEVEL_KEYS` in `validation.py` and added `_validate_targets()` helper rejecting non-`.yaml` sibling `file:` values
- Exported `TargetFileSpec` and `TargetStateSpec` from `fsm/__init__.py` and `__all__`
- Added `targets` property + `targetFileSpec`/`targetStateSpec` definitions to `fsm-loop-schema.json`
- Added 18 tests across `test_fsm_schema.py` (round-trip, defaults, no-warning) and `test_fsm_validation.py` (file extension rejection)
- Updated `docs/reference/API.md` with new field and subsections

All 653 tests pass, no regressions.

## Session Log
- `/ll:ready-issue` - 2026-05-17T10:02:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ac76456-978a-48e1-90ef-b033a3e9ce27.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86e13a1e-d2cd-4438-a454-96945bbb8a82.jsonl`
- `/ll:wire-issue` - 2026-05-17T09:57:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0f1ba70-d1e9-4509-8d3b-cafbe5231236.jsonl`
- `/ll:refine-issue` - 2026-05-17T09:51:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7cb355b-efac-4c30-841e-e88041e81fcc.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5cf22fe-a508-4b58-ace6-dd0a2c4187a3.jsonl`
- `/ll:manage-issue` - 2026-05-17T10:07:25Z - implementation complete

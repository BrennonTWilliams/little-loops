---
discovered_date: 2026-03-09
discovered_by: capture-issue
---

# ENH-661: Add Unknown-Key Detection to validate_fsm()

## Summary

Add unknown-key detection to `validate_fsm()` to warn users when their FSM loop YAML contains unrecognized top-level keys (e.g., `max_iteration` instead of `max_iterations`), closing a silent-misconfiguration gap without adding a `jsonschema` dependency.

## Current Behavior

Misspelled or unrecognized top-level keys in a loop YAML file are silently ignored by `FSMLoop.from_dict()` and `validate_fsm()`. Users receive no feedback that their configuration has a typo, leading to subtle misconfiguration bugs (e.g., `max_iteration: 5` is accepted without warning but has no effect).

## Expected Behavior

`ll-loop validate` emits a `WARNING`-severity `ValidationError` for each unknown top-level key found in the YAML config. Known keys produce no warning. Validation does not fail (no ERROR) for unknown keys — only warns.

## Motivation

The FSM loop YAML schema (`fsm-loop-schema.json`) uses `additionalProperties: false` on `stateConfig` to reject unknown keys, but this schema is never enforced at runtime. As a result, misspelled or unrecognized top-level keys in a loop YAML file are silently ignored by `FSMLoop.from_dict()` and `validate_fsm()`. Users get no feedback that their configuration has a typo (e.g. `max_iteration` instead of `max_iterations`), leading to subtle misconfiguration bugs.

Adding unknown-key detection directly to `validate_fsm()` closes this gap without adding a `jsonschema` dependency.

## Proposed Solution

In `scripts/little_loops/fsm/validation.py`, add a check at the start of `validate_fsm()` (or in `load_and_validate()` before parsing) that compares the raw YAML dict keys against a known allowlist:

```python
KNOWN_TOP_LEVEL_KEYS = {
    "name", "initial", "states", "paradigm", "context", "scope",
    "max_iterations", "backoff", "timeout", "maintain", "llm", "on_handoff",
}

unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS
if unknown:
    errors.append(ValidationError(
        path="<root>",
        message=f"Unknown top-level keys: {', '.join(sorted(unknown))}",
        severity=ValidationSeverity.WARNING,
    ))
```

Emit as a **WARNING** (not ERROR) to avoid breaking existing loops with forward-compatible or experimental keys.

> **Note**: `on_handoff` is read by `FSMLoop.from_dict()` at `schema.py:430` (`data.get("on_handoff", "pause")`) but is absent from `fsm-loop-schema.json`. Include it in `KNOWN_TOP_LEVEL_KEYS` to avoid false-positive warnings on valid YAML files that use `on_handoff`.

### Architectural Constraint: Raw Dict Only Available in load_and_validate()

`validate_fsm()` receives a typed `FSMLoop` dataclass — the raw YAML dict has already been consumed by `FSMLoop.from_dict()`. The unknown-key check **must run in `load_and_validate()`** (between lines 357 and 369, after YAML parse and before `FSMLoop.from_dict()`).

**However**, `cmd_validate()` (`config_cmds.py:77`) re-calls `validate_fsm(fsm)` to collect warnings for display — it never sees warnings emitted inside `load_and_validate()`. Two implementation options:

| Option | Change | Trade-off |
|--------|--------|-----------|
| **A** (recommended) | Change `load_and_validate()` return to `tuple[FSMLoop, list[ValidationError]]`; update callers | Warnings visible in `cmd_validate()` output; requires updating `_helpers.py`, `run.py`, and test callers |
| **B** | Keep return type; warnings only go to `logger.warning()` | No caller changes; warnings NOT shown in `ll-loop validate` output |

Option A matches the acceptance criteria ("ll-loop validate warns on unknown top-level keys").

## Scope Boundaries

- **In scope**:
  - `scripts/little_loops/fsm/validation.py` — add `KNOWN_TOP_LEVEL_KEYS` constant and unknown-key check in `validate_fsm()` or `load_and_validate()`
  - `scripts/tests/test_fsm_schema.py` — add case to `TestFSMValidation` for unknown top-level key warning
  - No new dependencies required

- **Out of scope**:
  - Per-state unknown key checking (future issue)

## Implementation Steps

1. **`validation.py`**: Add `KNOWN_TOP_LEVEL_KEYS: frozenset[str]` constant near line 70 (alongside `VALID_OPERATORS`). Include all 12 keys read by `FSMLoop.from_dict()` at `schema.py:417-430`.
2. **`validation.py:load_and_validate()`**: Between lines 357 (required-fields check) and 369 (`FSMLoop.from_dict(data)`), compute `unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS` and build a `list[ValidationError]` of WARNING-severity entries.
3. **`validation.py:load_and_validate()`**: Change return type from `FSMLoop` to `tuple[FSMLoop, list[ValidationError]]`. Merge unknown-key warnings with the warnings already collected from `validate_fsm()` (lines 381-384). Return `(fsm, warnings)`.
4. **`config_cmds.py:cmd_validate()`** (~line 74): Unpack `fsm, load_warnings = load_and_validate(path)`. Remove the second call to `validate_fsm(fsm)` at line 77 (or keep it; merge `load_warnings + validate_fsm(fsm)` for the warning display). Display all warnings at lines 80-85.
5. **`_helpers.py` and `run.py`**: Update callers of `load_and_validate()` to unpack the tuple (or discard warnings with `fsm, _ = load_and_validate(path)`).
6. **`test_fsm_schema.py`**: Add test to `TestFSMValidation` or `TestLoadAndValidate` (line 1291): write a YAML fixture or in-memory dict with `foo: bar` at top level → assert one WARNING containing "foo" in the returned warnings list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `validation.py:194` — `validate_fsm(fsm: FSMLoop) -> list[ValidationError]` operates on typed dataclass only; no raw dict access possible here
- `validation.py:336-386` — `load_and_validate(path: Path) -> FSMLoop`; raw dict available at lines 354-369
- `validation.py:60-70` — `EVALUATOR_REQUIRED_FIELDS` (dict) and `VALID_OPERATORS` (set) are the existing module-level allowlist patterns to follow
- `config_cmds.py:74-85` — `cmd_validate()` calls `load_and_validate()` then re-calls `validate_fsm()` at line 77 specifically to recover warnings; return type change required to surface unknown-key warnings here
- `schema.py:406-430` — `FSMLoop.from_dict()` reads: `name`, `initial`, `states`, `paradigm`, `context`, `scope`, `max_iterations`, `backoff`, `timeout`, `maintain`, `llm`, `on_handoff` (12 keys)
- `test_fsm_schema.py:1291` — `TestLoadAndValidate` class; fixtures in `scripts/tests/fixtures/fsm/`
- `test_fsm_schema.py:579-597` — WARNING test pattern: `warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]; assert any("substring" in e.message for e in warnings)`

## Acceptance Criteria

- `ll-loop validate` warns on unknown top-level keys (e.g. `max_iteration`, `foo`)
- Known keys are not warned on
- Validation does not fail (ERROR) for unknown keys — only warns
- New test passes alongside existing `TestFSMValidation` suite

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `KNOWN_TOP_LEVEL_KEYS` constant; add unknown-key check in `load_and_validate()` before `FSMLoop.from_dict()`
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` already surfaces warnings; verify warning passthrough

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/config_cmds.py:74` — calls `load_and_validate(path)` then `validate_fsm(fsm)` a second time (line 77) to collect warnings for display
- `scripts/little_loops/cli/loop/_helpers.py` — calls `load_and_validate` / `validate_fsm`
- `scripts/little_loops/cli/loop/run.py` — calls `load_and_validate` / `validate_fsm`
- `scripts/tests/test_fsm_schema.py` — `TestLoadAndValidate` (line 1291) and `TestFSMValidation` (line 530)

### Similar Patterns
- `EVALUATOR_REQUIRED_FIELDS` in `validation.py:60-67` — existing dict-based allowlist constant pattern to follow
- `VALID_OPERATORS` in `validation.py:70` — closer analogy: a `set` used as a membership allowlist, checked via `not in VALID_OPERATORS` at line 99-106
- `ValidationError(message=..., path=..., severity=ValidationSeverity.WARNING)` — WARNING instantiation pattern used at lines 169-176 and 295-300

### Tests
- `scripts/tests/test_fsm_schema.py` — add case to `TestFSMValidation` for unknown top-level key warning

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Low priority; affects developer experience but causes no data loss or blocking behavior
- **Effort**: Small — single function addition in one file, one new test
- **Risk**: Low — WARNING only, no behavioral change for valid YAML configs
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `validation`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5816af14-e401-4b6a-acd7-f46274a6140a.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5816af14-e401-4b6a-acd7-f46274a6140a.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/41ee4062-40ab-452f-8d2c-b2cd2867570e.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3048e96b-1730-44aa-8df6-029c8217cf8b.jsonl`

## Resolution

Implemented Option A: changed `load_and_validate()` return type to `tuple[FSMLoop, list[ValidationError]]`. Added `KNOWN_TOP_LEVEL_KEYS` frozenset and unknown-key detection before `FSMLoop.from_dict()`. Updated all callers (`config_cmds.py`, `_helpers.py`, `run.py`) and test mocks. Added 2 new tests in `TestLoadAndValidate`. All 3466 tests pass.

---
**Completed** | Created: 2026-03-09 | Completed: 2026-03-09 | Priority: P4

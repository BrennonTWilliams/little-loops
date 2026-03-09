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
    "max_iterations", "backoff", "timeout", "maintain", "llm",
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

## Scope Boundaries

- **In scope**:
  - `scripts/little_loops/fsm/validation.py` — add `KNOWN_TOP_LEVEL_KEYS` constant and unknown-key check in `validate_fsm()` or `load_and_validate()`
  - `scripts/tests/test_fsm_schema.py` — add case to `TestFSMValidation` for unknown top-level key warning
  - No new dependencies required

- **Out of scope**:
  - Per-state unknown key checking (future issue)

## Implementation Steps

1. Define `KNOWN_TOP_LEVEL_KEYS` constant near the top of `validation.py` (alongside existing `EVALUATOR_REQUIRED_FIELDS`)
2. In `load_and_validate()`, after the required-fields check and before `FSMLoop.from_dict()`, compute unknown keys from `data.keys()`
3. Collect warnings (don't raise) — return them from `load_and_validate()` alongside the `FSMLoop`, or append to a shared warnings list
4. Surface warnings via `cmd_validate()` in `config_cmds.py` (already surfaces other warnings)
5. Add unit test: loop YAML with an extra key `foo: bar` at top level → produces one WARNING containing "foo"
6. Consider whether per-state unknown keys should also be checked (out of scope for this issue)

## Acceptance Criteria

- `ll-loop validate` warns on unknown top-level keys (e.g. `max_iteration`, `foo`)
- Known keys are not warned on
- Validation does not fail (ERROR) for unknown keys — only warns
- New test passes alongside existing `TestFSMValidation` suite

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `KNOWN_TOP_LEVEL_KEYS` constant; add unknown-key check in `load_and_validate()` before `FSMLoop.from_dict()`
- `scripts/little_loops/config_cmds.py` — `cmd_validate()` already surfaces warnings; verify warning passthrough

### Dependent Files (Callers/Importers)
- TBD — use grep: `grep -r "validate_fsm\|load_and_validate" scripts/`

### Similar Patterns
- `EVALUATOR_REQUIRED_FIELDS` in `validation.py` — existing allowlist pattern to follow

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

---
**Open** | Created: 2026-03-09 | Priority: P4

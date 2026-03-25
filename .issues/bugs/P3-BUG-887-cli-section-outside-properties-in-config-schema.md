---
discovered_date: 2026-03-25
discovered_by: audit-architecture
focus_area: integration
confidence_score: 100
outcome_confidence: 86
---

# BUG-887: `cli` section placed outside `properties` in config-schema.json — never validated

## Summary

The `"cli"` key in `config-schema.json` is defined at the root schema object level as a
sibling to `"properties"` and `"additionalProperties"` rather than inside `"properties"`.
JSON Schema validators ignore it entirely: `cli.*` settings receive no type checking,
no autocomplete, and `additionalProperties: false` offers no protection against typos
in `cli` sub-keys.

## Current Behavior

The `"cli"` key in `config-schema.json` is a sibling of `"properties"` at the root schema
level. JSON Schema validators treat unrecognized root keywords as annotations and skip them
entirely. As a result:

1. Schema validators (VS Code, jsonschema, Pydantic, etc.) do not validate `cli` contents.
2. `"additionalProperties": false` on the root does NOT treat `cli` as an allowed property.
3. IDE autocomplete does not suggest `cli`, `cli.color`, `cli.colors.*`, etc.
4. A user misspelling `cli.colors.prioriyt` gets no warning.

## Expected Behavior

The `"cli"` key should be defined inside the `"properties"` object so that JSON Schema
validators:
- Type-check `cli.*` settings
- Offer IDE autocomplete for `cli`, `cli.color`, `cli.colors.*`, etc.
- Report validation errors for unrecognized sub-keys (e.g., `cli.colors.prioriyt`)
- Treat `cli` as an allowed property under `additionalProperties: false`

## Steps to Reproduce

1. Open `config-schema.json` in an IDE with JSON Schema validation (e.g., VS Code)
2. Open an `ll-config.json` that references the schema via `"$schema"`
3. Add a `cli` key with an invalid sub-key: `"cli": { "colorrs": true }`
4. Observe: no validation warning is shown — the typo is silently accepted

Alternatively, validate programmatically:
```bash
python -m jsonschema --instance .claude/ll-config.json config-schema.json
# Add "cli": {"invalid_key": true} to ll-config.json — expect error, observe none
```

## Root Cause

- **File**: `config-schema.json`
- **Anchor**: root schema object (line 810)
- **Cause**: The `"cli"` section was added after the closing brace of `"properties"` rather
  than inside it, making it a sibling to `"properties"` instead of a nested property.
  JSON Schema ignores unknown keywords at the root level.

## Location

- **File**: `config-schema.json`
- **Line**: 810
- **Section**: Root schema object

## Finding

### Current State

```json
// config-schema.json (abbreviated)
{
  "$schema": "...",
  "type": "object",
  "properties": {
    "project": {...},
    ...
    "sync": {...}
  },             ← "properties" closes at line 809
  "cli": {       ← line 810: sibling to "properties", NOT inside it
    "type": "object",
    "description": "CLI output settings",
    "properties": { "color": {...}, "colors": {...} },
    "additionalProperties": false
  },
  "additionalProperties": false
}
```

The `"cli"` keyword at the root schema level is not a recognized JSON Schema keyword, so
validators treat it as an annotation and skip it. Python runtime is unaffected
(`BRConfig._parse_config()` reads `_raw_config.get("cli", {})` correctly), but:

1. Schema validators (VS Code, jsonschema, Pydantic, etc.) do not validate `cli` contents.
2. `"additionalProperties": false` on the root does NOT treat `cli` as an allowed property.
3. IDE autocomplete does not suggest `cli`, `cli.color`, `cli.colors.*`, etc.
4. A user misspelling `cli.colors.prioriyt` gets no warning.

### Why it likely happened

The `cli` section was probably added at the end of the file and accidentally placed after
the closing brace of `"properties"` rather than inside it.

## Proposed Solution

Move `"cli"` from the root object into the `"properties"` object:

```json
"properties": {
  "project": {...},
  ...
  "sync": {...},
  "cli": {           ← move inside "properties"
    "type": "object",
    "description": "CLI output settings",
    "properties": { "color": {...}, "colors": {...} },
    "additionalProperties": false
  }
},
"additionalProperties": false
```

No Python code changes required — the runtime loading path is already correct.

## Motivation

This fix would:
- Restore schema correctness: `cli.*` settings are currently invisible to validators — type
  errors and typos go undetected silently
- Improve DX: IDE autocomplete does not suggest `cli`, `cli.color`, or `cli.colors.*` keys,
  making configuration discovery harder
- Align with existing patterns: all other top-level config sections (`project`, `issues`,
  `scan`, `sync`, etc.) are correctly placed inside `"properties"`

## Integration Map

### Files to Modify
- `config-schema.json` — move `"cli"` block inside `"properties"`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/brconfig.py` — `BRConfig._parse_config()` reads `cli` key via
  `_raw_config.get("cli", {})` — no changes needed (runtime path is already correct)

### Similar Patterns
- All other top-level schema sections (`project`, `issues`, `scan`, `sync`, etc.) are
  inside `"properties"` — this fix makes `cli` consistent with that pattern

### Tests
- `scripts/tests/test_config.py:1225` — `TestCliConfig`: unit tests for `CliConfig.from_dict` defaults/overrides
- `scripts/tests/test_config.py:1251` — `TestBRConfigCli`: integration tests for `BRConfig.cli` loading from `ll-config.json`
- No schema-level JSON validation tests exist anywhere in `scripts/tests/` (no `jsonschema` import found)
- No `test_cli_in_to_dict` test exists — needed since `to_dict()` currently omits `cli` (see Secondary Finding below)

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `config-schema.json:808-883` — Bug confirmed: `"properties"` closes at line 809 (`},`), then `"cli"` opens at line 810 as a sibling. The `"additionalProperties": false` at line 881 belongs to `"cli"`, and the root-level `"additionalProperties": false` is at line 883.
- `scripts/little_loops/config/core.py:342-440` — **Secondary gap**: `to_dict()` omits `"cli"` entirely. All other sections (`project`, `issues`, `automation`, `parallel`, `commands`, `scan`, `sprints`, `loops`, `sync`, `dependency_mapping`) are present; `cli` is the only missing one. This is a separate but related bug — `resolve_variable("cli.*")` will silently fail and any template using `{{config.cli.*}}` will break.
- `scripts/little_loops/config/cli.py` — `CliConfig` dataclass; `from_dict` classmethod exists
- `scripts/tests/test_config.py:928` — `test_sync_in_to_dict` pattern to follow for a `test_cli_in_to_dict` test
- `scripts/tests/conftest.py:66` — `sample_config` fixture does not include a `"cli"` key (no impact on existing tests)

## Implementation Steps

1. Open `config-schema.json` and locate the `"cli"` block at the root level (line 810, after `"properties"` closes at line 809)
2. Move the entire `"cli"` object (lines 810–882) inside `"properties"` as the last entry (after `"sync"` at line 748)
3. Verify JSON is structurally valid: `python -c "import json; json.load(open('config-schema.json'))"`
4. Validate `cli.*` keys are now recognized: add `"cli": {"invalid_key": true}` to `ll-config.json` and confirm `python -m jsonschema --instance .claude/ll-config.json config-schema.json` reports an error
5. **(Secondary fix)** Add `"cli"` to `to_dict()` in `scripts/little_loops/config/core.py:440` following the pattern of adjacent sections — `{"color": self._cli.color, "colors": {...}}`
6. Add `test_cli_in_to_dict` to `scripts/tests/test_config.py` following the pattern at line 928 (`test_sync_in_to_dict`)
7. Run tests: `python -m pytest scripts/tests/test_config.py -v -k "cli"`

## Impact

- **Priority**: P3 - Medium severity (schema correctness and DX degradation; no runtime impact)
- **Effort**: Small - JSON restructure only, no Python code changes required
- **Risk**: Low - No breaking change; runtime behavior is unchanged
- **Breaking Change**: No

## Labels

`bug`, `config`, `schema`, `auto-generated`

## Session Log
- `/ll:refine-issue` - 2026-03-25T23:19:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:format-issue` - 2026-03-25T23:14:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:confidence-check` - 2026-03-25T23:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`

---

## Status

**Open** | Created: 2026-03-25 | Priority: P3

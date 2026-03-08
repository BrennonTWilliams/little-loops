---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# ENH-651: Three config fields exist in code but are undocumented in schema

## Summary

Three fields in `config.py` have no corresponding entries in `config-schema.json`, making them undiscoverable by users inspecting the schema. They cannot be validated, autocompleted, or documented via schema tooling.

| Field | Location | Default |
|-------|----------|---------|
| `automation.idle_timeout_seconds` | `AutomationConfig` line 195 | `0` |
| `automation.max_continuations` | `AutomationConfig` line 200 | `3` |
| `parallel.require_code_changes` | `ParallelAutomationConfig` line 233 | `true` |

## Motivation

The schema is the contract between the tool and its users. Missing fields mean users can't discover, validate, or document these knobs without reading source code. Adding them enables schema-driven autocomplete and validation in IDEs and CI pipelines.

## Current Behavior

Three `config.py` fields have no schema entries:
- `automation.idle_timeout_seconds` (default `0`) — hidden from schema, no validation or IDE autocomplete
- `automation.max_continuations` (default `3`) — hidden from schema, no validation or IDE autocomplete
- `parallel.require_code_changes` (default `true`) — hidden from schema, no validation or IDE autocomplete

Users must read Python source to discover these settings.

**Notable gap**: The Phase 1 `ready-issue` calls in `issue_manager.py` (lines 313–368) pass `idle_timeout_seconds` but **not** `max_continuations`. Continuations during `ready-issue` always use the hardcoded default of `3` regardless of the configured value. Only the Phase 2 `manage-issue` call (line 531) respects `config.automation.max_continuations`.

## Expected Behavior

All three fields appear in `config-schema.json` with correct `type`, matching `default` values, and descriptive `description` strings. Schema-aware IDEs show autocomplete, and `jsonschema` validation catches invalid values.

## Proposed Solution

Add the three properties to their respective sections in `config-schema.json`:

**`automation` section (~line 160):**
```json
"idle_timeout_seconds": {
  "type": "integer",
  "default": 0,
  "description": "Seconds of inactivity before automation considers the session idle. 0 disables."
},
"max_continuations": {
  "type": "integer",
  "default": 3,
  "description": "Maximum number of continuation prompts before automation stops."
}
```

**`parallel` section (~line 230):**
```json
"require_code_changes": {
  "type": "boolean",
  "default": true,
  "description": "Require worktree to produce code changes before merging. Skips no-op runs."
}
```

## Implementation Steps

1. `config-schema.json:160` — insert `idle_timeout_seconds` and `max_continuations` after the closing `}` of `stream_output`, before the `"properties"` close brace at line 161 (just before `"additionalProperties": false` at line 162)
2. `config-schema.json:230` — insert `require_code_changes` after the closing `}` of `worktree_copy_files`, before the `"properties"` close brace at line 231 (just before `"additionalProperties": false` at line 232)
3. `scripts/tests/test_config.py:166-191` — update `TestAutomationConfig.test_from_dict_with_all_fields` and `test_from_dict_with_defaults` to assert `idle_timeout_seconds` and `max_continuations`
4. `scripts/tests/test_config.py:197-235` — update `TestParallelAutomationConfig.test_from_dict_with_all_fields` and `test_from_dict_with_defaults` to assert `require_code_changes`
5. Validate: `python -m jsonschema --instance .claude/ll-config.json config-schema.json`

## Acceptance Criteria

- [x] `config-schema.json` includes `automation.idle_timeout_seconds` with type `integer` and default `0`
- [x] `config-schema.json` includes `automation.max_continuations` with type `integer` and default `3`
- [x] `config-schema.json` includes `parallel.require_code_changes` with type `boolean` and default `true`
- [x] Schema validation passes: `python -m jsonschema --instance .claude/ll-config.json config-schema.json`
- [x] All three fields have descriptive `description` strings matching their runtime behavior

## Blocked By

- ~~ENH-650~~: Completed — schema default correction landed; `parallel` section conflict resolved.

## API/Interface

N/A — No public API changes (schema documentation only)

## Integration Map

### Files to Modify
- `config-schema.json` — add three property entries to `automation` (~line 160) and `parallel` (~line 230) sections

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config.py:195,200` — `AutomationConfig` fields (confirmed: `idle_timeout_seconds: int = 0`, `max_continuations: int = 3`); read in `from_dict` at lines 207, 212
- `scripts/little_loops/config.py:233` — `ParallelAutomationConfig.require_code_changes: bool = True`; read in `from_dict` at line 262
- `scripts/little_loops/issue_manager.py:318,367` — Phase 1 `ready-issue` calls pass `idle_timeout` but NOT `max_continuations` (always uses hardcoded default of 3 regardless of config)
- `scripts/little_loops/issue_manager.py:531` — Phase 2 `manage-issue` call correctly passes `config.automation.max_continuations`

### Similar Patterns
- Other `automation` and `parallel` schema properties for `type`/`default`/`description` formatting reference

### Tests
- `scripts/tests/test_config.py:166-181` — `TestAutomationConfig.test_from_dict_with_all_fields`: data dict missing `idle_timeout_seconds`/`max_continuations`; needs entries + assertions
- `scripts/tests/test_config.py:183-191` — `TestAutomationConfig.test_from_dict_with_defaults`: needs `assert config.idle_timeout_seconds == 0` and `assert config.max_continuations == 3`
- `scripts/tests/test_config.py:197-223` — `TestParallelAutomationConfig.test_from_dict_with_all_fields`: missing `require_code_changes` entry and assertion
- `scripts/tests/test_config.py:225-235` — `TestParallelAutomationConfig.test_from_dict_with_defaults`: needs `assert config.require_code_changes is True`

### Documentation
- `config-schema.json` — `description` fields for each new entry

### Configuration
- N/A

## Impact

- **Severity**: LOW — schema incomplete. No functional breakage; discoverability gap only.
- **Files affected**: `config-schema.json`

## Labels

enhancement, config, schema, documentation

## Resolution

Implemented 2026-03-08. Added three missing fields to `config-schema.json`:
- `automation.idle_timeout_seconds` (integer, default 0, minimum 0)
- `automation.max_continuations` (integer, default 3, minimum 1)
- `parallel.require_code_changes` (boolean, default true)

Updated `scripts/tests/test_config.py` to cover both fields in `TestAutomationConfig` and `require_code_changes` in `TestParallelAutomationConfig`. All 94 tests pass; `jsonschema` validation passes.

## Status

completed

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32aac736-5519-48ec-95de-0a16ae0781d8.jsonl`
- `/ll:refine-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2922e0f4-92bb-44ff-a157-9cd86f57c35e.jsonl`
- `/ll:ready-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/815f39b9-3a23-4309-a743-73a1899ec2ef.jsonl`

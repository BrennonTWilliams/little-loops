---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# BUG-649: `default_max_workers` defaults to `4` in schema but `2` in code

## Summary

`config-schema.json` declares `sprints.default_max_workers` default as `4`, but `SprintsConfig` in `config.py` uses `2` as both the dataclass field default and the `from_dict()` fallback. The correct default is `2` — the schema is wrong and needs to be updated.

## Location

- **File**: `config-schema.json`
- **Anchor**: `sprints.default_max_workers` default value

## Steps to Reproduce

1. Check `config-schema.json` — `sprints.default_max_workers` default is `4`
2. Check `scripts/little_loops/config.py` `SprintsConfig` — default is `2`
3. The schema advertises a default that does not match the actual runtime behavior

## Current Behavior

Schema declares default `4`, code uses `2`.

## Expected Behavior

Schema default should be `2`, matching `SprintsConfig` in code.

## Root Cause

- **File**: `config-schema.json`
- **Anchor**: `sprints.default_max_workers`
- **Cause**: Schema default was set incorrectly. The code default of `2` is correct.

## Proposed Solution

Update `config-schema.json` to set `sprints.default_max_workers` default to `2`:

```json
"default_max_workers": {
  "type": "integer",
  "default": 2
}
```

## Implementation Steps

1. Update `config-schema.json`: change `default_max_workers` default from `4` to `2`
2. Verify schema and code are now consistent
3. Run `python -m pytest scripts/tests/`

## Acceptance Criteria

- [ ] `config-schema.json` `sprints.default_max_workers` default is `2`
- [ ] `SprintsConfig().default_max_workers` returns `2` (unchanged)
- [ ] Schema default and code default are consistent at `2`
- [ ] All existing tests pass: `python -m pytest scripts/tests/`

## Integration Map

### Files to Modify
- `config-schema.json` — update `sprints.default_max_workers` default from `4` to `2`

### Dependent Files (Callers/Importers)
- TBD — `grep -r "default_max_workers" scripts/` to find all references

### Similar Patterns
- Other `SprintsConfig` fields follow same dataclass + `from_dict` pattern

### Tests
- `scripts/tests/` — verify tests assert `SprintsConfig().default_max_workers == 2`

### Documentation
- `config-schema.json` — needs correction

### Configuration
- N/A

## Impact

- **Severity**: LOW — Documentation/schema mismatch only. Runtime behavior (2 workers) is correct; schema misleads users reading it.
- **Files affected**: `config-schema.json`

## Labels

bug, config, sprints

## Resolution

- Updated `config-schema.json` `sprints.default_max_workers` default from `4` to `2`
- Schema and code are now consistent at `2`
- All 3421 tests pass

## Status

completed

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32aac736-5519-48ec-95de-0a16ae0781d8.jsonl`
- `/ll:ready-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/772ec29a-9616-4bc7-99c6-c3a84e53e53a.jsonl`

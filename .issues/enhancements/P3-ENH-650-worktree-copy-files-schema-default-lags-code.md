---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# ENH-650: `worktree_copy_files` schema default lags behind code — schema missing `.claude/settings.local.json`

## Summary

`config-schema.json` declares `parallel.worktree_copy_files` default as `[".env"]`. `ParallelAutomationConfig` in `config.py` defaults to `[".claude/settings.local.json", ".env"]`. The code is more correct — `settings.local.json` carries Claude Code auth tokens needed in worktrees — but users reading the schema see an incomplete default and may unknowingly strip it from their configs.

## Motivation

Schema and code must agree on defaults. When they diverge, users configuring from the schema get subtly broken behavior (missing auth in worktrees). Keeping the schema accurate also enables schema validation tools to catch misconfigurations.

## Current Behavior

Schema shows default `[".env"]`; code uses `[".claude/settings.local.json", ".env"]`.

## Expected Behavior

Schema `parallel.worktree_copy_files.default` matches code: `[".claude/settings.local.json", ".env"]`.

## Proposed Solution

Update `config-schema.json` line ~229:

```json
"default": [".claude/settings.local.json", ".env"]
```

## Implementation Steps

1. `config-schema.json:228` — update `"default"` from `[".env"]` to `[".claude/settings.local.json", ".env"]`
2. `config-schema.json:225` — update `description` to explain why `settings.local.json` is included (Claude Code auth tokens); current text: `"Additional files to copy from main repo to worktrees (relative paths). Note: .claude/ directory is always copied automatically."`
3. `scripts/little_loops/parallel/types.py:339` — also update `ParallelConfig.worktree_copy_files` field default from `[".env"]` to `[".claude/settings.local.json", ".env"]` (currently diverged; only reached when constructing `ParallelConfig` directly without `BRConfig`)
4. `scripts/tests/test_parallel_types.py:747` — update assertion from `[".env"]` to `[".claude/settings.local.json", ".env"]` after fixing `types.py:339`
5. Validate: `python -m jsonschema --instance .claude/ll-config.json config-schema.json`

## Acceptance Criteria

- [x] `config-schema.json` `parallel.worktree_copy_files.default` equals `[".claude/settings.local.json", ".env"]`
- [x] Schema validation passes: `python -m jsonschema --instance .claude/ll-config.json config-schema.json`
- [x] Schema `description` for `worktree_copy_files` explains why `.claude/settings.local.json` is included (Claude Code auth tokens)

## API/Interface

N/A — No public API changes (schema documentation only)

## Integration Map

### Files to Modify
- `config-schema.json:228` — update `parallel.worktree_copy_files` default array to `[".claude/settings.local.json", ".env"]`
- `scripts/little_loops/parallel/types.py:339` — update `ParallelConfig.worktree_copy_files` field default to match (also currently `[".env"]`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config.py` — `ParallelAutomationConfig` already has correct default; no changes needed

### Similar Patterns
- Other schema default arrays in `parallel` section for formatting reference

### Tests
- `scripts/tests/test_parallel_types.py:747` — asserts `config.worktree_copy_files == [".env"]`; update to `[".claude/settings.local.json", ".env"]` after fixing `types.py:339`
- No test currently asserts `ParallelAutomationConfig.from_dict({})` → `worktree_copy_files == [".claude/settings.local.json", ".env"]`; add one in `scripts/tests/test_config.py` `TestParallelAutomationConfig.test_from_dict_with_defaults` (lines 225-235)

### Documentation
- `config-schema.json` — add `description` note for `worktree_copy_files` explaining the auth token rationale

### Configuration
- N/A

## Impact

- **Severity**: MEDIUM — schema behind code. Users configuring from schema may omit critical file.
- **Files affected**: `config-schema.json`

## Labels

enhancement, config, schema, parallel

## Resolution

- Updated `config-schema.json` `parallel.worktree_copy_files.default` to `[".claude/settings.local.json", ".env"]` and improved description to explain auth token rationale
- Updated `scripts/little_loops/parallel/types.py` `ParallelConfig.worktree_copy_files` default to match
- Fixed `scripts/tests/test_parallel_types.py:747` assertion to match new default
- Added `worktree_copy_files` default assertion to `scripts/tests/test_config.py` `TestParallelAutomationConfig.test_from_dict_with_defaults`
- Fixed `.claude/ll-config.json`: moved `worktree_copy_files` from top level to `parallel` section (was invalid per schema)
- All 150 tests pass; schema validation passes

## Status

completed

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32aac736-5519-48ec-95de-0a16ae0781d8.jsonl`
- `/ll:refine-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2922e0f4-92bb-44ff-a157-9cd86f57c35e.jsonl`
- `/ll:ready-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac2542cc-0290-4e2e-b1d7-79ccd21482f8.jsonl`

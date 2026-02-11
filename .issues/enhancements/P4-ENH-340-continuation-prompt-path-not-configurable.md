---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-340: Continuation prompt path not configurable

## Summary

`subprocess_utils.py` hardcodes `.claude/ll-continue-prompt.md` as the continuation prompt path with no way to override via config.

## Context

Identified during a config consistency audit. Minor impact since most users won't need to change this path, but it's inconsistent with the pattern used for other paths.

## Affected Files

- `scripts/little_loops/subprocess_utils.py` (line 25): hardcoded `CONTINUATION_PROMPT_PATH`

## Current Behavior

`subprocess_utils.py` hardcodes `.claude/ll-continue-prompt.md` as `CONTINUATION_PROMPT_PATH` at line 25. There is no config key to override this path.

## Expected Behavior

The continuation prompt path should be configurable via `ll-config.json`, with the current path as the default.

## Motivation

This enhancement would:
- Improve consistency: all other major paths are configurable via `ll-config.json`
- Enable custom prompt locations for users with non-standard project layouts

## Proposed Solution

Either parameterize the function to accept the path, or add a config key under `continuation.prompt_path`.

## Scope Boundaries

- **In scope**: Making the continuation prompt path configurable
- **Out of scope**: Changing the prompt content or format

## Implementation Steps

1. Add `continuation.prompt_path` to `config-schema.json`
2. Update `subprocess_utils.py` to read path from config with fallback default
3. Run tests to verify no regressions

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` - Read path from config
- `config-schema.json` - Add `continuation.prompt_path` key

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` - Calls subprocess utils

### Similar Patterns
- `issues.base_dir`, `parallel.worktree_base` config patterns

### Tests
- `scripts/tests/test_subprocess_utils.py` - Test config-based path

### Documentation
- N/A

### Configuration
- `config-schema.json` - New `continuation.prompt_path` key

## Impact

- **Priority**: P4 - Minor inconsistency, low user impact
- **Effort**: Small - Single file change + schema addition
- **Risk**: Low - Default preserves existing behavior
- **Breaking Change**: No

## Labels

`enhancement`, `config`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P4

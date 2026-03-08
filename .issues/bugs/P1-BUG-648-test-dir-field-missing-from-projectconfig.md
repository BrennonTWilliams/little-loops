---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# BUG-648: `test_dir` field missing from `ProjectConfig` — template references silently fail

## Summary

`config-schema.json` defines `project.test_dir` with a default of `"tests"`, but `ProjectConfig` in `config.py` has no `test_dir` field at all. Any command template that uses `{{config.project.test_dir}}` (e.g., `commands/run-tests.md`) silently resolves to an empty string, producing broken test commands without any error.

## Location

- **File**: `scripts/little_loops/config.py`
- **Line(s)**: 75–100 (`ProjectConfig` class and `from_dict()`)
- **Anchor**: `class ProjectConfig`

## Current Behavior

`config.project.test_dir` raises `AttributeError` or silently returns `""` depending on access path. Template `{{config.project.test_dir}}` produces an empty string in generated commands.

## Expected Behavior

`ProjectConfig` exposes `test_dir: str = "tests"`, populated from `data.get("test_dir", "tests")` in `from_dict()`, consistent with the schema default.

## Root Cause

- **File**: `scripts/little_loops/config.py`
- **Anchor**: `class ProjectConfig` / `from_dict()`
- **Cause**: The `test_dir` field was defined in `config-schema.json` but never added to the corresponding Python dataclass.

## Proposed Solution

```python
# In ProjectConfig dataclass:
test_dir: str = "tests"

# In ProjectConfig.from_dict():
test_dir=data.get("test_dir", "tests"),
```

## Implementation Steps

1. Add `test_dir: str = "tests"` field to `ProjectConfig` dataclass in `config.py`
2. Add `test_dir=data.get("test_dir", "tests")` in `ProjectConfig.from_dict()`
3. Verify: `python -c "from little_loops.config import ProjectConfig; print(ProjectConfig().test_dir)"` → prints `tests`
4. Run `python -m pytest scripts/tests/`

## Impact

- **Severity**: HIGH — Broken. Any feature using `config.project.test_dir` in templates silently misfires.
- **Files affected**: `scripts/little_loops/config.py`

## Labels

bug, config, broken

## Status

---
open
---

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`

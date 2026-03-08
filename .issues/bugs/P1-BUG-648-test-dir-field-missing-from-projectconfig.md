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

## Steps to Reproduce

1. Without adding `test_dir` to `ll-config.json`, run any command template that interpolates `{{config.project.test_dir}}` (e.g., `/ll:run-tests`)
2. Observe the command resolves to an empty string — no `tests/` directory appended
3. Or from Python:

```python
from little_loops.config import ProjectConfig
print(ProjectConfig().test_dir)  # AttributeError or ""
```

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

1. `config.py:80` — add `test_dir: str = "tests"` field to `ProjectConfig` dataclass (after `src_dir`, before `test_cmd`)
2. `config.py:93` — add `test_dir=data.get("test_dir", "tests"),` in `ProjectConfig.from_dict()` (after `src_dir=...` line)
3. `config.py:893` — add `"test_dir": self._project.test_dir,` in `BRConfig.to_dict()` under the `"project"` key (after `"src_dir"`) — **required for template resolution to work**
4. `scripts/tests/test_config.py:67-101` — update `TestProjectConfig.test_from_dict_with_all_fields` and `test_from_dict_with_defaults` with assertions
5. Verify: `python -c "from little_loops.config import ProjectConfig; print(ProjectConfig().test_dir)"` → prints `tests`
6. Run `python -m pytest scripts/tests/`

## Acceptance Criteria

- [ ] `ProjectConfig().test_dir` returns `"tests"` (schema default)
- [ ] `ProjectConfig.from_dict({"test_dir": "custom_tests"}).test_dir` returns `"custom_tests"`
- [ ] Template `{{config.project.test_dir}}` in commands resolves to the configured value (not empty string)
- [ ] All existing tests pass: `python -m pytest scripts/tests/`

## Integration Map

### Files to Modify
- `scripts/little_loops/config.py` — add `test_dir: str = "tests"` to `ProjectConfig` dataclass and `test_dir=data.get("test_dir", "tests")` in `from_dict()`

### Dependent Files (Callers/Importers)
- `commands/run-tests.md:23,56,58,70,72,84,86,98,110,120` — 9 usages of `{{config.project.test_dir}}` in bash code blocks (unit, integration, all-tests, coverage scopes)
- `scripts/little_loops/config.py:884-899` — `BRConfig.to_dict()` builds the `"project"` dict that `resolve_variable()` walks; **`test_dir` must also be added here** or template resolution will still fail

### Similar Patterns
- Other `ProjectConfig` fields (`name`, `language`, `test_cmd`) — follow same dataclass + `from_dict` pattern

### Tests
- `scripts/tests/test_config.py:67-88` — `TestProjectConfig.test_from_dict_with_all_fields`: add `"test_dir": "custom_tests"` to data dict and assert `config.test_dir == "custom_tests"`
- `scripts/tests/test_config.py:90-101` — `TestProjectConfig.test_from_dict_with_defaults`: add assertion `assert config.test_dir == "tests"`

### Documentation
- `config-schema.json` — already correct (`project.test_dir` with default `"tests"`)

### Configuration
- N/A

## Impact

- **Severity**: HIGH — Broken. Any feature using `config.project.test_dir` in templates silently misfires.
- **Files affected**: `scripts/little_loops/config.py`

## Labels

bug, config, broken

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32aac736-5519-48ec-95de-0a16ae0781d8.jsonl`
- `/ll:refine-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2922e0f4-92bb-44ff-a157-9cd86f57c35e.jsonl`

---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# ENH-652: Three locations hardcode values that should be read from config

## Summary

Three files bypass the config system and hardcode values that duplicate or contradict config-defined settings, creating drift risk when config values change.

| File | Line | Issue |
|------|------|-------|
| `scripts/little_loops/cli/history.py` | 168 | `Path.cwd() / ".issues"` hardcoded instead of `config.issues.base_dir` |
| `scripts/little_loops/dependency_mapper/operations.py` | 272 | Hardcoded `["bugs", "features", "enhancements", "completed", "deferred"]` fallback |
| `scripts/little_loops/sync.py` | 640 | Hardcoded `category_map = {"BUG": "bugs", ...}` duplicates config |

## Motivation

When `config.issues.base_dir` or category mappings are changed, these three sites won't pick up the change. This has already caused issues when the `.issues` path was customizable — the hardcodes become stale silently.

## Proposed Solution

### `history.py:168`
Pass `BRConfig` into the history CLI and replace:
```python
# Before:
issues_dir = Path.cwd() / ".issues"

# After:
issues_dir = Path(config.issues.base_dir)
```

### `operations.py:272`
Replace hardcoded list with config-driven call when config is available:
```python
# Before:
dirs = ["bugs", "features", "enhancements", "completed", "deferred"]

# After:
dirs = config.issues.get_all_dirs() if config else ["bugs", "features", "enhancements", "completed", "deferred"]
```

### `sync.py:640`
Replace hardcoded dict with config-derived mapping:
```python
# Before:
category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}

# After:
category_map = {cat.prefix: cat.dir for cat in config.issues.categories.values()}
```

## Implementation Steps

1. `history.py`: Audit how `BRConfig` is already threaded through CLI; add `config` parameter to the history path resolution function; replace hardcoded path
2. `operations.py`: Add optional `config` parameter to the relevant function; use `config.issues.get_all_dirs()` when available
3. `sync.py`: Replace `category_map` literal with config-derived dict comprehension
4. Run `python -m pytest scripts/tests/` to confirm no regressions

## Impact

- **Severity**: LOW — drift risk. No current breakage, but any config path change will silently diverge.
- **Files affected**: `scripts/little_loops/cli/history.py`, `scripts/little_loops/dependency_mapper/operations.py`, `scripts/little_loops/sync.py`

## Labels

enhancement, config, refactor, tech-debt

## Status

---
open
---

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`

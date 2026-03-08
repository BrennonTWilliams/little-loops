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

## Current Behavior

Three code locations bypass the config system:
- `cli/history.py:168`: `Path.cwd() / ".issues"` — ignores `config.issues.base_dir`
- `dependency_mapper/operations.py:272`: hardcoded `["bugs", "features", "enhancements", "completed", "deferred"]` — ignores config categories
- `sync.py:640`: hardcoded `category_map = {"BUG": "bugs", ...}` — duplicates config mapping

Config changes to `base_dir` or categories silently diverge in all three locations.

## Expected Behavior

All three locations read from the config system:
- `cli/history.py:168`: uses `Path(config.issues.base_dir)`
- `dependency_mapper/operations.py:272`: uses `config.issues.get_all_dirs()` when config available, with safe fallback
- `sync.py:640`: derives `category_map` from `config.issues.categories`

Config changes propagate automatically to all three sites.

## Proposed Solution

### `history.py:168`
Add config loading to `main_history()` (BRConfig is not currently imported; `add_config_arg` is not called). Follow the pattern from `cli/sync.py:87,97-98`:
```python
# Add to imports:
from little_loops.config import BRConfig
from little_loops.cli_args import add_config_arg

# Add to parser setup:
add_config_arg(parser)

# In main_history(), replace:
issues_dir = args.directory or Path.cwd() / ".issues"
# With:
project_root = args.config or Path.cwd()
config = BRConfig(project_root)
issues_dir = args.directory or Path(config.project_root / config._issues.base_dir)
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
Use `IssuesConfig.get_category_by_prefix()` (already exists at `config.py:143-155`) rather than building a dict:
```python
# Before:
category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
category = category_map.get(issue_type, "features")

# After:
cat = self.config.issues.get_category_by_prefix(issue_type)
category = cat.dir if cat else "features"
```

## Implementation Steps

1. `history.py`: Audit how `BRConfig` is already threaded through CLI; add `config` parameter to the history path resolution function; replace hardcoded path
2. `operations.py`: Add optional `config` parameter to the relevant function; use `config.issues.get_all_dirs()` when available
3. `sync.py`: Replace `category_map` literal with config-derived dict comprehension
4. Run `python -m pytest scripts/tests/` to confirm no regressions

## Acceptance Criteria

- [ ] `history.py` resolves issues path from `config.issues.base_dir` (not hardcoded `".issues"`)
- [ ] `operations.py` uses `config.issues.get_all_dirs()` when config available; falls back safely when not
- [ ] `sync.py` derives `category_map` from config categories (no literal dict)
- [ ] All existing tests pass: `python -m pytest scripts/tests/`
- [ ] No regression when `base_dir` is set to a non-default value

## API/Interface

N/A — Internal refactor; no public API changes

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` (line 168) — replace `Path.cwd() / ".issues"` with `Path(config.issues.base_dir)`
- `scripts/little_loops/dependency_mapper/operations.py` (line 272) — replace hardcoded list with `config.issues.get_all_dirs()` call
- `scripts/little_loops/sync.py` (line 640) — replace `category_map` literal with `{cat.prefix: cat.dir for cat in config.issues.categories.values()}`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config.py:179-185` — `IssuesConfig.get_all_dirs()` exists and returns `[cat.dir for cat in self.categories.values()]`
- `scripts/little_loops/config.py:143-155` — `IssuesConfig.get_category_by_prefix(prefix)` — correct interface for `sync.py`: given `"BUG"`, returns `CategoryConfig` whose `.dir` is the configured dir name
- `scripts/little_loops/config.py:875-877` — `BRConfig.issue_categories` property returns `list[str]` of category keys
- `scripts/little_loops/cli_args.py:34-41` — `add_config_arg(parser)` is the standard pattern for adding `--config` to CLI parsers (used by `sync.py`, `auto.py`, `parallel.py` — but NOT `history.py`)
- `scripts/little_loops/cli/history.py` — `BRConfig` is **never imported** in this file; `main_history()` has no `--config` argument; `add_config_arg` is not called; requires threading `BRConfig` loading at the top of `main_history()` before the path can be read from config
- `scripts/little_loops/dependency_mapper/operations.py:250-283` — `gather_all_issue_ids(issues_dir, config=None)` already has `if config is not None` branch using `config.issue_categories` and `config.get_completed_dir().name`; hardcoded list is only the fallback when `config=None`
- `scripts/little_loops/cli/deps.py:208` — already passes `config=_dm_config` to `gather_all_issue_ids`; the only callers missing config are test-only

### Similar Patterns
- `scripts/little_loops/cli/sync.py:87,97-98` — canonical pattern: `add_config_arg(parser)` → `project_root = args.config or Path.cwd()` → `config = BRConfig(project_root)` → pass into class constructor
- `scripts/little_loops/cli/auto.py:53-54` — same pattern via `add_common_auto_args(parser)`

### Tests
- `scripts/tests/test_issue_history_cli.py` — all tests pass `"-d", str(tmp_path / ".issues")` explicitly; none exercise the hardcoded fallback; add a test that omits `-d` and verifies config-driven path resolution
- `scripts/tests/test_dependency_mapper.py:538-564` — exercises hardcoded fallback (no config); tests at lines 566-625 exercise config-driven path; no changes needed unless fallback list is removed
- `scripts/tests/test_sync.py:611-710` — `test_create_local_issue_*` tests; none use a custom `categories` config; add test asserting correct `category_dir` resolution when `BUG` prefix maps to a non-default dir

### Documentation
- N/A

### Configuration
- `config.issues.base_dir` — the field being propagated to `history.py`
- `config.issues.categories` — the mapping used by `sync.py`

## Impact

- **Severity**: LOW — drift risk. No current breakage, but any config path change will silently diverge.
- **Files affected**: `scripts/little_loops/cli/history.py`, `scripts/little_loops/dependency_mapper/operations.py`, `scripts/little_loops/sync.py`

## Labels

enhancement, config, refactor, tech-debt

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32aac736-5519-48ec-95de-0a16ae0781d8.jsonl`
- `/ll:refine-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2922e0f4-92bb-44ff-a157-9cd86f57c35e.jsonl`

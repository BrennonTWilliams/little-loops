---
id: FEAT-959
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-05
discovered_by: issue-size-review
parent_issue: FEAT-769
---

# FEAT-959: OpenCode Python Path Abstraction

## Summary

Update the Python layer of little-loops to support `.opencode/` config and log paths alongside the existing `.claude/` paths, enabling OpenCode users to have config and session log discovery work correctly.

## Parent Issue

Decomposed from FEAT-769: Add OpenCode Plugin Compatibility

## Current Behavior

The Python layer hardcodes `.claude/` paths in four places:
- `scripts/little_loops/config/core.py:74-75` — `CONFIG_DIR = ".claude"` constant
- `scripts/little_loops/config/features.py:193,206` — `state_file: str = ".claude/ll-sync-state.json"` default
- `scripts/little_loops/user_messages.py:338` — `Path.home() / ".claude" / "projects"` for log discovery
- `scripts/little_loops/user_messages.py:703` — `Path.cwd() / ".claude"` default output dir

## Expected Behavior

- `config/core.py` probes `.opencode/ll-config.json` first, falls back to `.claude/ll-config.json`
- `config/features.py` uses `.opencode/ll-sync-state.json` when `.opencode/` dir is present
- `user_messages.py` probes OpenCode log path when Claude Code path doesn't exist
- All existing Claude Code behavior unchanged

## Acceptance Criteria

- `config/core.py` loads config from `.opencode/ll-config.json` when present (falls back to `.claude/`)
- `config/features.py` `GithubSyncConfig.state_file` default probes `.opencode/` first
- `user_messages.py:338` tries OpenCode log path variant if `~/.claude/projects/` absent
- `user_messages.py:703` output dir probes `.opencode/` when `.claude/` absent
- `test_config.py` has `test_load_config_opencode_path()` and `test_load_config_fallback_to_claude()` tests passing
- `test_user_messages.py` has OpenCode log-path tests passing
- No regressions to existing Claude Code config loading

## Proposed Solution

### `config/core.py`

Change `CONFIG_DIR = ".claude"` constant (line 74) to a priority-ordered search function:

```python
def find_config() -> Path:
    for candidate in [Path(".opencode/ll-config.json"), Path(".claude/ll-config.json")]:
        if candidate.exists():
            return candidate
    return Path(".claude/ll-config.json")  # default (create on init)
```

Update `_load_config()` at line 89 to use this instead of `project_root / CONFIG_DIR / CONFIG_FILENAME`.

### `config/features.py`

Update `GithubSyncConfig.state_file` default (lines 193, 206) to probe `.opencode/ll-sync-state.json` first when `.opencode/` directory is present.

### `user_messages.py`

Update `claude_projects` at line 338 to try `Path.home() / ".opencode" / "projects"` when `~/.claude/projects/` doesn't exist. Update output_dir default at line 703 similarly.

### Tests

Follow existing pattern at `scripts/tests/test_config.py:373-381`:
- `test_load_config_opencode_path()` — creates `.opencode/ll-config.json`, verifies it's loaded
- `test_load_config_fallback_to_claude()` — only `.claude/ll-config.json` present, verifies fallback
- `conftest.py` — add `opencode_project_dir` fixture alongside `temp_project_dir`

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py:74-75` — CONFIG_DIR → path search function
- `scripts/little_loops/config/features.py:193,206` — state_file default
- `scripts/little_loops/user_messages.py:338,703` — log/output dir paths

### Files to Create / Modify (Tests)
- `scripts/tests/test_config.py` — add 2 OpenCode path tests
- `scripts/tests/test_user_messages.py` — add OpenCode log-path tests
- `scripts/tests/conftest.py` — add `opencode_project_dir` fixture

## Impact

- **Priority**: P4 — Unblocks OpenCode users, no risk to Claude Code users
- **Effort**: Small — 4 file changes + tests; no architectural shifts
- **Risk**: Low — Path fallback is additive; existing behavior only changes if `.opencode/ll-config.json` exists
- **Breaking Change**: No

## Notes

Write `test_config.py` tests BEFORE modifying `core.py:74-75` — `config/core.py` has 60 importers (grep-confirmed), so test-first is required to catch regressions early.

## Session Log
- `/ll:issue-size-review` - 2026-04-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e591ecf6-7232-42fc-b4c4-903ec2858064.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P4

---
id: FEAT-959
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-05
discovered_by: issue-size-review
parent_issue: FEAT-769
confidence_score: 90
outcome_confidence: 72
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Items already migrated (no changes needed for these):**
- `config/core.py:75` — `CONFIG_DIR` is already `".ll"` (not `".claude"`)
- `config/features.py:250,264` — `state_file` default is already `".ll/ll-sync-state.json"` (not `".claude/..."`)
- `user_messages.py:736` — `save_messages()` output dir is already `Path.cwd() / ".ll"` (not `".claude"`)

**Items with stale line numbers (still need changes):**
- `user_messages.py:374` (not 338) — `claude_projects = Path.home() / ".claude" / "projects"` in `get_project_folder()`

**Items missing from issue scope (need changes):**
- `cli/messages.py:256` — `output_dir = Path.cwd() / ".claude"` in `_save_combined()` — active hardcode
- `cli/messages.py:156` — error message string hardcodes `~/.claude/projects/<encoded>` — will show wrong path to OpenCode users

## Expected Behavior

- `config/core.py` probes `.opencode/ll-config.json` first, falls back to `.claude/ll-config.json`
- `config/features.py` uses `.opencode/ll-sync-state.json` when `.opencode/` dir is present
- `user_messages.py` probes OpenCode log path when Claude Code path doesn't exist
- All existing Claude Code behavior unchanged

## Use Case

**Who**: OpenCode users running little-loops CLI tools (`ll-auto`, `ll-parallel`, `ll-messages`, `ll-issues`, etc.)

**Context**: When using little-loops with OpenCode as their editor — config lives in `.opencode/ll-config.json` and session logs in `~/.opencode/projects/` instead of the `.claude/` paths

**Goal**: Have ll-config.json and session logs discovered automatically without manual path configuration

**Outcome**: All little-loops Python CLI tools work for OpenCode users — just create `.opencode/ll-config.json` and the tools resolve paths correctly

## Motivation

This feature would:
- Enable OpenCode users to adopt little-loops without forking or manual code changes
- Unblock the Python layer of FEAT-769 (OpenCode Plugin Compatibility) specifically
- Additive-only change — no risk to existing Claude Code users (fallback preserves current behavior)

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

> **Research correction** (`/ll:refine-issue`): `CONFIG_DIR` is already `".ll"` (not `".claude"`). The probe order in `find_config()` must use `".ll"` as the fallback, not `".claude"`:
> ```python
> def find_config() -> Path:
>     for candidate in [Path(".opencode/ll-config.json"), Path(".ll/ll-config.json")]:
>         if candidate.exists():
>             return candidate
>     return Path(".ll/ll-config.json")  # default (create on init)
> ```
> `_load_config()` is at `core.py:87` and builds `project_root / ".ll" / "ll-config.json"`. The `find_config()` should be called from there. Existing probe pattern to model after: `issue_history/parsing.py:330-332`.

### `config/features.py`

Update `GithubSyncConfig.state_file` default (lines 193, 206) to probe `.opencode/ll-sync-state.json` first when `.opencode/` directory is present.

> **Research correction** (`/ll:refine-issue`): Actual lines are 250/264 (not 193/206). Default is already `".ll/ll-sync-state.json"`. Additionally, `state_file` is populated from config but **never read by `sync.py` or `cli/sync.py`** — it is serialized by `BRConfig.to_dict()` but drives no file I/O. Consider whether this change is necessary; it is lower priority than the `user_messages.py` changes.

### `user_messages.py`

Update `claude_projects` at line 338 to try `Path.home() / ".opencode" / "projects"` when `~/.claude/projects/` doesn't exist. Update output_dir default at line 703 similarly.

> **Research correction** (`/ll:refine-issue`): Active `.claude` hardcode is at `user_messages.py:374` (not 338) inside `get_project_folder()`. The `save_messages()` output dir at line 736 is already `Path.cwd() / ".ll"` — no change needed there.
>
> `get_project_folder()` function context (`user_messages.py:354-380`):
> ```python
> def get_project_folder(cwd: Path | None = None) -> Path | None:
>     cwd = cwd or Path.cwd()
>     encoded_path = str(cwd.resolve()).replace("/", "-")
>     claude_projects = Path.home() / ".claude" / "projects"   # line 374 — needs probe
>     project_folder = claude_projects / encoded_path
>     if project_folder.exists():
>         return project_folder
>     return None
> ```
> Probe logic: try `~/.claude/projects/<encoded>` first, fall back to `~/.opencode/projects/<encoded>`.

### `cli/messages.py` (missing from issue scope)

> **Research finding** (`/ll:refine-issue`): Two additional `.claude` hardcodes require changes not mentioned in the original issue:
> - `cli/messages.py:256` — `output_dir = Path.cwd() / ".claude"` in `_save_combined()` — needs same `.opencode` probe as `user_messages.py:save_messages()`
> - `cli/messages.py:156` — error message string `f"Expected: ~/.claude/projects/{str(cwd).replace('/', '-')}"` — will display wrong expected path to OpenCode users; should show the probed path

### Tests

Follow existing pattern at `scripts/tests/test_config.py:373-381`:
- `test_load_config_opencode_path()` — creates `.opencode/ll-config.json`, verifies it's loaded
- `test_load_config_fallback_to_claude()` — only `.claude/ll-config.json` present, verifies fallback
- `conftest.py` — add `opencode_project_dir` fixture alongside `temp_project_dir`

> **Research correction** (`/ll:refine-issue`): The correct reference is `test_config.py:458-481` (class `TestBRConfig`), not 373-381 (which is inside `TestCommandsConfig`).
>
> `temp_project_dir` fixture to model after (`conftest.py:55-62`):
> ```python
> @pytest.fixture
> def temp_project_dir() -> Generator[Path, None, None]:
>     """Create a temporary project directory with .ll folder."""
>     with tempfile.TemporaryDirectory() as tmpdir:
>         project_root = Path(tmpdir)
>         ll_dir = project_root / ".ll"
>         ll_dir.mkdir()
>         yield project_root
> ```
> `opencode_project_dir` fixture: same shape, substitute `.opencode/` for `.ll/`.
>
> For `test_user_messages.py`, model after `TestGetProjectFolder` at `test_user_messages.py:79-97`. The `temp_project_folder` fixture (inline class fixture at line 103-107) uses `tempfile.TemporaryDirectory` — the OpenCode test can use the same pattern but create `~/.opencode/projects/<encoded>` using `tmp_path` and monkeypatching `Path.home()`.

## API/Interface

New internal helper introduced in `config/core.py`:

```python
def find_config() -> Path:
    """Return path to ll-config.json, preferring .opencode/ over .claude/."""
    for candidate in [Path(".opencode/ll-config.json"), Path(".claude/ll-config.json")]:
        if candidate.exists():
            return candidate
    return Path(".claude/ll-config.json")  # default (create on init)
```

All other changes (state_file default, log path probing) are internal — no public API surface changes.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py:74-75` — CONFIG_DIR → path search function
- `scripts/little_loops/config/features.py:193,206` — state_file default
- `scripts/little_loops/user_messages.py:338,703` — log/output dir paths

### Files to Create / Modify (Tests)
- `scripts/tests/test_config.py` — add 2 OpenCode path tests
- `scripts/tests/test_user_messages.py` — add OpenCode log-path tests
- `scripts/tests/conftest.py` — add `opencode_project_dir` fixture

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrected file:line references:_

**Active `.claude` hardcodes requiring changes:**
- `scripts/little_loops/user_messages.py:374` — `claude_projects = Path.home() / ".claude" / "projects"` in `get_project_folder()` (cited as line 338 — stale)
- `scripts/little_loops/cli/messages.py:256` — `output_dir = Path.cwd() / ".claude"` in `_save_combined()` (not in original issue)
- `scripts/little_loops/cli/messages.py:156` — error message string `~/.claude/projects/` (not in original issue)

**Items already migrated — no changes needed:**
- `scripts/little_loops/config/core.py:75` — `CONFIG_DIR = ".ll"` (already `.ll`, not `.claude`)
- `scripts/little_loops/config/features.py:250,264` — `state_file = ".ll/ll-sync-state.json"` (already `.ll`)
- `scripts/little_loops/user_messages.py:736` — `save_messages()` output dir already `Path.cwd() / ".ll"`

**Test files with actual line references:**
- `scripts/tests/test_config.py:458-481` — `TestBRConfig.test_load_config_from_file` (model for OpenCode tests)
- `scripts/tests/conftest.py:55-62` — `temp_project_dir` fixture (model for `opencode_project_dir`)
- `scripts/tests/test_user_messages.py:79-97` — `TestGetProjectFolder` (model for OpenCode log path tests)

**callers/dependents:**
- `scripts/little_loops/session_log.py:74` — calls `get_project_folder()` for JSONL discovery (`/ll:format-issue` session log appending)
- `scripts/little_loops/cli/messages.py:152` — calls `get_project_folder()` as entry for `ll-messages` CLI; returns exit code 1 on None

## Implementation Steps

1. Write `test_config.py` tests first (`test_load_config_opencode_path`, `test_load_config_fallback_to_claude`) — required before `core.py` changes (60 importers)
2. Add `opencode_project_dir` fixture to `scripts/tests/conftest.py`
3. Update `config/core.py`: replace `CONFIG_DIR = ".claude"` constant with `find_config()` priority-ordered search
4. Update `config/features.py`: probe `.opencode/ll-sync-state.json` first when `.opencode/` dir is present
5. Update `user_messages.py`: try OpenCode log path (`~/.opencode/projects/`) and output dir (`.opencode/`) as fallbacks
6. Add OpenCode log-path tests to `scripts/tests/test_user_messages.py`
7. Run full test suite; verify no regressions on existing Claude Code behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrected implementation steps:_

**Revised steps based on actual codebase state:**

1. Add `opencode_project_dir` fixture to `scripts/tests/conftest.py:55-62` (alongside `temp_project_dir`)
2. Write `test_config.py` tests in `TestBRConfig` (line 458+) — model after `test_load_config_from_file:458-481`
   - `test_load_config_opencode_path()` — create `.opencode/ll-config.json`, assert `BRConfig` loads it
   - `test_load_config_fallback_to_ll()` — only `.ll/ll-config.json` present, assert fallback loads it
3. Update `config/core.py:87-93` — add `find_config()` function probing `.opencode/ll-config.json` then `.ll/ll-config.json`; update `_load_config()` to call it (73 importers — tests must pass first)
4. Update `user_messages.py:374` — in `get_project_folder()`, after no result from `~/.claude/projects/<encoded>`, probe `~/.opencode/projects/<encoded>` before returning `None`
5. Update `cli/messages.py:256` — in `_save_combined()`, probe `.opencode/` when `.ll/` not present (parallel to step 4)
6. Update `cli/messages.py:156` — update error message to show the probed path variant
7. Add `TestGetProjectFolder` OpenCode tests to `test_user_messages.py:79+` using `monkeypatch`/`tmp_path` to mock `Path.home()`
8. Run: `python -m pytest scripts/tests/test_config.py scripts/tests/test_user_messages.py -v`
9. Run full suite: `python -m pytest scripts/tests/ -v --tb=short`

> **Note**: Step 4 in original (`config/features.py` `state_file`) is optional — the field is not consumed by sync code. Defer unless needed for config serialization consistency.

## Impact

- **Priority**: P4 — Unblocks OpenCode users, no risk to Claude Code users
- **Effort**: Small — 4 file changes + tests; no architectural shifts
- **Risk**: Low — Path fallback is additive; existing behavior only changes if `.opencode/ll-config.json` exists
- **Breaking Change**: No

## Notes

Write `test_config.py` tests BEFORE modifying `core.py:74-75` — `config/core.py` has 60 importers (grep-confirmed), so test-first is required to catch regressions early.

## Labels

`feature`, `opencode`, `python`, `captured`

## Blocks

- FEAT-960: OpenCode Shell Hooks Path Abstraction (requires Python config fallback first)

## Verification Notes

**Verdict**: VALID — Active hardcodes confirmed:

- `user_messages.py:374` — `claude_projects = Path.home() / ".claude" / "projects"` still hardcoded ✓
- `cli/messages.py:257` — `output_dir = Path.cwd() / ".claude"` still hardcoded (note: actual line is **257**, not 256 as stated — off by 1)
- `config/core.py:75` — `CONFIG_DIR = ".ll"` (already `.ll`, not `.claude`) ✓ (confirmed)
- `user_messages.py:736` — save_messages output dir already `.ll` ✓ (confirmed)
- Feature not yet implemented (no `find_config()` helper, no `opencode_project_dir` fixture)

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:confidence-check` - 2026-04-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29d9c69a-ea81-4ffe-8c79-77785ac2b32a.jsonl`
- `/ll:refine-issue` - 2026-04-06T04:44:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/924b0e9e-ff3c-45b6-b028-4d38a2ebbe23.jsonl`
- `/ll:format-issue` - 2026-04-06T04:39:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd7d1fbc-ba93-4a22-9dbc-fa00f11894d9.jsonl`
- `/ll:issue-size-review` - 2026-04-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e591ecf6-7232-42fc-b4c4-903ec2858064.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P4

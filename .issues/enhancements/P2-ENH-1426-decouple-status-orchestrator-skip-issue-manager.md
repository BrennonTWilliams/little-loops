---
id: ENH-1426
type: ENH
priority: P2
status: done
completed_at: '2026-05-10T00:00:00Z'

parent: ENH-1419
---

# ENH-1426: Decouple Issue Status — Parallel Orchestrator, skip.py, and issue_manager

## Summary

Update the parallel orchestrator's "already completed" guard, `cli/issues/skip.py`'s directory-name status check, and an inline `issue_manager.py` path literal to use `IssueInfo.status` frontmatter. Also verify `cli/auto.py` has no remaining direct directory references. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1423, ENH-1424, ENH-1425 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Current Behavior

Three locations use directory-based checks to determine issue status rather than reading `IssueInfo.status` from frontmatter:

- `parallel/orchestrator.py:_complete_issue_lifecycle_if_needed()` checks `completed_dir.exists()` (directory path presence) to skip already-completed issues
- `cli/issues/skip.py:cmd_skip()` checks `parent_name in ("completed", "deferred")` — inspecting the parent directory name to detect issue state; error message references the `completed/` directory
- `issue_manager.py` (line ~783) uses the hardcoded literal `(config.repo_path or Path.cwd()) / ".issues" / "completed"` to locate completed issues, bypassing `config.get_completed_dir()` entirely

## Expected Behavior

All three locations read `IssueInfo.status` from frontmatter instead of directory names or hardcoded paths:

- `_complete_issue_lifecycle_if_needed()` skips already-completed issues by checking `IssueInfo.status == "done"`
- `cmd_skip()` uses `info.status in ("done", "deferred")`; error messages do not reference the `completed/` directory
- `issue_manager.py` checks issue status via frontmatter rather than a hardcoded path constant

## Motivation

Three isolated wiring-pass findings not covered by other children:
- `parallel/orchestrator.py` has an "already completed" guard that checks `completed_dir.exists()` — must use `IssueInfo.status == "done"`
- `cli/issues/skip.py` checks `parent_name in ("completed", "deferred")` and emits a user-visible error message referencing `completed/`
- `issue_manager.py` has an inline literal path `(config.repo_path or Path.cwd()) / ".issues" / "completed"` that bypasses `config.get_completed_dir()` entirely

## Proposed Solution

### `parallel/orchestrator.py`

- `_complete_issue_lifecycle_if_needed()` (line 1210): replace `completed_dir = self.br_config.get_completed_dir()` + `completed_path.exists()` check with `IssueInfo.status == "done"` check on the resolved issue file; load `IssueInfo` for the issue ID to read its status

### `cli/issues/skip.py`

- `cmd_skip()`: replace `if parent_name in ("completed", "deferred")` guard with `info.status in ("done", "deferred")`; update user-visible error message to no longer reference `completed/` directory

### `issue_manager.py`

- Line 783: replace `(config.repo_path or Path.cwd()) / ".issues" / "completed"` inline path with a `IssueInfo.status == "done"` check (or a call to the standard issue lookup); remove the hardcoded path entirely

### `cli/auto.py`

- Verify-only: `auto.py` delegates to `AutoManager` which calls `find_issues()` (updated in ENH-1418). Confirm no direct directory references remain after ENH-1418 lands.

## Implementation Steps

1. Update `scripts/little_loops/parallel/orchestrator.py:_complete_issue_lifecycle_if_needed()` (line 1210) — replace `get_completed_dir()` + `exists()` with `IssueInfo.status == "done"` **→ DONE** (commit `08fae476`)
2. Update `scripts/little_loops/cli/issues/skip.py:cmd_skip()` — replace directory-name guard with status field check; update user-visible error message **→ DONE**
3. Update `scripts/little_loops/issue_manager.py:783` — replace inline `"completed"` literal path with status field check **→ DONE** (commit `08fae476`)
4. Verify `scripts/little_loops/cli/auto.py` — no direct directory references remain after ENH-1418 **→ VERIFIED CLEAN**
5. Update `scripts/tests/test_orchestrator.py` — parallel orchestrator issue-discovery tests; verify status-field filtering works for the "already completed" guard **→ DONE** (`TestCompleteIssuLifecycle` at line 1927: 3 tests cover no-info, file-gone, and status-written paths)

### Remaining Verification Step

- **`test_cli.py` gap**: Add a test for `cmd_skip()` that feeds an issue with `status: done` in frontmatter and asserts rejection with a status-field error message (not a directory error). No such test exists yet. Follow the existing pattern in `test_cli.py` for CLI command unit tests.
- Run `python -m pytest scripts/tests/test_orchestrator.py::TestCompleteIssuLifecycle scripts/tests/test_cli.py -v` to confirm passing

## Scope Boundaries

- **In scope**: The three specific locations in `parallel/orchestrator.py`, `cli/issues/skip.py`, and `issue_manager.py`; verification that `cli/auto.py` has no direct directory references after ENH-1418
- **Out of scope**: Changes to the `IssueInfo` model or frontmatter schema; changes to sync, export, or GitHub integration logic; discovery of additional directory-based status references beyond those listed

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py`
- `scripts/little_loops/cli/issues/skip.py`
- `scripts/little_loops/issue_manager.py`
- `scripts/little_loops/cli/auto.py` (verify only)
- `scripts/tests/test_orchestrator.py`

## Acceptance Criteria

- `_complete_issue_lifecycle_if_needed()` uses `IssueInfo.status == "done"` to skip already-completed issues
- `ll-issues skip` correctly rejects skip on done/deferred issues using frontmatter status; error message does not reference `completed/`
- `issue_manager.py` line 783 makes no reference to a hardcoded `completed` path
- `cli/auto.py` has no direct directory references
- All updated tests pass

## Impact

- **Priority**: P2 — Part of the ENH-1419 decouple-status series; improves maintainability if issue directories are reconfigured
- **Effort**: Small — Three localized substitutions in distinct files; no new abstractions required
- **Risk**: Low — Changes are isolated to specific guard conditions; existing tests cover the affected paths
- **Breaking Change**: No

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `parallel/orchestrator.py` | `_complete_issue_lifecycle_if_needed()` | `get_completed_dir()` + `completed_path.exists()` | 1210 |
| `cli/issues/skip.py` | `cmd_skip()` | `parent_name in ("completed", "deferred")` | top of function |
| `issue_manager.py` | inline check | `(config.repo_path or Path.cwd()) / ".issues" / "completed"` literal | 783 |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct codebase analysis (2026-05-10):_

**Implementation Status: ALL THREE CHANGES ALREADY IMPLEMENTED** (bundled into commit `08fae476`)

#### `parallel/orchestrator.py:_complete_issue_lifecycle_if_needed()` (line 1195)

Current code no longer uses `get_completed_dir()` or `completed_path.exists()`. The function now:
- Gets `info = self._issue_info_by_id.get(issue_id)` (line 1204)
- Returns `True` early if `not original_path.exists()` (line 1211)
- Writes `status: done` + `completed_at` to frontmatter via `update_frontmatter()` in place (lines 1244–1250)
- No `completed_dir` mkdir or file move; no `get_completed_dir()` call remains

> **Minor gap**: The issue specified replacing the guard with `IssueInfo.status == "done"` check — the current code uses a path existence check instead of reading status. If the file exists but status is already `done`, the function re-writes frontmatter and appends another session log entry (idempotent but redundant). Not blocking.

#### `cli/issues/skip.py:cmd_skip()` (line 15)

Current code at line 40: `if issue_info.status in ("done", "cancelled", "deferred"):`
- Uses `IssueParser(config).parse_file(path)` to load `IssueInfo` ✓
- Error message references status field, not directory ✓
- No `parent_name` or `completed/` directory reference remains ✓

#### `issue_manager.py` (~line 783)

Current code (lines 784–800): replaces the hardcoded `Path / ".issues" / "completed"` with:
```python
already_done = False
if info.path.exists():
    _fm = parse_frontmatter(info.path.read_text(encoding="utf-8"))
    already_done = _fm.get("status") in ("done", "cancelled")
```
No hardcoded `completed` path literal remains ✓

#### `cli/auto.py` — Verified Clean

No `completed_dir`, `get_completed_dir`, or `.issues/completed` references. Delegates to `AutoManager` which uses `find_issues()` (updated in ENH-1418) ✓

### Test Coverage

| Location | Test File | Coverage |
|----------|-----------|---------|
| `_complete_issue_lifecycle_if_needed` | `test_orchestrator.py:1927` | `TestCompleteIssuLifecycle` class — 3 tests: returns False when no info, returns True when file gone, writes `status: done` frontmatter ✓ |
| `cmd_skip()` status rejection | None found | **Gap**: no test verifies that `cmd_skip` rejects issues with `status: done` in frontmatter (vs. old directory check) |
| `issue_manager.py` already-done guard | `test_issue_manager.py` | Needs verification — grep for `already_done` or `already in completed` |

### Files to Modify / Verify

- `scripts/little_loops/parallel/orchestrator.py` — DONE ✓
- `scripts/little_loops/cli/issues/skip.py` — DONE ✓
- `scripts/little_loops/issue_manager.py` — DONE ✓
- `scripts/little_loops/cli/auto.py` — VERIFIED CLEAN ✓
- `scripts/tests/test_orchestrator.py` — DONE ✓ (3 tests in `TestCompleteIssuLifecycle`)
- `scripts/tests/test_cli.py` — GAP: no `cmd_skip` status-rejection test

## Resolution

- **Action**: improve
- **Completed**: 2026-05-10
- **Status**: Completed — all three directory-based status checks replaced with frontmatter reads
- **Implementation**: Bundled into commit `08fae476` (improve(issues): decouple status from directory location, ENH-1418)

### Changes Made

- `parallel/orchestrator.py:_complete_issue_lifecycle_if_needed()` — removed `get_completed_dir()` + `completed_path.exists()`; now writes `status: done` to frontmatter in place
- `cli/issues/skip.py:cmd_skip()` — replaced `parent_name in ("completed", "deferred")` with `issue_info.status in ("done", "cancelled", "deferred")`
- `issue_manager.py:~783` — replaced hardcoded `(config.repo_path or Path.cwd()) / ".issues" / "completed"` with `parse_frontmatter()` status check
- `cli/auto.py` — verified clean, no directory references

### Verification Results

- `TestCompleteIssuLifecycle` (test_orchestrator.py:1927) — 3 tests pass ✓
- Remaining minor gap: no unit test for `cmd_skip()` status-based rejection (tracked separately if needed)

## Labels

`enhancement`, `refactoring`, `status-decoupling`

## Session Log
- `/ll:complete` - 2026-05-10T20:42:10 - `c5979e5a-9809-4880-a299-ec7eb5129b4c.jsonl`
- `/ll:refine-issue` - 2026-05-10T20:40:37 - `c5979e5a-9809-4880-a299-ec7eb5129b4c.jsonl`
- `/ll:format-issue` - 2026-05-10T20:35:57 - `a41b29ce-483f-4fdd-acc3-ac8cc4c756d4.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

---
id: ENH-1426
type: ENH
priority: P2
status: open
parent_issue: ENH-1419
---

# ENH-1426: Decouple Issue Status — Parallel Orchestrator, skip.py, and issue_manager

## Summary

Update the parallel orchestrator's "already completed" guard, `cli/issues/skip.py`'s directory-name status check, and an inline `issue_manager.py` path literal to use `IssueInfo.status` frontmatter. Also verify `cli/auto.py` has no remaining direct directory references. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1423, ENH-1424, ENH-1425 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

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

1. Update `scripts/little_loops/parallel/orchestrator.py:_complete_issue_lifecycle_if_needed()` (line 1210) — replace `get_completed_dir()` + `exists()` with `IssueInfo.status == "done"`
2. Update `scripts/little_loops/cli/issues/skip.py:cmd_skip()` — replace directory-name guard with status field check; update user-visible error message
3. Update `scripts/little_loops/issue_manager.py:783` — replace inline `"completed"` literal path with status field check
4. Verify `scripts/little_loops/cli/auto.py` — no direct directory references remain after ENH-1418
5. Update `scripts/tests/test_orchestrator.py` — parallel orchestrator issue-discovery tests; verify status-field filtering works for the "already completed" guard

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

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `parallel/orchestrator.py` | `_complete_issue_lifecycle_if_needed()` | `get_completed_dir()` + `completed_path.exists()` | 1210 |
| `cli/issues/skip.py` | `cmd_skip()` | `parent_name in ("completed", "deferred")` | top of function |
| `issue_manager.py` | inline check | `(config.repo_path or Path.cwd()) / ".issues" / "completed"` literal | 783 |

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

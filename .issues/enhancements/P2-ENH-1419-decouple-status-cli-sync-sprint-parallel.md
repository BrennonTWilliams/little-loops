---
id: ENH-1419
type: ENH
priority: P2
status: open
parent_issue: ENH-1390
---

# ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Summary

Update the `ll-issues` CLI commands, `ll-sync`, sprint runner, parallel orchestrator discovery, and dependency tools to use `status:` frontmatter instead of directory location. Depends on ENH-1417 (IssueInfo.status). Can run in parallel with ENH-1418 and ENH-1421 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Motivation

This enhancement propagates the `status:` frontmatter model (established in ENH-1417) across all user-facing CLI tools, sync, sprint runner, parallel orchestrator, and dependency tools:
- Removes directory-as-status coupling from `ll-issues list/show/count`, `ll-sync`, sprint runner, and `ll-deps`
- Enables issues in any status to live in type-scoped directories (`bugs/`, `features/`, etc.) rather than status-named dirs
- Unblocks ENH-1418 and ENH-1421 from running concurrently once ENH-1417 lands

## Proposed Solution

### Step 3 — `ll-issues list` and display

- `scripts/little_loops/cli/issues/search.py:_load_issues_with_status()`: read `status:` from `IssueInfo.status` instead of mapping directory name; update `cmd_search()` status string values from `"active"/"completed"/"deferred"` to the full vocab (`open|in_progress|blocked|deferred|done|cancelled|all`)
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields()`: read `info.status` instead of checking `path.parent.name` (`"completed"` → `"Completed"`, etc.); update `_resolve_issue_id()` to search type dirs only (no separate `completed/` + `deferred/` pass)
- `scripts/little_loops/cli/issues/count_cmd.py`: update `--status active|completed|deferred` choices to align with new enum

### Step 6 — `ll-sync` status field mapping

- `scripts/little_loops/sync.py:GitHubSyncManager._get_local_issues()`: scan all type dirs; use `IssueInfo.status` to map to GitHub open/closed
- Update `close_issues()` and `reopen_issues()` to read `status:` field rather than directory
- `close_issues --all-completed`: scan type dirs for `status: done` instead of `get_completed_dir().glob()`
- `_find_local_issue()`: type-dir-only search

### Sprint runner + parallel discovery

- `scripts/little_loops/cli/sprint/run.py`: pre-validates sprint issues via `get_completed_dir().glob()` — replace with frontmatter `status: done` check
- `scripts/little_loops/cli/sprint/edit.py`: completed issue lookup via `get_completed_dir()` — replace with status field
- `scripts/little_loops/cli/sprint/show.py`: `completed_issues` tracking in sprint summary — replace with frontmatter filter

### Dependency tools

- `scripts/little_loops/cli/deps.py`: excludes `completed/` and `deferred/` dirs from dependency analysis — replace with `status` field filter
- `scripts/little_loops/dependency_mapper/operations.py`: excludes `"completed"` and `"deferred"` dir name strings from file-hint analysis — replace with status check

### `cli/auto.py` validation

- `scripts/little_loops/cli/auto.py`: delegates to `AutoManager` which calls `find_issues()` (directory-scoped) — no additional changes needed here once `find_issues()` is updated in ENH-1418, but verify no direct directory references remain

## Implementation Steps

1. Update `ll-issues list/show/count` — read `status:` from `IssueInfo.status`; align `--status` choices with new enum (Step 3)
2. Update `ll-sync` — scan type dirs; map `IssueInfo.status` to GitHub open/closed instead of directory checks (Step 6)
3. Update sprint runner (`run.py`, `edit.py`, `show.py`) — replace `get_completed_dir()` lookups with frontmatter `status: done` checks
4. Update dependency tools (`deps.py`, `dependency_mapper/operations.py`) — filter by status field instead of dir name
5. Verify `cli/auto.py` has no remaining direct directory references after ENH-1418 lands
6. Update all corresponding tests (list in Tests to Update section)

## Files to Modify

- `scripts/little_loops/cli/issues/search.py` — status from frontmatter; new status vocab
- `scripts/little_loops/cli/issues/show.py` — status from `info.status`; type-dir-only id resolution
- `scripts/little_loops/cli/issues/count_cmd.py` — align `--status` choices with new enum
- `scripts/little_loops/sync.py` — scan type dirs; use IssueInfo.status for open/closed mapping
- `scripts/little_loops/cli/sprint/run.py` — replace completed dir check with status field
- `scripts/little_loops/cli/sprint/edit.py` — replace `get_completed_dir()` lookup
- `scripts/little_loops/cli/sprint/show.py` — frontmatter-based completed_issues filter
- `scripts/little_loops/cli/deps.py` — status field exclusion
- `scripts/little_loops/dependency_mapper/operations.py` — status field exclusion

## Tests to Update

- `scripts/tests/test_issues_cli.py` — `ll-issues list` and `ll-issues show`; add `--status open|deferred|done|all` filter tests
- `scripts/tests/test_issues_path.py` — `_resolve_issue_id()` type-dir-only lookup post-migration
- `scripts/tests/test_issues_search.py` — `TestSearchStatusFilter`: update `test_include_completed`, `test_status_all`, `test_status_completed_only`, `test_text_query_with_include_completed` to use `status:` frontmatter in type dirs
- `scripts/tests/test_sprint.py`, `test_sprint_integration.py` — update `get_completed_dir()` pre-validation tests to use `status: done` frontmatter check
- `scripts/tests/test_orchestrator.py` — parallel orchestrator issue-discovery tests; verify status-field filtering works correctly
- `scripts/tests/test_sync.py` — `GitHubSyncManager` directory-to-remote-state mapping → `IssueInfo.status` field mapping
- `scripts/tests/test_cli_output.py` — update/remove `get_completed_dir`/`get_deferred_dir` mocks at line 291–292
- `scripts/tests/test_dependency_mapper.py` — `TestValidateDependencies::test_stale_completed_ref` and `test_valid_with_completed_blocker`: update `completed_ids=` API call after directory-based approach is replaced
- `scripts/tests/conftest.py` — add `status: open` to fixture issue file content; keep `"completed_dir"`/`"deferred_dir"` keys during migration, remove after ENH-1420

## Acceptance Criteria

- `ll-issues list` defaults to showing `open` + `in_progress`; `--status deferred` and `--status done` filters work
- `ll-issues show` displays correct status from frontmatter
- `ll-sync` maps `status: done` → remote closed and `status: open` → remote open without directory checks
- Sprint pre-validation uses `status: done` check
- Dependency tools exclude done/deferred issues via status field
- All updated tests pass

## Success Metrics

- Zero calls to `get_completed_dir()` or `get_deferred_dir()` remain in the listed files after changes
- `ll-issues list` returns correct results for `--status open`, `--status done`, `--status deferred`, and `--status all`
- `ll-sync` correctly maps `status: done` → remote closed and `status: open` → remote open without directory checks
- All updated tests pass without regressions

## Scope Boundaries

- **In scope**: `ll-issues list/show/count`, `ll-sync`, sprint runner (`run.py`/`edit.py`/`show.py`), parallel orchestrator discovery, `ll-deps`, `dependency_mapper/operations.py`, and their tests
- **Out of scope**: Core `IssueInfo.status` model and `find_issues()` (ENH-1417/ENH-1418); command/skill/doc updates (ENH-1421); migration script (ENH-1420); any new status vocab beyond the enum established in ENH-1417

## Session Log
- `/ll:format-issue` - 2026-05-10T15:18:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa41123a-15d8-4c8c-adaa-e1f58a46abea.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

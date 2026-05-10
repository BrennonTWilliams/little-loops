---
id: ENH-1423
type: ENH
priority: P2
status: open
parent_issue: ENH-1419
decision_needed: false
---

# ENH-1423: Decouple Issue Status — ll-sync

## Summary

Update `ll-sync` (`GitHubSyncManager`) to scan type dirs and use `IssueInfo.status` frontmatter for open/closed mapping instead of directory location. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1424, ENH-1425, ENH-1426 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Motivation

`GitHubSyncManager` currently globs `get_completed_dir()` to determine which issues are closed on GitHub. Removing this directory coupling allows issues to live in type-scoped directories and still sync correctly by reading `status: done` from frontmatter.

## Proposed Solution

### `sync.py` — `GitHubSyncManager`

- `_get_local_issues()` (lines 264–284): scan all type dirs (bugs/, features/, enhancements/); use `IssueInfo.status` to map to GitHub open/closed instead of directory check
- `close_issues()` (lines 926–931): replace `get_completed_dir().glob()` with a scan of type dirs filtering for `status: done`
- `reopen_issues()` (line 1079): replace `issue_path.parent == completed_dir` check with `IssueInfo.status != "done"` (or equivalent)
- `_find_local_issue()` (lines 741–761): replace re-glob of `get_completed_dir()` with type-dir-only search using `IssueInfo.status`

## Implementation Steps

1. Update `scripts/little_loops/sync.py:GitHubSyncManager._get_local_issues()` — scan type dirs via `config.issue_categories` + `config.get_issue_dir()`; map `IssueInfo.status in ("done", "cancelled")` to closed, otherwise open; replace the `sync_completed` completed-dir glob (lines 279–282) with a status filter on the type-dir scan (include issues with `status in ("done", "cancelled")` when `sync_completed=True`)
2. Update `scripts/little_loops/sync.py:close_issues()` — replace `get_completed_dir().glob()` (lines 926–931) with type-dir scan filtering for `IssueInfo.status in ("done", "cancelled")`
3. Update `scripts/little_loops/sync.py:reopen_issues()` — replace `issue_path.parent == completed_dir` check (line 1078) with `IssueInfo.status == "done"` check; remove the entire `git mv` block (lines 1078–~1090) — no file moves in the status-based model; call `update_frontmatter(issue_path, {"status": "open"})` (from `scripts/little_loops/frontmatter.py`) after successful GitHub reopen instead
4. Update `scripts/little_loops/sync.py:_find_local_issue()` — remove the second-pass completed-dir glob (lines 756–760) entirely; since `_get_local_issues()` will scan all type dirs, the fallback is redundant
5. Update `scripts/tests/test_cli_sync.py` — add `status: done` frontmatter to completed issue fixtures in `mock_config` setup; move those fixture files from `completed/` to type dirs; remove `(issues_dir / "completed").mkdir(parents=True)`
6. Update `scripts/tests/test_sync.py` — migrate all issue fixtures (currently in `tmp_path / ".issues" / "completed"`) to type dirs with `status: done` frontmatter; update `test_close_all_completed` (line 1318) and `test_reopen_specific_issue_in_completed` (line 1452) to use status-field logic; remove `completed_dir` local variable construction; verify no `git mv` is attempted in reopen tests
7. Update `scripts/tests/test_cli.py` — remove `"completed_dir": "completed"` from inline config dicts at lines 293, 480, 1471, 1586, 2370; add `status: done` frontmatter to fixture issue files currently placed in `completed/` dirs; move those fixture files to type dirs (`bugs/`, `features/`, `enhancements/`); remove `completed/` directory creation in test setup

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Canonical reference implementation** — follow `_load_issues_with_status()` in `scripts/little_loops/cli/issues/search.py:106` exactly: iterate `for category in config.issue_categories`, call `config.get_issue_dir(category)`, call `IssueParser(config).parse_file(f)`, dispatch on `issue.status`.

**`reopen_issues()` file-move removal** — the `git mv` block (lines 1078–~1090) physically moves files from `completed/` back to type dirs. In the new model issues never leave type dirs, so this entire block is dead code. Remove it. To update local state after reopen, call `update_frontmatter(issue_path, {"status": "open"})` from `scripts/little_loops/frontmatter.py` (already used elsewhere in sync.py for `github_issue` writes).

**`get_deferred_dir()` in sync.py** — research confirms zero calls to `get_deferred_dir()` in `sync.py`. The acceptance criterion "Zero calls to `get_deferred_dir()`" is already satisfied; no action needed there.

**Test fixture migration pattern** (from test_sync.py and test_issues_cli.py precedent):
```python
# Before
(completed_dir / "P1-BUG-001-bug.md").write_text(
    "---\ngithub_issue: 42\n---\n\n# BUG-001: Bug\n\nBody.\n"
)

# After
(bugs_dir / "P1-BUG-001-bug.md").write_text(
    "---\nstatus: done\ngithub_issue: 42\n---\n\n# BUG-001: Bug\n\nBody.\n"
)
```

## Files to Modify

- `scripts/little_loops/sync.py`
- `scripts/tests/test_cli_sync.py`
- `scripts/tests/test_sync.py`
- `scripts/tests/test_cli.py`

## Acceptance Criteria

- `ll-sync` maps `status: done` → remote closed and `status: open` → remote open without directory checks
- `close_issues --all-completed` scans type dirs for `status: done` instead of `get_completed_dir().glob()`
- `_find_local_issue()` finds issues in type dirs regardless of status
- Zero calls to `get_completed_dir()` or `get_deferred_dir()` remain in `sync.py` after changes
- All updated tests pass

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `sync.py` | `_get_local_issues()` | globs active dirs + `get_completed_dir()` when `sync_completed=True` | 264–284 |
| `sync.py` | `close_issues()` | globs `get_completed_dir()` when `all_completed=True` | 926–931 |
| `sync.py` | `reopen_issues()` | `issue_path.parent == completed_dir` guard + `git mv` block | 1078–~1090 |
| `sync.py` | `_find_local_issue()` | second-pass `get_completed_dir()` glob (lines 756–760) unconditionally | 741–761 |

### Breaking Tests

- `scripts/tests/test_cli_sync.py` — `mock_config` fixture calls `(issues_dir / "completed").mkdir(parents=True)`; must add `status: done` frontmatter instead
- `scripts/tests/test_sync.py` — all fixtures write issue files directly into `completed_dir` with no `status:` frontmatter (lines 1296, 1323, 1452); must migrate to type dirs with `status: done`
- `scripts/tests/test_cli.py` — hard-codes `"completed_dir": "completed"` at lines 293, 480, 1471, 1586, 2370; creates `completed/` dirs directly

### Similar Patterns

- `scripts/little_loops/cli/issues/search.py:106` — `_load_issues_with_status()`: canonical type-dir scan using `config.issue_categories` + `config.get_issue_dir()` + `IssueParser.parse_file()` + `issue.status` dispatch — **reference implementation to follow**
- `scripts/little_loops/cli/issues/skip.py:38` — `cmd_skip()`: guard pattern reading `issue_info.status` from frontmatter instead of checking parent directory
- `scripts/little_loops/sprint.py:323` — `SprintManager._find_issue_file()`: type-dir-only search pattern (no completed/ fallback)

## Session Log
- `/ll:refine-issue` - 2026-05-10T17:41:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80589cd9-0071-4d69-8045-5fbc3b9a2e61.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

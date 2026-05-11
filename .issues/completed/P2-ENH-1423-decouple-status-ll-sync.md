---
id: ENH-1423
type: ENH
priority: P2
status: done
completed_at: 2026-05-10T18:01:15Z

decision_needed: false
confidence_score: 98
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
parent: ENH-1419
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/cli/sync.py` — change `close_parser.add_argument("--all-completed", ...)` help text from "Close all GitHub issues whose local counterparts are in `completed/`" to "Close all GitHub issues whose local counterparts have `status: done` or `status: cancelled`"
9. Update `docs/reference/CLI.md` — rewrite `ll-sync close --all-completed` description to reference status-based detection; rewrite `ll-sync reopen` section to describe `status` being set back to `open` instead of a file move from `completed/`
10. Update `commands/sync-issues.md` — fix the status-action `find` template (line ~171) that uses `-not -path "*/completed/*"`; replace with a status-aware scan or remove the exclusion pattern

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sync.py` — `main_sync()` calls `manager.close_issues()` (line ~163) and `manager.reopen_issues()` (line ~172); also contains `close_parser.add_argument("--all-completed", ...)` whose help text reads "Close all GitHub issues whose local counterparts are in `completed/`" — this string must be updated to reflect status-based detection

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-sync close --all-completed` description references the `completed/` directory; `ll-sync reopen` section describes a file move from `completed/` back to the active type dir — both descriptions become incorrect after the git mv block is removed
- `commands/sync-issues.md` — Status action (line ~171) uses an inline `find` template with `-not -path "*/completed/*"` to exclude completed issues; this is not status-aware and will behave incorrectly once issues with `status: done` live in type dirs

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_sync.py` — write **new** tests for the following behaviors not yet covered:
  - `_get_local_issues()` returns issues with `status: done` from type dirs (not `completed/`) when `sync_completed=True`
  - `close_issues(all_completed=True)` scans type dirs for `status in ("done", "cancelled")` instead of globbing `completed/`
  - `reopen_issues()` calls `update_frontmatter(issue_path, {"status": "open"})` after a successful GitHub reopen (no `git mv` call)
  - `_find_local_issue()` finds a `status: done` issue in `bugs/` (type dir) without any `completed/` fallback pass

## Resolution

Implemented all 10 steps from the issue plan:

- `sync.py` `_get_local_issues()`: replaced `get_completed_dir()` glob with status filter on type-dir scan (done/cancelled excluded when `sync_completed=False`)
- `sync.py` `close_issues()`: replaced `get_completed_dir().glob()` with type-dir scan filtering `status in ("done", "cancelled")`
- `sync.py` `reopen_issues()`: removed git mv block; calls `update_frontmatter(content, {"status": "open"})` after successful GitHub reopen
- `sync.py` `_find_local_issue()`: removed second-pass completed-dir glob; added explicit type-dir fallback scan
- `sync.py` imports: added `update_frontmatter` to frontmatter import
- `cli/sync.py`: updated `--all-completed` help text
- `test_sync.py`: migrated all completed-dir fixtures to type dirs with `status: done`; updated 8 affected tests; renamed 2 tests; added 3 new tests (TestGetLocalIssues)
- `test_cli.py`: removed `"completed_dir": "completed"` from 5 config dicts; removed `completed/` from directory creation loops
- `docs/reference/CLI.md`: updated `ll-sync close` and `ll-sync reopen` descriptions
- `commands/sync-issues.md`: fixed status-action find template (removed `*/completed/*` exclusion)

Zero `get_completed_dir()` or `get_deferred_dir()` calls remain in `sync.py`. All 252 tests pass.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-10T18:01:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce241dac-979a-45b3-9fe3-99f7de889379.jsonl`
- `/ll:ready-issue` - 2026-05-10T17:51:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f3593ae-6212-4462-8aa4-340ec46773e5.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c94e8a9-aa8e-4703-b2bd-c9c8fded7b56.jsonl`
- `/ll:wire-issue` - 2026-05-10T17:47:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4394f412-f674-4bd5-a857-951ceede64a5.jsonl`
- `/ll:refine-issue` - 2026-05-10T17:41:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80589cd9-0071-4d69-8045-5fbc3b9a2e61.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

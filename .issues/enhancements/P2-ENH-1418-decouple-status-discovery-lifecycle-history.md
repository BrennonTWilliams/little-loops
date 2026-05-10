---
id: ENH-1418
type: ENH
priority: P2
status: open
parent_issue: ENH-1390
---

# ENH-1418: Decouple Issue Status — Discovery, Lifecycle, and History Redesign

## Summary

Update issue discovery (`find_issues()`), lifecycle operations (`close_issue`, `defer_issue`, etc.), the parallel orchestrator, and the issue history parser to use `status:` frontmatter instead of directory location. Depends on ENH-1417 (IssueInfo.status must exist first). Can run in parallel with ENH-1419 and ENH-1421 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Proposed Solution

### Step 2 — `find_issues()` status filter

- `scripts/little_loops/issue_parser.py:find_issues()`: replace frozenset-based filename exclusion (`completed_names`, `deferred_names`) with a post-parse filter: `if info.status in ("done", "deferred", "cancelled"): continue`
- Fix hardcoded `".issues/completed"` path at `issue_manager.py:783`: replace glob with `info.status == "done"` check
- Fix hardcoded `cli/history.py:199` path: stop relying on `completed/` dir

### Step 5 — `capture-issue` skill reopen flow

- `skills/capture-issue/SKILL.md`: replace "reopen completed issue" flow (which currently does a file move from `completed/`) with a `status:` field update via `update_frontmatter()`

### Step 11 — `issue_history/parsing.py` redesign (Sub-decision 1 from ENH-1390)

- `scripts/little_loops/issue_history/parsing.py`: redesign `scan_completed_issues()` to scan type directories (`features/`, `bugs/`, `enhancements/`, `epics/`) and filter on `status: done` from frontmatter
- Redesign `_batch_completion_dates()`: replace git-log file-move approach with `completed_at:` frontmatter field as primary source of truth (already the priority-1 path in `_parse_completion_date()` at lines 185–190); git-log fallback tiers can be removed once ENH-1420 backfills old files
- `scripts/little_loops/cli/history.py:199`: remove hardcoded `completed/` path dependency

### Step 5 (cont.) — `issue_lifecycle.py` + `orchestrator.py`

- `scripts/little_loops/issue_lifecycle.py`: rewrite `close_issue()`, `complete_issue_lifecycle()`, `defer_issue()`, `undefer_issue()` to call `update_frontmatter(path, {"status": ...})` instead of `shutil.move`; each currently calls `config.get_completed_dir()` / `config.get_deferred_dir()` — replace those calls
- `scripts/little_loops/parallel/orchestrator.py`: update completion path (lines 1210–1289) to write `status: done` to frontmatter instead of moving file; update `_deferred_issues` tracking (lines 127–128, 1000–1017) to use frontmatter reads

## Files to Modify

- `scripts/little_loops/issue_parser.py` — find_issues() status filter
- `scripts/little_loops/issue_manager.py` — fix hardcoded `".issues/completed"` at line 783
- `scripts/little_loops/issue_lifecycle.py` — rewrite close/defer/undefer to use frontmatter
- `scripts/little_loops/parallel/orchestrator.py` — completion path (lines 1210–1289), deferred tracking
- `scripts/little_loops/issue_history/parsing.py` — redesign scan_completed_issues, _batch_completion_dates
- `scripts/little_loops/cli/history.py` — fix hardcoded completed/ path at line 199
- `skills/capture-issue/SKILL.md` — reopen flow → status field update

## Tests to Update

- `scripts/tests/test_issue_lifecycle.py` — `TestCloseIssue`, `TestCompleteIssueLifecycle`: assert on frontmatter writes instead of file moves; update `sample_config` fixture usage
- `scripts/tests/test_issue_discovery.py` — `issues_with_content` fixture: refactor from directory-based to status-field-based discovery
- `scripts/tests/test_issue_history_parsing.py` — `scan_completed_issues()` coupling; update for frontmatter-based completion-date strategy
- `scripts/tests/test_issue_history_cli.py` — ~40 references to `completed/` directory; update all to create files in type dirs with `status: done`
- `scripts/tests/test_issue_manager.py` — `TestPathRenameHandling::test_path_rename_updates_tracking`: update `IssueInfo` construction for new `status` field
- `scripts/tests/test_merge_coordinator.py` — ~15 references to `completed/` dir; update `git mv` simulation to assert frontmatter write
- `scripts/tests/test_refine_status.py` — ~20 test methods with `completed/`/`deferred/` setup blocks; clean up setup

## Acceptance Criteria

- `find_issues()` returns only issues with `status: open` (or `in_progress`/`blocked`) regardless of which type dir they live in
- `close_issue()`, `defer_issue()`, `undefer_issue()` write frontmatter, no longer move files
- `scan_completed_issues()` finds done issues by frontmatter in type dirs
- No hardcoded `completed/` or `deferred/` directory paths remain in the above files
- All updated tests pass

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

---
id: ENH-1424
type: ENH
priority: P2
status: open
parent_issue: ENH-1419
---

# ENH-1424: Decouple Issue Status — Sprint Runner

## Summary

Update the sprint runner (`run.py`, `edit.py`) to use `IssueInfo.status` frontmatter instead of `get_completed_dir()` directory lookups for completed-issue tracking and pre-validation. Depends on ENH-1417. Can run in parallel with ENH-1422, ENH-1423, ENH-1425, ENH-1426 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Motivation

The sprint runner pre-validates issues by globbing `get_completed_dir()` to detect already-completed issues. `edit.py` builds a `completed_ids` set from the same directory. Removing these directory checks lets sprint operations work correctly when issues live in type-scoped directories.

## Proposed Solution

### `sprint/run.py`

- `_cmd_sprint_run()` (lines 162–178): replace `completed_dir.glob(f"*-{issue_id}-*.md")` pre-validation with a check for `IssueInfo.status == "done"` on the resolved issue file

### `sprint/edit.py`

- `_cmd_sprint_edit()` (lines 72–89): replace `get_completed_dir()` glob to build `completed_ids` with a scan of type dirs filtering for `status: done`

### `sprint/show.py`

- Verify-only: confirmed no directory-based logic; `completed_issues` tracking uses `.sprint-state.json`. Verify no regressions after ENH-1417 changes.

## Implementation Steps

1. Update `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()` — replace `completed_dir.glob()` pre-validation with `IssueInfo.status == "done"` check
2. Update `scripts/little_loops/cli/sprint/edit.py:_cmd_sprint_edit()` — replace `get_completed_dir()` glob with type-dir scan filtered by status field
3. Verify `scripts/little_loops/cli/sprint/show.py` — no regressions after ENH-1417 changes
4. Update `scripts/tests/test_sprint.py` — update `get_completed_dir()` pre-validation tests to use `status: done` frontmatter check; add `status: done` to completed issue fixture files
5. Update `scripts/tests/test_sprint_integration.py` — same fixture update for integration tests

## Files to Modify

- `scripts/little_loops/cli/sprint/run.py`
- `scripts/little_loops/cli/sprint/edit.py`
- `scripts/little_loops/cli/sprint/show.py` (verify only)
- `scripts/tests/test_sprint.py`
- `scripts/tests/test_sprint_integration.py`

## Acceptance Criteria

- Sprint pre-validation uses `status: done` check; no calls to `get_completed_dir()` in `run.py`
- `ll-sprint edit` correctly identifies completed issues via frontmatter
- `ll-sprint show` continues to work correctly (no regressions)
- Zero calls to `get_completed_dir()` remain in sprint runner files after changes
- All updated tests pass

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `sprint/run.py` | `_cmd_sprint_run()` | `completed_dir.glob(f"*-{issue_id}-*.md")` pre-validation | 162–178 |
| `sprint/edit.py` | `_cmd_sprint_edit()` | globs `get_completed_dir()` to build `completed_ids` | 72–89 |

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2

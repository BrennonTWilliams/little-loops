---
id: FEAT-1171
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1162
size: Small
depends_on: FEAT-1169
---

# FEAT-1171: Inject `completed_at` in Parallel Orchestrator Path

## Summary

Inject `completed_at` ISO 8601 UTC timestamp into issue frontmatter in `scripts/little_loops/parallel/orchestrator.py` before the inline `git mv` at lines 1182-1196, and add assertions to the orchestrator test suite.

## Parent Issue

Decomposed from FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Prerequisite

Requires FEAT-1169 (adds `update_frontmatter` utility to `frontmatter.py`).

## Motivation

The parallel orchestrator performs its own inline `git mv` and does NOT call `_move_issue_to_completed()`. It must independently inject `completed_at` to ensure parallel completions are timestamped.

## Implementation Steps

1. **`scripts/little_loops/parallel/orchestrator.py`**:
   - Import `update_frontmatter` from `little_loops.frontmatter` (add to imports)
   - Add `from datetime import UTC, datetime` if not already present (`orchestrator.py:1166` uses naive `datetime.now()` — fix this too)
   - Before the inline `git mv` at lines 1182-1196 in `_complete_issue_lifecycle_if_needed()`:
     - Read file content
     - Call `update_frontmatter(content, {"completed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})`
     - Write updated content back to disk
   - Replace the naive `datetime.now().strftime("%Y-%m-%d")` at line 1166 with `datetime.now(UTC).strftime("%Y-%m-%d")` (fix timezone-naive bug while here)

2. **`scripts/tests/test_orchestrator.py`**:
   - Add `completed_at` assertions to `TestCompleteIssueLifecycle` tests that exercise the parallel `git mv` path
   - See `test_appends_session_log_after_successful_git_mv` (line 1674) as the model
   - Assert `'completed_at:' in completed_path.read_text()`

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — inject `completed_at` before inline git mv; fix naive datetime at line 1166
- `scripts/tests/test_orchestrator.py` — add `completed_at` assertions

## Acceptance Criteria

- [ ] Issues completed via the parallel path have `completed_at` in frontmatter
- [ ] `completed_at` format is ISO 8601 UTC with `Z` suffix
- [ ] Naive `datetime.now()` at line 1166 replaced with `datetime.now(UTC)`
- [ ] Orchestrator tests assert `completed_at` is present in completed issue frontmatter

## Session Log
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`

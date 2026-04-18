---
id: FEAT-1162
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue
parent: FEAT-1155
---

# FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Summary

Record a `completed_at` ISO 8601 UTC timestamp in issue frontmatter whenever an issue is moved to `.issues/completed/`, covering all four code paths that perform this move.

## Parent Issue

Decomposed from FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Motivation

Without `completed_at`, cycle-time metrics in `ll-history` can only resolve to day granularity. All completion paths must write this timestamp atomically before the `git mv` so the data is never missing in the completed file.

## Implementation Steps

There are four distinct completion paths — all must be updated:

1. **`scripts/little_loops/issue_lifecycle.py:294`** — `_move_issue_to_completed()` — primary helper called by both sequential and automated-closure paths. Inject `completed_at` into frontmatter here using `_iso_now()` (line 26) before calling `git mv`. Use the `_update_issue_frontmatter` pattern from `sync.py:160-182` for the YAML round-trip.

2. **`scripts/little_loops/parallel/orchestrator.py:1182-1196`** — `_complete_issue_lifecycle_if_needed()` — parallel path performs its own inline `git mv` (does NOT call `_move_issue_to_completed()`). Must independently inject `completed_at` here.

3. **`skills/manage-issue/SKILL.md:408-418`** — interactive path; LLM runs `git mv` directly. Add an Edit-tool step to write `completed_at` to frontmatter immediately before the `git mv` command.

4. **Verify callers**: `issue_lifecycle.py:648` (`complete_issue_lifecycle`) and `issue_lifecycle.py:545` (`close_issue`) both call `_move_issue_to_completed()` — no direct changes needed if logic goes into the helper.

### Reusable Utilities

- `scripts/little_loops/issue_lifecycle.py:26-28` — `_iso_now()` returns `datetime.now(UTC).isoformat()` — use directly (note: produces `+00:00` suffix, not `Z`; standardize format across Python and shell paths).
- `scripts/little_loops/sync.py:160-182` — `_update_issue_frontmatter(content, updates)` — YAML round-trip updater pattern to replicate or extract.

### Timestamp Format Note

`_iso_now()` returns `+00:00` suffix; shell `date -u` produces `Z`. Decide format early and apply consistently. Recommendation: normalize to `Z` suffix everywhere by using `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` in Python paths.

## API/Interface

New frontmatter field:

```yaml
completed_at: "2026-05-01T09:15:44Z"  # set when moved to completed/
```

## Acceptance Criteria

- [ ] Issues moved to `completed/` via `_move_issue_to_completed()` contain `completed_at`
- [ ] Issues completed via the parallel orchestrator path contain `completed_at`
- [ ] Issues completed via `manage-issue` skill contain `completed_at`
- [ ] `completed_at` is a valid ISO 8601 UTC string
- [ ] Existing issues without `completed_at` continue to work without errors

## Files to Modify

- `scripts/little_loops/issue_lifecycle.py` — inject `completed_at` in `_move_issue_to_completed()` (line 294) before git mv; reuse `_iso_now()` from line 26
- `scripts/little_loops/parallel/orchestrator.py` — inject `completed_at` before the inline `git mv` at lines 1182-1196
- `skills/manage-issue/SKILL.md` — add Edit-tool step to write `completed_at` before `git mv` (near lines 408-418)

## Tests

- `scripts/tests/test_issue_lifecycle.py` — add assertions that `completed_at` appears in frontmatter after `_move_issue_to_completed()`; update `TestMoveIssueToCompleted` class (6 tests at lines 271-465) and `TestCompleteIssueLifecycle.test_full_complete_flow` (line 1114)
- `scripts/tests/test_orchestrator.py` — add `completed_at` assertions to `TestCompleteIssueLifecycle` tests that exercise the parallel `git mv` path; see `test_appends_session_log_after_successful_git_mv` (line 1674)

## Session Log
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`

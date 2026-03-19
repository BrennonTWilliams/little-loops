---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# FEAT-830: `ll-issues show` does not search the deferred directory

## Summary

`_resolve_issue_id` in `ll-issues show` searches active category directories and the completed directory, but does not include the deferred directory. Issuing `ll-issues show FEAT-123` for a deferred issue returns "not found" even though the file exists on disk.

## Location

- **File**: `scripts/little_loops/cli/issues/show.py`
- **Line(s)**: 62-82 (at scan commit: 8c6cf90)
- **Anchor**: `in function _resolve_issue_id`
- **Code**:
```python
search_dirs: list[Path] = []
for category in config.issue_categories:
    search_dirs.append(config.get_issue_dir(category))
search_dirs.append(config.get_completed_dir())
# Missing: config.get_deferred_dir()
```

## Current Behavior

`ll-issues show <id>` searches active and completed directories but not deferred. Deferred issues cannot be viewed by ID.

## Expected Behavior

`_resolve_issue_id` should also search `config.get_deferred_dir()`, consistent with `_load_issues_with_status` in `search.py` which supports deferred issues.

## Use Case

A developer defers an issue and later wants to review its contents to decide whether to undefer it. They run `ll-issues show BUG-042` and get "not found" instead of the issue contents.

## Acceptance Criteria

- [ ] `ll-issues show <id>` finds issues in the deferred directory
- [ ] No change to default output format
- [ ] Works with both full ID (BUG-042) and partial matching

## Proposed Solution

Add `search_dirs.append(config.get_deferred_dir())` after the completed directory line in `_resolve_issue_id`.

## Impact

- **Priority**: P3 - User-facing functional gap; deferred issues appear to vanish
- **Effort**: Small - One line addition
- **Risk**: Low - Additive search path
- **Breaking Change**: No

## Labels

`feature`, `cli`, `issues`

## Status

**Open** | Created: 2026-03-19 | Priority: P3


## Verification Notes

- **Verified**: 2026-03-19 by `/ll:verify-issues`
- **Verdict**: VALID
- **File exists**: `scripts/little_loops/cli/issues/show.py` confirmed present
- **Line numbers accurate**: `_resolve_issue_id` at lines 17-82; `search_dirs` built at lines 62-66 — matches issue description
- **Code snippet verified**: `search_dirs` includes active categories and `config.get_completed_dir()` but NOT `config.get_deferred_dir()`
- **Claim validated**: `search.py:_load_issues_with_status` (line 91) and `issue_discovery/search.py` (line 67) both support deferred via `config.get_deferred_dir()` — confirming the inconsistency
- **`get_deferred_dir` available**: Method exists on `BRConfig` (found in 10 files)
- **Deferred directory**: `.issues/deferred/` exists on disk (currently empty)

## Session Log
- `/ll:verify-issues` - 2026-03-19T22:16:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8637da89-7c9f-4c8a-bd66-a7063d39b45a.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`

---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-704: Add `--search` text filter to `ll-issues list`

## Summary

`ll-issues list` supports `--type` and `--priority` filters but has no text-search capability. Users cannot filter issues by title or content keywords. The `IssueInfo` objects carry a `title` field that could be matched against a search pattern.

## Location

- **File**: `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list`
- **File**: `scripts/little_loops/cli/issues/__init__.py` — subparser (lines 63-77)

## Current Behavior

Issues can only be filtered by type prefix and priority level. No text-based filtering.

## Expected Behavior

`ll-issues list --search "thread"` filters the issue list to only show issues whose title contains the search term (case-insensitive).

## Use Case

A developer wants to find all issues related to "parallel" or "thread safety": `ll-issues list --search thread` quickly narrows the list without manually scanning.

## Acceptance Criteria

- [ ] `ll-issues list --search <term>` filters by case-insensitive title match
- [ ] Combinable with existing filters: `--type BUG --search lock`
- [ ] Empty results show a clear message
- [ ] Works with `--json` output mode

## Impact

- **Priority**: P4 - Quality-of-life improvement for issue navigation
- **Effort**: Small - Add arg, filter `IssueInfo` list by `term.lower() in info.title.lower()`
- **Risk**: Low - Additive feature
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4

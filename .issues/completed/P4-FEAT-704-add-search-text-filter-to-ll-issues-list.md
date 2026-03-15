---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
closed_date: 2026-03-14
closed_reason: wont-do
---

# FEAT-704: Add `--search` text filter to `ll-issues list`

## Summary

`ll-issues list` supports `--type` and `--priority` filters but has no text-search capability.

## Motivation

When a backlog grows beyond ~50 issues, scanning the full list for a keyword (e.g., "thread", "parallel", "frontmatter") is tedious. Text search combined with existing `--type` and `--priority` filters makes targeted issue lookup practical without leaving the terminal. Users cannot filter issues by title or content keywords. The `IssueInfo` objects carry a `title` field that could be matched against a search pattern.

## Location

- **File**: `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list`
- **File**: `scripts/little_loops/cli/issues/__init__.py` — subparser (lines 63-77)

## Current Behavior

Issues can only be filtered by type prefix and priority level. No text-based filtering.

## Expected Behavior

`ll-issues list --search "thread"` filters the issue list to only show issues whose title contains the search term (case-insensitive).

## Use Case

A developer wants to find all issues related to "parallel" or "thread safety": `ll-issues list --search thread` quickly narrows the list without manually scanning.

## Proposed Solution

Add `--search <term>` argument to the `list` subparser. In `cmd_list`, after `find_issues()` returns `IssueInfo` objects, filter with `[i for i in issues if term.lower() in i.title.lower()]` before rendering.

## Acceptance Criteria

- [ ] `ll-issues list --search <term>` filters by case-insensitive title match
- [ ] Combinable with existing filters: `--type BUG --search lock`
- [ ] Empty results show a clear message
- [ ] Works with `--json` output mode

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py`, add `--search` argument to the `list` subparser (type=str, optional)
2. In `list_cmd.py`, after `find_issues()`, add `if args.search: issues = [i for i in issues if args.search.lower() in i.title.lower()]`
3. If `issues` is empty after filtering, print a "No issues matching '...' found" message
4. Verify `--search` composes correctly with `--type`, `--priority`, and `--json`

## Integration Map

- **Modified**: `scripts/little_loops/cli/issues/__init__.py` — `list` subparser (lines 63-77)
- **Modified**: `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` (add filter after `find_issues()` call)
- **Data used**: `IssueInfo.title` field (already populated by `find_issues()`)

## Impact

- **Priority**: P4 - Quality-of-life improvement for issue navigation
- **Effort**: Small - Add arg, filter `IssueInfo` list by `term.lower() in info.title.lower()`
- **Risk**: Low - Additive feature
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Closed (Won't Do — Superseded)** | Created: 2026-03-13 | Closed: 2026-03-14 | Priority: P4

## Closure Notes

Superseded by `ll-issues search`, which already provides a strict superset of this feature: full-text search across title and body content, combinable type/priority/label/date-range filters, multiple output formats (`--json`, `--format ids/list/table`), and support for active, completed, and deferred issues. Adding `--search` to `ll-issues list` is redundant.

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/cli/issues/__init__.py` subparser for `list` has no `--search` argument. `scripts/little_loops/cli/issues/list_cmd.py` `cmd_list` has no search/filter on `IssueInfo.title`. `list_cmd.py` supports `--json` (confirmed at line 36). Feature not yet implemented.

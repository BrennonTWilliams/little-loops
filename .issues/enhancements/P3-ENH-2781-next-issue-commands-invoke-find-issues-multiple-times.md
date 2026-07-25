---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
blocked_by: [ENH-2780]
---

<!-- Suggested by scan-codebase: file overlap with issue_parser.py (ENH-2780) -->

# ENH-2781: `next-issue`/`next-issues` invoke `find_issues` 2-4 times per command; parse once and share

## Summary

A single `ll-issues next-issue`/`next-issues` invocation parses the entire
issue directory multiple times: with `--include-blocked`, once to rank issues
and again to build the `DependencyGraph`; without it, the
`skip_blocked=True` call itself does two internal passes (ENH-2780) and the
no-ready-issues fallback path adds another — up to 3-4 full parses.

## Location

- **File**: `scripts/little_loops/cli/issues/next_issues.py`
- **Line(s)**: 13-89 (parses at 44, 56, 74, 77, at scan commit: fb567390)
- **Anchor**: `in function cmd_next_issues()`
- **Code**:
```python
all_issues = [i for i in find_issues(config) if not i.issue_id.startswith("EPIC-")]  # parse 1
...
graph = DependencyGraph.from_issues(find_issues(config), all_known_ids=all_known_ids)  # parse 2
...
issues = [i for i in find_issues(config, skip_blocked=True) ...]  # parse 3 (x2 internally)
if not issues:
    all_active = [i for i in find_issues(config) ...]  # parse 4
```
- Same pattern in `scripts/little_loops/cli/issues/next_issue.py`,
  `cmd_next_issue()`, lines 49, 65, 82, 91.

## Current Behavior

Each command run re-walks and re-parses `.issues/` up to 4 times.

## Expected Behavior

One parsed `IssueInfo` list is reused: rank from it, build
`DependencyGraph.from_issues(...)` from it, and derive the ready subset by
filtering it against `graph.get_ready_issues()`.

## Proposed Solution

Parse once via `find_issues(config)`, pass that list into
`DependencyGraph.from_issues(...)`, and replace the extra
`find_issues(..., skip_blocked=True)` / fallback calls with in-memory
filters over the same list.

## Impact

- **Effort**: Medium
- Cuts `next-issue(s)` latency by 2-4x on large backlogs; these commands run
  on every autodev/ll-auto dequeue cycle.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`

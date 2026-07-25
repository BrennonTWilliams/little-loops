---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
relates_to: [ENH-2781]
---

# ENH-2780: `find_issues(skip_blocked=True)` re-parses the entire issue directory to build the dependency graph

## Summary

Every `find_issues(..., skip_blocked=True)` call parses all matching issue
files once, then — inside the `skip_blocked` branch — calls
`find_issues(config, status_filter=set(non_terminal))` again, a second
complete `IssueParser.parse_file()` pass (frontmatter, session-log, and
regex section extraction per file) over essentially all non-terminal issues,
solely to build the `DependencyGraph`.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 1241-1286 (first pass at 1247, second pass at 1275, at scan commit: fb567390)
- **Anchor**: `in function find_issues(), skip_blocked branch`
- **Code**:
```python
for cat in categories:
    issue_dir = config.get_issue_dir(cat)
    ...
    for issue_file in issue_dir.glob("*.md"):
        info = parser.parse_file(issue_file)   # 1st full parse pass
        ...
if skip_blocked:
    ...
    all_active = find_issues(config, status_filter=set(non_terminal))  # 2nd full parse pass
```

## Current Behavior

Two full parse passes over the issue tree per call. With ~2,600 issue files
in this repo, every readiness-filtered listing pays the directory walk and
markdown parse twice.

## Expected Behavior

One parse pass: the dependency graph and readiness filter are computed from
a single shared parsed issue set.

## Proposed Solution

Have the `skip_blocked` branch build `all_active` by filtering the
already-parsed `issues` list, plus one targeted parse only for
categories/files not already covered; or extract a lower-level
`_find_issues_raw()` helper both steps share.

## Impact

- **Effort**: Medium
- Halves issue-directory I/O and parsing for every `skip_blocked` caller
  (`ll-issues next-issue(s)`, autodev dequeue paths, sprint planning).

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`

---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# ENH-826: `diff_all` spawns one subprocess per synced issue

## Summary

`GitHubSyncManager.diff_all` spawns a separate `gh issue view` subprocess for every synced issue to fetch its GitHub body for diffing. A repository with 50 synced issues generates 50 sequential subprocess calls, making the operation slow.

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 836-865 (at scan commit: 8c6cf90)
- **Anchor**: `in method GitHubSyncManager.diff_all`
- **Code**:
```python
for issue_path in local_issues:
    ...
    cmd_result = _run_gh_command(
        ["issue", "view", str(int(github_number)), "--json", "body", "-q", ".body"],
        self.logger,
    )
```

## Current Behavior

For each local issue with a `github_issue` frontmatter value, a separate `gh issue view` subprocess is spawned sequentially. N synced issues = N subprocess calls.

## Expected Behavior

Batch-fetch GitHub issue bodies in a single API call, then compare locally. This replaces N subprocesses with one.

## Motivation

`diff_all` is called during `ll-sync status` and `ll-sync diff` workflows. As the number of synced issues grows, the operation becomes increasingly slow (each `gh` invocation takes ~1-2 seconds for auth + API call).

## Proposed Solution

Collect all GitHub issue numbers upfront, then use `gh issue list --json number,body --limit 500` once to fetch all bodies. Build a lookup dict keyed by issue number:

```python
numbers = [...]  # collected from frontmatter
result = _run_gh_command(
    ["issue", "list", "--json", "number,body", "--limit", "500"],
    self.logger,
)
bodies = {item["number"]: item["body"] for item in json.loads(result.stdout)}
```

## Scope Boundaries

- Out of scope: Parallel subprocess execution (batch is simpler)
- Out of scope: Caching bodies between runs

## Impact

- **Priority**: P3 - Noticeable slowdown on repositories with many synced issues
- **Effort**: Small - Replace loop with single fetch + dict lookup
- **Risk**: Low - Uses same `gh` tool, just fewer invocations
- **Breaking Change**: No

## Labels

`enhancement`, `sync`, `performance`

## Status

**Open** | Created: 2026-03-19 | Priority: P3


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`

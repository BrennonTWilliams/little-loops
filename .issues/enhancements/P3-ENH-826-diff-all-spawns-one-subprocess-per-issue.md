---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
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


## Verification Notes

- **Verified**: 2026-03-19 | **Verdict**: VALID
- File `scripts/little_loops/sync.py` exists. `GitHubSyncManager.diff_all` is at line 823.
- The one-subprocess-per-issue loop is confirmed at lines 838–865; `_run_gh_command(["issue", "view", ...])` is at lines 851–854.
- Quoted code snippet matches current code exactly.
- Minor line number discrepancy: issue states "836-865" but `_run_gh_command` is at line 851. Line 836 is `local_issues = self._get_local_issues()`. Not significant.
- No dependency references to validate.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-19_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- `gh issue list` returns open issues only by default. Synced issues that are closed on GitHub will not appear in the batch result. Implementation should add `--state all` to the `gh issue list` call, or fall back to per-issue fetch for numbers missing from the batch result.

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc051ae-f218-443d-ad6a-bad1a1757fb1.jsonl`
- `/ll:verify-issues` - 2026-03-19T22:36:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc051ae-f218-443d-ad6a-bad1a1757fb1.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`

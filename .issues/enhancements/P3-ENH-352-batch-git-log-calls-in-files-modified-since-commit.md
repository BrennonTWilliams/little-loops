---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# ENH-352: Batch git log calls in _get_files_modified_since_commit

## Summary

`_get_files_modified_since_commit` spawns a separate `git log` subprocess for each file to check if it was modified since a commit. This should be a single batched call.

## Location

- **File**: `scripts/little_loops/issue_discovery.py`
- **Line(s)**: 462-496 (at scan commit: be30013)
- **Anchor**: `_get_files_modified_since_commit`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/be30013d0e2446b479c121af1d58a2309b3cfeb5/scripts/little_loops/issue_discovery.py#L462-L496)

## Current Behavior

For each file in `target_files`, a separate `git log` subprocess is spawned. N files = N subprocess calls.

## Expected Behavior

A single `git log` call with all file paths: `git log --pretty=format:%H --name-only {commit}..HEAD -- file1 file2 ...`

## Proposed Solution

Replace the per-file loop with a single batched call and parse the combined output to determine which files were modified.

## Scope Boundaries

- Only batch the git log calls, do not change the function's return contract

## Impact

- **Priority**: P3 - Reduces subprocess overhead for issue verification
- **Effort**: Small - Single function refactor
- **Risk**: Low - git log supports multiple paths natively
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `captured`

---

**Open** | Created: 2026-02-12 | Priority: P3

---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan-codebase
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

## Motivation

This enhancement would:
- Reduce subprocess overhead during issue verification by replacing N subprocess calls with a single batched call
- Business value: Faster issue discovery and verification workflows, especially in repositories with many tracked files
- Technical debt: Eliminates an inefficient per-file subprocess pattern in favor of git's native multi-path support

## Implementation Steps

1. **Replace per-file loop with batched call**: Refactor `_get_files_modified_since_commit` to invoke a single `git log --pretty=format:%H --name-only {commit}..HEAD -- file1 file2 ...`
2. **Parse combined output**: Process the batched git log output to determine which files were modified
3. **Preserve return contract**: Ensure the function returns the same data structure as before
4. **Run tests**: Execute `python -m pytest scripts/tests/test_issue_discovery.py` to verify no regressions

## Integration Map

- **Files to Modify**: `scripts/little_loops/issue_discovery.py`
- **Dependent Files (Callers/Importers)**: Internal callers within `issue_discovery.py` that use `_get_files_modified_since_commit`
- **Similar Patterns**: N/A
- **Tests**: `scripts/tests/test_issue_discovery.py`
- **Documentation**: N/A
- **Configuration**: N/A

## Scope Boundaries

- Only batch the git log calls, do not change the function's return contract

## Impact

- **Priority**: P3 - Reduces subprocess overhead for issue verification
- **Effort**: Small - Single function refactor
- **Risk**: Low - git log supports multiple paths natively
- **Breaking Change**: No

## Blocked By

- ENH-349: consolidate duplicated file path extraction (shared issue_discovery.py)

## Blocks

- ENH-387: add type flag to CLI processing tools (shared issue_discovery.py)

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`
- `/ll:format-issue --all --auto` - 2026-02-13


---

**Open** | Created: 2026-02-12 | Priority: P3

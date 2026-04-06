---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# BUG-968: `_is_lifecycle_file_move` substring check matches unrelated paths

## Summary

`MergeCoordinator._is_lifecycle_file_move` uses `"issues/completed/" in dest_path` (without the leading dot) to identify lifecycle file moves. This substring check matches any file path containing that sequence, such as `any-issues/completed/file.py` or `third-party-issues/completed/patch.md`. Such files would be incorrectly classified as lifecycle moves, excluded from stashing, and left in an inconsistent state during merges.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 393–403 (at scan commit: 96d74cda)
- **Anchor**: `in function MergeCoordinator._is_lifecycle_file_move`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/parallel/merge_coordinator.py#L393-L403)
- **Code**:
```python
return (
    ".issues/completed/" in dest_path          # correct — dot-prefixed
    or dest_path.startswith(".issues/completed/")  # redundant with above
    or "issues/completed/" in dest_path        # ← too broad: matches any path containing this
    or dest_path.startswith("issues/completed/")   # ok for root-relative paths
    ...
)
```

## Current Behavior

A file at `any-issues/completed/somefile.py` (a hypothetical path containing `issues/completed/`) passes `"issues/completed/" in dest_path` and is classified as a lifecycle file move. `_stash_local_changes` skips stashing it, and the merge proceeds without protecting those changes.

## Expected Behavior

Only paths that are genuinely lifecycle moves — under `.issues/completed/` or `issues/completed/` at the repo root — should match. Paths where `issues/completed/` appears as a substring in a deeper directory should not match.

## Motivation

False positives silently skip stashing legitimate source files, which could cause them to be overwritten or lost during a merge. The bug is unlikely to trigger on a typical project but is a correctness defect in an important safety mechanism.

## Steps to Reproduce

1. Add a tracked file at a path matching `*-issues/completed/*.py` in the repo.
2. Modify the file so it shows up in `git status`.
3. Trigger a merge cycle via `ll-parallel`.
4. Observe: the file is not stashed before the merge because `_is_lifecycle_file_move` returns `True` for it.

## Root Cause

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in function MergeCoordinator._is_lifecycle_file_move`
- **Cause**: `"issues/completed/" in dest_path` is a substring check with no boundary anchoring. It matches any path that contains `issues/completed/` anywhere, not just paths rooted at `issues/completed/` or `.issues/completed/`.

## Proposed Solution

Replace the broad substring check with a path prefix or anchored pattern:

```python
from pathlib import PurePosixPath

def _is_lifecycle_file_move(self, dest_path: str) -> bool:
    p = PurePosixPath(dest_path)
    lifecycle_prefixes = (
        ".issues/completed",
        ".issues/deferred",
        "issues/completed",
        "issues/deferred",
    )
    return any(
        str(p).startswith(prefix + "/") or p.parts[:len(PurePosixPath(prefix).parts)] == PurePosixPath(prefix).parts
        for prefix in lifecycle_prefixes
    )
```

Or more simply, use `startswith` consistently and drop the unanchored `in` checks:

```python
return (
    dest_path.startswith(".issues/completed/")
    or dest_path.startswith(".issues/deferred/")
    or dest_path.startswith("issues/completed/")
    or dest_path.startswith("issues/deferred/")
)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py` — `_is_lifecycle_file_move`

### Dependent Files (Callers/Importers)
- `_stash_local_changes` in the same file — calls `_is_lifecycle_file_move`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_merge_coordinator.py` — add test for `_is_lifecycle_file_move` with edge case paths containing `issues/completed/` as a substring

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace unanchored `in` substring checks with `startswith` checks in `_is_lifecycle_file_move`
2. Add parametrized test cases covering: true positive (`.issues/completed/`), root-relative (`issues/completed/`), false positive (e.g., `my-issues/completed/`)

## Impact

- **Priority**: P4 — Unlikely to trigger on real projects but is a correctness defect in a safety mechanism
- **Effort**: Small — Replacing 2 lines in one function
- **Risk**: Low — Only tightens the match criteria; false negatives (not matching a real lifecycle file) would just stash the file, which is the safe behavior
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `parallel`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4

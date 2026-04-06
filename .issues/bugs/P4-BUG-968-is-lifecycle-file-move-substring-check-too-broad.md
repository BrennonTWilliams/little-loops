---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
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
- `scripts/little_loops/parallel/merge_coordinator.py` — `_is_lifecycle_file_move` (lines 393–403)
- `scripts/little_loops/parallel/merge_coordinator.py:178–186` — secondary `in`-check block in `_stash_local_changes` for non-rename entries (modified/added files in lifecycle dirs); identical substring pattern, same bug; not addressed in current Implementation Steps _(Wiring pass added by `/ll:wire-issue`:)_

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/merge_coordinator.py:168` — `_stash_local_changes` calls `_is_lifecycle_file_move` to skip lifecycle moves before stash
- `scripts/little_loops/parallel/merge_coordinator.py:427` — `_commit_pending_lifecycle_moves` calls `_is_lifecycle_file_move` to find uncommitted lifecycle moves before merge

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py:26` — imports `MergeCoordinator`; no change needed (private method, signature unchanged)
- `scripts/little_loops/parallel/__init__.py:37` — re-exports `MergeCoordinator` in `__all__`; no change needed

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_merge_coordinator.py` — existing class `TestLifecycleFileMoveExclusion` (line ~836) covers true-positive and non-rename cases; add a new test method in this class for the false-positive edge cases (e.g., `my-issues/completed/`, `third-party-issues/completed/`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_merge_coordinator.py::TestLifecycleFileMoveExclusion` — **missing: `deferred/` true-positive tests** (`.issues/deferred/`, `issues/deferred/` → should return `True`); none exist anywhere in the file
- `scripts/tests/test_merge_coordinator.py::TestLifecycleFileMoveExclusion` — **missing: `deferred/` false-positive boundary** (`my-issues/deferred/file.md` → should return `False` after fix)
- `scripts/tests/test_merge_coordinator.py::TestLifecycleFileMoveEdgeCases` (line ~2686) — edge case class exists; note this as the alternate location for boundary tests
- Convention: the existing file uses grouped `assert` calls inside single test methods (not `@pytest.mark.parametrize`); new tests should follow this style

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/MERGE-COORDINATOR.md:161` — method table describes `_is_lifecycle_file_move` as "Identifies issue file renames to completed/" — omits `deferred/`; update description after fix
- `docs/development/MERGE-COORDINATOR.md:550` — battle-tested evolution log (`BUG-018` entry); per project convention, add a BUG-968 entry here once fixed

### Configuration
- N/A

## Implementation Steps

1. In `merge_coordinator.py:395–404`, replace the 8-clause `return` expression in `_is_lifecycle_file_move` with 4 `startswith` checks (`.issues/completed/`, `.issues/deferred/`, `issues/completed/`, `issues/deferred/`), dropping all `in` substring checks
2. In `scripts/tests/test_merge_coordinator.py`, add a new test method to `TestLifecycleFileMoveExclusion` that asserts `_is_lifecycle_file_move` returns `False` for `my-issues/completed/` and `third-party-issues/completed/` paths
3. Run `python -m pytest scripts/tests/test_merge_coordinator.py::TestLifecycleFileMoveExclusion -v` to confirm all cases pass

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. In `merge_coordinator.py:178–186`, fix the secondary `in`-check block in `_stash_local_changes` — same substring pattern applied to non-rename entries (modified/added files in lifecycle dirs); replace all `in` checks with `startswith` to mirror the fix in step 1
5. In `scripts/tests/test_merge_coordinator.py::TestLifecycleFileMoveExclusion`, add tests for `deferred/` paths:
   - True-positive: `.issues/bugs/file.md -> .issues/deferred/file.md` → `True`
   - True-positive: `issues/bugs/file.md -> issues/deferred/file.md` → `True`
   - False-positive boundary: `my-issues/deferred/file.md -> my-issues/deferred/v2.md` → `False`
6. Update `docs/development/MERGE-COORDINATOR.md:161` — change method description from "renames to completed/" to "renames to completed/ or deferred/"
7. Update `docs/development/MERGE-COORDINATOR.md:550` — add BUG-968 entry to the battle-tested evolution log

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
- `/ll:confidence-check` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6b83689-e38b-4d5c-9bf2-3397041e577d.jsonl`
- `/ll:wire-issue` - 2026-04-06T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:refine-issue` - 2026-04-06T19:03:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b8e371d7-b665-4469-820b-3fefb8f3907f.jsonl`
- `/ll:format-issue` - 2026-04-06T19:02:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b62b3af5-f0ff-40bf-954c-77e65503e981.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4

---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-971: `find_issues` makes double `Path.exists()` syscalls per file in hot loop

## Summary

`find_issues` iterates every `.md` file in an active issue directory and checks two `Path.exists()` syscalls per file — one for the completed path and one for the deferred path — to skip already-moved issues. `find_issues` is called on every `ll-auto`, `ll-parallel`, sprint run, and several CLI commands. Pre-materializing the completed and deferred filename sets as a `frozenset` before the loop replaces O(N) syscalls with O(1) membership tests.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 638–661 (at scan commit: 96d74cda)
- **Anchor**: `in function find_issues`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_parser.py#L638-L661)
- **Code**:
```python
for issue_file in issue_dir.glob("*.md"):
    completed_path = completed_dir / issue_file.name
    if completed_path.exists():        # syscall per file
        continue
    deferred_path = deferred_dir / issue_file.name
    if deferred_path.exists():         # syscall per file
        continue
```

## Current Behavior

For a project with 200 active issues, each `find_issues` call performs up to 400 `stat` syscalls (2 per file). `find_issues` is called by `IssuePriorityQueue.scan_issues`, `SprintManager.load_issue_infos`, `cmd_sequence`, and multiple CLI commands, so the overhead compounds across a typical run.

## Expected Behavior

The completed and deferred filename sets are materialized once with a single `glob` before the loop. Each per-file check becomes an O(1) `frozenset` membership test.

## Motivation

`find_issues` sits on the critical path of `ll-auto`, `ll-parallel`, and sprint execution. Reducing 400 syscalls to 2 `glob` calls improves startup latency for every automated run, which compounds when `find_issues` is called repeatedly.

## Proposed Solution

```python
completed_names = (
    frozenset(p.name for p in completed_dir.glob("*.md"))
    if completed_dir.exists() else frozenset()
)
deferred_names = (
    frozenset(p.name for p in deferred_dir.glob("*.md"))
    if deferred_dir.exists() else frozenset()
)

for issue_file in issue_dir.glob("*.md"):
    if issue_file.name in completed_names:
        continue
    if issue_file.name in deferred_names:
        continue
    ...
```

The two `glob` calls read directory entries in a single OS call each, which is more cache-friendly than N individual `stat` calls.

## Scope Boundaries

- Only change the skip-check mechanism; do not alter filtering logic, sorting, or return value structure
- The `completed_dir.exists()` guard is needed since the directory may not exist on fresh projects

## Success Metrics

- `find_issues` on a 200-issue project should issue 2 directory reads (one for completed, one for deferred) instead of up to 400 stat calls for the skip checks

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `find_issues`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `IssuePriorityQueue.scan_issues`
- `scripts/little_loops/sprint_manager.py` — `SprintManager.load_issue_infos`
- `scripts/little_loops/cli/issues/search.py` — `cmd_list`, `cmd_sequence`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_issue_parser.py` — existing `find_issues` tests should pass unchanged; add a test confirming completed/deferred files are excluded correctly

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `completed_names` and `deferred_names` frozenset pre-computation before the loop in `find_issues`
2. Replace `completed_path.exists()` / `deferred_path.exists()` checks with set membership
3. Confirm all existing tests pass; optionally add a performance assertion for large input

## Impact

- **Priority**: P3 — Hot path optimization; benefits every automated run and CLI command that calls `find_issues`
- **Effort**: Small — 6-line change before the loop
- **Risk**: Low — Logic-equivalent transformation; no change in return values
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P3

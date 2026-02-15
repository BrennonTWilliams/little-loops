---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# FEAT-434: Standalone overlap detection command for pre-flight checks

## Summary

Overlap detection (ENH-143) exists in `ParallelConfig` but only operates during execution. There's no standalone command to analyze potential overlaps without running `ll-parallel` or `ll-sprint`. A pre-flight check command would help users preview conflicts.

## Current Behavior

Overlap detection is embedded in `ll-parallel` execution. Users can only discover overlaps by starting a parallel run, at which point overlapping issues are either serialized or warned about.

## Expected Behavior

A command like `ll-parallel check-overlaps` or `ll-deps check-overlaps` analyzes all active issues for file overlaps and reports potential conflicts without executing anything.

## Motivation

Pre-flight overlap analysis lets users plan execution order before committing to a run. This is especially valuable for large batches where discovering conflicts mid-run wastes time and may require restarts.

## Use Case

Before running `ll-parallel`, a developer runs `ll-parallel check-overlaps` to see which issues share files. The output shows 2 pairs that will be serialized. The developer decides to process one pair's issues in separate runs for cleaner merge history.

## Acceptance Criteria

- Command lists all issue pairs with overlapping file references
- Shows overlap details (shared files, estimated conflict severity)
- Distinguishes true conflicts from parallel-safe overlaps
- Exit code indicates presence/absence of conflicts

## Proposed Solution

Add a `check-overlaps` subcommand or standalone function:

```python
def check_overlaps(issues_dir: Path) -> list[OverlapResult]:
    issues = discover_active_issues(issues_dir)
    hints = {i.id: extract_file_hints(i.content, i.id) for i in issues}
    overlaps = []
    for i, a in enumerate(issues):
        for b in issues[i+1:]:
            if hints[a.id].overlaps_with(hints[b.id]):
                overlaps.append(OverlapResult(a.id, b.id, shared_files=...))
    return overlaps
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/parallel.py` or `scripts/little_loops/cli/deps.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py` — reuse `extract_file_hints()`
- `scripts/little_loops/parallel/types.py` — reuse overlap config

### Similar Patterns
- `ll-deps analyze` provides dependency analysis
- FEAT-433 (sprint conflict analysis) is complementary

### Tests
- Add test for overlap detection command

### Documentation
- Update CLI help text

### Configuration
- N/A

## Implementation Steps

1. Add subcommand to appropriate CLI tool
2. Implement overlap scanning using existing `extract_file_hints`
3. Format output report
4. Add tests

## Impact

- **Priority**: P4 - Nice-to-have for planning, workaround exists (just run with detection on)
- **Effort**: Small - Reuses existing overlap infrastructure
- **Risk**: Low - Read-only analysis
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `parallel`, `cli`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4

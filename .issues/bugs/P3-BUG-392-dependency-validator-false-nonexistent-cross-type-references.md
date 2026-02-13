---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# BUG-392: Dependency validator reports false "nonexistent" for valid cross-type issue references

## Summary

The dependency validation in `analyze_dependencies()` reports "references nonexistent ENH-342" for BUG-359, despite ENH-342 existing at `.issues/enhancements/P4-ENH-342-command-examples-hardcode-tool-names.md`. The validator fails to find valid cross-type references (a BUG referencing an ENH in its `Blocked By` section).

## Current Behavior

Running `ll-sprint show bug-fixes` outputs:
```
Issue BUG-359 blocked by unknown issue ENH-342
...
  BUG-359: references nonexistent ENH-342
```

But `ENH-342` exists and is a valid active issue file.

## Expected Behavior

The validator should find ENH-342 across all issue category directories (bugs, features, enhancements) and not report it as nonexistent. It should only report references as nonexistent when the issue file truly cannot be found.

## Steps to Reproduce

1. Have a bug issue (BUG-359) with `## Blocked By` referencing an enhancement (ENH-342)
2. Ensure ENH-342 exists in `.issues/enhancements/`
3. Run `ll-sprint show bug-fixes` (with BUG-359 in the sprint)
4. Observe: warning says ENH-342 is nonexistent

## Actual Behavior

Two warnings are emitted:
- "Issue BUG-359 blocked by unknown issue ENH-342" (from DependencyGraph)
- "BUG-359: references nonexistent ENH-342" (from dependency_mapper validation)

## Root Cause

- **File**: `scripts/little_loops/dependency_mapper.py`
- **Anchor**: `in function analyze_dependencies()` (validation section)
- **Cause**: The validator likely only searches for referenced issues within the set of issues passed to it (the sprint issues), rather than scanning the full `.issues/` directory. Since ENH-342 is not part of the sprint, it's treated as nonexistent. The validation should distinguish between "not in this sprint" and "doesn't exist at all."

## Proposed Solution

TBD - requires investigation into `analyze_dependencies()` and `DependencyGraph.from_issues()` to determine where the lookup is scoped too narrowly. The fix should:

1. Check the full `.issues/` directory (all categories) when validating references
2. Distinguish between "exists but not in sprint" vs "truly nonexistent"
3. Adjust warning message: "blocked by ENH-342 (not in sprint)" vs "references nonexistent ENH-342"

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper.py` — `analyze_dependencies()` validation logic
- `scripts/little_loops/dependency_graph.py` — possibly `DependencyGraph.from_issues()` if it also emits the "unknown issue" warning

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint.py` — calls `analyze_dependencies()`, displays warnings

### Tests
- `scripts/tests/test_dependency_graph.py` — add cross-type reference test for BUG-referencing-ENH scenario
- `scripts/tests/test_dependency_mapper.py` — add validation test for cross-category issue reference resolution

### Documentation
- N/A — internal bug fix, no user-facing doc changes

### Configuration
- N/A

## Motivation

This bug would:
- Eliminate false positive "nonexistent" warnings that erode trust in the dependency validation output
- Business value: Ensures sprint planning decisions are based on accurate dependency data, not misleading warnings
- Technical debt: Fixes a lookup scope limitation that will produce more false positives as cross-type dependencies become more common

## Implementation Steps

1. Trace the "unknown issue" and "nonexistent" warnings to their source functions
2. Add full-directory lookup for referenced issue IDs
3. Change warning messages to distinguish "not in sprint" from "truly missing"
4. Add test with cross-type blocked_by reference

## Impact

- **Priority**: P3 - False positive warnings erode trust in the tool's output
- **Effort**: Small - Likely a lookup scope fix
- **Risk**: Low - Only affects warning messages, not execution
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Dependency system architecture |

## Blocked By

- ENH-388: standardize issue priority range to P0-P8 (shared ARCHITECTURE.md)

## Labels

`bug`, `dependency-mapper`, `sprint`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab030831-19f7-4fb7-8753-c1c282a30c99.jsonl`
- `/ll:format_issue --all --auto` - 2026-02-13

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# FEAT-433: Sprint conflict analysis CLI (ll-sprint analyze)

## Summary

The sprint CLI has `create`, `run`, `list`, `show`, `edit`, and `delete` subcommands but lacks a dedicated conflict analysis command. Sprint execution internally calls `refine_waves_for_contention()`, but there's no way to preview conflicts without running the sprint.

## Current Behavior

Users must run `ll-sprint show` (which loads the full dependency graph) or start `ll-sprint run` to discover conflicts. There's no lightweight command to preview which issues in a sprint will conflict.

## Expected Behavior

`ll-sprint analyze <sprint-name>` performs conflict detection and reports which issues share files, which will be serialized, and which can safely run in parallel — without executing any issues.

## Motivation

Large sprints with 10+ issues benefit from pre-flight conflict analysis. Users want to know before execution which issues will contend, so they can restructure the sprint or manually set dependencies. This is analogous to `--dry-run` for execution planning.

## Use Case

A developer creates a sprint with 12 issues and runs `ll-sprint analyze my-sprint`. The output shows 3 pairs of issues that overlap on shared files, recommending wave ordering. The developer uses `ll-sprint edit my-sprint` to adjust dependencies before running.

## Acceptance Criteria

- `ll-sprint analyze <name>` outputs conflict report
- Report shows: issue pairs with overlapping files, recommended serialization order, parallel-safe groups
- Runs quickly (no execution, only file analysis)
- Exit code 0 if no conflicts, 1 if conflicts found (useful for CI)

## Proposed Solution

Add `analyze` subcommand to `ll-sprint` CLI:

```python
def cmd_analyze(args: Namespace) -> int:
    sprint = load_sprint(args.name)
    issues = load_sprint_issues(sprint)
    # Reuse existing wave refinement logic
    waves = build_execution_waves(issues)
    conflicts = detect_wave_conflicts(waves)
    print_conflict_report(conflicts)
    return 1 if conflicts else 0
```

Reuse `refine_waves_for_contention()` and `extract_file_hints()` from `dependency_graph.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — add `analyze` subcommand

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py` — reuse `refine_waves_for_contention()`

### Similar Patterns
- `ll-deps analyze` provides similar analysis for individual issues

### Tests
- `scripts/tests/` — add test for analyze subcommand

### Documentation
- Update CLI help text

### Configuration
- N/A

## Implementation Steps

1. Add `analyze` subparser to sprint CLI
2. Implement conflict detection using existing wave refinement
3. Format output as readable report
4. Add exit code behavior for CI usage
5. Add tests

## Impact

- **Priority**: P3 - Useful for sprint planning, reuses existing infrastructure
- **Effort**: Small - Mostly wiring existing functions to a new subcommand
- **Risk**: Low - Read-only analysis, no side effects
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `sprint`, `cli`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3

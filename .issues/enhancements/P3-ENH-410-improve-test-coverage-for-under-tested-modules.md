---
discovered_date: 2026-02-13
discovered_by: capture_issue
---

# ENH-410: Improve Test Coverage for Under-tested Modules

## Summary

Several Python modules have significant coverage gaps. This issue tracks improving test coverage for the least-tested modules, excluding `logo.py` (trivial ASCII art, 0% coverage is acceptable).

## Current Behavior

Current coverage for under-tested modules (from pytest --cov run on 2026-02-13):

| Module | Stmts | Coverage | Missed Lines |
|--------|-------|----------|--------------|
| `cli/sync.py` | 98 | 10% | 88 missed |
| `cli/docs.py` | 46 | 11% | 41 missed |
| `issue_history.py` | 1825 | 74% | 481 missed |
| `parallel/orchestrator.py` | 542 | 81% | 103 missed |
| `parallel/merge_coordinator.py` | 439 | 81% | 83 missed |
| `issue_discovery.py` | 322 | 82% | 59 missed |
| `cli/loop.py` | 663 | 82% | 119 missed |
| `cli/messages.py` | 82 | 84% | 13 missed |
| `fsm/executor.py` | 238 | 84% | 39 missed |
| `parallel/worker_pool.py` | 412 | 84% | 64 missed |

Overall project coverage: 86% (10798 stmts, 1554 missed).

## Expected Behavior

- `cli/sync.py` and `cli/docs.py` should reach >= 80% coverage
- `issue_history.py` should reach >= 85% coverage
- All other listed modules should reach >= 90% coverage
- Overall project coverage should reach >= 90%

## Motivation

Higher test coverage reduces regression risk, especially in complex modules like `issue_history.py` (1825 lines, largest module) and the `parallel/` subsystem which handles concurrency. CLI entry points (`cli/sync.py`, `cli/docs.py`) are nearly untested, meaning regressions in argument parsing or output formatting would go undetected.

## Proposed Solution

TBD - requires investigation per module. General approach:
- CLI entry points (`cli/sync.py`, `cli/docs.py`): Add tests for argument parsing, output formatting, and error paths
- `issue_history.py`: Focus on the 481 uncovered lines in the reporting/analysis sections
- `parallel/` modules: Add tests for error recovery paths, edge cases in worker management and merge coordination
- `fsm/executor.py`: Test error handling and edge case execution paths

## Implementation Steps

1. Add tests for `cli/sync.py` and `cli/docs.py` (biggest coverage gaps)
2. Add tests for `issue_history.py` uncovered reporting sections
3. Add tests for `parallel/` subsystem error paths
4. Add tests for remaining modules (`cli/loop.py`, `fsm/executor.py`, `issue_discovery.py`)
5. Verify overall coverage reaches >= 90%

## Scope Boundaries

- **Excluded**: `logo.py` (0% coverage is acceptable — trivial ASCII art)
- **Excluded**: Modules already at >= 90% coverage
- **Out of scope**: Refactoring modules to improve testability (separate issue if needed)

## Impact

- **Priority**: P3 - Important for long-term quality but not blocking anything
- **Effort**: Large - 10+ modules across multiple subsystems, ~1090 uncovered lines
- **Risk**: Low - Adding tests only, no behavior changes
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Development setup and test conventions |
| architecture | docs/ARCHITECTURE.md | Module structure and responsibilities |

## Labels

`enhancement`, `testing`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-02-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff26efc-756f-45c9-b95d-159619b176d9.jsonl`

---

## Status

**Open** | Created: 2026-02-13 | Priority: P3

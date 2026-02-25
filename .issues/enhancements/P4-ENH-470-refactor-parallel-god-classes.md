---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-470: Refactor parallel/ god classes to extract shared concerns

## Summary

Architectural issue found by `/ll:audit-architecture`. The three core classes in `parallel/` average 1,174 lines each, with each class handling multiple distinct responsibilities.

## Current Behavior

The `parallel/` package contains three god classes:

**MergeCoordinator** (`merge_coordinator.py`, 1,226 lines):
- Core merge queue management
- Git stash handling
- Conflict detection and resolution
- Rebase/retry logic
- Worktree cleanup

**WorkerPool** (`worker_pool.py`, 1,164 lines):
- Thread pool management
- Git worktree creation/cleanup
- Claude CLI subprocess execution
- Output parsing integration
- Work verification

**ParallelOrchestrator** (`orchestrator.py`, 1,141 lines):
- Issue scanning and prioritization
- Worker dispatch logic
- State persistence for resume
- Signal handling
- Reporting and summary

## Expected Behavior

Cross-cutting concerns are extracted into focused helper modules. Each core class delegates specific responsibilities to helpers, reducing class size to ~600-800 lines while maintaining the same public API.

## Motivation

This enhancement would:
- Improve development velocity: hard to understand single-class files averaging 1,174 lines
- Reduce maintenance risk: each class has multiple concerns interleaved, making targeted changes difficult
- Improve testability: extracted helpers can be tested independently

## Proposed Solution

Extract cross-cutting concerns into focused helper modules:

1. Create `parallel/worktree_manager.py` — Extract worktree creation/cleanup from WorkerPool and cleanup from MergeCoordinator
2. Create `parallel/state_persistence.py` — Extract state save/restore from ParallelOrchestrator
3. Create `parallel/conflict_resolver.py` — Extract conflict detection, stash handling, and rebase logic from MergeCoordinator
4. Keep core coordination logic in existing classes but delegate to helpers
5. Target: reduce each class to ~600-800 lines

## Scope Boundaries

- **In scope**: Extracting cross-cutting concerns into helper modules; delegating from existing classes to helpers
- **Out of scope**: Changing concurrency model, adding new parallel features, changing public API, modifying thread safety guarantees

## Implementation Steps

1. Identify cross-cutting concerns shared between classes (worktree management, state persistence, conflict resolution)
2. Create helper modules and extract relevant methods
3. Update existing classes to delegate to new helpers
4. Verify thread safety is preserved in extracted code
5. Run full test suite including integration tests
6. Verify no regression in parallel processing behavior

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py` — extract conflict resolution and worktree cleanup
- `scripts/little_loops/parallel/worker_pool.py` — extract worktree management
- `scripts/little_loops/parallel/orchestrator.py` — extract state persistence

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "from.*parallel import\|parallel\." scripts/`

### Similar Patterns
- N/A — novel extraction, not following an existing codebase pattern

### Tests
- `scripts/tests/` — existing parallel tests should pass unchanged after refactor

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Three god classes with interleaved concerns
- **Effort**: Large — Careful refactoring of concurrency code
- **Risk**: Medium — Concurrency code is sensitive to restructuring
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Corrected merge_coordinator.py line count from 1,218 to 1,226
- `/ll:audit-architecture` - 2026-02-25 - Additional large-file finding: `issue_history/formatting.py` (1,020 lines, 6 very large format functions) shares the same "large single-concern module" pattern. Contains `format_analysis_text` (~436 lines) and `format_analysis_markdown` (~480 lines) as massive monolithic formatters. Consider including this file in scope when planning the refactor, splitting by output format type (text, JSON, YAML, markdown) following the `issue_history/` sub-package pattern that already exists.

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

---

## Tradeoff Review Note

**Reviewed**: 2026-02-24 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | LOW |

### Recommendation
Update first - Before implementation, this issue needs: (1) a full dependency audit to replace the "TBD" in Dependent Files, (2) a concrete method-level extraction plan specifying which methods move to which helper modules, (3) a thread-safety review checklist since concurrency code is sensitive to restructuring, and (4) an established pattern to follow (currently marked "N/A — novel extraction"). The HIGH effort with MEDIUM utility ratio does not justify implementation without this preparation.

## Blocked By

- FEAT-441

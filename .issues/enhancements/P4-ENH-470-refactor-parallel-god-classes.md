---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 55
outcome_confidence: 45
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

**Production callers (outside `parallel/` package):**
- `scripts/little_loops/cli/parallel.py:141` — lazily imports `WorkerPool`; `cli/parallel.py:195` — lazily imports `ParallelOrchestrator` (both from `little_loops.parallel`)
- `scripts/little_loops/cli/sprint/run.py` — imports `ParallelOrchestrator` directly from `little_loops.parallel.orchestrator`

**Package re-exports (must stay intact):**
- `scripts/little_loops/parallel/__init__.py` — re-exports `MergeCoordinator`, `WorkerPool`, `ParallelOrchestrator`, `GitLock`, `OverlapDetector`; all external callers depend on these names being available from `little_loops.parallel`

**Test files that patch parallel internals (require careful consideration during refactor):**
- `scripts/tests/test_orchestrator.py` — patches `little_loops.parallel.orchestrator.WorkerPool` and `little_loops.parallel.orchestrator.MergeCoordinator`
- `scripts/tests/test_merge_coordinator.py` — patches `little_loops.parallel.merge_coordinator.subprocess.run`
- `scripts/tests/test_worker_pool.py` — patches `little_loops.parallel.worker_pool._run_claude_base`
- `scripts/tests/test_subprocess_mocks.py` — imports from both `worker_pool` and `merge_coordinator` modules
- `scripts/tests/test_workflow_integration.py` — imports `ParallelOrchestrator` from `little_loops.parallel` and `ParallelConfig` from `little_loops.parallel.types`
- `scripts/tests/test_cli_e2e.py` — imports `ParallelOrchestrator` from `little_loops.parallel`

**Thread safety note:** Extracted helpers from `worker_pool.py` will be called from multiple worker threads; extracted helpers from `merge_coordinator.py` run in the merge background thread. Lock objects currently managed inside the god classes must move with the logic they protect.

### Similar Patterns
- N/A — novel extraction, not following an existing codebase pattern

### Tests
- `scripts/tests/` — existing parallel tests should pass unchanged after refactor

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Three god classes with interleaved concerns
- **Effort**: Large — Careful refactoring of concurrency code
- **Risk**: Medium — Concurrency code is sensitive to restructuring
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Corrected merge_coordinator.py line count from 1,218 to 1,226
- `/ll:verify-issues` - 2026-02-25 - Corrected internal priority from P3 → P4 to match filename (tradeoff review had downgraded priority)
- `/ll:audit-architecture` - 2026-02-25 - Additional large-file finding: `issue_history/formatting.py` (1,020 lines, 6 very large format functions) shares the same "large single-concern module" pattern. Contains `format_analysis_text` (~436 lines) and `format_analysis_markdown` (~480 lines) as massive monolithic formatters. Consider including this file in scope when planning the refactor, splitting by output format type (text, JSON, YAML, markdown) following the `issue_history/` sub-package pattern that already exists.
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl`
- `/ll:audit-architecture` - 2026-02-26 - Dependency mapping audit: `parallel/` has 4 cross-package runtime imports from root (issue_parser, logger, subprocess_utils, work_verification) plus bidirectional coupling via issue_manager→parallel.output_parsing. orchestrator.py sits at Layer 3 with 8 internal deps. Recommend extracting output_parsing to root first (ENH-510) to eliminate bidirectional coupling before tackling god class refactor.

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

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

### Update (2026-02-26 Tradeoff Review)
Second review confirms prior assessment. Scores unchanged: MEDIUM utility, HIGH effort, HIGH complexity, MEDIUM tech debt, LOW maintenance. Dependency audit in "Dependent Files" section has been updated with detailed caller/importer list. Remains blocked by FEAT-441. Recommendation: do not implement until all four preparedness items above are completed.

## Blocked By

- FEAT-441

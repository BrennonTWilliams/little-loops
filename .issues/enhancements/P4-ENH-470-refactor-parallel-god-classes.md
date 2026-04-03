---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 88
outcome_confidence: 71
---

# ENH-470: Refactor parallel/ god classes to extract shared concerns

## Summary

Architectural issue found by `/ll:audit-architecture`. The three core classes in `parallel/` average 1,181 lines each, with each class handling multiple distinct responsibilities.

## Current Behavior

The `parallel/` package contains three god classes:

**MergeCoordinator** (`merge_coordinator.py`, 1,236 lines):
- Core merge queue management
- Git stash handling
- Conflict detection and resolution
- Rebase/retry logic
- Worktree cleanup

**WorkerPool** (`worker_pool.py`, 1,334 lines):
- Thread pool management
- Git worktree creation/cleanup
- Claude CLI subprocess execution
- Output parsing integration
- Work verification

**ParallelOrchestrator** (`orchestrator.py`, 1,163 lines):
- Issue scanning and prioritization
- Worker dispatch logic
- State persistence for resume
- Signal handling
- Reporting and summary

## Expected Behavior

Cross-cutting concerns are extracted into focused helper modules. Each core class delegates specific responsibilities to helpers, reducing class size to ~600-800 lines while maintaining the same public API.

_Current average: ~1,244 lines each (MergeCoordinator: 1,236, WorkerPool: 1,334, ParallelOrchestrator: 1,163)._

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

### Method-Level Extraction Plan

| Method | Current Class | Target Helper | Notes |
|--------|--------------|---------------|-------|
| `_setup_worktree` | `WorkerPool` | `worktree_manager.py` | Creates branch+worktree, copies `.claude/`, writes session marker; calls `_git_lock` and registers `_active_worktrees` under `_process_lock` — lock stays in `WorkerPool`, helper receives path/lock/git_lock as args |
| `_cleanup_worktree` | `WorkerPool` | `worktree_manager.py` | Removes worktree+branch via `_git_lock`; guards `_active_worktrees` check under `_process_lock` — same ownership pattern as `_setup_worktree` |
| `cleanup_all_worktrees` | `WorkerPool` | `worktree_manager.py` | Iterates worktree base dir and delegates to `_cleanup_worktree`; no lock of its own |
| `_detect_worktree_model_via_api` | `WorkerPool` | `worktree_manager.py` | Stateless API probe; no lock involved — pure helper |
| `_cleanup_worktree` | `MergeCoordinator` | `worktree_manager.py` | Near-duplicate of `WorkerPool._cleanup_worktree`; merge the two implementations into a single `remove_worktree(path, branch, git_lock, repo_path)` free function |
| `_stash_local_changes` | `MergeCoordinator` | `conflict_resolver.py` | Sets `self._stash_active`; state flag must move with this method or be passed back as return value |
| `_pop_stash` | `MergeCoordinator` | `conflict_resolver.py` | Reads/clears `self._stash_active`; tightly coupled to `_stash_local_changes` |
| `_mark_state_file_assume_unchanged` | `MergeCoordinator` | `conflict_resolver.py` | Sets `self._assume_unchanged_active`; git hygiene helper |
| `_restore_state_file_tracking` | `MergeCoordinator` | `conflict_resolver.py` | Reads/clears `self._assume_unchanged_active` |
| `_is_lifecycle_file_move` | `MergeCoordinator` | `conflict_resolver.py` | Pure predicate; no state |
| `_commit_pending_lifecycle_moves` | `MergeCoordinator` | `conflict_resolver.py` | Git operations only; no lock needed |
| `_is_local_changes_error` | `MergeCoordinator` | `conflict_resolver.py` | Pure string predicate |
| `_is_untracked_files_error` | `MergeCoordinator` | `conflict_resolver.py` | Pure string predicate |
| `_is_index_error` | `MergeCoordinator` | `conflict_resolver.py` | Pure string predicate |
| `_is_rebase_in_progress` | `MergeCoordinator` | `conflict_resolver.py` | Stateless git query |
| `_abort_rebase_if_in_progress` | `MergeCoordinator` | `conflict_resolver.py` | Stateless git operation |
| `_is_unmerged_files_error` | `MergeCoordinator` | `conflict_resolver.py` | Pure string predicate |
| `_detect_conflict_commit` | `MergeCoordinator` | `conflict_resolver.py` | Pure string parse |
| `_check_and_recover_index` | `MergeCoordinator` | `conflict_resolver.py` | Git health-check; no lock; uses `_git_lock` — pass as arg |
| `_attempt_hard_reset` | `MergeCoordinator` | `conflict_resolver.py` | Git operation; no lock |
| `_handle_conflict` | `MergeCoordinator` | `conflict_resolver.py` | Rebase/retry orchestration; references `self._problematic_commits` — move set with this method or pass as mutable arg |
| `_handle_untracked_conflict` | `MergeCoordinator` | `conflict_resolver.py` | Variant conflict handler; stateless beyond git ops |
| `_load_state` | `ParallelOrchestrator` | `state_persistence.py` | Reads JSON file; populates `self.state` and calls `self.queue.load_completed/load_failed`; helper can return `OrchestratorState` and let orchestrator assign |
| `_save_state` | `ParallelOrchestrator` | `state_persistence.py` | Reads `self.queue` fields to build snapshot; writes JSON; helper receives `state + queue + path` |
| `_cleanup_state` | `ParallelOrchestrator` | `state_persistence.py` | Deletes state file; trivial but belongs with save/load |

### Thread-Safety Checklist

**`WorkerPool` — locks to audit during extraction:**

| Lock | Protected State | Methods Using It | Move With Methods? |
|------|----------------|-----------------|-------------------|
| `_process_lock` (threading.Lock) | `_active_processes`, `_active_worktrees`, `_worker_stages`, `_terminated_during_shutdown` | `terminate_all_processes`, `_cleanup_worktree`, `_process_issue` (worktree registration), `on_start`/`on_end` closures inside `_run_claude_command`, `set_worker_stage`, `get_worker_stage`, `get_active_stages`, `remove_worker_stage` | **Stay in WorkerPool.** `_process_lock` guards 4 distinct dictionaries/sets that are all used by the core dispatch loop. Extracted worktree helpers should receive `_process_lock` and `_active_worktrees` as constructor arguments to the helper class (or as call-site parameters for free functions). |
| `_callback_lock` (threading.Lock) | `_pending_callbacks` | `_handle_completion`, `active_count` | **Stay in WorkerPool.** Callback lifecycle is internal to pool dispatch; not part of worktree management. |

**`MergeCoordinator` — locks to audit during extraction:**

| Lock | Protected State | Methods Using It | Move With Methods? |
|------|----------------|-----------------|-------------------|
| `_lock` (threading.Lock) | `_merged` (list), `_failed` (dict), `_stash_pop_failures` (dict) | `_finalize_merge`, `_handle_failure`, `merged_ids` property, `failed_merges` property, `stash_pop_failures` property | **Stay in MergeCoordinator.** These are result-accumulation state, not conflict-resolver state. `conflict_resolver.py` helpers do not acquire `_lock`. |
| `_shutdown_event` (threading.Event) | merge loop termination | `_merge_loop`, `shutdown` | **Stay in MergeCoordinator.** Loop control is not a conflict-resolver concern. |
| `_stash_active`, `_assume_unchanged_active` (bool flags) | stash/index state within a single merge operation | `_stash_local_changes`, `_pop_stash`, `_mark_state_file_assume_unchanged`, `_restore_state_file_tracking` | **Move with conflict_resolver.py** if those methods are extracted as a class (e.g., `ConflictResolver`). If extracted as free functions, pass flags as explicit in/out parameters. Recommended: make `ConflictResolver` a lightweight class with `stash_active` and `assume_unchanged_active` as instance attributes, called from `MergeCoordinator._process_merge`. |
| `_problematic_commits` (set) | rebase conflict circuit-breaker | `_handle_conflict` | **Move with conflict_resolver.py** — this set belongs logically to conflict handling and has no interaction with `_lock`. |
| `_consecutive_failures`, `_paused` (circuit breaker) | merge coordinator circuit breaker | `_process_merge`, `_finalize_merge` | **Stay in MergeCoordinator.** These guard the overall merge loop behavior, not individual conflict resolution steps. |

**`ParallelOrchestrator` — locks to audit during extraction:**

| Lock | Protected State | Methods Using It | Move With Methods? |
|------|----------------|-----------------|-------------------|
| (none — no `threading.Lock` in orchestrator) | orchestrator is single-threaded; `_shutdown_requested` is written by signal handler and read by main loop | `_signal_handler`, `_execute` | No lock contention to preserve. `state_persistence.py` helpers are pure I/O and require no lock. |

### Extraction Pattern to Follow

The `issue_history/` sub-package (introduced to decompose `issue_history/formatting.py` and `analysis.py`) provides the established pattern for this codebase:

1. **Extract to module-level free functions or lightweight classes** — `issue_history/` modules export functions that accept data objects as arguments rather than holding shared mutable state. Prefer the same approach for stateless helpers (`conflict_resolver.py` predicates, `state_persistence.py` load/save, `worktree_manager.py` git operations).
2. **Re-export from the package `__init__.py`** — `issue_history/__init__.py` re-exports everything from sub-modules so callers do not change their import paths. Apply the same to `parallel/__init__.py`: existing public names (`MergeCoordinator`, `WorkerPool`, `ParallelOrchestrator`) must remain importable from `little_loops.parallel`.
3. **No circular imports** — helpers import only from `little_loops.parallel.types`, `little_loops.parallel.git_lock`, and stdlib. Core classes import helpers. This mirrors `issue_history/` where `models.py` is the only shared dependency between sub-modules.
4. **Tests patch at the module where the name is used** — `test_merge_coordinator.py` currently patches `little_loops.parallel.merge_coordinator.subprocess.run`. After extraction, new test files should patch `little_loops.parallel.conflict_resolver.subprocess.run` etc. Existing tests need no changes because `MergeCoordinator` public API is unchanged.

**Recommended extraction order** (lowest risk first):
1. `state_persistence.py` — pure I/O, no locks, no circular deps, easy to test in isolation
2. `worktree_manager.py` — git operations only, lock passed as argument, clear interface boundary
3. `conflict_resolver.py` — most complex; introduce `ConflictResolver` class to own `stash_active`, `assume_unchanged_active`, and `_problematic_commits` state; called from `MergeCoordinator._process_merge`

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
- `scripts/little_loops/issue_history/` — decomposed a large analysis module into per-concern sub-modules (`hotspots.py`, `coupling.py`, `quality.py`, `regressions.py`, `debt.py`, `doc_synthesis.py`) with re-exports from `__init__.py`. Free functions accept data objects as arguments; no shared mutable state between modules. This is the established pattern to follow.

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

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Parallel mode architecture — `WorkerPool`, `MergeCoordinator`, `ParallelOrchestrator` class relationships (line 428), parallel mode components (line 417) |

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-03-22T05:05:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a58662a-8ea7-4c74-bb16-c6d77d559e08.jsonl`
- `/ll:verify-issues` - 2026-03-22T02:49:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45cffc78-99fd-4e36-9bcb-32d53f60d9c2.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Corrected merge_coordinator.py line count from 1,218 to 1,226
- `/ll:verify-issues` - 2026-02-25 - Corrected internal priority from P3 → P4 to match filename (tradeoff review had downgraded priority)
- `/ll:audit-architecture` - 2026-02-25 - Additional large-file finding: `issue_history/formatting.py` (1,020 lines, 6 very large format functions) shares the same "large single-concern module" pattern. Contains `format_analysis_text` (~436 lines) and `format_analysis_markdown` (~480 lines) as massive monolithic formatters. Consider including this file in scope when planning the refactor, splitting by output format type (text, JSON, YAML, markdown) following the `issue_history/` sub-package pattern that already exists.
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl`
- `/ll:audit-architecture` - 2026-02-26 - Dependency mapping audit: `parallel/` has 4 cross-package runtime imports from root (issue_parser, logger, subprocess_utils, work_verification) plus bidirectional coupling via issue_manager→parallel.output_parsing. orchestrator.py sits at Layer 3 with 8 internal deps. Recommend extracting output_parsing to root first (ENH-510) to eliminate bidirectional coupling before tackling god class refactor.
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; comprehensive caller/importer list and thread safety notes remain current
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `docs/ARCHITECTURE.md` (lines 428, 417) to Related Key Documentation
- `/ll:verify-issues` - 2026-03-03 - Corrected `merge_coordinator.py` line count from 1,226 to 1,236 (actual); average updated from 1,174 to 1,181
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a018087-87e4-41d0-99de-499289e1e675.jsonl` — Updated `worker_pool.py` 1,164→1,316; `orchestrator.py` 1,141→1,143; average updated to 1,232
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — NEEDS_UPDATE: `worker_pool.py` 1,316→1,320; `orchestrator.py` 1,143→1,160; average updated to 1,239
- `/ll:verify-issues` - 2026-03-06T07:14:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7a87dd5-a8d5-4b8f-9271-78a1114bf527.jsonl` — VALID: line counts unchanged (MergeCoordinator: 1,236, WorkerPool: 1,320, Orchestrator: 1,160; avg 1,239)
- `/ll:refine-issue` - 2026-03-06T00:00:00Z - Codebase scan of `merge_coordinator.py`, `worker_pool.py`, `orchestrator.py`: added method-level extraction table (23 methods mapped to 3 helper modules), thread-safety checklist for all lock objects (`_lock`, `_process_lock`, `_callback_lock`, `_shutdown_event`, stash/index flags, `_problematic_commits`), extraction pattern based on `issue_history/` sub-package precedent, and recommended extraction order (state_persistence → worktree_manager → conflict_resolver). Replaced "novel extraction" with concrete pattern reference. Refine count: 6.
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — Readiness: 88/100 (PROCEED WITH CAUTION); Outcome: 71/100 (MODERATE). Both thresholds met. Complexity 18/25 (all within parallel/ subsystem), coverage 18/25, ambiguity 25/25 (method table fully specifies every method, order, and lock), change surface 10/25 (6 test files + 3 production callers).
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: god classes at 1236, 1320, 1163 lines
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — NEEDS_UPDATE: WorkerPool grew to 1,334 lines (was 1,320); updated counts (MergeCoordinator: 1,236, WorkerPool: 1,334, Orchestrator: 1,163; avg 1,244)

---

## Verification Notes

- **Date**: 2026-04-02
- **Verdict**: NEEDS_UPDATE
- Line counts: `merge_coordinator.py` = **1,244** (unchanged), `worker_pool.py` = **1,353** (unchanged), `orchestrator.py` = **1,246** (was 1,229, +17); avg **1,281**. No helper modules created. Enhancement not yet applied.

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

### Update (2026-03-03 Tradeoff Review)
Third review confirms prior assessment. The dependency audit is now complete (detailed caller/importer list in "Dependent Files" section). The remaining preparedness gaps are: (1) a method-level extraction plan specifying which methods move to which helper modules, (2) a thread-safety review checklist for lock ownership during extraction, and (3) an established extraction pattern to follow (currently "novel extraction"). Also note: the 2026-02-26 audit recommends extracting `output_parsing` to root first (ENH-510) to eliminate bidirectional coupling before tackling this refactor. Do not implement until all preparedness items are completed and ENH-510 is addressed.

## Blocked By

---

## Tradeoff Review Note

**Reviewed**: 2026-03-22 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | HIGH |
| Complexity added | HIGH |
| Technical debt risk | MEDIUM |
| Maintenance overhead | LOW |

### Recommendation
Update first - HIGH effort with MEDIUM utility ratio for live concurrency code. The issue is now well-specified (method-level extraction table, thread safety checklist, extraction order). However, the HIGH effort and concurrency risk (14+ test patches may need path updates, lock ownership must be preserved) warrants an explicit `/ll:go-no-go` before starting. Three prior tradeoff reviews have consistently recommended update-first. Proceed only after running go/no-go and confirming bandwidth for careful concurrency refactoring.

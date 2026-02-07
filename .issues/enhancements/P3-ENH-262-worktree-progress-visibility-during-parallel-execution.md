---
discovered_date: 2026-02-06
discovered_by: capture_issue
---

# ENH-262: Add real-time worktree progress visibility during parallel execution

## Summary

Add logger/CLI output updates for worktrees during execution so users have visibility into worktree status and issue implementation progress during parallel worktree execution via `ll-parallel` and/or `ll-sprint`.

## Context

User description: "Add logger/CLI output updates for worktrees during execution, so that the user has visibility into worktree status and Issue implementation progress during parallel worktree execution via `ll-parallel` and/or `ll-sprint`"

Currently, when `ll-parallel` or `ll-sprint` runs multiple workers in parallel, the user has limited real-time feedback about what each worktree/worker is doing. Users must wait until completion or check logs manually to understand progress.

## Current Behavior

- Workers run in parallel with minimal real-time status output
- Users lack visibility into which issues are being worked on, which worktrees are active, and how far along each worker is
- Progress information is only available after completion or by manually inspecting log files

## Expected Behavior

- Real-time CLI output showing each worktree's current status (e.g., started, in-progress, merging, completed, failed)
- Periodic progress updates indicating which issue each worker is processing and what phase it's in
- Summary line or status bar showing overall progress (e.g., "3/8 issues complete, 4 in progress, 1 queued")
- Works for both `ll-parallel` and `ll-sprint` execution modes

## Proposed Solution

TBD - requires investigation. Potential approaches:
1. **Periodic status logger**: A background thread that periodically polls worker state and prints a summary line
2. **Event-driven callbacks**: Workers emit status events that a central reporter formats and displays
3. **Rich/live display**: Use a library like `rich` for a live-updating table of worker statuses
4. **Log-level output**: Add structured log messages at INFO level for key lifecycle transitions per worker

### Key Integration Points

- **Orchestrator main loop**: `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator._execute()` (the main dispatch loop where periodic status could be emitted)
- **Worker lifecycle**: `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._process_issue()` (per-worker processing stages: worktree setup → ready_issue → manage_issue → verification)
- **Completion callback**: `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator._on_worker_complete()` (where individual worker results are processed)
- **Sprint integration**: `scripts/little_loops/sprint.py` — Sprint executor that wraps the parallel orchestrator

## Impact

- **Priority**: P3
- **Effort**: Medium - requires integrating status reporting into the worker lifecycle
- **Risk**: Low - additive feature, no changes to core processing logic

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Parallel execution architecture and worker lifecycle |
| architecture | docs/API.md | CLI and parallel module API reference |

## Labels

`enhancement`, `ll-parallel`, `ll-sprint`, `captured`, `ux`

---

## Status

**Open** | Created: 2026-02-06 | Priority: P3

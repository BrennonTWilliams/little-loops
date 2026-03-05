---
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# ENH-581: `ll-sprint run` Should Pre-Validate Issues Are Still Active Before Wave Dispatch

## Summary

`ll-sprint run` dispatches issues to parallel workers without checking whether they are still in the active issues directory. When an issue has already been moved to `completed/`, the parallel worker still creates a worktree, runs `ready-issue`, and only then discovers the issue is closed — wasting a full worker slot and several minutes of processing time.

## Context

From the 2026-03-04 sprint run, Wave 1 contained 3 already-completed issues (BUG-528, BUG-529, ENH-535) alongside one valid issue (BUG-530). All 3 were dispatched to parallel workers, created worktrees, ran Claude subprocesses, and then failed or were recovered via sequential retry — wasting ~45 minutes of total compute.

The sprint system loads issue metadata at the start (`manager.load_issue_infos()`), but **does not re-check whether the issue file is still in an active directory immediately before dispatch**. A sprint definition can become stale as issues are fixed between sprint creation and sprint execution.

## Current Behavior

Sprint runner (`cli/sprint/run.py`):
1. Loads all issue infos from the sprint definition
2. Builds dependency waves
3. Dispatches each wave to `ParallelOrchestrator`
4. Relies on `ready-issue` (running inside a worktree) as the only staleness check

The orchestrator's `_scan_issues()` does filter by `only_ids` and skips completed IDs from state, but **it scans the active issues directory** — if the issue file was already moved to `completed/`, it won't be found there, and behavior is undefined.

## Expected Behavior

Before building waves (or at least before dispatching each wave), the sprint runner should verify that each issue ID still exists in an active category directory. Issues found in `completed/` or missing entirely should be:
1. Logged as "already completed, skipping"
2. Excluded from the wave without consuming a worker slot
3. Counted as "skipped" (not "failed") in the summary

## Proposed Solution

Add a pre-dispatch validation step in `_cmd_sprint_run()` (cli/sprint/run.py) after loading `issue_infos`:

```python
# Pre-validate: filter out issues already in completed/
active_infos = []
for info in issue_infos:
    if info.path and info.path.exists():
        active_infos.append(info)
    else:
        completed_path = config.get_completed_dir() / info.path.name
        if completed_path.exists():
            logger.info(f"  {info.issue_id}: already in completed/, skipping")
        else:
            logger.warning(f"  {info.issue_id}: issue file not found, skipping")

issue_infos = active_infos
```

This check costs a few filesystem stat calls and prevents potentially hours of wasted parallel processing.

## Motivation

- Sprints are created ahead of time and issues get fixed in the interim
- Sprint resumes (--resume) are especially prone to staleness if issues were fixed in a previous partial run
- The ready-issue worktree approach as the only gate is expensive (creates a worktree, spawns Claude, runs ~2-4 minutes)
- Sequential retry (the current fallback) works but adds latency and defeats the purpose of parallel processing

## Implementation Steps

1. In `cli/sprint/run.py`, after `manager.load_issue_infos()`, add a lightweight file-existence check for each issue
2. Separate into `active_infos` (issue file in active dir) and `skipped_infos` (file in completed or missing)
3. Log skipped issues clearly
4. Build waves only from `active_infos`
5. Include `skipped_infos` in the final summary with "already completed" status
6. Add a test to `tests/test_sprint_run.py` verifying that completed issues are excluded from waves

## Similar Patterns

- `orchestrator.py:693` — `_scan_issues()` skips `completed_issues` from state, but only knows about issues it previously tracked
- `issue_lifecycle.py:558` — `close_issue()` has a similar "already in completed/" fast-path check

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a470e022-6e78-4989-a376-3d78b8dd783e.jsonl`

---
## Status
**Open** | Priority: P3

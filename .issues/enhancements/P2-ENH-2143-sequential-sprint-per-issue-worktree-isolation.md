---
id: ENH-2143
type: ENH
priority: P2
captured_at: '2026-06-14T03:50:03Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: deferred
relates_to:
- BUG-585
- BUG-2141
confidence_score: 85
outcome_confidence: 75
score_complexity: 12
score_test_coverage: 12
score_ambiguity: 16
score_change_surface: 14
---

# ENH-2143: Sequential sprint mode should use per-issue worktree isolation

## Summary

Sequential sprint processing (`process_issue_inplace`) operates directly on the main
working tree with no branch isolation. When Option J fires and spawns a fresh Claude
session, that session runs on main with no sandbox — it can commit to random branches,
modify unrelated files, or ask interactive questions that block the sprint orchestrator
indefinitely. Adding per-issue worktree isolation to the sequential path would contain
the blast radius of a rogue guillotine session without breaking serialization.

## Motivation

Sequential mode was intentionally kept in-place after BUG-585 (which fixed the opposite
problem: sequential was incorrectly using worktrees). The in-place approach is correct
for serialized execution, but it exposes a critical weakness: there is no rollback or
isolation if a session goes rogue (via Option J or otherwise).

Parallel mode avoids this because each worker gets a dedicated worktree. Sequential mode
can adopt the same isolation without losing its serialized execution guarantee by:
- Creating a worktree for each issue
- Processing the issue in that worktree
- Merging back to main serially (same order as today)
- Deleting the worktree after successful merge

## Current Behavior

`sprint/run.py:369` dispatches sequential issues to `process_issue_inplace()`:
```python
issue_result = process_issue_inplace(
    info=issue,
    config=config,
    logger=logger,
    dry_run=args.dry_run,
)
```

`process_issue_inplace()` operates on the current working tree. Option J spawns
a fresh session (`_run_with_continuation()`) that also operates on the current
working tree — no branch, no isolation.

## Proposed Solution

Extend the sequential dispatch path to use worktrees:

1. Before calling the issue processor, create a worktree for the issue:
   ```python
   worktree_path = setup_worktree(issue.issue_id, base_branch="main")
   ```

2. Process the issue inside the worktree (passing `repo_path=worktree_path`).

3. On success, merge the worktree branch back to main (serialized, same as today):
   ```python
   merge_worktree(worktree_path, strategy="merge-commit")
   ```

4. Clean up the worktree regardless of outcome.

This reuses the existing `WorktreeManager` / `ParallelOrchestrator` worktree
infrastructure, just with `max_workers=1` and a deterministic merge order.

**Key benefit for BUG-2141**: Even if Option J spawns a rogue session, it operates
inside the worktree — it can only commit to the worktree branch, not main. The sprint
orchestrator still needs a timeout (BUG-2144) to kill it, but the blast radius is
contained.

## Implementation Steps

1. In `sprint/run.py`, replace the `process_issue_inplace` call in the sequential branch
   with a worktree-aware wrapper (or invoke `ParallelOrchestrator` with `max_workers=1`).
2. Add a `use_worktree: bool = True` parameter to `process_issue_inplace` that, when set,
   creates a temporary worktree for the issue, processes inside it, and merges on return.
3. Ensure sprint state file updates (completed/failed lists) still happen correctly after
   the worktree merge.
4. Add `ll-sprint show` output to indicate sequential issues will use worktrees.
5. Tests: sequential contention sub-wave creates worktrees and merges cleanly.

## Files to Modify

- `scripts/little_loops/cli/sprint/run.py` — sequential dispatch (line 369), add worktree wrapper
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()`, optional worktree parameter
- `scripts/little_loops/parallel/worktree_manager.py` — reuse existing setup/teardown logic

## Impact

- **Severity**: Medium — prevents rogue session from contaminating main; contains Option J blast radius
- **Effort**: Large — touches sprint dispatch, issue manager, and worktree lifecycle
- **Risk**: Medium — sequential mode is load-bearing; careful testing needed
- **Breaking Change**: No (opt-in, or default=True behind a config flag)

## Related Issues

- BUG-585 (done): Sequential sprint was incorrectly using worktrees (opposite bug — this adds worktrees intentionally)
- BUG-2141: Option J loses sprint worker framing — worktrees contain the blast radius even if framing is missing
- BUG-2144: Sprint orchestrator deadlock timeout — complementary mitigation

## Session Log
- `/ll:capture-issue` - 2026-06-14T03:50:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status
**Open** | Priority: P2

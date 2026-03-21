---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# BUG-823: `_cleanup_orphaned_worktrees` fragile branch name derivation

## Summary

`ParallelOrchestrator._cleanup_orphaned_worktrees` derives the branch name from the worktree directory name using `str.replace("worker-", "parallel/")`. This is fragile — if the naming convention changes in one place but not the other, orphan cleanup silently fails to delete the branch because the `branch -D` return code is not checked.

## Location

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Line(s)**: 271-278 (at scan commit: 8c6cf90)
- **Anchor**: `in method ParallelOrchestrator._cleanup_orphaned_worktrees`
- **Code**:
```python
branch_name = worktree_path.name.replace("worker-", "parallel/")
self._git_lock.run(
    ["branch", "-D", branch_name],
    ...
)
```

## Current Behavior

Branch name is derived from directory name via string replacement. If the derived name doesn't match the actual branch, `branch -D` silently fails (return code not checked). Compare with `worker_pool.py:_cleanup_worktree` (line 641) which reads the actual branch name via `git rev-parse --abbrev-ref HEAD`.

Additionally, `_inspect_worktree` at `orchestrator.py:302` uses the same fragile derivation — the string-derived name flows into `PendingWorktreeInfo.branch_name`, which is later passed to `merge_coordinator._cleanup_worktree()`.

## Expected Behavior

Either read the actual branch name from the worktree (using `git rev-parse`) or check the return code of `branch -D` and log a warning on failure.

## Steps to Reproduce

1. Interrupt `ll-parallel` during a run to create orphaned worktrees
2. On the next run, observe that orphaned branches may not be deleted if the naming convention has any inconsistency

## Proposed Solution

Use `git -C <worktree_path> rev-parse --abbrev-ref HEAD` to read the actual branch name before deletion, matching the pattern in `_cleanup_worktree`. Alternatively, check the return code of `branch -D` and log a warning.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py:274` — replace `str.replace` derivation in `_cleanup_orphaned_worktrees` with `subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, ...)`
- `scripts/little_loops/parallel/orchestrator.py:302` — same fix in `_inspect_worktree` (secondary occurrence; feeds `PendingWorktreeInfo.branch_name`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py:449-453` — `_merge_pending_worktrees` calls `branch -D info.branch_name` where `info.branch_name` was string-derived in `_inspect_worktree`; benefits from fix at line 302
- `scripts/little_loops/parallel/merge_coordinator.py:1166` — `_cleanup_worktree(worktree_path, branch_name)` receives `branch_name` from orchestrator; already has `parallel/` prefix guard at line 1188

### Similar Patterns (to model after)
- `scripts/little_loops/parallel/worker_pool.py:658-665` — canonical `rev-parse` pattern using bare `subprocess.run` (not `GitLock.run()`), with `returncode == 0` guard
- `scripts/little_loops/parallel/worker_pool.py:679` — `parallel/` prefix guard before `branch -D`
- `scripts/little_loops/parallel/merge_coordinator.py:1188` — same `parallel/` prefix guard

### Tests
- `scripts/tests/test_orchestrator.py:348` — `TestOrphanedWorktreeCleanup` class covers existing behavior; add test cases for rev-parse success/failure paths and the `parallel/` prefix guard
- `scripts/tests/test_worker_pool.py:754` — `TestWorktreeCleanup` shows the mock pattern: `patch("subprocess.run")` for the bare `rev-parse` call alongside `patch.object(..._git_lock, "run")` for GitLock calls

### Configuration
- None required — worktree naming convention (`worker-<id>-<timestamp>` / `parallel/<id>-<timestamp>`) defined at `worker_pool.py:241-245`

## Impact

- **Priority**: P4 - Orphaned branches accumulate but don't cause functional issues
- **Effort**: Small - Mirror existing pattern from `_cleanup_worktree`
- **Risk**: Low - Additive improvement
- **Breaking Change**: No

## Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Fix `_cleanup_orphaned_worktrees` in `orchestrator.py:271-279`**: Replace the string-replacement derivation with `subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, capture_output=True, text=True)`. Set `branch_name = result.stdout.strip() if result.returncode == 0 else None`. Gate the `branch -D` call on `branch_name and branch_name.startswith("parallel/")`, matching the pattern at `worker_pool.py:679`.

2. **Fix `_inspect_worktree` in `orchestrator.py:299-305`**: Apply the same `rev-parse` pattern for the secondary occurrence. Note: `_inspect_worktree` already uses `GitLock.run()` for the `rev-list` call, but `rev-parse` should use bare `subprocess.run(cwd=worktree_path)` — consistent with `worker_pool.py:659`.

3. **Add tests to `TestOrphanedWorktreeCleanup` in `test_orchestrator.py:348`**: Add cases for (a) rev-parse succeeds and branch is deleted, (b) rev-parse fails and branch deletion is skipped, (c) derived name would have matched but rev-parse returns different actual branch. Follow the mock pattern from `test_worker_pool.py:769` — use `patch("subprocess.run")` for the rev-parse call.

4. **Verify**: Run `python -m pytest scripts/tests/test_orchestrator.py -v -k "cleanup_orphaned"` and `python -m pytest scripts/tests/test_worker_pool.py -v -k "cleanup"`.

## Labels

`bug`, `parallel`, `cleanup`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

**Verified**: 2026-03-19 | **Verdict**: NEEDS_UPDATE

**Core bug is VALID and still present** (orchestrator.py:273):
```python
branch_name = worktree_path.name.replace("worker-", "parallel/")
```
`GitLock.run()` (git_lock.py:81) returns `CompletedProcess` without raising on non-zero exit codes, so the `branch -D` failure at lines 274-278 is silently swallowed — confirming the silent-failure claim.

**Incorrect reference**: The issue states "Compare with `_cleanup_worktree` (line 679)" implying this is in `orchestrator.py`. Line 679 in `orchestrator.py` is `issue = queued.issue_info` — unrelated. The correct comparison is `scripts/little_loops/parallel/worker_pool.py`, `_cleanup_worktree` at line 641, which reads the actual branch via `git rev-parse --abbrev-ref HEAD` at line 660.

**Update needed**: Change the `## Current Behavior` comparison reference from `(line 679)` to `worker_pool.py:_cleanup_worktree (line 641)`.

## Session Log
- `/ll:refine-issue` - 2026-03-21T05:23:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/356af2e8-db65-4a06-a82f-a7cc1aa781aa.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:49:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:confidence-check` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e3b18d90-a338-4eff-b0ba-be389b8e767d.jsonl`

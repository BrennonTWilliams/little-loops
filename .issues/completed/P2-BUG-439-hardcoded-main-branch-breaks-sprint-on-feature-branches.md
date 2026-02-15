---
discovered_date: 2026-02-15
discovered_by: capture-issue
confidence_score: 100
---

# BUG-439: Hardcoded main branch references break ll-sprint/ll-parallel on feature branches

## Summary

`ll-sprint run` and `ll-parallel` hardcode `"main"` as the target branch in 6+ locations across `worker_pool.py` and `merge_coordinator.py`. When running from a non-main branch (e.g., `autodev-2-9`), workers are rebased onto `origin/main` instead of the working branch, and the merge coordinator checks out `main` instead of the original branch — causing merge failures and data loss.

## Steps to Reproduce

1. Check out a feature branch: `git checkout autodev-2-9`
2. Create a sprint: `/ll:create-sprint`
3. Run the sprint: `ll-sprint run all-active`
4. Observe: worktrees are created from HEAD (correct), but post-work rebase targets `origin/main`, merge coordinator checks out `main`, and merges fail

## Current Behavior

The worktree/merge pipeline assumes `main` throughout:

1. **Worktree creation** (`worker_pool.py:494`): Uses HEAD (correct — no explicit start-point)
2. **Post-work rebase** (`worker_pool.py:806,818`): `git fetch origin main` + `git rebase origin/main` — wrong target when on feature branch
3. **Merge checkout** (`merge_coordinator.py:743,760`): `git checkout main` — switches away from feature branch
4. **Merge pull** (`merge_coordinator.py:780,804`): `git pull --rebase origin main` — pulls wrong branch
5. **Conflict retry rebase** (`merge_coordinator.py:983,989,993`): `git fetch origin main` + `git rebase origin/main` — wrong target
6. **Diff comparison** (`worker_pool.py:778`): `git diff --name-only main HEAD` — compares against wrong base

## Actual Behavior

From a sprint run on branch `autodev-2-9`:
```
[16:34:51] [BUG-005] Rebased branch onto origin/main
[16:34:52] Merge conflict for BUG-005, attempting rebase (retry 1/2)
[16:34:53] Merge conflict for BUG-005, attempting rebase (retry 2/2)
[16:34:55] Merge failed for BUG-005: Merge conflict after 3 retries
```

The worker was created from `autodev-2-9` but rebased onto `origin/main`, introducing divergence. The merge coordinator then checked out `main` (not `autodev-2-9`) and attempted to merge there — guaranteed failure.

## Expected Behavior

The system should detect the current branch at startup and use it as the base branch for all operations:
- Worktree branches should be rebased onto the detected base branch
- Merge coordinator should checkout and pull the detected base branch
- Diff comparisons should use the detected base branch

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `_update_branch_base()` and `_get_changed_files()`
- **Cause**: Branch name `"main"` is hardcoded as string literals in git commands. No `base_branch` concept exists in the data model or any of the parallel infrastructure.

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `_process_merge()` and `_handle_conflict()`
- **Cause**: Same — `"main"` hardcoded in checkout, pull, fetch, and rebase commands.

## Error Messages

```
[16:34:52] Git status output: ?? .sprints/all-active.yaml
[16:34:52] Merge conflict for BUG-005, attempting rebase (retry 1/2)
[16:34:53] Merge conflict for BUG-005, attempting rebase (retry 2/2)
[16:34:55] Merge failed for BUG-005: Merge conflict after 3 retries
```

## Motivation

Feature branch workflows are common — users work on long-lived branches and want to run sprints against that branch, not main. This bug makes ll-sprint/ll-parallel completely unusable for any non-main branch workflow, which was the first real-world usage scenario encountered.

## Proposed Solution

### 1. Add `base_branch` to `ParallelConfig`

In `parallel/types.py`, add a field to `ParallelConfig`:
```python
base_branch: str = "main"  # Detected at runtime, "main" is just the default
```

### 2. Auto-detect at startup

In both `cli/parallel.py` and `cli/sprint.py`, detect the current branch before creating the config:
```python
result = subprocess.run(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    capture_output=True, text=True
)
base_branch = result.stdout.strip() if result.returncode == 0 else "main"
```

Pass `base_branch` into `ParallelConfig`.

### 3. Replace all hardcoded `"main"` references

Use `self.config.base_branch` (or `self.parallel_config.base_branch`) instead of `"main"` in:

| File | Lines | Current | Replacement |
|------|-------|---------|-------------|
| `worker_pool.py` | 778 | `"main"` | `self.parallel_config.base_branch` |
| `worker_pool.py` | 806, 818 | `"origin", "main"` / `"origin/main"` | `"origin", base_branch` / `f"origin/{base_branch}"` |
| `merge_coordinator.py` | 743, 760 | `"checkout", "main"` | `"checkout", self.base_branch` |
| `merge_coordinator.py` | 780, 804 | `"origin", "main"` | `"origin", self.base_branch` |
| `merge_coordinator.py` | 983, 989 | `"origin", "main"` / `"origin/main"` | `"origin", self.base_branch` / `f"origin/{self.base_branch}"` |

### 4. Thread `base_branch` through constructors

`MergeCoordinator.__init__()` and `WorkerPool.__init__()` need to receive the base branch from `ParallelConfig` or as a constructor parameter.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/types.py` — add `base_branch` field to `ParallelConfig`
- `scripts/little_loops/parallel/worker_pool.py` — replace 3 hardcoded `"main"` usages
- `scripts/little_loops/parallel/merge_coordinator.py` — replace 5 hardcoded `"main"` usages
- `scripts/little_loops/cli/parallel.py` — detect branch and pass to config
- `scripts/little_loops/cli/sprint.py` — detect branch and pass to config

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — creates WorkerPool and MergeCoordinator
- `scripts/little_loops/config.py` — `get_parallel_config()` builds ParallelConfig

### Tests
- `scripts/tests/test_worker_pool.py` — update mocks for `_update_branch_base()`
- `scripts/tests/test_merge_coordinator.py` — update mocks for checkout/pull/rebase calls
- `scripts/tests/test_parallel_types.py` — test new `base_branch` field
- `scripts/tests/test_cli.py` — test branch detection in CLI entry points
- `scripts/tests/test_orchestrator.py` — verify base_branch threading

### Documentation
- N/A (internal behavior change, no user-facing docs needed beyond changelog)

### Configuration
- `config-schema.json` — consider adding optional `base_branch` override to parallel config

## Implementation Steps

1. Add `base_branch` field to `ParallelConfig` dataclass with `"main"` default
2. Add branch detection utility (shared between `cli/parallel.py` and `cli/sprint.py`)
3. Thread `base_branch` through `WorkerPool` and `MergeCoordinator` constructors
4. Replace all hardcoded `"main"` references in `worker_pool.py` (3 locations)
5. Replace all hardcoded `"main"` references in `merge_coordinator.py` (5 locations)
6. Update tests to cover non-main branch scenarios
7. Verify with existing test suite (no regressions)

## Impact

- **Priority**: P2 - Completely breaks sprint execution on non-main branches; first real-world external usage hit this immediately
- **Effort**: Medium - Straightforward string replacement + threading a config value through constructors, but touches many test files
- **Risk**: Low - Additive change; default `"main"` preserves existing behavior for main-branch workflows
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Parallel processing design |
| architecture | docs/API.md | ParallelConfig API reference |

## Related Issues

- **BUG-180**: Stale worktree base causes merge failures (completed) — the fix for BUG-180 introduced `_update_branch_base()` which hardcodes `origin/main`, directly contributing to this bug
- **ENH-037**: Smarter pull strategy for repeated rebase conflicts (completed) — added merge-strategy fallback but also hardcodes `origin/main`

## Labels

`bug`, `ll-sprint`, `ll-parallel`, `worker-pool`, `merge-coordinator`, `git`

## Session Log
- `/ll:capture-issue` - 2026-02-15 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847109c3-8cd1-41de-9d1c-46ceeaf98ce2.jsonl`

---

## Resolution

Added `base_branch` field to `ParallelConfig` (defaults to `"main"`). Both `cli/parallel.py` and `cli/sprint.py` now auto-detect the current branch via `git rev-parse --abbrev-ref HEAD` at startup and pass it through the config. Replaced all 10 hardcoded `"main"` references across `worker_pool.py`, `merge_coordinator.py`, and `orchestrator.py` with `config.base_branch`. Updated `to_dict`/`from_dict` serialization and test coverage.

## Status

**Completed** | Created: 2026-02-15 | Resolved: 2026-02-15 | Priority: P2

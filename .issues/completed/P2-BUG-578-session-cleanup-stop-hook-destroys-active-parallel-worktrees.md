---
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 68
---

# BUG-578: `session-cleanup.sh` Stop Hook Destroys Active Parallel Worktrees

## Summary

When a Claude subprocess inside a parallel worktree finishes, the `Stop` hook runs `session-cleanup.sh`, which calls `git worktree remove --force` on **all** `.worktrees/*` entries. If the hook's effective CWD is the main repo root (not the worktree), the `[ -d ".worktrees" ]` guard evaluates true and all sibling workers' worktrees are destroyed mid-execution, causing the next subprocess call in those workers to fail with `[Errno 2] No such file or directory: PosixPath(...)`.

## Context

Observed in `ll-sprint-run-debug.txt` (2026-03-04 sprint run). Three parallel workers failed with worktree-not-found errors at different times, each coinciding with the moment a sibling Claude subprocess exited:

- BUG-530 failed at 18:02:46 (worktree vanished immediately after ready-issue Claude exited)
- BUG-529 failed at 18:05:48 (worktree vanished immediately after manage-issue Claude exited)
- BUG-528 failed at 18:07:18 (same pattern)

BUG-142 added `_active_worktrees` guard to `worker_pool._cleanup_worktree()`, but that guard is in Python — the `session-cleanup.sh` bash script has no knowledge of it.

## Current Behavior

`hooks/scripts/session-cleanup.sh` (Stop hook):

```bash
if [ -d "$WORKTREE_BASE" ] && command -v git >/dev/null 2>&1; then
    WORKTREE_PATTERN=$(basename "$WORKTREE_BASE")
    git worktree list 2>/dev/null | grep "$WORKTREE_PATTERN" 2>/dev/null | awk '{print $1}' | while read -r w; do
        [ -n "$w" ] && git worktree remove --force "$w" 2>/dev/null || true
    done || true
fi
```

When Claude's effective CWD at session end is the main repo root, `[ -d ".worktrees" ]` is true and ALL registered worktrees are force-removed — including those actively used by other parallel workers.

## Root Cause

- **File**: `hooks/scripts/session-cleanup.sh`
- **Trigger**: `Stop` event fires when any Claude subprocess exits
- **Guard failure**: `[ -d ".worktrees" ]` is only safe when CWD is inside a worktree. If `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` fails to keep Claude in the worktree directory (e.g., due to file leaks), the Stop hook runs from the main repo root where `.worktrees/` exists.
- **Effect**: `git worktree remove --force` on active worktrees causes the next `subprocess.Popen(cwd=worktree_path)` in the Python worker to raise `FileNotFoundError`.

## Expected Behavior

The Stop hook should never remove a worktree that is actively in use by a running worker. Cleanup should only target the current session's own worktree (if any), not all worktrees.

## Proposed Solution

Add a reliable guard to `session-cleanup.sh` that detects whether the current Claude session is itself running inside a worktree, and if so, skip worktree cleanup entirely:

```bash
# Detect if we are inside a worktree (not the main repo)
if git rev-parse --git-dir > /dev/null 2>&1; then
    GIT_COMMON=$(git rev-parse --git-common-dir 2>/dev/null || echo "")
    GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || echo "")
    if [ "$GIT_DIR" != "$GIT_COMMON" ] && [ "$GIT_COMMON" != ".git" ]; then
        # Inside a worktree — skip worktree cleanup to avoid killing siblings
        return 0
    fi
fi
```

Alternatively: the hook should only remove worktrees with a specific session marker (e.g., a lockfile created by the session), not all worktrees globally.

## Similar Patterns

- `BUG-142` (completed): added `_active_worktrees` Python guard — but that doesn't protect against bash-level cleanup
- `worker_pool.py:612` — `_cleanup_worktree` skips if `worktree_path in self._active_worktrees`

## Steps to Reproduce

1. Run `ll-sprint run <sprint>` with a multi-issue wave (4+ parallel workers)
2. Let one worker complete while others are still running
3. Observe: subsequent workers fail with `[Errno 2] No such file or directory: PosixPath('.worktrees/worker-...')`

## Actual Behavior

Workers fail mid-execution with missing worktree errors. The parallel run falls back to sequential retry for all affected issues.

## Impact

- **Priority**: P2 - Breaks all multi-worker parallel sprint runs; every sibling worker fails when any Claude subprocess exits
- **Effort**: Small - Single bash script change (~10 lines); no Python changes required
- **Risk**: Low - Additive guard; does not change cleanup behavior for the main repo session (happy path unchanged)
- **Breaking Change**: No

## Labels

`bug`, `hooks`, `worktree`, `parallel`

## Implementation Steps

1. Read `hooks/scripts/session-cleanup.sh` and understand the current worktree removal logic
2. Add `git rev-parse --git-common-dir` guard at the top of the cleanup block to detect if the current session is inside a worktree; if so, skip worktree removal entirely
3. Verify the guard does not break main-repo Stop hook behavior (cleanup still runs when Claude exits from the main repo)
4. Test with `ll-sprint run <sprint>` using a multi-issue wave; confirm sibling worktrees survive until their own workers complete

## Integration Map

### Files to Modify
- `hooks/scripts/session-cleanup.sh` — add worktree-detection guard before the `git worktree remove` loop

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — defines the `Stop` hook that invokes `session-cleanup.sh` (line 60)

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:612` — `_cleanup_worktree()` skips if `worktree_path in self._active_worktrees` (Python-level guard this fix mirrors at the bash level)

### Tests
- `scripts/tests/test_worker_pool.py` — existing tests for `_active_worktrees` guard; no automated tests exist for the bash hook script
- `scripts/tests/test_hooks_integration.py` — integration test file to check for relevant hook behavior tests
- Manual: run `ll-sprint run <sprint>` with 4+ workers and verify no `[Errno 2] No such file or directory` errors for sibling workers

### Documentation
- N/A

### Configuration
- N/A

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a470e022-6e78-4989-a376-3d78b8dd783e.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a2ad1fa-f48d-4711-8455-c6f62218b4bc.jsonl`
- `/ll:confidence-check` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e35d8b7-568c-4518-868e-3fe343f4568c.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ee9b94f-78e9-4f21-b7c3-3f05a94e1b37.jsonl`

---
## Resolution

**Fixed** | 2026-03-04

Added a `git rev-parse` guard to `hooks/scripts/session-cleanup.sh` inside the worktree removal block. Before removing any worktrees, the script now detects whether the current session is itself running inside a worktree by comparing `--git-dir` and `--git-common-dir`. When they differ (i.e., we're in a worktree), it returns early and skips all worktree removal — preserving sibling parallel workers' worktrees. Main-repo sessions (where `git-dir == git-common-dir`) proceed with cleanup unchanged.

**Files Changed**:
- `hooks/scripts/session-cleanup.sh` — added 5-line guard before the `git worktree remove` loop

---
## Status
**Completed** | Priority: P2

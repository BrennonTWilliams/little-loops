---
discovered_date: 2026-05-24
discovered_by: capture-issue
captured_at: '2026-05-24T18:10:20Z'
completed_at: '2026-05-24T18:47:22Z'
status: done
relates_to:
- BUG-142
- BUG-578
testable: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1683: Worktree disappears mid-validation in ll-sprint parallel run

## Summary

During a `ll-sprint run refined-ready` invocation, parallel workers fail ~2-3 minutes into the VALIDATING phase with `[Errno 2] No such file or directory: PosixPath('.worktrees/worker-<id>-<ts>')`. Root cause confirmed: when a validation Claude subprocess (`ll-ready-issue`) exits, Claude Code fires Stop hooks in the **main-repo context**. `hooks/scripts/session-cleanup.sh` then force-removes all `.worktrees/*` entries. The BUG-578 guard (`GIT_DIR != GIT_COMMON`) does not protect against this path because both vars resolve identically in the main-repo context. Fix: add a `.ll-session-<pid>` liveness check (already present in `commands/cleanup-worktrees.md`) before each `git worktree remove`.

## Steps to Reproduce

1. Run `ll-sprint run refined-ready` with at least 3 issues and `max_workers=2`.
2. Observe workers transition to `VALIDATING` and spawn `ll-ready-issue` Claude subprocesses.
3. ~2–3 minutes later, 3 workers die with `[Errno 2] No such file or directory: PosixPath('.worktrees/worker-...')`.
4. Check disk: those 3 worktrees are gone; workers that never completed validation (killed by Ctrl+C at <60s) still have their worktrees present.

## Current Behavior

Workers stuck in the VALIDATING phase for >~60s lose their worktrees. The throw site is `subprocess_utils.py:277` — `subprocess.Popen(..., cwd=working_dir)` — inside `run_claude_command`, after the `ll-ready-issue` subprocess has returned and the worker is about to continue. The error format `PosixPath('...')` in the `[Errno 2]` message is diagnostic of the `cwd=` kwarg being a `pathlib.Path` object pointing to a deleted directory.

## Expected Behavior

Worktrees must survive until their owning worker has completed (success or failure). No external component should delete a worktree that is registered in `WorkerPool._active_worktrees`.

## Motivation

Parallel sprint runs (`ll-sprint`) fail with >80% worker loss when any worker's `ll-ready-issue` validation takes longer than ~60 seconds. This blocks the sprint automation feature entirely and makes `ll-sprint` unreliable for multi-issue runs. The existing BUG-142 and BUG-578 guards are insufficient — a new, unidentified deletion path bypasses them.

## Root Cause

**Confirmed** (2026-05-24 investigation). The culprit is `session-cleanup.sh` — the same hook implicated in BUG-578 — but triggered via a different path that bypasses the BUG-578 fix.

### Mechanism (step by step)

1. `ll-sprint` creates `worker-enh-839-20260524-124401` and launches `claude -p "/ll:ready-issue ENH-839" --dangerously-skip-permissions --cwd <worktree_path>` (the validation subprocess).

2. The validation Claude session runs inside the worktree (~3 min) and then exits.

3. **Claude Code fires `Stop` hooks when the validation subprocess's session ends.** The hook runner uses the project root mapped to the *main repo*, not the worktree — because Claude Code resolves the project via `GIT_DIR` env var pointing to the worktree's admin dir, which traces back to the main repo's `.git`.

4. `hooks/scripts/session-cleanup.sh` runs. Its BUG-578 guard is:
   ```bash
   GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
   GIT_COMMON=$(git rev-parse --git-common-dir 2>/dev/null)
   if [ "$GIT_DIR" != "$GIT_COMMON" ]; then return 0; fi
   ```
   In main-repo context both resolve to `/path/to/.git` → `GIT_DIR == GIT_COMMON` → **guard does not fire** → cleanup proceeds and calls `git worktree remove --force` on all `.worktrees/*` entries.

5. ENH-839's worktree directory is deleted (Claude process has already exited, so git removes it cleanly). ENH-1114's worktree survives because its Claude process is still running and holds a git index lock, making `git worktree remove --force` fail silently (`|| true`).

6. 15 s later, the Python sprint runner attempts `subprocess.Popen(cmd_args, cwd=worktree_path)` for the implementation phase. Python 3.12 pre-checks `cwd` before forking. Directory is gone → `FileNotFoundError: [Errno 2] No such file or directory: PosixPath('...')`.

7. `_process_issue()`'s `except Exception as e` catches this, sets `error=str(e)`, and returns a failed `WorkerResult`.

### Why the BUG-578 guard failed

BUG-578's fix added `GIT_DIR != GIT_COMMON` to detect "running inside a worktree." It correctly skips cleanup when the Stop hook fires while Claude itself is *inside* a worktree. But it does **not** protect against the hook firing in the main-repo context *after* a worktree-hosted subprocess exits — the hook runner re-enters via the main repo path.

### Secondary defect

`session-cleanup.sh` has no per-worktree liveness check. `commands/cleanup-worktrees.md` checks `.ll-session-<pid>` markers before removing a worktree; `session-cleanup.sh` does not.

## Proposed Solution

**In `hooks/scripts/session-cleanup.sh`**, add a per-worktree `.ll-session-<pid>` liveness check (matching the logic already present in `commands/cleanup-worktrees.md`) before calling `git worktree remove`:

```bash
git worktree list 2>/dev/null | grep "$WORKTREE_PATTERN" 2>/dev/null | awk '{print $1}' | while read -r w; do
    if [ -n "$w" ]; then
        # Skip if owned by a running process
        MARKER=$(ls "${w}/.ll-session-"* 2>/dev/null | head -1)
        if [ -n "$MARKER" ]; then
            PID=$(basename "$MARKER" | sed 's/^\.ll-session-//')
            if kill -0 "$PID" 2>/dev/null; then
                continue  # live sprint — skip
            fi
        fi
        git worktree remove --force "$w" 2>/dev/null || true
    fi
done
```

The `GIT_DIR != GIT_COMMON` guard can be retained as a fast-path for processes inside a worktree, or removed (liveness checks are per-worktree and sufficient on their own).

## Integration Map

### Files to Modify

- `hooks/scripts/session-cleanup.sh` — add per-worktree `.ll-session-<pid>` liveness check before `git worktree remove` (lines ~35–43); model after `commands/cleanup-worktrees.md` liveness logic

### Dependent Files (Callers/Importers)

- `hooks/hooks.json` — references `hooks/scripts/session-cleanup.sh` as the `Stop` hook handler
- `commands/cleanup-worktrees.md` — already has liveness-check logic to mirror
- `scripts/little_loops/worktree_utils.py:97–100` — `setup_worktree()` writes `.ll-session-<pid>` into each new worktree; confirms markers are present before the fix triggers (PID is the ll-sprint orchestrator process, which stays alive for the entire sprint run)

### Similar Patterns

- `commands/cleanup-worktrees.md:132–141` — `.ll-session-<pid>` liveness-check loop, run mode (exact snippet to replicate in `session-cleanup.sh`); dry-run variant at lines 95–103
- `scripts/little_loops/parallel/worker_pool.py:605` — `_cleanup_worktree()` / `_active_worktrees` guard added for BUG-142 (Python-side equivalent; in-process only, not visible to the shell hook)
- `scripts/little_loops/parallel/orchestrator.py:248–268` — `_cleanup_orphaned_worktrees()`: Python analog using `os.kill(pid, 0)` + `item.glob(".ll-session-*")`
- `scripts/little_loops/fsm/concurrency.py:26–38` — `_process_alive()`: shared `os.kill(0)` helper with `errno.ESRCH` handling (reusable reference for EPERM edge case)
- `hooks/scripts/session-cleanup.sh:28–35` — `GIT_DIR != GIT_COMMON` guard (retain as fast-path or remove; actual line range is 28–35, not 31–35)

### Tests

- Manual: run `ll-sprint run refined-ready`; confirm no workers fail with `[Errno 2]` when validation takes >60 s.
- Manual: start a sprint, open a second Claude session in the same project, confirm its Stop hook does NOT remove active sprint worktrees.
- Manual: confirm orphaned worktrees (from interrupted runs with dead PIDs) are still cleaned up.
- Automated test pattern: model after `scripts/tests/test_orchestrator.py:434` (`test_skips_worktree_owned_by_live_process`) and `:462` (`test_removes_worktree_with_dead_process_marker`) for unit-testing the liveness-check logic in isolation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` — existing test `TestContextHandoffSentinel.test_sentinel_survives_session_cleanup()` directly invokes `session-cleanup.sh` as a subprocess (os.chdir + subprocess.run pattern); no update needed for this test since it has no `.worktrees/` dir, but this is the canonical template and class for new liveness-check shell tests
- `scripts/tests/test_hooks_integration.py` — **new test** `test_session_cleanup_skips_worktree_with_live_pid_marker`: create `.worktrees/worker-*/` with `.ll-session-<os.getpid()>`, run script, assert worktree dir NOT removed [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` — **new test** `test_session_cleanup_removes_worktree_with_dead_pid_marker`: create `.worktrees/worker-*/` with `.ll-session-99999` (guaranteed-dead PID), run script, assert dir removed [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` — **new test** `test_session_cleanup_removes_worktree_with_no_marker`: create `.worktrees/worker-*/` with no `.ll-session-*` file (orphan), run script, assert dir removed — preserves original hook behavior [Agent 3 finding]

### Documentation

- N/A

### Configuration

- N/A

## Implementation Steps

1. Read `hooks/scripts/session-cleanup.sh` lines 27–43 to confirm the current worktree-removal loop.
2. Read `commands/cleanup-worktrees.md` to extract the exact `.ll-session-<pid>` liveness-check snippet.
3. Insert the liveness check into `session-cleanup.sh` before `git worktree remove --force`.
4. Run `ll-sprint run refined-ready`; confirm all workers survive the VALIDATING phase.
5. Confirm orphaned worktrees (dead PIDs, no session marker) are still removed by the hook.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `TestSessionCleanupWorktrees` class to `scripts/tests/test_hooks_integration.py` with three new tests (live PID marker skipped, dead PID marker removed, no marker removed), following the `os.chdir(tmp_path)` + `subprocess.run` + git-init fixture pattern from `TestContextHandoffSentinel.test_sentinel_survives_session_cleanup()`.

## Impact

- **Priority**: P2 — Causes >80% failure rate in parallel sprint runs; blocks sprint automation entirely.
- **Effort**: Medium — Phase 1 is ~15 lines; Phase 2 scope depends on root cause.
- **Risk**: Low — Phase 1 is read-only telemetry; Phase 2 adds guards that only fire in the abnormal case.
- **Breaking Change**: No

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 277
- **Anchor**: `in function run_claude_command()`
- **Code**:
  ```python
  # Popen throw site — working_dir is a PosixPath that no longer exists
  process = subprocess.Popen(..., cwd=working_dir)
  ```

## Related Key Documentation

_No documents linked._

## Labels

`bug`, `parallel`, `worktrees`, `sprint`, `captured`

## Resolution

Added per-worktree `.ll-session-<pid>` liveness check to `hooks/scripts/session-cleanup.sh` before `git worktree remove --force`. The loop now skips any worktree whose marker PID responds to `kill -0`, matching the guard already present in `commands/cleanup-worktrees.md`. Added `TestSessionCleanupWorktrees` to `scripts/tests/test_hooks_integration.py` with three tests covering live-marker skip, dead-marker removal, and no-marker (orphan) removal.

## Status

**Done** | Created: 2026-05-24 | Completed: 2026-05-24 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-24T18:42:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cd1ea99-2823-484b-b85e-8f3b4510c87a.jsonl`
- `/ll:confidence-check` - 2026-05-24T20:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a81d6ad-24b7-4dad-bf14-3d71a58d887a.jsonl`
- `/ll:wire-issue` - 2026-05-24T18:38:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ad45c05-bad9-4ebc-b977-9b171de94333.jsonl`
- `/ll:refine-issue` - 2026-05-24T18:33:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35b81809-b274-4166-94fd-a3eed014891c.jsonl`
- `/ll:capture-issue` (root cause update from investigation plan) - 2026-05-24T19:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d101d16a-5b2a-4404-abe1-a8952f35ab27.jsonl`
- `/ll:format-issue` - 2026-05-24T18:14:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d101d16a-5b2a-4404-abe1-a8952f35ab27.jsonl`
- `/ll:capture-issue` - 2026-05-24T18:10:20Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a47fb14-5706-4306-941e-98961a5295b3.jsonl`

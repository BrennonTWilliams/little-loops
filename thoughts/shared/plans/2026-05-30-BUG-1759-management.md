# Implementation Plan: BUG-1759

## Summary
`ll-auto` does not forward `CONTEXT_HANDOFF` signals to the outer FSM loop. When the inner Claude session emits `CONTEXT_HANDOFF:`, `ll-auto` spawns internal continuation sessions transparently, blocking the outer FSM's `implement_current` action for hours. The fix forwards the signal to stdout and exits cleanly so the outer FSM's existing `HandoffHandler` pipeline handles the lifecycle.

## Decision
**Option 1 (stdout + exit 0)**, 10/12 score. Zero FSM schema/routing changes needed — existing `HANDOFF_SIGNAL` → `detect_first()` → `_pending_handoff` → `_handle_handoff()` pipeline handles everything downstream.

## Changes

### 1. `scripts/little_loops/issue_manager.py` — `run_with_continuation()`

**Add `issue_path` parameter** to enable pre-continuation guard.

**In the `detect_context_handoff(result.stdout)` block (line 251)**:
- Print `CONTEXT_HANDOFF:` to sys.stdout (signal forwarding)
- Pre-continuation guard: if `issue_path` is provided, parse frontmatter for `status`. If already `done` or `cancelled`, return success immediately (work is complete, no handoff needed)
- Otherwise, return cleanly with returncode 0 (signal already printed, outer FSM handles rest)
- Remove the internal continuation spawning logic (reading prompt, spawning `--resume` sessions)

**At call site (line 770)**: Pass `issue_path=info.path`.

### 2. `scripts/little_loops/parallel/worker_pool.py` — `_run_with_continuation()`

**In the `detect_context_handoff(result.stdout)` block (line 748)**:
- Same changes as issue_manager.py: print signal, pre-continuation guard using `working_dir` + `issue_id`, exit cleanly

### 3. Tests

Per issue test gaps:
1. **test_issue_manager.py**: Signal forwarding assertion — mock handoff output, assert signal in returned stdout
2. **test_issue_manager.py**: Pre-continuation guard — mock `status: done`, assert no continuation spawned
3. **test_fsm_executor.py**: FSM executor with `ll-auto` as action — mock subprocess returning handoff, assert `_pending_handoff` set
4. **test_worker_pool.py**: Worker pool signal mirror — mirror signal-forwarding assertion
5. **test_issue_manager.py**: Orphan process detection — test AutoManager warns about stale processes

## Phases
- [ ] Phase 0: Write Tests (Red) — TDD mode
- [ ] Phase 1: Implement signal forwarding in run_with_continuation()
- [ ] Phase 2: Mirror fix in worker_pool.py
- [ ] Phase 3: Make tests pass (Green)
- [ ] Phase 4: Verify (tests, lint, type check)
- [ ] Phase 5: Complete (update issue, commit)

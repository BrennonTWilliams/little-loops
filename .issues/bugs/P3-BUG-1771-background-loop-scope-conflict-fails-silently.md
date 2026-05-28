---
id: BUG-1771
title: Background loop scope conflict fails silently with no user feedback
type: BUG
status: done
priority: P3
captured_at: '2026-05-28T22:49:27Z'
completed_at: '2026-05-28T23:41:37Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
decision_needed: false
labels:
- bug
- ll-loop
- concurrency
- ux
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1771: Background loop scope conflict fails silently with no user feedback

## Summary

Running `ll-loop run rn-refine -b` prints "started in background" but the child process immediately dies due to a scope conflict with `deep-research-arxiv`. The parent returns exit code 0 and the user has no way to know why — `ll-loop status` and `ll-loop monitor` both report "no instances found."

## Current Behavior

1. **Parent process** creates the instance ID, writes the `.pid` file, spawns the child, prints "Loop started in background (PID: N)" — and returns 0.
2. **Child process** re-enters `cmd_run()` via `--foreground-internal`, then calls `lock_manager.acquire()` — which fails due to the scope conflict.
3. The child logs the error to the `.log` file and exits with code 1, **without ever creating a `.state.json` or `.lock` file**.
4. Because no `.state.json` exists, `_find_instances()` returns nothing — so `status` and `monitor` see "no instances."

The scope conflict check happens in the child, but the user-facing "started" message happens in the parent — so the parent confidently announces success before the child discovers the conflict.

## Expected Behavior

The user gets immediate, visible feedback on stderr before the child is spawned. No `.pid` or `.log` file is created for the failed attempt.

## Motivation

Silent failures waste user time debugging. When a background loop can't start, the user should know immediately and be told why, not left to discover it by digging through log files.

## Steps to Reproduce

1. Start a long-running loop in background: `ll-loop run deep-research-arxiv -b`
2. Try to start `rn-refine` in background while it's running: `ll-loop run rn-refine -b`
3. Observe: "Loop started in background" printed, but `ll-loop status` shows nothing
4. The only trace of the failure is in the `.log` file

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in function run_background()` (line ~912)
- **Cause**: Ordering issue — the parent spawns the child and reports success before the child performs the scope conflict check. The child fails silently because it has no channel back to the user.

The scope conflict check happens at line 271 of `run.py` inside the child process, after the parent has already returned 0.

## Proposed Solution

Perform a pre-flight scope conflict check in `run_background()` **before** spawning the child:

```python
# Pre-flight scope conflict check (before spawning)
lock_manager = LockManager(loops_dir)
scope = fsm.scope or ["."]
conflict = lock_manager.find_conflict(scope)
if conflict and not getattr(args, "queue", False):
    print(f"Scope conflict with running loop: {conflict.loop_name}", file=sys.stderr)
    print(f"  Conflicting scope: {conflict.scope}", file=sys.stderr)
    print("  Use --queue to wait for it to finish", file=sys.stderr)
    return 1
```

This needs access to `fsm.scope`, which requires loading the loop definition. The function already has `loop_name` and `loops_dir` — it just needs to call `load_loop(loop_name, loops_dir)`.

If acquisition fails and `--queue` IS set, proceed with spawn as normal (the child will handle the queue wait loop).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing pattern to mirror**: `cmd_run()` lines 262-324 in `run.py` — the exact scope-conflict check that needs to be duplicated into `run_background()`. Uses `LockManager(loops_dir)`, `fsm.scope or ["."]`, `lock_manager.find_conflict(scope)`, and the error reporting pattern `logger.error()` + `logger.info()` detail lines.
- **`load_loop()` already exists in `_helpers.py`** (line 816) — no new import needed. Returns `FSMLoop` with `.scope` attribute. Call pattern: `fsm = load_loop(loop_name, loops_dir, logger)` wrapped in `try/except (FileNotFoundError, ValueError)`.
- **Pre-flight validation precedent**: `cmd_run()` lines 235-242 already does mutually-exclusive flag checks (`--worktree` + `--background`, `--follow` + `--background`) before calling `run_background()` — same "validate before side effects" principle.
- **Stderr reporting**: Use `print(..., file=sys.stderr)` for the conflict summary and detail lines (adapted from `cmd_run()` lines 316-320 logger pattern; `run_background()` has no logger instance — the `load_loop()` call will need a local logger created for the pre-flight check).
- **Test pattern**: Mock `subprocess.Popen` (as in `TestRunBackground.test_spawns_detached_process`), use `capsys` fixture to capture stderr, assert exit code 1. `LockManager` test fixtures use `tmp_path` with a `.loops` subdirectory.
- **Broader impact**: `cmd_resume()` in `lifecycle.py` (line 371) has the same ordering gap — calls `run_background()` before `load_loop()`. Fixing `run_background()` covers both call sites.
- **Why `.pid` files don't help discovery**: `list_running_loops()` does check `.pid` files with `_process_alive()`, but `cmd_status()` and `cmd_monitor()` use `_find_instances()` which only globs `*.state.json`. Even if they used `list_running_loops()`, the child dies before the user can run `status`, so the PID is already dead.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()` (line 912): add pre-flight scope check before spawning child

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` line 271: scope check runs in child; still needed for foreground mode and `--queue` wait loop
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` line 371: calls `run_background()` before loading the loop (same ordering gap)
- `scripts/little_loops/fsm/concurrency.py` — `LockManager.find_conflict()` (line 154): used by pre-flight check; returns `ScopeLock | None`

### Key Imports Already Available in `_helpers.py`
- `load_loop()` (line 816): wraps `resolve_loop_path()` + `load_and_validate()`, returns `FSMLoop` with `.scope` attribute
- `LockManager` is importable from `little_loops.fsm.concurrency`
- `Logger` is importable from `little_loops.logger`

### Existing Test Files
- `scripts/tests/test_cli_loop_background.py` — `TestRunBackground` class (line 137): existing tests mock `subprocess.Popen` and capture stdout via `capsys`; new test should also capture stderr
- `scripts/tests/test_concurrency.py` — `TestLockManager` class (line 60): `find_conflict()` test patterns with `tmp_path` fixtures

### Historical Related Bugs (Prior Art)
- `P2-BUG-1359` — outer-loop eval scope conflict prevents sub-loop execution
- `P2-BUG-525` — TOCTOU race condition in lock acquisition
- `P2-BUG-232` — earlier TOCTOU race in scope lock acquisition

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — user-facing loop guide with background/concurrency sections
- `docs/reference/CLI.md` — `ll-loop run -b` / `ll-loop status` / `ll-loop monitor` reference

### Configuration
- N/A

## Implementation Steps

1. In `run_background()` (`_helpers.py` line 912), before `_make_instance_id()` (line 930) but after `running_dir` setup (line 928), add:
   - Create a local `Logger` instance: `logger = Logger.get(__name__)` or equivalent
   - `fsm = load_loop(loop_name, loops_dir, logger)` wrapped in try/except (follow pattern from `lifecycle.py:cmd_resume()` line 430)
   - `lock_manager = LockManager(loops_dir)` (follow pattern from `run.py:cmd_run()` line 263)
   - `scope = fsm.scope or ["."]` (follow pattern from `run.py:cmd_run()` line 264)
   - `conflict = lock_manager.find_conflict(scope)` (read-only check, no lock file written)
2. If conflict found and `--queue` not set: report via `print(..., file=sys.stderr)` (no logger in `run_background()`), return 1
3. If conflict found and `--queue` IS set: proceed with spawn (child handles queue wait loop)
4. If no conflict: proceed with existing spawn logic unchanged
5. Add test in `test_cli_loop_background.py` → `TestRunBackground`: mock `Popen`, pre-acquire a conflicting lock via `LockManager`, call `run_background()`, assert exit code 1, assert stderr contains conflict message (follow `capsys` pattern from `test_prints_confirmation` at line 373)
6. Verify `--queue` still works: pre-acquire conflicting lock, call with `queue=True`, assert `Popen` IS called (proceed to spawn)
7. Run existing tests: `python -m pytest scripts/tests/test_cli_loop_background.py scripts/tests/test_concurrency.py -v`

## Impact

- **Priority**: P3 — UX/debugging pain point with workaround (check log file), no data loss
- **Effort**: Small — single function change, ~15 lines of code
- **Risk**: Low — read-only check before spawn, no change to child process behavior
- **Breaking Change**: No

## Related Key Documentation

- [API Reference](../docs/reference/API.md) — LockManager and FSM concurrency docs

## Session Log
- `/ll:ready-issue` - 2026-05-28T23:31:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dca5f423-069e-45b7-9c52-c9b45e034276.jsonl`
- `/ll:refine-issue` - 2026-05-28T22:58:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ef33930-afbc-4fc6-97f3-3dddef828d29.jsonl`
- `/ll:format-issue` - 2026-05-28T22:52:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd427990-f2e8-4af5-a088-fc75387df617.jsonl`
- `/ll:capture-issue` - 2026-05-28T22:49:27Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/694fe427-3cbd-4daa-82f6-275b1a9363d0.jsonl`
- `/ll:confidence-check` - 2026-05-28T23:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5894230-faa5-424a-9205-9417a3ec5259.jsonl`
- `/ll:manage-issue` - 2026-05-28T23:41:37Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/<current>.jsonl`

## Resolution

**Completed**: 2026-05-28

### Changes Made

1. **`scripts/little_loops/cli/loop/_helpers.py`**:
   - Added `LockManager` to imports from `little_loops.fsm.concurrency`
   - Added pre-flight scope conflict check in `run_background()` before spawning child process
   - Loads loop definition, checks for scope conflicts, prints to stderr and returns 1 on conflict
   - `--queue` flag bypasses the pre-flight check (child handles queue wait loop)

2. **`scripts/tests/test_cli_loop_background.py`**:
   - Added `autouse` fixture to `TestRunBackground` and `TestRunBackgroundInstanceIdForwarding` creating minimal loop YAML
   - Changed all `loops_dir.mkdir()` to `loops_dir.mkdir(parents=True, exist_ok=True)` for fixture compatibility
   - Added `test_scope_conflict_returns_1`: verifies conflict detection returns 1, prints to stderr, doesn't spawn
   - Added `test_queue_bypasses_preflight_check`: verifies `--queue` bypasses pre-flight check and spawns

### Root Cause

`run_background()` spawned the child process and reported success before the child performed the scope conflict check. The child failed silently because it had no channel back to the user.

### Fix

Performed a read-only `find_conflict()` check in the parent process before spawning the child, matching the error reporting pattern from `cmd_run()` in `run.py`.

---

**Open** | Created: 2026-05-28 | Priority: P3

---
captured_at: '2026-05-03T18:44:03Z'
completed_at: '2026-05-04T00:08:08Z'
discovered_date: '2026-05-03'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1353: `ll-loop stop` refuses to act on `interrupted` loops with a live lock-file PID

## Summary

`ll-loop stop <name>` exits with an error when the loop's state file has `status: interrupted`, even if the `.lock` file holds a live PID that is actively blocking scope acquisition. The command gates on `state.status != "running"` before ever inspecting the lock file, leaving no CLI path to kill an orphaned lock-holder other than `kill` + `rm` by hand.

## Current Behavior

```
$ ll-loop stop autodev
[13:37:25] Loop not running: autodev (status: interrupted)
# exit code 1
```

This occurs even when `.loops/.running/autodev.lock` contains a live PID (e.g. 58522), verified alive via `kill -0 58522`. The orphaned process holds the scope and blocks all subsequent `ll-loop run` invocations on that directory.

## Expected Behavior

`ll-loop stop` should check the `.lock` file for a live PID **regardless of `state.status`**. If the lock file exists and its PID is alive, it should:

1. SIGTERM the process (with SIGKILL fallback after 10s, matching the existing alive-PID path)
2. Remove the `.lock` file
3. Report success — not error

This resolves scope conflicts without requiring users to manually `kill` and `rm`.

## Motivation

The only symptom of a zombie lock-holder is the scope conflict error on the next `ll-loop run`. The natural recovery action is `ll-loop stop` — but it fails silently with a misleading message. Users must inspect `.lock` files manually, identify the PID, kill it, and delete the file, turning a recoverable CLI error into a multi-step system investigation. `cleanup-loops` skill also cannot invoke `ll-loop stop` to fix this class of issue.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `cmd_stop()` (line ~220)
- **Cause**: `if state.status != "running": return 1` short-circuits before the lock-file check. The `.pid` file path is only reached after that gate. The `.lock` file is never read at all inside `cmd_stop()`.

The `LockManager` (in `concurrency.py`) manages `.lock` files independently of `StatePersistence`. A loop's state can transition to `interrupted` while the wrapper process (which holds the lock) is still alive. This is the normal completion/interruption path for foreground runs — the process writes the final state then exits, but a race or crash can leave the lock unreleased.

## Steps to Reproduce

1. Start `ll-loop run autodev ENH-1341 -v` (foreground)
2. Let it complete normally — state becomes `interrupted`, wrapper PID still alive (orphaned)
3. Run `ll-loop stop autodev`
4. Observe: `Loop not running: autodev (status: interrupted)` — exit code 1
5. Run `ll-loop run autodev ENH-1340 -v`
6. Observe: `Scope conflict with running loop: autodev` — blocked

## Error Messages

```
[13:37:25] Loop not running: autodev (status: interrupted)
```

## Proposed Solution

In `cmd_stop()`, add a secondary check on the `.lock` file **before** returning the "not running" error:

```python
# In lifecycle.py: cmd_stop()
if state.status != "running":
    # Secondary check: orphaned lock file with live PID can block scope even if
    # state is not "running". Kill the lock holder and release the scope.
    running_dir = loops_dir / ".running"
    lock_file = running_dir / f"{loop_name}.lock"
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text())
            lock_pid = lock_data.get("pid")
        except (OSError, json.JSONDecodeError):
            lock_pid = None
        if lock_pid and _process_alive(lock_pid):
            logger.warning(
                f"Loop state is '{state.status}' but lock file holds live PID {lock_pid}. "
                "Killing orphaned lock holder..."
            )
            _kill_with_timeout(lock_pid, logger)  # existing helper
            lock_file.unlink(missing_ok=True)
            logger.success(f"Released orphaned scope lock for {loop_name}")
            return 0
    logger.error(f"Loop not running: {loop_name} (status: {state.status})")
    return 1
```

Extract the kill-with-timeout logic from the existing alive-PID path into a shared helper `_kill_with_timeout(pid, logger)` to avoid duplication.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction: `_kill_with_timeout` does not yet exist.** The pseudo-code above references it as if it were an existing helper, but no such function exists anywhere in the codebase. The equivalent logic lives **inline** in `cmd_stop()` at `lifecycle.py:249–266`. Step 1 must create it before it can be called.

**Correction: lock file path must use `stem`, not `loop_name`.** The codebase uses `stem = instance_id or loop_name` throughout lifecycle.py for all per-instance file paths (`.pid`, `.lock`). The secondary check must be placed inside the `for instance_id, state in instances:` loop (wrapping the early return), using `running_dir / f"{stem}.lock"`.

**Correction: preferred lock file read pattern.** All three existing call sites in `_status_single()` use:
```python
with open(lock_file_path) as _lf:
    lock_data = json.load(_lf)
pid = lock_data.get("pid")
# exception tuple: (json.JSONDecodeError, KeyError, OSError)
```
Prefer this over `json.loads(lock_file.read_text())` for consistency.

**Note on `LockManager.release()` (Step 3).** `LockManager` is not currently imported in `lifecycle.py`. Its `release()` method body is a single `lock_file.unlink(missing_ok=True)` call — adding an import solely for that is unnecessary. Use `lock_file.unlink(missing_ok=True)` directly, matching how `_status_single()` handles cleanup.

**`loops_dir` and `running_dir` are already in scope** at the gate point — `running_dir = loops_dir / ".running"` is assigned at the top of `cmd_stop()`. No variable lookups needed.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()`: add orphaned-lock-holder path before the "not running" early return

### Dependent Files (Callers/Importers)
- `skills/cleanup-loops/SKILL.md` — calls `ll-loop stop` for stuck-running loops; this fix enables it to handle interrupted-with-live-lock as well
- `scripts/little_loops/fsm/concurrency.py` — `LockManager`: defines `.lock` file format and `release()` (alternative to `unlink` in the fix)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — single production caller; dispatches to `cmd_stop()` in `main_loop()` at line ~388; signature unchanged, no modification needed [Agent 1 finding]

### Similar Patterns
- `cmd_status()` has a parallel gap — see BUG-1352; fixing both together is natural
- Lock file read pattern (canonical): `lifecycle.py:63–73` in `_status_single()` — use `with open / json.load / (json.JSONDecodeError, KeyError, OSError)` exception tuple
- Inline kill pattern to extract: `lifecycle.py:249–266` in `cmd_stop()` — SIGTERM → 10×1s poll → SIGKILL with `OSError` guard
- Test fixture pattern for lock file: `test_cli_loop_lifecycle.py:1045–1074` (`TestCmdStatusLockFilePid.test_status_json_reads_pid_from_lock_file`) — writes `{"loop_name": ..., "scope": [...], "pid": 12345, "started_at": "..."}` to `running_dir/test-loop.lock`

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: `cmd_stop` on interrupted loop with live lock-file PID kills process and removes lock
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: `cmd_stop` on interrupted loop with dead lock-file PID removes stale lock, exits 0
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: `cmd_stop` on interrupted loop with no lock file still returns error (unchanged behavior)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_state.py` — `test_stop_interrupted_loop_returns_error` (line 167): test will still pass (no `.lock` file written), but docstring says "stop returns error if loop already interrupted" — update docstring to "returns error if interrupted and no lock file" to keep intent accurate post-fix [Agent 3 finding]

### Documentation
- `skills/cleanup-loops/SKILL.md` — Step 6 could mention that `ll-loop stop` now handles interrupted-with-live-lock; update post-fix

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `/ll:cleanup-loops` command entry states that `stale-interrupted` loops use `rm` (not `ll-loop stop`); after fix, the live-PID variant of that category becomes a `ll-loop stop` case — update the entry description [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Extract kill logic from existing alive-PID branch into `_kill_with_timeout(pid, logger)` helper
   - Source: inline at `lifecycle.py:249–266` (SIGTERM → poll `_process_alive()` × 10 × 1s → SIGKILL, swallow `OSError`)
2. Add orphaned-lock-holder check in `cmd_stop()` before the "not running" early return
   - Gate is at `lifecycle.py:~237`; the check must be placed inside the `for instance_id, state in instances:` loop using `stem = instance_id or loop_name`
   - Read lock file with `with open(lock_file_path) as _lf: json.load(_lf)`, catching `(json.JSONDecodeError, KeyError, OSError)` — mirrors `_status_single()` at `lifecycle.py:63–73`
   - On success: call `_kill_with_timeout(lock_pid, logger)`, then `lock_file.unlink(missing_ok=True)`, log success, `return 0`
3. ~~Use `LockManager.release()` instead of manual `unlink`~~ — use `lock_file.unlink(missing_ok=True)` directly; `LockManager` is not imported in `lifecycle.py` and its `release()` body is just `unlink`
4. Add tests in `TestCmdStop` class (`test_cli_loop_lifecycle.py`) following pattern from `TestCmdStatusLockFilePid` (line 1025):
   - `test_stop_interrupted_with_live_lock_pid_kills_process_and_removes_lock`
   - `test_stop_interrupted_with_dead_lock_pid_removes_stale_lock_exits_0`
   - `test_stop_interrupted_with_no_lock_file_returns_error` (unchanged behavior)
5. Update `cleanup-loops` skill SKILL.md to note that interrupted loops with live PIDs can now be stopped via CLI

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_ll_loop_state.py` — narrow docstring of `test_stop_interrupted_loop_returns_error` (line 167) to "returns error if interrupted and no lock file" so intent remains accurate after fix adds the orphaned-lock success path
7. Update `docs/reference/COMMANDS.md` — revise `/ll:cleanup-loops` command entry description to reflect that `stale-interrupted` + live-lock-PID is now handled via `ll-loop stop` (not manual `rm`)
8. Scope of Step 5 (`cleanup-loops` SKILL.md) is broader than "add a note": Step 3's `stale-interrupted` routing (currently sends all cases to `rm -f`) must distinguish live-PID (→ `ll-loop stop`) vs. dead-PID (→ `rm`); Step 6's action branch for `stuck-running` should document that `interrupted`+live-lock is also handled by `ll-loop stop`

## Impact

- **Priority**: P2 — no CLI recovery path for a common stuck-loop scenario; requires manual system commands
- **Effort**: Small — ~20-line change; logic mirrors the existing alive-PID path
- **Risk**: Low — new code path only activates when state is non-running AND a live lock PID exists; existing behavior unchanged for clean interrupted loops
- **Breaking Change**: No (expands stop command to handle more cases; existing success/error semantics preserved)

## Related Key Documentation

- `docs/reference/CLI.md` — documents `ll-loop stop` command flags and behavior
- `docs/guides/LOOPS_GUIDE.md` — user guide for loop execution, monitoring, and recovery; mentions PID storage locations
- `docs/ARCHITECTURE.md` — system design including loop concurrency model
- `docs/development/TROUBLESHOOTING.md` — stuck loop troubleshooting; post-fix update may be useful

## Resolution

**Status**: Resolved

**Changes**:
- `scripts/little_loops/cli/loop/lifecycle.py`: Extracted `_kill_with_timeout(pid, label, logger)` helper from the inline kill logic in `cmd_stop()`. Added orphaned-lock-holder check before the "not running" early return — when state is not "running" but a `.lock` file exists with a live PID, kills the orphaned process and removes the lock (returning 0). Also handles the stale dead-PID case: removes the lock file and returns 0.
- `scripts/tests/test_cli_loop_lifecycle.py`: Added 3 tests to `TestCmdStop`: live lock PID killed and lock removed, dead lock PID stale lock removed, no lock file still errors.
- `scripts/tests/test_ll_loop_state.py`: Updated docstring of `test_stop_interrupted_loop_returns_error` to "returns error if interrupted and no lock file".
- `skills/cleanup-loops/SKILL.md`: Updated Step 6 stale-interrupted routing — `pid_source == "lock_file"` with live PID now routes through `ll-loop stop` rather than `rm`.
- `docs/reference/COMMANDS.md`: Updated `/ll:cleanup-loops` description to reflect the new live-PID routing.

## Labels

`bug`, `ll-loop`, `concurrency`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-05-03T23:56:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3086669d-6eed-430e-823c-8cef4c6f73c2.jsonl`
- `/ll:confidence-check` - 2026-05-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3beee65a-d21d-43ad-abd0-d2ce469a08bb.jsonl`
- `/ll:wire-issue` - 2026-05-03T23:52:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/846a8184-3664-47bd-a47f-ce007070c81f.jsonl`
- `/ll:refine-issue` - 2026-05-03T23:48:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b8a2d402-93dd-42a9-8ac5-46952e85b43a.jsonl`
- `/ll:format-issue` - 2026-05-03T21:54:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0105a40-4f11-453e-842b-a9855e8ac301.jsonl`

- `/ll:manage-issue` - 2026-05-04T00:08:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

- `/ll:capture-issue` - 2026-05-03T18:44:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d6eb746-1937-4f45-bb7f-14d33480c49e.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2

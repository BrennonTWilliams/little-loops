---
captured_at: "2026-05-03T18:44:03Z"
discovered_date: "2026-05-03"
discovered_by: capture-issue
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
- **Anchor**: `cmd_stop()` (line ~138)
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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()`: add orphaned-lock-holder path before the "not running" early return

### Dependent Files (Callers/Importers)
- `skills/cleanup-loops/SKILL.md` — calls `ll-loop stop` for stuck-running loops; this fix enables it to handle interrupted-with-live-lock as well
- `scripts/little_loops/fsm/concurrency.py` — `LockManager`: defines `.lock` file format and `release()` (alternative to `unlink` in the fix)

### Similar Patterns
- `cmd_status()` has a parallel gap — see BUG-1352; fixing both together is natural

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: `cmd_stop` on interrupted loop with live lock-file PID kills process and removes lock
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: `cmd_stop` on interrupted loop with dead lock-file PID removes stale lock, exits 0
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: `cmd_stop` on interrupted loop with no lock file still returns error (unchanged behavior)

### Documentation
- `skills/cleanup-loops/SKILL.md` — Step 6 could mention that `ll-loop stop` now handles interrupted-with-live-lock; update post-fix

### Configuration
- N/A

## Implementation Steps

1. Extract kill logic from existing alive-PID branch into `_kill_with_timeout(pid, logger)` helper
2. Add orphaned-lock-holder check in `cmd_stop()` before the "not running" early return
3. Use `LockManager.release()` instead of manual `unlink` to keep lock management centralized
4. Add tests covering: live lock PID killed, dead lock PID cleaned, no lock file (unchanged error)
5. Update `cleanup-loops` skill SKILL.md to note that interrupted loops with live PIDs can now be stopped via CLI

## Impact

- **Priority**: P2 — no CLI recovery path for a common stuck-loop scenario; requires manual system commands
- **Effort**: Small — ~20-line change; logic mirrors the existing alive-PID path
- **Risk**: Low — new code path only activates when state is non-running AND a live lock PID exists; existing behavior unchanged for clean interrupted loops
- **Breaking Change**: No (expands stop command to handle more cases; existing success/error semantics preserved)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `concurrency`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-05-03T18:44:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d6eb746-1937-4f45-bb7f-14d33480c49e.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2

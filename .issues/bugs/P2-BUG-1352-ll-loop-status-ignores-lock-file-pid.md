---
captured_at: "2026-05-03T18:44:03Z"
discovered_date: "2026-05-03"
discovered_by: capture-issue
---

# BUG-1352: `ll-loop status` ignores `.lock` file PID, reports `null`

## Summary

`ll-loop status <name> --json` returns `"pid": null` even when a `.lock` file exists with a live PID holding the scope. The command reads only from a `.pid` file (used for background-mode tracking), never from the `.lock` file managed by `LockManager`. This causes `cleanup-loops` to misclassify scope-holding zombie processes as clean interrupted loops, masking the real blocker.

## Current Behavior

Running `ll-loop status autodev --json` on a loop whose state is `interrupted` but whose `.lock` file holds a live orphaned PID (e.g. 58522) returns:

```json
{ "status": "interrupted", "pid": null, ... }
```

The `cleanup-loops` skill reads `pid: null`, skips the stale-interrupted cleanup path (which requires `pid` non-null), and reports the loop as needing no action. Attempting `ll-loop run` on the same scope then fails with `Scope conflict with running loop: autodev`.

## Expected Behavior

`ll-loop status` should check both the `.pid` file **and** the `.lock` file. If a `.lock` file exists and its PID is alive, `pid` should be populated from the lock file. If the lock-file PID is dead, it should be treated as a stale lock (reported as such or cleaned up). The `cleanup-loops` skill can then detect and surface the orphaned lock process.

## Motivation

`cleanup-loops` is the primary diagnostic tool for unblocking stuck loops. Its effectiveness depends on `ll-loop status` accurately surfacing the PID. A loop stuck in scope conflict (blocking all new runs on the same directory) appears clean in the output, requiring manual inspection of `.lock` files to diagnose. This turns a 5-second fix into a multi-minute investigation.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `cmd_status()` (line ~64)
- **Cause**: `pid = _read_pid_file(pid_file)` reads exclusively from `<loop_name>.pid`. Foreground runs and queue-acquired locks are written to `<loop_name>.lock` by `LockManager.acquire()` in `concurrency.py`. The status command never opens the `.lock` file.

The `.lock` file lives at `.loops/.running/<name>.lock` and contains `{"pid": <int>, "scope": [...], ...}`. The `.pid` file is only written when `--foreground-internal` is passed (background subprocess mode). Foreground runs hold the scope via `.lock` only — so `pid` is always null for foreground-run loops.

## Steps to Reproduce

1. Run `ll-loop run autodev ENH-1341 -v` (foreground, no `--background`)
2. Interrupt or let it complete with status `interrupted`
3. Verify `.loops/.running/autodev.lock` exists and its PID is alive: `kill -0 <pid> && echo alive`
4. Run `ll-loop status autodev --json`
5. Observe `"pid": null` despite the live lock-file PID

## Error Messages

```
# From ll-loop run ENH-1340 after the above:
[13:37:05] Scope conflict with running loop: autodev
[13:37:05]   Conflicting scope: ['/Users/.../little-loops']
[13:37:05]   Use --queue to wait for it to finish
```

## Proposed Solution

In `cmd_status()`, after reading the `.pid` file, fall back to reading the `.lock` file if `pid` is None:

```python
# In lifecycle.py: cmd_status()
running_dir = loops_dir / ".running"
pid_file = running_dir / f"{loop_name}.pid"
pid = _read_pid_file(pid_file)

# Fall back to lock file PID if no .pid file
if pid is None:
    lock_file = running_dir / f"{loop_name}.lock"
    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text())
            pid = lock_data.get("pid")
        except (OSError, json.JSONDecodeError):
            pass
```

This makes `pid` non-null for foreground-run loops still holding their scope lock, allowing `cleanup-loops` to detect and clean them.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status()`: add lock-file PID fallback

### Dependent Files (Callers/Importers)
- `skills/cleanup-loops/SKILL.md` — reads `pid` from `ll-loop status --json`; benefits automatically once fixed
- `scripts/little_loops/fsm/concurrency.py` — `LockManager`: source of truth for `.lock` file format

### Similar Patterns
- `cmd_stop()` in `lifecycle.py` also reads only from `.pid` file — see BUG-1353

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — add test: status of foreground-interrupted loop shows lock-file PID
- `scripts/tests/test_ll_loop_commands.py` — add scenario with live lock-file PID and no `.pid` file

### Documentation
- `skills/cleanup-loops/SKILL.md` — Step 2 assumes `pid` from status reflects all live PIDs; no doc change needed once code is fixed

### Configuration
- N/A

## Implementation Steps

1. Read lock-file format from `LockManager.acquire()` in `concurrency.py` to confirm JSON shape
2. Add lock-file PID fallback in `cmd_status()` with try/except for malformed files
3. Add a `pid_source` field to JSON output (`"pid_file"` or `"lock_file"`) so callers can distinguish
4. Add/update tests in `test_cli_loop_lifecycle.py` covering foreground-run lock-only scenario
5. Verify `cleanup-loops` skill correctly classifies the loop after the fix

## Impact

- **Priority**: P2 — blocks new loop runs silently; `cleanup-loops` gives false "no action needed"
- **Effort**: Small — surgical addition of ~10 lines in `cmd_status()`; lock-file format already defined
- **Risk**: Low — read-only change to status output; no state mutation
- **Breaking Change**: No (adds `pid` data where it was previously null)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `concurrency`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-03T21:54:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0105a40-4f11-453e-842b-a9855e8ac301.jsonl`

- `/ll:capture-issue` - 2026-05-03T18:44:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d6eb746-1937-4f45-bb7f-14d33480c49e.jsonl`

---

**Open** | Created: 2026-05-03 | Priority: P2

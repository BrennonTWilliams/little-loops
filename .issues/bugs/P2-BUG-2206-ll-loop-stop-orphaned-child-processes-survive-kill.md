---
discovered_date: 2026-06-14T00:00:00Z
discovered_by: manual-observation
confidence_score: 99
outcome_confidence: 99
status: done
completed_at: 2026-06-14T00:00:00Z
labels: [loop, process-management, cli]
---

# BUG-2147: `ll-loop stop` Leaves Orphaned Child Processes Alive

## Summary

`ll-loop stop` sent SIGTERM/SIGKILL to the wrapper process PID only. Child
processes launched with `start_new_session=True` (the `claude` CLI and its
grandchildren like `claude agent-desktop`) survived in their own process group
and had to be killed manually.

## Symptom

```
ll-loop stop qa-pipeline
[18:01:35] Sent SIGKILL to qa-pipeline-20260614T175106 (PID: 89092)
[18:01:35] Stopped qa-pipeline-20260614T175106 (PID: 89092)
```

But `claude agent-desktop` (PID 77210) continued running. Required manual
`kill -9` to stop.

## Root Cause

Three factors combined:

1. **`_kill_with_timeout` targeted a single PID** —
   `scripts/little_loops/cli/loop/lifecycle.py:87-98` sent signals to exactly
   one PID with no process group kill or child traversal.

2. **`start_new_session=True` isolates the `claude` subprocess** —
   `scripts/little_loops/subprocess_utils.py:339` makes the `claude` process
   a new session leader in its own process group (PG2), isolated from the
   wrapper's group (PG1). `os.killpg` on PG1 misses PG2 entirely.

3. **`_kill_process_group` existed but was never called from the stop path** —
   `scripts/little_loops/subprocess_utils.py:256-266` correctly kills an
   entire process group, but was only reachable from internal timeout handling
   inside `run_claude_command`, not from `cmd_stop`.

Process tree:
```
Wrapper (PG1, PID 89092)              ← killed by ll-loop stop
  └─ claude -p ... (PG2, leader)      ← SURVIVED: different PG
       └─ claude agent-desktop (PG2)   ← SURVIVED: orphaned grandchild
```

## Fix

Replaced `_kill_with_timeout` in
`scripts/little_loops/cli/loop/lifecycle.py` with a two-function solution:

- **`_get_descendant_pids(pid)`** — recursively walks the full process tree
  using `pgrep -P`, which follows parent-PID relationships and crosses process
  group boundaries. Returns all descendant PIDs.
- **Updated `_kill_with_timeout(pid, label, logger)`** — collects all
  descendants, sends SIGTERM to descendants first then root (so the root
  cannot respawn children after receiving SIGTERM), waits up to 10 s, then
  sends SIGKILL to any survivors.

No other files were changed. `_kill_process_group` in `subprocess_utils.py`
and the signal handler in `_helpers.py` are unchanged.

## Files Changed

| File | Change |
|------|--------|
| `scripts/little_loops/cli/loop/lifecycle.py` | Added `_get_descendant_pids`; replaced `_kill_with_timeout` with recursive tree kill |

## Verification

All 5312 existing tests pass. Manual verification per the root cause doc:
start a loop with a long-lived subprocess, run `ll-loop stop`, confirm no
orphaned processes remain via `ps aux | grep <process>`.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-14T23:18:27 - `3c5b779f-18a6-461c-bff9-2000b46446bd.jsonl`

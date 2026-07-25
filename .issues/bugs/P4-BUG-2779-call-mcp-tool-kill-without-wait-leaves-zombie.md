---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
relates_to: [BUG-2778]
---

# BUG-2779: `call_mcp_tool` cleanup issues `kill()` without a follow-up `wait()`, leaving a zombie process

## Summary

In `call_mcp_tool`'s `finally` block, if graceful termination times out,
`proc.wait(timeout=5)` raises `subprocess.TimeoutExpired`, the handler calls
`proc.kill()` — but never reaps the killed child with a follow-up `wait()`.
The child stays a `<defunct>` zombie until interpreter shutdown.

## Location

- **File**: `scripts/little_loops/mcp_call.py`
- **Line(s)**: 306-312 (at scan commit: fb567390)
- **Anchor**: `in function call_mcp_tool(), finally block`
- **Code**:
```python
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        stderr_thread.join(timeout=5)
```

## Current Behavior

A server that ignores SIGTERM for >5s gets SIGKILLed but is never reaped;
`ps` shows a defunct entry until the parent Python process exits.

## Expected Behavior

After `proc.kill()`, a bounded `proc.wait(timeout=...)` reaps the child so no
zombie remains.

## Steps to Reproduce

1. Point `call_mcp_tool` at a server command with a SIGTERM handler that
   sleeps >5 seconds.
2. After the call returns, run `ps` — the killed process shows as
   `<defunct>` until the parent exits.

## Proposed Solution

```python
        except Exception:
            proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
```

## Impact

- **Severity**: Low — cosmetic in short-lived CLI calls, but long-running
  loop processes (`ll-loop`, `ll-auto`) accumulate zombies across repeated
  MCP failures.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`

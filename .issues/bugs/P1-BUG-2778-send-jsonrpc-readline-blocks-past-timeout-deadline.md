---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
relates_to: [BUG-2779]
---

# BUG-2778: `_send_jsonrpc` deadline does not bound blocking `readline()`; unresponsive MCP server hangs `call_mcp_tool` indefinitely

## Summary

`mcp_call._send_jsonrpc` documents a hard transport-timeout contract (exit
code 124), but its deadline check `while time.monotonic() < deadline:` only
runs *between* calls to `proc.stdout.readline()`. `readline()` itself is a
plain blocking pipe read with no timeout, so a live-but-silent MCP server
blocks the call past the deadline — potentially forever. The
`proc.stdout.readable()` call on the preceding line is a no-op check, not a
wait-with-timeout.

## Location

- **File**: `scripts/little_loops/mcp_call.py`
- **Line(s)**: 93-114 (at scan commit: fb567390)
- **Anchor**: `in function _send_jsonrpc()`
- **Code**:
```python
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc.stdout.readable()
        try:
            response_line = proc.stdout.readline()
        except (OSError, ValueError):
            break
```

## Current Behavior

If the spawned MCP server process is alive but never writes another line to
stdout (hangs, deadlocks, or responds slower than `timeout`), `readline()`
blocks indefinitely instead of returning after `timeout` seconds with the
documented `(isError: True, ...), 124` result.

## Expected Behavior

Each read is bounded by the remaining deadline (e.g. `select.select()` on the
pipe fd with the remaining time, or a reader thread + `queue.get(timeout=...)`),
so `call_mcp_tool(..., timeout=N)` returns the exit-124 timeout result no more
than ~N seconds after the call.

## Steps to Reproduce

1. Configure a `.mcp.json` server command that starts but never responds to
   `initialize` (e.g. a script that reads stdin then sleeps forever without
   writing stdout).
2. Call `call_mcp_tool(server, tool, {}, timeout=5)`.
3. The call blocks well past 5 seconds (until the process is killed
   externally) instead of returning the documented timeout result.

## Proposed Solution

Use `select.select([proc.stdout], [], [], remaining)` before each `readline()`
(POSIX pipes; this project targets darwin/linux hosts), breaking to the
timeout path when `select` returns empty. Alternatively drain stdout on a
daemon thread into a `queue.Queue` and `get(timeout=remaining)`.

## Impact

- **Severity**: High
- Any FSM `mcp_result`-evaluated state or `ll-action --runner mcp` call can
  wedge an entire automation loop on one bad server, defeating the
  transport-level timeout contract callers rely on.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`

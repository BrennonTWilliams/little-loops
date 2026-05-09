---
captured_at: "2026-05-09T19:39:32Z"
discovered_date: 2026-05-09
discovered_by: capture-issue
---

# BUG-1388: UnixSocketTransport skips initial state seed on client connect

## Summary

When a new client connects to the Unix socket (`events.sock`), `UnixSocketTransport` does not send current FSM state. The client only receives events from future state transitions, so any loop that is mid-execution with no imminent transition appears invisible to the new subscriber.

## Root Cause

`transport.py` — `UnixSocketTransport._accept_loop` (line ~163): after accepting a connection and appending the `_SocketClient` to `self._clients`, it starts the client drain thread and returns. No seed payload is sent. Compare to `FallbackTransport.connect()`, which reads all `.loops/.running/*.state.json` files and emits `state_change` events for each before registering the subscriber.

## Observed Behavior

- `ll-loop run auto-refine-and-implement` is running (PID active, `.state.json` exists, REST API `/api/project/loop-viz/running` returns 64 entries including it)
- Opening the loop-viz dashboard while the loop is in a long-running `implement_issue` action (no imminent state transition) shows **0 FSM loops running**
- The SSE stream at `/api/project/loop-viz/events/stream` returns only `retry: 1000` — no state events — confirming the socket client received nothing on connect

## Expected Behavior

A new socket subscriber should immediately receive `state_change` events for all currently running loops, matching the behavior of `FallbackTransport`.

## Proposed Fix

Add an `on_connect` callback parameter to `UnixSocketTransport.__init__`. When `_accept_loop` admits a new client (after appending to `self._clients`), call `on_connect(client)` if set. In `wire_transports`, supply a callback that reads `.loops/.running/*.state.json` and enqueues a `state_change` event to the specific new client's queue.

This keeps the transport layer generic (no filesystem knowledge baked in) and lets `wire_transports` own the seeding logic alongside the rest of the transport wiring.

## Affected Files

- `scripts/little_loops/transport.py` — `UnixSocketTransport._accept_loop`, `wire_transports`
- `scripts/tests/test_transport.py` — add test for on-connect seeding

## Impact

Any consumer of the Unix socket (loop-viz dashboard, TUI tools, `nc -U` one-liners) will show stale/empty state if it connects while a loop is mid-action with no transitions pending. This is the common case for long-running actions like `implement_issue`.

## Session Log
- `/ll:capture-issue` - 2026-05-09T19:39:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b297ddb7-801f-4ba1-aabc-68f533f30384.jsonl`

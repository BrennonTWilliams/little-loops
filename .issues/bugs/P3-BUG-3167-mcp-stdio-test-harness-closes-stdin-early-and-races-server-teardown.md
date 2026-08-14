---
id: BUG-3167
type: BUG
title: MCP stdio test harness closes stdin early and races server teardown
priority: P3
status: done
discovered_by: test-flake-investigation
discovered_date: '2026-08-14'
captured_at: '2026-08-14T00:00:00Z'
completed_at: '2026-08-14T00:00:00Z'
testable: true
---

# BUG-3167: MCP stdio test harness closes stdin early and races server teardown

## Summary

`_stdio_call` in `scripts/tests/test_mcp_server.py` drove the server subprocess with
`subprocess.run(input=...)`, which closes the child's stdin the instant the three
JSON-RPC messages are written. In `mcp==2.0.0`, stdin EOF ends the dispatcher's receive
loop, whose `finally` block calls `tg.cancel_scope.cancel()` —
`mcp/shared/jsonrpc_dispatcher.py:514-517`, commented *"Cancel in-flight handlers;
otherwise the task-group join waits on handlers whose callers are already gone."* The
same path sets `_closed` and calls `_fan_out_closed()`.

So every invocation of `test_list_returning_tools_serialize_over_stdio` raced: the
`tools/call` handler had to finish writing its response before EOF teardown cancelled it.
The handler normally wins, which is why the test passes in isolation essentially always.

**Not a product bug.** Cancelling in-flight handlers on transport EOF is the SDK's
intended contract, and real MCP clients hold stdin open for the whole session — only the
harness produced this teardown ordering.

## Current Behavior

Under heavy CPU load the scheduler occasionally inverts the ordering and the test fails in
one of two ways:

- the `tools/call` response is never written → `AssertionError: no tools/call response`
  with an otherwise clean exit and empty stderr
- the waiter is woken by `_fan_out_closed()` → `{"error": {"code": -32000, "message":
  "Connection closed"}}`, failing `assert "error" not in message`

Which parametrization loses is random, matching the observed evidence: two full-suite runs
launched ~12 minutes apart (with a third overlapping, so up to three ~19k-test suites on a
14-core machine) each failed a *different* case — `[issues_query-2025-06-18]` in one,
`[history_search-2024-11-05]` in the other.

## Expected Behavior

The stdio round-trip is deterministic regardless of machine load. The test keeps crossing
the real wire — that is its whole purpose, catching encode-time validation regressions the
in-memory `Client` cannot see (the `structuredContent` regression) — without depending on
a scheduling race for its result.

## Root Cause

- **File**: `scripts/tests/test_mcp_server.py`
- **Anchor**: `in function _stdio_call()`
- **Cause**: `subprocess.run(input=...)` pipes stdin and closes it immediately after the
  write, so handler completion races EOF-triggered cancellation on every call.

## Frequency

Intermittent. Not reproducible in isolation (240+ repro calls, zero failures, including
under 14-process CPU saturation); observed twice across concurrent full-suite runs.

## Environment

`mcp==2.0.0`, Python 3.12, macOS (14 cores). Reproduced deterministically against a
minimal MCP server by suspending the handler 0.2s at EOF: piped stdin yields the `-32000`
error, held-open stdin yields a clean payload.

## Resolution

- **Action**: fix
- **Completed**: 2026-08-14
- **Status**: Completed

### Changes Made
- `scripts/tests/test_mcp_server.py`: `_stdio_call` rewritten from `subprocess.run` onto
  `subprocess.Popen` — writes the three requests, holds stdin **open**, reads stdout
  line-by-line until the `id: 2` response arrives, then closes stdin and terminates the
  child. Docstring records why stdin must stay open.
- Failure-path hardening, preserving what `subprocess.run` gave for free: a
  `threading.Timer(60, proc.kill)` watchdog so a wedged handler fails the test instead of
  hanging the suite (the kill makes the blocking `readline()` return `''` at EOF);
  `terminate()` → `communicate(timeout=10)` → `kill()` so no child is left behind; and
  both the stdout seen so far and stderr retained in the `no tools/call response`
  assertion message.
- `proc.stdin` set to `None` after closing, or `communicate()` re-flushes the closed
  handle and raises `ValueError: I/O operation on closed file`.

### Verification Results
- Tests: PASS — 6 passed for `-k stdio`; then 12 consecutive runs (72 executions) green
  while 14 busy-loop processes saturated all cores, i.e. under the exact condition that
  produced the original failures
- Lint: PASS (`ruff check`, `ruff format --check` on the changed file)
- No product code changed; no leaked `main_mcp` child processes after the runs

## Session Log
- `hook:posttooluse-status-done` - 2026-08-14T16:58:43 - `f0535309-2c03-4c29-b98c-444cd9efbe9b.jsonl`
- flake investigation + fix - 2026-08-14 - `current.jsonl`

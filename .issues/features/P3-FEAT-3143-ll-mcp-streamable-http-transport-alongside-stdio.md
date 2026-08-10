---
id: 3143
title: 'll-mcp: streamable HTTP transport alongside stdio'
type: FEAT
priority: P3
status: open
discovered_date: '2026-08-10'
discovered_by: learning-test
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp HTTP transport
relates_to:
- FEAT-3135
---

# FEAT-3143: ll-mcp: streamable HTTP transport alongside stdio

## Summary

Add a streamable-HTTP entry path to `ll-mcp` beside the existing stdio one, so a
running little-loops project can be reached from another machine instead of only
from a host that spawns the server as a child process. `build_server()` is not
modified: the same `Server`, the same five tools, the same resource and prompt
surfaces, served over a second transport.

This is a transport addition, not a rewrite — that is proven, not assumed. See
the learning test below.

## Current Behavior

`scripts/little_loops/mcp_server/server.py` exposes exactly one entry coroutine,
`run_stdio()`, which opens `mcp.server.stdio.stdio_server()` and calls
`server.run(...)`. `ll-mcp = "little_loops.mcp_server:main_mcp"` wraps it under
`anyio.run()`. There is no way to reach the server except by having the host
spawn it and speak over the child process's stdin/stdout.

## Expected Behavior

A second entry coroutine (`run_http()`) serves the same server over streamable
HTTP via `mcp.server.streamable_http_manager.StreamableHTTPSessionManager`,
selected by an explicit flag or env var on the `ll-mcp` entry point. Default
behavior is unchanged: bare `ll-mcp` still runs stdio.

## Use Case

Run a little-loops project on a remote or always-on machine and drive it from a
workstation, phone-side agent, or another MCP host — without that host needing
to spawn the process or hold the repo on local disk.

## Impact

Unblocks every remote-access story for `ll-mcp`. Today "remote little-loops"
requires an out-of-band mechanism; after this it is the same server on a
different transport.

## Proven by learning test

`.ll/learning-tests/mcp-http-transport.md` (`proven`, mcp 2.0.0, 6/6 assertions).
The load-bearing result:

- The unmodified `build_server()` `Server` served `tools/list` over
  `StreamableHTTPSessionManager` and returned a byte-identical five-tool catalog
  to the stdio handler, with no handler changes.
- The SEP-2549 cache hints configured in `build_server(cache_hints=...)` came
  through the HTTP response automatically (`"cacheScope":"public"`).

Also proven and load-bearing for callers:

- `Mcp-Method` is enforced, not advisory: a well-formed `tools/list` body with
  the header absent is rejected `-32020` (HEADER_MISMATCH).
- `Mcp-Name` is required only for the three methods in `NAME_BEARING_METHODS`
  (`tools/call`→`name`, `prompts/get`→`name`, `resources/read`→`uri`), and a
  value disagreeing with the body param is rejected `-32020`.
- The `params._meta` envelope rung runs *before* the header rung, so a body
  missing the protocol-version/clientCapabilities keys fails `-32602` even when
  every header is correct.

## Integration Map

- `scripts/little_loops/mcp_server/server.py` — add `run_http()`; leave
  `build_server()` and `run_stdio()` untouched.
- `scripts/little_loops/mcp_server/__init__.py` — `main_mcp` grows transport
  selection.
- `scripts/pyproject.toml` — no dependency change. The `mcp==2.0.0` optional
  extra already pulls starlette, uvicorn, and sse-starlette; the pin comment
  currently justifies them as unused by a stdio-only server, and that comment
  needs updating rather than the dependency list.

## Decisions (settled)

1. **Bind interface and DNS-rebinding protection.** Default bind is loopback
   (`127.0.0.1`), never `0.0.0.0`. `TransportSecuritySettings` keeps its
   `enable_dns_rebinding_protection=True` default in production; the proof's
   `False` override was only to drive an in-process ASGI client and must not
   carry over. A tailnet or other non-public interface may be offered as an
   explicit opt-in, never the default.
2. **`json_response` vs SSE framing, and `stateless`.** Default to
   `json_response=True, stateless=True` — the exact combination the learning
   test proved (`.ll/learning-tests/mcp-http-transport.md`), so the shipped
   default has direct evidence behind it rather than being re-decided at
   implementation time.
3. **Flag vs separate entry point.** A flag/env var on the existing `ll-mcp`
   entry point (as the Expected Behavior section already specifies), not a
   second console script — matches the "same server, second transport"
   framing and avoids a duplicate entry point to keep in sync.

## Anti-goals

- No authentication, TLS termination, or session model in this issue. Those are
  a hosting concern and belong outside the facade.
- No new tools. The tool surface is exactly what stdio serves today.
- No public network exposure as a default.

## Acceptance Criteria

- `ll-mcp` with no arguments still runs stdio, unchanged.
- The HTTP path serves `tools/list`, `resources/list`, and `prompts/list` with
  responses equal to the stdio path's.
- A request missing `Mcp-Method` is rejected `-32020` rather than served.
- The bind interface is explicit and defaults to something non-public; a test
  asserts the default is not `0.0.0.0`.
- `build_server()` is unchanged by this issue.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.

This is transport plumbing under the tier-1 facade, not a new tool surface, so it
does not cross the tier-2 or tier-3 boundaries.

## Status

**Open** | Created: 2026-08-10 | Priority: P3

---
id: FEAT-3143
title: 'll-mcp: streamable HTTP transport alongside stdio'
type: FEAT
priority: P3
status: done
discovered_date: '2026-08-10'
discovered_by: learning-test
completed_at: '2026-08-10T22:10:45Z'
testable: true
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp HTTP transport
relates_to:
- FEAT-3135
- ENH-3173
confidence_score: 98
outcome_confidence: 86
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 22
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

## Program Design

### Deviations

_2026-08-10, implementation:_ `run_http()` calls `Server.streamable_http_app()`
(`mcp.server.lowlevel.Server`, unchanged SDK method) instead of hand-constructing
`StreamableHTTPSessionManager` + a `Starlette` `Route` + `async with
session_manager.run():` as the Signatures/Call Path sections below describe. Two reasons:

1. **Correctness.** `session_manager` bare-constructed with `security_settings=
   TransportSecuritySettings()` (empty `allowed_hosts`/`allowed_origins`, `enable_dns_rebinding_protection=True`)
   rejects *every* request's `Host`/`Origin` header with 421/403 — `allowed_hosts=[]` matches
   nothing, so DNS-rebinding protection becomes deny-all, not "kept at its default" as Decision 1
   intended. `streamable_http_app()` auto-fills a working `allowed_hosts=["127.0.0.1:*",
   "localhost:*", "[::1]:*"]`/`allowed_origins` pair whenever `host` is loopback, which is what
   the SDK's own `run_streamable_http_async()` helper (`mcp.server.mcpserver.server`) relies on
   too — so this is the SDK's own documented path for loopback, not a bespoke shortcut.
2. **Correct lifespan entry.** `streamable_http_app()` wires `session_manager.run()` via
   Starlette's `lifespan=` hook, which `uvicorn.Server.serve()` drives automatically. The
   manual `async with session_manager.run():` the Call Path describes would need to wrap the
   `await uvicorn.Server(...).serve()` call in the same coroutine — extra sequencing the SDK's
   own builder already gets right.

`json_response=True, stateless_http=True` (Decision 2) and the loopback-default `host`
(Decision 1) are unchanged from the design; only the construction path for the Starlette
app changed. `build_server()` remains untouched.

### Types

- `TransportSecuritySettings` (`mcp.server.transport_security`, pydantic
  model) — `enable_dns_rebinding_protection: bool = True` (kept at its
  default), `allowed_hosts: list[str] = []`, `allowed_origins: list[str] = []`.
  Constructed with no overrides; the learning test's `enable_dns_rebinding_protection=False`
  was proof-only and must not appear in `run_http()`.
- No new little-loops types. `run_http()` composes only SDK/Starlette/uvicorn
  types below plus the existing `Server` from `build_server()`.

### Signatures

- `async def run_http(host: str = "127.0.0.1", port: int = 8765) -> None`
  (new, `scripts/little_loops/mcp_server/server.py`, alongside `run_stdio()`)
  — entry coroutine for the HTTP transport, run under `anyio.run()` exactly
  like `run_stdio()`. Binds loopback by default per Decision 1; no parameter
  defaults to `0.0.0.0`.
- `StreamableHTTPSessionManager.__init__(self, app: Server, event_store: EventStore | None = None, json_response: bool = False, stateless: bool = False, security_settings: TransportSecuritySettings | None = None, ...) -> None`
  (`mcp.server.streamable_http_manager`, unchanged SDK class) — constructed
  inside `run_http()` as `StreamableHTTPSessionManager(app=build_server(), json_response=True, stateless=True, security_settings=TransportSecuritySettings())`
  per Decision 2 (the exact combination the learning test proved).
- `StreamableHTTPSessionManager.run(self) -> AsyncContextManager[None]`
  (`@asynccontextmanager`, unchanged SDK method) — must be entered
  (`async with session_manager.run():`) before any request is served; owns
  the manager's background task group for the process lifetime, mirroring
  how `stdio_server()` is entered in `run_stdio()`.
- `StreamableHTTPSessionManager.handle_request(self, scope: Scope, receive: Receive, send: Send) -> None`
  (unchanged SDK method) — the ASGI entrypoint; `run_http()` wires it as a
  `Starlette` route (`Mount` or a single `Route` catching all methods on the
  MCP path) rather than calling it directly.
- `uvicorn.Config.__init__(self, app: ASGIApplication, host: str, port: int, ...) -> None`
  and `uvicorn.Server.serve(self, sockets=None) -> None` (unchanged, already
  a transitive dep of the `mcp` extra) — `run_http()` builds
  `uvicorn.Config(starlette_app, host=host, port=port)`, wraps it in
  `uvicorn.Server(config)`, and awaits `.serve()` from inside the
  `session_manager.run()` context — this replaces `anyio.run(uvicorn.run, ...)`,
  which is sync-only and cannot be awaited alongside the manager's context.
- `main_mcp(argv: list[str] | None = None) -> int` (existing,
  `scripts/little_loops/mcp_server/__init__.py`) — signature is unchanged;
  the transport-selection branch reads inside the function body, not a new
  parameter (console-script entry points take no argv from `pyproject.toml`,
  so a flag has to come from `argv`/env, not a new function signature).

### Transport-selection branch (`main_mcp`)

```python
def main_mcp(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ...  # existing mcp-extra ImportError check, unchanged

    import anyio

    from little_loops.mcp_server.server import run_http, run_stdio

    if "--http" in argv or os.environ.get("LL_MCP_TRANSPORT") == "http":
        anyio.run(run_http)
    else:
        anyio.run(run_stdio)
    return 0
```

`argv` is read here (not parsed with `argparse`) to keep `main_mcp`'s existing
"protocol server, not a CLI" framing (`__init__.py` module docstring) — one
boolean flag check plus one env var fallback, no help text or subcommands.
`LL_MCP_TRANSPORT=http` exists for host configs that invoke `ll-mcp` with no
args (env var is the only lever available when the caller can't pass flags).
Default with neither `--http` nor the env var set is unchanged: `run_stdio()`,
satisfying Acceptance Criterion 1.

### Call Path

`main_mcp()` → (flag/env check) → `anyio.run(run_http)` → `run_http()` builds
`server = build_server()` (unmodified) → constructs
`StreamableHTTPSessionManager(app=server, json_response=True, stateless=True, security_settings=TransportSecuritySettings())`
→ wraps `session_manager.handle_request` in a `Starlette` app → `async with
session_manager.run():` → `uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port)).serve()`.
Each inbound request flows `Starlette` route → `handle_request(scope, receive, send)`
→ SDK's existing header/envelope validation (`Mcp-Method`, `Mcp-Name`,
`params._meta`, proven by the learning test's claims 1-4) → the same
`on_list_tools`/`on_call_tool`/`on_read_resource`/etc. handlers `build_server()`
already registers.

### Decision Rules

N/A — no new gap kind, gate, or threshold. The three open questions this
issue faced (bind interface, `json_response`/`stateless`, flag-vs-entry-point)
are already resolved in `## Decisions (settled)` above with direct learning-test
evidence; this section only makes those decisions concrete in code.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-10_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH

`## Program Design` section added 2026-08-10 with concrete `run_http()` and
`StreamableHTTPSessionManager`/uvicorn signatures and the `main_mcp()`
transport-selection branch; `ll-issues check-design FEAT-3143` now passes.

## Status

**Open** | Created: 2026-08-10 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-10T22:10:17 - `95a2ffbd-8fe6-4696-85b1-3e0eb81cea65.jsonl`
- `/ll:ready-issue` - 2026-08-10T21:51:16 - `36db716f-7499-4b8a-97d1-bf0e7c247e11.jsonl`
- `/ll:confidence-check` - 2026-08-10T21:19:52 - `c399e98c-b001-4568-9896-227421406281.jsonl`

"""Builds and runs the `ll-mcp` stdio server (FEAT-3135, FEAT-3136, FEAT-3137).

No Roots, Sampling, or Logging handlers are registered — all three were deprecated in the
2026-07-28 spec with a 12-month minimum window — and no MRTR (multi round-trip) request shape
is issued or handled: every tool resolves from its own params in a single round trip.
`server/discover` is the SDK's default handler (no custom handler registered here), and it
auto-derives capabilities from whatever handlers this module registers, so "advertises no
Roots/Sampling/Logging" is satisfied structurally rather than needing its own assertion target.
Resources ARE registered (FEAT-3136), so `caps.resources` is non-`None`. Prompts ARE registered
(FEAT-3137, every discovered `SKILL.md`), so `caps.prompts` is non-`None`.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.lowlevel import Server


def _server_version() -> str:
    try:
        return importlib.metadata.version("little-loops")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def build_http_app(host: str = "127.0.0.1") -> Any:
    """Build the streamable-HTTP ASGI app with the FEAT-3149 transport policy wrapped around it.

    Split out of :func:`run_http` so tests can drive the composed app through Starlette's
    `TestClient` without binding a socket, and so the policy wrapper cannot be applied on
    one path and forgotten on the other.

    The wrapper is outermost on purpose: :class:`TransportPolicyMiddleware` must reach its
    deny decision from the SEP-2243 routing headers *before* the SDK app parses the
    JSON-RPC body, which it can only do if nothing downstream has consumed the request yet.

    Note this is the HTTP path only — stdio has no headers to route on. The policy
    *decision* therefore lives in `policy.check_tool_call`, which the middleware invokes;
    encoding the rules inside the middleware would make them silently absent over stdio.
    """
    from little_loops.mcp_server.policy import TransportPolicyMiddleware

    server = build_server()
    app = server.streamable_http_app(json_response=True, stateless_http=True, host=host)
    return TransportPolicyMiddleware(app, transport="http")


def build_server() -> Server:
    """Construct the `ll-mcp` lowlevel `Server`: the read-only and guarded-mutation tool
    surface, the `ll://` resource surface, and the prompts-from-skills surface.

    The resource/prompt enumerations are built fresh here, once per `Server` instance — this
    function is called once per stdio session (`run_stdio`) and once per test — rather than at
    module import time, so they never leak state across servers/tests.
    """
    from mcp.server.caching import CacheHint
    from mcp.server.lowlevel import Server

    from little_loops.config import BRConfig
    from little_loops.mcp_server.prompts import (
        build_prompt_index,
        make_get_prompt_handler,
        make_list_prompts_handler,
    )
    from little_loops.mcp_server.resources import (
        build_resource_index,
        make_list_resources_handler,
        make_read_resource_handler,
    )
    from little_loops.mcp_server.tools import handle_call_tool, handle_list_tools
    from little_loops.skill_expander import _find_plugin_root

    config = BRConfig(Path.cwd())
    resource_index = build_resource_index(config)
    prompt_index = build_prompt_index(_find_plugin_root() / "skills")

    return Server(
        "ll-mcp",
        version=_server_version(),
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
        on_list_resources=make_list_resources_handler(resource_index),
        on_read_resource=make_read_resource_handler(resource_index, config),
        on_list_prompts=make_list_prompts_handler(prompt_index),
        on_get_prompt=make_get_prompt_handler(prompt_index),
        # tools/list, resources/list, resources/read, and prompts/list are the SEP-2549
        # cacheable methods this tier registers handlers for. The tool catalog, resource
        # enumeration, and skill catalog only change on an `ll-mcp` upgrade or restart, so a
        # 5-minute, cross-client ("public") freshness window is safe for all four. This is the
        # SDK auto-filling ttlMs/cacheScope from a server-wide hint, not something a handler
        # sets by hand — see `mcp.server.caching.apply_cache_hint`.
        cache_hints={
            "tools/list": CacheHint(ttl_ms=300_000, scope="public"),
            "resources/list": CacheHint(ttl_ms=300_000, scope="public"),
            "resources/read": CacheHint(ttl_ms=300_000, scope="public"),
            "prompts/list": CacheHint(ttl_ms=300_000, scope="public"),
        },
    )


async def run_stdio() -> None:
    """Entry coroutine: open the stdio transport and run the server to completion.

    `stdio_server()` is an `@asynccontextmanager` yielding `(read_stream, write_stream)`;
    `Server.run()` is `async def`. Both close over the process's real stdin/stdout, so this
    coroutine must run under `anyio.run()` (see `main_mcp`) — nothing here should be called
    from synchronous code.
    """
    import mcp.server.stdio as stdio_transport

    server = build_server()
    async with stdio_transport.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_http(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Entry coroutine: serve the same `build_server()` `Server` over streamable HTTP.

    Built on `Server.streamable_http_app()` (the SDK's own Starlette-app builder for this
    transport) rather than hand-constructing a `StreamableHTTPSessionManager` and wiring a
    `Starlette` route directly — see the "Deviations" note under FEAT-3143's Program Design
    for why: `streamable_http_app()` already enters `session_manager.run()` via Starlette's
    `lifespan`, and for a loopback `host` it auto-fills `TransportSecuritySettings` with a
    working `allowed_hosts`/`allowed_origins` pair. A bare `TransportSecuritySettings()` has
    empty allow-lists, which — with DNS-rebinding protection on by default — rejects every
    request's `Host`/`Origin` header, including legitimate ones.

    Binds loopback by default (Decision 1 in FEAT-3143): no parameter here defaults to
    `0.0.0.0`. `json_response=True, stateless=True` is Decision 2, the exact combination
    proven by `.ll/learning-tests/mcp-http-transport.md`.

    App construction moved to `build_http_app()` (FEAT-3149) so the mutation-policy
    middleware is applied on exactly one code path.
    """
    import uvicorn

    config = uvicorn.Config(build_http_app(host), host=host, port=port)
    await uvicorn.Server(config).serve()

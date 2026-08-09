"""Builds and runs the `ll-mcp` stdio server (FEAT-3135, FEAT-3136).

No Roots, Sampling, or Logging handlers are registered — all three were deprecated in the
2026-07-28 spec with a 12-month minimum window — and no MRTR (multi round-trip) request shape
is issued or handled: every tool resolves from its own params in a single round trip.
`server/discover` is the SDK's default handler (no custom handler registered here), and it
auto-derives capabilities from whatever handlers this module registers, so "advertises no
Roots/Sampling/Logging" is satisfied structurally rather than needing its own assertion target.
Resources ARE registered (FEAT-3136), so `caps.resources` is non-`None`.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.lowlevel import Server


def _server_version() -> str:
    try:
        return importlib.metadata.version("little-loops")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def build_server() -> Server:
    """Construct the `ll-mcp` lowlevel `Server`: five read-only tools plus the `ll://`
    resource surface.

    The resource enumeration is built fresh here, once per `Server` instance — this function
    is called once per stdio session (`run_stdio`) and once per test — rather than at module
    import time, so it never leaks state across servers/tests.
    """
    from mcp.server.caching import CacheHint
    from mcp.server.lowlevel import Server

    from little_loops.config import BRConfig
    from little_loops.mcp_server.resources import (
        build_resource_index,
        make_list_resources_handler,
        make_read_resource_handler,
    )
    from little_loops.mcp_server.tools import handle_call_tool, handle_list_tools

    config = BRConfig(Path.cwd())
    resource_index = build_resource_index(config)

    return Server(
        "ll-mcp",
        version=_server_version(),
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
        on_list_resources=make_list_resources_handler(resource_index),
        on_read_resource=make_read_resource_handler(resource_index, config),
        # tools/list, resources/list, and resources/read are the SEP-2549 cacheable methods
        # this tier registers handlers for. The tool catalog and resource enumeration only
        # change on an `ll-mcp` upgrade or restart, so a 5-minute, cross-client ("public")
        # freshness window is safe for all three. This is the SDK auto-filling
        # ttlMs/cacheScope from a server-wide hint, not something a handler sets by hand —
        # see `mcp.server.caching.apply_cache_hint`.
        cache_hints={
            "tools/list": CacheHint(ttl_ms=300_000, scope="public"),
            "resources/list": CacheHint(ttl_ms=300_000, scope="public"),
            "resources/read": CacheHint(ttl_ms=300_000, scope="public"),
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

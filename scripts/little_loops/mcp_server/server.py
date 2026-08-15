"""Builds and runs the `ll-mcp` stdio server (FEAT-3135, FEAT-3136, FEAT-3137).

No Roots, Sampling, or Logging handlers are registered — all three were deprecated in the
2026-07-28 spec with a 12-month minimum window — and no MRTR (multi round-trip) request shape
is issued or handled: every tool resolves from its own params in a single round trip.
`server/discover` is the SDK's default handler (no custom handler registered here), and it
auto-derives capabilities from whatever handlers this module registers, so "advertises no
Roots/Sampling/Logging" is satisfied structurally rather than needing its own assertion target.
Resources ARE registered (FEAT-3136), so `caps.resources` is non-`None`. Prompts ARE registered
(FEAT-3137, every discovered `SKILL.md`), so `caps.prompts` is non-`None`. `subscriptions/listen`
IS registered (ENH-3172) — unrelated to the deprecated Roots/Sampling/Logging trio above; it is
how the 2026-07-28 wire delivers `resources`/`prompts` list-changed events once the index behind
either surface is rebuilt after startup.
"""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import mcp_types as types
    from mcp.server.context import ServerRequestContext
    from mcp.server.lowlevel import Server


def _server_version() -> str:
    try:
        return importlib.metadata.version("little-loops")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _resolve_skills_root() -> Path:
    """Resolve the prompts-from-skills root (BUG-3177).

    `_find_plugin_root()`'s bare fallback (three parents above this file) only lands
    on `skills/` in an editable checkout — a wheel install has no `skills/` there,
    which silently produced an empty prompt catalog. This adds, in order: an explicit
    override, the Claude Code plugin root, the in-package copy `pyproject.toml`'s
    `force-include` ships into the wheel, then the editable-checkout fallback. Each
    candidate is validated with `.is_dir()` before being trusted — unlike
    `_find_plugin_root()` itself, which trusts `CLAUDE_PLUGIN_ROOT` unconditionally —
    so a stale/wrong env var falls through instead of resolving to a directory that
    doesn't exist. If nothing resolves, warns on stderr naming every path tried;
    `ll-mcp` is spawned by a host, so stderr is the host's server log.
    """
    from little_loops.skill_expander import _find_plugin_root

    candidates: list[Path] = []

    override = os.environ.get("LL_MCP_SKILLS_ROOT")
    if override:
        candidates.append(Path(override))

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        candidates.append(Path(plugin_root) / "skills")

    try:
        candidates.append(Path(str(importlib.resources.files("little_loops"))) / "skills")
    except (ModuleNotFoundError, TypeError):
        pass

    candidates.append(_find_plugin_root() / "skills")

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    tried = ", ".join(str(candidate) for candidate in candidates)
    print(f"ERROR: no skills directory found; tried: {tried}", file=sys.stderr)
    return candidates[-1]


#: Hosts the SDK's own `Server.streamable_http_app()` recognizes as loopback and
#: auto-fills `TransportSecuritySettings` for. Kept in sync with that recognition set
#: (not derived from it — the SDK does not expose it as a constant) so ENH-3173's
#: non-loopback branch below activates on exactly the hosts the SDK's own branch does not.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def build_http_app(host: str = "127.0.0.1", project_root: Path | None = None) -> Any:
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

    ENH-3171: `project_root` resolves the same way `build_server` does, and is threaded
    into :class:`TransportPolicyMiddleware` too — it decides mutation/task grants from
    `.ll/ll-config.json` before the request body is even parsed, so it is a policy call
    site in the same sense `build_server`'s own `config` is.

    ENH-3173: `Server.streamable_http_app()` only auto-fills `TransportSecuritySettings`
    for a loopback `host` (see `_LOOPBACK_HOSTS`); for any other host it leaves
    `transport_security=None`, which disables DNS-rebinding protection outright — not the
    "empty allow-lists reject everything" failure this issue is about, but still the wrong
    posture for a deliberately-exposed non-loopback bind. So a non-loopback `host` here
    gets an explicit `TransportSecuritySettings` seeded from that same host, mirroring the
    SDK's own loopback pattern (`allowed_hosts=["host:*"]`,
    `allowed_origins=["scheme://host:*"]`) rather than leaving protection off.
    """
    from little_loops.mcp_server.policy import TransportPolicyMiddleware
    from little_loops.mcp_server.tools import _project_root

    resolved_root = _project_root(project_root)
    server = build_server(transport="http", project_root=resolved_root)

    transport_security = None
    if host not in _LOOPBACK_HOSTS:
        from mcp.server.transport_security import TransportSecuritySettings

        transport_security = TransportSecuritySettings(
            allowed_hosts=[f"{host}:*"],
            allowed_origins=[f"http://{host}:*", f"https://{host}:*"],
        )

    app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        host=host,
        transport_security=transport_security,
    )
    return TransportPolicyMiddleware(app, transport="http", project_root=resolved_root)


def build_server(transport: str, project_root: Path | None = None) -> Server:
    """Construct the `ll-mcp` lowlevel `Server`: the read-only and guarded-mutation tool
    surface, the `ll://` resource surface, and the prompts-from-skills surface.

    The resource/prompt enumerations are built fresh here, once per `Server` instance — this
    function is called once per stdio session (`run_stdio`) and once per test — rather than at
    module import time, so they never leak state across servers/tests.

    FEAT-3168: `transport` (``"http"`` or ``"stdio"``) threads transport identity into the
    `tools/call` and `tasks/*` handler factories so `policy.check_tool_call` can enforce the
    same decision on both transports, not just HTTP's ASGI middleware. It is **required and
    has no default**: the value selects which half of `mcp.transport_policy` applies, so a
    default would let a new call site silently enforce the wrong operator grant. A wrong
    answer here is a security misconfiguration, not a convenience nit — there is no value
    that is safe to guess, so the caller must state it.

    ENH-3171: `project_root` defaults to `None`, resolved via `tools._project_root()`
    (explicit arg, then `LL_MCP_PROJECT_ROOT`, then `Path.cwd()`) — the same precedence
    `main_mcp` applies before calling in here, so a caller that already resolved a root
    (or a test that doesn't care) is never forced to re-derive it.
    """
    from mcp.server.caching import CacheHint
    from mcp.server.extension import compose_tool_call_handler
    from mcp.server.lowlevel import Server
    from mcp.server.subscriptions import InMemorySubscriptionBus, ListenHandler

    from little_loops.config import BRConfig
    from little_loops.mcp_server.prompts import (
        PromptIndex,
        make_get_prompt_handler,
        make_list_prompts_handler,
    )
    from little_loops.mcp_server.resources import (
        ResourceIndex,
        make_list_resources_handler,
        make_read_resource_handler,
    )
    from little_loops.mcp_server.tasks import (
        TasksCancelParams,
        TasksExtension,
        TasksGetParams,
        make_tasks_cancel_handler,
        make_tasks_get_handler,
    )
    from little_loops.mcp_server.tools import (
        _project_root,
        handle_list_tools,
        make_call_tool_handler,
    )

    resolved_root = _project_root(project_root)
    config = BRConfig(resolved_root)
    resource_index = ResourceIndex(config)
    prompt_index = PromptIndex(_resolve_skills_root())

    # ENH-3172: SEP-2575's `subscriptions/listen` is how the 2026-07-28 wire delivers
    # `ResourcesListChanged`/`PromptsListChanged` — registering `on_subscriptions_listen`
    # also makes `get_capabilities()` derive `resources.listChanged`/`prompts.listChanged`
    # (and `resources.subscribe`) as `True` for modern clients automatically, with no
    # separate NotificationOptions wiring needed. `resource_index`/`prompt_index` publish
    # to this same bus from inside their `*_list` handlers when a refresh rebuilds them.
    subscription_bus = InMemorySubscriptionBus()

    # FEAT-3151: wraps handle_call_tool with the SEP-2663 start-path interceptor.
    # Additive — TasksExtension passes every call through unchanged except the one tool
    # name it re-shapes (Decision 2a scoping note) — so this composition preserves
    # existing tools/call behavior for every other tool (AC 7).
    # compose_tool_call_handler's RequestHandler is typed against the SDK's broader
    # HandlerResult (BaseModel | dict | None); Server.on_call_tool's annotation is the
    # narrower CallToolResult | InputRequiredResult it normally serializes — the same
    # widening `_dump_result` already accepts at runtime (tools.py's handle_call_tool
    # docstring).
    on_call_tool = cast(
        "Callable[[ServerRequestContext[Any, Any], types.CallToolRequestParams], Awaitable[types.CallToolResult | types.InputRequiredResult]]",
        compose_tool_call_handler(
            [TasksExtension()], make_call_tool_handler(transport, resolved_root)
        ),
    )

    server = Server(
        "ll-mcp",
        version=_server_version(),
        on_list_tools=handle_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=make_list_resources_handler(resource_index, subscription_bus),
        on_read_resource=make_read_resource_handler(resource_index, config),
        on_list_prompts=make_list_prompts_handler(prompt_index, subscription_bus),
        on_get_prompt=make_get_prompt_handler(prompt_index),
        on_subscriptions_listen=ListenHandler(subscription_bus),
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

    # FEAT-3145: tasks/get + tasks/cancel poll surface. Additive method names (neither
    # collides with a spec method), registered via add_request_handler rather than the
    # SDK's MCPServer(extensions=[...]) API, which the lowlevel Server has no parameter
    # for. Gated by the transport policy in policy.py, not here — see build_http_app().
    server.add_request_handler(
        "tasks/get", TasksGetParams, make_tasks_get_handler(transport, resolved_root)
    )
    server.add_request_handler(
        "tasks/cancel", TasksCancelParams, make_tasks_cancel_handler(transport, resolved_root)
    )

    return server


async def run_stdio(project_root: Path | None = None) -> None:
    """Entry coroutine: open the stdio transport and run the server to completion.

    `stdio_server()` is an `@asynccontextmanager` yielding `(read_stream, write_stream)`;
    `Server.run()` is `async def`. Both close over the process's real stdin/stdout, so this
    coroutine must run under `anyio.run()` (see `main_mcp`) — nothing here should be called
    from synchronous code.

    ENH-3171: `project_root` threads through to `build_server`, defaulting to `None` so
    `main_mcp`'s no-flag path is unchanged.
    """
    import mcp.server.stdio as stdio_transport

    server = build_server(transport="stdio", project_root=project_root)
    async with stdio_transport.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_http(
    host: str = "127.0.0.1", port: int = 8765, project_root: Path | None = None
) -> None:
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

    config = uvicorn.Config(build_http_app(host, project_root=project_root), host=host, port=port)
    await uvicorn.Server(config).serve()

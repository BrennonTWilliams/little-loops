"""Guard 2 of FEAT-3149: which tools mutate, and which transports may run them.

This module owns two things that must never disagree:

1. :data:`MUTATING_TOOLS` — the single registry of tool names that write. Both guards
   consult it: `tools.py`'s dry-run wrapper (Guard 1) and the transport policy here
   (Guard 2). One list, so the two guards cannot form different opinions about what
   counts as a write. `tools.py` imports from here and not the reverse, so there is no
   import cycle.
2. :func:`check_tool_call` — the policy decision itself, expressed once, at the policy
   layer. :class:`TransportPolicyMiddleware` *invokes* it rather than encoding rules
   inline, because the middleware only exists on the HTTP path: a rule written inside it
   would be silently absent over stdio.

**Why a middleware and not an SDK hook.** `mcp==2.0.0` implements SEP-2243 header routing
(`mcp.shared.inbound` exports `MCP_METHOD_HEADER`/`MCP_NAME_HEADER`) but exposes no
pre-parse extension point: `classify_inbound_request` takes the *decoded body* as its
first required positional parameter, and `handle_modern_request` parses the body
(`json.loads`) before it validates the headers. The library's only use of these headers
is a mismatch rejection (`HEADER_MISMATCH`, -32020); they are never used to dispatch.
Proven in `.ll/learning-tests/mcp-header-routing.md` against the pinned SDK version.

**Why a header-only decision is sound.** The obvious objection is spoofing: why trust
`Mcp-Method`/`Mcp-Name` when the body is what actually gets executed? Because the server
independently enforces header/body agreement *downstream*. A request whose headers lie
about its body is rejected with -32020 before reaching any handler, and — verified
against the pinned SDK — both headers are mandatory for `tools/call` on the modern HTTP
path: omitting either is itself a -32020. So a request cannot reach a mutating handler
while hiding its identity from this middleware. The two mechanisms compose: the SDK
guarantees the headers are truthful, and this guard reads them before the body exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping

    from little_loops.config import BRConfig

#: SEP-2243 routing headers, lowercased as they arrive on the raw ASGI scope. Hardcoded
#: rather than imported from `mcp.shared.inbound` so this module stays importable without
#: the optional `mcp` extra installed; `test_feat_3149_transport_policy.py` asserts they
#: still match the SDK's own constants.
MCP_METHOD_HEADER = b"mcp-method"
MCP_NAME_HEADER = b"mcp-name"

#: The one registry of mutating tool names, consulted by both guards (FEAT-3149's
#: "Method classification" decision rule). Adding a write tool means adding it here;
#: `tools.py` will then refuse to dispatch it without an explicit apply opt-in.
MUTATING_TOOLS = frozenset(
    {
        "issue_capture",
        "issue_set_status",
        "issue_link",
        "issue_append_log",
    }
)

#: FEAT-3151 Decision 8: tools that start a run (spawn an agent with the project's full
#: tool permissions) are a separate registry from `MUTATING_TOOLS` — starting a run is not
#: a file mutation, and joining `MUTATING_TOOLS` would make `handle_call_tool`'s dry-run
#: guard refuse to dispatch without `apply: true`, which has no coherent meaning for
#: "start". Gated by `allows_tasks()`, the same grant FEAT-3145's `tasks/*` poll/stop
#: surface reuses (Decision 4): an operator who has enabled `tasks/*` over HTTP has
#: consented to run control.
TASK_STARTING_TOOLS = frozenset({"loop_start"})

#: JSON-RPC error code for a policy denial. -32001 sits in the -32000..-32099
#: implementation-defined server-error band, so it cannot collide with a reserved
#: protocol code (the SDK's own `HEADER_MISMATCH` is -32020).
POLICY_DENIED_CODE = -32001


@dataclass(frozen=True)
class PolicyDecision:
    """Whether a call may proceed, and — when it may not — why."""

    allowed: bool
    reason: str = ""


def check_tool_call(
    transport: str,
    method: str | None,
    tool_name: str | None,
    *,
    config: BRConfig | None = None,
) -> PolicyDecision:
    """Decide whether ``method``/``tool_name`` may run over ``transport``.

    Two independent grants are checked, and every other method (`tools/list`,
    `resources/read`, the tier-1 read tools, …) passes through untouched, which is
    what keeps a deny-configured HTTP transport fully useful for reads:

    - `tools/call` naming a tool in :data:`MUTATING_TOOLS` is gated by
      ``allows_mutations()``.
    - Any `tasks/*` method (FEAT-3145: `tasks/get`, `tasks/cancel`) is gated by
      ``allows_tasks()``. This is a *separate* grant from mutations (Decision 6) —
      an operator who allows issue-file writes over HTTP has not thereby consented
      to stopping a running agent.
    - `tools/call` naming a tool in :data:`TASK_STARTING_TOOLS` (FEAT-3151: `loop_start`)
      is also gated by ``allows_tasks()`` — starting and stopping a run are the same
      class of authority over the same resource (Decision 4/8).

    Args:
        transport: ``"http"`` or ``"stdio"``.
        method: The JSON-RPC method name, or None when absent.
        tool_name: The tool being called, or None when absent.
        config: Project configuration; resolved fresh from :func:`Path.cwd` when omitted,
            matching the per-request statelessness invariant `tools.py` follows.

    Returns:
        A :class:`PolicyDecision`.
    """
    is_mutating_call = method == "tools/call" and tool_name in MUTATING_TOOLS
    is_task_call = method is not None and method.startswith("tasks/")
    is_task_starting_call = method == "tools/call" and tool_name in TASK_STARTING_TOOLS

    if not is_mutating_call and not is_task_call and not is_task_starting_call:
        return PolicyDecision(allowed=True)

    if config is None:
        from little_loops.config import BRConfig

        config = BRConfig(Path.cwd())

    if is_task_call or is_task_starting_call:
        if config.mcp.transport_policy.allows_tasks(transport):
            return PolicyDecision(allowed=True)
        # The subject names what was actually denied — `tasks/*` and `loop_start` share
        # one grant but are different surfaces, and a `loop_start` denial that says
        # "tasks/* requests are disabled" reads as a mismatch to whoever hits it. The
        # remedy clause is shared because the grant genuinely is.
        if is_task_call:
            denied_what, disabled_what = method, "tasks/* requests"
        else:
            denied_what, disabled_what = f"tools/call/{tool_name}", "run-starting tools"
        return PolicyDecision(
            allowed=False,
            reason=(
                f"policy denied {denied_what}: {disabled_what} are disabled on the "
                f"{transport} transport (set mcp.transport_policy.{transport}.allow_tasks "
                "to true in .ll/ll-config.json to permit them)"
            ),
        )

    if config.mcp.transport_policy.allows_mutations(transport):
        return PolicyDecision(allowed=True)

    return PolicyDecision(
        allowed=False,
        reason=(
            f"policy denied tools/call/{tool_name}: mutating tools are disabled on the "
            f"{transport} transport (set mcp.transport_policy.{transport}.allow_mutations "
            "to true in .ll/ll-config.json to permit them)"
        ),
    )


class TransportPolicyMiddleware:
    """ASGI middleware enforcing :func:`check_tool_call` on the HTTP transport.

    Wraps `Server.streamable_http_app()`. Reads the SEP-2243 routing headers off the raw
    ASGI ``scope`` and, on denial, writes a JSON-RPC error response directly — **without
    ever awaiting** ``receive()``, so the decision genuinely precedes body parsing rather
    than merely preceding dispatch. The denial is a JSON-RPC error object (not a bare HTTP
    error page) so a compliant client surfaces it as a protocol error rather than a
    transport failure.

    HTTP 403 accompanies the JSON-RPC body: the request was well-formed and understood,
    and refusing it is a deployment policy choice, not a client mistake.
    """

    def __init__(self, app: Any, transport: str = "http", project_root: Path | None = None) -> None:
        self.app = app
        self.transport = transport
        self.project_root = project_root

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        method = _decode(headers.get(MCP_METHOD_HEADER))
        tool_name = _decode(headers.get(MCP_NAME_HEADER))

        # ENH-3171: `project_root` defaults to `None` (unset by callers that construct this
        # middleware directly, e.g. tests) — `check_tool_call` falls back to `Path.cwd()`
        # in that case, same as before this issue. `build_http_app` always passes the
        # resolved root, so the real server path never hits that fallback.
        config = None
        if self.project_root is not None:
            from little_loops.config import BRConfig

            config = BRConfig(self.project_root)

        decision = check_tool_call(self.transport, method, tool_name, config=config)
        if decision.allowed:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": POLICY_DENIED_CODE, "message": decision.reason},
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _decode(raw: bytes | None) -> str | None:
    """Decode a raw ASGI header value, treating undecodable bytes as absent."""
    if raw is None:
        return None
    try:
        return raw.decode("latin-1").strip()
    except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes any byte string
        return None

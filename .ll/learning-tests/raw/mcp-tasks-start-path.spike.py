"""Spike: SEP-2663 task-start reachability + SEP-2243 pre-parse header routing on mcp==2.0.0.

Claims under test
  C1  A `tools/call` handler returning a task-shaped Mapping (`resultType: "task"`)
      passes the outbound pipeline UNSIEVED and reaches the wire intact.
  C2  `tasks/get`, `tasks/update`, `tasks/cancel` all register via add_request_handler.
  C3  `MethodBinding` still rejects `tools/call` (so C1 needed no spec-method re-registration).
  C4  There is NO library pre-parse hook: classify_inbound_request requires the decoded body,
      and handle_modern_request parses the body BEFORE validating headers.
  C5  ASGI middleware in front of streamable_http_app() CAN read Mcp-Method/Mcp-Name and
      short-circuit a request BEFORE the MCP server parses the JSON-RPC body.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from mcp.server.lowlevel import Server
from mcp.shared.inbound import MCP_METHOD_HEADER, MCP_NAME_HEADER, classify_inbound_request
from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

PROTOCOL_VERSION = "2026-07-28"
RESULTS: list[tuple[str, bool, str]] = []


def record(claim: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((claim, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {claim}\n       {detail}\n")


def envelope(extra: dict | None = None) -> dict:
    meta = {
        PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
        CLIENT_CAPABILITIES_META_KEY: {},
    }
    return {"_meta": meta, **(extra or {})}


def post(client: TestClient, method: str, params: dict, *, name: str | None = None):
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": PROTOCOL_VERSION,
        MCP_METHOD_HEADER: method,
    }
    if name is not None:
        headers[MCP_NAME_HEADER] = name
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return client.post("/mcp", json=body, headers=headers)


TASK_SEED = {
    "resultType": "task",
    "taskId": "786512e2-9e0d-44bd-8f29-789f320fe840",
    "status": "working",
    "statusMessage": "The operation is now in progress.",
    "createdAt": "2026-08-11T10:30:00Z",
    "lastUpdatedAt": "2026-08-11T10:30:00Z",
    "ttlMs": 60000,
    "pollIntervalMs": 5000,
}


def build_spike_server() -> Server:
    async def on_list_tools(ctx):  # noqa: ANN001
        from mcp_types import Tool

        return [
            Tool(
                name="start_run",
                description="spike tool",
                inputSchema={"type": "object", "properties": {}},
            )
        ]

    async def on_call_tool(ctx, params):  # noqa: ANN001
        # Return the SEP-2663 CreateTaskResult shape as a plain Mapping, NOT a CallToolResult.
        return dict(TASK_SEED)

    server = Server("spike", version="0.0.0", on_list_tools=on_list_tools, on_call_tool=on_call_tool)

    from mcp_types import RequestParams

    class TaskIdParams(RequestParams):
        taskId: str | None = None

    async def tasks_get(ctx, params):  # noqa: ANN001
        return {"resultType": "complete", "taskId": params.taskId, "status": "completed"}

    async def tasks_update(ctx, params):  # noqa: ANN001
        return {"resultType": "complete", "taskId": params.taskId, "status": "working"}

    async def tasks_cancel(ctx, params):  # noqa: ANN001
        return {"resultType": "complete", "taskId": params.taskId, "status": "cancelled"}

    for method, handler in (
        ("tasks/get", tasks_get),
        ("tasks/update", tasks_update),
        ("tasks/cancel", tasks_cancel),
    ):
        server.add_request_handler(method, TaskIdParams, handler)
    return server


# ---------------------------------------------------------------- C3
def check_method_binding() -> None:
    from mcp.server.extension import MethodBinding
    from mcp_types import RequestParams

    async def _noop(ctx, params):  # noqa: ANN001
        return {}

    try:
        MethodBinding("tools/call", RequestParams, _noop)
        record("C3 MethodBinding rejects tools/call", False, "constructed without error")
    except ValueError as exc:
        record("C3 MethodBinding rejects tools/call", True, f"ValueError: {exc}")
    try:
        MethodBinding("tasks/get", RequestParams, _noop)
        record("C3b MethodBinding accepts tasks/get", True, "constructed cleanly")
    except ValueError as exc:
        record("C3b MethodBinding accepts tasks/get", False, str(exc))


# ---------------------------------------------------------------- C4
def check_no_preparse_hook() -> None:
    sig = inspect.signature(classify_inbound_request)
    body_required = sig.parameters["body"].default is inspect.Parameter.empty
    record(
        "C4a classify_inbound_request REQUIRES the decoded body (headers alone insufficient)",
        body_required,
        f"signature: {sig}",
    )

    import mcp.server._streamable_http_modern as mod

    src, start = inspect.getsourcelines(mod.handle_modern_request)
    parse_ln = classify_ln = None
    for i, line in enumerate(src):
        if "json.loads(" in line and parse_ln is None:
            parse_ln = start + i
        if "classify_inbound_request(" in line and classify_ln is None:
            classify_ln = start + i
    ok = parse_ln is not None and classify_ln is not None and parse_ln < classify_ln
    record(
        "C4b body is parsed BEFORE headers are validated (no pre-parse policy hook)",
        ok,
        f"json.loads at line {parse_ln}; classify_inbound_request at line {classify_ln}",
    )


# ---------------------------------------------------------------- C1 + C2 + C5
def check_wire() -> None:
    server = build_spike_server()
    app = server.streamable_http_app(json_response=True, stateless_http=True, host="127.0.0.1")

    # ---- C5: ASGI middleware reading routing headers before the MCP app sees the body.
    seen: list[dict[str, Any]] = []

    class PolicyMiddleware:
        def __init__(self, app):  # noqa: ANN001
            self.app = app

        async def __call__(self, scope, receive, send):  # noqa: ANN001
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            method = headers.get(MCP_METHOD_HEADER)
            name = headers.get(MCP_NAME_HEADER)
            # NOTE: body never awaited here — decision is made on headers alone.
            seen.append({"method": method, "name": name})
            if name == "forbidden_tool":
                response = JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32001, "message": f"policy denied {method}/{name}"},
                    },
                    status_code=403,
                )
                return await response(scope, receive, send)
            return await self.app(scope, receive, send)

    guarded = PolicyMiddleware(app)

    with TestClient(guarded, base_url="http://127.0.0.1:8765") as client:
        # C1 — task-shaped result from tools/call
        r = post(client, "tools/call", envelope({"name": "start_run", "arguments": {}}), name="start_run")
        payload = r.json()
        result = payload.get("result", {})
        ok = (
            "error" not in payload
            and result.get("resultType") == "task"
            and result.get("taskId") == TASK_SEED["taskId"]
            and result.get("status") == "working"
            and result.get("pollIntervalMs") == 5000
        )
        record(
            "C1 tools/call returns SEP-2663 CreateTaskResult unsieved over the wire",
            ok,
            json.dumps(payload)[:400],
        )

        # C2 — the three tasks/* methods dispatch
        for method in ("tasks/get", "tasks/update", "tasks/cancel"):
            resp = post(client, method, envelope({"taskId": TASK_SEED["taskId"]}))
            body = resp.json()
            good = "error" not in body and body.get("result", {}).get("taskId") == TASK_SEED["taskId"]
            record(f"C2 {method} registers and dispatches", good, json.dumps(body)[:250])

        # C5 — policy denial on headers alone, before body parse
        denied = post(
            client, "tools/call", envelope({"name": "forbidden_tool", "arguments": {}}), name="forbidden_tool"
        )
        ok5 = denied.status_code == 403 and denied.json()["error"]["code"] == -32001
        record(
            "C5 ASGI middleware denies on Mcp-Method/Mcp-Name pre-parse",
            ok5,
            f"status={denied.status_code} body={json.dumps(denied.json())[:200]}",
        )
        record(
            "C5b middleware observed routing headers without reading the body",
            all(s["method"] for s in seen),
            f"observed: {seen}",
        )


# ---------------------------------------------------------------- C6
def check_intercept_path() -> None:
    """The extension-faithful start path: an Extension.intercept_tool_call that
    short-circuits tools/call with a CreateTaskResult, composed onto the LOWLEVEL
    Server (which has no `extensions=` parameter) via compose_tool_call_handler."""
    from mcp.server.extension import Extension, compose_tool_call_handler

    class TasksExtension(Extension):
        identifier = "io.modelcontextprotocol/tasks"

        async def intercept_tool_call(self, params, ctx, call_next):  # noqa: ANN001
            # Server-directed: decide per-request to materialize a task.
            return dict(TASK_SEED)

    async def real_handler(ctx, params):  # noqa: ANN001
        from mcp_types import CallToolResult, TextContent

        return CallToolResult(content=[TextContent(type="text", text="sync result")])

    composed = compose_tool_call_handler([TasksExtension()], real_handler)

    async def on_list_tools(ctx):  # noqa: ANN001
        from mcp_types import Tool

        return [Tool(name="start_run", description="s", inputSchema={"type": "object", "properties": {}})]

    server = Server("spike2", version="0.0.0", on_list_tools=on_list_tools, on_call_tool=composed)
    app = server.streamable_http_app(json_response=True, stateless_http=True, host="127.0.0.1")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        r = post(client, "tools/call", envelope({"name": "start_run", "arguments": {}}), name="start_run")
        payload = r.json()
        result = payload.get("result", {})
        ok = "error" not in payload and result.get("resultType") == "task" and result.get("taskId")
        record(
            "C6 Extension.intercept_tool_call short-circuits tools/call with CreateTaskResult "
            "on the LOWLEVEL Server via compose_tool_call_handler",
            bool(ok),
            json.dumps(payload)[:400],
        )


if __name__ == "__main__":
    print(f"mcp version: 2.0.0  |  protocol: {PROTOCOL_VERSION}\n" + "=" * 78 + "\n")
    check_method_binding()
    check_no_preparse_hook()
    check_wire()
    check_intercept_path()
    print("=" * 78)
    failed = [c for c, ok, _ in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} claims passed")
    if failed:
        print("FAILED: " + "; ".join(failed))

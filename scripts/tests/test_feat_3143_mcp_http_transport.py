"""Tests for FEAT-3143: `ll-mcp` streamable HTTP transport alongside stdio.

Drives `Server.streamable_http_app()` (what `run_http()` builds) over Starlette's
`TestClient` — no real socket, no `uvicorn.Server` — mirroring how
`.ll/learning-tests/mcp-http-transport.md` proved the transport. `TestClient` (unlike a bare
`httpx.ASGITransport`) drives the ASGI `lifespan` protocol on `__enter__`/`__exit__`, which is
what actually enters `session_manager.run()` — `streamable_http_app()` wires that entry via
`lifespan=lambda app: session_manager.run()`, so skipping it fails every request with
"Task group is not initialized". Skips entirely when the `mcp` extra isn't installed.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402
from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from little_loops.mcp_server import main_mcp  # noqa: E402
from little_loops.mcp_server.server import build_server, run_http, run_stdio  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"


def _make_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _envelope() -> dict:
    return {
        "_meta": {
            PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
            CLIENT_CAPABILITIES_META_KEY: {},
        }
    }


def _post(client: TestClient, method: str, params: dict, *, include_mcp_method: bool = True):
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": PROTOCOL_VERSION,
    }
    if include_mcp_method:
        headers["mcp-method"] = method
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return client.post("/mcp", json=body, headers=headers)


def test_run_http_defaults_to_loopback_not_public() -> None:
    """Acceptance criterion: bind interface is explicit and never `0.0.0.0` by default."""
    default_host = inspect.signature(run_http).parameters["host"].default
    assert default_host == "127.0.0.1"
    assert default_host != "0.0.0.0"


def test_build_server_signature_unchanged() -> None:
    """Acceptance criterion: `build_server()` is unchanged by this issue."""
    assert inspect.signature(build_server).parameters == {}


def test_http_tools_list_matches_stdio_path(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    server = build_server()

    async def stdio_names() -> list[str]:
        async with Client(server) as stdio_client:
            return [t.name for t in (await stdio_client.list_tools()).tools]

    expected_names = anyio.run(stdio_names)

    app = server.streamable_http_app(json_response=True, stateless_http=True, host="127.0.0.1")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = _post(client, "tools/list", _envelope())
        assert response.status_code == 200
        payload = response.json()
        assert "error" not in payload, payload
        http_names = [t["name"] for t in payload["result"]["tools"]]
        assert http_names == expected_names
        # SEP-2549 cache hints still come through on the HTTP path.
        assert payload["result"]["cacheScope"] == "public"


def test_http_resources_and_prompts_list_succeed(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    server = build_server()
    app = server.streamable_http_app(json_response=True, stateless_http=True, host="127.0.0.1")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        resources_response = _post(client, "resources/list", _envelope())
        assert "error" not in resources_response.json(), resources_response.json()

        prompts_response = _post(client, "prompts/list", _envelope())
        assert "error" not in prompts_response.json(), prompts_response.json()


def test_http_missing_mcp_method_header_is_rejected(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    server = build_server()
    app = server.streamable_http_app(json_response=True, stateless_http=True, host="127.0.0.1")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = _post(client, "tools/list", _envelope(), include_mcp_method=False)
        payload = response.json()
        assert payload["error"]["code"] == -32020


def test_main_mcp_default_selects_stdio(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))
    rc = main_mcp([])
    assert rc == 0
    assert calls == [run_stdio]


def test_main_mcp_http_flag_selects_http(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))
    rc = main_mcp(["--http"])
    assert rc == 0
    assert calls == [run_http]


def test_main_mcp_env_var_selects_http(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))
    monkeypatch.setenv("LL_MCP_TRANSPORT", "http")
    rc = main_mcp([])
    assert rc == 0
    assert calls == [run_http]

"""Tests for FEAT-3149 AC 5: per-method transport policy over HTTP.

The mechanism is ASGI middleware wrapped around `Server.streamable_http_app()`, not an SDK
pre-parse hook — `mcp==2.0.0` has none (Open Question 1, proven by
`.ll/learning-tests/mcp-header-routing.md`). These tests assert the three things that
substitution requires: the deny decision is reached from `Mcp-Method`/`Mcp-Name` on the raw
ASGI scope **without awaiting the request body**, the denial is a JSON-RPC error object, and
tier-1 reads keep working on the same server instance.

Reuses `test_feat_3143_mcp_http_transport.py`'s raw-JSON-RPC `_envelope()`/`_post()` shape
rather than the SDK `Client`, because the policy decision keys off transport headers the
in-memory client never emits.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from little_loops.mcp_server.server import build_http_app, build_server  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"


def _make_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, allow_http_mutations: bool | None = None
) -> Path:
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".issues" / "features" / "P2-FEAT-501-sample.md").write_text(
        "---\nid: FEAT-501\ntitle: 'Sample'\ntype: FEAT\npriority: P2\nstatus: open\n---\n\n"
        "# FEAT-501: Sample\n",
        encoding="utf-8",
    )
    (tmp_path / ".ll").mkdir(exist_ok=True)
    config: dict = {"project": {"name": "fixture"}}
    if allow_http_mutations is not None:
        config["mcp"] = {"transport_policy": {"http": {"allow_mutations": allow_http_mutations}}}
    (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _envelope() -> dict:
    return {
        "_meta": {
            PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
            CLIENT_CAPABILITIES_META_KEY: {},
        }
    }


def _call_tool(client: TestClient, name: str, arguments: dict):
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": "tools/call",
        "mcp-name": name,
    }
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments, **_envelope()},
    }
    return client.post("/mcp", json=body, headers=headers)


def test_build_server_signature_still_unchanged() -> None:
    """AC 6: the policy hook is additive and must not reach `build_server()`'s signature."""
    assert inspect.signature(build_server).parameters == {}


def test_ac5_mutating_call_is_refused_while_reads_still_succeed(tmp_path, monkeypatch) -> None:
    """Deny-configured HTTP transport: mutation refused, `issues_query` unaffected."""
    tmp_path = _make_project(tmp_path, monkeypatch, allow_http_mutations=False)
    before = (tmp_path / ".issues" / "features" / "P2-FEAT-501-sample.md").read_bytes()

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        denied = _call_tool(
            client, "issue_set_status", {"issue_id": "FEAT-501", "status": "done", "apply": True}
        )
        assert denied.status_code == 403
        payload = denied.json()
        # The denial is a JSON-RPC error object, so a compliant client surfaces it as a
        # protocol error rather than an opaque transport failure.
        assert payload["jsonrpc"] == "2.0"
        assert "error" in payload, payload
        assert isinstance(payload["error"]["code"], int)
        assert "issue_set_status" in payload["error"]["message"]
        assert "result" not in payload

        allowed = _call_tool(client, "issues_query", {})
        assert allowed.status_code == 200
        assert "error" not in allowed.json(), allowed.json()

    assert (tmp_path / ".issues" / "features" / "P2-FEAT-501-sample.md").read_bytes() == before


def test_ac5_default_config_denies_http_mutations(tmp_path, monkeypatch) -> None:
    """No `mcp` config section at all → HTTP mutations denied (deny-by-default posture)."""
    _make_project(tmp_path, monkeypatch, allow_http_mutations=None)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _call_tool(client, "issue_capture", {"type": "BUG", "title": "x"})
        assert response.status_code == 403
        assert "error" in response.json()


def test_ac5_opting_in_allows_the_same_call(tmp_path, monkeypatch) -> None:
    """`http.allow_mutations: true` lets the mutating call through to the handler."""
    _make_project(tmp_path, monkeypatch, allow_http_mutations=True)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _call_tool(
            client, "issue_set_status", {"issue_id": "FEAT-501", "status": "done"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert "error" not in payload, payload
        result = json.loads(payload["result"]["content"][0]["text"])
        assert result["applied"] is False  # dry-run default still applies


def test_ac5_denial_never_awaits_the_request_body(tmp_path, monkeypatch) -> None:
    """The deny decision comes from headers alone — `receive()` is never awaited.

    Calls the middleware directly as a raw ASGI app so `receive` can be instrumented; the
    Starlette `TestClient` path above cannot observe whether the body was consumed.
    """
    _make_project(tmp_path, monkeypatch, allow_http_mutations=False)

    import anyio

    received: list[str] = []
    sent: list[dict] = []

    async def receive() -> dict:
        received.append("awaited")
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def inner_app(scope, receive_, send_):  # pragma: no cover - must not be reached
        raise AssertionError("denied request reached the wrapped MCP app")

    from little_loops.mcp_server.policy import TransportPolicyMiddleware

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [
            (b"content-type", b"application/json"),
            (b"mcp-method", b"tools/call"),
            (b"mcp-name", b"issue_set_status"),
        ],
    }

    anyio.run(lambda: TransportPolicyMiddleware(inner_app)(scope, receive, send))

    assert received == [], "the policy guard awaited the request body before deciding"
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 403
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert "error" in json.loads(body)


def test_ac5_non_mutating_method_passes_through_untouched(tmp_path, monkeypatch) -> None:
    """Only `tools/call` for a mutating tool is gated; everything else is forwarded."""
    _make_project(tmp_path, monkeypatch, allow_http_mutations=False)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        for method in ("tools/list", "resources/list", "prompts/list"):
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": _envelope()},
                headers={
                    "content-type": "application/json",
                    "accept": "application/json, text/event-stream",
                    "mcp-protocol-version": PROTOCOL_VERSION,
                    "mcp-method": method,
                },
            )
            assert response.status_code == 200, method
            assert "error" not in response.json(), (method, response.json())


def test_ac5_stdio_transport_defaults_to_allowing_mutations(tmp_path, monkeypatch) -> None:
    """Policy layer, not middleware: stdio is a same-machine channel and defaults open."""
    _make_project(tmp_path, monkeypatch, allow_http_mutations=None)

    from little_loops.config import BRConfig
    from little_loops.mcp_server.policy import check_tool_call

    config = BRConfig(tmp_path)
    assert check_tool_call("stdio", "tools/call", "issue_set_status", config=config).allowed
    assert not check_tool_call("http", "tools/call", "issue_set_status", config=config).allowed
    assert check_tool_call("http", "tools/call", "issues_query", config=config).allowed

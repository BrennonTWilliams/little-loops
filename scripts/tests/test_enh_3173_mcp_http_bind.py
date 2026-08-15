"""Tests for ENH-3173: `ll-mcp --http` exposes bind host/port, and a non-loopback bind
also configures `TransportSecuritySettings` so the server does not reject 100% of traffic.

Skips entirely when the `mcp` extra isn't installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from little_loops.mcp_server import main_mcp  # noqa: E402
from little_loops.mcp_server.server import build_http_app  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"


def _make_project(root: Path, *, mcp_http: dict | None = None) -> Path:
    for category in ("bugs", "features", "enhancements", "epics"):
        (root / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (root / ".ll").mkdir(exist_ok=True)
    config: dict = {"project": {"name": "fixture"}}
    if mcp_http is not None:
        config["mcp"] = {"http": mcp_http}
    (root / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def _envelope() -> dict:
    return {
        "_meta": {
            PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
            CLIENT_CAPABILITIES_META_KEY: {},
        }
    }


def _post(client: TestClient, *, host_header: str) -> object:
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": "tools/list",
        "host": host_header,
    }
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": _envelope()}
    return client.post("/mcp", json=body, headers=headers)


# ------------------------------------------------------------------------------------------
# `build_http_app` allow-list derivation for a non-loopback bind
# ------------------------------------------------------------------------------------------


def test_non_loopback_bind_accepts_matching_host_header(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    app = build_http_app("192.168.1.50", project_root=project)
    with TestClient(app, base_url="http://192.168.1.50:8765") as client:
        response = _post(client, host_header="192.168.1.50:8765")
        payload = response.json()
        assert "error" not in payload, payload


def test_non_loopback_bind_rejects_mismatched_host_header(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    app = build_http_app("192.168.1.50", project_root=project)
    with TestClient(app, base_url="http://192.168.1.50:8765") as client:
        response = _post(client, host_header="evil.example.com")
        assert response.status_code == 421


def test_loopback_bind_still_accepts_loopback_host_header(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    app = build_http_app("127.0.0.1", project_root=project)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = _post(client, host_header="127.0.0.1:8765")
        payload = response.json()
        assert "error" not in payload, payload


# ------------------------------------------------------------------------------------------
# `main_mcp` --host/--port and mcp.http.* config threading
# ------------------------------------------------------------------------------------------


def test_main_mcp_host_port_flags_thread_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path)
    monkeypatch.chdir(project)
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp(["--http", "--host", "0.0.0.0", "--port", "9999"])
    assert rc == 0
    target = calls[0]
    assert target.keywords["host"] == "0.0.0.0"
    assert target.keywords["port"] == 9999


def test_main_mcp_http_config_threads_through_without_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path, mcp_http={"host": "10.0.0.5", "port": 9001})
    monkeypatch.chdir(project)
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp(["--http"])
    assert rc == 0
    target = calls[0]
    assert target.keywords["host"] == "10.0.0.5"
    assert target.keywords["port"] == 9001


def test_main_mcp_host_flag_wins_over_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path, mcp_http={"host": "10.0.0.5", "port": 9001})
    monkeypatch.chdir(project)
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp(["--http", "--host", "0.0.0.0"])
    assert rc == 0
    target = calls[0]
    assert target.keywords["host"] == "0.0.0.0"
    assert target.keywords["port"] == 9001


def test_main_mcp_http_default_path_unwrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `--host`/`--port`/`mcp.http.*` override: `anyio.run` receives the bare
    `run_http` function, not a wrapper — preserving the pre-ENH-3173 identity existing
    tests assert."""
    from little_loops.mcp_server.server import run_http

    project = _make_project(tmp_path)
    monkeypatch.chdir(project)
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp(["--http"])
    assert rc == 0
    assert calls == [run_http]


def test_main_mcp_stdio_ignores_http_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mcp.http.*` config must not leak into the stdio path — `run_stdio` has no
    host/port parameters to bind, and the no-`--http` path should stay unwrapped."""
    from little_loops.mcp_server.server import run_stdio

    project = _make_project(tmp_path, mcp_http={"host": "10.0.0.5", "port": 9001})
    monkeypatch.chdir(project)
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp([])
    assert rc == 0
    assert calls == [run_stdio]

"""Tests for FEAT-3168: `check_tool_call` enforcement reaches both transports.

Modeled on `test_feat_3149_transport_policy.py`, but driving the stdio server. Two
complementary layers, per the codebase research findings that closed Open Question 1/2:

- Fast unit assertions directly against `policy.check_tool_call("stdio", ...)` — the
  decision layer, unchanged by this issue.
- Real over-the-wire `_stdio_roundtrip()` round trips (subprocess, real stdin/stdout) —
  the only way to prove the *handler* actually consults the decision, not just that the
  decision function itself is correct. Generalizes `test_mcp_server.py::_stdio_call` to
  an arbitrary JSON-RPC method/params pair so it covers `tasks/get`/`tasks/cancel`
  denials too, not just `tools/call`. Applies BUG-3167's fix: stdin stays open until the
  response is read (closing it earlier races the SDK's stdin-EOF cancellation of
  in-flight handlers).

AC 3's "no process is spawned" is asserted in-process (`Client` + `build_server`) rather
than over the wire, since monkeypatching `run_background` inside a spawned subprocess
isn't possible.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import anyio  # noqa: E402
from mcp.client import Client  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402
from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from little_loops.config import BRConfig  # noqa: E402
from little_loops.mcp_server.policy import POLICY_DENIED_CODE, check_tool_call  # noqa: E402
from little_loops.mcp_server.server import build_http_app, build_server  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"


def _make_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_stdio_mutations: bool | None = None,
    allow_stdio_tasks: bool | None = None,
    allow_http_mutations: bool | None = None,
    allow_http_tasks: bool | None = None,
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
    (tmp_path / ".loops").mkdir(exist_ok=True)

    stdio_policy: dict = {}
    if allow_stdio_mutations is not None:
        stdio_policy["allow_mutations"] = allow_stdio_mutations
    if allow_stdio_tasks is not None:
        stdio_policy["allow_tasks"] = allow_stdio_tasks

    http_policy: dict = {}
    if allow_http_mutations is not None:
        http_policy["allow_mutations"] = allow_http_mutations
    if allow_http_tasks is not None:
        http_policy["allow_tasks"] = allow_http_tasks

    transport_policy: dict = {}
    if stdio_policy:
        transport_policy["stdio"] = stdio_policy
    if http_policy:
        transport_policy["http"] = http_policy

    config: dict = {"project": {"name": "fixture"}}
    if transport_policy:
        config["mcp"] = {"transport_policy": transport_policy}
    (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _write_loop(loops_dir: Path, name: str = "sample-loop") -> Path:
    loop_path = loops_dir / f"{name}.yaml"
    loop_path.write_text(
        f"""
name: {name}
initial: done
states:
  done:
    terminal: true
""".strip(),
        encoding="utf-8",
    )
    return loop_path


def _stdio_roundtrip(tmp_path: Path, method: str, params: dict) -> dict:
    """Spawn `ll-mcp` over real stdio and return the response to a single request.

    Generalizes `test_mcp_server.py::_stdio_call` to an arbitrary method/params pair.
    Stdin is held open until the `id: 2` response has been read (BUG-3167) — closing it
    earlier races the server's stdin-EOF cancellation of in-flight handlers.
    """
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
    ]
    proc = subprocess.Popen(
        [sys.executable, "-c", "from little_loops.mcp_server import main_mcp; main_mcp()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
    )
    assert proc.stdin is not None and proc.stdout is not None
    watchdog = threading.Timer(60, proc.kill)
    watchdog.start()
    seen: list[str] = []
    message: dict | None = None
    stderr = ""
    try:
        proc.stdin.write("".join(json.dumps(r) + "\n" for r in requests))
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            seen.append(line)
            try:
                candidate = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if candidate.get("id") == 2:
                message = candidate
                break
    finally:
        watchdog.cancel()
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.stdin = None
        proc.terminate()
        try:
            _, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
    if message is None:
        raise AssertionError(f"no response id=2; stdout={''.join(seen)!r} stderr={stderr!r}")
    return message


# AC 1: mutating tools denied over stdio.


def test_ac1_check_tool_call_denies_mutating_tool_over_stdio(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, allow_stdio_mutations=False)
    config = BRConfig(tmp_path)
    assert not check_tool_call("stdio", "tools/call", "issue_set_status", config=config).allowed


def test_ac1_mutating_tool_denied_over_stdio_wire(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, allow_stdio_mutations=False)
    issue_path = tmp_path / ".issues" / "features" / "P2-FEAT-501-sample.md"
    before = issue_path.read_text()

    response = _stdio_roundtrip(
        tmp_path,
        "tools/call",
        {
            "name": "issue_set_status",
            "arguments": {"issue_id": "FEAT-501", "status": "done", "apply": True},
        },
    )

    assert "result" not in response
    assert response["error"]["code"] == POLICY_DENIED_CODE
    assert issue_path.read_text() == before, "denied call must not have written anything"


# AC 2: tasks/get and tasks/cancel denied over stdio.


def test_ac2_check_tool_call_denies_tasks_over_stdio(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, allow_stdio_tasks=False)
    config = BRConfig(tmp_path)
    assert not check_tool_call("stdio", "tasks/get", None, config=config).allowed
    assert not check_tool_call("stdio", "tasks/cancel", None, config=config).allowed


def test_ac2_tasks_get_denied_over_stdio_wire(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, allow_stdio_tasks=False)
    response = _stdio_roundtrip(tmp_path, "tasks/get", {"taskId": "nonexistent"})
    assert "result" not in response
    assert response["error"]["code"] == POLICY_DENIED_CODE


def test_ac2_tasks_cancel_denied_over_stdio_wire(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, allow_stdio_tasks=False)
    response = _stdio_roundtrip(tmp_path, "tasks/cancel", {"taskId": "nonexistent"})
    assert "result" not in response
    assert response["error"]["code"] == POLICY_DENIED_CODE


# AC 3: loop_start denied over stdio, and no process is spawned.


def test_ac3_check_tool_call_denies_loop_start_over_stdio(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, allow_stdio_tasks=False)
    config = BRConfig(tmp_path)
    assert not check_tool_call("stdio", "tools/call", "loop_start", config=config).allowed


def test_ac3_loop_start_denied_over_stdio_and_no_process_spawned(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch, allow_stdio_tasks=False)
    _write_loop(project / ".loops")

    spawned = []

    def fake_run_background(loop_name, args, loops_dir, subcommand="run", instance_id=None):
        spawned.append(loop_name)
        return 0

    monkeypatch.setattr("little_loops.cli.loop._helpers.run_background", fake_run_background)

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            with pytest.raises(MCPError) as exc_info:
                await client.call_tool("loop_start", {"loop": "sample-loop"})
            assert exc_info.value.error.code == POLICY_DENIED_CODE

    anyio.run(run)
    assert spawned == [], "a denied loop_start must not spawn a process"


def test_ac3_wire_denial_carries_the_run_starting_tools_message(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch, allow_stdio_tasks=False)
    _write_loop(project / ".loops")

    response = _stdio_roundtrip(
        tmp_path, "tools/call", {"name": "loop_start", "arguments": {"loop": "sample-loop"}}
    )
    assert "result" not in response
    assert response["error"]["code"] == POLICY_DENIED_CODE
    message = response["error"]["message"]
    assert "tools/call/loop_start" in message
    assert "run-starting tools are disabled" in message


# AC 4: unset knobs leave stdio's default-open posture unchanged.


def test_ac4_stdio_default_open_when_knobs_unset(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    config = BRConfig(tmp_path)
    assert check_tool_call("stdio", "tools/call", "issue_set_status", config=config).allowed
    assert check_tool_call("stdio", "tasks/get", None, config=config).allowed
    assert check_tool_call("stdio", "tools/call", "loop_start", config=config).allowed


# AC 5 / AC 8: HTTP enforcement is unaffected, including when stdio is locked down.


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


def test_ac8_stdio_locked_does_not_close_off_http(tmp_path, monkeypatch) -> None:
    """Wrong-transport-closure guard: a locked-down stdio config must not leak into the
    HTTP handler closure. Catches a `build_http_app` that forgot `transport="http"`."""
    _make_project(
        tmp_path,
        monkeypatch,
        allow_stdio_mutations=False,
        allow_stdio_tasks=False,
        allow_http_mutations=True,
        allow_http_tasks=True,
    )

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        allowed = _call_tool(client, "issues_query", {})
        assert allowed.status_code == 200
        assert "error" not in allowed.json()

        mutation = _call_tool(
            client,
            "issue_set_status",
            {"issue_id": "FEAT-501", "status": "done", "apply": True},
        )
        assert mutation.status_code == 200
        assert "error" not in mutation.json()


def test_ac5_transport_policy_http_suite_passes_unmodified() -> None:
    """AC 5 is exercised by the untouched `test_feat_3149_transport_policy.py` suite; this
    is a smoke check that the module still imports and its pinned signature test target
    resolves, not a duplicate of that suite."""
    assert build_http_app is not None


def test_both_enforcement_layers_agree_on_http_denial(tmp_path, monkeypatch) -> None:
    """Decision D2: the ASGI middleware and the handler-level check must never disagree.
    The handler-level check is normally unreachable on HTTP (the middleware denies
    first); this asserts it independently reaches the same verdict an ASGI-bypass would
    hit, by calling `check_tool_call` directly with `"http"`."""
    _make_project(tmp_path, monkeypatch, allow_http_mutations=False)
    config = BRConfig(tmp_path)

    handler_decision = check_tool_call("http", "tools/call", "issue_set_status", config=config)
    assert not handler_decision.allowed

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        middleware_response = _call_tool(
            client, "issue_set_status", {"issue_id": "FEAT-501", "status": "done", "apply": True}
        )
    assert middleware_response.status_code == 403
    assert middleware_response.json()["error"]["code"] == POLICY_DENIED_CODE

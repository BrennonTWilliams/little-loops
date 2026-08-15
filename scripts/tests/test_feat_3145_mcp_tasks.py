"""Tests for FEAT-3145: the `tasks/get` + `tasks/cancel` poll surface.

`add_request_handler`-registered methods aren't reachable via `mcp.client.Client`'s typed
tool-call surface, so these post raw JSON-RPC bodies through `starlette.testclient.TestClient`
wrapping `build_http_app()` — the same shape `test_feat_3143_mcp_http_transport.py` and
`test_feat_3149_transport_policy.py` use. `http.allow_tasks: true` is set on every fixture
project here so the transport-policy gate itself (covered by
`test_feat_3149_transport_policy.py`) doesn't interfere with these handler-behavior tests.

The poll path is a disk read, so no real `ll-loop` run is needed: tests write a
`<instance_id>.state.json` fixture directly, matching the pattern
`test_fsm_persistence.py`'s reconciliation tests use.
"""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402
from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from little_loops.mcp_server.server import build_http_app, build_server  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"


def _make_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps({"mcp": {"transport_policy": {"http": {"allow_tasks": True}}}}),
        encoding="utf-8",
    )
    return tmp_path


def _write_state(tmp_path: Path, instance_id: str, **overrides) -> Path:
    running_dir = tmp_path / ".loops" / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "loop_name": "sample-loop",
        "current_state": "done",
        "iteration": 3,
        "captured": {"foo": {"output": "bar"}},
        "prev_result": None,
        "last_result": None,
        "started_at": "2026-08-11T10:00:00Z",
        "updated_at": "2026-08-11T10:05:00Z",
        "status": "running",
        "accumulated_ms": 12345,
    }
    data.update(overrides)
    state_file = running_dir / f"{instance_id}.state.json"
    state_file.write_text(json.dumps(data), encoding="utf-8")
    return running_dir


def _envelope() -> dict:
    return {
        "_meta": {
            PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
            CLIENT_CAPABILITIES_META_KEY: {},
        }
    }


def _post_method(client: TestClient, method: str, params: dict):
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**params, **_envelope()}}
    return client.post("/mcp", json=body, headers=headers)


def test_ac1_live_pid_reconciled_before_reporting_running(tmp_path, monkeypatch) -> None:
    """A dead process behind a `running` state file is reported not-running (Decision 1)."""
    _make_project(tmp_path, monkeypatch)
    running_dir = _write_state(tmp_path, "run-1", status="running")
    (running_dir / "run-1.pid").write_text("99999999")
    monkeypatch.setattr("little_loops.fsm.persistence._process_alive", lambda pid: False)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post_method(client, "tasks/get", {"taskId": "run-1"})
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["status"] != "working"
        assert result["runStatus"] != "running"


def test_ac2_completed_run_returns_execution_result_shape(tmp_path, monkeypatch) -> None:
    """A completed run's result carries the ExecutionResult.to_dict() field set."""
    _make_project(tmp_path, monkeypatch)
    _write_state(
        tmp_path,
        "run-2",
        status="completed",
        current_state="finish",
        iteration=7,
        captured={"x": {"output": "y"}},
        accumulated_ms=4200,
    )

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post_method(client, "tasks/get", {"taskId": "run-2"})
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["status"] == "completed"
        assert result["final_state"] == "finish"
        assert result["iterations"] == 7
        assert result["duration_ms"] == 4200
        assert result["captured"] == {"x": {"output": "y"}}
        assert "terminated_by" in result


def test_ac3_unknown_task_id_is_not_found_not_a_default_running_shape(
    tmp_path, monkeypatch
) -> None:
    """AC 3: an unresolvable taskId is a distinct error, never an empty `running` shape."""
    _make_project(tmp_path, monkeypatch)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post_method(client, "tasks/get", {"taskId": "does-not-exist"})
        assert response.status_code == 200
        payload = response.json()
        assert "result" not in payload
        assert payload["error"]["code"] == -32002


def test_ac4_cancel_reports_cancelled_resumable_and_raw_run_status(tmp_path, monkeypatch) -> None:
    """AC 4: cancel's result carries all three fields as separate assertions (Decision 3)."""
    _make_project(tmp_path, monkeypatch)
    running_dir = _write_state(tmp_path, "run-4", status="running")
    (running_dir / "run-4.pid").write_text("99999999")
    # Alive on the initial check, dead on the first _kill_with_timeout poll.
    alive_seq = iter([True, False])
    monkeypatch.setattr(
        "little_loops.cli.loop.lifecycle._process_alive", lambda pid: next(alive_seq)
    )
    monkeypatch.setattr("little_loops.cli.loop.lifecycle.os.getpgid", lambda pid: 77)
    monkeypatch.setattr("little_loops.cli.loop.lifecycle.os.killpg", lambda pgid, sig: None)
    monkeypatch.setattr("little_loops.cli.loop.lifecycle.time.sleep", lambda s: None)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post_method(client, "tasks/cancel", {"taskId": "run-4"})
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["status"] == "cancelled"
        assert result["resumable"] is True
        assert result["runStatus"] == "user_stopped"


def test_ac10_capabilities_do_not_advertise_the_tasks_extension(tmp_path, monkeypatch) -> None:
    """AC 10: `initialize`'s capabilities never mention io.modelcontextprotocol/tasks."""
    _make_project(tmp_path, monkeypatch)
    server = build_server(transport="stdio")

    async def get_caps() -> str:
        async with Client(server) as client:
            return client.server_capabilities.model_dump_json()

    caps_json = anyio.run(get_caps)
    assert "io.modelcontextprotocol/tasks" not in caps_json


def test_ac12_no_module_touched_by_this_issue_can_spawn_a_run(tmp_path, monkeypatch) -> None:
    """AC 12: nothing in the tasks/* dispatch path imports the start-path helpers."""
    import little_loops.mcp_server.tasks as tasks_module

    source = Path(tasks_module.__file__).read_text(encoding="utf-8")
    assert "run_background" not in source
    assert "run_foreground" not in source

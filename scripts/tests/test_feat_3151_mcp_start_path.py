"""Tests for FEAT-3151: the SEP-2663 start path — `loop_start` materializes a task and
starts a detached `ll-loop` run.

Modeled on `test_feat_3143_mcp_http_transport.py`'s raw `_envelope()`/`_post()` helpers,
not `mcp.client.Client`'s typed surface: AC 2's declared-vs-undeclared client-capability
distinction requires control over `_meta`, which the typed client does not expose (and,
per `tools.py:780`'s comment, negotiates the legacy handshake down regardless).
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from little_loops.fsm.concurrency import _process_alive  # noqa: E402
from little_loops.mcp_server.server import build_http_app  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"


def _make_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, allow_tasks: bool = True
) -> Path:
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps({"mcp": {"transport_policy": {"http": {"allow_tasks": allow_tasks}}}}),
        encoding="utf-8",
    )
    (tmp_path / ".loops").mkdir(exist_ok=True)
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


def _write_long_running_loop(loops_dir: Path, name: str = "slow-loop") -> Path:
    """A loop whose first state outlasts any plausible request, so AC 3 can observe the
    spawned process still alive after the response comes back."""
    loop_path = loops_dir / f"{name}.yaml"
    loop_path.write_text(
        f"""
name: {name}
initial: wait
states:
  wait:
    action_type: shell
    action: "sleep 120"
    next: done
  done:
    terminal: true
""".strip(),
        encoding="utf-8",
    )
    return loop_path


def _reap(pid_file: Path) -> None:
    """Kill a spawned run's whole process group. `run_background` uses
    `start_new_session=True`, so the child is a session leader with PGID == PID."""
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text())
    except ValueError:
        return
    with contextlib.suppress(OSError):
        os.killpg(os.getpgid(pid), signal.SIGKILL)


def _meta(*, declare_ext: bool, protocol_version: str = PROTOCOL_VERSION) -> dict:
    caps: dict = {"extensions": {"io.modelcontextprotocol/tasks": {}}} if declare_ext else {}
    return {PROTOCOL_VERSION_META_KEY: protocol_version, CLIENT_CAPABILITIES_META_KEY: caps}


def _start_params(
    *,
    loop: str = "sample-loop",
    declare_ext: bool = False,
    want_task: bool = False,
    protocol_version: str = PROTOCOL_VERSION,
) -> dict:
    params: dict = {
        "name": "loop_start",
        "arguments": {"loop": loop},
        "_meta": _meta(declare_ext=declare_ext, protocol_version=protocol_version),
    }
    if want_task:
        params["task"] = {"ttl": 60000}
    return params


@pytest.fixture
def stub_spawn(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace `run_background`'s real detached spawn with the two observable effects the
    result-shape tests actually depend on: a return code and a PID file.

    The shape tests (ACs 1/2/2b/2c) are about the *envelope* `TasksExtension` puts around
    an already-successful start — nothing in them is made truer by really forking a Python
    interpreter, and doing so leaves detached children racing pytest's `tmp_path` teardown.
    The un-mocked spawn belongs to `test_ac3_*`, which is the AC that asserts something
    about the real process.

    Returns the list of `instance_id`s the tool asked to spawn.
    """
    spawned: list[str] = []

    def fake_run_background(loop_name, args, loops_dir, subcommand="run", instance_id=None):
        spawned.append(instance_id)
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True, exist_ok=True)
        # Mirrors the real parent: PID file written before returning, state file left to
        # the child (FEAT-3151 Decision 9's window).
        (running_dir / f"{instance_id}.pid").write_text(str(os.getpid()))
        return 0

    monkeypatch.setattr("little_loops.cli.loop._helpers.run_background", fake_run_background)
    return spawned


def _post(
    client: TestClient,
    method: str,
    params: dict,
    *,
    tool_name: str | None = None,
    protocol_version: str = PROTOCOL_VERSION,
):
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": protocol_version,
        "mcp-method": method,
    }
    if tool_name is not None:
        headers["mcp-name"] = tool_name
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return client.post("/mcp", json=body, headers=headers)


def test_ac1_declared_and_task_returns_task_shaped_result(
    tmp_path, monkeypatch, stub_spawn
) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=True, want_task=True),
            tool_name="loop_start",
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["resultType"] == "task"
        assert result["status"] == "working"
        assert result["taskId"]


def test_ac2_undeclared_client_gets_ordinary_result_with_instance_id(
    tmp_path, monkeypatch, stub_spawn
) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=False, want_task=True),
            tool_name="loop_start",
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "resultType" not in result or result["resultType"] != "task"
        payload = json.loads(result["content"][0]["text"])
        assert payload["instance_id"]


def test_ac2b_declared_but_no_task_param_gets_ordinary_result(
    tmp_path, monkeypatch, stub_spawn
) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=True, want_task=False),
            tool_name="loop_start",
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "resultType" not in result or result["resultType"] != "task"
        payload = json.loads(result["content"][0]["text"])
        assert payload["instance_id"]


def test_ac2c_legacy_protocol_version_gets_ordinary_result(
    tmp_path, monkeypatch, stub_spawn
) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(
                declare_ext=True, want_task=True, protocol_version=LEGACY_PROTOCOL_VERSION
            ),
            tool_name="loop_start",
            protocol_version=LEGACY_PROTOCOL_VERSION,
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "resultType" not in result or result["resultType"] != "task"
        payload = json.loads(result["content"][0]["text"])
        assert payload["instance_id"]


def test_ac3b_scope_conflict_returns_tool_error_never_a_task_id(tmp_path, monkeypatch) -> None:
    """When `run_background()` fails before spawning, no instance_id is ever returned."""
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    def fake_run_background(loop_name, args, loops_dir, subcommand="run", instance_id=None):
        import sys

        print("Scope conflict with running loop: other-loop", file=sys.stderr)
        return 1

    monkeypatch.setattr("little_loops.cli.loop._helpers.run_background", fake_run_background)

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=True, want_task=True),
            tool_name="loop_start",
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert result["isError"] is True
        assert result.get("structuredContent") is None
        assert "Scope conflict" in result["content"][0]["text"]


def test_ac5_denied_over_http_when_allow_tasks_false(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch, allow_tasks=False)
    _write_loop(project / ".loops")

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=True, want_task=True),
            tool_name="loop_start",
        )
        assert response.status_code == 403
        payload = response.json()
        assert payload["error"]["code"] == -32001
        # The denial names the surface that was actually denied. `loop_start` and `tasks/*`
        # share the `allow_tasks` grant, but a `loop_start` denial reporting "tasks/*
        # requests are disabled" reads as a mismatch to whoever hits it.
        message = payload["error"]["message"]
        assert "tools/call/loop_start" in message
        assert "run-starting tools are disabled" in message
        assert "tasks/*" not in message
        # The remedy clause still points at the shared grant.
        assert "allow_tasks" in message


def test_task_envelope_is_never_emitted_without_a_resolvable_task_id(tmp_path, monkeypatch) -> None:
    """A task envelope whose `taskId` is null is a handle that resolves to nothing — the
    failure mode Decision 7 forbids. If the start tool's payload ever stops carrying
    `instance_id`, the interceptor must fall back to the plain result, not emit a
    pollable-looking envelope no `tasks/get` can satisfy."""
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    from little_loops.mcp_server.tools import _TOOL_HANDLERS

    monkeypatch.setitem(
        _TOOL_HANDLERS,
        "loop_start",
        # payload without `instance_id`; **_ absorbs the `project_root` kwarg (ENH-3171)
        # `handle_call_tool` now passes to every handler.
        lambda arguments, **_: {"loop": arguments["loop"]},
    )

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=True, want_task=True),
            tool_name="loop_start",
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert result.get("resultType") != "task"
        assert "taskId" not in result


def test_ac3_request_returns_while_the_spawned_run_is_still_alive(tmp_path, monkeypatch) -> None:
    """AC 3: the call returns within normal request latency and the `ll-loop` run keeps
    going after the response is sent.

    Deliberately **not** mocked — mocking `run_background` here would assert only that the
    handler calls a function, which is not what this AC claims. The loop below occupies its
    first state for far longer than the request takes, so finding its PID alive after the
    response proves the response did not wait on the run.
    """
    project = _make_project(tmp_path, monkeypatch)
    _write_long_running_loop(project / ".loops")

    instance_id = None
    try:
        with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
            response = _post(
                client,
                "tools/call",
                _start_params(loop="slow-loop"),
                tool_name="loop_start",
            )
            assert response.status_code == 200
            result = response.json()["result"]
            assert not result["isError"]
            instance_id = json.loads(result["content"][0]["text"])["instance_id"]

        pid_file = project / ".loops" / ".running" / f"{instance_id}.pid"
        assert pid_file.exists(), "the parent writes the PID file before returning"
        pid = int(pid_file.read_text())
        assert _process_alive(pid), "the run must outlive the request that started it"
    finally:
        if instance_id is not None:
            _reap(project / ".loops" / ".running" / f"{instance_id}.pid")


def test_ac4_immediate_poll_after_start_resolves_via_pid_fallback(
    tmp_path, monkeypatch, stub_spawn
) -> None:
    """AC 4/4b: polling tasks/get immediately after start (before any state file exists)
    resolves via Decision 9's PID-file fallback, and taskId/status agree with the start
    result's task-core fields."""
    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
        start_response = _post(
            client,
            "tools/call",
            _start_params(declare_ext=True, want_task=True),
            tool_name="loop_start",
        )
        start_result = start_response.json()["result"]
        assert start_result["resultType"] == "task"
        task_id = start_result["taskId"]

        poll_response = _post(
            client, "tasks/get", {"taskId": task_id, "_meta": _meta(declare_ext=False)}
        )
        assert poll_response.status_code == 200
        poll_result = poll_response.json()["result"]
        assert poll_result["taskId"] == task_id == start_result["taskId"]
        assert poll_result["status"] == "working" == start_result["status"]
        assert poll_result["runStatus"] == "starting"


def test_immediate_cancel_after_start_stops_the_starting_run(tmp_path, monkeypatch) -> None:
    """The cancel-side counterpart of AC 4: a run started via `loop_start` is stoppable
    during its child's startup window, not reported task-not-found.

    Without this, `loop_start` opens a window in which a host can start an agent it cannot
    stop — the asymmetry Decision 9 closed only on the `tasks/get` side.
    """
    import subprocess
    import sys

    project = _make_project(tmp_path, monkeypatch)
    _write_loop(project / ".loops")

    # A real, harmless stand-in for a loop child still in startup: alive, in its own
    # session (as `run_background` spawns), and with no state file written yet.
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True
    )

    def fake_run_background(loop_name, args, loops_dir, subcommand="run", instance_id=None):
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True, exist_ok=True)
        (running_dir / f"{instance_id}.pid").write_text(str(child.pid))
        return 0

    monkeypatch.setattr("little_loops.cli.loop._helpers.run_background", fake_run_background)

    try:
        with TestClient(build_http_app(), base_url="http://127.0.0.1:8765") as client:
            start_result = _post(
                client,
                "tools/call",
                _start_params(declare_ext=True, want_task=True),
                tool_name="loop_start",
            ).json()["result"]
            task_id = start_result["taskId"]

            cancel_response = _post(
                client, "tasks/cancel", {"taskId": task_id, "_meta": _meta(declare_ext=False)}
            )
            assert cancel_response.status_code == 200, "a starting run must not be not-found"
            cancel_result = cancel_response.json()["result"]

        assert cancel_result["taskId"] == task_id
        assert cancel_result["status"] == "cancelled"
        # Same window vocabulary tasks/get reports, and nothing to resume from.
        assert cancel_result["runStatus"] == "starting"
        assert cancel_result["resumable"] is False
        assert child.wait(timeout=15) is not None, "the starting child must actually be stopped"
    finally:
        if child.poll() is None:
            with contextlib.suppress(OSError):
                os.killpg(os.getpgid(child.pid), signal.SIGKILL)


def test_ac6_capabilities_do_not_advertise_the_tasks_extension(tmp_path, monkeypatch) -> None:
    import anyio
    from mcp.client import Client

    from little_loops.mcp_server.server import build_server

    _make_project(tmp_path, monkeypatch)

    async def get_caps() -> str:
        async with Client(build_server(transport="stdio")) as client:
            return client.server_capabilities.model_dump_json()

    caps_json = anyio.run(get_caps)
    assert "io.modelcontextprotocol/tasks" not in caps_json

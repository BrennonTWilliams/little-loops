"""Tests for the `ll-mcp` queue tools (`queue_list`, `queue_get`, `queue_add`,
`queue_remove`, `queue_requeue`): two tier-1 read tools plus three tier-2 guarded
mutation tools wrapping `little_loops.queue_store`, following the conventions of
`test_mcp_server.py` and `test_feat_3149_mcp_mutation_tools.py`.

Skips entirely when the `mcp` extra isn't installed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402

from little_loops.mcp_server.server import build_server  # noqa: E402


def _payload(result: Any) -> Any:
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def _make_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_queue_add_dry_run_writes_nothing(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            dry = _payload(
                await client.call_tool(
                    "queue_add", {"target": "pytest scripts/tests/", "runner": "cmd"}
                )
            )
            assert dry["applied"] is False
            assert dry["entry"]["runner"] == "cmd"
            assert dry["entry"]["target"] == "pytest scripts/tests/"

            listed = _payload(await client.call_tool("queue_list", {}))
            assert listed == []

    anyio.run(run)


def test_queue_add_scopes_symmetric_between_dry_run_and_apply(tmp_path, monkeypatch) -> None:
    """ENH-3234 AC6: dry-run preview and post-apply entry.to_dict() must show the
    same `scopes` value. Both are None here since queue_add has no --scope
    input yet (out of scope per ENH-3234's Decision Rules) — this pins the key's
    presence and symmetry, not a populated value."""
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            dry = _payload(
                await client.call_tool("queue_add", {"target": "echo hi", "runner": "cmd"})
            )
            assert dry["entry"]["scopes"] is None

            applied = _payload(
                await client.call_tool(
                    "queue_add", {"target": "echo hi", "runner": "cmd", "apply": True}
                )
            )
            assert applied["entry"]["action"]["scopes"] is None

    anyio.run(run)


def test_queue_add_apply_then_list_and_get(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            applied = _payload(
                await client.call_tool(
                    "queue_add",
                    {"target": "pytest scripts/tests/", "runner": "cmd", "apply": True},
                )
            )
            assert applied["applied"] is True
            entry_id = applied["entry"]["id"]
            assert applied["entry"]["status"] == "pending"

            listed = _payload(await client.call_tool("queue_list", {}))
            assert [e["id"] for e in listed] == [entry_id]

            fetched = _payload(await client.call_tool("queue_get", {"id": entry_id[:8]}))
            assert fetched["id"] == entry_id

    anyio.run(run)


def test_queue_get_unknown_id_is_error(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            result = await client.call_tool("queue_get", {"id": "deadbeef"})
            assert result.is_error

    anyio.run(run)


def test_queue_remove_dry_run_then_apply(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            added = _payload(
                await client.call_tool(
                    "queue_add", {"target": "audit-docs", "runner": "cmd", "apply": True}
                )
            )
            entry_id = added["entry"]["id"]

            dry = _payload(await client.call_tool("queue_remove", {"id": entry_id}))
            assert dry["applied"] is False
            still_listed = _payload(await client.call_tool("queue_list", {}))
            assert len(still_listed) == 1

            removed = _payload(
                await client.call_tool("queue_remove", {"id": entry_id, "apply": True})
            )
            assert removed["applied"] is True
            after = _payload(await client.call_tool("queue_list", {}))
            assert after == []

    anyio.run(run)


def test_queue_requeue_running_entry(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        from little_loops.queue_store import add_entry, connect
        from little_loops.runner_spec import ActionSpec, RunnerType

        entry = add_entry(
            ActionSpec(name="audit-docs", runner=RunnerType.CMD, target="audit-docs", args={}),
            "P3",
            root=project,
        )
        conn = connect(root=project)
        try:
            conn.execute(
                "UPDATE queue_entries SET status = 'running', owner_pid = 999999 WHERE id = ?",
                (entry.id,),
            )
            conn.commit()
        finally:
            conn.close()

        async with Client(build_server(transport="stdio", project_root=project)) as client:
            dry = _payload(await client.call_tool("queue_requeue", {"id": entry.id}))
            assert dry["applied"] is False

            applied = _payload(
                await client.call_tool("queue_requeue", {"id": entry.id, "apply": True})
            )
            assert applied["applied"] is True

            fetched = _payload(await client.call_tool("queue_get", {"id": entry.id}))
            assert fetched["status"] == "pending"

    anyio.run(run)


def test_queue_requeue_dead_letter_entry(tmp_path, monkeypatch) -> None:
    """ENH-3416: queue_requeue widens to accept dead_letter (and failed/cancelled)."""
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        from little_loops.queue_store import add_entry, claim_entry, dead_letter_entry
        from little_loops.runner_spec import ActionSpec, RunnerType

        entry = add_entry(
            ActionSpec(name="audit-docs", runner=RunnerType.CMD, target="audit-docs", args={}),
            "P3",
            root=project,
        )
        claim_entry(entry.id, db_path=project / ".ll" / "queue.db")
        dead_letter_entry(entry.id, "budget exhausted", db_path=project / ".ll" / "queue.db")

        async with Client(build_server(transport="stdio", project_root=project)) as client:
            dry = _payload(await client.call_tool("queue_requeue", {"id": entry.id}))
            assert dry["applied"] is False
            assert dry["changes"][0]["from"] == "dead_letter"

            applied = _payload(
                await client.call_tool("queue_requeue", {"id": entry.id, "apply": True})
            )
            assert applied["applied"] is True

            fetched = _payload(await client.call_tool("queue_get", {"id": entry.id}))
            assert fetched["status"] == "pending"
            assert fetched["attempt"] == 0

    anyio.run(run)


def test_queue_tools_anchor_at_project_root_not_cwd(tmp_path, monkeypatch) -> None:
    """BUG-3181-style regression: the server's process cwd can differ from `project_root`
    (ENH-3171); queue tools must resolve `.ll/queue.db` against `project_root`, not
    wherever the process happened to be started.
    """
    project = tmp_path / "project"
    other_cwd = tmp_path / "elsewhere"
    (project / ".ll").mkdir(parents=True)
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            applied = _payload(
                await client.call_tool(
                    "queue_add", {"target": "audit-docs", "runner": "cmd", "apply": True}
                )
            )
            assert applied["applied"] is True

    anyio.run(run)

    assert (project / ".ll" / "queue.db").exists()
    assert not (other_cwd / ".ll").exists()

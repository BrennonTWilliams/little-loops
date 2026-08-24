"""Tests for ENH-3174: `resources/list` pagination and enumeration scoping.

Skips entirely when the `mcp` extra isn't installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402

from little_loops.mcp_server.server import build_server  # noqa: E402


def _issue_body(issue_id: str, status: str = "open") -> str:
    return f"""---
id: {issue_id.split("-")[1]}
title: 'Sample issue {issue_id}'
type: {issue_id.split("-")[0]}
priority: P2
status: {status}
---

# {issue_id}: Sample issue

## Summary
Sample body for tests.
"""


def _make_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mcp_resources: dict | None = None,
) -> Path:
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    config: dict = {"project": {"name": "fixture"}}
    if mcp_resources is not None:
        config["mcp"] = {"resources": mcp_resources}
    (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def _write_issue(tmp_path: Path, category: str, filename: str, issue_id: str, status: str) -> None:
    path = tmp_path / ".issues" / category / filename
    path.write_text(_issue_body(issue_id, status), encoding="utf-8")


# ------------------------------------------------------------------------------------------
# Pagination — always honored, regardless of config
# ------------------------------------------------------------------------------------------


def test_list_resources_paginates_when_page_size_is_smaller_than_the_index(
    tmp_path, monkeypatch
) -> None:
    _make_project(tmp_path, monkeypatch, mcp_resources={"page_size": 2})
    for i in range(5):
        _write_issue(
            tmp_path, "features", f"P2-FEAT-{3200 + i}-sample.md", f"FEAT-{3200 + i}", "open"
        )

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            page1 = await client.list_resources()
            assert len(page1.resources) == 2
            assert page1.next_cursor is not None

            page2 = await client.list_resources(cursor=page1.next_cursor)
            assert len(page2.resources) == 2
            assert page2.next_cursor is not None

            page3 = await client.list_resources(cursor=page2.next_cursor)
            assert page3.next_cursor is None

            seen = {r.uri for r in page1.resources + page2.resources + page3.resources}
            assert len(seen) == 6

    import anyio

    anyio.run(run)


def test_list_resources_default_page_size_returns_everything_in_one_page(
    tmp_path, monkeypatch
) -> None:
    _make_project(tmp_path, monkeypatch)
    for i in range(5):
        _write_issue(
            tmp_path, "features", f"P2-FEAT-{3210 + i}-sample.md", f"FEAT-{3210 + i}", "open"
        )

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            result = await client.list_resources()
            assert len(result.resources) == 6
            assert result.next_cursor is None

    import anyio

    anyio.run(run)


# ------------------------------------------------------------------------------------------
# Scoping — opt-in, defaults preserve pre-ENH-3174 behavior
# ------------------------------------------------------------------------------------------


def test_issue_statuses_unset_enumerates_every_status(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3220-open.md", "FEAT-3220", "open")
    _write_issue(tmp_path, "features", "P2-FEAT-3221-done.md", "FEAT-3221", "done")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            result = await client.list_resources()
            uris = {r.uri for r in result.resources}
            assert "ll://issues/FEAT-3220" in uris
            assert "ll://issues/FEAT-3221" in uris

    import anyio

    anyio.run(run)


def test_issue_statuses_scoped_to_open_excludes_other_statuses(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch, mcp_resources={"issue_statuses": ["open"]})
    _write_issue(tmp_path, "features", "P2-FEAT-3222-open.md", "FEAT-3222", "open")
    _write_issue(tmp_path, "features", "P2-FEAT-3223-done.md", "FEAT-3223", "done")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            result = await client.list_resources()
            uris = {r.uri for r in result.resources}
            assert "ll://issues/FEAT-3222" in uris
            assert "ll://issues/FEAT-3223" not in uris

    import anyio

    anyio.run(run)


def test_docs_globs_unset_enumerates_every_doc(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    (project / "docs" / "guides").mkdir(parents=True)
    (project / "docs" / "guides" / "a.md").write_text("a", encoding="utf-8")
    (project / "docs" / "reference").mkdir(parents=True)
    (project / "docs" / "reference" / "b.md").write_text("b", encoding="utf-8")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            result = await client.list_resources()
            uris = {r.uri for r in result.resources}
            assert "ll://docs/guides/a.md" in uris
            assert "ll://docs/reference/b.md" in uris

    import anyio

    anyio.run(run)


def test_docs_globs_scoped_excludes_non_matching_paths(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch, mcp_resources={"docs_globs": ["guides/*"]})
    (project / "docs" / "guides").mkdir(parents=True)
    (project / "docs" / "guides" / "a.md").write_text("a", encoding="utf-8")
    (project / "docs" / "reference").mkdir(parents=True)
    (project / "docs" / "reference" / "b.md").write_text("b", encoding="utf-8")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            result = await client.list_resources()
            uris = {r.uri for r in result.resources}
            assert "ll://docs/guides/a.md" in uris
            assert "ll://docs/reference/b.md" not in uris

    import anyio

    anyio.run(run)


def test_a_resource_excluded_by_scoping_is_still_unreadable_but_present_ones_still_read(
    tmp_path, monkeypatch
) -> None:
    """Scoping only narrows enumeration — `resources/read` for an in-scope URI is untouched."""
    _make_project(tmp_path, monkeypatch, mcp_resources={"issue_statuses": ["open"]})
    _write_issue(tmp_path, "features", "P2-FEAT-3224-open.md", "FEAT-3224", "open")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            result = await client.read_resource("ll://issues/FEAT-3224")
            assert result.contents

    import anyio

    anyio.run(run)

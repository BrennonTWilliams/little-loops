"""Tests for FEAT-3352: the `ll-mcp` `loop_list` tier-1 tool wrapping
`enumerate_loop_catalog` (`little_loops.cli.loop.info`), following the conventions of
`test_feat_queue_mcp_tools.py` and the project-root regression shape from
`test_enh_3171_mcp_project_root.py`.

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


def _hide_builtins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the built-in loops dir at an empty location so assertions on exact name
    sets aren't polluted by this repo's real built-in catalog."""
    from little_loops.cli.loop import info as loop_info

    monkeypatch.setattr(loop_info, "get_builtin_loops_dir", lambda: tmp_path / "no-builtins")


def _write_loop(loops_dir: Path, rel_name: str, **fields: str) -> None:
    path = loops_dir / f"{rel_name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"name: {rel_name}"] + [f"{k}: {v}" for k, v in fields.items()]
    lines += ["initial: done", "states:", "  done:", "    terminal: true"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_loop_list_default_hides_internal_and_example(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "public-loop", visibility="public", description="A public loop")
    _write_loop(loops_dir, "internal-loop", visibility="internal", description="Internal")
    _write_loop(loops_dir, "example-loop", visibility="example", description="An example")

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {}))
            names = {i["name"] for i in items}
            assert names == {"public-loop"}

    anyio.run(run)


def test_loop_list_visibility_all_shows_everything(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "public-loop", visibility="public")
    _write_loop(loops_dir, "internal-loop", visibility="internal")

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {"visibility": "all"}))
            names = {i["name"] for i in items}
            assert names == {"public-loop", "internal-loop"}

    anyio.run(run)


def test_loop_list_category_and_label_filters(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "a", category="ci", labels="[fast]")
    _write_loop(loops_dir, "b", category="release", labels="[slow]")

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            by_category = _payload(await client.call_tool("loop_list", {"category": "ci"}))
            assert {i["name"] for i in by_category} == {"a"}

            by_label = _payload(await client.call_tool("loop_list", {"label": ["FAST"]}))
            assert {i["name"] for i in by_label} == {"a"}

    anyio.run(run)


def test_loop_list_project_loop_shadows_builtin(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "shared-name", description="project version")

    fake_builtin_dir = tmp_path / "fake-builtins"
    _write_loop(fake_builtin_dir, "shared-name", description="builtin version")
    _write_loop(fake_builtin_dir, "builtin-only", description="not shadowed")

    from little_loops.cli.loop import info as loop_info

    monkeypatch.setattr(loop_info, "get_builtin_loops_dir", lambda: fake_builtin_dir)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {}))
            by_name = {i["name"]: i for i in items}
            assert "built_in" not in by_name["shared-name"]
            assert by_name["shared-name"]["description"] == "project version"
            assert by_name["builtin-only"].get("built_in") is True

    anyio.run(run)


def test_loop_list_json_contract_parity_with_cmd_list(tmp_path, monkeypatch) -> None:
    """The MCP payload matches `ll-loop list --json`'s required-field contract
    (`test_json_output_contracts.py::TestLoopListJsonContract`)."""
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "my-loop", description="Test loop", visibility="public")

    required_fields = {"name", "path", "category", "labels", "visibility", "description"}

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {}))
            assert items
            for item in items:
                for field in required_fields:
                    assert field in item
                assert isinstance(item["name"], str)
                assert isinstance(item["labels"], list)

    anyio.run(run)


def test_loop_list_resolves_loops_dir_from_project_root_not_cwd(tmp_path, monkeypatch) -> None:
    """BUG-3180-style regression: `loop_list` must anchor at `project_root`, not the
    process cwd (mirrors `test_loop_start_resolves_loops_dir_from_explicit_root`)."""
    _hide_builtins(tmp_path, monkeypatch)
    project = tmp_path / "project"
    (project / ".ll").mkdir(parents=True)
    _write_loop(project / ".loops", "only-under-project")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".ll").mkdir()
    _write_loop(elsewhere / ".loops", "only-under-elsewhere")
    monkeypatch.chdir(elsewhere)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {}))
            names = {i["name"] for i in items}
            assert names == {"only-under-project"}

    anyio.run(run)


def _write_draft(loops_dir: Path, instance: str, name: str) -> Path:
    """BUG-3367: write an unpromoted workflow-generator draft (`runs/<instance>/workflow.yaml`)."""
    run_dir = loops_dir / "runs" / instance
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "workflow.yaml"
    path.write_text(
        f"name: {name}\ninitial: done\nstates:\n  done:\n    terminal: true\n",
        encoding="utf-8",
    )
    return path


def test_loop_list_default_hides_drafts(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "public-loop")
    _write_draft(loops_dir, "workflow-generator-1", "sample-brand-kit-synth")

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {}))
            names = {i["name"] for i in items}
            assert names == {"public-loop"}

    anyio.run(run)


def test_loop_list_visibility_draft_surfaces_drafts_under_internal_name(
    tmp_path, monkeypatch
) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_draft(loops_dir, "workflow-generator-1", "sample-brand-kit-synth")

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {"visibility": "draft"}))
            names = {i["name"] for i in items}
            assert names == {"sample-brand-kit-synth"}
            assert items[0]["visibility"] == "draft"

    anyio.run(run)


def test_loop_list_visibility_all_includes_drafts(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_loop(loops_dir, "public-loop")
    _write_draft(loops_dir, "workflow-generator-1", "sample-brand-kit-synth")

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {"visibility": "all"}))
            names = {i["name"] for i in items}
            assert names == {"public-loop", "sample-brand-kit-synth"}

    anyio.run(run)


def test_loop_list_only_direct_runs_workflow_yaml_counts_as_draft(tmp_path, monkeypatch) -> None:
    """BUG-3367: other YAMLs under runs/ (nested probes, non-`workflow.yaml` artifacts)
    are excluded from the catalog entirely, not surfaced under an unrecognizable path."""
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    _write_draft(loops_dir, "workflow-generator-1", "sample-brand-kit-synth")
    nested = loops_dir / "runs" / "workflow-generator-1" / "probes" / "probe-1.yaml"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text(
        "name: probe-1\ninitial: done\nstates:\n  done:\n    terminal: true\n", encoding="utf-8"
    )

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {"visibility": "all"}))
            names = {i["name"] for i in items}
            assert names == {"sample-brand-kit-synth"}

    anyio.run(run)


def test_loop_list_dedups_duplicate_draft_names_to_latest(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    old_path = _write_draft(loops_dir, "workflow-generator-old", "dup-name")
    new_path = _write_draft(loops_dir, "workflow-generator-new", "dup-name")

    import os
    import time

    now = time.time()
    os.utime(old_path, (now - 100, now - 100))
    os.utime(new_path, (now, now))

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            items = _payload(await client.call_tool("loop_list", {"visibility": "draft"}))
            matches = [i for i in items if i["name"] == "dup-name"]
            assert len(matches) == 1
            assert matches[0]["path"] == str(new_path)

    anyio.run(run)


def test_loop_run_resolves_the_exact_name_loop_list_displays_for_a_draft(
    tmp_path, monkeypatch
) -> None:
    """Contract test (BUG-3367): whatever identifier `ll-loop list` displays for a draft,
    `resolve_loop_path` (which `ll-loop run` calls) must resolve."""
    from little_loops.cli.loop.info import enumerate_loop_catalog
    from little_loops.fsm.loop_paths import resolve_loop_path

    project = _make_project(tmp_path, monkeypatch)
    _hide_builtins(tmp_path, monkeypatch)
    loops_dir = project / ".loops"
    draft_path = _write_draft(loops_dir, "workflow-generator-1", "sample-brand-kit-synth")

    catalog = enumerate_loop_catalog(loops_dir=loops_dir, visibilities={"draft"})
    assert len(catalog.entries) == 1
    displayed_name = catalog.entries[0].name

    resolved = resolve_loop_path(displayed_name, loops_dir)

    assert resolved == draft_path


def test_loop_list_advertised_as_read_only(tmp_path, monkeypatch) -> None:
    project = _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert "loop_list" in tools
            assert tools["loop_list"].annotations is None

    anyio.run(run)

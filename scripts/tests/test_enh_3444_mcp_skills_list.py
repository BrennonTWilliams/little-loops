"""Tests for ENH-3444: the `ll-mcp` `skills_list` tier-1 tool wrapping
`tool_catalog.assemble_tool_catalog`, anchored at `skill_expander._find_plugin_root()`
rather than `--project-root` — following the conventions of
`test_feat_3352_mcp_loop_list.py`.

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


def _use_plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    return tmp_path


def _make_skill(
    plugin_root: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    args_hint: str | None = None,
) -> Path:
    skill_dir = plugin_root / "skills" / name
    skill_dir.mkdir(parents=True)
    fm = f"description: {description}\n"
    if args_hint is not None:
        fm += f'args: "{args_hint}"\n'
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\n{fm}---\n\nBody.", encoding="utf-8")
    return skill_md


def _make_command(
    plugin_root: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    args_hint: str | None = None,
) -> Path:
    commands_dir = plugin_root / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    fm = f"description: {description}\n"
    if args_hint is not None:
        fm += f'args: "{args_hint}"\n'
    cmd_md = commands_dir / f"{name}.md"
    cmd_md.write_text(f"---\n{fm}---\n\nBody.", encoding="utf-8")
    return cmd_md


def _make_agent(plugin_root: Path, name: str) -> Path:
    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agents_dir / f"{name}.md"
    agent_md.write_text(
        f'---\nname: {name}\ndescription: Agent desc.\nmodel: sonnet\ntools: ["Read"]\n---\n\nBody.',
        encoding="utf-8",
    )
    return agent_md


def test_skills_list_appears_with_no_apply_argument(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert "skills_list" in tools
            assert "apply" not in tools["skills_list"].input_schema["properties"]

    anyio.run(run)


def test_skills_list_returns_skills_and_commands_with_kind(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "my-skill", description="Do the skill thing.")
    _make_command(plugin_root, "my-command", description="Do the command thing.")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            by_name = {row["name"]: row for row in rows}
            assert by_name["my-skill"]["kind"] == "skill"
            assert by_name["my-skill"]["description"] == "Do the skill thing."
            assert by_name["my-command"]["kind"] == "command"
            assert by_name["my-command"]["description"] == "Do the command thing."

    anyio.run(run)


def test_skills_list_excludes_agents(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "my-skill")
    _make_agent(plugin_root, "my-agent")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            names = {row["name"] for row in rows}
            assert names == {"my-skill"}

    anyio.run(run)


def test_skills_list_args_present_iff_hint_exists(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "with-hint", args_hint="ISSUE_ID [--auto]")
    _make_skill(plugin_root, "without-hint")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            by_name = {row["name"]: row for row in rows}
            assert by_name["with-hint"]["args"] == "ISSUE_ID [--auto]"
            assert "args" not in by_name["without-hint"]

    anyio.run(run)


def test_skills_list_ordered_by_kind_then_name(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "zebra-skill")
    _make_skill(plugin_root, "alpha-skill")
    _make_command(plugin_root, "alpha-command")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            assert [row["name"] for row in rows] == [
                "alpha-skill",
                "zebra-skill",
                "alpha-command",
            ]
            assert [row["kind"] for row in rows] == ["skill", "skill", "command"]

    anyio.run(run)


def test_skills_list_dedupes_name_collision_skill_wins(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "shared-name", description="Skill wins.")
    _make_command(plugin_root, "shared-name", description="Command loses.")

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            matches = [row for row in rows if row["name"] == "shared-name"]
            assert len(matches) == 1
            assert matches[0]["kind"] == "skill"
            assert matches[0]["description"] == "Skill wins."

    anyio.run(run)


def test_skills_list_returns_empty_on_unresolvable_plugin_root(tmp_path, monkeypatch) -> None:
    # BUG-3490: resolve_plugin_content_root() validates each candidate and
    # falls through invalid ones (unlike the legacy `_find_plugin_root()`,
    # which trusted a bad `CLAUDE_PLUGIN_ROOT` unconditionally). Force every
    # candidate to be invalid to exercise the genuine "nothing resolves" path.
    _make_project(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "little_loops.skill_expander._content_root_candidates",
        lambda: [tmp_path / "does-not-exist"],
    )

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            assert rows == []

    anyio.run(run)


def test_skills_list_invalid_env_root_falls_through_to_checkout(tmp_path, monkeypatch) -> None:
    # A bad CLAUDE_PLUGIN_ROOT no longer produces an empty catalog on its own —
    # the resolver falls through to the next valid candidate.
    _make_project(tmp_path, monkeypatch)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "does-not-exist"))

    async def run() -> None:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            rows = _payload(await client.call_tool("skills_list", {}))
            assert isinstance(rows, list)
            assert len(rows) > 0

    anyio.run(run)


def test_skills_list_identical_across_project_root_values(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "my-skill")
    other_project = tmp_path / "other-project"
    other_project.mkdir()

    async def run() -> None:
        default_server = build_server(transport="stdio")
        scoped_server = build_server(transport="stdio", project_root=other_project)
        async with Client(default_server) as client:
            default_rows = _payload(await client.call_tool("skills_list", {}))
        async with Client(scoped_server) as client:
            scoped_rows = _payload(await client.call_tool("skills_list", {}))
        assert default_rows == scoped_rows

    anyio.run(run)


def test_skills_list_entries_classify_as_skill_via_queue_add(tmp_path, monkeypatch) -> None:
    """Classification parity (AC 2): every returned name must classify `RunnerType.SKILL`
    via the same `_classify_action` path `queue_add` uses.

    `monkeypatch.chdir(tmp_path)` (already done by `_make_project`) keeps
    `_classify_action`'s LOOP-branch `BRConfig(Path.cwd())` lookup from matching a
    same-named loop and flipping the classification before the skill branch runs.
    """
    from little_loops.cli.queue import _classify_action
    from little_loops.runner_spec import RunnerType

    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "my-skill")
    _make_command(plugin_root, "my-command")

    async def run() -> list[dict[str, Any]]:
        server = build_server(transport="stdio")
        async with Client(server) as client:
            return _payload(await client.call_tool("skills_list", {}))

    rows = anyio.run(run)
    assert rows
    for row in rows:
        spec = _classify_action(row["name"], runner_override=None, timeout=None, arg_pairs=None)
        assert spec.runner is RunnerType.SKILL, (
            f"{row['name']} listed by skills_list but classifies as {spec.runner}"
        )

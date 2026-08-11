"""Tests for little_loops.mcp_server (FEAT-3135).

Drives the server over the SDK's in-memory `Client` (`mcp.client.Client(server)`, default
`mode="auto"`), which dispatches directly against an in-process `Server` — no JSON-RPC
framing, no stdin/stdout, no `initialize` handshake. This is the "modern" 2026-07-28
connection path `ll-mcp` is built for; see the module docstrings under
`little_loops/mcp_server/` for why no hand-rolled stdin-loop harness exists.

Skips entirely when the `mcp` extra isn't installed (it's optional — see
`[project.optional-dependencies].mcp` in `scripts/pyproject.toml`).
"""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402
from mcp.shared.exceptions import MCPError  # noqa: E402

from little_loops.mcp_server.server import build_server  # noqa: E402

ISSUE_BODY = """---
id: 3135
title: 'Sample issue'
type: FEAT
priority: P2
status: open
---

# FEAT-3135: Sample issue

## Summary
Sample body for tests.
"""


def _make_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chdir into a fresh, empty little-loops project layout under tmp_path."""
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_issue(tmp_path: Path, category: str, filename: str, body: str = ISSUE_BODY) -> Path:
    path = tmp_path / ".issues" / category / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_list_tools_returns_the_five_read_tools_first_with_cache_metadata(
    tmp_path, monkeypatch
) -> None:
    """The tier-1 five are unchanged and still lead the catalog, in source order.

    FEAT-3149 appended four mutating tools, so this no longer asserts an exact five-name
    catalog — but the tier-1 contract it was written to protect (these five names, this
    order, SDK-supplied cache metadata) is asserted unchanged. The tier-2 additions have
    their own coverage in `test_feat_3149_mcp_mutation_tools.py`.
    """
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.list_tools()
            names = [t.name for t in result.tools]
            assert names[:5] == [
                "issues_query",
                "issue_get",
                "history_search",
                "deps_check",
                "capabilities",
            ]
            # SDK-supplied per SEP-2549 — not something a handler sets by hand.
            assert result.ttl_ms > 0
            assert result.cache_scope == "public"

    anyio.run(run)


def test_tools_list_ordering_is_stable_across_calls(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            first = [t.name for t in (await client.list_tools()).tools]
            second = [t.name for t in (await client.list_tools()).tools]
            shuffled_call_order = [
                await client.call_tool("capabilities", {}),
                await client.call_tool("deps_check", {}),
            ]
            third = [t.name for t in (await client.list_tools()).tools]
            assert first == second == third
            assert all(not r.is_error for r in shuffled_call_order)

    anyio.run(run)


def test_discover_advertises_tools_resources_and_prompts_only(tmp_path, monkeypatch) -> None:
    """No custom `server/discover` handler is registered; the SDK's default auto-derives
    capabilities from registered handlers, so no Sampling/Logging appear.
    Resources ARE registered (FEAT-3136) and Prompts ARE registered (FEAT-3137), so
    `caps.resources`/`caps.prompts` are non-`None`."""
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            caps = client.session.server_capabilities
            assert caps is not None
            assert caps.tools is not None
            assert caps.resources is not None
            assert caps.prompts is not None
            assert caps.logging is None
            assert getattr(caps, "sampling", None) is None
            assert getattr(caps, "roots", None) is None

    anyio.run(run)


def test_capabilities_tool_returns_report_shape(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    monkeypatch.setenv("LL_HOST_CLI", "claude-code")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.call_tool("capabilities", {})
            assert not result.is_error
            payload = json.loads(result.content[0].text)
            assert payload["host"] == "claude-code"
            assert isinstance(payload["capabilities"], list)
            assert all({"name", "status", "note"} <= c.keys() for c in payload["capabilities"])

    anyio.run(run)


def test_issues_query_tool_filters_and_sorts(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    _write_issue(
        tmp_path,
        "features",
        "P2-FEAT-3135-sample.md",
        ISSUE_BODY,
    )
    _write_issue(
        tmp_path,
        "bugs",
        "P0-BUG-1-urgent.md",
        "---\nid: 1\ntitle: 'Urgent'\ntype: BUG\npriority: P0\nstatus: open\n---\n\n# BUG-1: Urgent\n",
    )

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.call_tool("issues_query", {"status": "open"})
            assert not result.is_error
            payload = json.loads(result.content[0].text)
            ids = [entry["id"] for entry in payload]
            assert ids == ["BUG-1", "FEAT-3135"]  # P0 sorts before P2

            filtered = await client.call_tool(
                "issues_query", {"status": "open", "issue_type": "BUG"}
            )
            filtered_payload = json.loads(filtered.content[0].text)
            assert [entry["id"] for entry in filtered_payload] == ["BUG-1"]

            limited = await client.call_tool("issues_query", {"status": "open", "limit": 1})
            limited_payload = json.loads(limited.content[0].text)
            assert len(limited_payload) == 1

    anyio.run(run)


def test_issue_get_tool_resolves_and_reports_not_found(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3135-sample.md", ISSUE_BODY)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            found = await client.call_tool("issue_get", {"issue_id": "FEAT-3135"})
            assert not found.is_error
            payload = json.loads(found.content[0].text)
            assert payload["issue_id"] == "FEAT-3135"

            missing = await client.call_tool("issue_get", {"issue_id": "FEAT-999999"})
            assert missing.is_error
            assert "not found" in missing.content[0].text.lower()

    anyio.run(run)


def test_deps_check_tool_reports_validation_shape(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3135-sample.md", ISSUE_BODY)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.call_tool("deps_check", {})
            assert not result.is_error
            payload = json.loads(result.content[0].text)
            expected_keys = {
                "has_issues",
                "broken_refs",
                "missing_backlinks",
                "cycles",
                "stale_completed_refs",
                "broken_depends_on_refs",
                "broken_relates_to_refs",
            }
            assert expected_keys <= payload.keys()

    anyio.run(run)


def test_history_search_tool_empty_db_returns_empty_list(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.call_tool("history_search", {"query": "anything"})
            assert not result.is_error
            payload = json.loads(result.content[0].text)
            assert payload == []

    anyio.run(run)


def test_history_search_tool_finds_seeded_result(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    from little_loops.session_store import SQLiteTransport

    db = tmp_path / ".ll" / "history.db"
    transport = SQLiteTransport(db)
    transport.send({"event": "state_enter", "loop_name": "ratelimit-fast", "state": "execute"})
    transport.close()

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.call_tool(
                "history_search", {"query": "ratelimit", "kind": "loop"}
            )
            assert not result.is_error
            payload = json.loads(result.content[0].text)
            assert len(payload) >= 1
            assert all(entry["kind"] == "loop" for entry in payload)

    anyio.run(run)


def test_call_unknown_tool_returns_error_not_exception(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.call_tool("does_not_exist", {})
            assert result.is_error
            assert "Unknown tool" in result.content[0].text

    anyio.run(run)


def test_no_unguarded_mutating_tool_is_advertised(tmp_path, monkeypatch) -> None:
    """Nothing can write without announcing itself and taking the dry-run guard.

    Tier 2 (FEAT-3149) moved this boundary deliberately, so the assertion is no longer
    "the catalog contains only these five names". The invariant that actually mattered
    survives, and is now stronger: any tool outside the tier-1 five must be registered in
    `policy.MUTATING_TOOLS` — which is what subjects it to the dry-run wrapper and the
    per-transport policy — and must declare the `apply` opt-in in its schema. A new tool
    added to `_TOOLS` but forgotten in the registry fails here.
    """
    from little_loops.mcp_server.policy import MUTATING_TOOLS

    _make_project(tmp_path, monkeypatch)

    read_only = {
        "issues_query",
        "issue_get",
        "history_search",
        "deps_check",
        "capabilities",
    }

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.list_tools()
            for tool in result.tools:
                if tool.name in read_only:
                    continue
                assert tool.name in MUTATING_TOOLS, (
                    f"{tool.name} is advertised but is neither a tier-1 read tool nor "
                    "registered in policy.MUTATING_TOOLS — it would bypass both guards"
                )
                assert tool.input_schema["properties"]["apply"]["default"] is False

    anyio.run(run)


def test_repeated_and_reordered_calls_are_identical(tmp_path, monkeypatch) -> None:
    """No handler depends on state from a prior request (2026-07-28 statelessness invariant):
    the same call twice, and calls issued in a different order, produce identical results."""
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3135-sample.md", ISSUE_BODY)
    monkeypatch.setenv("LL_HOST_CLI", "claude-code")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            first_a = await client.call_tool("capabilities", {})
            first_b = await client.call_tool("issue_get", {"issue_id": "FEAT-3135"})

            second_b = await client.call_tool("issue_get", {"issue_id": "FEAT-3135"})
            second_a = await client.call_tool("capabilities", {})

            assert first_a.content[0].text == second_a.content[0].text
            assert first_b.content[0].text == second_b.content[0].text

    anyio.run(run)


GOALS_BODY = """---
version: '1.0'
persona:
  id: dev
  name: Developer
  role: Builds things
priorities:
- id: p1
  name: Ship it
---

# Product Goals
"""


def test_list_resources_returns_issues_goals_and_docs_with_cache_metadata(
    tmp_path, monkeypatch
) -> None:
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3135-sample.md", ISSUE_BODY)
    (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll" / "ll-goals.md").write_text(GOALS_BODY, encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.list_resources()
            uris = {r.uri for r in result.resources}
            assert uris == {
                "ll://issues/FEAT-3135",
                "ll://goals",
                "ll://docs/ARCHITECTURE.md",
            }
            issue_entry = next(r for r in result.resources if r.uri == "ll://issues/FEAT-3135")
            assert issue_entry.description == "Sample issue"
            # SDK-supplied per SEP-2549 — not something a handler sets by hand.
            assert result.ttl_ms > 0
            assert result.cache_scope == "public"

    anyio.run(run)


def test_read_resource_issue_returns_card_fields(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3135-sample.md", ISSUE_BODY)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.read_resource("ll://issues/FEAT-3135")
            payload = json.loads(result.contents[0].text)
            assert payload["issue_id"] == "FEAT-3135"
            assert result.ttl_ms > 0
            assert result.cache_scope == "public"

    anyio.run(run)


def test_read_resource_goals_returns_raw_markdown(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll" / "ll-goals.md").write_text(GOALS_BODY, encoding="utf-8")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.read_resource("ll://goals")
            assert result.contents[0].text == GOALS_BODY

    anyio.run(run)


def test_read_resource_docs_returns_file_text(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.read_resource("ll://docs/ARCHITECTURE.md")
            assert result.contents[0].text == "# Architecture\n"

    anyio.run(run)


def test_read_resource_outside_enumeration_is_rejected(tmp_path, monkeypatch) -> None:
    """A `uri` never enumerated at startup (including path-traversal attempts) is rejected
    without any filesystem read — dict membership in the discovery-time enumeration is the
    entire access-control boundary."""
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            for bad_uri in (
                "ll://issues/FEAT-999999",
                "ll://docs/../../etc/passwd",
                "ll://not-a-real-scheme",
            ):
                with pytest.raises(MCPError):
                    await client.read_resource(bad_uri)

    anyio.run(run)


# ---------------------------------------------------------------------------
# Prompts-from-skills (FEAT-3137)
# ---------------------------------------------------------------------------


def _make_skill(
    plugin_root: Path,
    rel_dir: str,
    description: str = "Use when the user asks for stuff.",
    args_hint: str | None = None,
    disable_model_invocation: bool = False,
    body: str = "# My Skill\n\nDoes stuff.",
) -> Path:
    skill_dir = plugin_root / "skills" / rel_dir
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    fm = f"description: {description}\n"
    if args_hint is not None:
        fm += f"args: {args_hint}\n"
    if disable_model_invocation:
        fm += "disable-model-invocation: true\n"
    skill_md.write_text(f"---\n{fm}---\n\n{body}", encoding="utf-8")
    return skill_md


def _use_plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    return tmp_path


def test_list_prompts_returns_skills_with_frontmatter_and_cache_metadata(
    tmp_path, monkeypatch
) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "my-skill", description="Do the thing.", args_hint="ID [--force]")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.list_prompts()
            assert len(result.prompts) == 1
            prompt = result.prompts[0]
            assert prompt.name == "my-skill"
            assert prompt.description == "Do the thing."
            assert prompt.arguments is not None
            assert prompt.arguments[0].name == "args"
            assert prompt.arguments[0].description == "ID [--force]"
            # SDK-supplied per SEP-2549 — not something a handler sets by hand.
            assert result.ttl_ms > 0
            assert result.cache_scope == "public"

    anyio.run(run)


def test_list_prompts_registers_nested_skill_md_as_own_prompt(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "parent-skill", description="Parent.")
    _make_skill(plugin_root, "parent-skill/nested-skill", description="Nested.")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.list_prompts()
            names = {p.name for p in result.prompts}
            assert names == {"parent-skill", "nested-skill"}

    anyio.run(run)


def test_list_prompts_skips_disable_model_invocation_skills(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "visible-skill", description="Visible.")
    _make_skill(
        plugin_root,
        "hidden-skill",
        description="Hidden.",
        disable_model_invocation=True,
    )

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.list_prompts()
            names = {p.name for p in result.prompts}
            assert names == {"visible-skill"}

    anyio.run(run)


def test_get_prompt_returns_skill_body_without_frontmatter(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)
    plugin_root = _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(plugin_root, "my-skill", body="# My Skill\n\nDoes stuff.")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            result = await client.get_prompt("my-skill")
            assert len(result.messages) == 1
            message = result.messages[0]
            assert message.role == "user"
            assert message.content.text.strip() == "# My Skill\n\nDoes stuff."

    anyio.run(run)


def test_get_prompt_unknown_name_is_rejected(tmp_path, monkeypatch) -> None:
    """A `name` never enumerated at startup is rejected without any filesystem read — dict
    membership in the discovery-time enumeration is the entire access-control boundary."""
    _make_project(tmp_path, monkeypatch)
    _use_plugin_root(tmp_path, monkeypatch)
    _make_skill(tmp_path, "my-skill")

    async def run() -> None:
        server = build_server()
        async with Client(server) as client:
            with pytest.raises(MCPError):
                await client.get_prompt("../../etc/passwd")
            with pytest.raises(MCPError):
                await client.get_prompt("not-a-real-skill")

    anyio.run(run)


def _stdio_call(tmp_path: Path, protocol_version: str, tool: str, arguments: dict) -> dict:
    """Drive `ll-mcp` over a real stdin/stdout JSON-RPC exchange and return the response.

    Unlike every other test here, this crosses the wire: it spawns the server as a
    subprocess and speaks framed JSON-RPC at it. The in-memory `Client` skips result
    serialization entirely, so it cannot observe validation failures that only occur on
    encode — which is how the `structuredContent` regression below reached a release.
    """
    import subprocess
    import sys

    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    ]
    proc = subprocess.run(
        [sys.executable, "-c", "from little_loops.mcp_server import main_mcp; main_mcp()"],
        input="".join(json.dumps(r) + "\n" for r in requests),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=60,
    )
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == 2:
            return message
    raise AssertionError(f"no tools/call response; stdout={proc.stdout!r} stderr={proc.stderr!r}")


@pytest.mark.parametrize("protocol_version", ["2024-11-05", "2025-06-18", "2026-07-28"])
@pytest.mark.parametrize("tool", ["issues_query", "history_search"])
def test_list_returning_tools_serialize_over_stdio(
    tmp_path, monkeypatch, tool: str, protocol_version: str
) -> None:
    """`issues_query`/`history_search` return a JSON *list*, and `structuredContent` is an
    arbitrary JSON value only on 2026-07-28 — every earlier version restricts it to an
    object, and `mcp==2.0.0` negotiates down to 2025-11-25 even when the client asks for
    2026-07-28. Attaching the list unconditionally failed encode validation with -32603
    ("Handler returned an invalid result") for every real client while the in-memory tests
    stayed green. The payload must always arrive intact via `content[0].text`.
    """
    _make_project(tmp_path, monkeypatch)
    _write_issue(tmp_path, "features", "P2-FEAT-3135-sample.md", ISSUE_BODY)

    arguments = {"query": "sample", "limit": 1} if tool == "history_search" else {"limit": 5}
    message = _stdio_call(tmp_path, protocol_version, tool, arguments)

    assert "error" not in message, message.get("error")
    result = message["result"]
    assert not result.get("isError"), result
    assert "structuredContent" not in result  # a list payload is never attached
    assert isinstance(json.loads(result["content"][0]["text"]), list)

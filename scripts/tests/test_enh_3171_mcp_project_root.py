"""Tests for ENH-3171: `ll-mcp` resolves its project root explicitly rather than only from
`Path.cwd()`.

Covers the two things the issue calls out as the actual failure mode:

1. Every tool surface (read tools, mutating tools, `tasks/*`, and the transport policy
   gating both) serves the *resolved* root even when the process `cwd` points somewhere
   else entirely — proven by chdir-ing into an unrelated directory and passing
   `--project-root`/`LL_MCP_PROJECT_ROOT`/an explicit `build_server(project_root=...)`.
2. The "fail loudly" secondary requirement: a resolved root with neither `.ll/` nor
   `.issues/` produces a visible signal via `capabilities` and via `main_mcp`'s startup
   stderr, rather than every surface answering empty successfully.

Skips entirely when the `mcp` extra isn't installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client import Client  # noqa: E402

from little_loops.mcp_server import main_mcp  # noqa: E402
from little_loops.mcp_server.server import build_http_app, build_server  # noqa: E402
from little_loops.mcp_server.tools import _looks_like_project_root, _project_root  # noqa: E402


def _make_project(root: Path, *, allow_stdio_mutations: bool | None = None) -> Path:
    for category in ("bugs", "features", "enhancements", "epics"):
        (root / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (root / ".issues" / "features" / "P2-FEAT-900-sample.md").write_text(
        "---\nid: FEAT-900\ntitle: 'Sample'\ntype: FEAT\npriority: P2\nstatus: open\n---\n\n"
        "# FEAT-900: Sample\n",
        encoding="utf-8",
    )
    (root / ".ll").mkdir(exist_ok=True)
    config: dict = {"project": {"name": "fixture"}}
    if allow_stdio_mutations is not None:
        config["mcp"] = {"transport_policy": {"stdio": {"allow_mutations": allow_stdio_mutations}}}
    (root / ".ll" / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def _payload(result) -> object:
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


# ------------------------------------------------------------------------------------------
# `_project_root` precedence
# ------------------------------------------------------------------------------------------


def test_project_root_precedence_explicit_beats_env_beats_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit"
    env_dir = tmp_path / "env"
    cwd_dir = tmp_path / "cwd"
    for d in (explicit, env_dir, cwd_dir):
        d.mkdir()
    monkeypatch.chdir(cwd_dir)
    monkeypatch.setenv("LL_MCP_PROJECT_ROOT", str(env_dir))

    assert _project_root(explicit) == explicit
    assert _project_root(None) == env_dir

    monkeypatch.delenv("LL_MCP_PROJECT_ROOT")
    assert _project_root(None) == cwd_dir


# ------------------------------------------------------------------------------------------
# `build_server(project_root=...)` reaches every call site regardless of cwd
# ------------------------------------------------------------------------------------------


def test_tool_surface_serves_explicit_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`issues_query` finds the issue under the explicit root even though `cwd` is a
    different, empty directory (the "spawned from $HOME" failure mode)."""
    project = _make_project(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            result = await client.call_tool("issues_query", {"status": "all"})
            issues = _payload(result)
            assert any(issue["id"] == "FEAT-900" for issue in issues)

    anyio.run(run)


def test_loop_start_resolves_loops_dir_from_explicit_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`loop_start` (which reaches `tasks._loops_dir`) fails for a missing loop under the
    explicit root's `.loops/`, not silently against `cwd`'s (or a nonexistent) `.loops/`."""
    project = _make_project(tmp_path / "project")
    (project / ".loops").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            result = await client.call_tool("loop_start", {"loop": "does-not-exist"})
            assert result.is_error

    anyio.run(run)


def test_stdio_policy_reads_config_from_explicit_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The security-relevant site: `check_tool_call`'s mutation grant is read from the
    explicit root's `.ll/ll-config.json`, not from `cwd`'s (or the schema default)."""
    project = _make_project(tmp_path / "project", allow_stdio_mutations=False)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    from mcp.shared.exceptions import MCPError

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            with pytest.raises(MCPError, match="policy denied"):
                await client.call_tool(
                    "issue_append_log",
                    {"issue_id": "FEAT-900", "command": "/ll:test", "apply": True},
                )

    anyio.run(run)


def test_http_transport_policy_middleware_reads_config_from_explicit_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`build_http_app`'s `TransportPolicyMiddleware` — the ASGI pre-parse gate — also reads
    `.ll/ll-config.json` from the resolved root, not `cwd`. Default HTTP policy already
    denies mutations, so this asserts the *allow* path only reachable via the project's own
    config to prove the middleware is not silently falling back to schema defaults."""
    from starlette.testclient import TestClient

    project = _make_project(tmp_path / "project")
    (project / ".ll" / "ll-config.json").write_text(
        json.dumps(
            {
                "project": {"name": "fixture"},
                "mcp": {"transport_policy": {"http": {"allow_mutations": True}}},
            }
        ),
        encoding="utf-8",
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2026-07-28",
        "mcp-method": "tools/call",
        "mcp-name": "issue_append_log",
    }
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "issue_append_log", "arguments": {}},
    }
    with TestClient(
        build_http_app(project_root=project), base_url="http://127.0.0.1:8765"
    ) as client:
        response = client.post("/mcp", json=body, headers=headers)
        # 403 would mean the middleware denied it (project's own config allows it); the
        # request reaches the real handler, whose own failure mode (missing issue_id/apply)
        # is a 200 with a tool-level error, not a 403 policy denial.
        assert response.status_code != 403


# ------------------------------------------------------------------------------------------
# Secondary: fail loudly on a non-project root
# ------------------------------------------------------------------------------------------


def test_looks_like_project_root(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _looks_like_project_root(empty) is False

    with_issues = tmp_path / "with-issues"
    with_issues.mkdir()
    (with_issues / ".issues").mkdir()
    assert _looks_like_project_root(with_issues) is True

    with_ll = tmp_path / "with-ll"
    with_ll.mkdir()
    (with_ll / ".ll").mkdir()
    assert _looks_like_project_root(with_ll) is True


def test_capabilities_reports_project_root_validity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    async def run() -> None:
        async with Client(build_server(transport="stdio", project_root=project)) as client:
            result = await client.call_tool("capabilities", {})
            payload = _payload(result)
            assert payload["project_root"]["path"] == str(project)
            assert payload["project_root"]["resolved"] is True

    anyio.run(run)

    async def run_empty() -> None:
        async with Client(build_server(transport="stdio", project_root=elsewhere)) as client:
            result = await client.call_tool("capabilities", {})
            payload = _payload(result)
            assert payload["project_root"]["resolved"] is False

    anyio.run(run_empty)


def test_main_mcp_warns_on_non_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr("anyio.run", lambda fn: None)

    rc = main_mcp(["--project-root", str(empty)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert str(empty) in captured.err


def test_main_mcp_no_warning_for_a_real_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _make_project(tmp_path / "project")
    monkeypatch.setattr("anyio.run", lambda fn: None)

    rc = main_mcp(["--project-root", str(project)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err


# ------------------------------------------------------------------------------------------
# `main_mcp` threading: --project-root / LL_MCP_PROJECT_ROOT reach `run_stdio`/`run_http`
# ------------------------------------------------------------------------------------------


def test_main_mcp_project_root_flag_threads_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path / "project")
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp(["--project-root", str(project)])
    assert rc == 0
    assert len(calls) == 1
    target = calls[0]
    assert target.keywords["project_root"] == project


def test_main_mcp_project_root_env_var_threads_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path / "project")
    monkeypatch.setenv("LL_MCP_PROJECT_ROOT", str(project))
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp([])
    assert rc == 0
    assert calls[0].keywords["project_root"] == project


def test_main_mcp_default_path_unwrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No `--project-root`/env override: `anyio.run` receives the bare `run_stdio` function,
    not a wrapper — preserving the pre-ENH-3171 identity existing tests assert."""
    from little_loops.mcp_server.server import run_stdio

    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr("anyio.run", lambda fn: calls.append(fn))

    rc = main_mcp([])
    assert rc == 0
    assert calls == [run_stdio]

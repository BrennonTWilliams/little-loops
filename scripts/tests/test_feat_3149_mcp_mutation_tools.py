"""Tests for FEAT-3149: `ll-mcp` tier-2 guarded mutation tools.

Drives the four mutating tools (`issue_capture`, `issue_set_status`, `issue_link`,
`issue_append_log`) over the SDK's in-memory `Client`, following `test_mcp_server.py`'s
`build_server()` + `_make_project(tmp_path, monkeypatch)` + `anyio.run(run)` conventions.

The AC 2 assertion shape is deliberate: a dry-run must be proven inert by comparing the
issue file's **bytes** before and after the call, not by re-parsing its frontmatter. A
frontmatter comparison would pass even if the handler rewrote the file with equivalent-but-
reserialized YAML, which is still a write.

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

ISSUE_BODY = """---
id: FEAT-501
title: 'Sample issue'
type: FEAT
priority: P2
status: open
---

# FEAT-501: Sample issue

## Summary
Sample body for tests.

---

## Status

**Open**
"""

TARGET_BODY = """---
id: BUG-502
title: 'Target issue'
type: BUG
priority: P1
status: open
---

# BUG-502: Target issue

## Summary
Link target.
"""


def _make_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chdir into a fresh little-loops project layout with two issues on disk."""
    monkeypatch.chdir(tmp_path)
    for category in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / category).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".issues" / "features" / "P2-FEAT-501-sample-issue.md").write_text(
        ISSUE_BODY, encoding="utf-8"
    )
    (tmp_path / ".issues" / "bugs" / "P1-BUG-502-target-issue.md").write_text(
        TARGET_BODY, encoding="utf-8"
    )
    return tmp_path


def _source(tmp_path: Path) -> Path:
    return tmp_path / ".issues" / "features" / "P2-FEAT-501-sample-issue.md"


def _payload(result: Any) -> Any:
    """Decode a tool result's JSON payload from `content[0].text`."""
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def _snapshot(tmp_path: Path) -> dict[str, bytes]:
    """Byte-level snapshot of every issue file, for AC 2's inertness assertion."""
    return {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in sorted((tmp_path / ".issues").rglob("*.md"))
    }


def _contains_key(payload: Any, key: str) -> bool:
    """Recursively test whether `key` appears anywhere in a decoded JSON payload."""
    if isinstance(payload, dict):
        return key in payload or any(_contains_key(v, key) for v in payload.values())
    if isinstance(payload, list):
        return any(_contains_key(item, key) for item in payload)
    return False


MUTATING_NAMES = ["issue_capture", "issue_set_status", "issue_link", "issue_append_log"]

TIER1_NAMES = ["issues_query", "issue_get", "history_search", "deps_check", "capabilities"]


# --------------------------------------------------------------------------------------
# AC 1 — mutating annotation in the tool catalog
# --------------------------------------------------------------------------------------


def test_ac1_mutating_tools_are_listed_and_annotated(tmp_path, monkeypatch) -> None:
    """The four tools appear in `tools/list` annotated as non-read-only."""
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server()) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            for name in MUTATING_NAMES:
                assert name in tools, f"{name} missing from tools/list"
                annotations = tools[name].annotations
                assert annotations is not None, f"{name} has no annotations"
                assert annotations.read_only_hint is False, (
                    f"{name} must be annotated read_only_hint=False to distinguish it "
                    "from the five tier-1 read-only tools"
                )

    anyio.run(run)


def test_ac1_tier1_tools_keep_their_shape_and_ordering(tmp_path, monkeypatch) -> None:
    """Anti-goal guard: tier-1 entries are unchanged and still come first, in order."""
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server()) as client:
            tools = (await client.list_tools()).tools
            names = [t.name for t in tools]
            assert names[:5] == TIER1_NAMES
            assert sorted(names[5:]) == sorted(MUTATING_NAMES)
            for tool in tools[:5]:
                assert tool.annotations is None, (
                    f"{tool.name} gained an annotation — tier-1 output shapes must not change"
                )

    anyio.run(run)


def test_ac1_apply_flag_is_declared_on_every_mutating_tool(tmp_path, monkeypatch) -> None:
    """Each mutating tool's input schema carries `apply`, defaulting to false."""
    _make_project(tmp_path, monkeypatch)

    async def run() -> None:
        async with Client(build_server()) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            for name in MUTATING_NAMES:
                schema = tools[name].input_schema
                assert "apply" in schema["properties"], f"{name} has no `apply` parameter"
                apply_schema = schema["properties"]["apply"]
                assert apply_schema["type"] == "boolean"
                assert apply_schema["default"] is False
                assert "apply" not in schema.get("required", []), (
                    f"{name} must not require `apply` — omitting it entirely must not write"
                )

    anyio.run(run)


# --------------------------------------------------------------------------------------
# AC 2 — dry-run by default leaves the filesystem unchanged
# --------------------------------------------------------------------------------------


DRY_RUN_CALLS = [
    ("issue_capture", {"type": "BUG", "title": "A newly noticed bug", "priority": "P1"}),
    ("issue_set_status", {"issue_id": "FEAT-501", "status": "deferred"}),
    ("issue_link", {"issue_id": "FEAT-501", "field": "relates_to", "target": "BUG-502"}),
    ("issue_append_log", {"issue_id": "FEAT-501", "command": "/ll:manage-issue"}),
]


@pytest.mark.parametrize("tool_name,arguments", DRY_RUN_CALLS, ids=[c[0] for c in DRY_RUN_CALLS])
def test_ac2_omitting_apply_leaves_every_issue_file_byte_identical(
    tmp_path, monkeypatch, tool_name, arguments
) -> None:
    """No `apply` key at all → no write, and a description of the intended change."""
    _make_project(tmp_path, monkeypatch)
    before = _snapshot(tmp_path)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return _payload(await client.call_tool(tool_name, arguments))

    payload = anyio.run(run)

    assert _snapshot(tmp_path) == before, f"{tool_name} wrote to disk without `apply`"
    assert payload["applied"] is False
    assert payload["tool"] == tool_name
    assert payload["changes"], "dry-run must describe the intended change"


@pytest.mark.parametrize(
    "apply_value",
    [False, None, "true", 1, "yes"],
    ids=["false", "null", "string-true", "int-1", "string-yes"],
)
def test_ac2_only_literal_true_opts_in(tmp_path, monkeypatch, apply_value) -> None:
    """Fail closed: any non-`True` value for `apply` means do not write."""
    _make_project(tmp_path, monkeypatch)
    before = _snapshot(tmp_path)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return await client.call_tool(
                "issue_set_status",
                {"issue_id": "FEAT-501", "status": "deferred", "apply": apply_value},
            )

    result = anyio.run(run)

    assert _snapshot(tmp_path) == before, (
        f"apply={apply_value!r} was treated as an opt-in — the guard must fail closed"
    )
    if not result.is_error:
        assert json.loads(result.content[0].text)["applied"] is False


# --------------------------------------------------------------------------------------
# AC 3 — apply performs the same mutation the backing library call performs
# --------------------------------------------------------------------------------------


def test_ac3_set_status_apply_matches_direct_library_call(tmp_path, monkeypatch) -> None:
    """`issue_set_status` with apply produces the same file state as the CLI's own core."""
    _make_project(tmp_path, monkeypatch)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return _payload(
                await client.call_tool(
                    "issue_set_status",
                    {"issue_id": "FEAT-501", "status": "deferred", "apply": True},
                )
            )

    payload = anyio.run(run)
    assert payload["applied"] is True
    via_tool = _source(tmp_path).read_text(encoding="utf-8")

    # Identical fixture, mutated through the backing library function directly.
    from little_loops.cli.issues.set_status import apply_status_transition
    from little_loops.config import BRConfig

    reference_root = tmp_path / "reference"
    (reference_root / ".issues" / "features").mkdir(parents=True)
    reference = reference_root / ".issues" / "features" / "P2-FEAT-501-sample-issue.md"
    reference.write_text(ISSUE_BODY, encoding="utf-8")
    apply_status_transition(BRConfig(reference_root), reference, "FEAT-501", "deferred")

    from little_loops.frontmatter import parse_frontmatter

    tool_fm = parse_frontmatter(via_tool)
    ref_fm = parse_frontmatter(reference.read_text(encoding="utf-8"))
    assert tool_fm["status"] == ref_fm["status"] == "deferred"
    # `deferred_date` is a timestamp, so compare the fields that are not time-dependent.
    assert tool_fm["deferred_by"] == ref_fm["deferred_by"]
    assert set(tool_fm) == set(ref_fm)


def test_ac3_link_apply_writes_the_edge(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return _payload(
                await client.call_tool(
                    "issue_link",
                    {
                        "issue_id": "FEAT-501",
                        "field": "relates_to",
                        "target": "BUG-502",
                        "apply": True,
                    },
                )
            )

    payload = anyio.run(run)
    assert payload["applied"] is True

    from little_loops.frontmatter import parse_frontmatter

    assert parse_frontmatter(_source(tmp_path).read_text(encoding="utf-8"))["relates_to"] == [
        "BUG-502"
    ]


def test_ac3_append_log_apply_writes_an_entry(tmp_path, monkeypatch) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return await client.call_tool(
                "issue_append_log",
                {"issue_id": "FEAT-501", "command": "/ll:manage-issue", "apply": True},
            )

    result = anyio.run(run)
    text = _source(tmp_path).read_text(encoding="utf-8")
    if result.is_error:
        # `append_session_log_entry` returns False when no session JSONL resolves
        # (the normal case under pytest); the tool surfaces that as a tool error.
        assert "session" in result.content[0].text.lower()
        assert "/ll:manage-issue" not in text
    else:
        assert json.loads(result.content[0].text)["applied"] is True
        assert "- `/ll:manage-issue`" in text


def test_ac3a_capture_dry_run_has_no_issue_id_apply_does(tmp_path, monkeypatch) -> None:
    """Decision 1: the dry-run response names no ID; the apply response carries the real one."""
    _make_project(tmp_path, monkeypatch)
    arguments = {"type": "BUG", "title": "A newly noticed bug", "priority": "P1"}

    async def run() -> tuple[Any, Any]:
        async with Client(build_server()) as client:
            dry = _payload(await client.call_tool("issue_capture", dict(arguments)))
            applied = _payload(
                await client.call_tool("issue_capture", {**arguments, "apply": True})
            )
            return dry, applied

    dry, applied = anyio.run(run)

    # AC 3a: schema check — no ID field anywhere in the dry-run payload, not even predicted.
    assert not _contains_key(dry, "issue_id")
    assert not _contains_key(dry, "id")
    assert not _contains_key(dry, "predicted_id")
    # It does describe the shape of what would be written.
    assert dry["target"]["type"] == "BUG"
    assert dry["target"]["priority"] == "P1"
    assert dry["target"]["slug"]
    assert dry["target"]["directory"]
    assert dry["rendered_body"]

    # The apply response's ID equals the created file's frontmatter `id`.
    from little_loops.frontmatter import parse_frontmatter

    issue_id = applied["target"]["issue_id"]
    created = Path(applied["target"]["path"])
    assert created.exists()
    assert parse_frontmatter(created.read_text(encoding="utf-8"))["id"] == issue_id


# --------------------------------------------------------------------------------------
# AC 4 — tool-level errors, not exceptions into the SDK dispatch loop
# --------------------------------------------------------------------------------------


ERROR_CALLS = [
    ("issue_set_status", {"issue_id": "FEAT-9999", "status": "done", "apply": True}),
    ("issue_set_status", {"issue_id": "FEAT-501", "status": "finished", "apply": True}),
    (
        "issue_link",
        {"issue_id": "FEAT-501", "field": "relates_to", "target": "NOPE-1", "apply": True},
    ),
    ("issue_link", {"issue_id": "FEAT-501", "field": "not_a_field", "target": "BUG-502"}),
    ("issue_capture", {"type": "WIDGET", "title": "bad type", "apply": True}),
    ("issue_append_log", {"issue_id": "FEAT-9999", "command": "/ll:manage-issue"}),
]


@pytest.mark.parametrize(
    "tool_name,arguments", ERROR_CALLS, ids=[f"{n}-{i}" for i, (n, _) in enumerate(ERROR_CALLS)]
)
def test_ac4_invalid_input_returns_is_error(tmp_path, monkeypatch, tool_name, arguments) -> None:
    _make_project(tmp_path, monkeypatch)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return await client.call_tool(tool_name, arguments)

    result = anyio.run(run)
    assert result.is_error is True, f"{tool_name}{arguments} should be a tool error"
    assert result.content[0].text


def test_ac4_errors_do_not_write(tmp_path, monkeypatch) -> None:
    """An invalid status is rejected before anything reaches the filesystem."""
    _make_project(tmp_path, monkeypatch)
    before = _snapshot(tmp_path)

    async def run() -> Any:
        async with Client(build_server()) as client:
            return await client.call_tool(
                "issue_set_status",
                {"issue_id": "FEAT-501", "status": "finished", "apply": True},
            )

    result = anyio.run(run)
    assert result.is_error is True
    assert _snapshot(tmp_path) == before

"""ll-mcp's `ll://` resource surface (FEAT-3136).

`ll-mcp` exposes issue files, `ll-goals.md`, and docs as MCP resources under an `ll://`
scheme (`ll://issues/<ID>`, `ll://goals`, `ll://docs/<relative-path>`). Because this server
is reachable by arbitrary MCP clients, `resources/read` never performs a filesystem read
derived directly from client-supplied input: `build_resource_index()` walks the resource set
once at server construction and records the exact set of readable `(uri -> path)` pairs; a
read request is only served when its `uri` is a key already present in that dict — dict
membership *is* the rejection mechanism, not path sanitization.

This is the first stateful construct in `mcp_server/` — a deliberate, scoped departure from
`tools.py`'s statelessness invariant (every tool handler resolves fresh from `Path.cwd()` on
every call). The index is built once per `Server` instance in `build_server()` and closed
over by the handlers here, not stored at module scope, so it never leaks across servers/tests.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mcp_types as types
from mcp.shared.exceptions import MCPError

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_ISSUE_ID_RE = re.compile(r"(BUG|FEAT|ENH|EPIC)-(\d+)", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class _ResourceEntry:
    """One discovery-time-enumerated `ll://` resource."""

    uri: str
    name: str
    description: str | None
    mime_type: str
    kind: str  # "issue" | "goals" | "docs"
    path: Path


def _issue_entries(config: BRConfig) -> list[_ResourceEntry]:
    """Enumerate issue files as `ll://issues/<ID>` entries.

    Walks the type-scoped category dirs plus `config.legacy_issue_dirs()` (BUG-2733) — the
    same search-dir set `_resolve_issue_id` uses — so status (open/done/deferred) doesn't
    affect discoverability. Name/description come from frontmatter only (`title`), never a
    full-body parse, per the "list cheaply, read on demand" split this issue calls for.
    """
    from little_loops.frontmatter import parse_frontmatter

    search_dirs = [config.get_issue_dir(category) for category in config.issue_categories]
    search_dirs.extend(config.legacy_issue_dirs())

    entries: dict[str, _ResourceEntry] = {}
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for md_path in sorted(search_dir.glob("*.md")):
            match = _ISSUE_ID_RE.search(md_path.name)
            if match is None:
                continue
            issue_id = f"{match.group(1).upper()}-{match.group(2)}"
            uri = f"ll://issues/{issue_id}"
            if uri in entries:
                continue
            try:
                content = md_path.read_text()
            except OSError:
                continue
            title = parse_frontmatter(content).get("title")
            entries[uri] = _ResourceEntry(
                uri=uri,
                name=issue_id,
                description=str(title) if title else None,
                mime_type="application/json",
                kind="issue",
                path=md_path,
            )
    return list(entries.values())


def _goals_entry(config: BRConfig) -> _ResourceEntry | None:
    """Enumerate `.ll/ll-goals.md` as the single `ll://goals` entry, if it exists."""
    path = config.project_root / ".ll" / "ll-goals.md"
    if not path.is_file():
        return None
    return _ResourceEntry(
        uri="ll://goals",
        name="goals",
        description="Project product goals, persona, and strategic priorities.",
        mime_type="text/markdown",
        kind="goals",
        path=path,
    )


def _docs_entries(config: BRConfig) -> list[_ResourceEntry]:
    """Enumerate `docs/**/*.md` as `ll://docs/<relative-path>` entries.

    No frontmatter convention exists under `docs/` (170+ files, no shared header shape), so
    entries carry no description — unlike issues, there's no cheap structured field to pull.
    """
    docs_dir = config.project_root / "docs"
    if not docs_dir.is_dir():
        return []
    entries = []
    for md_path in sorted(docs_dir.rglob("*.md")):
        rel = md_path.relative_to(docs_dir).as_posix()
        entries.append(
            _ResourceEntry(
                uri=f"ll://docs/{rel}",
                name=rel,
                description=None,
                mime_type="text/markdown",
                kind="docs",
                path=md_path,
            )
        )
    return entries


def build_resource_index(config: BRConfig) -> dict[str, _ResourceEntry]:
    """Build the discovery-time enumeration once: the full `uri -> _ResourceEntry` map.

    This is the allowlist `resources/read` resolves against — see the module docstring.
    """
    index: dict[str, _ResourceEntry] = {}
    for entry in _issue_entries(config):
        index[entry.uri] = entry
    goals_entry = _goals_entry(config)
    if goals_entry is not None:
        index[goals_entry.uri] = goals_entry
    for entry in _docs_entries(config):
        index[entry.uri] = entry
    return index


def _read_issue_body(entry: _ResourceEntry, config: BRConfig) -> str:
    """Mirror `_tool_issue_get`'s `_parse_card_fields` call, guarding its unguarded read.

    `_parse_card_fields()` (`cli/issues/show.py:166`) calls `path.read_text()` with no
    surrounding try/except; a resource whose backing file was deleted or became unreadable
    between discovery-time enumeration and this read needs a clean MCP error instead of an
    uncaught `OSError` reaching the SDK dispatch loop.
    """
    from little_loops.cli.issues.show import _parse_card_fields

    try:
        fields = _parse_card_fields(entry.path, config)
    except OSError as exc:
        raise MCPError(
            code=types.INVALID_PARAMS,
            message=f"Issue resource unreadable: {exc}",
            data={"uri": entry.uri},
        ) from exc
    return json.dumps(fields)


def _read_goals_body(entry: _ResourceEntry) -> str:
    """`ProductGoals.from_file()` is null-safe end to end; a `None` result means malformed."""
    from little_loops.goals_parser import ProductGoals

    goals = ProductGoals.from_file(entry.path)
    if goals is None:
        raise MCPError(
            code=types.INVALID_PARAMS,
            message="Goals file is missing or malformed",
            data={"uri": entry.uri},
        )
    return goals.raw_content


def _read_docs_body(entry: _ResourceEntry) -> str:
    try:
        return entry.path.read_text()
    except OSError as exc:
        raise MCPError(
            code=types.INVALID_PARAMS,
            message=f"Docs resource unreadable: {exc}",
            data={"uri": entry.uri},
        ) from exc


def _read_body(entry: _ResourceEntry, config: BRConfig) -> str:
    if entry.kind == "issue":
        return _read_issue_body(entry, config)
    if entry.kind == "goals":
        return _read_goals_body(entry)
    return _read_docs_body(entry)


def make_list_resources_handler(index: dict[str, _ResourceEntry]) -> Any:
    """Build the `resources/list` handler, closing over the enumeration built once at startup.

    `ttlMs`/`cacheScope` are left unset here, same as `handle_list_tools` — the
    `Server(cache_hints=...)` entry for `"resources/list"` fills them per SEP-2549.
    """
    resources = [
        types.Resource(
            uri=entry.uri,
            name=entry.name,
            description=entry.description,
            mime_type=entry.mime_type,
        )
        for entry in index.values()
    ]

    async def handle_list_resources(
        _ctx: Any,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=resources)

    return handle_list_resources


def make_read_resource_handler(index: dict[str, _ResourceEntry], config: BRConfig) -> Any:
    """Build the `resources/read` handler, closing over the same enumeration and `config`.

    A `uri` absent from `index` is rejected outright — the dict lookup below is the entire
    access-control boundary, and no filesystem read happens before or instead of it.
    """

    async def handle_read_resource(
        _ctx: Any,
        params: types.ReadResourceRequestParams,
    ) -> types.ReadResourceResult:
        entry = index.get(params.uri)
        if entry is None:
            raise MCPError(
                code=types.INVALID_PARAMS,
                message=f"Unknown resource: {params.uri}",
                data={"uri": params.uri},
            )
        text = _read_body(entry, config)
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(uri=entry.uri, mime_type=entry.mime_type, text=text)
            ]
        )

    return handle_read_resource

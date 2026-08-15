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

ENH-3172: the once-built index goes stale the moment an issue is created, deleted, or
renamed after startup — which the server itself can now trigger (`issue_capture`, tier 2;
`loop_start`, tier 3). `ResourceIndex` wraps the dict in a cheap on-demand refresh
(`_staleness.dir_signature` over the watched dirs) so every handler call resolves against
a fresh enumeration instead of the discovery-time snapshot. Membership in `ResourceIndex.entries`
remains the sole access-control boundary — `refresh()` only decides *when* to rebuild it,
never whether a URI is admitted.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mcp_types as types
from mcp.shared.exceptions import MCPError

from little_loops.mcp_server._staleness import Signature, dir_signature

if TYPE_CHECKING:
    from mcp.server.subscriptions import SubscriptionBus

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


def _watched_paths(config: BRConfig) -> list[Path]:
    """Top-level dirs/files whose mtime signals the resource index may be stale."""
    paths = [config.get_issue_dir(category) for category in config.issue_categories]
    paths.extend(config.legacy_issue_dirs())
    paths.append(config.project_root / ".ll" / "ll-goals.md")
    paths.append(config.project_root / "docs")
    return paths


@dataclasses.dataclass
class ResourceIndex:
    """Mutable holder for the `ll://` enumeration, refreshed on demand (ENH-3172).

    Built once (`__post_init__`), then re-derived only when `refresh()` observes the
    watched-path signature has changed — cheap `stat()` calls, not a full re-walk, on
    every request that doesn't need one.
    """

    config: BRConfig
    entries: dict[str, _ResourceEntry] = dataclasses.field(default_factory=dict, init=False)
    _signature: Signature = dataclasses.field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        self.entries = build_resource_index(self.config)
        self._signature = dir_signature(_watched_paths(self.config))

    def refresh(self) -> bool:
        """Rebuild `entries` if the watched-path signature changed.

        Returns whether a rebuild happened, so callers can decide whether to notify
        subscribers and whether this response is safe to let a client cache.
        """
        signature = dir_signature(_watched_paths(self.config))
        if signature == self._signature:
            return False
        self.entries = build_resource_index(self.config)
        self._signature = signature
        return True


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


def make_list_resources_handler(index: ResourceIndex, bus: SubscriptionBus) -> Any:
    """Build the `resources/list` handler, closing over `index` and refreshing it per call.

    `ttlMs`/`cacheScope` are left unset on the common path, same as `handle_list_tools` —
    the `Server(cache_hints=...)` entry for `"resources/list"` fills them per SEP-2549. When
    `index.refresh()` rebuilds (ENH-3172), a `ResourcesListChanged` event is published on
    `bus` (delivered to any open `subscriptions/listen` stream) and this particular response
    has `ttl_ms=0` forced on it — the 5-minute public `CacheHint` is a safe default for an
    unchanged list, not for the one response that just proved the list changed.
    """
    from mcp.server.subscriptions import ResourcesListChanged

    def _resources() -> list[types.Resource]:
        return [
            types.Resource(
                uri=entry.uri,
                name=entry.name,
                description=entry.description,
                mime_type=entry.mime_type,
            )
            for entry in index.entries.values()
        ]

    async def handle_list_resources(
        _ctx: Any,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListResourcesResult:
        changed = index.refresh()
        result = types.ListResourcesResult(resources=_resources())
        if changed:
            await bus.publish(ResourcesListChanged())
            result = result.model_copy(update={"ttl_ms": 0})
        return result

    return handle_list_resources


def make_read_resource_handler(index: ResourceIndex, config: BRConfig) -> Any:
    """Build the `resources/read` handler, closing over `index` and refreshing it per call.

    A `uri` absent from `index.entries` after the refresh is rejected outright — the dict
    lookup below is the entire access-control boundary, and no filesystem read happens
    before or instead of it.
    """

    async def handle_read_resource(
        _ctx: Any,
        params: types.ReadResourceRequestParams,
    ) -> types.ReadResourceResult:
        index.refresh()
        entry = index.entries.get(params.uri)
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

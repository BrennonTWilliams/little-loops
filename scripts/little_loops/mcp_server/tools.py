"""ll-mcp's five coarse read-only tools (FEAT-3135).

Each tool wraps an existing `little_loops` library function or helper directly — no CLI
subprocess invocation, and no second implementation of behavior the CLI already has. Any
divergence between a tool's output and its CLI equivalent is a bug in this module, not a
design choice.

The tool surface is deliberately coarse (anti-goal: do not mirror all ~40 `ll-issues`
subcommands as tools — that is a context-budget disaster) and read-only (anti-goal: no
orchestration tool — `ll-auto`/`ll-parallel`/`ll-loop`/`ll-action invoke` stay off the
surface entirely).

Every handler resolves entirely from its own `arguments` dict plus the filesystem/SQLite —
none reads or writes state established by a prior request or cached across calls (the
2026-07-28 statelessness invariant): a fresh `BRConfig` is built from `Path.cwd()` on every
call rather than once at module or server-construction time.

JSON encoding follows existing per-type precedent rather than inventing a fourth convention:
`dataclasses.asdict()` for `SearchResult` (`history_search`), a hand-rolled dict for
`CapabilityReport` (`capabilities`, mirroring `cli/doctor.py::_print_report`), and the
tuple-to-`list(pair)` shape from `cli/deps.py` (`deps_check`). This keeps each tool's payload
byte-identical to its CLI equivalent.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp.server.context import ServerRequestContext


def _project_root() -> Path:
    """Resolve the project root fresh on every call — never cached across requests."""
    return Path.cwd()


def _tool_issues_query(arguments: dict[str, Any]) -> Any:
    """List issues, tagged with frontmatter status, filtered and sorted.

    Wraps `cli.issues.search._load_issues_with_status` — the same non-argparse helper
    `ll-issues search` itself calls — rather than synthesizing an `argparse.Namespace` to
    drive `cmd_search` directly.
    """
    from little_loops.cli.issues.search import _load_issues_with_status
    from little_loops.config import BRConfig

    config = BRConfig(_project_root())

    status = str(arguments.get("status") or "open")
    include_open = status in ("open", "all")
    include_done = status in ("done", "all")
    include_deferred = status in ("deferred", "all")

    results = _load_issues_with_status(config, include_open, include_done, include_deferred)

    issue_type = arguments.get("issue_type")
    if issue_type:
        wanted_type = str(issue_type).upper()
        results = [r for r in results if r[0].issue_id.split("-", 1)[0] == wanted_type]

    priority = arguments.get("priority")
    if priority:
        wanted_priority = str(priority).upper()
        results = [r for r in results if r[0].priority == wanted_priority]

    results.sort(key=lambda r: (r[0].priority_int, r[0].issue_id))

    limit = arguments.get("limit")
    if isinstance(limit, int) and limit > 0:
        results = results[:limit]

    return [
        {
            "id": issue.issue_id,
            "priority": issue.priority,
            "type": issue.issue_id.split("-", 1)[0],
            "title": issue.title,
            "path": str(issue.path),
            "status": issue_status,
            "parent": issue.parent,
            "labels": issue.labels,
        }
        for issue, issue_status in results
    ]


def _tool_issue_get(arguments: dict[str, Any]) -> Any:
    """Return the full summary-card field dict for a single issue.

    Wraps `cli.issues.show._parse_card_fields` — the same non-argparse helper `ll-issues
    show` forwards to `print_json`/`_render_card` — after resolving the user-supplied ID via
    `_resolve_issue_id` (accepts numeric, `TYPE-NNN`, or `P#-TYPE-NNN` forms).
    """
    from little_loops.cli.issues.show import _parse_card_fields, _resolve_issue_id
    from little_loops.config import BRConfig

    config = BRConfig(_project_root())
    issue_id = str(arguments.get("issue_id") or "")
    path = _resolve_issue_id(config, issue_id)
    if path is None:
        raise ValueError(f"Issue not found: {issue_id!r}")
    return _parse_card_fields(path, config)


def _tool_history_search(arguments: dict[str, Any]) -> Any:
    """FTS5 full-text search over `.ll/history.db`, optionally filtered by kind.

    Wraps `history_reader.search()` directly; results marshal via `dataclasses.asdict()`,
    the existing convention for plain dataclasses elsewhere in the CLI surface.
    """
    from little_loops.history_reader import search

    query = str(arguments.get("query") or "")
    kind = arguments.get("kind")
    limit = arguments.get("limit", 10)
    if not isinstance(limit, int) or limit <= 0:
        limit = 10

    results = search(query, kind=kind, limit=limit)
    return [dataclasses.asdict(r) for r in results]


def _tool_deps_check(_arguments: dict[str, Any]) -> Any:
    """Validate the cross-issue dependency graph: broken refs, cycles, stale/missing links.

    Wraps `cli.deps._load_issues()` (the same assembly function `ll-deps validate` uses) plus
    `dependency_mapper.validate_dependencies()`; the response shape mirrors
    `cli/deps.py`'s `--json` encoding exactly (tuple pairs as `list(pair)`).
    """
    from little_loops.cli.deps import _load_issues
    from little_loops.config import BRConfig
    from little_loops.dependency_mapper import gather_all_issue_ids, validate_dependencies

    config = BRConfig(_project_root())
    issues_dir = config.project_root / config.issues.base_dir

    issues, _issue_contents, completed_ids = _load_issues(issues_dir)

    try:
        all_known_ids = gather_all_issue_ids(issues_dir, config=config)
    except Exception:  # pragma: no cover - defensive, mirrors cli/deps.py
        all_known_ids = {i.issue_id for i in issues}

    result = validate_dependencies(issues, completed_ids, all_known_ids)

    return {
        "has_issues": result.has_issues,
        "broken_refs": [list(pair) for pair in result.broken_refs],
        "missing_backlinks": [list(pair) for pair in result.missing_backlinks],
        "cycles": result.cycles,
        "stale_completed_refs": [list(pair) for pair in result.stale_completed_refs],
        "broken_depends_on_refs": [list(pair) for pair in result.broken_depends_on_refs],
        "broken_relates_to_refs": [list(pair) for pair in result.broken_relates_to_refs],
    }


def _tool_capabilities(_arguments: dict[str, Any]) -> Any:
    """Report the resolved host runner's capability surface.

    Wraps `host_runner.resolve_host().describe_capabilities()`; the response shape mirrors
    the hand-rolled dict `cli/doctor.py::_print_report` builds from the same `CapabilityReport`
    dataclass (no call site anywhere passes it to `dataclasses.asdict()`).
    """
    from little_loops.host_runner import resolve_host

    report = resolve_host().describe_capabilities()
    return {
        "host": report.host,
        "binary": report.binary,
        "version": report.version,
        "capabilities": [
            {"name": c.name, "status": c.status, "note": c.note} for c in report.capabilities
        ],
    }


_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "issues_query": _tool_issues_query,
    "issue_get": _tool_issue_get,
    "history_search": _tool_history_search,
    "deps_check": _tool_deps_check,
    "capabilities": _tool_capabilities,
}

# Source-order literal: `list_tools` returns this list as-is, and list order is the entirety
# of the ordering guarantee — no separate sort step, no precedent to follow beyond this.
_TOOLS: list[types.Tool] = [
    types.Tool(
        name="issues_query",
        description=(
            "List little-loops issues (bugs/features/enhancements/epics), tagged with "
            "frontmatter status, filtered by status/type/priority and sorted by priority."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["open", "done", "deferred", "all"],
                    "description": "Status bucket to include. Default: open.",
                },
                "issue_type": {
                    "type": "string",
                    "enum": ["BUG", "FEAT", "ENH", "EPIC"],
                    "description": "Restrict to one issue type.",
                },
                "priority": {
                    "type": "string",
                    "pattern": "^P[0-5]$",
                    "description": "Restrict to one priority level, e.g. P1.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of issues to return.",
                },
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="issue_get",
        description="Fetch the full summary-card field set for a single issue by ID.",
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Issue ID in any of: '3135', 'FEAT-3135', 'P3-FEAT-3135'.",
                },
            },
            "required": ["issue_id"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="history_search",
        description=(
            "Full-text search over the project's .ll/history.db (tool calls, file edits, "
            "issue transitions, user corrections, session messages)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "FTS5 phrase to search for."},
                "kind": {
                    "type": "string",
                    "enum": ["tool", "file", "issue", "loop", "correction", "message"],
                    "description": "Restrict results to one event kind.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of results. Default: 10.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="deps_check",
        description=(
            "Validate the cross-issue dependency graph: broken references, missing "
            "backlinks, cycles, and stale references to completed issues."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="capabilities",
        description="Report the resolved AI-host CLI's capability surface (streaming, tool allowlist, etc).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
]


async def handle_list_tools(
    _ctx: ServerRequestContext[Any],
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    """`tools/list` handler: returns the fixed five-tool catalog in source order.

    `ttlMs`/`cacheScope` are left unset here — the `Server(cache_hints=...)` passed in
    `little_loops.mcp_server.server.build_server` fills them, per SEP-2549.
    """
    return types.ListToolsResult(tools=_TOOLS)


async def handle_call_tool(
    _ctx: ServerRequestContext[Any],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    """`tools/call` handler: dispatches to the named tool's handler function.

    Any exception raised by a tool handler (unknown issue ID, invalid FTS5 query, no host
    configured, ...) becomes a tool-level error result (`is_error=True`) rather than an
    uncaught exception reaching the SDK's dispatch loop — MCP's contract for a tool that
    failed on its own terms, as opposed to a transport/protocol fault.
    """
    handler = _TOOL_HANDLERS.get(params.name)
    if handler is None:
        return types.CallToolResult(
            content=[types.TextContent(text=f"Unknown tool: {params.name}")],
            is_error=True,
        )

    try:
        payload = handler(params.arguments or {})
    except Exception as exc:
        return types.CallToolResult(
            content=[types.TextContent(text=str(exc))],
            is_error=True,
        )

    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(payload))],
        structured_content=payload,
    )

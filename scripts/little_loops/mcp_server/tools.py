"""ll-mcp's tool surface: eight coarse read-only tools (FEAT-3135, plus `queue_list`/
`queue_get`/`loop_list`) plus seven guarded mutation tools (FEAT-3149, plus `queue_add`/
`queue_remove`/`queue_requeue`).

Each tool wraps an existing `little_loops` library function or helper directly — no CLI
subprocess invocation, and no second implementation of behavior the CLI already has. Any
divergence between a tool's output and its CLI equivalent is a bug in this module, not a
design choice.

The tool surface is deliberately coarse (anti-goal: do not mirror all ~40 `ll-issues`
subcommands as tools — that is a context-budget disaster). Orchestration stays off it
entirely (`ll-auto`/`ll-parallel`/`ll-loop`/`ll-action invoke` are tier 3, separately
evidence-gated).

The four mutating tools are dry-run **by default**: an `apply` parameter that is absent or
anything other than the literal `True` produces a description of the intended change and
writes nothing. This is a refusal-to-mutate default, not an opt-out flag — see
`handle_call_tool` for the wrapper that enforces it, and `policy.py` for the registry of
which tools count as mutating and the per-transport policy that gates them.

Every handler resolves entirely from its own `arguments` dict, the `project_root` closed
over by `make_call_tool_handler` (ENH-3171), plus the filesystem/SQLite — none reads or
writes state established by a prior request or cached across calls (the 2026-07-28
statelessness invariant): a fresh `BRConfig` is built from the resolved `project_root` on
every call rather than the resolution itself being repeated or cached at module scope.

JSON encoding follows existing per-type precedent rather than inventing a fourth convention:
`dataclasses.asdict()` for `SearchResult` (`history_search`), a hand-rolled dict for
`CapabilityReport` (`capabilities`, mirroring `cli/doctor.py::_print_report`), and the
tuple-to-`list(pair)` shape from `cli/deps.py` (`deps_check`). This keeps each tool's payload
byte-identical to its CLI equivalent.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.shared.exceptions import MCPError

from little_loops.mcp_server.policy import MUTATING_TOOLS, POLICY_DENIED_CODE, check_tool_call


def _project_root(explicit: Path | None = None) -> Path:
    """Resolve the project root: ``explicit``, then ``LL_MCP_PROJECT_ROOT``, then cwd (ENH-3171).

    Called once by `main_mcp` at startup; the resolved value is threaded down through the
    same factory-closure shape `transport` already uses (FEAT-3168) rather than being
    re-resolved — or cached as a module global — on every call, so two `Server` instances
    built in the same process (as in tests) can never leak each other's resolved root.
    """
    if explicit is not None:
        return explicit
    env_root = os.environ.get("LL_MCP_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    return Path.cwd()


def _looks_like_project_root(project_root: Path) -> bool:
    """Whether ``project_root`` has either marker directory a little-loops project has.

    Used both for `capabilities`' `project_root.resolved` field and `main_mcp`'s startup
    stderr warning (ENH-3171 "Secondary: fail loudly on a non-project root") — a resolved
    root with neither directory answers every other tool truthfully about a project that
    does not exist there, with no error and no warning.
    """
    return (project_root / ".ll").is_dir() or (project_root / ".issues").is_dir()


def _tool_issues_query(arguments: dict[str, Any], *, project_root: Path) -> Any:
    """List issues, tagged with frontmatter status, filtered and sorted.

    Wraps `cli.issues.search._load_issues_with_status` — the same non-argparse helper
    `ll-issues search` itself calls — rather than synthesizing an `argparse.Namespace` to
    drive `cmd_search` directly.
    """
    from little_loops.cli.issues.search import _load_issues_with_status
    from little_loops.config import BRConfig

    config = BRConfig(project_root)

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


def _tool_issue_get(arguments: dict[str, Any], *, project_root: Path) -> Any:
    """Return the full summary-card field dict for a single issue.

    Wraps `cli.issues.show._parse_card_fields` — the same non-argparse helper `ll-issues
    show` forwards to `print_json`/`_render_card` — after resolving the user-supplied ID via
    `_resolve_issue_id` (accepts numeric, `TYPE-NNN`, or `P#-TYPE-NNN` forms).
    """
    from little_loops.cli.issues.show import _parse_card_fields, _resolve_issue_id
    from little_loops.config import BRConfig

    config = BRConfig(project_root)
    issue_id = str(arguments.get("issue_id") or "")
    path = _resolve_issue_id(config, issue_id)
    if path is None:
        raise ValueError(f"Issue not found: {issue_id!r}")
    return _parse_card_fields(path, config)


def _tool_history_search(arguments: dict[str, Any], *, project_root: Path) -> Any:
    """FTS5 full-text search over `.ll/history.db`, optionally filtered by kind.

    Wraps `history_reader.search()` directly; results marshal via `dataclasses.asdict()`,
    the existing convention for plain dataclasses elsewhere in the CLI surface.

    BUG-3181: `history.db` is per-project, not process-global — `search()`'s `db` default
    is the *relative* `.ll/history.db`, which resolves against whatever cwd the host
    happened to spawn this server with. The DB is resolved here through the shared
    `resolve_history_db`, anchored at `project_root` (`root=`), so the established
    precedence — `LL_HISTORY_DB`, then `history.db_path`, then
    `<project_root>/.ll/history.db` — applies without a second resolution living in this
    module.
    """
    from little_loops.history_reader import search
    from little_loops.session_store import DEFAULT_DB_PATH, resolve_history_db

    query = str(arguments.get("query") or "")
    kind = arguments.get("kind")
    limit = arguments.get("limit", 10)
    if not isinstance(limit, int) or limit <= 0:
        limit = 10

    db = resolve_history_db(project_root / DEFAULT_DB_PATH, root=project_root)
    results = search(query, kind=kind, limit=limit, db=db)
    return [dataclasses.asdict(r) for r in results]


def _tool_deps_check(_arguments: dict[str, Any], *, project_root: Path) -> Any:
    """Validate the cross-issue dependency graph: broken refs, cycles, stale/missing links.

    Wraps `cli.deps._load_issues()` (the same assembly function `ll-deps validate` uses) plus
    `dependency_mapper.validate_dependencies()`; the response shape mirrors
    `cli/deps.py`'s `--json` encoding exactly (tuple pairs as `list(pair)`).
    """
    from little_loops.cli.deps import _load_issues
    from little_loops.config import BRConfig
    from little_loops.dependency_mapper import gather_all_issue_ids, validate_dependencies

    config = BRConfig(project_root)
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


def _tool_capabilities(_arguments: dict[str, Any], *, project_root: Path) -> Any:
    """Report the resolved host runner's capability surface.

    Wraps `host_runner.resolve_host().describe_capabilities()`; the response shape mirrors
    the hand-rolled dict `cli/doctor.py::_print_report` builds from the same `CapabilityReport`
    dataclass (no call site anywhere passes it to `dataclasses.asdict()`).

    Also carries `project_root` (ENH-3171 "Secondary: fail loudly on a non-project root"):
    the one tool a user runs first when verifying the server, so a client that swallows
    stderr still gets the misconfiguration signal through here.
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
        "project_root": {
            "path": str(project_root),
            "resolved": _looks_like_project_root(project_root),
        },
    }


# ---------------------------------------------------------------------------------------
# Tier 2 (FEAT-3149): guarded mutation tools.
#
# Each of the four wraps the same non-printing library function the equivalent `ll-issues`
# subcommand calls — never the `cmd_*` function itself. That is not a style preference:
# `cmd_set_status`/`cmd_link` write their results to stdout, and on the stdio transport
# stdout *is* the JSON-RPC frame, so calling them here would corrupt the protocol.
# FEAT-3149 extracted `apply_status_transition`/`apply_link`/`render_issue_preview`/
# `format_session_log_entry` for exactly this reason, so there is still one implementation
# of each mutation rather than a second one living in the MCP layer.
#
# Every handler takes `apply` as a REQUIRED keyword. That is the enforcement mechanism for
# Guard 1: a future mutating tool whose author forgets to think about dry-run cannot
# silently write, because dispatch passes `apply=` and a handler that does not accept it
# raises TypeError. The wrapper in `handle_call_tool` owns reading the flag, failing
# closed, and stamping the response — one place to audit.
# ---------------------------------------------------------------------------------------


def _tool_issue_capture(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Create a new issue file (`ll-issues create`).

    Wraps `cli.issues.create.create_issue` for apply and `render_issue_preview` for
    dry-run. Per FEAT-3149 Decision 1 the dry-run response carries **no issue ID**, not
    even a predicted one: allocation happens inside `create_issue`'s lock hold, so any ID
    produced beforehand is a guess that is wrong exactly when it matters — when something
    else allocated concurrently. The apply response carries the real allocated ID, which
    is the only value that was ever true.
    """
    from little_loops.cli.issues.create import IssueSpec, create_issue, render_issue_preview
    from little_loops.config import BRConfig

    config = BRConfig(project_root)

    title = str(arguments.get("title") or "").strip()
    if not title:
        raise ValueError("issue_capture requires a non-empty title")

    labels = arguments.get("labels") or []
    if not isinstance(labels, list):
        raise ValueError("issue_capture 'labels' must be a list of strings")

    spec = IssueSpec(
        type=str(arguments.get("type") or "").upper(),
        title=title,
        priority=str(arguments.get("priority") or "P2").upper(),
        body=arguments.get("body"),
        parent=arguments.get("parent"),
        labels=[str(label) for label in labels],
    )

    if not apply:
        preview = render_issue_preview(config, spec)
        return {
            "target": {
                "type": preview["type"],
                "priority": preview["priority"],
                "slug": preview["slug"],
                "directory": preview["directory"],
            },
            "rendered_body": preview["rendered_body"],
            "id_allocation": (
                "The issue ID is allocated at apply time, under the .issues/.id-alloc.lock "
                "hold — it does not exist yet and is deliberately not predicted here."
            ),
            "changes": [
                {
                    "field": "file",
                    "from": None,
                    "to": f"{preview['directory']}/{preview['priority']}-{preview['type']}"
                    f"-<id>-{preview['slug']}.md",
                }
            ],
        }

    created = create_issue(config, spec)
    return {
        "target": {"issue_id": created.id, "path": str(created.path)},
        "changes": [{"field": "file", "from": None, "to": str(created.path)}],
    }


def _tool_issue_set_status(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Transition an issue's frontmatter status (`ll-issues set-status`).

    Wraps `cli.issues.set_status.apply_status_transition`; the dry-run preview comes from
    `status_frontmatter_updates`, the same function that computes the real write, so the
    preview cannot drift from what apply does. `--cascade` is deliberately not exposed:
    cascading multiplies the blast radius across a whole EPIC subtree, and tier 2's brief
    is four coarse tools, not a full mirror of the CLI's flag surface.
    """
    from little_loops.cli.issues.set_status import (
        apply_status_transition,
        status_frontmatter_updates,
    )
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.config import BRConfig
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.issue_progress import _ALL_STATUSES

    config = BRConfig(project_root)

    issue_id = str(arguments.get("issue_id") or "")
    status = str(arguments.get("status") or "")
    if status not in _ALL_STATUSES:
        raise ValueError(
            f"Invalid status: {status!r} (expected one of {', '.join(sorted(_ALL_STATUSES))})"
        )

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        raise ValueError(f"Issue not found: {issue_id!r}")

    reason = arguments.get("reason")
    by = arguments.get("by")
    current = parse_frontmatter(path.read_text())
    target = {"issue_id": issue_id, "path": str(path)}

    if not apply:
        updates = status_frontmatter_updates(status, reason=reason, by=by)
        return {
            "target": target,
            "changes": [
                {"field": key, "from": current.get(key), "to": value}
                for key, value in updates.items()
            ],
        }

    result = apply_status_transition(config, path, issue_id, status, reason=reason, by=by)
    return {
        "target": target,
        "changes": [
            {"field": key, "from": current.get(key), "to": value}
            for key, value in result.updates.items()
        ],
    }


def _tool_issue_link(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Write or remove a cross-issue dependency edge (`ll-issues link`).

    Wraps `cli.issues.link.apply_link`, which already had a `dry_run` mode — so here the
    guard's `apply` flag maps straight onto it rather than onto a second preview path.
    """
    from little_loops.cli.issues.link import apply_link
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.config import BRConfig
    from little_loops.frontmatter import parse_frontmatter

    config = BRConfig(project_root)

    issue_id = str(arguments.get("issue_id") or "")
    field = str(arguments.get("field") or "")
    target_input = str(arguments.get("target") or "")
    unlink = arguments.get("unlink") is True

    path = _resolve_issue_id(config, issue_id)
    before: list[Any] = []
    if path is not None:
        existing = parse_frontmatter(path.read_text()).get(field) or []
        before = existing if isinstance(existing, list) else [existing]

    result = apply_link(
        config,
        issue_id=issue_id,
        field=field,
        target=target_input,
        unlink=unlink,
        reciprocal=arguments.get("reciprocal") is True,
        force=arguments.get("force") is True,
        dry_run=not apply,
    )

    if result.status in ("linked", "would_link"):
        after = [*before, result.target_id]
    elif result.status in ("unlinked", "would_unlink"):
        after = [item for item in before if item != result.target_id]
    else:  # unchanged
        after = before

    return {
        "target": {"issue_id": result.issue_id, "path": str(path) if path else None},
        "changes": [
            {"field": result.field, "from": before, "to": after, "operation": result.status}
        ],
    }


def _tool_issue_append_log(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Append a session-log entry to an issue (`ll-issues append-log`).

    Wraps `session_log.append_session_log_entry`; the dry-run renders the exact bullet via
    the shared `format_session_log_entry`. A dry-run whose session cannot be resolved still
    succeeds and says so, rather than erroring — the caller asked what *would* happen, and
    "this would fail, here is why" is a better answer to that question than an error.
    Apply, by contrast, raises: there is nothing to write.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.config import BRConfig
    from little_loops.session_log import append_session_log_entry, format_session_log_entry

    config = BRConfig(project_root)

    issue_id = str(arguments.get("issue_id") or "")
    command = str(arguments.get("command") or "").strip()
    if not command:
        raise ValueError("issue_append_log requires a non-empty command")

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        raise ValueError(f"Issue not found: {issue_id!r}")

    target = {"issue_id": issue_id, "path": str(path)}
    entry = format_session_log_entry(command)

    if not apply:
        payload: dict[str, Any] = {
            "target": target,
            "changes": [
                {
                    "field": "Session Log",
                    "from": None,
                    "to": entry or f"- `{command}` - <timestamp> - `<current session id>`",
                }
            ],
        }
        if entry is None:
            payload["note"] = (
                "The current session JSONL could not be resolved, so applying this call "
                "would fail. The entry above shows the shape it would take."
            )
        return payload

    if not append_session_log_entry(path, command):
        raise ValueError(
            "Could not resolve the current session JSONL; no session-log entry was written."
        )
    return {
        "target": target,
        "changes": [{"field": "Session Log", "from": None, "to": entry}],
    }


def _tool_queue_list(_arguments: dict[str, Any], *, project_root: Path) -> Any:
    """List all persisted `ll-queue` entries (`ll-queue list`).

    Wraps `queue_store.list_entries` directly, anchored at `project_root` via its `root`
    kwarg (mirrors `history_search`'s BUG-3181 fix: the process cwd this server happened
    to be spawned with is not necessarily `project_root`), and returns each entry's
    `to_dict()` shape — byte-identical to `ll-queue list --json`.
    """
    from little_loops.queue_store import list_entries

    entries = list_entries(root=project_root)
    return [entry.to_dict() for entry in entries]


def _tool_queue_get(arguments: dict[str, Any], *, project_root: Path) -> Any:
    """Fetch a single `ll-queue` entry by full id or 8+-char prefix (`ll-queue status`).

    Wraps `queue_store.resolve_entry`, the same id-resolution helper `ll-queue status`
    and `ll-queue remove`/`requeue` use.
    """
    from little_loops.queue_store import resolve_entry

    entry_id = str(arguments.get("id") or "")
    if not entry_id:
        raise ValueError("queue_get requires a non-empty id")

    entry = resolve_entry(entry_id, root=project_root)
    if entry is None:
        raise ValueError(f"Queue entry not found: {entry_id!r}")
    return entry.to_dict()


def _tool_loop_list(arguments: dict[str, Any], *, project_root: Path) -> Any:
    """List the project's loop catalog (`ll-loop list`).

    Wraps `enumerate_loop_catalog` (FEAT-3352) — the same non-printing enumeration
    `cmd_list` calls — anchored at `project_root` via `_loops_dir` (ENH-3171/BUG-3180)
    rather than the process cwd. `visibility` maps to the set-based signature: a single
    tier becomes a one-element set, `"all"` becomes `None` (show everything). Returns each
    entry's `to_json_item()` — byte-identical to `ll-loop list --json`.
    """
    from little_loops.cli.loop.info import enumerate_loop_catalog
    from little_loops.mcp_server.tasks import _loops_dir

    category = arguments.get("category")
    label = arguments.get("label")
    if label is not None and not isinstance(label, list):
        raise ValueError("loop_list 'label' must be a list of strings")

    visibility = str(arguments.get("visibility") or "public")
    visibilities: set[str] | None = None if visibility == "all" else {visibility}

    catalog = enumerate_loop_catalog(
        loops_dir=_loops_dir(project_root),
        category=str(category) if category else None,
        label=[str(lb) for lb in label] if label else None,
        visibilities=visibilities,
    )
    return [entry.to_json_item() for entry in catalog.entries]


def _tool_queue_add(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Classify and persist a new `ll-queue` entry (`ll-queue add`).

    Wraps `cli.queue._classify_action` (the same classifier `ll-queue add` calls) for the
    dry-run preview, then `queue_store.add_entry` to actually persist on `apply: true`.
    `--runner mcp`/`--runner loop` targets can themselves start further runs, so — like
    `loop_start` — this tool's dry-run preview is the caller's only chance to see what an
    apply would queue before it queues it.
    """
    from little_loops.cli.queue import _classify_action
    from little_loops.queue_store import add_entry

    target = str(arguments.get("target") or "")
    if not target:
        raise ValueError("queue_add requires a non-empty target")

    priority = str(arguments.get("priority") or "P3")
    runner_override = arguments.get("runner")
    timeout = arguments.get("timeout")
    input_value = arguments.get("input")
    arg_pairs = [f"{k}={v}" for k, v in dict(arguments.get("args") or {}).items()]

    spec = _classify_action(
        target,
        runner_override=str(runner_override) if runner_override else None,
        timeout=int(timeout) if isinstance(timeout, int) else None,
        arg_pairs=arg_pairs,
        input_value=str(input_value) if input_value is not None else None,
    )

    preview = {
        "name": spec.name,
        "runner": spec.runner.value,
        "target": spec.target,
        "args": spec.args,
        "timeout": spec.timeout,
        "priority": priority,
    }
    if not apply:
        return {"entry": preview}

    entry = add_entry(spec, priority, root=project_root)
    return {"entry": entry.to_dict()}


def _tool_queue_remove(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Delete a pending `ll-queue` entry by id (`ll-queue remove`).

    `--force` (removing a non-pending entry) is deliberately not exposed — mirrors
    `issue_link`'s precedent of trimming rare escape-hatch flags off tier 2's coarse
    surface.
    """
    from little_loops.queue_store import remove_entry, resolve_entry

    entry_id = str(arguments.get("id") or "")
    if not entry_id:
        raise ValueError("queue_remove requires a non-empty id")

    entry = resolve_entry(entry_id, root=project_root)
    if entry is None:
        raise ValueError(f"Queue entry not found: {entry_id!r}")
    if entry.status != "pending":
        raise ValueError(
            f"Queue entry {entry.id[:8]} is {entry.status!r}, not 'pending'; "
            "queue_remove only removes pending entries"
        )

    target = {"id": entry.id, "target": entry.action.target, "status": entry.status}
    if not apply:
        return {"target": target}

    remove_entry(entry.id, root=project_root)
    return {"target": target}


def _tool_queue_requeue(arguments: dict[str, Any], *, project_root: Path, apply: bool) -> Any:
    """Return a stranded `running` entry to `pending` (`ll-queue requeue`).

    `--force` (requeue even if the owner process still appears alive) is deliberately not
    exposed, for the same reason `queue_remove` drops `--force`: it is a rare escape-hatch
    flag, not part of tier 2's coarse brief.
    """
    from little_loops.queue_store import reset_to_pending, resolve_entry

    entry_id = str(arguments.get("id") or "")
    if not entry_id:
        raise ValueError("queue_requeue requires a non-empty id")

    entry = resolve_entry(entry_id, root=project_root)
    if entry is None:
        raise ValueError(f"Queue entry not found: {entry_id!r}")
    if entry.status != "running":
        raise ValueError(
            f"Queue entry {entry.id[:8]} is {entry.status!r}, not 'running'; "
            "queue_requeue only requeues running entries"
        )

    target = {"id": entry.id, "target": entry.action.target, "status": entry.status}
    if not apply:
        return {
            "target": target,
            "changes": [{"field": "status", "from": "running", "to": "pending"}],
        }

    reset_to_pending(entry.id, root=project_root)
    return {"target": target, "changes": [{"field": "status", "from": "running", "to": "pending"}]}


# ---------------------------------------------------------------------------------------
# Tier 3 (FEAT-3151): the SEP-2663 start-path tool.
#
# Always performs the identical detached spawn regardless of caller (Decision 2a) — the
# task-shaped vs plain-shaped response is decided entirely by `TasksExtension` in
# `mcp_server/tasks.py`, composed onto `handle_call_tool` in `server.py`. This handler
# never sees whether the caller declared the tasks extension or set `params.task`; it
# just spawns and returns the plain payload, matching the "spawn lives in one place"
# invariant Decision 2a's implementation note requires.
#
# Not in `policy.MUTATING_TOOLS` (Decision 4): a dry-run "start" has no coherent meaning,
# so this tool takes no `apply` parameter and is gated instead by
# `policy.TASK_STARTING_TOOLS` / `allows_tasks()` (Decision 8).
# ---------------------------------------------------------------------------------------


def _tool_loop_start(arguments: dict[str, Any], *, project_root: Path) -> Any:
    """Start a detached `ll-loop` run (`ll-loop run <loop>`) — SEP-2663 start-path entry.

    Crosses the `argparse` boundary per Decision 7 option (a): builds a `SimpleNamespace`
    carrying only the fields this tool exposes rather than routing through `cmd_run`'s
    full flag surface, and calls `run_background()` under `redirect_stdout`/
    `redirect_stderr` since it prints to stdout on success — corrupting the JSON-RPC frame
    on the stdio transport — and to stderr on failure.

    Mints its own `instance_id` (Decision 3) rather than delegating to
    `_make_instance_id()`, whose one-second timestamp resolution can collide under
    agent-paced calls. A non-zero `run_background()` return means nothing was spawned;
    this raises so `handle_call_tool`'s except-branch turns it into `is_error=True` with
    no `structured_content` — never a task id for a run that does not exist (AC 3b).
    """
    import argparse
    import contextlib
    import io
    from types import SimpleNamespace
    from typing import cast

    from little_loops.cli.loop._helpers import run_background
    from little_loops.mcp_server.tasks import _loops_dir, mint_start_instance_id

    loop_name = str(arguments.get("loop") or "").strip()
    if not loop_name:
        raise ValueError("loop_start requires a non-empty 'loop' name")

    context = arguments.get("context") or []
    if not isinstance(context, list):
        raise ValueError("loop_start 'context' must be a list of 'KEY=VALUE' strings")

    loops_dir = _loops_dir(project_root)
    instance_id = mint_start_instance_id(loop_name, loops_dir)
    # Decision 7 option (a): every `run_background()` access is a defensive
    # `getattr(args, ..., default)`, so a `SimpleNamespace` carrying only the fields this
    # tool exposes satisfies it at runtime despite the stricter `argparse.Namespace` annotation.
    args = cast(argparse.Namespace, SimpleNamespace(context=[str(item) for item in context]))

    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        rc = run_background(loop_name, args, loops_dir, instance_id=instance_id)

    if rc != 0:
        message = stderr_buf.getvalue().strip() or f"run_background exited with code {rc}"
        raise ValueError(message)

    # `instance_id` here is what TasksExtension reads out of structured_content to build
    # the task-shaped result's `taskId` (Decision 2a extraction note) — and what a
    # non-tasks caller reads directly off this plain payload (Decision 2a).
    return {"instance_id": instance_id, "loop": loop_name}


_TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "issues_query": _tool_issues_query,
    "issue_get": _tool_issue_get,
    "history_search": _tool_history_search,
    "deps_check": _tool_deps_check,
    "capabilities": _tool_capabilities,
    "queue_list": _tool_queue_list,
    "queue_get": _tool_queue_get,
    "loop_list": _tool_loop_list,
    # Tier 2 (FEAT-3149) — these take an extra required `apply` keyword, which is why the
    # value type is `Callable[..., Any]` rather than `Callable[[dict], Any]`. The split is
    # by `policy.MUTATING_TOOLS`, not by a second registry, so there is exactly one list
    # defining what counts as a write.
    "issue_capture": _tool_issue_capture,
    "issue_set_status": _tool_issue_set_status,
    "issue_link": _tool_issue_link,
    "issue_append_log": _tool_issue_append_log,
    "queue_add": _tool_queue_add,
    "queue_remove": _tool_queue_remove,
    "queue_requeue": _tool_queue_requeue,
    # Tier 3 (FEAT-3151) — takes no `apply` keyword; see the module comment above.
    "loop_start": _tool_loop_start,
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
        # ENH-3306: links to the `ui://issues/view` MCP Apps resource — a host that
        # negotiated `io.modelcontextprotocol/ui` renders this instead of raw JSON.
        # `meta=` is the correct runtime kwarg (verified: both `meta=` and `_meta=`
        # construct identically, see .ll/learning-tests/mcp-extension-mechanism.md) —
        # mypy's stub for this one field disagrees and expects the alias `_meta`.
        meta={"ui": {"resourceUri": "ui://issues/view"}},  # type: ignore[call-arg]
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
    types.Tool(
        name="queue_list",
        description="List all persisted `ll-queue` entries (pending/running/done/failed).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="queue_get",
        description="Fetch a single `ll-queue` entry's state and result by full id or 8+-char prefix.",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entry id (full uuid or 8+-char prefix)."},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="loop_list",
        description=(
            "List the project's loop catalog (built-ins plus `.loops/`, with the same "
            "override and visibility semantics `ll-loop list` applies) — project loops "
            "first, then built-ins not shadowed by a same-named project loop."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Restrict to one category."},
                "label": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict to loops carrying any of these labels (case-insensitive).",
                },
                "visibility": {
                    "type": "string",
                    "enum": ["public", "internal", "example", "all"],
                    "description": "Visibility tier to include. Default: public.",
                },
            },
            "additionalProperties": False,
        },
    ),
    # --- Tier 2: mutating tools (FEAT-3149) ---------------------------------------------
    # `annotations` is set ONLY on these four. The five tier-1 entries above deliberately
    # keep `annotations=None`: annotating them would change tier-1's `tools/list` output
    # shape, which this issue's anti-goals forbid. A host distinguishes the two groups by
    # `readOnlyHint == false` being present, which is exactly AC 1's requirement.
    types.Tool(
        name="issue_capture",
        description=(
            "Create a new little-loops issue file. Dry-run by default: without "
            "`apply: true` this returns the type/priority/slug/directory and rendered body "
            "it would write, and no issue ID (the ID is allocated at apply time)."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            # Creates a new file; never overwrites or deletes an existing one.
            destructive_hint=False,
            # Two identical calls create two issues.
            idempotent_hint=False,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["BUG", "FEAT", "ENH", "EPIC"],
                    "description": "Issue type.",
                },
                "title": {"type": "string", "description": "Issue title."},
                "priority": {
                    "type": "string",
                    "pattern": "^P[0-5]$",
                    "description": "Priority level. Default: P2.",
                },
                "body": {"type": "string", "description": "Summary section body."},
                "parent": {"type": "string", "description": "Parent EPIC ID to wire."},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to set in frontmatter.",
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually create the issue. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["type", "title"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="issue_set_status",
        description=(
            "Transition an issue's frontmatter status. Dry-run by default: without "
            "`apply: true` this returns the frontmatter fields it would change, old value "
            "to new value, and writes nothing."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            # Overwrites an existing frontmatter value.
            destructive_hint=True,
            idempotent_hint=True,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Issue ID in any of: '3149', 'FEAT-3149', 'P3-FEAT-3149'.",
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "blocked", "deferred", "done", "cancelled"],
                    "description": "Target status value.",
                },
                "reason": {
                    "type": "string",
                    "description": "Deferral or closure reason code, per the target status.",
                },
                "by": {
                    "type": "string",
                    "description": "Actor recorded as `deferred_by` on a deferral. Default: human.",
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually write the transition. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["issue_id", "status"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="issue_link",
        description=(
            "Write or remove a cross-issue dependency edge (blocked_by/depends_on/"
            "relates_to). Dry-run by default: without `apply: true` this reports the list "
            "the field would hold and writes nothing."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            # `unlink: true` removes an existing edge.
            destructive_hint=True,
            idempotent_hint=True,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string", "description": "Source issue ID."},
                "field": {
                    "type": "string",
                    "enum": ["blocked_by", "depends_on", "relates_to"],
                    "description": "Which edge type to write.",
                },
                "target": {"type": "string", "description": "Target issue ID."},
                "unlink": {
                    "type": "boolean",
                    "default": False,
                    "description": "Remove the edge instead of adding it.",
                },
                "reciprocal": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also write the matching reverse edge on the target.",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Skip target-existence validation.",
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually write the edge. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["issue_id", "field", "target"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="issue_append_log",
        description=(
            "Append a session-log entry to an issue's `## Session Log` section. Dry-run by "
            "default: without `apply: true` this returns the exact bullet it would insert "
            "and writes nothing."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            # Purely additive: appends a bullet, never rewrites existing ones.
            destructive_hint=False,
            # Two identical calls append two entries.
            idempotent_hint=False,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string", "description": "Issue ID to append to."},
                "command": {
                    "type": "string",
                    "description": "Command name to record, e.g. '/ll:manage-issue'.",
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually append the entry. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["issue_id", "command"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="queue_add",
        description=(
            "Classify and persist a new `ll-queue` entry (FSM loop, skill/command, or raw "
            "CLI invocation). Dry-run by default: without `apply: true` this returns the "
            "classified runner/target/args/timeout it would queue and writes nothing."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            # Adds a new row; never overwrites or deletes an existing one.
            destructive_hint=False,
            # Two identical calls queue two entries.
            idempotent_hint=False,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Loop name, skill/command name, or raw CLI invocation.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["P0", "P1", "P2", "P3", "P4", "P5"],
                    "description": "Priority tier. Default: P3.",
                },
                "runner": {
                    "type": "string",
                    "enum": ["skill", "cmd", "mcp", "prompt", "loop"],
                    "description": "Force a specific runner kind instead of classifying target.",
                },
                "args": {
                    "type": "object",
                    "description": "Extra ActionSpec args as key/value pairs.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default: 120 (unbounded for runner=loop).",
                },
                "input": {
                    "type": "string",
                    "description": "Input for a loop-runner target, same semantics as "
                    "`ll-loop run <loop> [input]`.",
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually queue the entry. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="queue_remove",
        description=(
            "Delete a pending `ll-queue` entry by id. Dry-run by default: without "
            "`apply: true` this reports the entry it would remove and writes nothing. "
            "Only removes entries in `pending` state."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entry id (full uuid or 8+-char prefix)."},
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually remove the entry. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="queue_requeue",
        description=(
            "Return a stranded `running` `ll-queue` entry to `pending`. Dry-run by "
            "default: without `apply: true` this reports the transition and writes "
            "nothing. Only requeues entries in `running` state."
        ),
        annotations=types.ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
        ),
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Entry id (full uuid or 8+-char prefix)."},
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "Set true to actually requeue the entry. Omitted or "
                    "anything other than true means dry-run: nothing is written.",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    ),
    # --- Tier 3: SEP-2663 start path (FEAT-3151) ------------------------------------------
    # Not in MUTATING_TOOLS, so no `apply` param and no ToolAnnotations `readOnlyHint`
    # false-vs-mutating distinction — this tool is gated by a separate registry entirely
    # (`policy.TASK_STARTING_TOOLS` / `allows_tasks()`, Decision 8/4).
    types.Tool(
        name="loop_start",
        description=(
            "Start a detached ll-loop run. Returns immediately with the run's instance "
            "id; poll progress with tasks/get and stop it with tasks/cancel. On a client "
            "that declared the tasks extension and set params.task on this call, the "
            "response is a SEP-2663 task-shaped result instead of an ordinary tool result "
            "— see docs/guides/MCP_SERVER_GUIDE.md."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "loop": {"type": "string", "description": "Loop name to run."},
                "context": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "KEY=VALUE context overrides, mirrors `ll-loop run --context`.",
                },
            },
            "required": ["loop"],
            "additionalProperties": False,
        },
    ),
]


async def handle_list_tools(
    _ctx: ServerRequestContext[Any],
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    """`tools/list` handler: returns the fixed sixteen-tool catalog in source order.

    The eight tier-1 read-only tools come first, then the seven tier-2 mutating tools,
    then FEAT-3151's tier-3 start tool; only the tier-2 seven carry `annotations`, which is
    how a host tells the mutating group apart from the rest.

    `ttlMs`/`cacheScope` are left unset here — the `Server(cache_hints=...)` passed in
    `little_loops.mcp_server.server.build_server` fills them, per SEP-2549.
    """
    return types.ListToolsResult(tools=_TOOLS)


def make_call_tool_handler(
    transport: str,
    project_root: Path,
) -> Callable[
    [ServerRequestContext[Any], types.CallToolRequestParams],
    Any,
]:
    """Build the `tools/call` handler, bound to the transport it is served over.

    FEAT-3168: `transport` is threaded in at `build_server()` construction time (the same
    factory-closure shape `resources.py`/`prompts.py` already use) so Guard 0 — the
    per-transport policy check — knows which transport it is deciding for. Neither
    `handle_call_tool` nor `ServerRequestContext` had access to that identity before.

    ENH-3171: `project_root` is threaded in the same way — resolved once by `main_mcp`
    (or defaulted from cwd by `build_server`) and closed over here, rather than each
    handler resolving `Path.cwd()` for itself or a resolved value being cached at module
    scope, where it would leak across `Server` instances built in the same process.
    """

    async def handle_call_tool(
        _ctx: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        """`tools/call` handler: dispatches to the named tool's handler function.

        Any exception raised by a tool handler (unknown issue ID, invalid FTS5 query, no
        host configured, ...) becomes a tool-level error result (`is_error=True`) rather
        than an uncaught exception reaching the SDK's dispatch loop — MCP's contract for a
        tool that failed on its own terms, as opposed to a transport/protocol fault.

        Guard 0 (FEAT-3168) runs first, ahead of Guard 1 below: it raises `MCPError` rather
        than returning a tool-result error, so a denied call over stdio or an ASGI-bypassed
        HTTP call surfaces the same `-32001` JSON-RPC protocol error the HTTP middleware
        returns — not a tool-level error result. It must stay outside the `try:` block
        below: that block's catch-all turns any exception into `is_error=True`, which would
        swallow the denial into a tool-result error instead of a protocol error.

        Guard 1 of FEAT-3149 lives here, as a wrapper rather than per-handler, so there is
        one place to audit and no way to forget it on a new tool. It **fails closed**:
        `apply` opts in only on the literal boolean `True`. A missing key, `null`, `"true"`,
        `1`, or any other truthy-looking value is a dry-run. That asymmetry is deliberate —
        the cost of misreading an opt-in is an unintended write to a user's issue tree, and
        the cost of misreading an opt-out is one wasted round trip.

        The `applied`/`tool` keys are stamped **after** the handler's payload, so the
        guard's account of whether a write happened always wins over the handler's.
        """
        from little_loops.config import BRConfig

        decision = check_tool_call(
            transport, "tools/call", params.name, config=BRConfig(project_root)
        )
        if not decision.allowed:
            raise MCPError(code=POLICY_DENIED_CODE, message=decision.reason)

        handler = _TOOL_HANDLERS.get(params.name)
        if handler is None:
            return types.CallToolResult(
                content=[types.TextContent(text=f"Unknown tool: {params.name}")],
                is_error=True,
            )

        arguments = dict(params.arguments or {})

        try:
            if params.name in MUTATING_TOOLS:
                apply = arguments.pop("apply", False) is True
                payload = {
                    **handler(arguments, project_root=project_root, apply=apply),
                    "applied": apply,
                    "tool": params.name,
                }
            else:
                payload = handler(arguments, project_root=project_root)
        except Exception as exc:
            return types.CallToolResult(
                content=[types.TextContent(text=str(exc))],
                is_error=True,
            )

        # `structuredContent` is an arbitrary JSON value only on 2026-07-28; every earlier
        # protocol version restricts it to a JSON *object*, and `mcp==2.0.0` negotiates down
        # to 2025-11-25 even when a client asks for 2026-07-28. Attaching a list payload
        # (the `issues_query`/`history_search` shape) therefore fails wire-level validation
        # with -32603 for every real client. Send it only when it is a dict; the full
        # payload — list or dict — always travels in `content[0].text` regardless.
        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(payload))],
            structured_content=payload if isinstance(payload, dict) else None,
        )

    return handle_call_tool

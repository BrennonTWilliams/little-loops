"""Session-discovery seam for host log ingestion (FEAT-3417).

Promoted from the spike at ``scripts/tests/spike/session_discovery_lifecycle/``.
Exposes the batch-read lifecycle only — ``list_workspaces``, ``detect_sessions``,
``iter_events`` — for every host that writes session transcripts to disk.
Live ``watch``/``stop`` are deferred to the first consumer that tails a host
session (a dashboard); ``SessionHandle`` carries ``path`` so a later ``watch``
needs no signature change above it.

**The seam is refused on content.** Per-host parsers (``parse_codex_rollout``,
``parse_claude_transcript``) share no content-level code above this module:
tool-call shapes and token accounting do not overlap enough between hosts to
justify a common abstraction, and forcing one would produce a
lowest-common-denominator record worse than two honest per-host ones. This is
a deliberate departure from the existing ``HostLayout.normalize``/
``normalize_file`` seam (``writers.py``, covering qwen/gemini/omp), which
translates host-native records into a shared Claude-shaped record; the two
seams coexist until ENH-3420 decides whether to unify them.

Every function takes ``home: Path | None = None`` (resolving to ``Path.home()``
at call time) so tests never touch a real ``~/.codex`` or ``~/.claude`` —
pass ``home=tmp_path``. This is distinct from ``get_project_folder``/
``get_sessions_folder``, which read ``Path.home()`` directly and therefore
cannot be reused here without dropping the override (see the Claude Code
branch of :func:`detect_sessions`).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.user_messages import encode_project_path


@dataclass(frozen=True)
class SessionHandle:
    """One session file: a Codex rollout, or a Claude Code ``<uuid>.jsonl``.

    ``cwd`` is always the caller's spelling of the workspace, even when the
    Codex row matched on ``cwd.resolve()`` — so handles from both hosts
    compare equal on ``cwd`` for the same call. ``updated_at`` is epoch
    seconds on both hosts (DB integer vs. ``st_mtime`` float); do not
    "correct" it to milliseconds.
    """

    host: str
    session_id: str
    path: Path
    cwd: Path
    updated_at: float
    is_agent: bool = False


@dataclass(frozen=True)
class SessionEvent:
    """One typed record from a session file, host-native payload untouched."""

    type: str
    timestamp: str
    host: str
    payload: dict[str, Any] = field(default_factory=dict)


_STATE_DB_RE = re.compile(r"^state_(\d+)\.sqlite$")


def _newest_state_dbs(home: Path) -> list[Path]:
    """All ``state_*.sqlite`` under ``home/.codex``, newest (highest N) first."""
    codex_home = home / ".codex"
    if not codex_home.is_dir():
        return []
    candidates = []
    for p in codex_home.glob("state_*.sqlite"):
        m = _STATE_DB_RE.match(p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [p for _, p in candidates]


def _query_threads_db(db_path: Path, cwd: Path) -> list[SessionHandle] | None:
    """Query one ``state_*.sqlite``'s ``threads`` table for *cwd*.

    ``None`` means unusable (missing/unreadable/schema mismatch) — caller
    should try the next DB or fall back to the date-dir scan. Empty list
    means usable but no rows. ``sqlite3.connect(..., mode=ro)`` succeeds on a
    non-database file and on a WAL database whose ``-shm`` sidecar isn't
    writable; the error only surfaces at the first statement, so both the
    ``PRAGMA`` and the ``SELECT`` are guarded, not just the connect.

    Matches *cwd* against both ``str(cwd)`` and ``str(cwd.resolve())`` (macOS
    ``/tmp`` -> ``/private/tmp``). ``agent_role`` drives ``is_agent`` when the
    column is present; ``thread_spawn_edges`` membership is not independently
    queried — every local capture has zero rows in it and its column schema
    is unverified (see fixtures/codex/README.md's Agent-thread finding).
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
        required = {"id", "rollout_path", "cwd", "updated_at"}
        if not required.issubset(cols):
            return None
        has_agent_role = "agent_role" in cols
        select_cols = "id, rollout_path, updated_at" + (", agent_role" if has_agent_role else "")
        rows = conn.execute(
            f"SELECT {select_cols} FROM threads WHERE cwd = ? OR cwd = ? ORDER BY updated_at DESC",
            (str(cwd), str(cwd.resolve())),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    handles = []
    for row in rows:
        session_id, rollout_path, updated_at = row[0], row[1], row[2]
        agent_role = row[3] if has_agent_role else None
        rp = Path(rollout_path)
        if not rp.exists():
            continue
        handles.append(
            SessionHandle(
                host="codex",
                session_id=str(session_id),
                path=rp,
                cwd=cwd,
                updated_at=float(updated_at),
                is_agent=agent_role is not None,
            )
        )
    return handles


def _scan_rollout_tree(root: Path, cwd: Path) -> list[SessionHandle]:
    """Scan one rollout tree (``sessions/`` or ``archived_sessions/``) for *cwd*.

    Globs ``**/*.jsonl`` (defensively recursive, so this tolerates both the
    date-keyed ``sessions/YYYY/MM/DD/`` shape and the flat
    ``archived_sessions/`` shape confirmed on codex-cli 0.152.1), reading only
    line 1 of each rollout to match ``payload.cwd`` against both ``str(cwd)``
    and ``str(cwd.resolve())``. ``is_agent`` is left ``False``: the capture
    that verified this fallback found ``session_meta.payload.originator``
    does not distinguish subagent threads (values seen: ``codex-tui``,
    ``codex_exec`` — neither agent-related), so there is no scan-fallback
    signal for it yet (see fixtures/codex/README.md's Agent-thread finding).
    """
    if not root.is_dir():
        return []
    cwd_spellings = {str(cwd), str(cwd.resolve())}
    handles = []
    for rollout in root.glob("**/*.jsonl"):
        try:
            with rollout.open(encoding="utf-8") as f:
                first_line = f.readline()
        except OSError:
            continue
        if not first_line.strip():
            continue
        try:
            header = json.loads(first_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(header, dict):
            continue
        payload = header.get("payload", {})
        if not isinstance(payload, dict) or payload.get("cwd") not in cwd_spellings:
            continue
        handles.append(
            SessionHandle(
                host="codex",
                session_id=payload.get("id", rollout.stem),
                path=rollout,
                cwd=cwd,
                updated_at=rollout.stat().st_mtime,
            )
        )
    return handles


def _scan_date_dirs(home: Path, cwd: Path) -> list[SessionHandle]:
    """Fallback: scan ``sessions/`` and ``archived_sessions/``, newest-first.

    These are two separate trees with different shapes (date-keyed vs. flat
    — see § Codex On-Disk Layout → Archived threads) and neither is assumed
    to have the other's structure; ordering is by ``updated_at`` alone, not
    by which tree a handle came from.
    """
    codex_home = home / ".codex"
    handles = _scan_rollout_tree(codex_home / "sessions", cwd)
    handles += _scan_rollout_tree(codex_home / "archived_sessions", cwd)
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles


def _detect_codex_sessions(
    cwd: Path, home: Path, limit: int | None, include_agents: bool
) -> list[SessionHandle]:
    handles: list[SessionHandle] | None = None
    for db_path in _newest_state_dbs(home):
        handles = _query_threads_db(db_path, cwd)
        if handles is not None:
            break
    if handles is None:
        handles = _scan_date_dirs(home, cwd)
    if not include_agents:
        handles = [h for h in handles if not h.is_agent]
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles[:limit] if limit else handles


def _detect_claude_sessions(
    cwd: Path, home: Path, limit: int | None, include_agents: bool
) -> list[SessionHandle]:
    """``home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))``.

    Computed locally rather than via ``get_project_folder``/
    ``get_sessions_folder``, both of which read ``Path.home()`` internally
    and would ignore the ``home`` override. Encodes the **resolved** cwd,
    exactly as ``get_project_folder`` does.
    """
    project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
    if not project_dir.is_dir():
        return []
    handles = []
    for jsonl in project_dir.glob("*.jsonl"):
        is_agent = jsonl.name.startswith("agent-")
        if is_agent and not include_agents:
            continue
        handles.append(
            SessionHandle(
                host="claude-code",
                session_id=jsonl.stem,
                path=jsonl,
                cwd=cwd,
                updated_at=jsonl.stat().st_mtime,
                is_agent=is_agent,
            )
        )
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles[:limit] if limit else handles


_REGISTERED_HOSTS = ("claude-code", "codex")


def detect_sessions(
    cwd: Path,
    host: str | None = None,
    *,
    include_agents: bool = False,
    limit: int | None = None,
    home: Path | None = None,
) -> list[SessionHandle]:
    """Every session for *cwd*, newest ``updated_at`` first.

    ``host=None`` unions every registered host's sessions for *cwd*, each
    handle carrying its own ``host`` — none of the eventual consumers has a
    ``--host`` flag, so a required ``host`` argument would leave Codex
    sessions invisible by default. ``limit`` applies once, after the
    cross-host merge (global newest-N, not N per host). Never raises for a
    missing host home; returns ``[]``.
    """
    resolved_home = home if home is not None else Path.home()
    if host is None:
        merged: list[SessionHandle] = []
        for one_host in _REGISTERED_HOSTS:
            merged += detect_sessions(
                cwd, one_host, include_agents=include_agents, home=resolved_home
            )
        merged.sort(key=lambda h: h.updated_at, reverse=True)
        return merged[:limit] if limit else merged
    if host == "codex":
        return _detect_codex_sessions(cwd, resolved_home, limit, include_agents)
    if host == "claude-code":
        return _detect_claude_sessions(cwd, resolved_home, limit, include_agents)
    return []


def list_workspaces(
    host: str, *, existing_only: bool = True, home: Path | None = None
) -> list[Path]:
    """Every cwd *host* has recorded sessions for; empty for a host with no home.

    Claude Code: walk ``projects_root``, reading each project's first
    non-agent JSONL record for its ``cwd`` (a local reimplementation, not
    ``cli/logs.py``'s ``_extract_cwd_from_project`` — importing that would
    invert the ``session_store`` -> ``cli`` dependency direction). Codex:
    ``SELECT DISTINCT cwd FROM threads``, or the scan fallback's distinct
    line-1 ``cwd``s when the DB is unusable.
    """
    resolved_home = home if home is not None else Path.home()
    if host == "claude-code":
        workspaces = _list_claude_workspaces(resolved_home)
    elif host == "codex":
        workspaces = _list_codex_workspaces(resolved_home)
    else:
        return []
    if existing_only:
        workspaces = [w for w in workspaces if w.exists()]
    return workspaces


def _list_claude_workspaces(home: Path) -> list[Path]:
    projects_root = home / ".claude" / "projects"
    if not projects_root.is_dir():
        return []
    workspaces = []
    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue
        cwd = _first_record_cwd(project_dir)
        if cwd is not None:
            workspaces.append(cwd)
    return workspaces


def _first_record_cwd(project_dir: Path) -> Path | None:
    """First ``cwd`` field found in *project_dir*'s non-agent JSONL files."""
    for jsonl_file in project_dir.glob("*.jsonl"):
        if jsonl_file.name.startswith("agent-"):
            continue
        try:
            with jsonl_file.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    cwd = record.get("cwd")
                    if isinstance(cwd, str) and cwd:
                        return Path(cwd)
        except OSError:
            continue
    return None


def _list_codex_workspaces(home: Path) -> list[Path]:
    for db_path in _newest_state_dbs(home):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            continue
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
            if "cwd" not in cols:
                continue
            rows = conn.execute("SELECT DISTINCT cwd FROM threads").fetchall()
        except sqlite3.Error:
            continue
        finally:
            conn.close()
        return [Path(row[0]) for row in rows if row[0]]

    codex_home = home / ".codex"
    cwds: set[str] = set()
    for root_name in ("sessions", "archived_sessions"):
        root = codex_home / root_name
        if not root.is_dir():
            continue
        for rollout in root.glob("**/*.jsonl"):
            try:
                with rollout.open(encoding="utf-8") as f:
                    first_line = f.readline()
            except OSError:
                continue
            try:
                header = json.loads(first_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(header, dict):
                continue
            payload = header.get("payload", {})
            cwd = payload.get("cwd") if isinstance(payload, dict) else None
            if isinstance(cwd, str) and cwd:
                cwds.add(cwd)
    return [Path(c) for c in cwds]


def parse_codex_rollout(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of a Codex rollout. Malformed/missing file -> no yield.

    A line that parses as JSON but is not an object (``[1, 2]``, ``"str"``)
    is skipped like a malformed line — this generator never raises.

    Every top-level ``type`` and every subtype nested under
    ``response_item.payload.type``/``event_msg.payload.type`` is passed
    through untouched in ``payload`` — including ones not documented at
    promotion time (``world_state`` at the top level; ``custom_tool_call``,
    ``custom_tool_call_output``, ``reasoning``, ``item_completed`` as
    subtypes; confirmed on codex-cli 0.152.1). This parser never enumerates
    the subtype vocabulary, so a vendor addition needs no code change here.

    ``base_instructions.text`` is inlined into line 1's ``session_meta``
    payload (~18KB uncompressed in the committed fixtures) — Python's
    ``open()`` text iteration has no line-length ceiling, so this is not a
    hazard for this parser itself, only for a downstream consumer with a
    fixed read buffer.
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            payload = record.get("payload")
            yield SessionEvent(
                type=record.get("type", ""),
                timestamp=record.get("timestamp", ""),
                host="codex",
                payload=payload if isinstance(payload, dict) else {},
            )


def parse_claude_transcript(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of a Claude Code session JSONL, lifted verbatim.

    Unlike the Codex parser, ``payload`` is the whole record — Claude Code's
    JSONL has no separate envelope/payload split.
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            yield SessionEvent(
                type=record.get("type", ""),
                timestamp=record.get("timestamp", ""),
                host="claude-code",
                payload=record,
            )


_PARSERS = {
    "codex": parse_codex_rollout,
    "claude-code": parse_claude_transcript,
}


def iter_events(handle: SessionHandle) -> Iterator[SessionEvent]:
    """Dispatch to the per-host parser by ``handle.host``; unknown host -> no yield."""
    parser = _PARSERS.get(handle.host)
    if parser is None:
        return
    yield from parser(handle.path)

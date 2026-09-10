"""Session-discovery seam for host log ingestion (FEAT-3417).

Promoted from the spike at ``scripts/tests/spike/session_discovery_lifecycle/``.
Exposes the batch-read lifecycle only — ``list_workspaces``, ``detect_sessions``,
``iter_events`` — for every host that writes session transcripts to disk.
Live ``watch``/``stop`` are deferred to the first consumer that tails a host
session (a dashboard); ``SessionHandle`` carries ``path`` so a later ``watch``
needs no signature change above it.

**Payload rule (ENH-3420, unify phase 1).** Payload is host-native where no
normalizer to Claude shape exists (``claude-code``, ``codex``, ``kimi-code``);
where a host already ships a normalizer to Claude shape for the
``HostLayout``/``writers.py`` seam (``qwen``, ``gemini``, ``omp``), payload is
that normalizer's own output, wrapped and host-stamped here rather than
reimplemented; ``opencode``/``pi`` are Claude-shaped on disk already and reuse
the Claude per-line loop with their own host stamped. The two discovery
mechanisms this module and ``HostLayout`` used to be — one per-host parser
here, one normalizer-to-Claude-shape seam there — are unified for discovery
and reading as of this phase; the ingest half (``raw_events``, via
``iter_events``) was unified in ENH-3422.

Every function takes ``home: Path | None = None`` (resolving to ``Path.home()``
at call time) so tests never touch a real ``~/.codex`` or ``~/.claude`` —
pass ``home=tmp_path``. The private per-host probes in ``user_messages.py``
(``_get_<host>_project_folder``, ``_omp_sessions_root``,
``encode_omp_session_dir``) accept the same ``home=`` kwarg, defaulting to
``Path.home()`` at call time, so this module calls them directly instead of
reimplementing their path joins — the one exception is Codex, which has no
project-folder probe at all (it keys sessions by date, not by project; see
:func:`_detect_codex_sessions`).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.user_messages import (
    _cwd_spellings,
    _get_claude_project_folder,
    _get_gemini_project_folder,
    _get_kimi_project_folder,
    _get_omp_project_folder,
    _get_opencode_project_folder,
    _get_pi_project_folder,
    _get_qwen_project_folder,
    encode_project_path,
)


@dataclass(frozen=True)
class SessionHandle:
    """One session file, for any registered host (Codex rollout, Claude Code
    ``<uuid>.jsonl``, or an opencode/pi/kimi-code/qwen/gemini/omp session file).

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
    """One typed record from a session file, host-native payload untouched.

    ``line_no`` (ENH-3422) is the real file line number for per-line hosts
    (blank/malformed lines consume a number, matching the ``raw_events``
    ``(source_path, line_no)`` dedup index) and the enumeration index over a
    file-level normalizer's yield for gemini/omp.
    """

    type: str
    timestamp: str
    host: str
    payload: dict[str, Any] = field(default_factory=dict)
    line_no: int | None = None


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
        # BUG-2489: guard against a TOCTOU race where the live host process
        # rotates or deletes the rollout between the glob above and this stat.
        try:
            updated_at = rollout.stat().st_mtime
        except OSError:
            continue
        handles.append(
            SessionHandle(
                host="codex",
                session_id=payload.get("id", rollout.stem),
                path=rollout,
                cwd=cwd,
                updated_at=updated_at,
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
    """Delegates to ``_get_claude_project_folder(encoded, home=home)``.

    That probe is now ``home``-aware (ENH-3420), so this no longer needs its
    own local reimplementation of the path join. Probes both the resolved
    and as-recorded spellings of cwd (resolved first, see
    ``_cwd_spellings``), exactly as ``get_project_folder`` does.
    """
    project_dir = None
    for path_str in _cwd_spellings(cwd):
        encoded = encode_project_path(path_str)
        project_dir = _get_claude_project_folder(encoded, home=home)
        if project_dir is not None:
            break
    if project_dir is None or not project_dir.is_dir():
        return []
    handles = []
    for jsonl in project_dir.glob("*.jsonl"):
        is_agent = jsonl.name.startswith("agent-")
        if is_agent and not include_agents:
            continue
        # BUG-2489: guard against a TOCTOU race where the live host process
        # rotates or deletes the file between the glob above and this stat.
        try:
            updated_at = jsonl.stat().st_mtime
        except OSError:
            continue
        handles.append(
            SessionHandle(
                host="claude-code",
                session_id=jsonl.stem,
                path=jsonl,
                cwd=cwd,
                updated_at=updated_at,
                is_agent=is_agent,
            )
        )
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles[:limit] if limit else handles


_REGISTERED_HOSTS = (
    "claude-code",
    "codex",
    "opencode",
    "pi",
    "kimi-code",
    "qwen",
    "gemini",
    "omp",
)

# Hosts handled by _detect_layout_sessions/_project_folder_for_layout_host
# (every registered host other than codex and claude-code, which have their
# own dedicated discovery functions above).
_LAYOUT_HOSTS = ("opencode", "pi", "kimi-code", "qwen", "gemini", "omp")


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
    handle carrying its own ``host`` — a required ``host`` argument would
    leave Codex sessions invisible by default when a caller's ``--host`` flag
    is unset (the three CLI consumers default their own ``--host`` to
    ``None``/union for the same reason, ENH-3427). ``limit`` applies once,
    after the cross-host merge (global newest-N, not N per host). Never
    raises for a missing host home; returns ``[]``.

    ``include_agents`` is honoured wherever the host's session glob reaches
    agent transcripts — today only ``claude-code`` (``agent-*.jsonl``); on
    every other registered host it is a documented no-op (ENH-3420 § Current
    Behavior) because no other host's glob matches an agent-prefixed name.
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
    if host in _LAYOUT_HOSTS:
        return _detect_layout_sessions(host, cwd, resolved_home, limit, include_agents)
    return []


def _project_folder_for_layout_host(host: str, cwd: Path, home: Path) -> Path | None:
    """Resolve the on-disk project folder for one ``_LAYOUT_HOSTS`` member.

    Delegates to the same ``home``-aware private probes ``get_project_folder``
    uses, so behaviour matches that public seam exactly minus the ``home``
    override.
    """
    if host in ("opencode", "pi", "qwen"):
        probe = {
            "opencode": _get_opencode_project_folder,
            "pi": _get_pi_project_folder,
            "qwen": _get_qwen_project_folder,
        }[host]
        for path_str in _cwd_spellings(cwd):
            result = probe(encode_project_path(path_str), home=home)
            if result is not None:
                return result
        return None
    if host == "kimi-code":
        return _get_kimi_project_folder(cwd, home=home)
    if host == "gemini":
        return _get_gemini_project_folder(cwd, home=home)
    if host == "omp":
        return _get_omp_project_folder(cwd, home=home)
    return None


def _header_session_id(host: str, path: Path) -> str | None:
    """Read a gemini/omp session id from the file, or ``None`` on any failure.

    gemini: line 1's ``sessionId``. omp: scans for the first ``type:
    "session"`` record's ``id``, **stopping at the first ``type: "message"``
    line** — the header always precedes every message when present, and
    discovery over many sessions must not read a whole file just to find no
    header. Both apply the ``isinstance(record, dict)`` guard and never raise;
    a malformed line is skipped, not fatal.
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return None
    with handle:
        if host == "gemini":
            first_line = handle.readline().strip()
            if not first_line:
                return None
            try:
                record = json.loads(first_line)
            except json.JSONDecodeError:
                return None
            if not isinstance(record, dict):
                return None
            session_id = record.get("sessionId")
            return session_id if isinstance(session_id, str) and session_id else None
        if host == "omp":
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
                record_type = record.get("type")
                if record_type == "session":
                    session_id = record.get("id")
                    return session_id if isinstance(session_id, str) and session_id else None
                if record_type == "message":
                    return None
            return None
    return None


def _codex_header_session_id(path: Path) -> str | None:
    """Read a codex session id from line 1's ``payload.id``, or ``None``.

    Mirrors :func:`_scan_rollout_tree`'s inline ``payload.get("id", ...)``
    rule so :func:`session_id_for` agrees with codex discovery.
    """
    try:
        with path.open(encoding="utf-8") as f:
            first_line = f.readline()
    except OSError:
        return None
    if not first_line.strip():
        return None
    try:
        header = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(header, dict):
        return None
    payload = header.get("payload", {})
    if not isinstance(payload, dict):
        return None
    session_id = payload.get("id")
    return session_id if isinstance(session_id, str) and session_id else None


def session_id_for(host: str, path: Path) -> str:
    """Derive *path*'s session id per *host*'s own rule (ENH-3422, D3).

    kimi-code: the ``session_*`` directory two levels up (never the stem,
    which is always ``"wire"``). gemini/omp: the file header's session id,
    falling back to the stem (:func:`_header_session_id`). codex: line 1's
    ``payload.id``, falling back to the stem (:func:`_codex_header_session_id`,
    matching :func:`_scan_rollout_tree`). Every other host: the file stem.
    Shared by :func:`_detect_layout_sessions` and :func:`handles_from_paths`
    so discovery and path-synthesis cannot drift.
    """
    if host == "kimi-code":
        return path.parents[2].name
    if host in ("gemini", "omp"):
        return _header_session_id(host, path) or path.stem
    if host == "codex":
        return _codex_header_session_id(path) or path.stem
    return path.stem


def handles_from_paths(
    paths: list[Path], host: str, *, cwd: Path | None = None
) -> list[SessionHandle]:
    """Synthesize ``SessionHandle``\\ s for *paths* already known to be *host*'s.

    Widens the legacy ``list[Path]`` shape the public backfill wrappers still
    accept into the ``SessionHandle`` shape :func:`iter_events` needs
    (ENH-3422, D4). ``session_id`` comes from :func:`session_id_for` — the
    same rule discovery applies — so a handle synthesized here and one
    :func:`detect_sessions` produces for the same file agree (D3).
    ``updated_at`` is the file's mtime; a file that vanishes between glob and
    stat (BUG-2489 TOCTOU) is skipped, not raised. ``cwd`` defaults to
    ``Path.cwd()``.
    """
    resolved_cwd = cwd if cwd is not None else Path.cwd()
    handles = []
    for path in paths:
        try:
            updated_at = path.stat().st_mtime
        except OSError:
            continue
        handles.append(
            SessionHandle(
                host=host,
                session_id=session_id_for(host, path),
                path=path,
                cwd=resolved_cwd,
                updated_at=updated_at,
                is_agent=path.name.startswith("agent-"),
            )
        )
    return handles


def _detect_layout_sessions(
    host: str, cwd: Path, home: Path, limit: int | None, include_agents: bool
) -> list[SessionHandle]:
    """Shared discovery for every ``_LAYOUT_HOSTS`` member.

    Resolves the project folder via :func:`_project_folder_for_layout_host`,
    then globs ``HostLayout.session_glob`` relative to it (already encoding
    any subdir, e.g. qwen's ``"chats/*.jsonl"``, or kimi-code's
    ``"session_*/agents/main/wire.jsonl"`` since ENH-3422 gave it a real
    entry). ``session_id`` is derived by :func:`session_id_for`, shared with
    :func:`handles_from_paths` so discovery and path-synthesis cannot drift
    (D3).
    """
    project = _project_folder_for_layout_host(host, cwd, home)
    if project is None or not project.is_dir():
        return []
    from little_loops.session_store.writers import host_layout_for

    session_glob = host_layout_for(host).session_glob
    handles = []
    for path in project.glob(session_glob):
        if not path.is_file():
            continue
        is_agent = path.name.startswith("agent-")
        if is_agent and not include_agents:
            continue
        session_id = session_id_for(host, path)
        # BUG-2489: guard against a TOCTOU race where the live host process
        # rotates or deletes the file between the glob above and this stat.
        try:
            updated_at = path.stat().st_mtime
        except OSError:
            continue
        handles.append(
            SessionHandle(
                host=host,
                session_id=session_id,
                path=path,
                cwd=cwd,
                updated_at=updated_at,
                is_agent=is_agent,
            )
        )
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles[:limit] if limit else handles


def list_workspaces(
    host: str, *, existing_only: bool = True, home: Path | None = None
) -> list[Path]:
    """Every cwd *host* has recorded sessions for; empty for a host with no home.

    Claude Code/opencode/pi/qwen: walk the host's ``<home>/.<cli>/projects``
    root — computed from ``home`` directly, **never**
    ``host_layout_for(...).projects_root`` (that reads the real
    ``Path.home()`` internally and would leak past a ``home=`` override) —
    reading each project's first non-agent session-JSONL record for its
    ``cwd`` (a local reimplementation, not ``cli/logs.py``'s own code —
    importing from there would invert the ``session_store`` -> ``cli``
    dependency direction; ``cli/logs.py``'s prior local implementation,
    ``_extract_cwd_from_project``, was deleted in ENH-3430 once this
    function became the seam every discovery caller routes through).
    Codex: ``SELECT DISTINCT cwd FROM threads``, or the scan fallback's
    distinct line-1 ``cwd``s when the DB is unusable. Gemini: the
    ``projects`` keys of ``<home>/.gemini/projects.json``. Kimi-code:
    distinct ``workDir`` values from ``session_index.jsonl``. Omp: always
    ``[]`` — its session-dir encoding is lossy (``/``, ``\\``, ``:`` all
    collapse to ``-``), so recovering ``cwd`` would require reading every
    session file's header; ``cli/logs.py``'s ``discover_all_projects``
    (ENH-3430) surfaces this the same way — a silent ``[]`` for omp under
    ``--all``, not an error.
    """
    resolved_home = home if home is not None else Path.home()
    if host == "claude-code":
        workspaces = _list_claude_workspaces(resolved_home)
    elif host == "codex":
        workspaces = _list_codex_workspaces(resolved_home)
    elif host == "opencode":
        workspaces = _list_claude_workspaces(
            resolved_home, projects_root=resolved_home / ".opencode" / "projects"
        )
    elif host == "pi":
        workspaces = _list_claude_workspaces(
            resolved_home, projects_root=resolved_home / ".pi" / "projects"
        )
    elif host == "qwen":
        workspaces = _list_claude_workspaces(
            resolved_home,
            projects_root=resolved_home / ".qwen" / "projects",
            session_glob="chats/*.jsonl",
        )
    elif host == "gemini":
        workspaces = _list_gemini_workspaces(resolved_home)
    elif host == "kimi-code":
        workspaces = _list_kimi_workspaces(resolved_home)
    else:
        return []
    if existing_only:
        workspaces = [w for w in workspaces if w.exists()]
    return workspaces


def _list_claude_workspaces(
    home: Path, *, projects_root: Path | None = None, session_glob: str = "*.jsonl"
) -> list[Path]:
    root = projects_root if projects_root is not None else home / ".claude" / "projects"
    if not root.is_dir():
        return []
    workspaces = []
    for project_dir in root.iterdir():
        if not project_dir.is_dir():
            continue
        cwd = _first_record_cwd(project_dir, session_glob)
        if cwd is not None:
            workspaces.append(cwd)
    return workspaces


def _list_gemini_workspaces(home: Path) -> list[Path]:
    """The ``projects`` keys of ``<home>/.gemini/projects.json`` — absolute cwds."""
    registry = home / ".gemini" / "projects.json"
    if not registry.is_file():
        return []
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        return []
    return [Path(cwd) for cwd in projects if isinstance(cwd, str) and cwd]


def _list_kimi_workspaces(home: Path) -> list[Path]:
    """Distinct ``workDir`` values from ``$KIMI_CODE_HOME``-or-``<home>/.kimi-code``'s
    ``session_index.jsonl``."""
    kimi_home = Path(os.environ.get("KIMI_CODE_HOME") or (home / ".kimi-code"))
    index = kimi_home / "session_index.jsonl"
    if not index.is_file():
        return []
    work_dirs: set[str] = set()
    try:
        for line in index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            work_dir = entry.get("workDir")
            if isinstance(work_dir, str) and work_dir:
                work_dirs.add(work_dir)
    except OSError:
        return []
    return [Path(w) for w in work_dirs]


def _first_record_cwd(project_dir: Path, session_glob: str = "*.jsonl") -> Path | None:
    """First ``cwd`` field found in *project_dir*'s non-agent session-JSONL files."""
    for jsonl_file in project_dir.glob(session_glob):
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
    promotion time (``world_state`` at the top level; ``reasoning``,
    ``item_completed`` as subtypes; confirmed on codex-cli 0.152.1) —
    **except** ``response_item``/``custom_tool_call`` (``name == "exec"``)
    and its paired ``custom_tool_call_output``, which
    :class:`~little_loops.session_store.codex.CodexNormalizer` replaces with
    Claude-shaped ``assistant``/``user`` records so the ll-signal readers in
    ``cli/logs.py`` can see Codex shell activity (ENH-3433). This parser
    still never enumerates the rest of the subtype vocabulary, so a vendor
    addition to any other type needs no code change here.

    Stateful across the file: line 1's ``session_meta`` payload seeds the
    normalizer's ``session_id``/``cwd`` (read once, before any tool call),
    and the normalizer itself carries ``call_id`` pairing state between the
    ``custom_tool_call``/``item_completed``/``custom_tool_call_output``
    triple for each exec. **Rows ingested into ``raw_events`` before this
    normalizer existed still yield a ``sessions`` row on ``rebuild()`` (via
    the ``raw_events.session_id`` fallback) but no ``tool_events`` rows** —
    re-deriving those requires deleting and re-ingesting the source rows.

    ``base_instructions.text`` is inlined into line 1's ``session_meta``
    payload (~18KB uncompressed in the committed fixtures) — Python's
    ``open()`` text iteration has no line-length ceiling, so this is not a
    hazard for this parser itself, only for a downstream consumer with a
    fixed read buffer.
    """
    from little_loops.session_store.codex import CodexNormalizer

    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        normalizer: CodexNormalizer | None = None
        for line_no, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if normalizer is None:
                payload = record.get("payload")
                header = payload if isinstance(payload, dict) else {}
                normalizer = CodexNormalizer(
                    session_id=str(header.get("id", "")),
                    cwd=str(header.get("cwd", "")),
                )
            normalized = normalizer(record)
            if normalized is not None:
                yield SessionEvent(
                    type=normalized.get("type", ""),
                    timestamp=normalized.get("timestamp", ""),
                    host="codex",
                    payload=normalized,
                    line_no=line_no,
                )
                continue
            payload = record.get("payload")
            yield SessionEvent(
                type=record.get("type", ""),
                timestamp=record.get("timestamp", ""),
                host="codex",
                payload=payload if isinstance(payload, dict) else {},
                line_no=line_no,
            )


def _parse_claude_shaped(path: Path, host: str) -> Iterator[SessionEvent]:
    """Per-line parse of a Claude-shaped-on-disk session JSONL, host stamped.

    Shared body for every host whose on-disk records are already Claude
    shape at the envelope level (``claude-code``, ``opencode``, ``pi``) —
    unlike the Codex parser, ``payload`` is the whole record, since these
    hosts' JSONL has no separate envelope/payload split.
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        for line_no, raw_line in enumerate(handle, start=1):
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
                host=host,
                payload=record,
                line_no=line_no,
            )


def parse_claude_transcript(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of a Claude Code session JSONL, lifted verbatim."""
    yield from _parse_claude_shaped(path, "claude-code")


def parse_opencode_transcript(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of an OpenCode session JSONL (Claude-shaped on disk)."""
    yield from _parse_claude_shaped(path, "opencode")


def parse_pi_transcript(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of a Pi session JSONL (Claude-shaped on disk)."""
    yield from _parse_claude_shaped(path, "pi")


def parse_kimi_wire(path: Path) -> Iterator[SessionEvent]:
    """Per-line raw passthrough of kimi's ``wire.jsonl`` typed events.

    Same never-raise guards as :func:`parse_codex_rollout`; ``payload`` is
    the whole record — kimi has no normalizer to Claude shape yet (a follow-up,
    not this issue).
    """
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        for line_no, raw_line in enumerate(handle, start=1):
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
                host="kimi-code",
                payload=record,
                line_no=line_no,
            )


def parse_qwen_session(path: Path) -> Iterator[SessionEvent]:
    """Per-line qwen parse via :func:`normalize_qwen_record`, host stamped.

    No ``qwen_skip_at_ingest``: that is an ingest volume guard and redundant
    on the read path (``ui_telemetry`` records are ``type: "system"``, which
    ``normalize_qwen_record`` already drops).
    """
    from little_loops.session_store.qwen import normalize_qwen_record

    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return
    with handle:
        for line_no, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            normalized = normalize_qwen_record(record)
            if normalized is None:
                continue
            yield SessionEvent(
                type=normalized.get("type", ""),
                timestamp=normalized.get("timestamp", ""),
                host="qwen",
                payload=normalized,
                line_no=line_no,
            )


def parse_gemini_session(path: Path) -> Iterator[SessionEvent]:
    """Wrap :func:`normalize_gemini_session`, host stamped."""
    from little_loops.session_store.gemini import normalize_gemini_session

    for line_no, record in enumerate(normalize_gemini_session(path), start=1):
        yield SessionEvent(
            type=record.get("type", ""),
            timestamp=record.get("timestamp", ""),
            host="gemini",
            payload=record,
            line_no=line_no,
        )


def parse_omp_session(path: Path) -> Iterator[SessionEvent]:
    """Wrap :func:`normalize_omp_session`, host stamped."""
    from little_loops.session_store.omp import normalize_omp_session

    for line_no, record in enumerate(normalize_omp_session(path), start=1):
        yield SessionEvent(
            type=record.get("type", ""),
            timestamp=record.get("timestamp", ""),
            host="omp",
            payload=record,
            line_no=line_no,
        )


_PARSERS = {
    "codex": parse_codex_rollout,
    "claude-code": parse_claude_transcript,
    "opencode": parse_opencode_transcript,
    "pi": parse_pi_transcript,
    "kimi-code": parse_kimi_wire,
    "qwen": parse_qwen_session,
    "gemini": parse_gemini_session,
    "omp": parse_omp_session,
}


def iter_events(handle: SessionHandle) -> Iterator[SessionEvent]:
    """Dispatch to the per-host parser by ``handle.host``; unknown host -> no yield."""
    parser = _PARSERS.get(handle.host)
    if parser is None:
        return
    yield from parser(handle.path)

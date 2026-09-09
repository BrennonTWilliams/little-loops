"""Session-discovery lifecycle spike (FEAT-3417).

Proves the detect_sessions/iter_events algorithm described in FEAT-3417's
Program Design and Codex On-Disk Layout sections: a sqlite `threads`-table
query for Codex session discovery, with a date-directory scan fallback, and
per-host dispatch to a parser that yields typed SessionEvents.

No shared content-level parsing above the per-host parsers (the issue's
"seam is refused on content" rule) — parse_codex_rollout and
parse_claude_transcript each own their own record shape.

`home` is threaded explicitly everywhere instead of os.path.expanduser, so
tests never touch a real ~/.codex or ~/.claude.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionHandle:
    host: str
    session_id: str
    path: Path
    cwd: Path
    updated_at: float


@dataclass(frozen=True)
class SessionEvent:
    type: str
    timestamp: str
    host: str
    payload: dict


_STATE_DB_RE = re.compile(r"^state_(\d+)\.sqlite$")


def _newest_state_dbs(home: Path) -> list[Path]:
    """All state_*.sqlite under home/.codex, newest (highest N) first."""
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
    """Query one state_*.sqlite's threads table for cwd. None means unusable
    (missing/unreadable/schema mismatch) -> caller should try the next DB or
    fall back to the date-dir scan. Empty list means usable but no rows."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
        required = {"id", "rollout_path", "cwd", "updated_at"}
        if not required.issubset(cols):
            return None
        rows = conn.execute(
            "SELECT id, rollout_path, updated_at FROM threads "
            "WHERE cwd = ? ORDER BY updated_at DESC",
            (str(cwd),),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    handles = []
    for session_id, rollout_path, updated_at in rows:
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
            )
        )
    return handles


def _scan_date_dirs(home: Path, cwd: Path) -> list[SessionHandle]:
    """Fallback: scan home/.codex/sessions/YYYY/MM/DD/ newest-first, reading
    only line 1 of each rollout to match payload.cwd."""
    sessions_root = home / ".codex" / "sessions"
    if not sessions_root.is_dir():
        return []

    handles = []
    day_dirs = sorted(
        (p for p in sessions_root.glob("*/*/*") if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    # Sort by the full YYYY/MM/DD tuple, not just the day component.
    day_dirs = sorted(day_dirs, key=lambda p: (p.parent.parent.name, p.parent.name, p.name), reverse=True)

    for day_dir in day_dirs:
        rollouts = sorted(day_dir.glob("rollout-*.jsonl"), reverse=True)
        for rollout in rollouts:
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
            payload = header.get("payload", {})
            if payload.get("cwd") != str(cwd):
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


def _detect_codex_sessions(cwd: Path, home: Path, limit: int | None) -> list[SessionHandle]:
    for db_path in _newest_state_dbs(home):
        handles = _query_threads_db(db_path, cwd)
        if handles is not None:
            handles.sort(key=lambda h: h.updated_at, reverse=True)
            return handles[:limit] if limit else handles
    handles = _scan_date_dirs(home, cwd)
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles[:limit] if limit else handles


def _encode_project_path(path_str: str) -> str:
    """Minimal reimplementation of the production dash-encoding scheme,
    kept local so this spike has zero production imports (isolation guard)."""
    return re.sub(r"[^a-zA-Z0-9]", "-", path_str)


def _detect_claude_sessions(cwd: Path, home: Path, limit: int | None) -> list[SessionHandle]:
    """Minimal reimplementation: one project dir keyed by encoded cwd."""
    encoded = _encode_project_path(str(cwd))
    project_dir = home / ".claude" / "projects" / encoded
    if not project_dir.is_dir():
        return []
    handles = []
    for jsonl in project_dir.glob("*.jsonl"):
        if jsonl.name.startswith("agent-"):
            continue
        handles.append(
            SessionHandle(
                host="claude-code",
                session_id=jsonl.stem,
                path=jsonl,
                cwd=cwd,
                updated_at=jsonl.stat().st_mtime,
            )
        )
    handles.sort(key=lambda h: h.updated_at, reverse=True)
    return handles[:limit] if limit else handles


def detect_sessions(
    cwd: Path, host: str, *, home: Path, limit: int | None = None
) -> list[SessionHandle]:
    """Every session for cwd under host, newest updated_at first.

    `home` stands in for the real HOME so tests never touch a real
    ~/.codex or ~/.claude. Never raises for a missing host home; returns [].
    """
    if host == "codex":
        return _detect_codex_sessions(cwd, home, limit)
    if host == "claude-code":
        return _detect_claude_sessions(cwd, home, limit)
    return []


def parse_codex_rollout(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of a Codex rollout. Malformed/missing file -> no yield."""
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
            yield SessionEvent(
                type=record.get("type", ""),
                timestamp=record.get("timestamp", ""),
                host="codex",
                payload=record.get("payload", {}),
            )


def parse_claude_transcript(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse of a Claude Code session JSONL."""
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
    """Dispatch to the per-host parser by handle.host."""
    parser = _PARSERS.get(handle.host)
    if parser is None:
        return
    yield from parser(handle.path)

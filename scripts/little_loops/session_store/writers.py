"""Event writers for the session store (ENH-2890 split from session_store.py).

The bulk of the original module: every ``record_*``/``*_event_context``
writer, the paired ``_backfill_*`` helpers that seed those same tables from
on-disk sources, ``SQLiteTransport`` (the EventBus sink), the raw_events
zlib pack/unpack helpers, and the correction-detection helpers
(``is_correction``/``normalize_issue_id``/``mine_corrections_from_messages``).
Depends on :mod:`little_loops.session_store.schema` (``connect``, ``ensure_db``,
``_configure_connection``, ``_LOOP_EVENT_TYPES``) and
:mod:`little_loops.session_store.db` (``DEFAULT_DB_PATH``, ``resolve_history_db``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import subprocess
import threading
import time
import zlib
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import little_loops.session_store as _pkg
from little_loops.session_store.db import DEFAULT_DB_PATH, resolve_history_db
from little_loops.session_store.schema import _LOOP_EVENT_TYPES, _configure_connection

logger = logging.getLogger(__name__)

# NOTE: internal calls in this module go through ``_pkg.connect``/``_pkg.ensure_db``
# (the package's re-exported names) rather than importing ``connect``/``ensure_db``
# directly from ``schema``. Before the ENH-2890 package split, every writer lived
# in one flat module and shared one set of globals, so tests that
# ``monkeypatch.setattr(session_store, "connect", boom)`` transparently redirected
# every internal caller. Binding ``connect`` directly here would break that
# transparency (the monkeypatch would only replace the package's copy of the
# name, not this module's), so calls are routed through the package object,
# resolved lazily at call time — long after this module (and the package
# __init__ that imports it) has finished loading.

# raw_events payload compression (ENH: shrink the source-of-truth table).
# ``raw_line``/``parsed_json`` are stored zlib-compressed as BLOBs. SQLite's
# dynamic typing lets a BLOB live in the existing (nominally TEXT) columns with
# no destructive DDL, and legacy uncompressed TEXT rows coexist with new BLOB
# rows: readers dispatch on the Python type (bytes → decompress, str → legacy
# passthrough), so a partially-recompressed table always reads correctly. Level
# 6 is stdlib zlib's default (good ratio/speed; ~2.9x on these JSONL payloads).
_PAYLOAD_ZLIB_LEVEL = 6


def _pack_payload(text: str) -> bytes:
    """Compress a payload string for storage in ``raw_events``."""
    return zlib.compress(text.encode("utf-8"), _PAYLOAD_ZLIB_LEVEL)


def _unpack_payload(value: str | bytes) -> str:
    """Return payload text: ``bytes`` → zlib-decompress, ``str`` → legacy passthrough.

    New rows store compressed BLOBs (read back as ``bytes``); rows written before
    the compression change are plain TEXT (read back as ``str``) and pass through
    unchanged. This keeps a partially-recompressed table fully readable.
    """
    if isinstance(value, bytes):
        return zlib.decompress(value).decode("utf-8")
    return value


_CORRECTION_RE = re.compile(
    r"^\s*(no[,!]|don'?t\s|stop\s|revert|that'?s\s+wrong|not\s+like\s+that)",
    re.IGNORECASE,
)

_PHRASE_RE = re.compile(
    r"\b(?:"
    r"instead"
    r"|actually\s+(?:that|this|it)\s"
    r"|you missed"
    r"|should be\s+(?!fine\b|ok\b|okay\b|good\b|great\b|alright\b|correct\b|right\b)"
    r"|wrong approach"
    r"|remember that"
    r"|always use"
    r"|never use"
    r"|from now on"
    r"|I meant\b.*\bnot\b"
    r"|not\b.*\buse\b"
    r")",
    re.IGNORECASE,
)

_REMEMBER_RE = re.compile(r"^!remember\b", re.IGNORECASE)


def is_correction(text: str, extra_patterns: Sequence[str] = ()) -> bool:
    """Return True if *text* matches a known user-correction signal.

    ``extra_patterns`` are raw regex strings appended to the built-in set
    (``analytics.capture.correction_patterns``). Built-ins always remain active.
    Invalid patterns are skipped with a warning.
    """
    t = text[:512]
    _extra_re: re.Pattern[str] | None = None
    if extra_patterns:
        parts: list[str] = []
        for p in extra_patterns:
            try:
                re.compile(p, re.IGNORECASE)
                parts.append(f"(?:{p})")
            except re.error:
                logger.warning("is_correction: skipping invalid extra_pattern %r", p)
        if parts:
            _extra_re = re.compile("|".join(parts), re.IGNORECASE)
    return bool(
        _REMEMBER_RE.match(t)
        or _CORRECTION_RE.match(t)
        or _PHRASE_RE.search(t)
        or (_extra_re and _extra_re.search(t))
    )


def _now() -> str:
    """Return the current UTC time as a Z-suffixed ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_ISSUE_NUM_RE = re.compile(r"(?:BUG|ENH|FEAT|EPIC)-(\d+)", re.IGNORECASE)


def normalize_issue_id(issue_id: str | int | None) -> int | None:
    """Extract the stable numeric issue id from a ``TYPE-NNN`` string or bare number.

    ENH-2771: history tables key on the immutable numeric ``issue_num`` rather
    than the mutable ``TYPE-NNN`` display string, so every read boundary that
    accepts a caller-supplied ``issue_id`` normalizes it through this helper
    first. Accepts:

    - a canonical ``TYPE-NNN`` string (``"ENH-2705"`` -> ``2705``), matching
      any of the known prefixes (case-insensitive), mirroring
      ``issue_parser.py``'s ``get_next_issue_number()`` prefix-union regex;
    - a bare/string number (``"2705"`` or ``2705`` -> ``2705``);
    - a trailing-digit fallback for any other ``"-"``-delimited string (e.g.
      an unrecognized/legacy prefix), consistent with the migration's
      backfill extraction (``substr(issue_id, instr(issue_id, '-') + 1)``).

    Returns ``None`` if no digits can be extracted (including ``None`` input).
    """
    if issue_id is None:
        return None
    if isinstance(issue_id, int):
        return issue_id
    issue_id = issue_id.strip()
    if not issue_id:
        return None
    match = _ISSUE_NUM_RE.search(issue_id)
    if match:
        return int(match.group(1))
    if issue_id.isdigit():
        return int(issue_id)
    # Fallback: trailing digits after the last '-', mirroring the migration's
    # SQL extraction for any prefix not in the known BUG/ENH/FEAT/EPIC set.
    if "-" in issue_id:
        tail = issue_id.rsplit("-", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def _index(
    conn: sqlite3.Connection,
    *,
    content: str,
    kind: str,
    ref: str,
    anchor: str,
    ts: str,
) -> None:
    """Insert one row into the FTS5 ``search_index`` table."""
    conn.execute(
        "INSERT INTO search_index(content, kind, ref, anchor, ts) VALUES(?, ?, ?, ?, ?)",
        (content, kind, ref, anchor, ts),
    )


def write_file_event(
    db_path: Path | str,
    session_id: str | None,
    path: str,
    op: str,
    issue_id: str | None = None,
    config: dict | None = None,
) -> None:
    """Write one row to ``file_events`` and index it in ``search_index``.

    Gated by ``analytics.capture.file_events`` (ENH-1841): when ``config`` is
    provided and the flag is ``false``, the write is suppressed. Missing ``capture``
    key defaults to permissive (no behavior change).
    """
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not capture.file_events:
            return
    conn = _pkg.connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO file_events(ts, session_id, path, op, issue_id, git_sha) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (ts, session_id, path, op, issue_id, None),
        )
        _index(conn, content=path, kind="file", ref=path, anchor=op, ts=ts)
        conn.commit()
    finally:
        conn.close()


def record_correction(
    db_path: Path | str,
    session_id: str | None,
    content: str,
    source: str,
    config: dict | None = None,
) -> None:
    """Write one row to ``user_corrections`` and index it in ``search_index``.

    Gated by ``analytics.capture.corrections`` (ENH-1841): when ``config`` is
    provided and the flag is ``false``, the write is suppressed. Missing ``capture``
    key defaults to permissive (no behavior change).
    """
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not capture.corrections:
            return
    content = content[:512]
    conn = _pkg.connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
            (ts, session_id, content, source),
        )
        _index(conn, content=content, kind="correction", ref=session_id or "", anchor=source, ts=ts)
        conn.commit()
    finally:
        conn.close()


def record_skill_event(
    db_path: Path | str,
    session_id: str | None,
    skill_name: str,
    args: str,
    config: dict | None = None,
) -> None:
    """Write one row to ``skill_events`` and index it in ``search_index``.

    Gated by ``analytics.capture.skills`` (ENH-2932): when ``config`` is provided,
    ``skill_name`` must match one of the configured glob patterns or the write is
    suppressed. Missing ``capture`` key or missing ``config`` defaults to permissive
    (no behavior change).
    """
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled_for

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not feature_enabled_for({"skills": capture.skills}, "skills", skill_name):
            return
    args = args[:200]
    conn = _pkg.connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
            (ts, session_id, skill_name, args),
        )
        _index(
            conn, content=skill_name, kind="skill", ref=session_id or "", anchor=skill_name, ts=ts
        )
        conn.commit()
    finally:
        conn.close()


def _warn_on_dedup_collision(
    conn: sqlite3.Connection,
    table: str,
    issue_num: int | None,
    issue_id: str,
    transition: str,
    inserted: bool,
) -> None:
    """Log when an ``INSERT OR IGNORE`` was suppressed by a *different* issue's row.

    ``idx_issue_events_dedup`` / ``idx_issue_snapshots_dedup`` are unique on
    ``(issue_num, transition)`` — type-blind by design (ENH-2771), so that a
    retyped issue (ENH-1234 -> FEAT-1234) doesn't split its history across two
    rows. That type-blindness has a side effect: when two *different* issues
    reuse the same bare number under different type prefixes, the second
    issue's transition silently no-ops against the first issue's row (BUG-3006).

    Called after every ``INSERT OR IGNORE`` on *table* with *inserted* derived
    from ``cursor.rowcount == 1``. When the insert was suppressed
    (``inserted`` is ``False``) and *issue_num* is not ``None``, reads back the
    stored ``issue_id`` for ``(issue_num, transition)``; if it differs from
    *issue_id*, warns naming both ids. An identical stored id means the
    suppression was a genuine idempotent no-op (retype or repeated call) and
    stays silent.

    *table* is an internal literal (``"issue_events"`` / ``"issue_snapshots"``),
    never caller-supplied — interpolated into the ``SELECT``, never
    parameterized.
    """
    if inserted or issue_num is None:
        return
    row = conn.execute(
        f"SELECT issue_id FROM {table} WHERE issue_num = ? AND transition = ?",  # noqa: S608
        (issue_num, transition),
    ).fetchone()
    stored_id = row[0] if row is not None else None
    if stored_id is not None and stored_id != issue_id:
        logger.warning(
            "%s dedup collision: %s %s discarded — (issue_num=%d, transition=%r) "
            "already held by %s. If these are distinct issues, the newer "
            "transition is lost; if this is a retype, it is expected.",
            table,
            issue_id,
            transition,
            issue_num,
            transition,
            stored_id,
        )


def record_issue_snapshot(
    db_path: Path | str,
    issue_id: str,
    transition: str,
    file_path: str,
) -> None:
    """Write one row to ``issue_snapshots`` and index it in ``search_index``.

    Reads the issue file at *file_path*, extracts frontmatter metadata and
    markdown body, then inserts into ``issue_snapshots`` using ``INSERT OR IGNORE``
    so repeated calls for the same ``(issue_num, transition)`` are idempotent
    (type-blind — see ``_warn_on_dedup_collision``). A suppressed insert whose
    stored row belongs to a *different* issue id emits a collision warning
    (BUG-3006) instead of discarding silently.
    Also calls ``_index()`` with ``kind="snapshot"`` so FTS5 searches surface it.

    Silently returns if *file_path* does not exist or cannot be read.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter

    issue_id = canonicalize_issue_id(issue_id, file_path) or issue_id

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return

    fm = parse_frontmatter(content)
    body = strip_frontmatter(content)
    title = fm.get("title") or fm.get("id") or issue_id
    priority = fm.get("priority")
    issue_type = fm.get("type")

    # Serialise frontmatter as JSON for storage.
    fm_json = json.dumps({k: str(v) for k, v in fm.items() if v is not None}, sort_keys=True)

    issue_num = normalize_issue_id(issue_id)
    conn = _pkg.connect(db_path)
    ts = _now()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO issue_snapshots"
            "(ts, issue_id, issue_num, transition, title, priority, issue_type, body, frontmatter)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, issue_id, issue_num, transition, str(title), priority, issue_type, body, fm_json),
        )
        _warn_on_dedup_collision(
            conn, "issue_snapshots", issue_num, issue_id, transition, cursor.rowcount == 1
        )
        _index(
            conn,
            content=f"{issue_id} {title} {body or ''}".strip(),
            kind="snapshot",
            ref=issue_id,
            anchor=file_path,
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


def record_issue_event(
    db_path: Path | str,
    issue_id: str,
    transition: str,
    *,
    session_id: str | None = None,
    issue_type: str | None = None,
    priority: str | None = None,
    discovered_by: str | None = None,
    captured_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    """Write one row to ``issue_events`` and index it in ``search_index`` (BUG-2770).

    Direct-call sibling of :func:`record_issue_snapshot`, modeled on the
    inline ``INSERT OR IGNORE INTO issue_events(...)`` in
    ``SQLiteTransport.send()``'s ``issue.*`` branch. Callers that own an
    issue transition outside the EventBus (e.g. ``ll-issues set-status``)
    call this directly rather than emitting a bus event, per the
    ENH-2466 decision that scoped the EventBus to FSM-loop/issue-lifecycle
    events only.

    Idempotent via the ``idx_issue_events_dedup`` unique index on
    ``(issue_num, transition)`` — type-blind by design, so repeated calls for
    the same pair are no-ops after the first. A suppressed insert whose
    stored row belongs to a *different* issue id emits a collision warning
    (BUG-3006) instead of discarding silently — see
    ``_warn_on_dedup_collision``.
    """
    issue_num = normalize_issue_id(issue_id)
    conn = _pkg.connect(db_path)
    ts = _now()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO issue_events("
            "ts, issue_id, issue_num, transition, discovered_by, "
            "issue_type, priority, captured_at, completed_at, session_id"
            ") VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                ts,
                issue_id,
                issue_num,
                transition,
                discovered_by,
                issue_type,
                priority,
                captured_at,
                completed_at,
                session_id,
            ),
        )
        _warn_on_dedup_collision(
            conn, "issue_events", issue_num, issue_id, transition, cursor.rowcount == 1
        )
        _index(
            conn,
            content=f"{issue_id} {issue_type or ''}".strip(),
            kind="issue",
            ref=issue_id,
            anchor="",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def cli_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    binary: str = "",
    args: list[str] | None = None,
    config: dict | None = None,
) -> Generator[None, None, None]:
    """Insert a ``cli_events`` row on enter; update exit_code and duration_ms on exit.

    Best-effort per the EPIC-1707 graceful-degradation contract (matching
    :func:`skill_event_context`): a missing, locked, or otherwise unavailable
    database must never block the wrapped command. If the enter ``INSERT`` fails
    (e.g. ``OperationalError: database is locked`` under multi-writer contention),
    the analytics row is skipped and the command body still runs; a failure of the
    exit ``UPDATE`` never masks a successful command either. Only errors raised by
    the wrapped body propagate.

    Gated by ``analytics.capture.cli_commands`` (ENH-2932): when ``config`` is
    provided, ``binary`` must match one of the configured glob patterns or the
    row write is suppressed (the wrapped body still runs). Missing ``capture``
    key or missing ``config`` defaults to permissive (no behavior change).
    """
    if args is None:
        args = []
    effective_path = resolve_history_db(db_path)
    conn: sqlite3.Connection | None = None
    row_id: int | None = None
    start = time.time()
    ts = _now()
    gate_open = True
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled_for

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        gate_open = feature_enabled_for(
            {"cli_commands": capture.cli_commands}, "cli_commands", binary
        )
    if gate_open:
        try:
            conn = _pkg.connect(effective_path)
            cursor = conn.execute(
                "INSERT INTO cli_events(ts, binary, args) VALUES(?, ?, ?)",
                (ts, binary, json.dumps(args[:50])),
            )
            row_id = cursor.lastrowid
            conn.commit()
        except sqlite3.Error:
            logger.warning("cli_event_context: insert failed for %r", binary, exc_info=True)
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            conn = None
            row_id = None
    exit_code = 0
    try:
        yield
    except BaseException:
        exit_code = 1
        raise
    finally:
        if conn is not None and row_id is not None:
            duration_ms = int((time.time() - start) * 1000)
            try:
                conn.execute(
                    "UPDATE cli_events SET exit_code=?, duration_ms=? WHERE id=?",
                    (exit_code, duration_ms, row_id),
                )
                conn.commit()
            except sqlite3.Error:
                logger.warning(
                    "cli_event_context: exit update failed for %r", binary, exc_info=True
                )
            finally:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass


@dataclass
class SkillEventCompletion:
    """Mutable completion handle yielded by :func:`skill_event_context` (ENH-2460).

    Hosts that observe a concrete process exit code (e.g. ``ll-action``) set
    ``exit_code`` before the ``with`` block exits; ``success`` is derived from
    it unless set explicitly. Left untouched, a clean exit records
    ``exit_code=0, success=1`` and a raise records ``exit_code=1, success=0``.
    """

    exit_code: int | None = None
    success: bool | None = None


@contextmanager
def skill_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    skill_name: str = "",
    args: str = "",
    config: dict | None = None,
) -> Generator[SkillEventCompletion, None, None]:
    """Insert a ``skill_events`` row on enter; update completion columns on exit.

    Skill-host analogue of :func:`cli_event_context` (ENH-2460): records
    ``exit_code``, ``success`` and ``duration_ms`` when the wrapped skill body
    finishes. Unlike ``cli_event_context`` this is best-effort per the
    EPIC-1707 graceful-degradation contract — a missing or locked database
    never blocks the skill run (the body still executes; the row is skipped).

    Gated by ``analytics.capture.skills`` (ENH-2932): when ``config`` is provided,
    ``skill_name`` must match one of the configured glob patterns or the row write
    is suppressed (the wrapped body still runs, yielding a default
    ``SkillEventCompletion()``). Missing ``capture`` key or missing ``config``
    defaults to permissive (no behavior change).
    """
    args = args[:200]
    conn: sqlite3.Connection | None = None
    row_id: int | None = None
    effective_path = resolve_history_db(db_path)
    ts = _now()
    gate_open = True
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig, feature_enabled_for

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        gate_open = feature_enabled_for({"skills": capture.skills}, "skills", skill_name)
    if gate_open:
        try:
            conn = _pkg.connect(effective_path)
            cursor = conn.execute(
                "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
                (ts, session_id, skill_name, args),
            )
            row_id = cursor.lastrowid
            _index(
                conn,
                content=skill_name,
                kind="skill",
                ref=session_id or "",
                anchor=skill_name,
                ts=ts,
            )
            conn.commit()
        except sqlite3.Error:
            logger.warning("skill_event_context: insert failed for %r", skill_name, exc_info=True)
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            conn = None
            row_id = None
    start = time.time()
    completion = SkillEventCompletion()
    try:
        yield completion
        if completion.exit_code is None:
            completion.exit_code = 0
        if completion.success is None:
            completion.success = completion.exit_code == 0
    except BaseException:
        if completion.exit_code is None or completion.exit_code == 0:
            completion.exit_code = 1
        completion.success = False
        raise
    finally:
        if conn is not None and row_id is not None:
            duration_ms = int((time.time() - start) * 1000)
            exit_code = completion.exit_code if completion.exit_code is not None else 1
            success = completion.success if completion.success is not None else False
            try:
                conn.execute(
                    "UPDATE skill_events SET exit_code=?, success=?, duration_ms=? WHERE id=?",
                    (exit_code, 1 if success else 0, duration_ms, row_id),
                )
                conn.commit()
            except sqlite3.Error:
                logger.warning(
                    "skill_event_context: update failed for %r", skill_name, exc_info=True
                )
            finally:
                conn.close()


# ---------------------------------------------------------------------------

_STDERR_PREVIEW_MAX = 512


def record_hook_event(
    db_path: Path | str,
    *,
    ts: str | None = None,
    session_id: str | None,
    event_name: str,
    matcher: str | None,
    script: str | None,
    exit_code: int | None,
    duration_ms: int | None,
    stderr_preview: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None:
    """Write one row to ``hook_events`` and index it in ``search_index``.

    Live-write-only (ENH-2506): the Claude Code host does not emit hook
    execution results into the transcript JSONL, so there is no backfill
    source and no ``_backfill_hook_events``. Best-effort per the EPIC-1707
    graceful-degradation contract — a missing or locked database is logged
    and swallowed, never raised, mirroring :func:`skill_event_context`.
    """
    if stderr_preview is not None:
        stderr_preview = stderr_preview[:_STDERR_PREVIEW_MAX]
    ts = ts or _now()
    effective_path = resolve_history_db(db_path)
    try:
        conn = _pkg.connect(effective_path)
    except sqlite3.Error:
        logger.warning("record_hook_event: connect failed for %r", event_name, exc_info=True)
        return
    try:
        conn.execute(
            "INSERT INTO hook_events(ts, session_id, event_name, matcher, script, exit_code, "
            "duration_ms, stderr_preview, head_sha, branch) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                event_name,
                matcher,
                script,
                exit_code,
                duration_ms,
                stderr_preview,
                head_sha,
                branch,
            ),
        )
        _index(
            conn,
            content=f"{event_name} {matcher or ''}".strip(),
            kind="hook_event",
            ref=session_id or "",
            anchor=event_name,
            ts=ts,
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning("record_hook_event: insert failed for %r", event_name, exc_info=True)
    finally:
        conn.close()


@dataclass
class HookEventCompletion:
    """Mutable completion handle yielded by :func:`hook_event_context` (ENH-2506).

    Callers that observe a concrete exit code (e.g. a bash shim capturing
    ``$?``) set ``exit_code`` before the ``with`` block exits. Left untouched,
    a clean exit records ``exit_code=0`` and a raised exception records
    ``exit_code=1`` — mirroring :class:`SkillEventCompletion`.
    """

    exit_code: int | None = None
    stderr_preview: str | None = None


@contextmanager
def hook_event_context(
    db_path: Path | str = DEFAULT_DB_PATH,
    session_id: str | None = None,
    event_name: str = "",
    matcher: str | None = None,
    script: str | None = None,
    config: dict | None = None,
) -> Generator[HookEventCompletion, None, None]:
    """Measure and record one hook fire: ``exit_code``, ``duration_ms``, ``stderr_preview``.

    Best-effort per the EPIC-1707 graceful-degradation contract (matching
    :func:`skill_event_context`): a missing or locked database never blocks
    the wrapped hook body, and this wrap must never alter the wrapped body's
    exit code or swallow behavior — it only observes and records. Uses
    ``time.monotonic()`` for duration (unlike ``cli_event_context``'s
    ``time.time()``), since this measures elapsed wall-clock duration of a
    single fire, not a timestamp.

    The ``config`` parameter is a forward-compatibility gate for
    ``analytics.capture.hooks``; the caller is expected to check the flag
    before entering (mirroring the ``skill_event_context`` stub pattern) —
    this function does not read config itself.
    """
    completion = HookEventCompletion()
    start = time.monotonic()
    ts = _now()
    try:
        yield completion
        if completion.exit_code is None:
            completion.exit_code = 0
    except BaseException:
        if completion.exit_code is None or completion.exit_code == 0:
            completion.exit_code = 1
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        record_hook_event(
            db_path,
            ts=ts,
            session_id=session_id,
            event_name=event_name,
            matcher=matcher,
            script=script,
            exit_code=completion.exit_code,
            duration_ms=duration_ms,
            stderr_preview=completion.stderr_preview,
        )


_COMMIT_MSG_ISSUE_RE = re.compile(
    r"\b(?:closes|fixes|resolves|issue:?)\s*:?\s*#?((?:BUG|ENH|FEAT|EPIC)-\d+|\d+)",
    re.IGNORECASE,
)

_COMMIT_ID_RE = re.compile(r"\b((?:BUG|ENH|FEAT|EPIC)-\d+)\b")

_BRANCH_ISSUE_RE = re.compile(r"((?:BUG|ENH|FEAT|EPIC)-\d+)", re.IGNORECASE)


def _infer_issue_id(message: str, branch: str | None = None) -> str | None:
    """Infer an issue ID from a commit *message* and optional *branch* name.

    Checks (in order): explicit ``Closes/Fixes/Resolves/Issue:`` references,
    any bare ``TYPE-NNN`` token in the message, then branch-name conventions
    (``feat/ENH-2458-...``). Returns ``None`` when nothing matches.
    """
    m = _COMMIT_MSG_ISSUE_RE.search(message)
    if m:
        ref = m.group(1).upper()
        if "-" in ref:
            return ref
        # Bare "#123" — cannot resolve the type prefix; fall through to
        # a typed token elsewhere in the message before giving up.
    m = _COMMIT_ID_RE.search(message)
    if m:
        return m.group(1).upper()
    if branch:
        m = _BRANCH_ISSUE_RE.search(branch)
        if m:
            return m.group(1).upper()
    return None


def record_commit_event(
    db_path: Path | str,
    commit_sha: str,
    message: str,
    *,
    author: str | None = None,
    branch: str | None = None,
    issue_id: str | None = None,
    files: Sequence[str] | None = None,
    parent_sha: str | None = None,
    ts: str | None = None,
    config: dict | None = None,
) -> bool:
    """Write one row to ``commit_events`` and index it in ``search_index``.

    ``issue_id`` is inferred from the message/branch when not given. Idempotent
    via ``INSERT OR IGNORE`` on the ``commit_sha`` UNIQUE constraint; the FTS
    row is only written when the insert actually lands, so repeated calls do
    not duplicate search results. Returns True when a new row was inserted.

    The ``config`` parameter is a forward-compatibility stub for an
    ``analytics.capture.commits`` gate; it is accepted but not yet used.
    """
    if not commit_sha:
        return False
    if issue_id is None:
        issue_id = _infer_issue_id(message, branch)
    files_json = json.dumps(list(files)) if files is not None else None
    conn = _pkg.connect(db_path)
    ts = ts or _now()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO commit_events("
            "ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json),
        )
        inserted = bool(cursor.rowcount)
        if inserted:
            _index(
                conn,
                content=f"{commit_sha[:12]} {issue_id or ''} {message}".strip()[:512],
                kind="commit",
                ref=commit_sha,
                anchor=issue_id or "",
                ts=ts,
            )
        conn.commit()
    finally:
        conn.close()
    return inserted


def _backfill_commit_events(conn: sqlite3.Connection, repo_root: Path) -> int:
    """Seed ``commit_events`` from ``git log --all`` under *repo_root*.

    Follows the ``_backfill_messages()`` pattern: idempotent via
    ``INSERT OR IGNORE`` on the ``commit_sha`` UNIQUE constraint (the FTS row
    is only written for genuinely new commits). Branch attribution is not
    reconstructed retroactively (``git log --all`` has no unambiguous branch
    per commit), so backfilled rows carry ``branch=NULL``.
    """
    # \x1e separates records, \x1f separates fields: sha, parents, author,
    # author-date (ISO), full message body. --name-only appends touched paths.
    fmt = "%x1e%H%x1f%P%x1f%an%x1f%aI%x1f%B%x1f"
    try:
        proc = subprocess.run(
            ["git", "log", "--all", "--name-only", f"--pretty=format:{fmt}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    count = 0
    for record in proc.stdout.split("\x1e"):
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) < 6:
            continue
        sha, parents, author, author_date, message, tail = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
            parts[3].strip(),
            parts[4],
            parts[5],
        )
        if not sha:
            continue
        files = [line.strip() for line in tail.splitlines() if line.strip()]
        message = message.strip()
        issue_id = _infer_issue_id(message)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO commit_events("
            "ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                author_date,
                sha,
                parents.split(" ")[0] if parents else None,
                message,
                author or None,
                None,
                issue_id,
                json.dumps(files),
            ),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=f"{sha[:12]} {issue_id or ''} {message}".strip()[:512],
                kind="commit",
                ref=sha,
                anchor=issue_id or "",
                ts=author_date,
            )
            count += 1
    return count


def record_test_run_event(
    db_path: Path | str,
    *,
    ts: str,
    ended_at: str | None = None,
    total: int = 0,
    passed: int = 0,
    failed: int = 0,
    errored: int = 0,
    skipped: int = 0,
    duration_s: float | None = None,
    failing_names: Sequence[str] | None = None,
    env_label: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    command: str | None = None,
    config: dict | None = None,
) -> None:
    """Write one row to ``test_run_events`` and index it in ``search_index``.

    ``failing_names`` (pytest node IDs) are stored as a JSON array and also
    fed into the FTS index so ``ll-session search --fts "<test name>"
    --kind test_run`` surfaces the runs where that test failed.

    The ``config`` parameter is a forward-compatibility stub for an
    ``analytics.capture.test_runs`` gate; it is accepted but not yet used.
    """
    names = list(failing_names) if failing_names else []
    conn = _pkg.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO test_run_events("
            "ts, ended_at, total, passed, failed, errored, skipped, duration_s, "
            "failing_names_json, env_label, head_sha, branch, command"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                ended_at,
                total,
                passed,
                failed,
                errored,
                skipped,
                duration_s,
                json.dumps(names),
                env_label,
                head_sha,
                branch,
                command,
            ),
        )
        summary = f"{command or 'pytest'} passed={passed} failed={failed} " + " ".join(names)
        _index(
            conn,
            content=summary.strip()[:512],
            kind="test_run",
            ref=head_sha or "",
            anchor=branch or "",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


def record_harness_event(
    db_path: Path | str,
    *,
    ts: str,
    runner: str | None = None,
    target: str | None = None,
    exit_code: int | None = None,
    semantic_verdict: str | None = None,
    semantic_passed: bool | None = None,
    timed_out: bool | None = None,
    duration_ms: int | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    parent_id: int | None = None,
    semantic_prompt: str | None = None,
    semantic_confidence: float | None = None,
    semantic_reason: str | None = None,
    semantic_evidence: str | None = None,
    semantic_model: str | None = None,
) -> None:
    """Write one row to ``harness_events`` and index it in ``search_index``.

    Mirrors :func:`record_test_run_event`'s shape: raises on failure — callers
    (the ``ll-harness`` producer, ENH-2740) are responsible for wrapping calls
    in ``contextlib.suppress(Exception)`` if a failed write should not abort
    the run.
    """
    conn = _pkg.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO harness_events("
            "ts, runner, target, exit_code, semantic_verdict, semantic_passed, "
            "timed_out, duration_ms, head_sha, branch, parent_id, "
            "semantic_prompt, semantic_confidence, semantic_reason, "
            "semantic_evidence, semantic_model"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                runner,
                target,
                exit_code,
                semantic_verdict,
                None if semantic_passed is None else int(semantic_passed),
                None if timed_out is None else int(timed_out),
                duration_ms,
                head_sha,
                branch,
                parent_id,
                semantic_prompt,
                semantic_confidence,
                semantic_reason,
                semantic_evidence,
                semantic_model,
            ),
        )
        summary = f"{runner or 'harness'} {target or ''} exit={exit_code}".strip()
        _index(
            conn,
            content=summary[:512],
            kind="harness",
            ref=head_sha or "",
            anchor=branch or "",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


def record_prompt_opt_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    offered: bool,
    mode: str | None = None,
    bypass_reason: str | None = None,
    raw_len: int | None = None,
    ts: str | None = None,
) -> None:
    """Write one row to ``prompt_opt_events`` and index it in ``search_index``.

    Best-effort, fire-and-forget contract like :func:`record_correction` /
    :func:`record_skill_event` — the caller (``user_prompt_submit.py::handle()``)
    wraps this in ``contextlib.suppress(Exception)`` so a DB failure never
    changes the hook's stdout/exit (EPIC-2457 graceful-degradation contract).
    See the v32 migration comment for why this table is excluded from
    ``_REBUILD_TABLES`` and how :func:`_backfill_prompt_opt` enriches it
    separately.
    """
    ts = ts or _now()
    conn = _pkg.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO prompt_opt_events("
            "ts, session_id, mode, offered, bypass_reason, raw_len"
            ") VALUES(?, ?, ?, ?, ?, ?)",
            (ts, session_id, mode, int(offered), bypass_reason, raw_len),
        )
        summary = f"mode={mode or ''} offered={int(offered)} reason={bypass_reason or ''}"
        _index(
            conn,
            content=summary.strip()[:512],
            kind="prompt_opt",
            ref=session_id or "",
            anchor=mode or "",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


def record_verdict_event(
    db_path: Path | str,
    *,
    ts: str,
    session_id: str | None,
    verdict_kind: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    verdict: str,
    severity_counts: dict | None = None,
    findings_count: int | None = None,
    confidence: int | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None:
    """Write one row to ``verdict_events`` and index it in ``search_index``.

    Mirrors :func:`record_harness_event`'s shape: raises on failure — the
    ``cmd_invoke()`` call site (ENH-2504) wraps this in
    ``contextlib.suppress(Exception)`` so a DB failure never changes a
    verifier's exit code.
    """
    severity_json = json.dumps(severity_counts) if severity_counts is not None else None
    conn = _pkg.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO verdict_events("
            "ts, session_id, verdict_kind, target_kind, target_id, verdict, "
            "severity_counts, findings_count, confidence, head_sha, branch"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                verdict_kind,
                target_kind,
                target_id,
                verdict,
                severity_json,
                findings_count,
                confidence,
                head_sha,
                branch,
            ),
        )
        summary = f"{target_id or ''} {verdict} {verdict_kind} {severity_json or ''}".strip()
        _index(
            conn,
            content=summary[:512],
            kind="verdict",
            ref=head_sha or "",
            anchor=branch or "",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


def record_review_event(
    db_path: Path | str,
    *,
    ts: str,
    session_id: str | None,
    reviewer_skill: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    severity_counts: dict | None = None,
    findings_count: int | None = None,
    findings_json_summary: dict | list | None = None,
    verdict: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
) -> None:
    """Write one row to ``review_events`` and index it in ``search_index`` (ENH-2512).

    Mirrors :func:`record_verdict_event`'s shape: raises on failure — the
    ``cmd_invoke()`` call site wraps this in ``contextlib.suppress(Exception)``
    so a DB failure never changes an audit/review's exit code.
    """
    severity_json = json.dumps(severity_counts) if severity_counts is not None else None
    findings_json = json.dumps(findings_json_summary) if findings_json_summary is not None else None
    conn = _pkg.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO review_events("
            "ts, session_id, reviewer_skill, target_kind, target_id, "
            "severity_counts, findings_count, findings_json_summary, verdict, "
            "head_sha, branch"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                reviewer_skill,
                target_kind,
                target_id,
                severity_json,
                findings_count,
                findings_json,
                verdict,
                head_sha,
                branch,
            ),
        )
        summary = (
            f"{target_id or ''} {verdict or ''} {reviewer_skill} {severity_json or ''}".strip()
        )
        _index(
            conn,
            content=summary[:512],
            kind="review",
            ref=head_sha or "",
            anchor=branch or "",
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()


# ENH-2866: the status an orchestrator writes at dequeue, before the issue has
# an outcome. Rows in this state are deliberately left with a NULL ``ended_at``.
_ORCHESTRATION_IN_FLIGHT_STATUS = "running"


def record_orchestration_run(
    db_path: Path | str,
    *,
    run_id: str,
    driver: str,
    issue_id: str,
    status: str,
    failure_reason: str | None = None,
    duration_s: float | None = None,
    wave: str | None = None,
    pr_url: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    base_sha: str | None = None,
    base_dirty: bool | None = None,
    config: dict | None = None,
) -> bool:
    """UPSERT one per-issue orchestration outcome and refresh its FTS row.

    ``run_id`` identifies the top-level ``ll-auto``, ``ll-parallel``, or
    ``ll-sprint`` invocation. Reusing the same ``(run_id, issue_id)`` for a retry
    replaces the initial result with the final outcome. The matching FTS row is
    deleted and recreated in the same transaction so stale failure text cannot
    remain searchable after a successful retry.

    ENH-2866: orchestrators call this twice per issue. The first call is issued
    at dequeue with ``status="running"`` and the ``base_sha``/``base_dirty``
    stamp, so the base state is readable *while the issue is in flight*; the
    second is the existing end-of-issue call carrying the outcome. Three columns
    are therefore write-once rather than last-write-wins: ``base_sha``,
    ``base_dirty``, and ``started_at`` are ``COALESCE``d so a terminal upsert
    that passes none of them (as all three real call sites do) cannot null the
    dequeue-time values. An in-flight row also leaves ``ended_at`` NULL — the
    ``_now()`` default applies only to a terminal status — so an abandoned run
    does not read as ``ended_at == started_at``.

    The ``config`` parameter is a forward-compatibility stub for a future
    ``analytics.capture.orchestration_runs`` gate; it is accepted but unused.
    Returns ``False`` only when the required identity fields are empty.
    """
    if not run_id or not driver or not issue_id or not status:
        return False

    # A failed `git rev-parse` yields "" (worker_pool._get_main_head_sha); store
    # NULL so the reader's None-means-unstamped contract holds.
    effective_base_sha = base_sha or None
    effective_base_dirty = None if base_dirty is None else int(base_dirty)
    in_flight = status == _ORCHESTRATION_IN_FLIGHT_STATUS
    effective_ended_at = ended_at if in_flight else (ended_at or _now())
    # An in-flight row is the only write that knows when work actually began,
    # so it defaults its own started_at rather than making each capture site
    # format a timestamp. Paired with the COALESCE below, that value survives
    # the terminal upsert and keeps the row inside history_reader's
    # COALESCE(ended_at, started_at) windows even if the run is abandoned.
    effective_started_at = started_at or (_now() if in_flight else None)
    index_ts = effective_ended_at or effective_started_at or _now()
    index_ref = f"{run_id}:{issue_id}"
    conn = _pkg.connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO orchestration_runs("
            "run_id, driver, issue_id, status, failure_reason, duration_s, wave, pr_url, "
            "started_at, ended_at, head_sha, branch, base_sha, base_dirty"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, issue_id) DO UPDATE SET "
            "driver=excluded.driver, status=excluded.status, "
            "failure_reason=excluded.failure_reason, duration_s=excluded.duration_s, "
            "wave=excluded.wave, pr_url=excluded.pr_url, "
            # write-once (ENH-2866): the terminal upsert passes none of these
            "started_at=COALESCE(excluded.started_at, started_at), "
            "base_sha=COALESCE(excluded.base_sha, base_sha), "
            "base_dirty=COALESCE(excluded.base_dirty, base_dirty), "
            "ended_at=excluded.ended_at, "
            "head_sha=excluded.head_sha, branch=excluded.branch",
            (
                run_id,
                driver,
                issue_id,
                status,
                failure_reason,
                duration_s,
                wave,
                pr_url,
                effective_started_at,
                effective_ended_at,
                head_sha,
                branch,
                effective_base_sha,
                effective_base_dirty,
            ),
        )
        conn.execute(
            "DELETE FROM search_index WHERE kind = ? AND ref = ?",
            ("orchestration_run", index_ref),
        )
        _index(
            conn,
            content=(f"{driver} {run_id} {issue_id} {status} {failure_reason or ''}").strip()[:512],
            kind="orchestration_run",
            ref=index_ref,
            anchor=issue_id,
            ts=index_ts,
        )
        conn.commit()
        return bool(cursor.rowcount)
    finally:
        conn.close()


def record_loop_run_summary(
    db_path: Path | str,
    *,
    run_id: str,
    loop_name: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    final_state: str | None = None,
    iterations: int | None = None,
    terminated_by: str | None = None,
    error: str | None = None,
    evaluator_score: float | None = None,
    diagnostics_path: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    failure_terminal: bool | None = None,
    config: dict | None = None,
) -> bool:
    """Write one row to ``loop_runs`` and index it in ``search_index`` (ENH-2463).

    ``run_id`` is the archive-time run identifier (see
    :meth:`little_loops.fsm.persistence.RunPersistence.archive_run` for the
    derivation) so this row JOINs cleanly to on-disk
    ``.loops/.history/<run_id>-<loop_name>/`` archives. Idempotent via
    ``INSERT OR IGNORE`` on the ``run_id`` UNIQUE constraint, mirroring
    :func:`record_commit_event` — a resumed-then-completed run contributes
    exactly one row. The FTS row is only written when the insert actually
    lands, so repeated calls do not duplicate search results.

    ``failure_terminal`` (ENH-2814) records whether the run stopped on a state
    declared ``failure: true``. ``None`` writes SQL NULL, marking a row whose
    failure-ness is unknown so readers fall back to the legacy name check.

    The ``config`` parameter is a forward-compatibility stub for a future
    ``analytics.capture.loop_runs`` gate; it is accepted but not yet used.
    Returns ``False`` only when the required identity fields are empty or the
    row already existed.
    """
    if not run_id or not loop_name:
        return False
    ts = ended_at or _now()
    conn = _pkg.connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO loop_runs("
            "run_id, loop_name, started_at, ended_at, final_state, iterations, "
            "terminated_by, error, evaluator_score, diagnostics_path, head_sha, branch, "
            "failure_terminal"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                loop_name,
                started_at,
                ts,
                final_state,
                iterations,
                terminated_by,
                error,
                evaluator_score,
                diagnostics_path,
                head_sha,
                branch,
                None if failure_terminal is None else int(failure_terminal),
            ),
        )
        inserted = bool(cursor.rowcount)
        if inserted:
            _index(
                conn,
                content=f"{loop_name} {final_state or ''} {terminated_by or ''}".strip()[:512],
                kind="loop_run",
                ref=run_id,
                anchor=loop_name,
                ts=ts,
            )
        conn.commit()
    finally:
        conn.close()
    return inserted


def record_usage_event(
    db_path: Path | str,
    *,
    run_id: str,
    ts: str,
    state: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
) -> None:
    """Write one live per-invocation row to ``usage_events`` (ENH-2724).

    Unlike :func:`_backfill_usage_events` (post-hoc, ``state`` always ``NULL``),
    this is called at loop-run finish with the FSM state each invocation ran in
    already known. ``usage_events`` has no uniqueness constraint — plain
    ``INSERT``, one row per :class:`~little_loops.subprocess_utils.TokenUsage`.
    """
    from little_loops.pricing import estimate_cost_usd

    cost_usd = estimate_cost_usd(
        model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
    )
    conn = _pkg.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, model, state, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, cost_usd, run_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                model,
                state,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_creation_tokens,
                cost_usd,
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_loop_run_diagnostics(db_path: Path | str, run_id: str, diagnostics_path: str) -> bool:
    """Link a ``loop-specialist``-written diagnostics artifact to its ``loop_runs`` row.

    A single ``UPDATE ... WHERE run_id = ?``, mirroring the
    ``skill_event_context`` completion-UPDATE pattern. Best-effort by design:
    returns ``False`` (does not raise) when no matching row exists yet.
    """
    if not run_id or not diagnostics_path:
        return False
    conn = _pkg.connect(db_path)
    try:
        cursor = conn.execute(
            "UPDATE loop_runs SET diagnostics_path = ? WHERE run_id = ?",
            (diagnostics_path, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    return bool(cursor.rowcount)


def record_learning_test_event(
    db_path: Path | str,
    target: str,
    file_path: str,
    config: dict | None = None,
) -> bool:
    """UPSERT one Learning Test Registry record mirror and refresh its FTS row.

    Reads the registry file at *file_path* (YAML frontmatter parsed the same
    way as :func:`little_loops.learning_tests._read_frontmatter_yaml`) and
    upserts it into ``learning_test_events`` keyed on ``record_id`` — the
    slugified *target*, matching the registry's own file-stem identity. A
    re-prove (or ``mark_stale``) overwrites the existing row's ``status``,
    ``assertions_json``, and ``date`` rather than inserting a duplicate. The
    matching FTS row is deleted and recreated in the same transaction so
    stale assertion text cannot remain searchable after a status change.

    Best-effort per the EPIC-1707 graceful-degradation contract: returns
    ``False`` (does not raise) when *file_path* is missing/unreadable or
    frontmatter fails to parse; callers should also wrap the call in
    ``try/except: pass`` or ``contextlib.suppress(Exception)`` per the
    ``record_issue_snapshot``/``record_commit_event`` precedent.

    The ``config`` parameter is a forward-compatibility stub for a future
    ``analytics.capture.learning_tests`` gate; it is accepted but not yet used.
    """
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import _read_frontmatter_yaml

    if not target:
        return False
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return False
    data = _read_frontmatter_yaml(content)
    if not data:
        return False

    record_id = slugify(target)
    status = data.get("status")
    date = data.get("date")
    raw_output_path = data.get("raw_output_path")
    assertions = data.get("assertions") or []
    assertions_json = json.dumps(assertions)
    claims = " ".join(str(a.get("claim", "")) for a in assertions if isinstance(a, dict))

    conn = _pkg.connect(db_path)
    ts = _now()
    try:
        conn.execute(
            "INSERT INTO learning_test_events"
            "(ts, record_id, target, status, assertions_json, date, raw_output_path)"
            " VALUES(?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(record_id) DO UPDATE SET"
            " ts=excluded.ts, target=excluded.target, status=excluded.status,"
            " assertions_json=excluded.assertions_json, date=excluded.date,"
            " raw_output_path=excluded.raw_output_path",
            (ts, record_id, target, status, assertions_json, date, raw_output_path),
        )
        conn.execute(
            "DELETE FROM search_index WHERE kind = ? AND ref = ?",
            ("learning_test", record_id),
        )
        _index(
            conn,
            content=f"{target} {claims}".strip()[:512],
            kind="learning_test",
            ref=record_id,
            anchor=target,
            ts=ts,
        )
        conn.commit()
    finally:
        conn.close()
    return True


def _backfill_learning_test_events(conn: sqlite3.Connection, registry_dir: Path) -> int:
    """Seed ``learning_test_events`` from ``.ll/learning-tests/*.md`` (ENH-2466).

    Follows the ``_backfill_snapshots()`` pattern: iterates ``*.md`` files,
    reads frontmatter, inserts with ``INSERT OR IGNORE`` on the ``record_id``
    UNIQUE constraint so re-running the backfill (or a record already written
    by :func:`record_learning_test_event`) does not duplicate rows. This is a
    best-effort reconcile companion for registry files edited outside the
    ``ll-learning-tests`` CLI — it does not overwrite a live-written row's
    newer status, unlike the CLI-path UPSERT.
    """
    from little_loops.issue_parser import slugify
    from little_loops.learning_tests import _read_frontmatter_yaml

    if not registry_dir.is_dir():
        return 0
    count = 0
    ts = _now()
    for md_file in sorted(registry_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        data = _read_frontmatter_yaml(content)
        if not data:
            continue
        target = data.get("target")
        if not target:
            continue
        record_id = slugify(target)
        status = data.get("status")
        date = data.get("date")
        raw_output_path = data.get("raw_output_path")
        assertions = data.get("assertions") or []
        assertions_json = json.dumps(assertions)
        claims = " ".join(str(a.get("claim", "")) for a in assertions if isinstance(a, dict))
        cursor = conn.execute(
            "INSERT OR IGNORE INTO learning_test_events"
            "(ts, record_id, target, status, assertions_json, date, raw_output_path)"
            " VALUES(?, ?, ?, ?, ?, ?, ?)",
            (ts, record_id, target, status, assertions_json, date, raw_output_path),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=f"{target} {claims}".strip()[:512],
                kind="learning_test",
                ref=record_id,
                anchor=target,
                ts=ts,
            )
        count += 1
    return count


def record_session_lifecycle_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    event: str,
    detail: dict | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool:
    """Write one row to ``session_lifecycle_events`` and index it in ``search_index``.

    Records session-lifecycle / handoff transitions (``handoff_needed``,
    ``compaction``, ``stale_ref_sweep``, plus ENH-2509's ``worktree_*``
    discriminators). Best-effort per the EPIC-1707 graceful-degradation
    contract: returns ``False`` (never raises) on any ``sqlite3.Error`` so a
    hook's primary job is never blocked by a missing/locked database.
    """
    detail_json = json.dumps(detail) if detail is not None else None
    ts = ts or _now()
    conn: sqlite3.Connection | None = None
    try:
        conn = _pkg.connect(db_path)
        conn.execute(
            "INSERT INTO session_lifecycle_events"
            "(ts, session_id, event, detail, head_sha, branch)"
            " VALUES(?, ?, ?, ?, ?, ?)",
            (ts, session_id, event, detail_json, head_sha, branch),
        )
        _index(
            conn,
            content=f"{event} {session_id or ''} {json.dumps(detail or {})}"[:512],
            kind="session_lifecycle",
            ref=session_id or "",
            anchor=event,
            ts=ts,
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_session_lifecycle_event: insert failed for event=%r", event, exc_info=True
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return True


def record_context_pressure_event(
    db_path: Path | str,
    *,
    session_id: str | None,
    used_pct: float | None,
    used_tokens_est: int | None,
    threshold_crossed: bool = False,
    crossed_level: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool:
    """Write one row to ``context_pressure_events`` and index it in ``search_index``.

    Records a single context-window-pressure measurement from
    ``context-monitor.sh`` (ENH-2507): the running ``used_pct``/token estimate
    plus whether this row crossed a new threshold level (``"50"``/``"75"``/
    ``"80"``/``"90"``/``"100"``). Best-effort per the EPIC-1707
    graceful-degradation contract: returns ``False`` (never raises) on any
    ``sqlite3.Error`` so the PostToolUse hook's primary job is never blocked
    by a missing/locked database.
    """
    ts = ts or _now()
    conn: sqlite3.Connection | None = None
    try:
        conn = _pkg.connect(db_path)
        conn.execute(
            "INSERT INTO context_pressure_events"
            "(ts, session_id, used_pct, used_tokens_est, threshold_crossed, crossed_level,"
            " head_sha, branch)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                used_pct,
                used_tokens_est,
                int(threshold_crossed),
                crossed_level,
                head_sha,
                branch,
            ),
        )
        _index(
            conn,
            content=f"{session_id or ''} {used_pct} {crossed_level or ''}"[:512],
            kind="context_pressure",
            ref=session_id or "",
            anchor=crossed_level or "",
            ts=ts,
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_context_pressure_event: insert failed for session_id=%r",
            session_id,
            exc_info=True,
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return True


def record_subagent_run_start(
    db_path: Path | str,
    *,
    parent_session_id: str | None,
    agent_id: str | None,
    agent_type: str | None,
    started_at: str | None = None,
    head_sha: str | None = None,
    branch: str | None = None,
    ts: str | None = None,
) -> bool:
    """Write one row to ``subagent_runs`` for a ``SubagentStart`` spawn.

    Idempotent via ``INSERT OR IGNORE`` on the ``(parent_session_id, agent_id)``
    UNIQUE constraint, mirroring :func:`record_commit_event` — a replayed
    SubagentStart (e.g. backfill re-run) contributes exactly one row. Best-effort
    per the EPIC-1707 contract: returns ``False`` (never raises) on any
    ``sqlite3.Error`` or a missing ``agent_id``.
    """
    if not agent_id:
        return False
    ts = ts or _now()
    started_at = started_at or ts
    conn: sqlite3.Connection | None = None
    try:
        conn = _pkg.connect(db_path)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO subagent_runs("
            "ts, parent_session_id, agent_id, agent_type, started_at, status, "
            "head_sha, branch"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, parent_session_id, agent_id, agent_type, started_at, "running", head_sha, branch),
        )
        inserted = bool(cursor.rowcount)
        if inserted:
            _index(
                conn,
                content=f"{agent_type or ''} {agent_id} {parent_session_id or ''}".strip()[:512],
                kind="subagent_run",
                ref=agent_id,
                anchor=agent_type or "",
                ts=ts,
            )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_subagent_run_start: insert failed for agent_id=%r", agent_id, exc_info=True
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return inserted


def record_subagent_run_stop(
    db_path: Path | str,
    *,
    parent_session_id: str | None,
    agent_id: str | None,
    agent_type: str | None = None,
    agent_transcript_path: str | None = None,
    status: str = "completed",
    ended_at: str | None = None,
) -> bool:
    """Update the matching ``subagent_runs`` row for a ``SubagentStop`` event.

    Matches on the ``(parent_session_id, agent_id)`` composite key. Best-effort:
    returns ``False`` (never raises) when no matching row exists yet, the
    ``agent_id`` is missing, or a ``sqlite3.Error`` occurs — mirroring
    :func:`update_loop_run_diagnostics`.
    """
    if not agent_id:
        return False
    ended_at = ended_at or _now()
    conn: sqlite3.Connection | None = None
    try:
        conn = _pkg.connect(db_path)
        cursor = conn.execute(
            "UPDATE subagent_runs SET ended_at = ?, status = ?, "
            "agent_transcript_path = COALESCE(?, agent_transcript_path), "
            "agent_type = COALESCE(?, agent_type) "
            "WHERE agent_id = ? AND parent_session_id IS ?",
            (ended_at, status, agent_transcript_path, agent_type, agent_id, parent_session_id),
        )
        conn.commit()
    except sqlite3.Error:
        logger.warning(
            "record_subagent_run_stop: update failed for agent_id=%r", agent_id, exc_info=True
        )
        return False
    finally:
        if conn is not None:
            conn.close()
    return bool(cursor.rowcount)


def _backfill_subagent_runs(conn: sqlite3.Connection, sessions_root: Path) -> int:
    """Seed ``subagent_runs`` from nested ``subagents/agent-<id>.jsonl`` transcripts.

    Discovers subagent transcripts under each parent session's transcript
    directory (``<session-dir>/subagents/*.jsonl``) and writes one completed row
    per nested file found, since a persisted transcript implies the spawn ran to
    completion (the live ``SubagentStart``/``SubagentStop`` hooks capture
    ``running``/``failed``/``timeout`` states that backfill cannot reconstruct
    after the fact). Idempotent via the same ``INSERT OR IGNORE`` as the live
    writer.
    """
    count = 0
    for subagents_dir in sessions_root.glob("*/subagents"):
        parent_session_id = subagents_dir.parent.name
        for transcript in subagents_dir.glob("*.jsonl"):
            agent_id = transcript.stem
            try:
                mtime = datetime.fromtimestamp(transcript.stat().st_mtime, tz=UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            except OSError:
                continue
            cursor = conn.execute(
                "INSERT OR IGNORE INTO subagent_runs("
                "ts, parent_session_id, agent_id, agent_transcript_path, started_at, "
                "ended_at, status"
                ") VALUES(?, ?, ?, ?, ?, ?, ?)",
                (mtime, parent_session_id, agent_id, str(transcript), mtime, mtime, "completed"),
            )
            if cursor.rowcount:
                count += 1
    return count


# ---------------------------------------------------------------------------

_ISSUE_TRANSITION_MAP: dict[str, str] = {
    "issue.completed": "done",
    "issue.closed": "done",
    "issue.deferred": "deferred",
    "issue.skipped": "cancelled",
    "issue.created": "open",
    "issue.started": "in_progress",
}


def _derive_transition(event_type: str) -> str:
    """Map an ``issue.*`` event type to the canonical transition/status string."""
    return _ISSUE_TRANSITION_MAP.get(event_type, event_type.split(".", 1)[1])


class SQLiteTransport:
    """EventBus sink that records FSM loop events into the session database.

    A single connection is opened at construction with ``check_same_thread``
    disabled, since :meth:`send` may be called from the FSM thread while other
    transports run their own threads; a lock serialises writes. Every
    operation is best-effort — a database error is logged and swallowed so a
    failing sink never aborts a loop run (the four ``wire_transports`` call
    sites depend on this).
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = resolve_history_db(db_path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            _pkg.ensure_db(self._path)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            _configure_connection(self._conn)
        except sqlite3.Error:
            logger.warning(
                "SQLiteTransport: could not open %s; sink disabled", self._path, exc_info=True
            )
            self._conn = None

    def send(self, event: dict[str, Any]) -> None:
        """Record a recognised event as a ``loop_events`` or ``issue_events`` row (best-effort)."""
        conn = self._conn
        if conn is None:
            return
        event_type = str(event.get("event", ""))
        ts = str(event.get("ts") or _now())
        try:
            with self._lock:
                if event_type in _LOOP_EVENT_TYPES:
                    loop_name = str(event.get("loop_name", "")) or None
                    state = event.get("state")
                    if event_type == "loop_complete":
                        state = event.get("outcome", state)
                    retries = event.get("retries")
                    conn.execute(
                        "INSERT INTO loop_events(ts, loop_name, state, transition, retries) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (
                            ts,
                            loop_name,
                            str(state) if state is not None else None,
                            event_type,
                            int(retries) if isinstance(retries, int) else None,
                        ),
                    )
                    _index(
                        conn,
                        content=" ".join(
                            str(p) for p in (loop_name, state, event_type) if p is not None
                        ),
                        kind="loop",
                        ref=loop_name or "",
                        anchor=f".loops/{loop_name}.yaml" if loop_name else "",
                        ts=ts,
                    )
                elif event_type.startswith("issue."):
                    _id_source_path = event.get("file_path") or event.get("issue_file")
                    issue_id = canonicalize_issue_id(
                        event.get("issue_id"), _id_source_path
                    ) or event.get("issue_id")
                    transition = _derive_transition(event_type)
                    # Authoritative session linkage (ENH-2462): producers put the
                    # emitting session's ID in the payload; both snake_case and
                    # the host JSONL camelCase spelling are accepted.
                    session_id = event.get("session_id") or event.get("sessionId")
                    issue_num = normalize_issue_id(issue_id) if issue_id else None
                    _cursor = conn.execute(
                        "INSERT OR IGNORE INTO issue_events("
                        "ts, issue_id, issue_num, transition, discovered_by, "
                        "issue_type, priority, captured_at, completed_at, session_id"
                        ") VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            ts,
                            issue_id,
                            issue_num,
                            transition,
                            event.get("discovered_by"),
                            event.get("issue_type"),
                            event.get("priority"),
                            event.get("captured_at"),
                            event.get("completed_at"),
                            str(session_id) if session_id else None,
                        ),
                    )
                    if issue_id:
                        _warn_on_dedup_collision(
                            conn,
                            "issue_events",
                            issue_num,
                            str(issue_id),
                            transition,
                            _cursor.rowcount == 1,
                        )
                    _index(
                        conn,
                        content=f"{issue_id or ''} {event.get('issue_type', '')}".strip(),
                        kind="issue",
                        ref=str(issue_id or ""),
                        anchor=event.get("issue_file", ""),
                        ts=ts,
                    )
                    # Side-effect: write content snapshot when the event carries a file path.
                    file_path = event.get("file_path")
                    if file_path and issue_id and transition in ("done", "open", "cancelled"):
                        try:
                            conn.commit()  # flush issue_events before spawning new conn
                        except sqlite3.Error:
                            pass
                        record_issue_snapshot(self._path, str(issue_id), transition, str(file_path))
                        return  # skip second commit below; record_issue_snapshot committed
                else:
                    return
                conn.commit()
        except sqlite3.Error:
            logger.warning("SQLiteTransport: write failed for event %r", event_type, exc_info=True)

    def close(self) -> None:
        """Close the underlying connection (best-effort)."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None


def _hash_args(value: Any) -> str:
    """Return a short stable hash of a tool-call argument structure."""
    try:
        blob = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = repr(value)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _normalize_agent_type(subagent_type: Any) -> str | None:
    """Strip the ``ll:`` plugin prefix so built-in and plugin agent names group together.

    ``Task`` tool spawns carry ``subagent_type`` as either a bare name
    (``Explore``) or an ``ll:``-prefixed plugin agent (``ll:codebase-locator``);
    without normalization these count as distinct agents in aggregation.
    """
    if not isinstance(subagent_type, str) or not subagent_type:
        return None
    normalized = subagent_type.removeprefix("ll:")
    return normalized or None


_MCP_TOOL_NAME_RE = re.compile(r"^mcp__(.+?)__(.+)$")


def _parse_mcp_tool_name(tool_name: str) -> tuple[str | None, str | None]:
    """Split ``mcp__<server>__<tool>`` into ``(server, tool)``, else ``(None, None)``."""
    match = _MCP_TOOL_NAME_RE.match(tool_name)
    if not match:
        return None, None
    return match.group(1), match.group(2)


_FILENAME_TYPE_RE = re.compile(r"(BUG|ENH|FEAT|EPIC)-(\d+)")

_FILENAME_PRIORITY_RE = re.compile(r"^(P\d)")

_CANONICAL_ISSUE_ID_RE = re.compile(r"^(?:BUG|ENH|FEAT|EPIC)-\d+$", re.IGNORECASE)


def canonicalize_issue_id(raw: object, file_path: str | Path | None) -> str | None:
    """Canonicalize a frontmatter/caller-supplied issue id to ``TYPE-NNN``.

    BUG-2769: every history-db ingest path previously trusted a truthy
    frontmatter ``id`` verbatim, falling back to the filename-derived
    ``TYPE-NNN`` only when ``id`` was entirely absent. A present-but-malformed
    id (bare ``2756``, quoted ``"1294"``) sailed through and mis-keyed the
    row. This helper is the single normalization point for all four ingest
    sites:

    - if *raw* already has the canonical ``TYPE-NNN`` shape (case-insensitive),
      it is returned uppercased as-is;
    - else, if *file_path*'s filename yields a ``TYPE`` via
      ``_FILENAME_TYPE_RE`` and *raw* is a bare integer/numeric string, the two
      are spliced into ``TYPE-<raw>``;
    - else, falls back to the filename's own ``TYPE-NNN`` match entirely (this
      also covers the "id absent" case);
    - else ``None`` when nothing usable can be derived.

    Distinct from :func:`normalize_issue_id` (line ~1189), which is a
    deliberately permissive numeric (``int | None``) extractor already used
    for DB key columns — this helper instead validates/repairs the *display*
    ``TYPE-NNN`` string written to ``issue_id``/``ref`` columns.
    """
    raw_str = str(raw).strip() if raw is not None else ""
    if _CANONICAL_ISSUE_ID_RE.match(raw_str):
        canonical = raw_str.upper()
        if canonical != raw_str:
            logger.warning("canonicalize_issue_id: normalized id casing %r -> %r", raw, canonical)
        return canonical

    filename = Path(file_path).name if file_path else ""
    m = _FILENAME_TYPE_RE.search(filename) if filename else None
    filename_type = m.group(1) if m else None
    filename_num = m.group(2) if m else None

    result: str | None = None
    if filename_type and raw_str.isdigit():
        result = f"{filename_type}-{raw_str}"
    elif filename_type and filename_num:
        result = f"{filename_type}-{filename_num}"

    if result:
        logger.warning(
            "canonicalize_issue_id: normalized malformed id %r -> %r (file=%s)",
            raw,
            result,
            filename or file_path,
        )
    return result


def _derive_type_priority(filename: str, fm: dict[str, Any]) -> tuple[str | None, str | None]:
    """Derive (issue_type, priority) preferring frontmatter, falling back to filename.

    Mirrors :func:`little_loops.issue_history.parsing.parse_completed_issue`'s
    filename-parsing convention (``P[0-5]-[TYPE]-[NNN]-...``).
    """
    fm_type = fm.get("type")
    issue_type: str | None = str(fm_type) if isinstance(fm_type, str) and fm_type else None
    fm_priority = fm.get("priority")
    priority: str | None = (
        str(fm_priority) if isinstance(fm_priority, str) and fm_priority else None
    )
    if issue_type is None:
        m = _FILENAME_TYPE_RE.search(filename)
        if m:
            issue_type = m.group(1)
    if priority is None:
        m = _FILENAME_PRIORITY_RE.match(filename)
        if m:
            priority = m.group(1)
    return issue_type, priority


def _backfill_snapshots(
    conn: sqlite3.Connection, issues_dir: Path, *, warn_on_collision: bool = False
) -> int:
    """Seed ``issue_snapshots`` and ``search_index`` from issue files under *issues_dir*.

    Follows the ``_backfill_issues()`` pattern: iterates ``*.md`` files, reads
    frontmatter + body, inserts with ``INSERT OR IGNORE`` for idempotency.
    Uses the issue's current ``status`` as the ``transition`` value.

    Collision warnings (BUG-3006) are suppressed by default
    (``warn_on_collision=False``): a backfill legitimately replays already-
    recorded history and would otherwise warn on every retyped issue. Pass
    ``warn_on_collision=True`` to surface genuine number-reuse collisions.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter

    count = 0
    ts = _now()
    for issue_file in sorted(issues_dir.rglob("*.md")):
        try:
            content = issue_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(content)
        issue_id = canonicalize_issue_id(fm.get("id"), issue_file)
        if not issue_id:
            continue
        transition = str(fm.get("status", "open"))
        title = fm.get("title") or fm.get("id") or issue_id
        priority = fm.get("priority")
        issue_type = fm.get("type")
        body = strip_frontmatter(content)
        fm_json = json.dumps({k: str(v) for k, v in fm.items() if v is not None}, sort_keys=True)
        issue_num = normalize_issue_id(str(issue_id))
        cursor = conn.execute(
            "INSERT OR IGNORE INTO issue_snapshots"
            "(ts, issue_id, issue_num, transition, title, priority, issue_type, body, frontmatter)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                str(issue_id),
                issue_num,
                transition,
                str(title),
                priority,
                issue_type,
                body,
                fm_json,
            ),
        )
        if warn_on_collision:
            _warn_on_dedup_collision(
                conn, "issue_snapshots", issue_num, str(issue_id), transition, cursor.rowcount == 1
            )
        _index(
            conn,
            content=f"{issue_id} {title} {body or ''}".strip(),
            kind="snapshot",
            ref=str(issue_id),
            anchor=str(issue_file),
            ts=ts,
        )
        count += 1
    return count


def _backfill_issues_and_snapshots(
    conn: sqlite3.Connection, issues_dir: Path, *, warn_on_collision: bool = False
) -> tuple[int, int]:
    """Seed ``issue_events`` and ``issue_snapshots`` in a single read/parse pass.

    Combines :func:`_backfill_issues` and :func:`_backfill_snapshots` into one
    ``rglob("*.md")`` walk so each issue file is read and its frontmatter
    parsed exactly once (ENH-2782), instead of once per helper. The read and
    parse are wrapped in a single ``try/except OSError`` (matching
    ``_backfill_issues``'s broader guard rather than ``_backfill_snapshots``'s
    read-only one — no existing test asserts on the narrower propagation
    behavior). Otherwise preserves each function's per-file logic: the
    per-file event ``ts`` derivation vs. the single shared snapshot ``ts``,
    and the ``_derive_type_priority()`` normalization used only for events.
    Returns ``(issues_count, snapshots_count)``.

    Collision warnings (BUG-3006) are suppressed by default
    (``warn_on_collision=False``): a backfill legitimately replays already-
    recorded history and would otherwise warn on every retyped issue. Pass
    ``warn_on_collision=True`` to surface genuine number-reuse collisions.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter

    issues_count = 0
    snapshots_count = 0
    snapshot_ts = _now()
    for issue_file in sorted(issues_dir.rglob("*.md")):
        try:
            content = issue_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
        except OSError:
            continue
        issue_id = canonicalize_issue_id(fm.get("id"), issue_file)
        if not issue_id:
            continue
        issue_num = normalize_issue_id(str(issue_id))

        # _backfill_issues portion
        status = str(fm.get("status", "open"))
        discovered_by = fm.get("discovered_by")
        captured_at = fm.get("captured_at")
        completed_at = fm.get("completed_at")
        event_ts = str(completed_at or captured_at or fm.get("discovered_date") or "")
        issue_type, priority = _derive_type_priority(issue_file.name, fm)
        completed_date: str | None = None
        if isinstance(completed_at, str) and completed_at:
            completed_date = completed_at[:10]
        _events_cursor = conn.execute(
            "INSERT OR IGNORE INTO issue_events("
            "ts, issue_id, issue_num, transition, discovered_by, "
            "issue_type, priority, completed_date, captured_at, completed_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_ts,
                str(issue_id),
                issue_num,
                status,
                str(discovered_by) if discovered_by else None,
                issue_type,
                priority,
                completed_date,
                str(captured_at) if captured_at else None,
                str(completed_at) if completed_at else None,
            ),
        )
        if warn_on_collision:
            _warn_on_dedup_collision(
                conn,
                "issue_events",
                issue_num,
                str(issue_id),
                status,
                _events_cursor.rowcount == 1,
            )
        _index(
            conn,
            content=f"{issue_id} {status} {issue_type or ''}",
            kind="issue",
            ref=str(issue_id),
            anchor=str(issue_file),
            ts=event_ts,
        )
        issues_count += 1

        # _backfill_snapshots portion
        transition = status
        title = fm.get("title") or fm.get("id") or issue_id
        snapshot_priority = fm.get("priority")
        snapshot_issue_type = fm.get("type")
        body = strip_frontmatter(content)
        fm_json = json.dumps({k: str(v) for k, v in fm.items() if v is not None}, sort_keys=True)
        _snapshots_cursor = conn.execute(
            "INSERT OR IGNORE INTO issue_snapshots"
            "(ts, issue_id, issue_num, transition, title, priority, issue_type, body, frontmatter)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_ts,
                str(issue_id),
                issue_num,
                transition,
                str(title),
                snapshot_priority,
                snapshot_issue_type,
                body,
                fm_json,
            ),
        )
        if warn_on_collision:
            _warn_on_dedup_collision(
                conn,
                "issue_snapshots",
                issue_num,
                str(issue_id),
                transition,
                _snapshots_cursor.rowcount == 1,
            )
        _index(
            conn,
            content=f"{issue_id} {title} {body or ''}".strip(),
            kind="snapshot",
            ref=str(issue_id),
            anchor=str(issue_file),
            ts=snapshot_ts,
        )
        snapshots_count += 1

    return issues_count, snapshots_count


def _backfill_loops(conn: sqlite3.Connection, loops_dir: Path) -> int:
    """Seed ``loop_events`` from FSM state JSON under ``.loops/.running`` + ``.history``."""
    count = 0
    for sub in (".running", ".history"):
        directory = loops_dir / sub
        if not directory.is_dir():
            continue
        for state_file in sorted(directory.glob("*.json")):
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            loop_name = str(data.get("loop_name") or state_file.stem)
            state = data.get("current_state") or data.get("state")
            ts = str(data.get("updated_at") or data.get("started_at") or "")
            conn.execute(
                "INSERT INTO loop_events(ts, loop_name, state, transition, retries) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, loop_name, str(state) if state else None, "backfill", None),
            )
            _index(
                conn,
                content=f"{loop_name} {state or ''}",
                kind="loop",
                ref=loop_name,
                anchor=str(state_file),
                ts=ts,
            )
            count += 1
    return count


def _iter_events(source: list[Path] | sqlite3.Cursor) -> Generator[tuple[str, str], None, None]:
    """Yield ``(raw_line, source_label)`` pairs from JSONL files or a raw_events cursor.

    Lets the JSONL-derived ``_backfill_*`` functions accept either a legacy
    ``list[Path]`` (re-reads files line-by-line) or a ``raw_events`` cursor
    selecting ``(raw_line, source_path)`` rows in that order — the
    :func:`rebuild` path, replaying previously-ingested lines instead of
    re-reading the filesystem (ENH-2581). Cursor-sourced ``raw_line`` values pass
    through :func:`_unpack_payload` (compressed BLOB → text; legacy TEXT unchanged).
    """
    if isinstance(source, sqlite3.Cursor):
        for row in source:
            yield _unpack_payload(row[0]), row[1]
        return
    for jsonl_file in source:
        try:
            handle = jsonl_file.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield line, str(jsonl_file)


def _backfill_tool_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``tool_events`` from assistant tool-use blocks in session JSONL files.

    *source* is either a list of on-disk JSONL files (legacy) or a
    ``raw_events`` cursor (the :func:`rebuild` path) — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "assistant":
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        content = record.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_name = str(block.get("name", ""))
            args = block.get("input", {})
            agent_type = (
                _normalize_agent_type(args.get("subagent_type"))
                if tool_name == "Task" and isinstance(args, dict)
                else None
            )
            mcp_server, mcp_tool = _parse_mcp_tool_name(tool_name)
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                "result_size, bytes_in, bytes_out, cache_hit, agent_type, "
                "mcp_server, mcp_tool) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    session_id,
                    tool_name,
                    _hash_args(args),
                    None,
                    None,
                    None,
                    None,
                    agent_type,
                    mcp_server,
                    mcp_tool,
                ),
            )
            _index(
                conn,
                content=f"{tool_name} {agent_type or ''}".strip(),
                kind="tool",
                ref=tool_name,
                anchor=source_label,
                ts=ts,
            )
            count += 1
    return count


def _load_loop_run_windows(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return ``(started_at, ended_at, run_id)`` triples for run_id backfill joins.

    ``loop_runs`` has no ``session_id`` (ENH-2725 research), so this is the only
    correlation available between a ``usage_events`` row and its owning run: a
    timestamp-window join. Rows with a NULL boundary can't participate in a
    window comparison and are excluded up front.
    """
    rows = conn.execute(
        "SELECT started_at, ended_at, run_id FROM loop_runs "
        "WHERE started_at IS NOT NULL AND ended_at IS NOT NULL"
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _derive_run_id_for_ts(ts: str, windows: list[tuple[str, str, str]]) -> str | None:
    """Stamp ``run_id`` only when exactly one ``loop_runs`` window contains *ts*.

    Concurrent/overlapping ``loop_runs`` (e.g. ``ll-parallel`` worktree runs)
    make the join ambiguous; per the ENH-2725 decision, ambiguous or
    zero-match rows stay ``NULL`` rather than guessing (Option A).
    """
    if not ts:
        return None
    matches = [run_id for started_at, ended_at, run_id in windows if started_at <= ts <= ended_at]
    return matches[0] if len(matches) == 1 else None


def _backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``usage_events`` from assistant ``message.usage`` blocks (ENH-2461).

    Persists the real LLM token counts the API returned (``input_tokens``,
    ``output_tokens``, ``cache_read_input_tokens``,
    ``cache_creation_input_tokens``) plus a derived ``cost_usd``, one row per
    assistant turn. The on-disk transcript carries the usage block on
    ``type == "assistant"`` records at ``message.usage`` — verified against live
    session files. (The ``type == "result"`` shape referenced in earlier issue
    research only exists in the *live* subprocess stdout stream, which
    ``raw_events`` never ingests.) The ``state`` column is always ``NULL`` here:
    the transcript stream carries no FSM-state boundary, so per-state grain is
    not derivable from this source (ENH-2461 Addendum 2). *source* accepts either
    JSONL files or a ``raw_events`` cursor — see :func:`_iter_events`.

    ``run_id`` is backfilled via a timestamp-window join against ``loop_runs``
    (ENH-2725) — see :func:`_derive_run_id_for_ts`. Rows with no derivable
    ``run_id`` stay ``NULL``, matching the live-writer path's behavior for
    non-loop sessions.
    """
    from little_loops.pricing import estimate_cost_usd

    count = 0
    windows = _load_loop_run_windows(conn)
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        cache_read = usage.get("cache_read_input_tokens")
        cache_creation = usage.get("cache_creation_input_tokens")
        # Every real usage block carries at least input/output; skip rows with
        # no token signal at all (defensive against malformed/partial records).
        if input_tokens is None and output_tokens is None:
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        model = message.get("model")
        cost_usd = estimate_cost_usd(
            str(model or ""),
            int(input_tokens or 0),
            int(output_tokens or 0),
            int(cache_read or 0),
            int(cache_creation or 0),
        )
        run_id = _derive_run_id_for_ts(ts, windows)
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
            "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, cost_usd, "
            "run_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                session_id,
                model,
                None,
                input_tokens,
                output_tokens,
                cache_read,
                cache_creation,
                cost_usd,
                run_id,
            ),
        )
        _index(
            conn,
            content=f"{model or ''} usage",
            kind="usage",
            ref=str(model or ""),
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


def _backfill_messages(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``message_events`` from user blocks in session JSONL files.

    Mirrors :func:`_backfill_tool_events` but selects ``type == "user"`` records
    and inserts the user's textual content. Used by analyze_workflows() so
    workflow analysis can read message bodies from the DB instead of a JSONL
    file (ENH-1621). *source* accepts either JSONL files or a raw_events
    cursor — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "user":
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        # The user message body lives at message.content; it may be a
        # plain string or a list of content blocks. We persist a text
        # rendering — list blocks are concatenated by their "text"
        # field so analyze_workflows() can run its regexes over it.
        content = record.get("message", {}).get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            text = "\n".join(parts)
        elif isinstance(content, str):
            text = content
        else:
            text = ""
        if not text.strip():
            continue
        conn.execute(
            "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
            (ts, str(session_id) if session_id else None, text),
        )
        _index(
            conn,
            content=text[:512],
            kind="message",
            ref=str(session_id) if session_id else "",
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


def _backfill_assistant_messages(
    conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor
) -> int:
    """Seed ``assistant_messages`` from assistant blocks in session JSONL files.

    Mirrors :func:`_backfill_messages` but selects ``type == "assistant"`` records
    and concatenates text blocks with ``"\\n\\n"`` — matching the output shape of
    ``_extract_turn_pairs()`` in ``user_messages.py``. Also counts ``tool_use``
    blocks and stores the count in ``tool_use_count`` so filter predicates like
    ``min_tool_invocations`` (ENH-1941) can operate without a JOIN.

    Idempotent: INSERT OR IGNORE prevents duplicate rows on repeated backfill.
    Depends on the ``sessions`` table (v4 / ENH-1710) for the session_id→JSONL
    mapping used by ``conversation_turns()`` to JOIN on session_id. *source*
    accepts either JSONL files or a raw_events cursor — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "assistant":
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        content = record.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        # Collect text blocks and count tool_use blocks
        text_blocks: list[str] = []
        tool_use_count = 0
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    txt = block.get("text", "").strip()
                    if txt:
                        text_blocks.append(txt)
                elif block.get("type") == "tool_use":
                    tool_use_count += 1
        if not text_blocks:
            continue
        concatenated = "\n\n".join(text_blocks)
        conn.execute(
            "INSERT OR IGNORE INTO assistant_messages(ts, session_id, content, tool_use_count)"
            " VALUES(?, ?, ?, ?)",
            (ts, str(session_id) if session_id else None, concatenated, tool_use_count),
        )
        _index(
            conn,
            content=concatenated[:512],
            kind="message",
            ref=str(session_id) if session_id else "",
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


_BACKFILL_SKILL_RE = re.compile(r"<command-name>/ll:(\S+)")

_BACKFILL_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)

_BACKFILL_ENHANCED_RE = re.compile(r"^ENHANCED:\s*(.+)", re.MULTILINE | re.DOTALL)


def _backfill_prompt_opt(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Best-effort enrich ``prompt_opt_events`` offer rows with the optimized text.

    Matches each still-unenriched ``offered=1`` row (written live by
    ``user_prompt_submit.py::handle()``) to the nearest-following assistant
    turn in the same session whose text contains an ``ENHANCED:`` block —
    the ``confirm=true`` path in ``optimize-prompt-hook.md`` (ENH-2498).
    ``confirm=false`` sessions emit only a short summary with no recoverable
    replacement prompt, so those offer rows are left unenriched
    (``optimized_text``/``accepted`` stay NULL) — a documented evidence
    limitation, not a bug. Only rows with ``optimized_text IS NULL`` are
    candidates and the UPDATE is guarded the same way, so repeated calls
    (e.g. from :func:`rebuild`) are idempotent and never re-index duplicate
    FTS rows. *source* accepts either JSONL files or a ``raw_events``
    cursor — see :func:`_iter_events`.
    """
    offers = conn.execute(
        "SELECT id, ts, session_id FROM prompt_opt_events "
        "WHERE offered = 1 AND optimized_text IS NULL AND session_id IS NOT NULL"
    ).fetchall()
    if not offers:
        return 0
    by_session: dict[str, list[tuple[int, str]]] = {}
    for row_id, ts, session_id in offers:
        by_session.setdefault(session_id, []).append((row_id, ts))

    count = 0
    for line, _source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "assistant":
            continue
        session_id = record.get("sessionId")
        candidates = by_session.get(session_id)
        if not candidates:
            continue
        ts = str(record.get("timestamp") or "")
        content = record.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        text = "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        m = _BACKFILL_ENHANCED_RE.search(text)
        if not m:
            continue
        eligible = [(row_id, o_ts) for row_id, o_ts in candidates if o_ts <= ts]
        if not eligible:
            continue
        row_id, _ = max(eligible, key=lambda c: c[1])
        enhanced = m.group(1).strip()
        cursor = conn.execute(
            "UPDATE prompt_opt_events SET optimized_len = ?, optimized_text = ?, accepted = 1 "
            "WHERE id = ? AND optimized_text IS NULL",
            (len(enhanced), enhanced, row_id),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=enhanced[:512],
                kind="prompt_opt",
                ref=session_id or "",
                anchor="",
                ts=ts,
            )
            count += 1
    return count


def _backfill_skill_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``skill_events`` from /ll: invocations in user blocks of session JSONL files.

    Mirrors :func:`_backfill_messages` but selects ``type == "user"`` records and
    matches the ``<command-name>/ll:<name></command-name>`` signal. Populates the
    ``skill_events`` table that was added in schema v7 (ENH-1833) but never extended
    to include a backfill path (BUG-2283). Used by ``ll-logs stats`` so pre-init
    invocations are reflected in skill invocation counts. *source* accepts either
    JSONL files or a raw_events cursor — see :func:`_iter_events`.
    """
    count = 0
    for line, source_label in _iter_events(source):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "user":
            continue
        session_id = record.get("sessionId")
        ts = str(record.get("timestamp") or "")
        content = record.get("message", {}).get("content", "")
        if isinstance(content, list):
            text = ""
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if text:
                        break
        elif isinstance(content, str):
            text = content
        else:
            text = ""
        if not text:
            continue
        m = _BACKFILL_SKILL_RE.search(text)
        if not m:
            continue
        skill_name = m.group(1)
        if skill_name.endswith("</command-name>"):
            skill_name = skill_name[: -len("</command-name>")]
        args_m = _BACKFILL_ARGS_RE.search(text)
        args = args_m.group(1).strip()[:200] if args_m else ""
        conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
            (ts, str(session_id) if session_id else None, skill_name, args),
        )
        _index(
            conn,
            content=skill_name,
            kind="skill",
            ref=str(session_id) if session_id else "",
            anchor=source_label,
            ts=ts,
        )
        count += 1
    return count


def mine_corrections_from_messages(conn: sqlite3.Connection, config: dict | None = None) -> int:
    """Scan ``message_events`` and insert matching rows into ``user_corrections``.

    Designed for both the one-time retroactive pass over existing rows and
    repeated calls during backfill; idempotent via ``INSERT OR IGNORE`` +
    ``idx_corrections_dedup``. Only writes a ``search_index`` entry when the
    row is actually inserted (rowcount == 1) to avoid duplicate FTS rows.
    Gated by ``analytics.capture.corrections`` (ENH-1841).

    Returns the count of newly inserted correction rows.
    """
    extra_patterns: list[str] = []
    if config is not None:
        from little_loops.config.features import AnalyticsCaptureConfig

        capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
        if not capture.corrections:
            return 0
        extra_patterns = capture.correction_patterns

    count = 0
    rows = conn.execute("SELECT ts, session_id, content FROM message_events").fetchall()
    for ts, session_id, content in rows:
        if not content or not is_correction(content, extra_patterns=extra_patterns):
            continue
        text = content[:512]
        cursor = conn.execute(
            "INSERT OR IGNORE INTO user_corrections(ts, session_id, content, source)"
            " VALUES(?, ?, ?, 'backfill')",
            (ts, session_id, text),
        )
        if cursor.rowcount:
            _index(
                conn,
                content=text,
                kind="correction",
                ref=session_id or "",
                anchor="backfill",
                ts=ts,
            )
            count += 1
    return count

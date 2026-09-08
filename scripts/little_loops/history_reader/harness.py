"""ll-harness / eval outcome telemetry (ENH-2775 split from the former flat
``history_reader.py``).

Backing tables: ``harness_events`` (``recent_harness_events``,
``harness_eval_pass_rate``, ``harness_eval_abstention_rate``) and
``verdict_events`` (``check_high_confidence_abstention`` — queries the
``verdict_events`` table directly by name, not via ``events.py``'s
``VerdictEvent``/``recent_verdict_events``, so no DAG exception is needed).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    CANNOT_JUDGE,
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)

__all__ = [
    "HarnessEvent",
    "HighConfidenceAbstention",
    "authoritative_attempt",
    "authoritative_attempts",
    "check_high_confidence_abstention",
    "harness_event_by_id",
    "harness_eval_abstention_rate",
    "harness_eval_pass_rate",
    "recent_harness_events",
]


@dataclass
class HarnessEvent:
    """A ``harness_events`` row — one ll-harness / eval run outcome (ENH-2741).

    ENH-141 adds three content-pin fields (``target_content_hash``,
    ``target_path``, ``dirty``) so consumers can compare runs across commits
    without re-diffing the working tree by hand.

    ENH-3407 adds ``id`` plus the five v49 run-model columns (``cell_key``,
    ``repetition``, ``attempt_kind``, ``continuations``, ``superseded_by``),
    all trailing-default so existing positional construction in tests keeps
    working.
    """

    ts: str
    runner: str | None
    target: str | None
    exit_code: int | None
    semantic_verdict: str | None
    semantic_passed: int | None
    timed_out: int | None
    duration_ms: int | None
    head_sha: str | None
    branch: str | None
    parent_id: int | None
    semantic_prompt: str | None
    semantic_confidence: float | None
    semantic_reason: str | None
    semantic_evidence: str | None
    semantic_model: str | None
    target_content_hash: str | None = None
    target_path: str | None = None
    dirty: int | None = None
    id: int | None = None
    cell_key: str | None = None
    repetition: int | None = None
    attempt_kind: str | None = None
    continuations: int | None = None
    superseded_by: int | None = None


_HARNESS_EVENT_COLUMNS = (
    "id, ts, runner, target, exit_code, semantic_verdict, semantic_passed, timed_out, "
    "duration_ms, head_sha, branch, parent_id, semantic_prompt, semantic_confidence, "
    "semantic_reason, semantic_evidence, semantic_model, "
    "target_content_hash, target_path, dirty, "
    "cell_key, repetition, attempt_kind, continuations, superseded_by"
)


def recent_harness_events(
    *,
    runner: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[HarnessEvent]:
    """Return recent ll-harness / eval outcomes, newest first, optionally filtered (ENH-2741)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_HARNESS_EVENT_COLUMNS} FROM harness_events "
        clauses: list[str] = []
        params: list[Any] = []
        if runner is not None:
            clauses.append("runner = ?")
            params.append(runner)
        if target is not None:
            clauses.append("target = ?")
            params.append(target)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_harness_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, HarnessEvent) for row in rows]


def harness_event_by_id(db_path: Path | str, attempt_id: int) -> HarnessEvent | None:
    """Return the ``harness_events`` row with ``id == attempt_id``, or None (ENH-3407).

    Used by ``ll-harness``'s ``--retry-of`` admissibility gate to look up the
    prior attempt a run claims to retry.
    """
    conn = _connect_readonly(Path(db_path))
    if conn is None:
        return None
    try:
        sql = f"SELECT {_HARNESS_EVENT_COLUMNS} FROM harness_events WHERE id = ?"
        row = conn.execute(sql, (attempt_id,)).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: harness_event_by_id query failed", exc_info=True)
        return None
    finally:
        conn.close()
    return None if row is None else _row_to_dataclass(row, HarnessEvent)


def authoritative_attempt(
    db_path: Path | str, cell_key: str, repetition: int
) -> HarnessEvent | None:
    """Return the earliest non-superseded row for ``(cell_key, repetition)`` (ENH-3407).

    Per-repetition, not per-cell: a cell with three clean repetitions has
    three authoritative rows, one per repetition index. "Earliest" is by
    ``id`` — the first attempt recorded for that repetition that has never
    been superseded.
    """
    conn = _connect_readonly(Path(db_path))
    if conn is None:
        return None
    try:
        sql = (
            f"SELECT {_HARNESS_EVENT_COLUMNS} FROM harness_events "
            "WHERE cell_key = ? AND repetition = ? AND superseded_by IS NULL "
            "ORDER BY id LIMIT 1"
        )
        row = conn.execute(sql, (cell_key, repetition)).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: authoritative_attempt query failed", exc_info=True)
        return None
    finally:
        conn.close()
    return None if row is None else _row_to_dataclass(row, HarnessEvent)


def authoritative_attempts(db_path: Path | str, cell_key: str) -> list[HarnessEvent]:
    """Return one authoritative row per repetition index for *cell_key* (ENH-3407).

    The set ENH-3408 counts as n: excludes superseded rows, and for each
    repetition index keeps only the earliest (lowest ``id``) surviving
    attempt. Losing (superseded) attempts remain in ``harness_events`` but
    are never returned here.
    """
    conn = _connect_readonly(Path(db_path))
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {_HARNESS_EVENT_COLUMNS} FROM harness_events "
            "WHERE cell_key = ? AND superseded_by IS NULL "
            "ORDER BY repetition ASC, id ASC"
        )
        rows = conn.execute(sql, (cell_key,)).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: authoritative_attempts query failed", exc_info=True)
        return []
    finally:
        conn.close()
    seen: set[int] = set()
    result: list[HarnessEvent] = []
    for row in rows:
        repetition = row["repetition"]
        if repetition in seen:
            continue
        seen.add(repetition)
        result.append(_row_to_dataclass(row, HarnessEvent))
    return result


def harness_eval_pass_rate(
    target: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the semantic-verdict pass fraction for *target*, or None if no scored rows (ENH-2741).

    Counts every row with a non-NULL ``semantic_passed``. ``cli/harness.py`` sets
    ``semantic_passed`` on every non-abstained run regardless of whether
    ``--semantic`` was supplied (exit-code-only runs included), so the
    denominator is *all non-abstained runs* for *target*, not only the
    ``check_semantic`` verdict path (ENH-3223).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = (
            "SELECT SUM(CASE WHEN semantic_passed = 1 THEN 1 ELSE 0 END) AS successes, "
            "COUNT(semantic_passed) AS scored "
            "FROM harness_events WHERE target = ?"
        )
        params: list[Any] = [target]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: harness_eval_pass_rate query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["scored"]:
        return None
    return row["successes"] / row["scored"]


def harness_eval_abstention_rate(
    target: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Return the `cannot_judge` abstention rate for *target*, or None if no scored rows.

    ENH-3185 AC4: sits alongside :func:`harness_eval_pass_rate`, whose
    ``COUNT(semantic_passed)`` denominator already excludes abstained rows
    (callers write ``semantic_passed = NULL`` for a ``cannot_judge`` verdict)
    -- this function reports that excluded slice as its own rate rather than
    letting it silently deflate the pass rate. ``scored`` here counts every
    row with a non-NULL ``semantic_verdict`` (pass, fail, and abstain), unlike
    ``harness_eval_pass_rate()``'s ``scored`` which only counts non-abstained
    rows -- the two denominators are deliberately different questions.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        # `_` is a SQL LIKE wildcard; escape it so the pattern only matches the
        # literal `_uncertain` suffix (ENH-3185 AC12), not an arbitrary char.
        sql = (
            "SELECT SUM(CASE WHEN semantic_verdict = ? OR semantic_verdict LIKE ? ESCAPE '\\' "
            "THEN 1 ELSE 0 END) AS abstentions, "
            "COUNT(semantic_verdict) AS scored "
            "FROM harness_events WHERE target = ?"
        )
        params: list[Any] = [CANNOT_JUDGE, f"{CANNOT_JUDGE}\\_%", target]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: harness_eval_abstention_rate query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["scored"]:
        return None
    return {
        "abstentions": row["abstentions"] or 0,
        "scored": row["scored"],
        "abstention_rate": (row["abstentions"] or 0) / row["scored"],
    }


@dataclass
class HighConfidenceAbstention:
    """A ``cannot_judge`` row whose ``confidence`` exceeds the manual-review threshold (ENH-230).

    A high-confidence abstention is a producer-side regression signal: if
    the gate is confident enough to score >= threshold, it should be able
    to render a real verdict. Catching these in a manual-review queue is
    the loud-failure point for the LLM-gaming path where a producer uses
    ``cannot_judge`` as a defensive fallback on borderline inputs.
    """

    ts: str
    session_id: str | None
    verdict_kind: str
    target_id: str | None
    abstention_reason: str | None
    confidence: int


def check_high_confidence_abstention(
    *,
    threshold: int = 90,
    verdict_kind: str | None = None,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[HighConfidenceAbstention]:
    """Return ``cannot_judge`` rows whose ``confidence`` is implausibly high.

    ENH-230 emits a ``logging.warning`` per row (logger name
    ``little_loops.history_reader``) and returns the row list. Threshold
    defaults to 90; callers may tighten or loosen. The check is best-effort
    and never raises — a missing or locked DB returns ``[]``.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, verdict_kind, target_id, abstention_reason, confidence "
            "FROM verdict_events WHERE verdict = 'cannot_judge' "
            "AND confidence IS NOT NULL AND confidence >= ? "
        )
        params: list[Any] = [threshold]
        if verdict_kind is not None:
            sql += "AND verdict_kind = ? "
            params.append(verdict_kind)
        if since is not None:
            sql += "AND ts >= ? "
            params.append(since)
        sql += "ORDER BY ts DESC, id DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning(
            "history_reader: check_high_confidence_abstention query failed",
            exc_info=True,
        )
        return []
    finally:
        conn.close()
    result = [_row_to_dataclass(row, HighConfidenceAbstention) for row in rows]
    for row in result:
        logger.warning(
            "high-confidence abstention: %s confidence=%d abstention_reason=%s",
            row.target_id,
            row.confidence,
            row.abstention_reason,
        )
    return result

"""Skill-event, context-pressure, commit-event, prompt-opt, and
learning-test queries (ENH-2775 split from the former flat
``history_reader.py``).

Backing tables: ``skill_events``, ``context_pressure_events``,
``commit_events``, ``prompt_opt_events``, ``learning_test_events`` — five
independent, low-traffic tables grouped into one submodule rather than five
one-function files (see the package docstring's grouping rule).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)
from little_loops.history_reader.models import (
    CommitEvent,
    ContextPressureEvent,
    LearningTestEvent,
    PromptOptEvent,
    SkillEvent,
)

__all__ = [
    "commit_issue_for_sha",
    "context_pressure_curve",
    "find_learning_test",
    "pressure_crossings",
    "pressure_summary",
    "prompt_opt_offer_rate",
    "recent_commit_events",
    "recent_learning_tests",
    "recent_prompt_opt_events",
    "recent_skill_events",
    "summarize_skills",
]


def recent_skill_events(
    skill_name: str | None = None,
    *,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[SkillEvent]:
    """Return recent skill events, newest first, incl. completion columns (ENH-2460)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, skill_name, args, exit_code, success, duration_ms "
            "FROM skill_events "
        )
        params: list[Any] = []
        if skill_name is not None:
            sql += "WHERE skill_name = ? "
            params.append(skill_name)
        sql += "ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_skill_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, SkillEvent) for row in rows]


def summarize_skills(
    since: str | None = None,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-skill rollup of invocations / completions / success rate (ENH-2460).

    ``success_rate`` and ``avg_duration_ms`` are computed over rows that carry
    a completion signal only (dispatch-only rows have ``success IS NULL`` and
    count toward ``invocations`` but not the rate). *since* is an ISO 8601
    lower bound on ``ts``. Sorted by invocation count, descending.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT skill_name, COUNT(*) AS invocations, "
            "COUNT(success) AS completions, "
            "SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successes, "
            "AVG(duration_ms) AS avg_duration_ms "
            "FROM skill_events "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ? "
            params.append(since)
        sql += "GROUP BY skill_name ORDER BY invocations DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: summarize_skills query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        completions = row["completions"] or 0
        successes = row["successes"] or 0
        result.append(
            {
                "skill_name": row["skill_name"],
                "invocations": row["invocations"],
                "completions": completions,
                "successes": successes,
                "success_rate": (successes / completions) if completions else None,
                "avg_duration_ms": row["avg_duration_ms"],
            }
        )
    return result


def context_pressure_curve(
    session_id: str,
    *,
    limit: int = 500,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[ContextPressureEvent]:
    """Return a session's context-pressure samples, oldest first (ENH-2507).

    Returns ``[]`` on any read failure or missing database (graceful degradation).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, session_id, used_pct, used_tokens_est, threshold_crossed, "
            "crossed_level, head_sha, branch FROM context_pressure_events "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: context_pressure_curve query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, ContextPressureEvent) for row in rows]


def pressure_crossings(
    session_id: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[ContextPressureEvent]:
    """Return a session's threshold-crossing rows, oldest first (ENH-2507).

    Returns ``[]`` on any read failure or missing database (graceful degradation).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, used_pct, used_tokens_est, threshold_crossed, "
            "crossed_level, head_sha, branch FROM context_pressure_events "
            "WHERE session_id = ? AND threshold_crossed = 1"
        )
        params: list[Any] = [session_id]
        if since is not None:
            sql += " AND ts >= ?"
            params.append(since)
        sql += " ORDER BY id ASC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: pressure_crossings query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, ContextPressureEvent) for row in rows]


def pressure_summary(
    session_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Return peak/average pct and sample count for a session (ENH-2507).

    Returns ``None`` when the session has no recorded pressure rows, the
    database is missing, or the read fails (graceful degradation).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS samples, MAX(used_pct) AS peak_pct, "
            "AVG(used_pct) AS avg_pct, MAX(used_tokens_est) AS peak_tokens_est "
            "FROM context_pressure_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: pressure_summary query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or not row["samples"]:
        return None
    return {
        "session_id": session_id,
        "samples": row["samples"],
        "peak_pct": row["peak_pct"],
        "avg_pct": row["avg_pct"],
        "peak_tokens_est": row["peak_tokens_est"],
    }


def recent_commit_events(
    *,
    branch: str | None = None,
    issue_id: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[CommitEvent]:
    """Return recent commit events, newest first, optionally filtered (ENH-2458)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, commit_sha, parent_sha, message, author, branch, issue_id, files_json "
            "FROM commit_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if branch is not None:
            clauses.append("branch = ?")
            params.append(branch)
        if issue_id is not None:
            clauses.append("issue_id = ?")
            params.append(issue_id)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_commit_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, CommitEvent) for row in rows]


def commit_issue_for_sha(
    commit_sha: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None:
    """Return the issue_id attributed to *commit_sha*, or None (FEAT-2867).

    Reverse of ``recent_commit_events(issue_id=...)`` — that function looks up
    commits *for* an issue; this looks up the issue *for* a commit. Needed by
    the revert-rate signal to resolve a ``git revert``'s "This reverts commit
    <sha>" lineage back to the issue that owned the reverted commit.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT issue_id FROM commit_events WHERE commit_sha = ? LIMIT 1",
            (commit_sha,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: commit_issue_for_sha query failed", exc_info=True)
        return None
    finally:
        conn.close()
    return row["issue_id"] if row is not None else None


def recent_prompt_opt_events(
    *,
    mode: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[PromptOptEvent]:
    """Return recent prompt-optimization offer/outcome rows, newest first (ENH-2498)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, session_id, mode, offered, bypass_reason, raw_len, "
            "optimized_len, optimized_text, accepted FROM prompt_opt_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if mode is not None:
            clauses.append("mode = ?")
            params.append(mode)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_prompt_opt_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, PromptOptEvent) for row in rows]


def prompt_opt_offer_rate(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Fraction of prompt_opt_events rows with ``offered = 1``, or None if empty (ENH-2498)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = "SELECT COUNT(*) AS total, SUM(CASE WHEN offered = 1 THEN 1 ELSE 0 END) AS offered "
        sql += "FROM prompt_opt_events "
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ?"
            params.append(since)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: prompt_opt_offer_rate query failed", exc_info=True)
        return None
    finally:
        conn.close()
    total = row["total"] or 0
    if not total:
        return None
    return (row["offered"] or 0) / total


def recent_learning_tests(
    *,
    status: str | None = None,
    limit: int = 20,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LearningTestEvent]:
    """Return recent Learning Test Registry mirror rows, newest first (ENH-2466)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, record_id, target, status, assertions_json, date, raw_output_path "
            "FROM learning_test_events "
        )
        params: list[Any] = []
        if status is not None:
            sql += "WHERE status = ? "
            params.append(status)
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_learning_tests query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, LearningTestEvent) for row in rows]


def find_learning_test(
    target: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> LearningTestEvent | None:
    """Return the mirror row for *target* (slugified to ``record_id``), or None (ENH-2466)."""
    from little_loops.issue_parser import slugify

    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT ts, record_id, target, status, assertions_json, date, raw_output_path "
            "FROM learning_test_events WHERE record_id = ?",
            (slugify(target),),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: find_learning_test query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_dataclass(row, LearningTestEvent)

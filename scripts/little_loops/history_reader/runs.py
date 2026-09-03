"""Test-run, orchestration-run, and loop-run queries (ENH-2775 split from the
former flat ``history_reader.py``).

Three adjacent clusters grouped into one submodule: ``test_run_events``
(``recent_test_runs``), ``orchestration_runs`` (``recent_orchestration_runs``,
``aggregate_orchestration_runs``, ``read_base_sha``, ``read_base_dirty``,
``read_prepatch_evidence``, the latter backed by the separate
``prepatch_evidence`` table but joined at the same per-issue-run grain), and
``loop_runs`` (``recent_loop_runs``, ``find_loop_run``, ``aggregate_loop_runs``).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)
from little_loops.history_reader.models import LoopRun, OrchestrationRun, RunEvent

__all__ = [
    "aggregate_loop_runs",
    "aggregate_orchestration_runs",
    "find_loop_run",
    "read_base_dirty",
    "read_base_sha",
    "read_prepatch_evidence",
    "recent_loop_runs",
    "recent_orchestration_runs",
    "recent_test_runs",
]


def recent_test_runs(
    *,
    branch: str | None = None,
    head_sha: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[RunEvent]:
    """Return recent test-run events, newest first, optionally filtered (ENH-2459)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT ts, ended_at, total, passed, failed, errored, skipped, duration_s, "
            "failing_names_json, env_label, head_sha, branch, command "
            "FROM test_run_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if branch is not None:
            clauses.append("branch = ?")
            params.append(branch)
        if head_sha is not None:
            clauses.append("head_sha = ?")
            params.append(head_sha)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_test_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, RunEvent) for row in rows]


_ORCHESTRATION_GROUP_COLUMNS: dict[str, str] = {
    "driver": "driver",
    "issue_id": "issue_id",
    "status": "status",
}


def recent_orchestration_runs(
    driver: str | None = None,
    issue_id: str | None = None,
    *,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[OrchestrationRun]:
    """Return recent per-issue orchestration outcomes, newest first (ENH-2492)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT run_id, driver, issue_id, status, failure_reason, duration_s, "
            "wave, pr_url, started_at, ended_at, head_sha, branch, base_sha, base_dirty "
            "FROM orchestration_runs "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if driver is not None:
            clauses.append("driver = ?")
            params.append(driver)
        if issue_id is not None:
            clauses.append("issue_id = ?")
            params.append(issue_id)
        if since is not None:
            clauses.append("COALESCE(ended_at, started_at) >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY COALESCE(ended_at, started_at) DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_orchestration_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, OrchestrationRun) for row in rows]


def aggregate_orchestration_runs(
    group_by: Literal["driver", "issue_id", "status"] = "driver",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Roll up run count, completion rate, and mean duration by a fixed dimension."""
    column = _ORCHESTRATION_GROUP_COLUMNS.get(group_by)
    if column is None:
        raise ValueError(
            f"aggregate_orchestration_runs: unsupported group_by {group_by!r}; "
            f"expected one of {sorted(_ORCHESTRATION_GROUP_COLUMNS)}"
        )
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {column} AS group_key, COUNT(*) AS runs, "  # noqa: S608 - fixed map
            "SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed, "
            "AVG(duration_s) AS avg_duration_s FROM orchestration_runs "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE COALESCE(ended_at, started_at) >= ? "
            params.append(since)
        sql += f"GROUP BY {column} ORDER BY runs DESC, group_key"  # noqa: S608 - fixed map
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: aggregate_orchestration_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()

    result: list[dict] = []
    for row in rows:
        runs = row["runs"] or 0
        completed = row["completed"] or 0
        result.append(
            {
                group_by: row["group_key"],
                "runs": runs,
                "completed": completed,
                "success_rate": completed / runs if runs else None,
                "avg_duration_s": row["avg_duration_s"],
            }
        )
    return result


def read_base_sha(
    issue_id: str,
    *,
    run_id: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> str | None:
    """Resolve the dequeue-time base commit SHA stamped for *issue_id* (ENH-2866).

    The stamp is the tree state an orchestrator took the work item from, written
    before anything mutated the tree or the issue file. It is advisory: a
    consumer that gets ``None`` back falls back to merge-base and should say
    which base it used.

    ``run_id`` identifies an exact ``orchestration_runs`` row via its
    ``UNIQUE(run_id, issue_id)`` key, but it is *optional* — it is a
    process-local ``uuid4().hex`` that is never exported to env, run-dir, or
    subprocess argv, so an out-of-process consumer cannot supply one. When it is
    omitted the most recent *stamped* row for the issue wins; the
    ``base_sha IS NOT NULL`` filter matters, or a later unstamped row would
    shadow an earlier stamped one.

    Returns:
        The stamped SHA, or ``None`` when the database is missing or
        unreadable, no matching row exists, or the row's ``base_sha`` is NULL
        (the orchestrator predates the stamp, opted out, or its ``git
        rev-parse`` failed). Never raises.
    """
    if not issue_id:
        return None
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        if run_id is not None:
            row = conn.execute(
                "SELECT base_sha FROM orchestration_runs WHERE run_id = ? AND issue_id = ?",
                (run_id, issue_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT base_sha FROM orchestration_runs "
                "WHERE issue_id = ? AND base_sha IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (issue_id,),
            ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: read_base_sha query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return row["base_sha"] or None


def read_base_dirty(
    issue_id: str,
    *,
    run_id: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> bool | None:
    """Resolve the dequeue-time ``base_dirty`` flag stamped for *issue_id* (ENH-3142).

    Additive sibling of :func:`read_base_sha`, mirroring its query dispatch
    exactly (``run_id``-present does an exact ``run_id + issue_id`` lookup;
    ``run_id``-absent takes the most recent *stamped* row). ``base_dirty`` is
    stored as ``int | None`` (SQLite has no native bool); this reader converts
    at the return boundary.

    Returns:
        ``True``/``False`` when a stamped row is found with a non-NULL
        ``base_dirty``, ``None`` when the database is missing or unreadable,
        no matching row exists, or the row's ``base_dirty`` is NULL. Never
        raises.
    """
    if not issue_id:
        return None
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        if run_id is not None:
            row = conn.execute(
                "SELECT base_dirty FROM orchestration_runs WHERE run_id = ? AND issue_id = ?",
                (run_id, issue_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT base_dirty FROM orchestration_runs "
                "WHERE issue_id = ? AND base_dirty IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (issue_id,),
            ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: read_base_dirty query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or row["base_dirty"] is None:
        return None
    return bool(row["base_dirty"])


def read_prepatch_evidence(
    issue_id: str,
    *,
    db: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Read the most recently persisted pre-patch-check bundle for *issue_id* (ENH-2997).

    ``prepatch_evidence`` rows are never upserted -- a run can guard multiple
    states, so this takes the most recent row by insertion order. This is the
    only surface ENH-2998's run_dir-less ``cli/harness.py`` consumer can
    discover a verdict by issue ID from.

    Returns:
        ``PrePatchEvidence.to_dict()`` (parsed from the stored JSON), or
        ``None`` when the database is missing or unreadable, no matching row
        exists, or the stored JSON fails to parse. Never raises.
    """
    if not issue_id:
        return None
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT evidence_json FROM prepatch_evidence "
            "WHERE issue_id = ? ORDER BY id DESC LIMIT 1",
            (issue_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: read_prepatch_evidence query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None:
        return None
    try:
        return json.loads(row["evidence_json"])
    except (TypeError, ValueError):
        logger.warning("history_reader: read_prepatch_evidence JSON decode failed", exc_info=True)
        return None


_LOOP_RUN_COLUMNS = (
    "run_id, loop_name, started_at, ended_at, final_state, iterations, "
    "terminated_by, error, evaluator_score, diagnostics_path, head_sha, branch, "
    "failure_terminal"
)


def recent_loop_runs(
    *,
    loop_name: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[LoopRun]:
    """Return recent loop-run summaries, newest first, optionally filtered (ENH-2463)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_LOOP_RUN_COLUMNS} FROM loop_runs "
        clauses: list[str] = []
        params: list[Any] = []
        if loop_name is not None:
            clauses.append("loop_name = ?")
            params.append(loop_name)
        if since is not None:
            clauses.append("COALESCE(ended_at, started_at) >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY COALESCE(ended_at, started_at) DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_loop_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, LoopRun) for row in rows]


def find_loop_run(run_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> LoopRun | None:
    """Return the single ``loop_runs`` row for *run_id*, or None if missing (ENH-2463)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            f"SELECT {_LOOP_RUN_COLUMNS} FROM loop_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: find_loop_run query failed", exc_info=True)
        return None
    finally:
        conn.close()
    return _row_to_dataclass(row, LoopRun) if row is not None else None


_LOOP_RUN_GROUP_COLUMNS: dict[str, str] = {
    "loop_name": "loop_name",
    "terminated_by": "terminated_by",
}


def aggregate_loop_runs(
    group_by: Literal["loop_name", "terminated_by"] = "loop_name",
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Roll up run count and mean iteration count by loop_name or terminated_by (ENH-2463)."""
    column = _LOOP_RUN_GROUP_COLUMNS.get(group_by)
    if column is None:
        raise ValueError(
            f"aggregate_loop_runs: unsupported group_by {group_by!r}; "
            f"expected one of {sorted(_LOOP_RUN_GROUP_COLUMNS)}"
        )
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            f"SELECT {column} AS group_key, COUNT(*) AS runs, "  # noqa: S608 - fixed map
            "AVG(iterations) AS avg_iterations FROM loop_runs "
        )
        params: list[Any] = []
        if since is not None:
            sql += "WHERE COALESCE(ended_at, started_at) >= ? "
            params.append(since)
        sql += f"GROUP BY {column} ORDER BY runs DESC, group_key"  # noqa: S608 - fixed map
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: aggregate_loop_runs query failed", exc_info=True)
        return []
    finally:
        conn.close()

    return [
        {
            group_by: row["group_key"],
            "runs": row["runs"] or 0,
            "avg_iterations": row["avg_iterations"],
        }
        for row in rows
    ]

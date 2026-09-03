"""The former flat module's unheadered tail: four independent event domains
(ENH-2775 split from the former flat ``history_reader.py``).

Grouped into one submodule because none of the four had its own region
comment in the flat file (unlike every other domain), each is small
(one table, a handful of functions), and the existing test file already
bundles them into a single grab-bag class (``TestNewEventReaders``):

* ``verdict_events`` (ENH-2504) — structured verifier outcomes
* ``advisor_consults`` (FEAT-3300) — advisor consult telemetry
* ``research_triage_events`` (ENH-2990) — re-refine skip-rate stats
* ``review_events`` (ENH-2512) — audit/review outcomes
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from little_loops.history_reader._base import (
    DEFAULT_DB_PATH,
    _connect_readonly,
    _row_to_dataclass,
    logger,
)

__all__ = [
    "AdvisorConsultRow",
    "AxisRates",
    "ConsultStats",
    "ResearchTriageStats",
    "ReviewEvent",
    "VerdictEvent",
    "consult_stats",
    "query_advisor_consults",
    "recent_review_events",
    "recent_verdict_events",
    "research_triage_stats",
    "review_velocity",
    "verdict_pass_rate",
]


@dataclass
class VerdictEvent:
    """A ``verdict_events`` row — one verifier invocation's structured outcome (ENH-2504).

    ``abstention_reason`` (ENH-230) carries the closed-enum tag from the
    producer when ``verdict`` is ``cannot_judge``. None for the pass/fail/
    implement outcomes. The SQL NULL vs Python ``None`` distinction
    is preserved end-to-end — readers MUST treat None distinctly from 0 when
    computing on ``findings_count`` or ``severity_counts``.
    """

    ts: str
    session_id: str | None
    verdict_kind: str
    target_kind: str | None
    target_id: str | None
    verdict: str
    severity_counts: str | None
    findings_count: int | None
    confidence: int | None
    abstention_reason: str | None
    head_sha: str | None
    branch: str | None


_VERDICT_EVENT_COLUMNS = (
    "ts, session_id, verdict_kind, target_kind, target_id, verdict, "
    "severity_counts, findings_count, confidence, abstention_reason, "
    "head_sha, branch"
)


def recent_verdict_events(
    *,
    verdict_kind: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[VerdictEvent]:
    """Return recent verifier verdicts, newest first, optionally filtered (ENH-2504)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_VERDICT_EVENT_COLUMNS} FROM verdict_events "
        clauses: list[str] = []
        params: list[Any] = []
        if verdict_kind is not None:
            clauses.append("verdict_kind = ?")
            params.append(verdict_kind)
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_verdict_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, VerdictEvent) for row in rows]


def verdict_pass_rate(
    *,
    verdict_kind: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Per-``verdict_kind`` pass-rate rollup, the readiness-trend query (ENH-2504).

    ``pass`` counts rows whose ``verdict`` is ``pass`` or ``implement`` (the two
    "proceed" outcomes across the nine verifiers). Sorted by invocation count,
    descending.

    ENH-230 adds a ``cannot_judge_count`` bucket so operators can see
    abstention volume without conflating it with pass/fail — rows where the
    gate's epistemic limit fired (criteria or evaluation context missing).
    Routing signal: fix the criteria or the context, not the verifier.

    ``success_rate`` keeps its existing definition (``successes /
    invocations``); a follow-up may add a decision-rate variant that excludes
    abstentions from the denominator, but the current contract is unchanged
    to avoid silent UI shifts. NULL ``findings_count`` is intentionally NOT
    coalesced to 0 in any bucket — abstention rows simply do not contribute
    to the success/failure count.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = (
            "SELECT verdict_kind, COUNT(*) AS invocations, "
            "SUM(CASE WHEN verdict IN ('pass', 'implement') THEN 1 ELSE 0 END) AS successes, "
            "SUM(CASE WHEN verdict = 'cannot_judge' THEN 1 ELSE 0 END) AS cannot_judge_count "
            "FROM verdict_events "
        )
        clauses: list[str] = []
        params: list[Any] = []
        if verdict_kind is not None:
            clauses.append("verdict_kind = ?")
            params.append(verdict_kind)
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "GROUP BY verdict_kind ORDER BY invocations DESC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: verdict_pass_rate query failed", exc_info=True)
        return []
    finally:
        conn.close()
    result: list[dict] = []
    for row in rows:
        invocations = row["invocations"] or 0
        successes = row["successes"] or 0
        cannot_judge_count = row["cannot_judge_count"] or 0
        result.append(
            {
                "verdict_kind": row["verdict_kind"],
                "invocations": invocations,
                "successes": successes,
                "cannot_judge_count": cannot_judge_count,
                "success_rate": (successes / invocations) if invocations else None,
            }
        )
    return result


@dataclass
class AdvisorConsultRow:
    """An ``advisor_consults`` row — one ``consult_for_trigger()`` invocation (FEAT-3300).

    ``outcome`` is ``"issued"`` or one of ``ConsultOutcome.skipped_reason``'s
    Literal values (``advisor.py``): ``disabled``, ``trigger_not_allowed``,
    ``budget_exhausted``, ``not_configured``, ``floor_violation``, ``failed``,
    ``timeout``. Token columns are NULL until a host surfaces usage.
    ``verdict_body`` is NULL unless the ``advisor.store_verdict_body`` opt-in
    was set at write time.
    """

    ts: str
    session_id: str | None
    task_key: str | None
    signal: str | None
    advisor_host: str | None
    advisor_model: str | None
    main_model: str | None
    floor_status: str | None
    outcome: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    confidence: float | None
    verdict_body: str | None


_ADVISOR_CONSULT_COLUMNS = (
    "ts, session_id, task_key, signal, advisor_host, advisor_model, main_model, "
    "floor_status, outcome, latency_ms, input_tokens, output_tokens, confidence, "
    "verdict_body"
)


def query_advisor_consults(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    limit: int = 500,
) -> list[AdvisorConsultRow]:
    """Return recent advisor consult rows, newest first, optionally filtered by *since* (FEAT-3300).

    Returns ``[]`` on any read failure or missing database (graceful degradation).
    """
    db_path = Path(db_path)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_ADVISOR_CONSULT_COLUMNS} FROM advisor_consults "
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ? "
            params.append(since)
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: query_advisor_consults query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, AdvisorConsultRow) for row in rows]


@dataclass
class ConsultStats:
    """Aggregate advisor-consult counts/tokens by signal (FEAT-3300)."""

    by_signal: dict[str, int]
    total: int
    total_tokens: int
    skipped: int


def consult_stats(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    days: int = 30,
) -> ConsultStats:
    """Aggregate advisor-consult counts and token totals by signal over the last *days* (FEAT-3300).

    Returns an all-zero :class:`ConsultStats` on any read failure, missing
    database, or empty table (graceful degradation).
    """
    db_path = Path(db_path)
    empty = ConsultStats(by_signal={}, total=0, total_tokens=0, skipped=0)
    conn = _connect_readonly(db_path)
    if conn is None:
        return empty
    try:
        since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute(
            "SELECT signal, outcome, input_tokens, output_tokens FROM advisor_consults "
            "WHERE ts >= ?",
            (since,),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: consult_stats query failed", exc_info=True)
        return empty
    finally:
        conn.close()

    by_signal: dict[str, int] = {}
    total = 0
    total_tokens = 0
    skipped = 0
    for row in rows:
        signal = row["signal"] or "unknown"
        by_signal[signal] = by_signal.get(signal, 0) + 1
        total += 1
        total_tokens += (row["input_tokens"] or 0) + (row["output_tokens"] or 0)
        if row["outcome"] != "issued":
            skipped += 1
    return ConsultStats(
        by_signal=by_signal, total=total, total_tokens=total_tokens, skipped=skipped
    )


@dataclass
class AxisRates:
    """Production vs coverage-only skip rates for one axis or the aggregate (ENH-2990)."""

    total: int
    covered: int
    stale: int
    production_rate: float
    coverage_only_rate: float


@dataclass
class ResearchTriageStats:
    """Live re-refine skip-rate figures for ``ll-issues research-triage`` (ENH-2990)."""

    first_refine_rows: int
    re_refine_rows: int
    program_design_unmet_count: int
    per_axis: dict[str, AxisRates]
    aggregate: AxisRates


def research_triage_stats(db_path: Path | str = DEFAULT_DB_PATH) -> ResearchTriageStats:
    """Aggregate ``research_triage_events`` into the ENH-2990 headline figures.

    Only rows with ``refined_at IS NOT NULL`` (re-refine invocations) feed the
    headline rates — the whole point of this issue is to isolate that
    population from first-refine rows, which can never carry a ``stale``
    verdict. Rows with ``reason = 'program_design_unmet'`` are excluded from
    the rates (BUG-3003's override says nothing about whether coverage or
    staleness would otherwise have passed); their count is reported
    separately via ``program_design_unmet_count``. Returns an all-zero
    :class:`ResearchTriageStats` on any read failure or missing/empty
    database (graceful degradation).

    Headline formulas (per axis, and in aggregate over all three axes):
    production skip rate = ``covered / total``; coverage-only counterfactual
    = ``(covered + stale) / total`` — the direct analogue of ENH-2971's
    33.7%-coverage-only vs 8.6%-production corpus figures, now measured on
    real invocations.

    Equivalent SQL, for re-deriving the same grouping without Python::

        SELECT axis, covered, reason, COUNT(*) FROM research_triage_events
        WHERE refined_at IS NOT NULL
          AND (reason IS NULL OR reason != 'program_design_unmet')
        GROUP BY axis, covered, reason;
    """
    empty_axis = AxisRates(total=0, covered=0, stale=0, production_rate=0.0, coverage_only_rate=0.0)
    empty = ResearchTriageStats(
        first_refine_rows=0,
        re_refine_rows=0,
        program_design_unmet_count=0,
        per_axis={},
        aggregate=empty_axis,
    )
    db_path = Path(db_path)
    conn = _connect_readonly(db_path)
    if conn is None:
        return empty
    try:
        first_refine_rows = conn.execute(
            "SELECT COUNT(*) FROM research_triage_events WHERE refined_at IS NULL"
        ).fetchone()[0]
        program_design_unmet_count = conn.execute(
            "SELECT COUNT(*) FROM research_triage_events "
            "WHERE refined_at IS NOT NULL AND reason = 'program_design_unmet'"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT axis, covered, reason, COUNT(*) as n FROM research_triage_events "
            "WHERE refined_at IS NOT NULL "
            "AND (reason IS NULL OR reason != 'program_design_unmet') "
            "GROUP BY axis, covered, reason"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: research_triage_stats query failed", exc_info=True)
        return empty
    finally:
        conn.close()

    per_axis_counts: dict[str, dict[str, int]] = {}
    re_refine_rows = 0
    for row in rows:
        n = row["n"]
        re_refine_rows += n
        counts = per_axis_counts.setdefault(row["axis"], {"total": 0, "covered": 0, "stale": 0})
        counts["total"] += n
        if row["covered"]:
            counts["covered"] += n
        elif row["reason"] == "stale":
            counts["stale"] += n

    def _rates(counts: dict[str, int]) -> AxisRates:
        total = counts["total"]
        covered = counts["covered"]
        stale = counts["stale"]
        return AxisRates(
            total=total,
            covered=covered,
            stale=stale,
            production_rate=covered / total if total else 0.0,
            coverage_only_rate=(covered + stale) / total if total else 0.0,
        )

    per_axis = {axis: _rates(counts) for axis, counts in per_axis_counts.items()}
    aggregate_counts = {"total": 0, "covered": 0, "stale": 0}
    for counts in per_axis_counts.values():
        for key in aggregate_counts:
            aggregate_counts[key] += counts[key]

    return ResearchTriageStats(
        first_refine_rows=first_refine_rows,
        re_refine_rows=re_refine_rows,
        program_design_unmet_count=program_design_unmet_count,
        per_axis=per_axis,
        aggregate=_rates(aggregate_counts),
    )


@dataclass
class ReviewEvent:
    """A ``review_events`` row — one audit/review invocation's structured outcome (ENH-2512)."""

    ts: str
    session_id: str | None
    reviewer_skill: str
    target_kind: str | None
    target_id: str | None
    severity_counts: str | None
    findings_count: int | None
    findings_json_summary: str | None
    verdict: str | None
    head_sha: str | None
    branch: str | None


_REVIEW_EVENT_COLUMNS = (
    "ts, session_id, reviewer_skill, target_kind, target_id, "
    "severity_counts, findings_count, findings_json_summary, verdict, head_sha, branch"
)


def recent_review_events(
    *,
    reviewer_skill: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    limit: int = 50,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[ReviewEvent]:
    """Return recent audit/review outcomes, newest first, optionally filtered (ENH-2512)."""
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = f"SELECT {_REVIEW_EVENT_COLUMNS} FROM review_events "
        clauses: list[str] = []
        params: list[Any] = []
        if reviewer_skill is not None:
            clauses.append("reviewer_skill = ?")
            params.append(reviewer_skill)
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if since is not None:
            clauses.append("ts >= ?")
            params.append(since)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + " "
        sql += "ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: recent_review_events query failed", exc_info=True)
        return []
    finally:
        conn.close()
    return [_row_to_dataclass(row, ReviewEvent) for row in rows]


def review_velocity(
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Weekly rollup of ``severity_counts`` totals across all reviews (ENH-2512).

    Buckets rows by ISO week (``strftime('%Y-%W', ts)``) and sums each
    severity bucket (``p0``/``p1``/``p2``/``info``) found in the JSON-encoded
    ``severity_counts`` column. Rows with a null/unparseable
    ``severity_counts`` contribute zero to every bucket but still count
    toward ``reviews``. Sorted by week ascending.
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return []
    try:
        sql = "SELECT ts, severity_counts FROM review_events "
        params: list[Any] = []
        if since is not None:
            sql += "WHERE ts >= ? "
            params.append(since)
        sql += "ORDER BY ts ASC"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: review_velocity query failed", exc_info=True)
        return []
    finally:
        conn.close()

    weeks: dict[str, dict[str, int]] = {}
    for row in rows:
        ts = row["ts"] or ""
        try:
            week = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-W%W")
        except ValueError:
            continue
        bucket = weeks.setdefault(week, {"reviews": 0, "p0": 0, "p1": 0, "p2": 0, "info": 0})
        bucket["reviews"] += 1
        raw = row["severity_counts"]
        if not raw:
            continue
        try:
            counts = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(counts, dict):
            continue
        for severity in ("p0", "p1", "p2", "info"):
            value = counts.get(severity)
            if isinstance(value, int):
                bucket[severity] += value

    return [{"week": week, **weeks[week]} for week in sorted(weeks)]

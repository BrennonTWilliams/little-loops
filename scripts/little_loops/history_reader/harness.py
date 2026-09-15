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
from collections.abc import Iterable
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
    "BaselineConditions",
    "BaselineKey",
    "BaselineResult",
    "HarnessEvent",
    "HighConfidenceAbstention",
    "admissions_by_reason",
    "authoritative_attempt",
    "authoritative_attempts",
    "baseline_for",
    "check_high_confidence_abstention",
    "harness_event_by_id",
    "harness_eval_abstention_rate",
    "harness_eval_pass_rate",
    "recent_harness_events",
]

# ENH-3408: single source of truth for "this row is the one that counts" — a
# bare boolean SQL expression spliced into every counting site (pass rate,
# abstention rate, authoritative_attempt(s)) via f-string, mirroring
# ``usage.py``'s ``_WASTED_RUN_PREDICATE`` pattern. A retry chain always
# collapses to exactly one row matching this predicate per (cell_key,
# repetition); pre-v49 rows (all three columns NULL) satisfy it too.
_AUTHORITATIVE_PREDICATE = "superseded_by IS NULL"


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
    # ENH-3435 v50 baseline-condition columns (trailing-default, same pattern
    # as the v49 run-model columns above).
    timeout_s: int | None = None
    host_cli: str | None = None
    subject_model: str | None = None
    input_hash: str | None = None
    conditions_fp: str | None = None
    # ENH-3464 v51 efficiency-vector columns (trailing-default, same pattern
    # as the v49/v50 columns above). Reporting only -- never read by a
    # pass/fail gate. tool_calls counts top-level tool_use blocks only (SKILL
    # path); always None on the PROMPT/DSL path and on CMD/MCP runners.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    tool_calls: int | None = None


_HARNESS_EVENT_COLUMNS = (
    "id, ts, runner, target, exit_code, semantic_verdict, semantic_passed, timed_out, "
    "duration_ms, head_sha, branch, parent_id, semantic_prompt, semantic_confidence, "
    "semantic_reason, semantic_evidence, semantic_model, "
    "target_content_hash, target_path, dirty, "
    "cell_key, repetition, attempt_kind, continuations, superseded_by, "
    "timeout_s, host_cli, subject_model, input_hash, conditions_fp, "
    "input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, tool_calls"
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
            f"WHERE cell_key = ? AND repetition = ? AND {_AUTHORITATIVE_PREDICATE} "
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
            f"WHERE cell_key = ? AND {_AUTHORITATIVE_PREDICATE} "
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


# ---------------------------------------------------------------------------
# ENH-3435: the unmutated-arm baseline reader. A baseline *is* the set of
# authoritative harness_events rows for one content identity under matching
# conditions — there is no second store (issue Program Design, Option A).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineKey:
    """The baseline match key: what was measured, not when or where.

    ``(runner, target, input_hash, target_content_hash)`` — deliberately
    **without** ``head_sha`` (provenance only) and without ``cell_key`` (both
    arms of a compare share it). ``input_hash`` is ``""`` for runners whose
    target *is* the input (``cmd``/``prompt``); a canonical hash of
    ``runner_args`` for ``skill`` and of the ``--args`` JSON for ``mcp``.
    """

    runner: str
    target: str
    input_hash: str
    target_content_hash: str


@dataclass(frozen=True)
class BaselineConditions:
    """Conditions a baseline must have been measured under (ENH-3435).

    The readable fields are provenance and post-hoc query surface; exact
    matching runs through ``conditions_fp`` alone (never NULL on
    baseline-eligible rows, so pre-migration rows are excluded by
    construction and no NULL-vs-NULL vacuous match exists). ``n`` is a
    threshold, not a matched field — rows don't carry n, so reuse requires
    at least n matching rows and uses the most recent n.
    """

    n: int
    conditions_fp: str
    semantic_prompt: str | None = None
    semantic_model: str | None = None
    subject_model: str | None = None
    timeout_s: int | None = None
    host_cli: str | None = None


@dataclass
class BaselineResult:
    """One resolved baseline: n authoritative rows, tallied (ENH-3435).

    ``source`` is read-side provenance set by the caller/reader — a stored
    row always describes a measurement, so it is never persisted.
    ``subject_model``/``dirty_rows`` come from the rows themselves and drive
    the ``subject model not pinned`` / ``measured on a dirty tree`` honesty
    notes on the reported delta.
    """

    key: BaselineKey
    conditions: BaselineConditions
    tally: Any  # cli.harness.SampleTally — deferred type to avoid a cycle
    attempt_ids: list[int]
    head_sha: str | None
    measured_at: str
    subject_model: str | None = None
    dirty_rows: bool = False
    source: str = "reused"


def _rc_from_event(event: HarnessEvent) -> int:
    """Reconstruct one row's `_grade()` exit code (ENH-3435).

    Mirrors the run-time banding: timeout or a missing process exit code is
    an infra error (2); a judge abstention (NULL ``semantic_passed`` with a
    verdict) is 3; otherwise ``semantic_passed`` decides pass (0) / fail (1).
    """
    if event.timed_out:
        return 2
    if event.exit_code is None:
        return 2
    if event.semantic_passed is None:
        return 3 if event.semantic_verdict is not None else 2
    return 0 if event.semantic_passed else 1


def baseline_for(
    db_path: Path | str,
    *,
    runner: str,
    target: str,
    input_hash: str,
    target_content_hash: str,
    conditions: BaselineConditions,
) -> BaselineResult | None:
    """Return the baseline for one content identity under matching conditions, or None.

    ENH-3435. Filters on ``(runner, target, input_hash, target_content_hash,
    conditions_fp)`` — **not** ``cell_key`` (both arms of a compare share it)
    and **not** ``head_sha`` (after a loop commits an accepted candidate, a
    head-keyed lookup would miss the candidate rows just written and re-pay
    them). Authoritative rows only. Returns None when fewer than ``n`` rows
    match (partial) or none of them is graded (no rate can be computed); more
    than n matching rows reuse the most recent n.
    """
    conn = _connect_readonly(Path(db_path))
    if conn is None:
        return None
    try:
        sql = (
            f"SELECT {_HARNESS_EVENT_COLUMNS} FROM harness_events "
            f"WHERE runner = ? AND target = ? AND input_hash = ? "
            f"AND target_content_hash = ? AND conditions_fp = ? "
            f"AND {_AUTHORITATIVE_PREDICATE} "
            "ORDER BY id DESC LIMIT ?"
        )
        rows = conn.execute(
            sql,
            (
                runner,
                target,
                input_hash,
                target_content_hash,
                conditions.conditions_fp,
                conditions.n,
            ),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: baseline_for query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if len(rows) < conditions.n:
        return None
    events = [_row_to_dataclass(row, HarnessEvent) for row in reversed(rows)]

    # Deferred import: little_loops.cli.harness imports this module at load
    # time, so importing SampleTally at module scope here would be circular.
    from little_loops.cli.harness import SampleTally
    from little_loops.stats import wilson_ci

    tally = SampleTally(requested=conditions.n)
    for event in events:
        tally.record(_rc_from_event(event))
    if tally.graded == 0:
        return None
    if tally.passed > 0 or tally.graded > 0:
        tally.ci_lo, tally.ci_hi = wilson_ci(tally.passed, tally.graded)
    return BaselineResult(
        key=BaselineKey(
            runner=runner,
            target=target,
            input_hash=input_hash,
            target_content_hash=target_content_hash,
        ),
        conditions=conditions,
        tally=tally,
        attempt_ids=[e.id for e in events if e.id is not None],
        head_sha=events[-1].head_sha,
        measured_at=events[-1].ts,
        subject_model=next((e.subject_model for e in events if e.subject_model), None),
        dirty_rows=any(e.dirty for e in events),
        source="reused",
    )


def harness_eval_pass_rate(
    target: str,
    *,
    since: str | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> float | None:
    """Return the semantic-verdict pass fraction for *target*, or None if no scored rows (ENH-2741).

    Counts every non-superseded row with a non-NULL ``semantic_passed``
    (ENH-3408: a retry chain contributes its surviving attempt's verdict
    once, not one row per attempt). ``cli/harness.py`` sets
    ``semantic_passed`` on every non-abstained run regardless of whether
    ``--semantic`` was supplied (exit-code-only runs included), so the
    denominator is *all non-abstained authoritative runs* for *target*, not
    only the ``check_semantic`` verdict path (ENH-3223).
    """
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        sql = (
            "SELECT SUM(CASE WHEN semantic_passed = 1 THEN 1 ELSE 0 END) AS successes, "
            "COUNT(semantic_passed) AS scored "
            f"FROM harness_events WHERE target = ? AND {_AUTHORITATIVE_PREDICATE}"
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
    non-superseded row with a non-NULL ``semantic_verdict`` (pass, fail, and
    abstain; ENH-3408 excludes superseded rows so this denominator converges
    on the same population as ``harness_eval_pass_rate()``'s), unlike
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
            f"FROM harness_events WHERE target = ? AND {_AUTHORITATIVE_PREDICATE}"
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


def admissions_by_reason(db_path: Path | str, attempt_ids: Iterable[int]) -> dict[str, int]:
    """Return admission counts by ``reason`` for the given ``attempt_id``s (ENH-3408).

    Scoped to a caller-supplied set of authoritative attempt ids (a target's
    windowed history, or one ``cmd_dsl`` invocation's written ids) rather than
    a global tail, since ``harness_admissions`` has no target/run column of
    its own. Returns ``{}`` for an empty *attempt_ids* or when none match.
    """
    ids = list(attempt_ids)
    if not ids:
        return {}
    db_path = Path(db_path)
    conn = _connect_readonly(db_path)
    if conn is None:
        return {}
    try:
        placeholders = ", ".join("?" for _ in ids)
        sql = (
            "SELECT reason, COUNT(*) AS n FROM harness_admissions "
            f"WHERE attempt_id IN ({placeholders}) GROUP BY reason"
        )
        rows = conn.execute(sql, ids).fetchall()
    except sqlite3.Error:
        logger.warning("history_reader: admissions_by_reason query failed", exc_info=True)
        return {}
    finally:
        conn.close()
    return {row["reason"]: row["n"] for row in rows}


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

"""Agent-quality signals over ``.ll/history.db`` (FEAT-3183).

Computes fix-rate, correction rate, cost per issue, tokens per issue, and
retry inflation, each as a time series of windows rather than a point-in-time
total, so a trend can be told apart from a snapshot. Read-only against
``.ll/history.db``; no network access, no LLM calls.

Fix-rate, correction rate, cost per issue, and tokens per issue share
``rework.py``'s ``(calendar month, orchestrator)`` windows via
``analyze_rework()`` and ``_utils.orchestrator_labels()`` so the two reports
read side by side. Retry inflation buckets by ``(calendar month, loop_name)``
instead — ``loop_runs`` has no ``issue_id`` column, and the two-hop join
needed to recover one (``loop_runs.run_id -> usage_events.run_id ->
issue_sessions.session_id -> issue_num``) is only 27% reachable on this
repo's own database (see the issue's Retry-inflation attribution section).

Resolved attribution decisions (restated here per the issue's Open Decisions):

1. A ``usage_events`` row whose session touches more than one issue (via the
   ``issue_sessions`` view) has its cost and tokens split evenly across those
   issues. The same even-split is applied to ``user_corrections`` rows for the
   same reason: duplicating into every touched issue would inflate the
   project-wide total, and attributing to just one issue is arbitrary when the
   session touched several.
2. Correction rate is per closed issue, not per session: ``user_corrections``
   carries only ``session_id`` while every other metric buckets by issue, so a
   per-session denominator would count a different unit than its numerator.
3. Cost verdicts (not values) are suppressed below ``LOW_COVERAGE_THRESHOLD``
   priced-row coverage in a window; tokens per issue has no such gate because
   it needs no pricing-table lookup.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.history_reader import _connect_readonly
from little_loops.issue_history._utils import MetricDefinition, classify_verdict, month_key
from little_loops.issue_history._utils import orchestrator_labels as _orchestrator_labels
from little_loops.issue_history.rework import (
    LOW_COVERAGE_THRESHOLD,
    MIN_SAMPLE_SIZE,
    UNATTRIBUTED_LABEL,
    ReworkAnalysis,
    ReworkWindow,
    analyze_rework,
)
from little_loops.session_store import DEFAULT_DB_PATH

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)

_STANDARD_NOTES = (
    "Orchestrator attribution is correlational, not causal.",
    "Most issues have no orchestration_runs row and fall into `unattributed`.",
    "Cost is attributed via issue_sessions; multi-issue sessions are split evenly.",
    "Cost verdicts are suppressed below 50% priced coverage; tokens per issue is "
    "unaffected by pricing-table gaps.",
    "Retry inflation buckets by loop, not orchestrator -- loop_runs has no issue_id.",
)


@dataclass
class QualityMetric:
    """One metric's value, sample size, and trend verdict for a window."""

    name: str
    value: float | None
    sample_size: int
    verdict: str | None
    baseline_period: str | None
    insufficient_history: bool
    coverage: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "sample_size": self.sample_size,
            "verdict": self.verdict,
            "baseline_period": self.baseline_period,
            "insufficient_history": self.insufficient_history,
            "coverage": self.coverage,
        }


@dataclass
class QualityWindow:
    """Quality metrics for one (calendar month, orchestrator) bucket."""

    period: str
    orchestrator: str
    closed_count: int
    metrics: dict[str, QualityMetric]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "orchestrator": self.orchestrator,
            "closed_count": self.closed_count,
            "metrics": {name: m.to_dict() for name, m in self.metrics.items()},
        }


@dataclass
class RetryWindow:
    """Retry-inflation signal for one (calendar month, loop_name) bucket."""

    period: str
    loop_name: str
    run_count: int
    mean_iterations: float | None
    verdict: str | None
    insufficient_history: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "loop_name": self.loop_name,
            "run_count": self.run_count,
            "mean_iterations": self.mean_iterations,
            "verdict": self.verdict,
            "insufficient_history": self.insufficient_history,
        }


@dataclass
class QualityAnalysis:
    """Time series of quality windows plus the interpretive notes callers must show."""

    windows: list[QualityWindow] = field(default_factory=list)
    retry_windows: list[RetryWindow] = field(default_factory=list)
    definitions: list[MetricDefinition] = field(default_factory=list)
    min_sample_size: int = MIN_SAMPLE_SIZE
    notes: tuple[str, ...] = field(default_factory=lambda: tuple(_STANDARD_NOTES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "windows": [w.to_dict() for w in self.windows],
            "retry_windows": [r.to_dict() for r in self.retry_windows],
            "definitions": [d.to_dict() for d in self.definitions],
            "min_sample_size": self.min_sample_size,
            "notes": list(self.notes),
        }


def _fingerprint(content: str) -> str:
    """Stable 16-char hex fingerprint, matching evolution.py's retirement convention."""
    return hashlib.sha256(content[:512].encode()).hexdigest()[:16]


def _definitions(min_sample: int) -> list[MetricDefinition]:
    verdict_band = "more than 20% vs the earliest same-orchestrator window"
    return [
        MetricDefinition(
            name="fix_rate",
            unit="ratio",
            window="calendar month x orchestrator",
            denominator="closed issues in window",
            formula="1 - rework_share (rework_share = max(reopen_rate, revert_rate), "
            "from ll-history rework)",
            min_sample=min_sample,
            verdict_band=verdict_band,
            caveats=(
                "issue_events dedups per (issue_num, transition), so a second "
                "done->open->done cycle collapses into the first; fix-rate is "
                "biased optimistic.",
            ),
        ),
        MetricDefinition(
            name="correction_rate",
            unit="corrections per closed issue",
            window="calendar month x orchestrator",
            denominator="closed issues in window",
            formula="non-retired user_corrections attributed via issue_sessions "
            "(split evenly across multi-issue sessions) / closed issues",
            min_sample=min_sample,
            verdict_band=verdict_band,
            caveats=(
                "user_corrections has no issue_id column; attribution requires a "
                "session_id -> issue_sessions hop, so sessions with no recorded "
                "issue association are excluded from the numerator.",
            ),
        ),
        MetricDefinition(
            name="cost_per_issue",
            unit="usd",
            window="calendar month x orchestrator",
            denominator="closed issues in window",
            formula="sum(usage_events.cost_usd, split evenly across multi-issue "
            "sessions) / closed issues",
            min_sample=min_sample,
            verdict_band=f"{verdict_band}; suppressed below "
            f"{LOW_COVERAGE_THRESHOLD:.0%} priced coverage",
            caveats=(
                "cost_usd is null for any model absent from pricing.MODEL_PRICING; "
                "the coverage gate withholds the verdict, not the number, below "
                f"{LOW_COVERAGE_THRESHOLD:.0%} priced share.",
                "cost_usd is frozen at write time from the then-current pricing "
                "table, so a pricing-table change alone moves the trend.",
            ),
        ),
        MetricDefinition(
            name="tokens_per_issue",
            unit="tokens",
            window="calendar month x orchestrator",
            denominator="closed issues in window",
            formula="sum(input+output+cache_read+cache_creation tokens, split "
            "evenly across multi-issue sessions) / closed issues",
            min_sample=min_sample,
            verdict_band=verdict_band,
            caveats=("Always computable -- no pricing-table dependency, unlike cost.",),
        ),
    ]


def _load_closed_issues(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """One row per closed issue: issue_num, issue_id, done_ts."""
    try:
        rows = conn.execute(
            "SELECT issue_num, issue_id, ts FROM issue_events "
            "WHERE transition = 'done' AND issue_num IS NOT NULL AND issue_id IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("agent_quality: issue_events query failed", exc_info=True)
        return []
    return [
        {"issue_num": row["issue_num"], "issue_id": row["issue_id"], "done_ts": row["ts"]}
        for row in rows
    ]


def _session_issue_map(conn: sqlite3.Connection) -> dict[str, set[int]]:
    """session_id -> the set of issue_num values it touched, via the issue_sessions view."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT session_id, issue_num FROM issue_sessions "
            "WHERE session_id IS NOT NULL AND issue_num IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("agent_quality: issue_sessions query failed", exc_info=True)
        return {}
    result: dict[str, set[int]] = {}
    for row in rows:
        result.setdefault(row["session_id"], set()).add(row["issue_num"])
    return result


def _load_retirement_fingerprints(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute("SELECT topic_fingerprint FROM correction_retirements").fetchall()
    except sqlite3.Error:
        return set()
    return {row["topic_fingerprint"] for row in rows}


def _correction_totals(
    conn: sqlite3.Connection,
    session_issues: dict[str, set[int]],
    issue_window: dict[int, tuple[str, str]],
    retirements: set[str],
) -> dict[tuple[str, str], float]:
    try:
        rows = conn.execute(
            "SELECT session_id, content FROM user_corrections WHERE session_id IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("agent_quality: user_corrections query failed", exc_info=True)
        return {}
    totals: dict[tuple[str, str], float] = {}
    for row in rows:
        content = row["content"] or ""
        if _fingerprint(content) in retirements:
            continue
        issues = session_issues.get(row["session_id"])
        if not issues:
            continue
        share = 1.0 / len(issues)
        for issue_num in issues:
            key = issue_window.get(issue_num)
            if key is None:
                continue
            totals[key] = totals.get(key, 0.0) + share
    return totals


def _usage_totals(
    conn: sqlite3.Connection,
    session_issues: dict[str, set[int]],
    issue_window: dict[int, tuple[str, str]],
) -> dict[tuple[str, str], dict[str, float]]:
    try:
        rows = conn.execute(
            "SELECT session_id, cost_usd, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens "
            "FROM usage_events WHERE session_id IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("agent_quality: usage_events query failed", exc_info=True)
        return {}
    totals: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        issues = session_issues.get(row["session_id"])
        if not issues:
            continue
        n = len(issues)
        tokens = (
            (row["input_tokens"] or 0)
            + (row["output_tokens"] or 0)
            + (row["cache_read_input_tokens"] or 0)
            + (row["cache_creation_input_tokens"] or 0)
        )
        cost = row["cost_usd"]
        for issue_num in issues:
            key = issue_window.get(issue_num)
            if key is None:
                continue
            bucket = totals.setdefault(
                key, {"cost": 0.0, "tokens": 0.0, "priced_rows": 0.0, "total_rows": 0.0}
            )
            bucket["tokens"] += tokens / n
            bucket["total_rows"] += 1.0 / n
            if cost is not None:
                bucket["cost"] += cost / n
                bucket["priced_rows"] += 1.0 / n
    return totals


def _fix_rate_metrics(rework: ReworkAnalysis) -> dict[tuple[str, str], QualityMetric]:
    """Fix-rate verdicts are derived from rework_share's own trend (see module docstring):

    fix_rate = 1 - rework_share, and rework_share improving (going down) is exactly
    fix_rate improving (going up), so the verdict is computed on rework_share directly
    rather than re-deriving it from the nonlinearly-transformed fix_rate value.
    """
    by_orchestrator: dict[str, list[ReworkWindow]] = {}
    for rw in rework.windows:
        by_orchestrator.setdefault(rw.orchestrator, []).append(rw)

    result: dict[tuple[str, str], QualityMetric] = {}
    for group in by_orchestrator.values():
        group.sort(key=lambda w: w.period)
        valid = [w for w in group if not w.insufficient_history]
        baseline = valid[0] if valid else None
        for rw in group:
            key = (rw.period, rw.orchestrator)
            if rw.insufficient_history:
                result[key] = QualityMetric(
                    "fix_rate", None, rw.closed_count, None, None, True, None
                )
                continue
            assert rw.rework_share is not None
            fix_rate = 1 - rw.rework_share
            if rw is baseline:
                result[key] = QualityMetric(
                    "fix_rate", fix_rate, rw.closed_count, "stable", None, False, None
                )
            else:
                assert baseline is not None and baseline.rework_share is not None
                verdict = classify_verdict(rw.rework_share, baseline.rework_share)
                result[key] = QualityMetric(
                    "fix_rate", fix_rate, rw.closed_count, verdict, baseline.period, False, None
                )
    return result


def _rate_metrics(
    name: str,
    numerator_by_key: dict[tuple[str, str], float],
    window_closed: dict[tuple[str, str], int],
    min_sample: int,
    coverage_by_key: dict[tuple[str, str], float] | None = None,
) -> dict[tuple[str, str], QualityMetric]:
    """A generic lower-is-better per-closed-issue rate, windowed like fix-rate."""
    periods_by_orchestrator: dict[str, list[tuple[str, str]]] = {}
    for key in window_closed:
        periods_by_orchestrator.setdefault(key[1], []).append(key)

    result: dict[tuple[str, str], QualityMetric] = {}
    for keys in periods_by_orchestrator.values():
        keys.sort(key=lambda k: k[0])
        valid_keys = [k for k in keys if window_closed[k] >= min_sample]
        baseline_key = valid_keys[0] if valid_keys else None
        for key in keys:
            closed_count = window_closed[key]
            coverage = coverage_by_key.get(key) if coverage_by_key is not None else None
            if closed_count < min_sample:
                result[key] = QualityMetric(name, None, closed_count, None, None, True, coverage)
                continue
            value = numerator_by_key.get(key, 0.0) / closed_count
            if key == baseline_key:
                verdict: str | None = "stable"
                baseline_period = None
            else:
                assert baseline_key is not None
                baseline_value = (
                    numerator_by_key.get(baseline_key, 0.0) / window_closed[baseline_key]
                )
                verdict = classify_verdict(value, baseline_value)
                baseline_period = baseline_key[0]
            if coverage is not None and coverage < LOW_COVERAGE_THRESHOLD:
                verdict = None
            result[key] = QualityMetric(
                name, value, closed_count, verdict, baseline_period, False, coverage
            )
    return result


def _compute_retry_windows(conn: sqlite3.Connection, min_sample: int) -> list[RetryWindow]:
    try:
        rows = conn.execute(
            "SELECT loop_name, started_at, ended_at, iterations FROM loop_runs "
            "WHERE iterations IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("agent_quality: loop_runs query failed", exc_info=True)
        return []

    groups: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        ts = row["started_at"] or row["ended_at"]
        key = (month_key(ts), row["loop_name"])
        groups.setdefault(key, []).append(row["iterations"])

    by_loop: dict[str, list[tuple[str, str]]] = {}
    for key in groups:
        by_loop.setdefault(key[1], []).append(key)

    means = {key: sum(vals) / len(vals) for key, vals in groups.items()}

    windows: list[RetryWindow] = []
    for loop_name, keys in by_loop.items():
        keys.sort(key=lambda k: k[0])
        valid_keys = [k for k in keys if len(groups[k]) >= min_sample]
        baseline_key = valid_keys[0] if valid_keys else None
        for key in keys:
            run_count = len(groups[key])
            if run_count < min_sample:
                windows.append(RetryWindow(key[0], loop_name, run_count, None, None, True))
                continue
            mean_iterations = means[key]
            if key == baseline_key:
                verdict = "stable"
            else:
                assert baseline_key is not None
                verdict = classify_verdict(mean_iterations, means[baseline_key])
            windows.append(
                RetryWindow(key[0], loop_name, run_count, mean_iterations, verdict, False)
            )
    windows.sort(key=lambda w: (w.period, w.loop_name))
    return windows


def analyze_agent_quality(
    issues: list[IssueInfo],
    *,
    db: Path | str = DEFAULT_DB_PATH,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> QualityAnalysis:
    """Compute agent-quality signals as a time series of windows.

    Args:
        issues: All on-disk issues (any status) — forwarded to
            :func:`analyze_rework` to resolve `supersedes:` edges for the
            fix-rate signal.
        db: Path to ``.ll/history.db``.
        min_sample: Minimum closed issues (or loop runs, for retry inflation)
            per window before a rate is reported.

    Returns:
        QualityAnalysis with empty windows if the DB is missing/empty.
    """
    definitions = _definitions(min_sample)
    empty = QualityAnalysis(min_sample_size=min_sample, definitions=definitions)
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return empty

    try:
        # Retry inflation buckets by (month, loop_name), not orchestrator (see module
        # docstring) -- it must not depend on any closed-issue/orchestrator data below.
        retry_windows = _compute_retry_windows(conn, min_sample)

        rework = analyze_rework(issues, db=db_path, min_sample=min_sample)
        if not rework.windows:
            return QualityAnalysis(
                retry_windows=retry_windows,
                definitions=definitions,
                min_sample_size=min_sample,
            )

        fix_rate_metrics = _fix_rate_metrics(rework)
        window_closed = {(rw.period, rw.orchestrator): rw.closed_count for rw in rework.windows}

        closed = _load_closed_issues(conn)
        orch_labels = _orchestrator_labels(conn, {c["issue_id"] for c in closed})
        issue_window: dict[int, tuple[str, str]] = {}
        for c in closed:
            period = month_key(c["done_ts"])
            orchestrator = orch_labels.get(c["issue_id"], UNATTRIBUTED_LABEL)
            issue_window[c["issue_num"]] = (period, orchestrator)

        session_issues = _session_issue_map(conn)
        retirements = _load_retirement_fingerprints(conn)
        correction_totals = _correction_totals(conn, session_issues, issue_window, retirements)
        usage_totals = _usage_totals(conn, session_issues, issue_window)

        cost_numerator = {key: v["cost"] for key, v in usage_totals.items()}
        tokens_numerator = {key: v["tokens"] for key, v in usage_totals.items()}
        coverage_by_key = {
            key: (v["priced_rows"] / v["total_rows"] if v["total_rows"] else 0.0)
            for key, v in usage_totals.items()
        }

        correction_metrics = _rate_metrics(
            "correction_rate", correction_totals, window_closed, min_sample
        )
        cost_metrics = _rate_metrics(
            "cost_per_issue", cost_numerator, window_closed, min_sample, coverage_by_key
        )
        tokens_metrics = _rate_metrics(
            "tokens_per_issue", tokens_numerator, window_closed, min_sample
        )

        windows: list[QualityWindow] = []
        for rw in rework.windows:
            key = (rw.period, rw.orchestrator)
            metrics = {
                "fix_rate": fix_rate_metrics[key],
                "correction_rate": correction_metrics[key],
                "cost_per_issue": cost_metrics[key],
                "tokens_per_issue": tokens_metrics[key],
            }
            windows.append(
                QualityWindow(
                    period=rw.period,
                    orchestrator=rw.orchestrator,
                    closed_count=rw.closed_count,
                    metrics=metrics,
                )
            )

        return QualityAnalysis(
            windows=windows,
            retry_windows=retry_windows,
            definitions=definitions,
            min_sample_size=min_sample,
        )
    finally:
        conn.close()


def _format_metric_line(label: str, unit_suffix: str, metric: QualityMetric) -> str:
    if metric.insufficient_history:
        return f"  {label}    insufficient history"
    assert metric.value is not None
    if metric.verdict is None:
        coverage_note = (
            f" (no verdict -- priced coverage {metric.coverage:.2f})"
            if (metric.coverage is not None)
            else " (no verdict)"
        )
        trend = coverage_note
    elif metric.verdict == "stable" or metric.baseline_period is None:
        trend = f" ({metric.verdict})"
    else:
        trend = f" ({metric.verdict} vs {metric.baseline_period})"
    return f"  {label}    {metric.value:.2f}{unit_suffix}{trend}"


_METRIC_LABELS: tuple[tuple[str, str, str], ...] = (
    ("fix_rate", "fix-rate", ""),
    ("correction_rate", "correction rate", " /closed issue"),
    ("cost_per_issue", "cost per issue", " usd"),
    ("tokens_per_issue", "tokens per issue", " tokens"),
)


def format_agent_quality_text(analysis: QualityAnalysis) -> str:
    """Format agent-quality analysis as a plain-text report."""
    lines: list[str] = ["Agent Quality Report", "=" * 21, ""]
    if not analysis.windows and not analysis.retry_windows:
        lines.append("No closed-issue history found.")
        return "\n".join(lines)

    for w in analysis.windows:
        lines.append(f"{w.period}  [{w.orchestrator}]  closed={w.closed_count}")
        for key, label, unit_suffix in _METRIC_LABELS:
            lines.append(_format_metric_line(label, unit_suffix, w.metrics[key]))
        lines.append("")

    if analysis.retry_windows:
        lines.append("Retry inflation (by month x loop)")
        for r in analysis.retry_windows:
            if r.insufficient_history:
                lines.append(f"  {r.period} / {r.loop_name}   insufficient history")
                continue
            assert r.mean_iterations is not None
            lines.append(
                f"  {r.period} / {r.loop_name}   "
                f"{r.mean_iterations:.1f} iterations/run  ({r.verdict})"
            )
        lines.append("")

    for note in analysis.notes:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def format_agent_quality_markdown(analysis: QualityAnalysis) -> str:
    """Format agent-quality analysis as a Markdown report."""
    lines: list[str] = ["# Agent Quality Report", ""]
    if not analysis.windows and not analysis.retry_windows:
        lines.append("No closed-issue history found.")
        return "\n".join(lines)

    if analysis.windows:
        lines.append(
            "| Period | Orchestrator | Closed | Fix-rate | Correction rate | "
            "Cost/issue | Tokens/issue |"
        )
        lines.append("|---|---|---|---|---|---|---|")

        def cell(metric: QualityMetric, fmt: str) -> str:
            if metric.insufficient_history:
                return "insufficient history"
            assert metric.value is not None
            verdict = metric.verdict or "no verdict"
            return f"{format(metric.value, fmt)} ({verdict})"

        for w in analysis.windows:
            lines.append(
                f"| {w.period} | {w.orchestrator} | {w.closed_count} | "
                f"{cell(w.metrics['fix_rate'], '.0%')} | "
                f"{cell(w.metrics['correction_rate'], '.2f')} | "
                f"{cell(w.metrics['cost_per_issue'], '.2f')} | "
                f"{cell(w.metrics['tokens_per_issue'], '.0f')} |"
            )
        lines.append("")

    if analysis.retry_windows:
        lines.append("| Period | Loop | Runs | Mean iterations | Verdict |")
        lines.append("|---|---|---|---|---|")
        for r in analysis.retry_windows:
            if r.insufficient_history:
                lines.append(
                    f"| {r.period} | {r.loop_name} | {r.run_count} | - | insufficient history |"
                )
                continue
            lines.append(
                f"| {r.period} | {r.loop_name} | {r.run_count} | "
                f"{r.mean_iterations:.1f} | {r.verdict} |"
            )
        lines.append("")

    for note in analysis.notes:
        lines.append(f"> {note}")
    return "\n".join(lines)


def format_agent_quality_json(analysis: QualityAnalysis) -> str:
    """Format agent-quality analysis as JSON."""
    return json.dumps(analysis.to_dict(), indent=2)


def format_agent_quality_yaml(analysis: QualityAnalysis) -> str:
    """Format agent-quality analysis as YAML (falls back to JSON if yaml unavailable)."""
    try:
        import yaml

        return yaml.dump(analysis.to_dict(), default_flow_style=False, sort_keys=False)
    except ImportError:
        return format_agent_quality_json(analysis)

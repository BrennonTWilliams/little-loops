"""Shared utilities for issue_history sub-modules.

``month_key``/``add_days``/``classify_verdict``/``orchestrator_labels`` and
``MetricDefinition`` are extracted from ``rework.py`` (FEAT-3183) so
``rework.py`` and ``agent_quality.py`` share one windowing/verdict/definition
convention instead of forking it.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from little_loops.issue_history.models import CompletedIssue

logger = logging.getLogger(__name__)

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def get_issue_content(issue: CompletedIssue, contents: dict[Path, str] | None) -> str | None:
    """Retrieve issue content from cache or filesystem.

    Args:
        issue: The completed issue to retrieve content for
        contents: Optional pre-loaded content cache (path -> content)

    Returns:
        Issue file content string, or None if unavailable
    """
    if contents is not None and issue.path in contents:
        return contents[issue.path]
    try:
        return issue.path.read_text(encoding="utf-8")
    except Exception:
        return None


def month_key(ts: str | None) -> str:
    """Calendar-month bucket key for an ISO timestamp (e.g. ``"2026-07"``)."""
    return ts[:7] if ts else "unknown"


def add_days(ts: str, days: int) -> str:
    """Offset an ISO ``_TS_FORMAT`` timestamp by *days*; return unchanged if unparsable."""
    try:
        dt = datetime.strptime(ts, _TS_FORMAT)
    except (ValueError, TypeError):
        return ts
    return (dt + timedelta(days=days)).strftime(_TS_FORMAT)


def classify_verdict(rate: float, baseline: float) -> str:
    """Classify *rate* against *baseline* as improving/stable/degrading.

    Lower-is-better convention: a rate more than 20% below baseline is
    "improving", more than 20% above is "degrading". Metrics where a higher
    value is better (e.g. fix-rate) must feed this the underlying
    lower-is-better quantity instead (e.g. rework_share, not fix_rate).
    """
    if baseline == 0:
        return "stable" if rate == 0 else "degrading"
    if rate < baseline * 0.8:
        return "improving"
    if rate > baseline * 1.2:
        return "degrading"
    return "stable"


def orchestrator_labels(conn: sqlite3.Connection, issue_ids: set[str]) -> dict[str, str]:
    """Map issue_id -> ``orchestration_runs.driver``; callers default missing to unattributed."""
    if not issue_ids:
        return {}
    placeholders = ",".join("?" for _ in issue_ids)
    try:
        rows = conn.execute(
            "SELECT issue_id, driver FROM orchestration_runs "  # noqa: S608 - fixed cols, ? placeholders
            f"WHERE issue_id IN ({placeholders}) ORDER BY started_at",
            list(issue_ids),
        ).fetchall()
    except sqlite3.Error:
        logger.warning("issue_history: orchestration_runs query failed", exc_info=True)
        return {}
    labels: dict[str, str] = {}
    for row in rows:
        labels.setdefault(row["issue_id"], row["driver"])
    return labels


@dataclass(frozen=True)
class MetricDefinition:
    """One documented metric definition, emitted verbatim into every JSON payload."""

    name: str
    unit: str
    window: str
    denominator: str
    formula: str
    min_sample: int
    verdict_band: str
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "window": self.window,
            "denominator": self.denominator,
            "formula": self.formula,
            "min_sample": self.min_sample,
            "verdict_band": self.verdict_band,
            "caveats": list(self.caveats),
        }

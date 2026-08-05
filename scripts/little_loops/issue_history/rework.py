"""Rework-rate signals: the quality-adjustment term on batch throughput (FEAT-2867).

Computes reopen, follow-up, touch-back, and revert rates from ``.ll/history.db``
plus on-disk issue state (for supersession edges), buckets closed issues into
monthly ``(period, orchestrator)`` windows, and reports a quality-adjusted
throughput figure alongside the raw closed-issue count. Read-only against every
source; no LLM calls.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.history_reader import _connect_readonly
from little_loops.issue_parser import superseded_by
from little_loops.session_store import DEFAULT_DB_PATH

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)

# Minimum closed issues a (period, orchestrator) window needs before a rate is
# reported instead of "insufficient history" (issue_history/debt.py convention).
MIN_SAMPLE_SIZE = 5
# N-day lookahead for follow-up/touch-back detection.
FOLLOW_UP_WINDOW_DAYS = 14
UNATTRIBUTED_LABEL = "unattributed"
LOW_COVERAGE_THRESHOLD = 0.5

_REOPEN_TRANSITIONS = ("open", "in_progress", "blocked")
_REVERT_MESSAGE_RE = re.compile(r"[Tt]his reverts commit ([0-9a-fA-F]{7,40})")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_STANDARD_NOTES = (
    "Orchestrator attribution is correlational, not causal.",
    "Reopen rate counts issues that ever reopened, not reopen events "
    "(issue_events dedups per (issue_num, transition), so a second "
    "done->open->done cycle collapses into the first).",
    "Revert rate is computed from commit message lineage "
    "('This reverts commit <sha>') only; diff-inverse detection is deferred "
    "to a follow-up.",
)


def quality_adjusted_throughput(closed_count: int, rework_share: float) -> float:
    """The pinned quality-adjustment formula: ``closed x (1 - rework_share)``."""
    return closed_count * (1 - rework_share)


@dataclass
class ReworkSignal:
    """One rework signal's rate, sample size, and trend verdict for a window."""

    rate: float | None
    sample_size: int
    verdict: str
    baseline_rate: float | None = None
    baseline_period: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "sample_size": self.sample_size,
            "verdict": self.verdict,
            "baseline_rate": self.baseline_rate,
            "baseline_period": self.baseline_period,
        }


@dataclass
class ReworkWindow:
    """Rework signals for one (calendar month, orchestrator) bucket."""

    period: str
    orchestrator: str
    closed_count: int
    insufficient_history: bool
    reopen: ReworkSignal
    follow_up: ReworkSignal
    touch_back: ReworkSignal
    revert: ReworkSignal
    rework_share: float | None
    quality_adjusted: float | None
    commit_attribution_coverage: float | None
    low_attribution_coverage: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "orchestrator": self.orchestrator,
            "closed_count": self.closed_count,
            "insufficient_history": self.insufficient_history,
            "reopen": self.reopen.to_dict(),
            "follow_up": self.follow_up.to_dict(),
            "touch_back": self.touch_back.to_dict(),
            "revert": self.revert.to_dict(),
            "rework_share": self.rework_share,
            "quality_adjusted": self.quality_adjusted,
            "commit_attribution_coverage": self.commit_attribution_coverage,
            "low_attribution_coverage": self.low_attribution_coverage,
        }


@dataclass
class ReworkAnalysis:
    """Time series of rework windows plus the interpretive notes callers must show."""

    windows: list[ReworkWindow] = field(default_factory=list)
    min_sample_size: int = MIN_SAMPLE_SIZE
    follow_up_window_days: int = FOLLOW_UP_WINDOW_DAYS
    notes: list[str] = field(default_factory=lambda: list(_STANDARD_NOTES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "windows": [w.to_dict() for w in self.windows],
            "min_sample_size": self.min_sample_size,
            "follow_up_window_days": self.follow_up_window_days,
            "notes": self.notes,
        }


def _month_key(ts: str | None) -> str:
    return ts[:7] if ts else "unknown"


def _add_days(ts: str, days: int) -> str:
    try:
        dt = datetime.strptime(ts, _TS_FORMAT)
    except (ValueError, TypeError):
        return ts
    return (dt + timedelta(days=days)).strftime(_TS_FORMAT)


def _load_issue_events(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    """issue_id -> [(transition, ts), ...] sorted by ts, oldest first."""
    try:
        rows = conn.execute(
            "SELECT issue_id, transition, ts FROM issue_events "
            "WHERE issue_id IS NOT NULL AND transition IS NOT NULL ORDER BY issue_id, ts"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("rework: issue_events query failed", exc_info=True)
        return {}
    result: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        result.setdefault(row["issue_id"], []).append((row["transition"], row["ts"]))
    return result


def _load_commits(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT ts, commit_sha, message, issue_id, files_json FROM commit_events ORDER BY ts"
        ).fetchall()
    except sqlite3.Error:
        logger.warning("rework: commit_events query failed", exc_info=True)
        return []
    commits: list[dict[str, Any]] = []
    for row in rows:
        files: set[str] = set()
        if row["files_json"]:
            try:
                files = set(json.loads(row["files_json"]))
            except (json.JSONDecodeError, TypeError):
                files = set()
        commits.append(
            {
                "ts": row["ts"],
                "commit_sha": row["commit_sha"],
                "message": row["message"] or "",
                "issue_id": row["issue_id"],
                "files": files,
            }
        )
    return commits


def _orchestrator_labels(conn: sqlite3.Connection, issue_ids: set[str]) -> dict[str, str]:
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
        logger.warning("rework: orchestration_runs query failed", exc_info=True)
        return {}
    labels: dict[str, str] = {}
    for row in rows:
        labels.setdefault(row["issue_id"], row["driver"])
    return labels


def _is_reopened(
    issue_id: str,
    transitions: list[tuple[str, str]],
    done_ts: str,
    superseded_ids: set[str],
) -> bool:
    for transition, ts in transitions:
        if ts <= done_ts:
            continue
        if transition in _REOPEN_TRANSITIONS:
            return True
        if transition == "cancelled" and issue_id in superseded_ids:
            return True
    return False


def _has_follow_up(
    issue_id: str,
    files: set[str],
    done_ts: str,
    commits: list[dict[str, Any]],
    window_days: int,
) -> bool:
    if not files:
        return False
    cutoff = _add_days(done_ts, window_days)
    for c in commits:
        if c["issue_id"] == issue_id or not c["issue_id"]:
            continue
        if not (done_ts < c["ts"] <= cutoff):
            continue
        if c["issue_id"].startswith("BUG-") and c["files"] & files:
            return True
    return False


def _has_touch_back(
    issue_id: str,
    files: set[str],
    done_ts: str,
    commits: list[dict[str, Any]],
    window_days: int,
) -> bool:
    if not files:
        return False
    cutoff = _add_days(done_ts, window_days)
    for c in commits:
        if c["issue_id"] == issue_id:
            continue
        if not (done_ts < c["ts"] <= cutoff):
            continue
        if c["files"] & files:
            return True
    return False


def _is_reverted(commit_shas: list[str], commits: list[dict[str, Any]]) -> bool:
    if not commit_shas:
        return False
    shas_lower = [s.lower() for s in commit_shas if s]
    for c in commits:
        match = _REVERT_MESSAGE_RE.search(c["message"])
        if not match:
            continue
        target = match.group(1).lower()
        for sha in shas_lower:
            if sha.startswith(target) or target.startswith(sha):
                return True
    return False


def _classify_verdict(rate: float, baseline: float) -> str:
    if baseline == 0:
        return "stable" if rate == 0 else "degrading"
    if rate < baseline * 0.8:
        return "improving"
    if rate > baseline * 1.2:
        return "degrading"
    return "stable"


def _assign_verdicts(windows: list[ReworkWindow]) -> None:
    """Compare each window's signals to the earliest window sharing its orchestrator."""
    by_orchestrator: dict[str, list[ReworkWindow]] = {}
    for w in windows:
        if w.insufficient_history:
            continue
        by_orchestrator.setdefault(w.orchestrator, []).append(w)

    for group in by_orchestrator.values():
        group.sort(key=lambda w: w.period)
        baseline = group[0]
        for w in group:
            for name in ("reopen", "follow_up", "touch_back", "revert"):
                signal: ReworkSignal = getattr(w, name)
                if w is baseline:
                    signal.verdict = "stable"
                    continue
                baseline_signal: ReworkSignal = getattr(baseline, name)
                signal.baseline_rate = baseline_signal.rate
                signal.baseline_period = baseline.period
                assert signal.rate is not None and baseline_signal.rate is not None
                signal.verdict = _classify_verdict(signal.rate, baseline_signal.rate)


def analyze_rework(
    issues: list[IssueInfo],
    *,
    db: Path | str = DEFAULT_DB_PATH,
    min_sample: int = MIN_SAMPLE_SIZE,
    follow_up_days: int = FOLLOW_UP_WINDOW_DAYS,
) -> ReworkAnalysis:
    """Compute rework signals as a time series of (period, orchestrator) windows.

    Args:
        issues: All on-disk issues (any status) — needed to resolve `supersedes:`
            edges for the reopen signal's cancelled-as-superseded case.
        db: Path to ``.ll/history.db``.
        min_sample: Minimum closed issues per window before a rate is reported.
        follow_up_days: Lookahead window for follow-up/touch-back detection.

    Returns:
        ReworkAnalysis with empty windows if the DB is missing/empty.
    """
    empty = ReworkAnalysis(min_sample_size=min_sample, follow_up_window_days=follow_up_days)
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return empty

    try:
        events_by_issue = _load_issue_events(conn)
        commits = _load_commits(conn)
        if not events_by_issue:
            return empty

        superseded_ids = {info.issue_id for info in issues if superseded_by(info.issue_id, issues)}

        commits_by_issue: dict[str, list[dict[str, Any]]] = {}
        for c in commits:
            if c["issue_id"]:
                commits_by_issue.setdefault(c["issue_id"], []).append(c)

        closed: list[dict[str, Any]] = []
        for issue_id, transitions in events_by_issue.items():
            done_ts = next((ts for transition, ts in transitions if transition == "done"), None)
            if done_ts is None:
                continue
            own_commits = commits_by_issue.get(issue_id, [])
            issue_files: set[str] = set()
            for c in own_commits:
                issue_files |= c["files"]
            commit_shas = [c["commit_sha"] for c in own_commits]
            closed.append(
                {
                    "issue_id": issue_id,
                    "done_ts": done_ts,
                    "reopened": _is_reopened(issue_id, transitions, done_ts, superseded_ids),
                    "follow_up": _has_follow_up(
                        issue_id, issue_files, done_ts, commits, follow_up_days
                    ),
                    "touch_back": _has_touch_back(
                        issue_id, issue_files, done_ts, commits, follow_up_days
                    ),
                    "reverted": _is_reverted(commit_shas, commits),
                }
            )

        if not closed:
            return empty

        orchestrator_labels = _orchestrator_labels(conn, {e["issue_id"] for e in closed})

        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for entry in closed:
            period = _month_key(entry["done_ts"])
            orchestrator = orchestrator_labels.get(entry["issue_id"], UNATTRIBUTED_LABEL)
            groups.setdefault((period, orchestrator), []).append(entry)

        commits_by_period: dict[str, list[dict[str, Any]]] = {}
        for c in commits:
            commits_by_period.setdefault(_month_key(c["ts"]), []).append(c)
        coverage_by_period: dict[str, float] = {}
        for period, period_commits in commits_by_period.items():
            attributed = sum(1 for c in period_commits if c["issue_id"])
            coverage_by_period[period] = attributed / len(period_commits)

        windows: list[ReworkWindow] = []
        for (period, orchestrator), entries in sorted(groups.items()):
            closed_count = len(entries)
            coverage = coverage_by_period.get(period)
            low_coverage = coverage is not None and coverage < LOW_COVERAGE_THRESHOLD

            if closed_count < min_sample:
                windows.append(
                    ReworkWindow(
                        period=period,
                        orchestrator=orchestrator,
                        closed_count=closed_count,
                        insufficient_history=True,
                        reopen=ReworkSignal(None, closed_count, "insufficient history"),
                        follow_up=ReworkSignal(None, closed_count, "insufficient history"),
                        touch_back=ReworkSignal(None, closed_count, "insufficient history"),
                        revert=ReworkSignal(None, closed_count, "insufficient history"),
                        rework_share=None,
                        quality_adjusted=None,
                        commit_attribution_coverage=coverage,
                        low_attribution_coverage=low_coverage,
                    )
                )
                continue

            reopen_rate = sum(1 for e in entries if e["reopened"]) / closed_count
            follow_up_rate = sum(1 for e in entries if e["follow_up"]) / closed_count
            touch_back_rate = sum(1 for e in entries if e["touch_back"]) / closed_count
            revert_rate = sum(1 for e in entries if e["reverted"]) / closed_count
            rework_share = max(reopen_rate, revert_rate)

            windows.append(
                ReworkWindow(
                    period=period,
                    orchestrator=orchestrator,
                    closed_count=closed_count,
                    insufficient_history=False,
                    reopen=ReworkSignal(reopen_rate, closed_count, "stable"),
                    follow_up=ReworkSignal(follow_up_rate, closed_count, "stable"),
                    touch_back=ReworkSignal(touch_back_rate, closed_count, "stable"),
                    revert=ReworkSignal(revert_rate, closed_count, "stable"),
                    rework_share=rework_share,
                    quality_adjusted=quality_adjusted_throughput(closed_count, rework_share),
                    commit_attribution_coverage=coverage,
                    low_attribution_coverage=low_coverage,
                )
            )

        _assign_verdicts(windows)
        return ReworkAnalysis(
            windows=windows, min_sample_size=min_sample, follow_up_window_days=follow_up_days
        )
    finally:
        conn.close()


def format_rework_json(analysis: ReworkAnalysis) -> str:
    """Format rework analysis as JSON."""
    return json.dumps(analysis.to_dict(), indent=2)


def format_rework_yaml(analysis: ReworkAnalysis) -> str:
    """Format rework analysis as YAML (falls back to JSON if yaml unavailable)."""
    try:
        import yaml

        return yaml.dump(analysis.to_dict(), default_flow_style=False, sort_keys=False)
    except ImportError:
        return format_rework_json(analysis)


def format_rework_text(analysis: ReworkAnalysis) -> str:
    """Format rework analysis as a plain-text report."""
    lines: list[str] = ["Rework Rate Analysis", "=" * 21, ""]
    if not analysis.windows:
        lines.append("No closed-issue history found.")
        return "\n".join(lines)

    for w in analysis.windows:
        lines.append(f"{w.period}  [{w.orchestrator}]  closed={w.closed_count}")
        if w.insufficient_history:
            lines.append("  insufficient history")
            lines.append("")
            continue
        assert w.quality_adjusted is not None and w.rework_share is not None
        lines.append(
            f"  quality-adjusted throughput: {w.quality_adjusted:.1f} "
            f"(raw closed: {w.closed_count}, rework_share: {w.rework_share:.0%})"
        )
        for label, signal in (
            ("reopen", w.reopen),
            ("follow-up", w.follow_up),
            ("touch-back", w.touch_back),
            ("revert", w.revert),
        ):
            assert signal.rate is not None
            lines.append(f"  {label}: {signal.rate:.0%} ({signal.verdict})")
        if w.commit_attribution_coverage is not None:
            coverage_note = " [LOW]" if w.low_attribution_coverage else ""
            lines.append(
                f"  commit attribution coverage: {w.commit_attribution_coverage:.0%}{coverage_note}"
            )
        lines.append("")

    for note in analysis.notes:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def format_rework_markdown(analysis: ReworkAnalysis) -> str:
    """Format rework analysis as a Markdown report."""
    lines: list[str] = ["# Rework Rate Analysis", ""]
    if not analysis.windows:
        lines.append("No closed-issue history found.")
        return "\n".join(lines)

    lines.append(
        "| Period | Orchestrator | Closed | Quality-Adj | Reopen | Follow-up | "
        "Touch-back | Revert | Coverage |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for w in analysis.windows:
        if w.insufficient_history:
            lines.append(
                f"| {w.period} | {w.orchestrator} | {w.closed_count} | "
                "insufficient history | - | - | - | - | - |"
            )
            continue
        assert w.quality_adjusted is not None
        coverage_str = (
            f"{w.commit_attribution_coverage:.0%}"
            if w.commit_attribution_coverage is not None
            else "n/a"
        )
        if w.low_attribution_coverage:
            coverage_str += " (low)"
        lines.append(
            f"| {w.period} | {w.orchestrator} | {w.closed_count} | "
            f"{w.quality_adjusted:.1f} | "
            f"{w.reopen.rate:.0%} ({w.reopen.verdict}) | "
            f"{w.follow_up.rate:.0%} ({w.follow_up.verdict}) | "
            f"{w.touch_back.rate:.0%} ({w.touch_back.verdict}) | "
            f"{w.revert.rate:.0%} ({w.revert.verdict}) | "
            f"{coverage_str} |"
        )
    lines.append("")
    for note in analysis.notes:
        lines.append(f"> {note}")
    return "\n".join(lines)

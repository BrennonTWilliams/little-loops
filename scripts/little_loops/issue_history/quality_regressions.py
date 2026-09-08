"""Quality-regression detection, attribution, and composition loading (FEAT-3405).

Detects a drop in the most recent window of each `agent_quality.py` metric
series against a prior-K-window baseline, and attributes the drop to the
model/host/`ll_version` whose share of the window's runs shifted most versus
the baseline. Deterministic and LLM-free -- statistical over recorded values
only.

Two series families share this module:

1. The four `QualityWindow` metrics (`fix_rate`, `correction_rate`,
   `cost_per_issue`, `tokens_per_issue`), keyed by `(period, orchestrator)`.
2. `retry_inflation` (`QualityAnalysis.retry_windows`), keyed by
   `(period, loop_name)`; attribution there is restricted to `ll_version`
   (`loop_runs` has no session join, so model/host are unavailable).

False friends -- do not conflate when searching or naming:

- `issue_history/regressions.py` (`analyze_regression_clustering`) and
  `models.py`'s `RegressionCluster`/`RegressionAnalysis`: an unrelated
  bug-fix regression-*clustering* system (temporal + file-overlap
  heuristics), not this module's statistical quality-metric detection.
- `issue_history/quality.py`: test-gap/rejection/config-gap analysis,
  unrelated to the agent-quality metric series this module detects over.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

from little_loops.issue_history._utils import month_key
from little_loops.issue_history.rework import LOW_COVERAGE_THRESHOLD

if TYPE_CHECKING:
    from little_loops.issue_history.agent_quality import QualityAnalysis, QualityWindow, RetryWindow

DEFAULT_SENSITIVITY = 0.30
DEFAULT_BASELINE_WINDOWS = 3
ATTRIBUTION_MIN_SHIFT = 0.25
HIGHER_IS_BETTER: frozenset[str] = frozenset({"fix_rate"})

_METRIC_NAMES: tuple[str, ...] = (
    "fix_rate",
    "correction_rate",
    "cost_per_issue",
    "tokens_per_issue",
)
# cost_per_issue/tokens_per_issue read 0.0 in months that predate usage-event
# capture -- not "free", just unmeasured. A window with value == 0.0 for these
# two metrics is never used as a baseline (see module docstring / Decision Rules).
_ZERO_INELIGIBLE_BASELINE_METRICS: frozenset[str] = frozenset(
    {"cost_per_issue", "tokens_per_issue"}
)

# A model column value meaning "not a real model" (e.g. title-generation
# scaffolding calls) -- excluded from the model dimension entirely.
_SYNTHETIC_MODEL = "<synthetic>"

_REGRESSION_NOTES: tuple[str, ...] = (
    "Attribution is correlational: a composition shift coinciding with a drop, not a proven cause.",
    "Host attribution requires transcripts from more than one host to discriminate.",
    "The newest window under-reports fix_rate regressions because reopens lag closes.",
)


@dataclass
class RunAttribution:
    """The (dimension, value) whose share of a flagged window's runs shifted most."""

    dimension: Literal["model", "host", "ll_version"]
    value: str
    window_share: float
    baseline_share: float
    shift: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "window_share": self.window_share,
            "baseline_share": self.baseline_share,
            "shift": self.shift,
        }


@dataclass
class RegressionEvent:
    """One flagged window: which metric/series/period, by how much, attributed to what."""

    metric: str
    series: str
    period: str
    value: float
    baseline_periods: list[str]
    baseline_value: float
    magnitude: float
    attribution: RunAttribution | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "series": self.series,
            "period": self.period,
            "value": self.value,
            "baseline_periods": self.baseline_periods,
            "baseline_value": self.baseline_value,
            "magnitude": self.magnitude,
            "attribution": self.attribution.to_dict() if self.attribution else None,
        }


@dataclass
class QualityRegressionAnalysis:
    """Detected regression events plus the parameters and skip counters behind them."""

    events: list[RegressionEvent] = field(default_factory=list)
    sensitivity: float = DEFAULT_SENSITIVITY
    baseline_windows: int = DEFAULT_BASELINE_WINDOWS
    latest_only: bool = True
    skipped_unknown_period: int = 0
    skipped_zero_baseline: int = 0
    notes: tuple[str, ...] = field(default_factory=lambda: _REGRESSION_NOTES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "sensitivity": self.sensitivity,
            "baseline_windows": self.baseline_windows,
            "latest_only": self.latest_only,
            "skipped_unknown_period": self.skipped_unknown_period,
            "skipped_zero_baseline": self.skipped_zero_baseline,
            "notes": list(self.notes),
        }


@dataclass
class WindowComposition:
    """Per-`(period, series)` weighted dimension composition for attribution.

    `counts` is dimension -> value -> weighted count. Storing counts (not
    shares) is what lets baseline composition be pooled across K windows
    rather than averaged as a mean-of-shares. `units` is the window's
    population size (closed-issue count for the `QualityWindow` series,
    loop-run count for `retry_inflation`) -- the shared denominator `coverage`
    is measured against, so a dimension's coverage is comparable across
    windows of different size.
    """

    period: str
    series: str
    counts: dict[str, dict[str, float]] = field(default_factory=dict)
    coverage: dict[str, float] = field(default_factory=dict)
    units: float = 0.0

    def shares(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for dimension, values in self.counts.items():
            total = sum(values.values())
            if total <= 0:
                result[dimension] = {}
                continue
            result[dimension] = {value: count / total for value, count in values.items()}
        return result


def load_window_compositions(
    conn: sqlite3.Connection,
    issue_window: dict[int, tuple[str, str]],
    issue_ids: dict[int, str],
    session_issues: dict[str, set[int]],
) -> list[WindowComposition]:
    """Build per-window model/host/ll_version compositions for attribution.

    Args:
        conn: Open connection to `.ll/history.db`.
        issue_window: `issue_num -> (period, orchestrator)`, from
            `analyze_agent_quality()`'s `closed` loop.
        issue_ids: `issue_num -> issue_id` text, for the `orchestration_runs.issue_id`
            join (TEXT column).
        session_issues: `session_id -> {issue_num, ...}`, from `_session_issue_map()`.

    Returns:
        One `WindowComposition` per `(period, orchestrator)` (model/host/ll_version
        dimensions) plus one per `(period, loop_name)` for the retry series
        (`ll_version` dimension only).
    """
    compositions: dict[tuple[str, str], WindowComposition] = {}
    window_units: dict[tuple[str, str], float] = {}
    for population_key in issue_window.values():
        window_units[population_key] = window_units.get(population_key, 0.0) + 1.0

    def get_or_create(key: tuple[str, str]) -> WindowComposition:
        comp = compositions.get(key)
        if comp is None:
            comp = WindowComposition(period=key[0], series=key[1], units=window_units.get(key, 0.0))
            compositions[key] = comp
        return comp

    model_known: dict[tuple[str, str], float] = {}
    try:
        rows = conn.execute(
            "SELECT session_id, model, COUNT(*) as cnt FROM usage_events "
            "WHERE session_id IS NOT NULL GROUP BY session_id, model"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    for row in rows:
        issues = session_issues.get(row["session_id"])
        if not issues:
            continue
        n = len(issues)
        model = row["model"]
        weight_total = row["cnt"] / n
        for issue_num in issues:
            key = issue_window.get(issue_num)
            if key is None:
                continue
            if model and model != _SYNTHETIC_MODEL:
                comp = get_or_create(key)
                dim = comp.counts.setdefault("model", {})
                dim[model] = dim.get(model, 0.0) + weight_total
                model_known[key] = model_known.get(key, 0.0) + weight_total

    host_known: dict[tuple[str, str], float] = {}
    try:
        rows = conn.execute(
            "SELECT session_id, host, COUNT(*) as cnt FROM raw_events "
            "WHERE session_id IS NOT NULL GROUP BY session_id, host"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    for row in rows:
        issues = session_issues.get(row["session_id"])
        if not issues:
            continue
        n = len(issues)
        host = row["host"]
        weight_total = row["cnt"] / n
        for issue_num in issues:
            key = issue_window.get(issue_num)
            if key is None:
                continue
            if host:
                comp = get_or_create(key)
                dim = comp.counts.setdefault("host", {})
                dim[host] = dim.get(host, 0.0) + weight_total
                host_known[key] = host_known.get(key, 0.0) + weight_total

    ll_known: dict[tuple[str, str], float] = {}
    if issue_ids:
        placeholders = ",".join("?" for _ in issue_ids)
        try:
            rows = conn.execute(
                "SELECT issue_id, ll_version FROM orchestration_runs "  # noqa: S608
                f"WHERE issue_id IN ({placeholders}) ORDER BY started_at",
                list(issue_ids.values()),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        latest_version_by_issue_id: dict[str, str | None] = {}
        for row in rows:
            # ORDER BY started_at ascending -- the last write per issue_id wins,
            # i.e. the row with the latest started_at (BUG-3051's multi-run tie-break).
            latest_version_by_issue_id[row["issue_id"]] = row["ll_version"]
        for issue_num, issue_id in issue_ids.items():
            key = issue_window.get(issue_num)
            if key is None or issue_id not in latest_version_by_issue_id:
                continue
            version = latest_version_by_issue_id[issue_id]
            if version:
                comp = get_or_create(key)
                dim = comp.counts.setdefault("ll_version", {})
                dim[version] = dim.get(version, 0.0) + 1.0
                ll_known[key] = ll_known.get(key, 0.0) + 1.0

    for key, comp in compositions.items():
        units = comp.units
        comp.coverage["model"] = (model_known.get(key, 0.0) / units) if units else 0.0
        comp.coverage["host"] = (host_known.get(key, 0.0) / units) if units else 0.0
        comp.coverage["ll_version"] = (ll_known.get(key, 0.0) / units) if units else 0.0

    # retry_inflation compositions: (period, loop_name) -> ll_version, unit = run count.
    # Independent of issue/session data above (loop_runs has no issue_id column).
    retry_compositions: dict[tuple[str, str], WindowComposition] = {}
    retry_units: dict[tuple[str, str], float] = {}
    retry_known: dict[tuple[str, str], float] = {}
    try:
        retry_rows = conn.execute(
            "SELECT loop_name, started_at, ended_at, ll_version FROM loop_runs"
        ).fetchall()
    except sqlite3.Error:
        retry_rows = []
    for row in retry_rows:
        ts = row["started_at"] or row["ended_at"]
        retry_key = (month_key(ts), row["loop_name"])
        retry_units[retry_key] = retry_units.get(retry_key, 0.0) + 1.0
        retry_comp = retry_compositions.get(retry_key)
        if retry_comp is None:
            retry_comp = WindowComposition(period=retry_key[0], series=retry_key[1])
            retry_compositions[retry_key] = retry_comp
        version = row["ll_version"]
        if version:
            dim = retry_comp.counts.setdefault("ll_version", {})
            dim[version] = dim.get(version, 0.0) + 1.0
            retry_known[retry_key] = retry_known.get(retry_key, 0.0) + 1.0
    for retry_key, retry_comp in retry_compositions.items():
        units = retry_units.get(retry_key, 0.0)
        retry_comp.units = units
        retry_comp.coverage["ll_version"] = (
            (retry_known.get(retry_key, 0.0) / units) if units else 0.0
        )

    return list(compositions.values()) + list(retry_compositions.values())


def _metric_eligible(window: QualityWindow, metric_name: str) -> bool:
    m = window.metrics[metric_name]
    return not m.insufficient_history and m.verdict is not None


def _metric_eligible_as_baseline(window: QualityWindow, metric_name: str) -> bool:
    if not _metric_eligible(window, metric_name):
        return False
    if metric_name in _ZERO_INELIGIBLE_BASELINE_METRICS:
        value = window.metrics[metric_name].value
        if value == 0.0:
            return False
    return True


def detect_quality_regressions(
    analysis: QualityAnalysis,
    compositions: list[WindowComposition],
    *,
    sensitivity: float = DEFAULT_SENSITIVITY,
    baseline_windows: int = DEFAULT_BASELINE_WINDOWS,
    latest_only: bool = True,
) -> QualityRegressionAnalysis:
    """Detect a drop in the latest (or every) eligible window of each series.

    Prior-K-window baseline comparison per `(metric, series)`, not a
    change-point algorithm (data is too sparse). See the module docstring and
    FEAT-3405's Decision Rules for the full eligibility/exclusion/attribution
    rules this implements.
    """
    composition_by_key = {(c.period, c.series): c for c in compositions}
    events: list[RegressionEvent] = []
    skipped_zero_baseline = 0

    by_orchestrator: dict[str, list[QualityWindow]] = {}
    for w in analysis.windows:
        by_orchestrator.setdefault(w.orchestrator, []).append(w)

    for series, windows in by_orchestrator.items():
        ordered = sorted((w for w in windows if w.period != "unknown"), key=lambda w: w.period)
        for metric_name in _METRIC_NAMES:
            higher_is_better = metric_name in HIGHER_IS_BETTER
            eligible_indices = [
                i for i, w in enumerate(ordered) if _metric_eligible(w, metric_name)
            ]
            if not eligible_indices:
                continue
            target_indices = [eligible_indices[-1]] if latest_only else eligible_indices
            for idx in target_indices:
                target = ordered[idx]
                baseline_candidates = [
                    w for w in ordered[:idx] if _metric_eligible_as_baseline(w, metric_name)
                ]
                baseline_candidates = (
                    baseline_candidates[-baseline_windows:] if baseline_windows > 0 else []
                )
                if not baseline_candidates:
                    continue
                baseline_value = sum(
                    cast(float, w.metrics[metric_name].value) for w in baseline_candidates
                ) / len(baseline_candidates)
                if baseline_value == 0:
                    skipped_zero_baseline += 1
                    continue
                value = cast(float, target.metrics[metric_name].value)
                if higher_is_better:
                    magnitude = (baseline_value - value) / baseline_value
                else:
                    magnitude = (value - baseline_value) / baseline_value
                if magnitude > sensitivity:
                    comp = composition_by_key.get((target.period, series))
                    baseline_comps = [
                        composition_by_key[(w.period, series)]
                        for w in baseline_candidates
                        if (w.period, series) in composition_by_key
                    ]
                    attribution = attribute_change(comp, baseline_comps) if comp else None
                    events.append(
                        RegressionEvent(
                            metric=metric_name,
                            series=series,
                            period=target.period,
                            value=value,
                            baseline_periods=[w.period for w in baseline_candidates],
                            baseline_value=baseline_value,
                            magnitude=magnitude,
                            attribution=attribution,
                        )
                    )

    by_loop: dict[str, list[RetryWindow]] = {}
    for r in analysis.retry_windows:
        by_loop.setdefault(r.loop_name, []).append(r)

    for loop_name, retry_series_windows in by_loop.items():
        ordered_r = sorted(
            (w for w in retry_series_windows if w.period != "unknown"), key=lambda w: w.period
        )
        eligible_indices = [i for i, w in enumerate(ordered_r) if not w.insufficient_history]
        if not eligible_indices:
            continue
        target_indices = [eligible_indices[-1]] if latest_only else eligible_indices
        for idx in target_indices:
            retry_target = ordered_r[idx]
            retry_baseline_candidates = [w for w in ordered_r[:idx] if not w.insufficient_history]
            retry_baseline_candidates = (
                retry_baseline_candidates[-baseline_windows:] if baseline_windows > 0 else []
            )
            if not retry_baseline_candidates:
                continue
            retry_baseline_value = sum(
                cast(float, w.mean_iterations) for w in retry_baseline_candidates
            ) / len(retry_baseline_candidates)
            if retry_baseline_value == 0:
                skipped_zero_baseline += 1
                continue
            retry_value = cast(float, retry_target.mean_iterations)
            retry_magnitude = (retry_value - retry_baseline_value) / retry_baseline_value
            if retry_magnitude > sensitivity:
                comp = composition_by_key.get((retry_target.period, loop_name))
                baseline_comps = [
                    composition_by_key[(w.period, loop_name)]
                    for w in retry_baseline_candidates
                    if (w.period, loop_name) in composition_by_key
                ]
                attribution = attribute_change(comp, baseline_comps) if comp else None
                events.append(
                    RegressionEvent(
                        metric="retry_inflation",
                        series=loop_name,
                        period=retry_target.period,
                        value=retry_value,
                        baseline_periods=[w.period for w in retry_baseline_candidates],
                        baseline_value=retry_baseline_value,
                        magnitude=retry_magnitude,
                        attribution=attribution,
                    )
                )

    skipped_unknown_period = sum(1 for w in analysis.windows if w.period == "unknown")
    skipped_unknown_period += sum(1 for r in analysis.retry_windows if r.period == "unknown")

    return QualityRegressionAnalysis(
        events=events,
        sensitivity=sensitivity,
        baseline_windows=baseline_windows,
        latest_only=latest_only,
        skipped_unknown_period=skipped_unknown_period,
        skipped_zero_baseline=skipped_zero_baseline,
    )


def attribute_change(
    window: WindowComposition | None,
    baseline: list[WindowComposition],
    *,
    min_shift: float = ATTRIBUTION_MIN_SHIFT,
    min_coverage: float = LOW_COVERAGE_THRESHOLD,
) -> RunAttribution | None:
    """Name the (dimension, value) whose pooled-baseline share increased most.

    Returns `None` ("no attributable change") when no dimension's coverage
    clears `min_coverage` on both sides, or no candidate's share increase
    exceeds `min_shift`.
    """
    if window is None or not baseline:
        return None

    pooled_counts: dict[str, dict[str, float]] = {}
    pooled_known: dict[str, float] = {}
    pooled_units = 0.0
    for b in baseline:
        pooled_units += b.units
        for dimension, values in b.counts.items():
            bucket = pooled_counts.setdefault(dimension, {})
            for value, count in values.items():
                bucket[value] = bucket.get(value, 0.0) + count
        for dimension, cov in b.coverage.items():
            pooled_known[dimension] = pooled_known.get(dimension, 0.0) + cov * b.units

    pooled_coverage = {
        dimension: (pooled_known.get(dimension, 0.0) / pooled_units if pooled_units else 0.0)
        for dimension in set(pooled_counts) | set(window.counts)
    }
    pooled_totals = {dimension: sum(values.values()) for dimension, values in pooled_counts.items()}
    window_shares = window.shares()

    best: RunAttribution | None = None
    for dimension, w_shares in window_shares.items():
        if window.coverage.get(dimension, 0.0) < min_coverage:
            continue
        if pooled_coverage.get(dimension, 0.0) < min_coverage:
            continue
        baseline_total = pooled_totals.get(dimension, 0.0)
        for value, w_share in w_shares.items():
            b_count = pooled_counts.get(dimension, {}).get(value, 0.0)
            b_share = (b_count / baseline_total) if baseline_total else 0.0
            shift = w_share - b_share
            if shift <= min_shift:
                continue
            if best is None or shift > best.shift:
                best = RunAttribution(
                    dimension=cast(Literal["model", "host", "ll_version"], dimension),
                    value=value,
                    window_share=w_share,
                    baseline_share=b_share,
                    shift=shift,
                )
    return best

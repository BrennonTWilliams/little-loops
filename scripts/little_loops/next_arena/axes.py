"""Bounded axis curves, raw-domain validators and weighted aggregation (FEAT-3561 phase C).

Every function here is **pure**: it takes injected values (a record, a ``Leverage``, an
``as_of`` datetime, resolved weights) and never reads the clock, cwd, environment, files or
git. Scores are always finite values in ``[0, 1]`` or ``None`` (missing, with a reason);
nothing serializes as NaN/Infinity.

Curves are lower-bounded with ``lerp(lo, 1, x) = lo + (1 - lo) * x`` so a worst-case value
never collapses the geometric aggregate (see :data:`AXIS_BOUNDS`); the aggregate itself is
:func:`little_loops.utility.weighted_geometric` over present axes with weights renormalized
(there is no make-up term and no coverage multiplier; coverage is only *reported*).

Date policy (documented UTC normalization): a date-only value (``2026-08-01``) means
midnight UTC; a timestamp without an offset (``2026-08-01T12:00:00``) is read as UTC (the
same convention :func:`little_loops.session_log.last_command_timestamp` uses for Session Log
stamps); a timestamp with an offset or ``Z`` is converted to UTC. Malformed values and values
later than ``as_of`` are *missing* with a reason, never clamped to "now".
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from little_loops.next_arena.graph import DEFAULT_LEVERAGE_CAP, Leverage
from little_loops.next_arena.registry import get_verb
from little_loops.session_log import _TIMESTAMPED_ENTRY_RE, session_log_body
from little_loops.utility import frequency_score, recency_score, weighted_geometric

if TYPE_CHECKING:
    from little_loops.next_arena.state import SourceRecord

__all__ = [
    "AXIS_BOUNDS",
    "AXIS_LOWER_BOUNDS",
    "AxisAggregate",
    "AxisScore",
    "EffortParse",
    "aggregate_axes",
    "axis_missing",
    "compute_issue_axes",
    "compute_loop_axes",
    "effort_axis",
    "latest_session_timestamp",
    "latest_session_timestamp_from_content",
    "leverage_axis",
    "loop_frequency_axis",
    "loop_minimum_evidence_met",
    "loop_recency_axis",
    "loop_success_axis",
    "leverage_evidence",
    "lerp",
    "minimum_evidence_met",
    "momentum_axis",
    "outcome_axis",
    "parse_effort",
    "parse_utc_datetime",
    "priority_axis",
    "readiness_gap_axis",
    "staleness_axis",
    "validate_score",
    "waiver_true",
]

# --------------------------------------------------------------------------- constants

#: Lower bound ``lo`` of each lerp-bounded curve.
PRIORITY_LO = 0.2
OUTCOME_LO = 0.2
READINESS_GAP_LO = 0.2
LEVERAGE_LO = 0.5
STALENESS_LO = 0.3
MOMENTUM_LO = 0.3
FREQUENCY_LO = 0.4
RECENCY_LO = 0.2
SUCCESS_LO = 0.2

STALENESS_FULL_DAYS = 30.0
MOMENTUM_HALF_LIFE_DAYS = 7.0
LEVERAGE_SATURATION = DEFAULT_LEVERAGE_CAP

#: ``(worst_score, best_score)`` per axis; the nominal-weight property is
#: ``(worst / best) ** weight >= 0.6`` for every axis of every registered verb.
AXIS_BOUNDS: Mapping[str, tuple[float, float]] = MappingProxyType(
    {
        "priority": (PRIORITY_LO, 1.0),
        "outcome": (OUTCOME_LO, 1.0),
        "readiness_gap": (READINESS_GAP_LO, 1.0),
        "leverage": (LEVERAGE_LO, 1.0),
        "effort": (1.0 / 3.0, 1.0),
        "staleness": (STALENESS_LO, 1.0),
        "momentum": (MOMENTUM_LO, 1.0),
        "frequency": (FREQUENCY_LO, 1.0),
        "recency": (RECENCY_LO, 1.0),
        "success": (SUCCESS_LO, 1.0),
    }
)
#: The recorded ``lo`` values (worst score) alone.
AXIS_LOWER_BOUNDS: Mapping[str, float] = MappingProxyType(
    {axis: worst for axis, (worst, _best) in AXIS_BOUNDS.items()}
)

#: ``validate_score`` reasons: ``valid``, ``absent``, or ``invalid:<why>``.
SCORE_VALID = "valid"
SCORE_ABSENT = "absent"

_SECONDS_PER_DAY = 86400.0


def lerp(lo: float, x: float) -> float:
    """``lerp(lo, 1, x)`` with *x* clamped to ``[0, 1]``: ``lo + (1 - lo) * x``."""
    clamped = 0.0 if x <= 0.0 else 1.0 if x >= 1.0 else x
    return lo + (1.0 - lo) * clamped


# ----------------------------------------------------------------------------- types


def _json_number(value: float | None) -> float | None:
    """A finite float or ``None`` (never NaN/Infinity)."""
    if value is None or not math.isfinite(value):
        return None
    return float(value)


@dataclass(frozen=True)
class AxisScore:
    """One axis outcome: raw evidence, the curve applied, the score and the weights.

    ``score`` is ``None`` when the axis is missing (``missing_reason`` explains and
    ``raw`` retains whatever text/evidence exists). ``configured_weight`` is the
    resolved settings weight; ``effective_weight`` is the renormalized weight actually
    applied to the geometric aggregate (``0.0`` for a missing or zero-weight axis).
    """

    raw: Any
    curve: str
    score: float | None
    configured_weight: float
    effective_weight: float
    source: str | None
    missing_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Deterministic JSON-ready mapping (``None`` for missing; no NaN/Infinity)."""
        return {
            "raw": self.raw,
            "curve": self.curve,
            "score": _json_number(self.score),
            "configured_weight": _json_number(self.configured_weight),
            "effective_weight": _json_number(self.effective_weight),
            "source": self.source,
            "missing_reason": self.missing_reason,
        }


def axis_missing(
    curve: str, reason: str, *, raw: Any = None, source: str | None = None
) -> AxisScore:
    """A missing axis result (weights are filled in later by :func:`aggregate_axes`)."""
    return AxisScore(raw, curve, None, 0.0, 0.0, source, reason)


def _present(curve: str, score: float, *, raw: Any, source: str | None) -> AxisScore:
    return AxisScore(raw, curve, score, 0.0, 0.0, source, None)


# ------------------------------------------------------------------ raw-domain validators


_DIGITS_RE = re.compile(r"[0-9]+")
_NONFINITE_TEXT = frozenset({"nan", "inf", "infinity"})


def validate_score(raw: Any) -> tuple[int | None, str]:
    """Validate a raw readiness/outcome score; return ``(value, reason)``.

    Valid: an ``int`` or a digit string in ``0..100`` (reason ``"valid"``). Absent:
    ``None`` or a blank string (reason ``"absent"``). Everything else is invalid with a
    reason ``"invalid:<why>"``: ``bool``, ``float``, ``negative``, ``above_100``,
    ``nonfinite``, ``signed`` (an explicit ``+``/``-`` prefix on a string that is not a
    negative number), ``non_numeric`` or ``type``. Nothing is clamped or coerced out of
    domain, so an invalid score can never pass a gate or feed a curve.
    """
    if raw is None:
        return None, SCORE_ABSENT
    if isinstance(raw, bool):
        return None, "invalid:bool"
    if isinstance(raw, int):
        return _check_range(raw)
    if isinstance(raw, float):
        return None, "invalid:nonfinite" if not math.isfinite(raw) else "invalid:float"
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None, SCORE_ABSENT
        if _DIGITS_RE.fullmatch(text):
            return _check_range(int(text))
        lowered = text.lower().lstrip("+-")
        if lowered in _NONFINITE_TEXT or lowered == ".inf":
            return None, "invalid:nonfinite"
        if lowered in {"true", "false"}:
            return None, "invalid:bool"
        if text.startswith("-") and _DIGITS_RE.fullmatch(text[1:]):
            return None, "invalid:negative"
        if text[0] in "+-" and _DIGITS_RE.fullmatch(text[1:]):
            return None, "invalid:signed"
        if re.fullmatch(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
            return None, "invalid:float"
        return None, "invalid:non_numeric"
    return None, "invalid:type"


def _check_range(value: int) -> tuple[int | None, str]:
    if value < 0:
        return None, "invalid:negative"
    if value > 100:
        return None, "invalid:above_100"
    return value, SCORE_VALID


def waiver_true(raw: Any) -> bool:
    """True only for boolean ``True`` or the case-insensitive string ``"true"``.

    Other truthy values (``1``, ``"yes"``, non-empty strings) do not waive anything.
    """
    if isinstance(raw, bool):
        return raw
    return isinstance(raw, str) and raw.lower() == "true"


# ------------------------------------------------------------------------------- dates

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
)


def parse_utc_datetime(raw: Any) -> tuple[datetime | None, str | None]:
    """Normalize a date-like value to UTC; return ``(datetime, None)`` or ``(None, reason)``.

    Accepts ``datetime``/``date`` objects and ISO-8601 extended strings (surrounding quotes
    tolerated). Date-only means midnight UTC; no offset means UTC; an offset converts to UTC.
    Reasons: ``absent`` and ``malformed_date``. Future-ness is judged separately against
    ``as_of`` by the caller.
    """
    if raw is None:
        return None, "absent"
    if isinstance(raw, datetime):
        return (raw.replace(tzinfo=UTC) if raw.tzinfo is None else raw.astimezone(UTC)), None
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day, tzinfo=UTC), None
    if not isinstance(raw, str):
        return None, "malformed_date"
    text = raw.strip().strip("\"'").strip()
    if not text:
        return None, "absent"
    if not (_DATE_RE.fullmatch(text) or _TIMESTAMP_RE.fullmatch(text)):
        return None, "malformed_date"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, "malformed_date"
    return (parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)), None


def _require_aware(as_of: datetime) -> datetime:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return as_of.astimezone(UTC)


def _age_days(moment: datetime, as_of: datetime) -> float:
    return (as_of - moment).total_seconds() / _SECONDS_PER_DAY


# ------------------------------------------------------------------------------ priority


def priority_axis(priority_int: int | None, priority: str | None, source: str | None) -> AxisScore:
    """``x = (5 - p) / 5`` -> ``lerp(0.2, 1, x)``; missing/invalid priority stays missing."""
    curve = "lerp(0.2, 1, (5 - priority) / 5)"
    if priority_int is None:
        return axis_missing(curve, "missing_or_invalid_priority")
    x = (5 - priority_int) / 5
    return _present(
        curve,
        lerp(PRIORITY_LO, x),
        raw=priority if priority is not None else f"P{priority_int}",
        source=source or "priority",
    )


# ------------------------------------------------------------------------------ outcome


def outcome_axis(raw: Any) -> AxisScore:
    """``x = outcome_confidence / 100`` -> ``lerp(0.2, 1, x)`` for a valid ``0..100`` value."""
    curve = "lerp(0.2, 1, outcome_confidence / 100)"
    source = "frontmatter:outcome_confidence"
    value, reason = validate_score(raw)
    if value is None:
        return axis_missing(
            curve, f"outcome_confidence_{reason}", raw=_raw_repr(raw), source=source
        )
    return _present(curve, lerp(OUTCOME_LO, value / 100), raw=value, source=source)


def _raw_repr(raw: Any) -> Any:
    """A JSON-safe stand-in for an arbitrary raw frontmatter value."""
    if raw is None or isinstance(raw, (str, bool, int)):
        return raw
    return repr(raw)


# ------------------------------------------------------------------------- readiness gap


def readiness_gap_axis(
    confidence_raw: Any,
    outcome_raw: Any,
    *,
    readiness_threshold: int | None,
    outcome_threshold: int | None,
    outcome_waived: bool,
) -> AxisScore:
    """``x`` = maximum normalized shortfall vs the thresholds -> ``lerp(0.2, 1, x)``.

    Shortfall per score is ``max(0, (threshold - score) / max(threshold, 1))``. Both scores
    must be valid (otherwise the axis is missing); a valid outcome waiver removes the
    outcome shortfall but not the requirement that the outcome score be valid.
    """
    curve = "lerp(0.2, 1, max_shortfall(readiness, outcome))"
    source = "frontmatter:confidence_score,outcome_confidence"
    cs, cs_reason = validate_score(confidence_raw)
    oc, oc_reason = validate_score(outcome_raw)
    if cs is None:
        return axis_missing(curve, f"confidence_score_{cs_reason}", source=source)
    if oc is None:
        return axis_missing(curve, f"outcome_confidence_{oc_reason}", source=source)
    if readiness_threshold is None or outcome_threshold is None:
        return axis_missing(curve, "invalid_threshold", source=source)
    readiness_shortfall = max(0.0, (readiness_threshold - cs) / max(readiness_threshold, 1))
    outcome_shortfall = (
        0.0 if outcome_waived else max(0.0, (outcome_threshold - oc) / max(outcome_threshold, 1))
    )
    x = max(readiness_shortfall, outcome_shortfall)
    raw = {
        "readiness_score": cs,
        "outcome_score": oc,
        "readiness_threshold": readiness_threshold,
        "outcome_threshold": outcome_threshold,
        "outcome_waived": outcome_waived,
        "readiness_shortfall": readiness_shortfall,
        "outcome_shortfall": outcome_shortfall,
        "max_shortfall": x,
    }
    return _present(curve, lerp(READINESS_GAP_LO, x), raw=raw, source=source)


# ------------------------------------------------------------------------------ leverage


def leverage_evidence(lev: Leverage) -> dict[str, Any]:
    """JSON-ready leverage/fan-out evidence (saturation reported, never an invented total)."""
    if lev.saturated:
        display = f"≥{lev.count_lower_bound}"
    elif lev.count is not None:
        display = str(lev.count)
    else:
        display = None
    return {
        "status": lev.status,
        "count": lev.count,
        "count_lower_bound": lev.count_lower_bound,
        "saturated": lev.saturated,
        "display": display,
        "sample": list(lev.sample),
        "missing_reason": lev.missing_reason,
        "in_cycle": lev.in_cycle,
        "cycle_ids": list(lev.cycle_ids),
        "missing_ids": list(lev.missing_ids),
        "ambiguous_ids": list(lev.ambiguous_ids),
    }


def leverage_axis(lev: Leverage) -> AxisScore:
    """``x = min(1, log1p(count) / log1p(10))`` -> ``lerp(0.5, 1, x)``.

    Zero dependents is a valid present value (score ``0.5``). A saturated count scores the
    ceiling without inventing an exact total; ambiguous/unknown fan-out stays missing.
    """
    curve = "lerp(0.5, 1, min(1, log1p(count) / log1p(10)))"
    source = "dependency_graph"
    evidence = leverage_evidence(lev)
    if lev.status == "missing":
        return axis_missing(
            curve, lev.missing_reason or "leverage_missing", raw=evidence, source=source
        )
    if lev.status == "saturated":
        x = 1.0
    else:
        count = lev.count if lev.count is not None else 0
        x = min(1.0, math.log1p(count) / math.log1p(LEVERAGE_SATURATION))
    return _present(curve, lerp(LEVERAGE_LO, x), raw=evidence, source=source)


# -------------------------------------------------------------------------------- effort

_EFFORT_TOKENS: Mapping[str, int] = MappingProxyType(
    {
        "trivial": 1,
        "small": 1,
        "low": 1,
        "s": 1,
        "medium": 2,
        "m": 2,
        "large": 3,
        "high": 3,
        "l": 3,
    }
)
_H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# Both label spellings: ``- **Effort**: ...`` (2,795 files) and ``- **Effort:** ...`` (21).
_EFFORT_LINE_RE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?\*\*Effort(?:\*\*[ \t]*:|:[ \t]*\*\*)[ \t]*(.*?)[ \t]*$",
    re.MULTILINE,
)
_LEADING_MARKUP = " \t*_`\"'("
_LEADING_TOKEN_RE = re.compile(r"[^\W\d_]+")


@dataclass(frozen=True)
class EffortParse:
    """Result of :func:`parse_effort` (``level`` is ``1..3`` or ``None``)."""

    text: str | None
    level: int | None
    reason: str | None


def _impact_section(content: str) -> str | None:
    headings = list(_H2_RE.finditer(content))
    for index, match in enumerate(headings):
        if match.group(1).strip().lower() == "impact":
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            return content[match.end() : end]
    return None


def parse_effort(content: str) -> EffortParse:
    """Parse the Impact-section ``Effort`` field with the strict leading-token map.

    Case-insensitive: ``trivial``/``small``/``low``/``s`` -> 1, ``medium``/``m`` -> 2,
    ``large``/``high``/``l`` -> 3. A range (``small-medium``, ``Medium–Large``) or trailing
    prose takes its first alphabetic token; anything else is missing with the raw text
    retained. Never reads ``IssueInfo.effort`` and never infers effort from priority.
    """
    section = _impact_section(content)
    if section is None:
        return EffortParse(None, None, "no_impact_section")
    match = _EFFORT_LINE_RE.search(section)
    if match is None:
        return EffortParse(None, None, "absent")
    text = match.group(1)
    if not text:
        return EffortParse(None, None, "absent")
    token_match = _LEADING_TOKEN_RE.match(text.lstrip(_LEADING_MARKUP))
    token = token_match.group(0).lower() if token_match else ""
    level = _EFFORT_TOKENS.get(token)
    if level is None:
        return EffortParse(text, None, f"unknown_effort_token: {text!r}")
    return EffortParse(text, level, None)


def effort_axis(content: str) -> AxisScore:
    """Score ``1 / effort`` from the Impact-section ``Effort`` field (unknown => missing)."""
    curve = "1 / effort_level"
    source = "impact_section:Effort"
    parsed = parse_effort(content)
    if parsed.level is None:
        return axis_missing(
            curve,
            parsed.reason or "absent",
            raw=parsed.text,
            source=source if parsed.text else None,
        )
    return _present(curve, 1.0 / parsed.level, raw=parsed.text, source=source)


# ----------------------------------------------------------------------------- staleness


def staleness_axis(captured_at_raw: Any, discovered_date_raw: Any, as_of: datetime) -> AxisScore:
    """``x = min(1, age_days / 30)`` from ``captured_at`` then ``discovered_date``.

    The first *valid* date at/before ``as_of`` wins; a missing, malformed or future-only date
    makes the axis missing with the reasons listed. No git history and no file mtime.
    """
    curve = "lerp(0.3, 1, min(1, age_days / 30))"
    now = _require_aware(as_of)
    reasons: list[str] = []
    for field_name, raw in (
        ("captured_at", captured_at_raw),
        ("discovered_date", discovered_date_raw),
    ):
        moment, reason = parse_utc_datetime(raw)
        if moment is None:
            reasons.append(f"{field_name}_{reason}")
            continue
        if moment > now:
            reasons.append(f"{field_name}_future_date")
            continue
        age = _age_days(moment, now)
        x = min(1.0, age / STALENESS_FULL_DAYS)
        evidence = {"date": moment.isoformat(), "age_days": age}
        return _present(
            curve, lerp(STALENESS_LO, x), raw=evidence, source=f"frontmatter:{field_name}"
        )
    return axis_missing(curve, "; ".join(reasons) or "absent")


# ----------------------------------------------------------------------------- momentum


def latest_session_timestamp(
    session_body: str | None, as_of: datetime
) -> tuple[datetime | None, str | None]:
    """Latest valid Session Log timestamp at/before *as_of* (any ``/ll:*`` command).

    *session_body* is the ``## Session Log`` body (``session_log_body(content)``).
    Entries are matched with ``session_log._TIMESTAMPED_ENTRY_RE``; a date-only stamp means
    midnight UTC and a stamp without an offset is read as UTC (matching
    ``last_command_timestamp``). Stamps later than *as_of* are ignored. Returns
    ``(None, reason)`` with ``no_session_log``, ``no_timestamped_entries`` or ``future_only``.
    """
    now = _require_aware(as_of)
    if session_body is None:
        return None, "no_session_log"
    found = 0
    future = 0
    latest: datetime | None = None
    for entry in _TIMESTAMPED_ENTRY_RE.finditer(session_body):
        moment, _reason = parse_utc_datetime(entry.group(2).rstrip("Z"))
        if moment is None:
            continue
        found += 1
        if moment > now:
            future += 1
            continue
        if latest is None or moment > latest:
            latest = moment
    if latest is not None:
        return latest, None
    if found == 0:
        return None, "no_timestamped_entries"
    return None, "future_only"


def momentum_axis(session_body: str | None, as_of: datetime) -> AxisScore:
    """``x = exp(-ln2 * age_days / 7)`` from the latest valid Session Log timestamp."""
    curve = "lerp(0.3, 1, exp(-ln(2) * age_days / 7))"
    source = "session_log"
    moment, reason = latest_session_timestamp(session_body, as_of)
    if moment is None:
        return axis_missing(curve, reason or "absent")
    age = _age_days(moment, _require_aware(as_of))
    x = math.exp(-math.log(2) * age / MOMENTUM_HALF_LIFE_DAYS)
    return _present(
        curve,
        lerp(MOMENTUM_LO, x),
        raw={"timestamp": moment.isoformat(), "age_days": age},
        source=source,
    )


def latest_session_timestamp_from_content(
    content: str, as_of: datetime
) -> tuple[datetime | None, str | None]:
    """:func:`latest_session_timestamp` over a full issue file's text."""
    return latest_session_timestamp(session_log_body(content), as_of)


# ------------------------------------------------------------------ per-record computation


def compute_issue_axes(
    record: SourceRecord,
    *,
    leverage: Leverage,
    as_of: datetime,
    readiness_threshold: int | None,
    outcome_threshold: int | None,
) -> dict[str, AxisScore]:
    """Every raw axis result for one record, keyed by axis identifier (unweighted).

    The mapping holds the union of both registered verbs' axes (``priority``, ``outcome``,
    ``readiness_gap``, ``leverage``, ``effort``, ``staleness``, ``momentum``); callers pass it
    to :func:`aggregate_axes`, which selects and orders each verb's axes.
    """
    return {
        "priority": priority_axis(record.priority_int, record.priority, record.priority_source),
        "outcome": outcome_axis(record.outcome_confidence_raw),
        "readiness_gap": readiness_gap_axis(
            record.confidence_score_raw,
            record.outcome_confidence_raw,
            readiness_threshold=readiness_threshold,
            outcome_threshold=outcome_threshold,
            outcome_waived=waiver_true(record.outcome_gate_waived_raw),
        ),
        "leverage": leverage_axis(leverage),
        "effort": effort_axis(record.content),
        "staleness": staleness_axis(record.captured_at_raw, record.discovered_date_raw, as_of),
        "momentum": momentum_axis(record.session_log, as_of),
    }


# ------------------------------------------------------------------------- loop history

#: Statuses whose runs count toward the success fraction (all others are non-terminal or
#: unknown and are never failures).
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "timed_out"})


def loop_frequency_axis(run_count: int) -> AxisScore:
    """``x = min(1, log1p(count) / log1p(50))`` -> ``lerp(0.4, 1, x)`` over qualified runs.

    A thin adapter over the FEAT-3681 curve primitive (:func:`frequency_score`), bounded as
    the arena requires. No qualifying run is *missing* (cold start), never a present zero.
    """
    curve = "lerp(0.4, 1, min(1, log1p(run_count) / log1p(50)))"
    source = "filesystem_history"
    if run_count <= 0:
        return axis_missing(curve, "no_qualifying_runs", raw=0, source=source)
    x = min(1.0, frequency_score(run_count))
    return _present(curve, lerp(FREQUENCY_LO, x), raw=run_count, source=source)


def loop_recency_axis(latest_start: datetime | None, as_of: datetime) -> AxisScore:
    """``x = exp(-ln2 * age_days / 7)`` of the latest qualified start -> ``lerp(0.2, 1, x)``."""
    curve = "lerp(0.2, 1, exp(-ln(2) * age_days / 7))"
    source = "filesystem_history"
    if latest_start is None:
        return axis_missing(curve, "no_qualifying_runs", source=source)
    now = _require_aware(as_of)
    stamp = latest_start.astimezone(UTC).isoformat()
    x = min(1.0, recency_score(stamp, as_of=now))
    evidence = {"timestamp": stamp, "age_days": _age_days(latest_start, now)}
    return _present(curve, lerp(RECENCY_LO, x), raw=evidence, source=source)


def loop_success_axis(completed: int, terminal: int) -> AxisScore:
    """``x = completed / terminal`` over recognized terminal runs -> ``lerp(0.2, 1, x)``.

    ``terminal`` counts ``completed``/``failed``/``timed_out`` runs only; interrupted,
    in-flight and unknown statuses do not count as failures. No terminal run is missing.
    """
    curve = "lerp(0.2, 1, completed / terminal_runs)"
    source = "filesystem_history"
    if terminal <= 0:
        return axis_missing(curve, "no_terminal_runs", source=source)
    x = completed / terminal
    raw = {"completed": completed, "terminal_runs": terminal, "success_fraction": x}
    return _present(curve, lerp(SUCCESS_LO, x), raw=raw, source=source)


def compute_loop_axes(
    *,
    run_count: int,
    latest_start: datetime | None,
    completed: int,
    terminal: int,
    as_of: datetime,
    history_available: bool = True,
) -> dict[str, AxisScore]:
    """The three loop axes from a loop's qualified-run summary (unweighted).

    All three are missing when *run_count* is zero or the history was unavailable (the
    latter reason is reported so unavailable evidence never reads as "never ran").
    """
    if not history_available:
        reason = "history_unavailable"
        return {
            axis: axis_missing(curve, reason, source="filesystem_history")
            for axis, curve in (("frequency", ""), ("recency", ""), ("success", ""))
        }
    if run_count <= 0:  # cold start: no qualifying run at all, so all three are missing
        return {
            "frequency": loop_frequency_axis(0),
            "recency": loop_recency_axis(None, as_of),
            "success": axis_missing(
                "lerp(0.2, 1, completed / terminal_runs)",
                "no_qualifying_runs",
                source="filesystem_history",
            ),
        }
    return {
        "frequency": loop_frequency_axis(run_count),
        "recency": loop_recency_axis(latest_start, as_of),
        "success": loop_success_axis(completed, terminal),
    }


# -------------------------------------------------------------------------- aggregation


@dataclass(frozen=True)
class AxisAggregate:
    """Weighted axes of one verb in canonical order plus the aggregate and coverage.

    ``utility`` is the weighted geometric mean over present positive-weight axes
    (``None`` when none resolved). ``resolved_axes`` / ``applicable_axes`` count
    positive-weight axes only; ``coverage`` is the display string (e.g. ``"4/5"``).
    """

    axes: Mapping[str, AxisScore]
    utility: float | None
    resolved_axes: int
    applicable_axes: int

    @property
    def coverage(self) -> str:
        """Display string ``"resolved/applicable"``."""
        return f"{self.resolved_axes}/{self.applicable_axes}"


def aggregate_axes(
    verb: str, weights: Mapping[str, float], results: Mapping[str, AxisScore]
) -> AxisAggregate:
    """Build *verb*'s ``axes`` in canonical order and aggregate them geometrically.

    Args:
        verb: A registered verb name (its registry entry fixes the axis set and order).
        weights: Resolved settings weights for that verb (``ArenaSettings.weights[verb]``).
        results: Raw per-axis results (a superset keyed by axis identifier is fine; an axis
            of the verb that is absent from *results* is treated as missing).

    Effective weights renormalize the configured positive weights over the axes that
    resolved. There is no make-up term and no coverage multiplier.
    """
    spec = get_verb(verb)
    ordered: dict[str, AxisScore] = {}
    for axis in spec.axes:
        base = results.get(axis) or axis_missing("", "not_computed")
        ordered[axis] = replace(
            base, configured_weight=float(weights.get(axis, spec.default_weights[axis]))
        )
    scores = {axis: item.score for axis, item in ordered.items()}
    configured = {axis: item.configured_weight for axis, item in ordered.items()}
    total = sum(w for a, w in configured.items() if w > 0 and scores[a] is not None)
    final: dict[str, AxisScore] = {}
    for axis, item in ordered.items():
        weight = configured[axis]
        effective = weight / total if total > 0 and weight > 0 and item.score is not None else 0.0
        final[axis] = replace(item, effective_weight=effective)
    utility = weighted_geometric(scores, configured)
    applicable = sum(1 for w in configured.values() if w > 0)
    resolved = sum(1 for a, w in configured.items() if w > 0 and scores[a] is not None)
    return AxisAggregate(
        axes=MappingProxyType(final),
        utility=_json_number(utility),
        resolved_axes=resolved,
        applicable_axes=applicable,
    )


def minimum_evidence_met(axes: Mapping[str, AxisScore]) -> bool:
    """Numeric utility needs a valid priority plus one resolved positive-weight non-priority axis.

    Priority validity is metadata: a zero configured priority weight does not disable the
    prerequisite (nor force an otherwise scorable issue into fallback ordering).
    """
    priority = axes.get("priority")
    if priority is None or priority.score is None:
        return False
    return any(
        axis != "priority" and item.score is not None and item.configured_weight > 0
        for axis, item in axes.items()
    )


def loop_minimum_evidence_met(axes: Mapping[str, AxisScore]) -> bool:
    """Numeric loop utility needs at least one resolved positive-weight history axis."""
    return any(item.score is not None and item.configured_weight > 0 for item in axes.values())

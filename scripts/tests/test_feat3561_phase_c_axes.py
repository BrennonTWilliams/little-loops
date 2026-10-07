"""Raw-domain validators, date normalization and bounded axis curves (FEAT-3561 phase C)."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest

from little_loops.next_arena.axes import (
    AXIS_BOUNDS,
    AxisScore,
    effort_axis,
    latest_session_timestamp,
    latest_session_timestamp_from_content,
    lerp,
    leverage_axis,
    leverage_evidence,
    momentum_axis,
    outcome_axis,
    parse_effort,
    parse_utc_datetime,
    priority_axis,
    readiness_gap_axis,
    staleness_axis,
    validate_score,
    waiver_true,
)
from little_loops.next_arena.graph import Leverage

AS_OF = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


# ------------------------------------------------------------------------ validate_score


@pytest.mark.parametrize(
    ("raw", "value"),
    [(0, 0), (85, 85), (100, 100), ("0", 0), ("85", 85), ("100", 100), (" 70 ", 70), ("085", 85)],
)
def test_validate_score_accepts_integer_domain(raw: Any, value: int) -> None:
    assert validate_score(raw) == (value, "valid")


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_validate_score_absent(raw: Any) -> None:
    assert validate_score(raw) == (None, "absent")


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (True, "invalid:bool"),
        (False, "invalid:bool"),
        ("true", "invalid:bool"),
        (85.0, "invalid:float"),
        (85.5, "invalid:float"),
        ("85.5", "invalid:float"),
        ("1e2", "invalid:non_numeric"),
        (-1, "invalid:negative"),
        ("-5", "invalid:negative"),
        (101, "invalid:above_100"),
        ("101", "invalid:above_100"),
        ("99999999999999999999", "invalid:above_100"),
        (float("nan"), "invalid:nonfinite"),
        (float("inf"), "invalid:nonfinite"),
        ("nan", "invalid:nonfinite"),
        (".inf", "invalid:nonfinite"),
        ("-inf", "invalid:nonfinite"),
        ("+85", "invalid:signed"),
        ("eighty", "invalid:non_numeric"),
        ("85%", "invalid:non_numeric"),
        ("٥", "invalid:non_numeric"),  # non-ASCII digit
        ([85], "invalid:type"),
        ({"a": 1}, "invalid:type"),
    ],
)
def test_validate_score_rejects_out_of_domain(raw: Any, reason: str) -> None:
    value, got = validate_score(raw)
    assert value is None
    assert got == reason


def test_validate_score_distinguishes_absent_from_invalid() -> None:
    assert validate_score(None)[1] == "absent"
    assert validate_score(101)[1].startswith("invalid:")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        ("true", True),
        ("TRUE", True),
        ("True", True),
        (False, False),
        ("false", False),
        (None, False),
        (1, False),
        ("yes", False),
        ("1", False),
        (" true", False),
        ([True], False),
    ],
)
def test_waiver_true_is_bool_true_or_string_true_only(raw: Any, expected: bool) -> None:
    assert waiver_true(raw) is expected


# ------------------------------------------------------------------------------- dates


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-08-01", datetime(2026, 8, 1, tzinfo=UTC)),
        ('"2026-08-01"', datetime(2026, 8, 1, tzinfo=UTC)),
        ("2026-08-01T12:30:00", datetime(2026, 8, 1, 12, 30, tzinfo=UTC)),
        ("2026-08-01T12:30:00Z", datetime(2026, 8, 1, 12, 30, tzinfo=UTC)),
        ("2026-08-01T12:30:00+02:00", datetime(2026, 8, 1, 10, 30, tzinfo=UTC)),
        ("2026-08-01T12:30:00.250", datetime(2026, 8, 1, 12, 30, 0, 250000, tzinfo=UTC)),
        (date(2026, 8, 1), datetime(2026, 8, 1, tzinfo=UTC)),
        (datetime(2026, 8, 1, 3, 0), datetime(2026, 8, 1, 3, 0, tzinfo=UTC)),
        (
            datetime(2026, 8, 1, 3, 0, tzinfo=timezone(timedelta(hours=-5))),
            datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
        ),
    ],
)
def test_parse_utc_datetime_normalizes_to_utc(raw: Any, expected: datetime) -> None:
    moment, reason = parse_utc_datetime(raw)
    assert reason is None
    assert moment == expected
    assert moment is not None
    assert moment.utcoffset() == timedelta(0)


@pytest.mark.parametrize("raw", ["2026-13-45", "yesterday", "08/01/2026", "2026-8-1", 20260801, []])
def test_parse_utc_datetime_malformed(raw: Any) -> None:
    assert parse_utc_datetime(raw) == (None, "malformed_date")


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_parse_utc_datetime_absent(raw: Any) -> None:
    assert parse_utc_datetime(raw) == (None, "absent")


# ------------------------------------------------------------------------------ priority


@pytest.mark.parametrize(
    ("priority", "expected"),
    [(0, 1.0), (1, 0.84), (2, 0.68), (3, 0.52), (4, 0.36), (5, 0.2)],
)
def test_priority_curve(priority: int, expected: float) -> None:
    axis = priority_axis(priority, f"P{priority}", "filename")
    assert axis.score == pytest.approx(expected)
    assert axis.raw == f"P{priority}"
    assert axis.source == "filename"
    assert axis.missing_reason is None


def test_priority_missing_is_not_p5() -> None:
    axis = priority_axis(None, None, None)
    assert axis.score is None
    assert axis.missing_reason == "missing_or_invalid_priority"


def test_p5_is_floored_not_vetoed() -> None:
    assert priority_axis(5, "P5", "filename").score == pytest.approx(0.2)


# ------------------------------------------------------------------------------ outcome


@pytest.mark.parametrize(("raw", "expected"), [(0, 0.2), ("50", 0.6), (100, 1.0), ("100", 1.0)])
def test_outcome_curve(raw: Any, expected: float) -> None:
    axis = outcome_axis(raw)
    assert axis.score == pytest.approx(expected)
    assert axis.source == "frontmatter:outcome_confidence"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "outcome_confidence_absent"),
        (101, "outcome_confidence_invalid:above_100"),
        (True, "outcome_confidence_invalid:bool"),
        (7.5, "outcome_confidence_invalid:float"),
    ],
)
def test_outcome_missing_reasons_distinguish_absent_and_invalid(raw: Any, reason: str) -> None:
    axis = outcome_axis(raw)
    assert axis.score is None
    assert axis.missing_reason == reason


def test_zero_outcome_is_present_not_missing() -> None:
    axis = outcome_axis("0")
    assert axis.score == pytest.approx(0.2)
    assert axis.missing_reason is None


# ---------------------------------------------------------------------- readiness_gap


def _gap(cs: Any, oc: Any, *, waived: bool = False, r: int | None = 85, o: int | None = 65):
    return readiness_gap_axis(
        cs, oc, readiness_threshold=r, outcome_threshold=o, outcome_waived=waived
    )


def test_readiness_gap_ready_issue_scores_floor() -> None:
    axis = _gap(90, 70)
    assert axis.score == pytest.approx(0.2)
    assert axis.raw["max_shortfall"] == 0.0


def test_readiness_gap_uses_max_normalized_shortfall() -> None:
    # readiness shortfall (85-60)/85 ~ 0.294; outcome shortfall (65-13)/65 = 0.8
    axis = _gap(60, 13)
    assert axis.raw["readiness_shortfall"] == pytest.approx(25 / 85)
    assert axis.raw["outcome_shortfall"] == pytest.approx(0.8)
    assert axis.score == pytest.approx(lerp(0.2, 0.8))


def test_readiness_gap_total_shortfall_hits_the_ceiling() -> None:
    assert _gap(0, 0).score == pytest.approx(1.0)


def test_readiness_gap_waiver_removes_outcome_shortfall_only() -> None:
    waived = _gap(90, 10, waived=True)
    assert waived.raw["outcome_shortfall"] == 0.0
    assert waived.score == pytest.approx(0.2)
    # readiness shortfall still counts under a waiver
    assert _gap(60, 10, waived=True).raw["max_shortfall"] == pytest.approx(25 / 85)


def test_readiness_gap_waiver_does_not_excuse_missing_outcome() -> None:
    axis = _gap(90, None, waived=True)
    assert axis.score is None
    assert axis.missing_reason == "outcome_confidence_absent"


@pytest.mark.parametrize(
    ("cs", "oc", "reason"),
    [
        (None, 70, "confidence_score_absent"),
        (90, None, "outcome_confidence_absent"),
        (101, 70, "confidence_score_invalid:above_100"),
        (90, "x", "outcome_confidence_invalid:non_numeric"),
    ],
)
def test_readiness_gap_requires_both_valid_scores(cs: Any, oc: Any, reason: str) -> None:
    axis = _gap(cs, oc)
    assert axis.score is None
    assert axis.missing_reason == reason


def test_readiness_gap_zero_threshold_does_not_divide_by_zero() -> None:
    assert _gap(0, 0, r=0, o=0).score == pytest.approx(0.2)


def test_readiness_gap_invalid_threshold_is_missing() -> None:
    assert _gap(90, 70, r=None).missing_reason == "invalid_threshold"


def test_readiness_gap_honors_overridden_thresholds() -> None:
    assert _gap(70, 50, r=70, o=50).score == pytest.approx(0.2)
    assert _gap(70, 50, r=90, o=50).score > 0.2


# ------------------------------------------------------------------------------ leverage


def _lev(**kw: Any) -> Leverage:
    base: dict[str, Any] = {
        "issue_id": "FEAT-001",
        "status": "exact",
        "cap": 10,
        "count": 0,
        "count_lower_bound": None,
        "saturated": False,
        "sample": (),
        "missing_reason": None,
        "partial_count": 0,
        "in_cycle": False,
        "cycle_ids": (),
        "missing_ids": (),
        "ambiguous_ids": (),
    }
    base.update(kw)
    return Leverage(**base)


def test_zero_dependents_is_valid_half_score() -> None:
    axis = leverage_axis(_lev(count=0))
    assert axis.score == pytest.approx(0.5)
    assert axis.missing_reason is None
    assert axis.raw["display"] == "0"


@pytest.mark.parametrize("count", [1, 3, 9])
def test_leverage_curve(count: int) -> None:
    axis = leverage_axis(_lev(count=count, sample=tuple(f"X-{i}" for i in range(count))))
    expected = 0.5 + 0.5 * min(1.0, math.log1p(count) / math.log1p(10))
    assert axis.score == pytest.approx(expected)
    assert axis.raw["count"] == count


def test_leverage_saturation_reports_lower_bound_not_total() -> None:
    lev = _lev(
        status="saturated",
        count=None,
        count_lower_bound=10,
        saturated=True,
        sample=tuple(f"X-{i}" for i in range(10)),
        partial_count=10,
    )
    axis = leverage_axis(lev)
    assert axis.score == pytest.approx(1.0)
    assert axis.raw["count"] is None
    assert axis.raw["count_lower_bound"] == 10
    assert axis.raw["saturated"] is True
    assert axis.raw["display"] == "≥10"
    assert len(axis.raw["sample"]) == 10


def test_leverage_missing_keeps_reason_and_evidence() -> None:
    lev = _lev(status="missing", count=None, missing_reason="ambiguous_downstream", partial_count=2)
    axis = leverage_axis(lev)
    assert axis.score is None
    assert axis.missing_reason == "ambiguous_downstream"
    assert axis.raw["status"] == "missing"


def test_leverage_evidence_is_json_ready() -> None:
    evidence = leverage_evidence(_lev(count=1, sample=("A-1",), cycle_ids=("A-1",)))
    assert json.loads(json.dumps(evidence)) == evidence


# -------------------------------------------------------------------------------- effort


def _impact(effort_line: str | None) -> str:
    lines = ["# T", "", "## Summary", "x", "", "## Impact", "", "- **Priority**: P3"]
    if effort_line is not None:
        lines.append(effort_line)
    lines.extend(["- **Risk**: Low", "", "## Other", "- **Effort**: Large"])
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("label", ["- **Effort**: {}", "- **Effort:** {}"])
@pytest.mark.parametrize(
    ("value", "level"),
    [
        ("Trivial", 1),
        ("Small", 1),
        ("low", 1),
        ("S", 1),
        ("Medium", 2),
        ("m", 2),
        ("LARGE", 3),
        ("High", 3),
        ("l", 3),
        ("small — one afternoon", 1),
        ("small-medium", 1),
        ("Medium–Large", 2),
        ("Medium - Large", 2),
        ("**Medium**", 2),
        ("Large (2 weeks)", 3),
    ],
)
def test_effort_both_label_spellings_and_strict_map(label: str, value: str, level: int) -> None:
    parsed = parse_effort(_impact(label.format(value)))
    assert parsed.level == level
    assert parsed.reason is None
    axis = effort_axis(_impact(label.format(value)))
    assert axis.score == pytest.approx(1.0 / level)
    assert axis.missing_reason is None


@pytest.mark.parametrize("value", ["Huge", "XL", "2 days", "1-2 days", "Mediumish", "?", "TBD"])
def test_effort_unknown_is_missing_with_raw_text_retained(value: str) -> None:
    axis = effort_axis(_impact(f"- **Effort**: {value}"))
    assert axis.score is None
    assert axis.raw == value
    assert axis.missing_reason is not None
    assert axis.missing_reason.startswith("unknown_effort_token")
    assert value in axis.missing_reason


def test_effort_absent_cases_are_missing() -> None:
    assert effort_axis(_impact(None)).missing_reason == "absent"
    assert effort_axis("# T\n\n## Summary\nno impact\n").missing_reason == "no_impact_section"
    assert effort_axis(_impact("- **Effort**:")).missing_reason == "absent"


def test_effort_only_reads_the_impact_section() -> None:
    content = "## Other\n- **Effort**: Large\n\n## Impact\n- **Priority**: P3\n"
    assert effort_axis(content).missing_reason == "absent"


def test_effort_ignores_priority_and_frontmatter() -> None:
    content = "---\neffort: 3\npriority: P0\n---\n## Impact\n- **Priority**: P0\n"
    assert effort_axis(content).score is None


# ----------------------------------------------------------------------------- staleness


def test_staleness_fresh_issue_scores_floor_not_veto() -> None:
    axis = staleness_axis("2026-10-07", None, AS_OF)
    assert axis.score == pytest.approx(0.3 + 0.7 * (0.5 / 30))
    assert axis.source == "frontmatter:captured_at"


def test_staleness_full_at_thirty_days_and_capped() -> None:
    assert staleness_axis("2026-09-07T12:00:00", None, AS_OF).score == pytest.approx(1.0)
    assert staleness_axis("2025-01-01", None, AS_OF).score == pytest.approx(1.0)


def test_staleness_linear_midpoint() -> None:
    captured = (AS_OF - timedelta(days=15)).isoformat()
    assert staleness_axis(captured, None, AS_OF).score == pytest.approx(lerp(0.3, 0.5))


def test_staleness_exactly_as_of_is_age_zero() -> None:
    axis = staleness_axis(AS_OF.isoformat(), None, AS_OF)
    assert axis.score == pytest.approx(0.3)


def test_staleness_falls_back_to_discovered_date() -> None:
    axis = staleness_axis(None, "2026-09-07", AS_OF)
    assert axis.source == "frontmatter:discovered_date"
    assert axis.score is not None


def test_staleness_captured_at_wins_when_both_valid() -> None:
    axis = staleness_axis("2026-10-06", "2020-01-01", AS_OF)
    assert axis.source == "frontmatter:captured_at"


def test_staleness_future_captured_at_falls_through_to_valid_discovered_date() -> None:
    axis = staleness_axis("2026-12-01", "2026-09-07", AS_OF)
    assert axis.source == "frontmatter:discovered_date"


def test_staleness_future_only_is_missing_with_reason() -> None:
    axis = staleness_axis("2026-12-01", "2027-01-01", AS_OF)
    assert axis.score is None
    assert axis.missing_reason == "captured_at_future_date; discovered_date_future_date"


def test_staleness_malformed_and_absent_reasons() -> None:
    axis = staleness_axis("soon", None, AS_OF)
    assert axis.score is None
    assert axis.missing_reason == "captured_at_malformed_date; discovered_date_absent"


def test_staleness_requires_aware_as_of() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        staleness_axis("2026-10-01", None, datetime(2026, 10, 7))


def test_staleness_uses_no_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    a = staleness_axis("2026-09-20", None, AS_OF)
    b = staleness_axis("2026-09-20", None, AS_OF)
    assert a == b


# ----------------------------------------------------------------------------- momentum


def _log(*entries: str) -> str:
    return "\n".join(["# T", "", "## Session Log", *entries, ""]) + "\n"


def test_momentum_latest_of_any_command() -> None:
    content = _log(
        "- `/ll:refine-issue` - 2026-10-01T12:00:00 - `a.jsonl`",
        "- `/ll:confidence-check` - 2026-10-06T12:00:00 - `b.jsonl`",
        "- `/ll:format-issue` - 2026-09-01T12:00:00 - `c.jsonl`",
    )
    moment, reason = latest_session_timestamp_from_content(content, AS_OF)
    assert reason is None
    assert moment == datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def test_momentum_half_life_is_seven_days() -> None:
    stamp = (AS_OF - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    axis = momentum_axis(_log(f"- `/ll:refine-issue` - {stamp} - `a.jsonl`"), AS_OF)
    assert axis.score == pytest.approx(lerp(0.3, 0.5))
    assert axis.raw["age_days"] == pytest.approx(7.0)


def test_momentum_age_zero_scores_one() -> None:
    stamp = AS_OF.strftime("%Y-%m-%dT%H:%M:%S")
    axis = momentum_axis(_log(f"- `/ll:refine-issue` - {stamp} - `a.jsonl`"), AS_OF)
    assert axis.score == pytest.approx(1.0)


def test_momentum_old_activity_floors_at_lo() -> None:
    axis = momentum_axis(_log("- `/ll:capture-issue` - 2020-01-01"), AS_OF)
    assert axis.score == pytest.approx(0.3, abs=1e-6)
    assert axis.score is not None and axis.score >= 0.3


def test_momentum_date_only_is_midnight_utc_and_offsetless_is_utc() -> None:
    body = _log("- `/ll:capture-issue` - 2026-10-07")
    moment, _ = latest_session_timestamp_from_content(body, AS_OF)
    assert moment == datetime(2026, 10, 7, tzinfo=UTC)
    body = _log("- `/ll:refine-issue` - 2026-10-07T01:02:03 - `a.jsonl`")
    moment, _ = latest_session_timestamp_from_content(body, AS_OF)
    assert moment == datetime(2026, 10, 7, 1, 2, 3, tzinfo=UTC)
    body = _log("- `/ll:refine-issue` - 2026-10-07T01:02:03Z - `a.jsonl`")
    moment, _ = latest_session_timestamp_from_content(body, AS_OF)
    assert moment == datetime(2026, 10, 7, 1, 2, 3, tzinfo=UTC)


def test_momentum_ignores_future_entries_but_uses_earlier_ones() -> None:
    content = _log(
        "- `/ll:refine-issue` - 2026-12-01T00:00:00 - `a.jsonl`",
        "- `/ll:refine-issue` - 2026-10-05T00:00:00 - `b.jsonl`",
    )
    moment, reason = latest_session_timestamp_from_content(content, AS_OF)
    assert reason is None
    assert moment == datetime(2026, 10, 5, tzinfo=UTC)


def test_momentum_future_only_is_missing() -> None:
    content = _log("- `/ll:refine-issue` - 2027-01-01T00:00:00 - `a.jsonl`")
    axis = momentum_axis(latest_body(content), AS_OF)
    assert axis.score is None
    assert axis.missing_reason == "future_only"


def latest_body(content: str) -> str | None:
    from little_loops.session_log import session_log_body

    return session_log_body(content)


def test_momentum_missing_reasons() -> None:
    assert momentum_axis(None, AS_OF).missing_reason == "no_session_log"
    assert momentum_axis("", AS_OF).missing_reason == "no_timestamped_entries"
    body = latest_body(_log("- some prose without a command"))
    assert momentum_axis(body, AS_OF).missing_reason == "no_timestamped_entries"
    assert latest_session_timestamp(None, AS_OF) == (None, "no_session_log")


def test_momentum_ignores_fenced_and_other_section_entries() -> None:
    content = (
        "# T\n\n## Notes\n- `/ll:refine-issue` - 2026-10-06T00:00:00 - `x`\n\n"
        "## Session Log\n- `/ll:refine-issue` - 2026-09-01T00:00:00 - `y`\n"
    )
    moment, _ = latest_session_timestamp_from_content(content, AS_OF)
    assert moment == datetime(2026, 9, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------- serialization


def test_axis_score_to_dict_is_deterministic_and_json_safe() -> None:
    axis = AxisScore(
        raw={"a": 1},
        curve="c",
        score=0.5,
        configured_weight=0.3,
        effective_weight=0.25,
        source="s",
        missing_reason=None,
    )
    data = axis.to_dict()
    assert list(data) == [
        "raw",
        "curve",
        "score",
        "configured_weight",
        "effective_weight",
        "source",
        "missing_reason",
    ]
    assert json.dumps(data, allow_nan=False) == json.dumps(axis.to_dict(), allow_nan=False)


def test_axis_score_missing_serializes_none_never_nan() -> None:
    axis = AxisScore(None, "c", None, 0.3, 0.0, None, "absent")
    assert axis.to_dict()["score"] is None
    bad = AxisScore(None, "c", float("nan"), float("inf"), float("-inf"), None, None)
    data = bad.to_dict()
    assert data["score"] is None
    assert data["configured_weight"] is None
    assert data["effective_weight"] is None
    json.dumps(data, allow_nan=False)


@pytest.mark.parametrize("axis", sorted(AXIS_BOUNDS))
def test_axis_bounds_table_matches_documented_floors(axis: str) -> None:
    worst, best = AXIS_BOUNDS[axis]
    assert 0 < worst < best == 1.0

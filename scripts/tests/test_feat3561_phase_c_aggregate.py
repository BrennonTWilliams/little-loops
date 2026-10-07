"""Weighted aggregation, coverage and the bounded-curve property tests (FEAT-3561 phase C)."""

from __future__ import annotations

import itertools
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from little_loops.config.features import NextConfig, NextConfigError
from little_loops.next_arena.axes import (
    AXIS_BOUNDS,
    AxisScore,
    aggregate_axes,
    axis_missing,
    effort_axis,
    leverage_axis,
    minimum_evidence_met,
    momentum_axis,
    outcome_axis,
    priority_axis,
    readiness_gap_axis,
    staleness_axis,
)
from little_loops.next_arena.graph import Leverage
from little_loops.next_arena.registry import REGISTRY, registered_verbs
from little_loops.utility import weighted_geometric

AS_OF = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _present(score: float) -> AxisScore:
    return AxisScore(None, "c", score, 0.0, 0.0, "s", None)


def _lev(count: int | None, **kw: Any) -> Leverage:
    base: dict[str, Any] = {
        "issue_id": "FEAT-001",
        "status": "exact",
        "cap": 10,
        "count": count,
        "count_lower_bound": None,
        "saturated": False,
        "sample": (),
        "missing_reason": None,
        "partial_count": count or 0,
        "in_cycle": False,
        "cycle_ids": (),
        "missing_ids": (),
        "ambiguous_ids": (),
    }
    base.update(kw)
    return Leverage(**base)


def _defaults(verb: str) -> dict[str, float]:
    return dict(REGISTRY[verb].default_weights)


# ------------------------------------------------------------------------ weights table


@pytest.mark.parametrize("verb", registered_verbs())
def test_default_weights_sum_to_one_and_follow_canonical_order(verb: str) -> None:
    spec = REGISTRY[verb]
    assert math.isclose(sum(spec.default_weights.values()), 1.0, abs_tol=1e-12)
    assert tuple(spec.default_weights) == spec.axes


def test_canonical_axis_orders() -> None:
    assert REGISTRY["implement-issue"].axes == (
        "priority",
        "outcome",
        "leverage",
        "effort",
        "momentum",
    )
    assert REGISTRY["refine-issue"].axes == (
        "priority",
        "readiness_gap",
        "leverage",
        "staleness",
        "momentum",
    )


# ------------------------------------------------------------- worst/best property tests


def _extremes() -> dict[str, tuple[AxisScore, AxisScore]]:
    """Real ``(worst, best)`` axis results produced by the actual curve functions."""
    ten = tuple(f"X-{i}" for i in range(10))
    saturated = _lev(None, status="saturated", count_lower_bound=10, saturated=True, sample=ten)
    stamp = AS_OF.strftime("%Y-%m-%dT%H:%M:%S")
    log = f"## Session Log\n- `/ll:refine-issue` - {stamp} - `a.jsonl`\n"
    old_log = "## Session Log\n- `/ll:refine-issue` - 2000-01-01\n"
    impact = "## Impact\n- **Effort**: {}\n"
    return {
        "priority": (priority_axis(5, "P5", "filename"), priority_axis(0, "P0", "filename")),
        "outcome": (outcome_axis(0), outcome_axis(100)),
        "readiness_gap": (
            readiness_gap_axis(
                100, 100, readiness_threshold=85, outcome_threshold=65, outcome_waived=False
            ),
            readiness_gap_axis(
                0, 0, readiness_threshold=85, outcome_threshold=65, outcome_waived=False
            ),
        ),
        "leverage": (leverage_axis(_lev(0)), leverage_axis(saturated)),
        "effort": (effort_axis(impact.format("Large")), effort_axis(impact.format("Trivial"))),
        "staleness": (
            staleness_axis(AS_OF.isoformat(), None, AS_OF),
            staleness_axis("2020-01-01", None, AS_OF),
        ),
        "momentum": (momentum_axis("\n" + old_log, AS_OF), momentum_axis(log, AS_OF)),
    }


def test_extreme_scores_match_documented_bounds() -> None:
    for axis, (worst, best) in _extremes().items():
        want_worst, want_best = AXIS_BOUNDS[axis]
        assert worst.score == pytest.approx(want_worst, abs=1e-3), axis
        assert best.score == pytest.approx(want_best), axis


@pytest.mark.parametrize("verb", registered_verbs())
def test_worst_to_best_factor_at_default_weights_is_at_least_point_six(verb: str) -> None:
    extremes = _extremes()
    weights = _defaults(verb)
    for axis in REGISTRY[verb].axes:
        worst, best = extremes[axis]
        assert worst.score is not None and best.score is not None
        factor = (worst.score / best.score) ** weights[axis]
        assert factor >= 0.6, f"{verb}.{axis}: factor {factor:.3f}"


@pytest.mark.parametrize("verb", registered_verbs())
def test_whole_aggregate_never_collapses_for_worst_case_axes(verb: str) -> None:
    """Every axis at its worst still leaves a non-trivial utility (no near-veto)."""
    extremes = _extremes()
    spec = REGISTRY[verb]
    worst = {a: extremes[a][0] for a in spec.axes}
    best = {a: extremes[a][1] for a in spec.axes}
    worst_utility = aggregate_axes(verb, spec.default_weights, worst).utility
    best_utility = aggregate_axes(verb, spec.default_weights, best).utility
    assert worst_utility is not None and best_utility is not None
    assert best_utility == pytest.approx(1.0)
    assert worst_utility / best_utility >= 0.2


def test_single_axis_swings_never_exceed_the_point_six_floor() -> None:
    """One axis worst vs best, others fixed mid: the utility ratio is that axis' factor."""
    extremes = _extremes()
    for verb in registered_verbs():
        spec = REGISTRY[verb]
        mid = {a: _present(0.7) for a in spec.axes}
        for axis in spec.axes:
            worst_case = {**mid, axis: extremes[axis][0]}
            best_case = {**mid, axis: extremes[axis][1]}
            lo = aggregate_axes(verb, spec.default_weights, worst_case).utility
            hi = aggregate_axes(verb, spec.default_weights, best_case).utility
            assert lo is not None and hi is not None
            assert lo / hi >= 0.6, f"{verb}.{axis}"


def test_zero_dependent_leaf_and_p5_are_not_vetoed() -> None:
    leaf = leverage_axis(_lev(0))
    p5 = priority_axis(5, "P5", "filename")
    assert leaf.score == pytest.approx(0.5)
    assert p5.score == pytest.approx(0.2)
    results = {a: _present(1.0) for a in REGISTRY["implement-issue"].axes}
    results["leverage"] = leaf
    results["priority"] = p5
    utility = aggregate_axes("implement-issue", _defaults("implement-issue"), results).utility
    assert utility is not None
    assert utility > 0.5  # nowhere near the 1e-6 floor


@pytest.mark.parametrize("verb", registered_verbs())
def test_every_curve_score_is_finite_in_unit_interval(verb: str) -> None:
    for worst, best in _extremes().values():
        for item in (worst, best):
            assert item.score is not None
            assert math.isfinite(item.score)
            assert 0.0 < item.score <= 1.0


# ----------------------------------------------------------------------- aggregate_axes


def test_axes_are_built_in_canonical_order_regardless_of_input_order() -> None:
    verb = "refine-issue"
    spec = REGISTRY[verb]
    results = {a: _present(0.5 + i / 20) for i, a in enumerate(reversed(spec.axes))}
    shuffled_weights = dict(reversed(list(spec.default_weights.items())))
    agg = aggregate_axes(verb, shuffled_weights, results)
    assert tuple(agg.axes) == spec.axes


def test_full_axis_set_effective_weights_equal_configured() -> None:
    verb = "implement-issue"
    results = {a: _present(0.8) for a in REGISTRY[verb].axes}
    agg = aggregate_axes(verb, _defaults(verb), results)
    for axis, item in agg.axes.items():
        assert item.configured_weight == pytest.approx(REGISTRY[verb].default_weights[axis])
        assert item.effective_weight == pytest.approx(item.configured_weight)
    assert sum(i.effective_weight for i in agg.axes.values()) == pytest.approx(1.0)
    assert agg.utility == pytest.approx(0.8)
    assert agg.coverage == "5/5"


def test_missing_axis_renormalizes_effective_weights() -> None:
    verb = "implement-issue"
    results = {a: _present(0.9) for a in REGISTRY[verb].axes}
    results["effort"] = axis_missing("1 / effort_level", "absent")
    results["momentum"] = axis_missing("m", "no_session_log")
    agg = aggregate_axes(verb, _defaults(verb), results)
    assert agg.axes["effort"].effective_weight == 0.0
    assert agg.axes["momentum"].effective_weight == 0.0
    assert agg.axes["effort"].configured_weight == pytest.approx(0.10)
    # remaining weights 0.3 + 0.3 + 0.2 = 0.8 renormalize to 1
    assert agg.axes["priority"].effective_weight == pytest.approx(0.30 / 0.8)
    assert agg.axes["leverage"].effective_weight == pytest.approx(0.20 / 0.8)
    assert sum(i.effective_weight for i in agg.axes.values()) == pytest.approx(1.0)
    assert (agg.resolved_axes, agg.applicable_axes, agg.coverage) == (3, 5, "3/5")


def test_aggregate_matches_weighted_geometric_in_canonical_order() -> None:
    verb = "implement-issue"
    scores = {"priority": 0.84, "outcome": 0.6, "leverage": 0.75, "effort": 0.5, "momentum": 0.4}
    agg = aggregate_axes(verb, _defaults(verb), {a: _present(s) for a, s in scores.items()})
    expected = weighted_geometric(scores, _defaults(verb))
    assert agg.utility == pytest.approx(expected)


def test_no_coverage_multiplier_or_make_up_term() -> None:
    """Missing evidence changes nothing but the renormalization: uniform scores stay put."""
    verb = "refine-issue"
    full = {a: _present(0.6) for a in REGISTRY[verb].axes}
    sparse = {"priority": _present(0.6)}
    assert aggregate_axes(verb, _defaults(verb), full).utility == pytest.approx(0.6)
    assert aggregate_axes(verb, _defaults(verb), sparse).utility == pytest.approx(0.6)


def test_nothing_resolved_gives_none_utility() -> None:
    agg = aggregate_axes("refine-issue", _defaults("refine-issue"), {})
    assert agg.utility is None
    assert (agg.resolved_axes, agg.applicable_axes) == (0, 5)
    assert all(i.missing_reason == "not_computed" for i in agg.axes.values())
    assert all(i.effective_weight == 0.0 for i in agg.axes.values())


def test_zero_weight_axes_do_not_count_toward_coverage_or_aggregate() -> None:
    verb = "implement-issue"
    weights = {**_defaults(verb), "effort": 0.0, "momentum": 0.0}
    results = {a: _present(0.5) for a in REGISTRY[verb].axes}
    results["effort"] = _present(0.1)  # would drag the mean down if counted
    agg = aggregate_axes(verb, weights, results)
    assert agg.utility == pytest.approx(0.5)
    assert (agg.resolved_axes, agg.applicable_axes) == (3, 3)
    assert agg.axes["effort"].effective_weight == 0.0
    assert agg.axes["effort"].score == pytest.approx(0.1)  # still reported


def test_priority_weight_zero_still_reports_priority_axis() -> None:
    verb = "implement-issue"
    weights = {**_defaults(verb), "priority": 0.0}
    results = {a: _present(0.5) for a in REGISTRY[verb].axes}
    agg = aggregate_axes(verb, weights, results)
    assert agg.applicable_axes == 4
    assert agg.axes["priority"].score == 0.5
    assert minimum_evidence_met(agg.axes) is True


def test_weights_from_arena_settings_drive_aggregation_and_reordered_config_matches() -> None:
    a = {
        "verbs": {
            "implement-issue": {"weights": {"priority": 0.5, "outcome": 0.25, "leverage": 0.25}}
        }
    }
    b = {
        "verbs": {
            "implement-issue": {"weights": {"leverage": 0.25, "outcome": 0.25, "priority": 0.5}}
        }
    }
    sa = NextConfig(True, a).resolve_arena_settings()
    sb = NextConfig(True, b).resolve_arena_settings()
    verb = "implement-issue"
    scores = {"priority": 0.84, "outcome": 0.6, "leverage": 0.75, "effort": 0.5, "momentum": 0.4}
    results = {k: _present(v) for k, v in scores.items()}
    first = aggregate_axes(verb, sa.weights[verb], results)
    second = aggregate_axes(verb, sb.weights[verb], results)
    assert first == second
    assert json.dumps([v.to_dict() for v in first.axes.values()]) == json.dumps(
        [v.to_dict() for v in second.axes.values()]
    )
    assert tuple(first.axes) == REGISTRY[verb].axes


def test_all_zero_weights_fail_at_the_config_consumer() -> None:
    zero = {"verbs": {"refine-issue": {"weights": dict.fromkeys(REGISTRY["refine-issue"].axes, 0)}}}
    with pytest.raises(NextConfigError):
        NextConfig(True, zero).resolve_arena_settings()


def test_unknown_verb_is_rejected() -> None:
    with pytest.raises(KeyError):
        aggregate_axes("run-loop", {}, {})


def test_aggregate_serialization_has_no_nan() -> None:
    verb = "refine-issue"
    agg = aggregate_axes(verb, _defaults(verb), {"priority": _present(0.5)})
    dumped = json.dumps([v.to_dict() for v in agg.axes.values()], allow_nan=False)
    assert "NaN" not in dumped and "Infinity" not in dumped


# ---------------------------------------------------------------------- minimum evidence


def _axes_with(**scores: float | None) -> dict[str, AxisScore]:
    spec = REGISTRY["implement-issue"]
    results = {
        a: _present(scores[a]) if scores.get(a) is not None else axis_missing("c", "absent")
        for a in spec.axes
    }
    return dict(aggregate_axes("implement-issue", spec.default_weights, results).axes)


def test_minimum_evidence_requires_priority_plus_one_other_axis() -> None:
    assert minimum_evidence_met(_axes_with(priority=0.5, outcome=0.5)) is True
    assert minimum_evidence_met(_axes_with(priority=0.5)) is False
    assert minimum_evidence_met(_axes_with(outcome=0.5, leverage=0.5)) is False
    assert minimum_evidence_met({}) is False


def test_minimum_evidence_ignores_zero_weight_non_priority_axes() -> None:
    verb = "implement-issue"
    weights = dict.fromkeys(REGISTRY[verb].axes, 0.0)
    weights["priority"] = 1.0
    results = {a: _present(0.5) for a in REGISTRY[verb].axes}
    agg = aggregate_axes(verb, weights, results)
    assert minimum_evidence_met(agg.axes) is False


# --------------------------------------------------------------------- combinational check


def test_utility_monotone_in_each_axis_under_default_weights() -> None:
    verb = "refine-issue"
    spec = REGISTRY[verb]
    levels = (0.3, 0.6, 1.0)
    for axis in spec.axes:
        previous = None
        for level in levels:
            results = {a: _present(0.7) for a in spec.axes}
            results[axis] = _present(level)
            utility = aggregate_axes(verb, spec.default_weights, results).utility
            assert utility is not None
            if previous is not None:
                assert utility > previous
            previous = utility


def test_input_order_independence_over_permutations() -> None:
    verb = "implement-issue"
    spec = REGISTRY[verb]
    scores = {a: 0.3 + 0.1 * i for i, a in enumerate(spec.axes)}
    baseline = aggregate_axes(
        verb, spec.default_weights, {a: _present(s) for a, s in scores.items()}
    )
    for perm in itertools.islice(itertools.permutations(scores.items()), 24):
        results = {a: _present(s) for a, s in perm}
        got = aggregate_axes(verb, spec.default_weights, results)
        assert got.utility == baseline.utility
        assert tuple(got.axes) == spec.axes


def test_age_math_is_clock_free() -> None:
    later = AS_OF + timedelta(days=1)
    a = staleness_axis("2026-10-01", None, AS_OF)
    b = staleness_axis("2026-10-01", None, later)
    assert a.score is not None and b.score is not None and b.score > a.score

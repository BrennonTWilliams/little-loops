"""Sprint-recency adapter: grammar, producer facts, witness semantics (FEAT-3713 step 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any

import pytest

from little_loops.next_arena.axes import sprint_since_last_run_axis
from little_loops.next_arena.history import (
    CliInvocationRow,
    HistoryReadCoverage,
    HistoryReadResult,
    HistorySnapshot,
)
from little_loops.next_arena.sprint_history import (
    DEFINITION_LABEL,
    qualify_row,
    sprint_history_evidence,
)

AS_OF = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)


def stamp(delta: timedelta) -> str:
    return (AS_OF - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(
    row_id: int,
    args: tuple[str, ...],
    *,
    ago: timedelta = timedelta(hours=2),
    duration_ms: int | None = 60_000,
    exit_code: int | None = 0,
    ts: str | None = None,
) -> CliInvocationRow:
    return CliInvocationRow(
        row_id, ts if ts is not None else stamp(ago), "ll-sprint", args, exit_code, duration_ms
    )


def snapshot(
    rows: list[CliInvocationRow],
    *,
    availability: str = "available",
    reason: str | None = None,
    reached_start: bool = True,
    skipped_malformed: int = 0,
    reasons: tuple[str, ...] = (),
) -> HistorySnapshot:
    coverage = HistoryReadCoverage(
        max_id=500,
        completed_range=(1, 500) if reached_start else (400, 500),
        returned_rows=len(rows),
        skipped_malformed=skipped_malformed,
        reasons=reasons,
        reached_start=reached_start,
    )
    result = HistoryReadResult(availability, reason, rows=tuple(rows), coverage=coverage)  # type: ignore[arg-type]
    return HistorySnapshot(MappingProxyType({"sprint_invocations": result}), (), AS_OF, AS_OF)


def evidence(snap: HistorySnapshot | None, name: str = "alpha") -> Any:
    return sprint_history_evidence(snap, name, AS_OF)


# ---------------------------------------------------------------------------- grammar


@pytest.mark.parametrize(
    ("args", "name", "verdict"),
    [
        (("run", "alpha"), "alpha", "qualified"),
        (("r", "alpha"), "alpha", "qualified"),
        (("run", "--", "alpha"), "alpha", "qualified"),
        (("r", "--", "alpha"), "alpha", "qualified"),
        (("run", "--", "-dash"), "-dash", "qualified"),  # after "--" a dash is a literal operand
        (("run", "-dash"), "-dash", "unmodeled_options"),  # without "--" it is an option
        (("run", "alpha", "--dry-run"), "alpha", "unmodeled_options"),
        (("run", "alpha", "--only", "BUG-001"), "alpha", "unmodeled_options"),
        (("run", "--skip", "BUG-001", "alpha"), "alpha", "unmodeled_options"),
        (("run", "alpha", "--resume"), "alpha", "unmodeled_options"),
        (("run", "alpha", "--config", "/x"), "alpha", "unmodeled_options"),
        (("run", "--type", "BUG", "--", "alpha"), "alpha", "unmodeled_options"),
        (("run", "alpha", "--label", "x"), "alpha", "unmodeled_options"),
        (("run", "other"), "alpha", None),
        (("list",), "alpha", None),
        (("show", "alpha"), "alpha", None),
        (("edit", "alpha", "--prune"), "alpha", None),
        ((), "alpha", None),
    ],
)
def test_run_grammar_qualifies_only_whole_unfiltered_invocations(
    args: tuple[str, ...], name: str, verdict: str | None
) -> None:
    assert qualify_row(args, name) == verdict


def test_an_args_array_at_the_capture_limit_is_incomplete() -> None:
    padded = ("run", *(f"--skip=X-{i}" for i in range(47)), "alpha")
    assert len(padded) == 49
    assert qualify_row(padded, "alpha") == "unmodeled_options"
    at_limit = ("run", "--", "alpha", *("x",) * 47)
    assert len(at_limit) == 50
    assert qualify_row(at_limit, "alpha") == "args_possibly_truncated"


# ----------------------------------------------------------------------- the witness


def test_witness_is_the_newest_qualified_ended_invocation_with_outcome_unknown() -> None:
    snap = snapshot(
        [
            row(1, ("run", "alpha"), ago=timedelta(days=10)),
            row(2, ("run", "--", "alpha"), ago=timedelta(days=3), duration_ms=3_600_000),
            row(3, ("r", "alpha"), ago=timedelta(days=5)),
            row(4, ("run", "beta"), ago=timedelta(hours=1)),
        ]
    )
    ev = evidence(snap)
    assert ev.complete and ev.qualified == 3 and ev.latest_qualified_unknown is False
    assert ev.witness is not None and ev.witness.row_id == 2
    # ended = ts + duration; age is measured from the derived end
    assert ev.witness.age_days == pytest.approx(3 - 1 / 24, abs=1e-3)
    data = ev.to_dict()
    assert data["witness"]["outcome"] == "outcome_unknown"
    assert DEFINITION_LABEL in data["labels"] and "witness_in_window" not in data["labels"]


def test_exit_code_zero_never_establishes_success() -> None:
    zero = evidence(snapshot([row(1, ("run", "alpha"), exit_code=0)]))
    nonzero = evidence(snapshot([row(1, ("run", "alpha"), exit_code=1)]))
    assert zero.witness is not None and nonzero.witness is not None
    assert zero.witness.age_days == nonzero.witness.age_days  # exit_code is never read


def test_option_bearing_and_dry_run_rows_cannot_supply_recency() -> None:
    ev = evidence(
        snapshot(
            [
                row(1, ("run", "alpha", "--dry-run"), ago=timedelta(hours=1)),
                row(2, ("run", "alpha", "--only", "BUG-001"), ago=timedelta(hours=2)),
                row(3, ("run", "alpha"), ago=timedelta(days=9)),
            ]
        )
    )
    assert ev.witness is not None and ev.witness.row_id == 3
    assert ev.excluded == {"unmodeled_options": 2}
    assert [list(a) for a in ev.to_dict()["excluded_args"]] == [
        ["run", "alpha", "--dry-run"],
        ["run", "alpha", "--only", "BUG-001"],
    ]  # excluded invocations keep their arguments in provenance


def test_unfinished_rows_never_establish_completion_but_are_activity_evidence() -> None:
    ev = evidence(snapshot([row(1, ("run", "alpha"), duration_ms=None, exit_code=None)]))
    assert ev.witness is None and ev.unfinished == 1
    assert ev.missing_reason == "no_qualified_witness"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"ts": "not-a-date"}, "malformed_timestamp"),
        ({"ts": "2026-10-08 10:00:00"}, "malformed_timestamp"),
        ({"duration_ms": -5}, "malformed_duration"),
        ({"duration_ms": 10**16}, "derived_end_overflow"),
        ({"ago": timedelta(minutes=-5)}, "start_after_as_of"),  # starts after as_of
        ({"ago": timedelta(seconds=30), "duration_ms": 120_000}, "end_after_as_of"),
    ],
)
def test_malformed_or_future_rows_are_row_local_exclusions(
    kwargs: dict[str, Any], reason: str
) -> None:
    good = row(1, ("run", "alpha"), ago=timedelta(days=4))
    bad = row(2, ("run", "alpha"), **kwargs)
    ev = evidence(snapshot([bad, good]))
    assert ev.witness is not None and ev.witness.row_id == 1  # not total source loss
    assert ev.excluded == {reason: 1}
    assert ev.qualified == 1


def test_row_validation_failures_make_the_walk_partial_not_complete() -> None:
    ev = evidence(snapshot([row(1, ("run", "alpha"), ts="bogus"), row(2, ("run", "alpha"))]))
    assert ev.witness is not None
    assert ev.complete is False and ev.latest_qualified_unknown is True
    assert ev.coverage["row_validation_failures"] == 1


def test_latest_row_by_derived_end_beats_a_later_started_shorter_run() -> None:
    long_early = row(1, ("run", "alpha"), ago=timedelta(hours=5), duration_ms=4 * 3600 * 1000)
    short_late = row(2, ("run", "alpha"), ago=timedelta(hours=3), duration_ms=60_000)
    ev = evidence(snapshot([short_late, long_early]))
    assert ev.witness is not None and ev.witness.row_id == 1  # ended at -1h vs -2h59m


# --------------------------------------------------------------------- completeness


def test_complete_walk_without_a_witness_is_missing_never_never_run() -> None:
    ev = evidence(snapshot([]))
    assert ev.complete and ev.witness is None
    assert ev.missing_reason == "no_qualified_witness"
    axis = sprint_since_last_run_axis(None, raw=ev.to_dict(), missing_reason=ev.missing_reason)
    assert axis.score is None and axis.missing_reason == "no_qualified_witness"
    assert "does not prove the sprint never ran" in ev.to_dict()["note"]


def test_incomplete_walk_with_a_witness_is_labeled_witness_in_window() -> None:
    snap = snapshot(
        [row(1, ("run", "alpha"), ago=timedelta(days=2))],
        availability="partial",
        reason="id_span_cap",
        reached_start=False,
        reasons=("id_span_cap",),
    )
    ev = evidence(snap)
    assert ev.complete is False and ev.latest_qualified_unknown is True
    assert ev.witness is not None
    data = ev.to_dict()
    assert "witness_in_window" in data["labels"] and DEFINITION_LABEL in data["labels"]
    assert "upper bound" in data["note"] and "optimistic" in data["note"]


def test_incomplete_walk_without_a_witness_is_missing_not_never_run() -> None:
    snap = snapshot(
        [row(1, ("run", "beta"))],
        availability="partial",
        reason="row_cap",
        reached_start=False,
        reasons=("row_cap",),
    )
    ev = evidence(snap)
    assert ev.witness is None and ev.missing_reason == "no_witness_in_incomplete_walk"
    assert ev.latest_qualified_unknown is True


def test_skipped_malformed_reader_rows_make_the_walk_incomplete() -> None:
    snap = snapshot(
        [row(1, ("run", "alpha"))],
        availability="partial",
        reason="malformed_row",
        skipped_malformed=2,
        reasons=("malformed_row",),
    )
    ev = evidence(snap)
    assert ev.witness is not None and ev.complete is False


def test_unavailable_unscoped_and_uncollected_sources_never_supply_a_witness() -> None:
    unavailable = HistorySnapshot(
        MappingProxyType({"sprint_invocations": HistoryReadResult("unavailable", "store_missing")}),
        (),
        AS_OF,
        None,
    )
    ev = evidence(unavailable)
    assert ev.witness is None and ev.missing_reason == "history_unavailable"
    unscoped = HistorySnapshot(
        MappingProxyType(
            {
                "sprint_invocations": HistoryReadResult(
                    "partial",
                    "unscoped_store",
                    rows=(row(1, ("run", "alpha")),),
                    coverage=HistoryReadCoverage(reasons=("unscoped_store",)),
                )
            }
        ),
        (),
        AS_OF,
        None,
    )
    # even if rows were attached, an unscoped store must not score
    scoped_out = evidence(unscoped)
    assert scoped_out.witness is None and scoped_out.missing_reason == "unscoped_store"
    assert evidence(None).missing_reason == "history_not_collected"
    other_kind = HistorySnapshot(MappingProxyType({}), (), AS_OF, None)
    assert evidence(other_kind).missing_reason == "history_not_collected"


def test_clock_rollback_and_out_of_order_ids_never_become_exact_recency() -> None:
    # a newer id with an older timestamp (rollback) and an older id with a newer one
    snap = snapshot(
        [
            row(9, ("run", "alpha"), ago=timedelta(days=20)),
            row(2, ("run", "alpha"), ago=timedelta(days=1)),
        ],
        availability="partial",
        reason="id_span_cap",
        reached_start=False,
        reasons=("id_span_cap",),
    )
    ev = evidence(snap)
    assert ev.witness is not None and ev.witness.row_id == 2  # chosen by derived end, not id
    assert ev.latest_qualified_unknown is True  # a newer end may lie outside the walk


# ------------------------------------------------------------------------- the axis


@pytest.mark.parametrize(
    ("age", "expected"),
    [(0.0, 0.2), (15.0, 0.6), (30.0, 1.0), (400.0, 1.0)],
)
def test_since_last_run_curve_is_lerp_of_age_over_thirty_days(age: float, expected: float) -> None:
    axis = sprint_since_last_run_axis(age, raw={}, missing_reason=None)
    assert axis.score == pytest.approx(expected)


def test_axis_floor_makes_a_busy_store_window_reach_only_the_low_end() -> None:
    # MAX_ID_SPAN covered ~4.5 days on the reference store: x <= 0.15 -> axis <= ~0.32
    assert sprint_since_last_run_axis(4.5, raw={}, missing_reason=None).score == pytest.approx(
        0.2 + 0.8 * 0.15
    )

"""Sprint-recency adapter over the shared ``cli_events`` snapshot (FEAT-3713).

Pure over an injected :class:`~little_loops.next_arena.history.HistorySnapshot`: no clock, no
store, no live query. For one sprint name it extracts the newest **qualified ended** invocation
(the *witness*) from FEAT-3721's bounded ``sprint_invocations`` result.

Qualification is a deliberately narrow projection of the real ``ll-sprint`` CLI grammar over the
argument list ``main_sprint`` records (``sys.argv[1:]``, no binary): ``run NAME``, the alias
``r NAME`` and either form with ``--`` before the one literal operand (the option-safe command the
arena emits, so ``run -- -dash`` qualifies and is *not* option-bearing). No execution option is
modeled for whole-sprint history -- ``--only``, ``--skip``, ``--type``, ``--label``, ``--config``,
``--resume``, ``--dry-run``, help and any other option exclude the row with its reason and
arguments retained -- so a filtered or dry run can never establish whole-sprint recency.

Producer facts pinned here (and in fixtures): ``ts`` is the UTC ``%Y-%m-%dT%H:%M:%SZ`` captured at
invocation entry, ``duration_ms`` an integer wall-clock elapsed set on wrapper exit (``NULL`` while
unfinished) and ``args`` is capped at 50 entries. The derived end ``ts + duration_ms`` is an
approximation from separate clock captures, not a completion-observation timestamp; ``exit_code``
is **never** read -- the wrapper records ``0`` for a handler that merely returned ``1``, so a zero
cannot establish success (the witness is an ended named invocation with outcome unknown).

The witness is the newest qualified ended row among the rows the bounded walk returned; when the
walk is incomplete its age is an upper bound on the true latest-run age and the age-based score can
be optimistic (``witness_in_window``). A complete walk with no witness is *missing*, never a
never-run ``x = 1``: ``cli_events`` capture is gated and an empty table cannot prove absence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from little_loops.next_arena.history import CliInvocationRow, HistorySnapshot

__all__ = [
    "ARGS_CAPTURE_LIMIT",
    "DEFINITION_LABEL",
    "SprintHistoryEvidence",
    "SprintWitness",
    "qualify_row",
    "sprint_history_evidence",
]

#: ``cli_event_context`` stores ``args[:50]``: an array of this length may be truncated.
ARGS_CAPTURE_LIMIT = 50
#: Label on the recency axis: no definition digest or member snapshot exists in CLI rows.
DEFINITION_LABEL = "name-based-definition-unknown"
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_RUN_WORDS = ("run", "r")

# Row exclusion reasons.
ARGS_TRUNCATED = "args_possibly_truncated"
UNMODELED_OPTIONS = "unmodeled_options"
MALFORMED_TIMESTAMP = "malformed_timestamp"
MALFORMED_DURATION = "malformed_duration"
END_OVERFLOW = "derived_end_overflow"
FUTURE_START = "start_after_as_of"
FUTURE_END = "end_after_as_of"


@dataclass(frozen=True)
class SprintWitness:
    """The newest qualified ended invocation observed for a sprint name."""

    row_id: int
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    age_days: float
    args: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {
            "row_id": self.row_id,
            "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "ended_at": self.ended_at.isoformat().replace("+00:00", "Z"),
            "duration_ms": self.duration_ms,
            "witness_age_days": self.age_days,
            "args": list(self.args),
            "outcome": "outcome_unknown",
        }


@dataclass(frozen=True)
class SprintHistoryEvidence:
    """Everything the recency axis and explain need for one sprint name.

    ``source_status`` is ``not_collected`` | ``available`` | ``partial`` | ``unavailable``.
    ``complete`` is true only for an ``available`` walk that reached the table start without
    skipping rows; otherwise ``latest_qualified_unknown`` is true and the witness (if any) is
    only the newest one seen (``witness_in_window``).
    """

    name: str
    source_status: str
    reason: str | None
    complete: bool
    witness: SprintWitness | None
    qualified: int
    unfinished: int
    excluded: Mapping[str, int]
    excluded_args: tuple[tuple[str, ...], ...]
    latest_qualified_unknown: bool
    coverage: Mapping[str, Any]

    @property
    def missing_reason(self) -> str | None:
        """Why the axis is missing, or ``None`` when a witness exists."""
        if self.witness is not None:
            return None
        if self.source_status == "not_collected":
            return "history_not_collected"
        if self.source_status == "unavailable":
            return "history_unavailable"
        if self.source_status == "partial" and self.reason == "unscoped_store":
            return "unscoped_store"
        if self.complete:
            return "no_qualified_witness"
        return "no_witness_in_incomplete_walk"

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping disclosing every limitation beside the numeric axis."""
        labels = [DEFINITION_LABEL]
        if self.witness is not None and not self.complete:
            labels.append("witness_in_window")
        return {
            "labels": labels,
            "source_status": self.source_status,
            "reason": self.reason,
            "complete": self.complete,
            "latest_qualified_unknown": self.latest_qualified_unknown,
            "qualified_invocations": self.qualified,
            "unfinished_invocations": self.unfinished,
            "excluded": dict(self.excluded),
            "excluded_args": [list(a) for a in self.excluded_args],
            "witness": self.witness.to_dict() if self.witness is not None else None,
            "missing_reason": self.missing_reason,
            "coverage": dict(self.coverage),
            "note": (
                "name-based: CLI rows carry no definition digest, so this does not prove the "
                "current YAML ran; the newest ended invocation's outcome is unknown. "
                + (
                    "The walk was bounded, so the latest run may be newer than this witness "
                    "(its age is an upper bound and the age-based score can be optimistic)."
                    if not self.complete
                    else "No qualified invocation observed does not prove the sprint never ran."
                )
            ),
        }


def _parse_utc(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, _TS_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def qualify_row(args: Sequence[str], name: str) -> str | None:
    """Classify an ``ll-sprint`` argument list against *name*.

    Returns ``"qualified"``, ``None`` (the row is not about *name*) or an exclusion reason
    (``args_possibly_truncated``/``unmodeled_options``) when it mentions *name* after a run word
    but cannot establish whole-sprint recency.
    """
    tokens = list(args)
    if not tokens or tokens[0] not in _RUN_WORDS:
        return None
    rest = tokens[1:]
    if len(tokens) >= ARGS_CAPTURE_LIMIT:
        return ARGS_TRUNCATED if name in rest else None
    if rest == ["--", name]:
        return "qualified"
    if len(rest) == 1 and rest[0] == name and not name.startswith("-"):
        return "qualified"
    # Everything else naming this sprint: after "--" tokens are literal operands, before it
    # they may be options. Either way an extra token means an unmodeled invocation.
    if name in rest:
        return UNMODELED_OPTIONS
    return None


def sprint_history_evidence(
    snapshot: HistorySnapshot | None, name: str, as_of: datetime
) -> SprintHistoryEvidence:
    """Distill the ``sprint_invocations`` result for *name* (pure; ``as_of`` is the boundary)."""
    if snapshot is None or "sprint_invocations" not in snapshot.results_by_request:
        return SprintHistoryEvidence(
            name, "not_collected", None, False, None, 0, 0, {}, (), True, {}
        )
    result = snapshot.results_by_request["sprint_invocations"]
    coverage = result.coverage
    summary = {
        "returned_rows": coverage.returned_rows,
        "visited_rows_upper_bound": coverage.visited_rows_upper_bound,
        "max_id": coverage.max_id,
        "completed_range": list(coverage.completed_range) if coverage.completed_range else None,
        "reached_start": coverage.reached_start,
        "skipped_malformed": coverage.skipped_malformed,
        "skipped_oversized": coverage.skipped_oversized,
        "reasons": list(coverage.reasons),
    }
    if result.availability == "unavailable":
        return SprintHistoryEvidence(
            name, "unavailable", result.reason, False, None, 0, 0, {}, (), True, summary
        )
    if result.reason == "unscoped_store" or "unscoped_store" in coverage.reasons:
        # ownership of the store is unproven: whatever rows exist cannot supply a witness
        return SprintHistoryEvidence(
            name, "partial", "unscoped_store", False, None, 0, 0, {}, (), True, summary
        )
    boundary = as_of.astimezone(UTC)
    excluded: Counter[str] = Counter()
    excluded_args: list[tuple[str, ...]] = []
    qualified = unfinished = 0
    best: tuple[datetime, int, CliInvocationRow, datetime, datetime] | None = None
    for row in result.rows:
        if not isinstance(row, CliInvocationRow):
            continue
        verdict = qualify_row(row.args, name)
        if verdict is None:
            continue
        if verdict != "qualified":
            excluded[verdict] += 1
            excluded_args.append(row.args)
            continue
        started = _parse_utc(row.ts)
        if started is None:
            excluded[MALFORMED_TIMESTAMP] += 1
            continue
        if row.duration_ms is None:
            unfinished += 1  # unfinished evidence: never an ended witness
            continue
        if row.duration_ms < 0:
            excluded[MALFORMED_DURATION] += 1
            continue
        try:
            ended = started + timedelta(milliseconds=row.duration_ms)
        except OverflowError:
            excluded[END_OVERFLOW] += 1
            continue
        if started > boundary:
            excluded[FUTURE_START] += 1
            continue
        if ended > boundary:
            excluded[FUTURE_END] += 1
            continue
        qualified += 1
        if best is None or (ended, row.id) > (best[0], best[1]):
            best = (ended, row.id, row, started, ended)
    witness = None
    if best is not None:
        _, _, row, started, ended = best
        witness = SprintWitness(
            row_id=row.id,
            started_at=started,
            ended_at=ended,
            duration_ms=row.duration_ms or 0,
            age_days=(boundary - ended).total_seconds() / 86400.0,
            args=row.args,
        )
    row_malformed = sum(
        excluded[r] for r in (MALFORMED_TIMESTAMP, MALFORMED_DURATION, END_OVERFLOW)
    )
    skipped = coverage.skipped_malformed + coverage.skipped_oversized + row_malformed
    summary["row_validation_failures"] = row_malformed  # partial(malformed_row), counted
    complete = result.availability == "available" and coverage.reached_start and skipped == 0
    return SprintHistoryEvidence(
        name=name,
        source_status=result.availability,
        reason=result.reason,
        complete=complete,
        witness=witness,
        qualified=qualified,
        unfinished=unfinished,
        excluded=dict(sorted(excluded.items())),
        excluded_args=tuple(excluded_args),
        latest_qualified_unknown=not complete,
        coverage=summary,
    )

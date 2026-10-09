"""Shared read-only ``history.db`` snapshot reader for ``ll-next`` consumers (FEAT-3721).

:func:`read_history_snapshot` is an independently callable, injected seam: it is **not**
imported by :mod:`little_loops.next_arena.state` or :mod:`little_loops.cli.next`, so the
history-free core and its core-only CLI modes never resolve, open or probe a store. Demand-driven
consumers (FEAT-3713 sprint recency, FEAT-3711 recommendation lookup) resolve the target once with
``resolve_history_target(..., root=project_root)`` -- only when they have requests -- freeze a
relative path to an absolute spelling at their CLI boundary, and pass the typed target in; the
reader never resolves it again from the cwd.

Contract (see ``docs/reference/API.md``):

* **Read-only.** The store is opened through ``connect_readonly`` (``mode=ro`` + ``query_only``),
  never created, migrated or configured, and no cache/marker/telemetry file is written. SQLite
  itself may create ``-wal``/``-shm`` coordination files for an existing WAL-mode database even
  on a read-only open; that narrow SQLite-managed exception is accepted rather than bypassed with
  ``immutable=1`` (which would ignore live WAL writers).
* **One transaction, one deadline.** Every request shares one read transaction and one
  :class:`~little_loops.session_store.deadline.Deadline` (1 s), with a 250 ms SQLite busy
  timeout. Neither is a universal wall-time cap: SQLite lock polling can overshoot, and
  filesystem stalls, JSON decoding and user-defined functions are not preempted.
* **Fail soft.** A missing store/table, old or incompatible schema, lock timeout, remote target
  or deadline yields typed per-request availability, never an exception and never negative
  evidence ("never ran"). Truncation (``partial``) is classified from the deadline object's
  state or a fired fixed cap, never from error text.
* **Bounded work.** ``cli_events`` has no binary/time index, so the sprint request walks
  descending primary-key ID ranges (``NOT INDEXED``) under fixed span/window/row caps. The
  recommendation lookup is an exact ``(rec_id, kind)`` point seek (at most two rows), and the
  schema probe reads metadata only.
* **Observed snapshot, not reconstruction.** The transaction is internally consistent but not
  atomic with the earlier issue/git/filesystem :class:`ProjectState`; ``as_of`` is carried for
  the consumer's time-window evidence (timestamps are not parsed or filtered here) and mutable
  duration fields have no completion-observed timestamp.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Literal

from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics
from little_loops.session_store.backend import HistoryTarget as HistoryTarget
from little_loops.session_store.backend import (
    HistoryUnavailable,
    LocalTarget,
    RemoteTarget,
    connect_readonly,
)
from little_loops.session_store.deadline import Deadline
from little_loops.session_store.queries import (
    RECOMMENDATION_EVENT_COLUMNS,
    RECOMMENDATION_LOOKUP_SQL,
    RecommendationSchemaStatus,
    recommendation_schema_status,
)

__all__ = [
    "CliInvocationRow",
    "HistoryReadCoverage",
    "HistoryReadRequest",
    "HistoryReadResult",
    "HistoryRequestKind",
    "HistorySnapshot",
    "RecentSprintInvocations",
    "RecommendationEventRow",
    "RecommendationLookup",
    "RecommendationSchemaProbe",
    "RecommendationSchemaStatus",
    "decode_recommendation_row",
    "read_history_snapshot",
]

HistoryRequestKind = Literal["sprint_invocations", "recommendation_lookup", "recommendation_schema"]
Availability = Literal["available", "partial", "unavailable"]

#: One shared budget for the whole snapshot (opening, probes, queries, fetches, decoding).
READ_DEADLINE_SECONDS = 1.0
#: SQLite busy timeout passed explicitly; ``connect_readonly``'s own default is 5 s.
BUSY_TIMEOUT_SECONDS = 0.25
#: Fixed work bounds for the recent-sprint walk (not a configuration framework).
MAX_ID_SPAN = 50_000
WINDOW_WIDTH = 200
MAX_ROWS = 2_000
#: Largest ``args`` value (UTF-8 bytes) transferred from SQLite and decoded.
MAX_ARGS_BYTES = 64 * 1024

_SPRINT_BINARY = "ll-sprint"
_CLI_COLUMNS = frozenset({"id", "ts", "binary", "args", "exit_code", "duration_ms"})
_LOCK_CODES = frozenset({sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})
# Primary reason reported on a partial result when several fired, most severe first.
_REASON_ORDER = ("deadline", "row_cap", "id_span_cap", "payload_limit", "malformed_row")

# ``NOT INDEXED`` keeps integer-rowid range access even when a compatible (binary, ts) index
# exists: the planner must not walk matching rows outside the ID range or sort.
_MAX_ID_SQL = "SELECT MAX(id) AS max_id FROM main.cli_events NOT INDEXED"
_WINDOW_SQL = f"""
SELECT id, ts, binary, exit_code, duration_ms,
       CASE WHEN length(CAST(args AS BLOB)) <= {MAX_ARGS_BYTES} THEN args END AS args,
       length(CAST(args AS BLOB)) AS args_bytes
FROM main.cli_events NOT INDEXED
WHERE id BETWEEN ? AND ? AND binary = '{_SPRINT_BINARY}'
ORDER BY id DESC
LIMIT ?
"""


@dataclass(frozen=True)
class RecentSprintInvocations:
    """Recent ``ll-sprint`` CLI evidence for *sprint_names* (batched under one work budget).

    ``project_root`` anchors the ownership proof (``cli_events`` has no project column); the
    rows are not filtered by name -- argument/completion qualification belongs to the consumer.
    """

    kind: ClassVar[HistoryRequestKind] = "sprint_invocations"
    project_root: Path
    sprint_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root))
        object.__setattr__(self, "sprint_names", tuple(self.sprint_names))


@dataclass(frozen=True)
class RecommendationLookup:
    """Exact ``(project_key, rec_id)`` point lookup of one recommendation's shown/accepted rows.

    Independent of the CLI history caps; ownership is the ``project_key`` predicate, so a
    foreign project's identical ``rec_id`` is simply absent.
    """

    kind: ClassVar[HistoryRequestKind] = "recommendation_lookup"
    project_key: str
    rec_id: str


@dataclass(frozen=True)
class RecommendationSchemaProbe:
    """Metadata-only probe of the ``recommendation_events`` table, index and schema stamp."""

    kind: ClassVar[HistoryRequestKind] = "recommendation_schema"


#: The closed request union; each kind owns an independent ``results_by_request`` slot.
HistoryReadRequest = RecentSprintInvocations | RecommendationLookup | RecommendationSchemaProbe


@dataclass(frozen=True)
class CliInvocationRow:
    """The bounded stored fields of one ``cli_events`` row (``args`` already decoded)."""

    id: int
    ts: str
    binary: str
    args: tuple[str, ...]
    exit_code: int | None
    duration_ms: int | None


@dataclass(frozen=True)
class RecommendationEventRow:
    """One stored ``recommendation_events`` row (``action_spec``/``requested_types`` are JSON)."""

    event_id: str
    rec_id: str
    kind: str
    ts: str
    project_key: str
    session_id: str | None
    invocation_id: str
    as_of: str
    rank: int
    action_type: str
    action_key: str
    action_fingerprint: str
    target: str
    target_key: str
    action_spec: str
    requested_top: int | None
    requested_types: str


@dataclass(frozen=True)
class HistoryReadCoverage:
    """What a request actually examined.

    ``completed_range`` is the inclusive ``(low, high)`` ID range fully read; ``attempted_range``
    is a window interrupted by the deadline (excluded from completed coverage but included in
    ``visited_rows_upper_bound``, an upper bound on rows visited -- never an exact count).
    ``reached_start`` is true only when the walk covered every ID down to the table start.
    """

    max_id: int | None = None
    completed_range: tuple[int, int] | None = None
    attempted_range: tuple[int, int] | None = None
    visited_rows_upper_bound: int = 0
    returned_rows: int = 0
    skipped_malformed: int = 0
    skipped_oversized: int = 0
    payload_bytes: int = 0
    reasons: tuple[str, ...] = ()
    reached_start: bool = False


@dataclass(frozen=True)
class HistoryReadResult:
    """One request's outcome: ``available`` | ``partial`` | ``unavailable`` with a reason."""

    availability: Availability
    reason: str | None = None
    rows: tuple[CliInvocationRow | RecommendationEventRow, ...] = ()
    coverage: HistoryReadCoverage = HistoryReadCoverage()
    diagnostics: tuple[Diagnostic, ...] = ()
    #: Populated only by the ``recommendation_schema`` probe.
    schema_status: RecommendationSchemaStatus | None = None


@dataclass(frozen=True)
class HistorySnapshot:
    """Per-request results keyed by request kind, plus provenance.

    ``as_of`` is the feature boundary; ``read_observed_at`` is when the first database read
    established the transaction snapshot (``None`` if none did).
    """

    results_by_request: Mapping[HistoryRequestKind, HistoryReadResult]
    diagnostics: tuple[Diagnostic, ...]
    as_of: datetime
    read_observed_at: datetime | None


def read_history_snapshot(
    target: HistoryTarget,
    *,
    as_of: datetime,
    requests: Sequence[HistoryReadRequest],
    now: Callable[[], datetime],
) -> HistorySnapshot:
    """Read *requests* from the already-resolved *target* in one read-only transaction.

    Raises ``ValueError``/``TypeError`` before opening for programming errors (duplicate request
    kinds, naive ``as_of``, a relative local path, an unresolved target); storage failures never
    raise -- they are reported per request. An empty request list opens nothing.
    """
    as_of = _normalize_as_of(as_of)
    kinds = [request.kind for request in requests]
    if len(set(kinds)) != len(kinds):
        raise ValueError(f"duplicate history request kinds: {sorted(kinds)}")
    if not requests:
        return HistorySnapshot(MappingProxyType({}), (), as_of, None)
    if isinstance(target, RemoteTarget):
        return _store_unavailable(requests, as_of, "remote_unsupported_v1")
    if not isinstance(target, LocalTarget):
        raise TypeError(
            f"expected a resolved LocalTarget/RemoteTarget, got {type(target).__name__}"
        )
    if not target.path.is_absolute():
        raise ValueError(f"history target path must be absolute (frozen at the CLI): {target.path}")

    deadline = Deadline.after(READ_DEADLINE_SECONDS)
    try:
        conn = connect_readonly(target, timeout=BUSY_TIMEOUT_SECONDS, deadline=deadline)
    except HistoryUnavailable as exc:
        reason = _open_failure_reason(exc, deadline, target.path)
        return _store_unavailable(requests, as_of, reason, detail=str(exc))
    session = _Session(conn, deadline, now)
    results: dict[HistoryRequestKind, HistoryReadResult] = {}
    try:
        try:
            conn.execute("BEGIN")
        except (sqlite3.Error, HistoryUnavailable) as exc:
            reason = _failure_reason(exc, deadline)
            return _store_unavailable(requests, as_of, reason, detail=str(exc))
        for request in requests:
            if deadline.expired():  # unstarted requests issue no statements
                results[request.kind] = _unavailable(request.kind, "deadline_exhausted")
                continue
            results[request.kind] = _read_request(session, request, target)
    finally:
        conn.close()
    diagnostics = sort_diagnostics(d for result in results.values() for d in result.diagnostics)
    return HistorySnapshot(MappingProxyType(results), diagnostics, as_of, session.observed_at)


# --------------------------------------------------------------------------- internals


class _Session:
    """The open transaction: connection, shared deadline and observation stamp."""

    def __init__(self, conn: sqlite3.Connection, deadline: Deadline, now: Callable[[], datetime]):
        self.conn = conn
        self.deadline = deadline
        self._now = now
        self.observed_at: datetime | None = None

    def observe(self) -> None:
        """Stamp ``read_observed_at`` once, after the first read establishes the snapshot."""
        if self.observed_at is None:
            self.observed_at = self._now()


def _normalize_as_of(as_of: datetime) -> datetime:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware (naive datetimes are rejected)")
    return as_of.astimezone(UTC)


def _diagnostic(
    kind: str, availability: str, reason: str | None, detail: str | None = None
) -> Diagnostic:
    message = f"history {kind} read {availability}: {reason}"
    if detail:
        message += f" ({detail})"
    return Diagnostic(code=f"history_{availability}", message=message, subject=kind)


def _unavailable(kind: str, reason: str, detail: str | None = None) -> HistoryReadResult:
    return HistoryReadResult(
        "unavailable", reason, diagnostics=(_diagnostic(kind, "unavailable", reason, detail),)
    )


def _store_unavailable(
    requests: Sequence[HistoryReadRequest],
    as_of: datetime,
    reason: str,
    *,
    detail: str | None = None,
) -> HistorySnapshot:
    """Every requested kind gets the same store-level reason; no snapshot was established."""
    results = {r.kind: _unavailable(r.kind, reason, detail) for r in requests}
    diagnostics = sort_diagnostics(d for result in results.values() for d in result.diagnostics)
    return HistorySnapshot(MappingProxyType(results), diagnostics, as_of, None)


def _sqlite_code(exc: BaseException) -> int | None:
    cause = exc if isinstance(exc, sqlite3.Error) else exc.__cause__
    code = getattr(cause, "sqlite_errorcode", None)
    return code & 0xFF if isinstance(code, int) else None


def _failure_reason(exc: BaseException, deadline: Deadline) -> str:
    """Classify a non-truncation failure from the deadline object / error code, not text."""
    if deadline.expired():
        return "deadline_exhausted"
    if _sqlite_code(exc) in _LOCK_CODES:
        return "lock_timeout"
    return "query_failed"


def _open_failure_reason(exc: BaseException, deadline: Deadline, path: Path) -> str:
    reason = _failure_reason(exc, deadline)
    if reason == "query_failed":
        return "store_missing" if not path.exists() else "store_unavailable"
    return reason


def _read_request(
    session: _Session, request: HistoryReadRequest, target: LocalTarget
) -> HistoryReadResult:
    try:
        if isinstance(request, RecommendationLookup):
            return _read_recommendation_lookup(session, request)
        if isinstance(request, RecommendationSchemaProbe):
            return _read_recommendation_schema(session, request)
        return _read_sprint_invocations(session, request, target)
    except Exception as exc:  # programming/decoder errors: this request only, rows discarded
        return _unavailable(request.kind, "unexpected_error", f"{type(exc).__name__}: {exc}")


def _is_owned(target: LocalTarget, project_root: Path) -> bool:
    """Physical-path ownership: the selected store resolves to the direct default store.

    The expected side resolves only the canonical root and appends ``.ll/history.db`` literally,
    so a redirected ``.ll`` directory or database symlink compares unequal.
    """
    expected = project_root.resolve() / ".ll" / "history.db"
    return target.path.resolve() == expected


def _check_cli_shape(session: _Session) -> str | None:
    """``None`` when ``cli_events`` is a compatible bounded-rowid source, else a reason.

    Metadata only (no activity SQL): an ordinary table with the consumed columns whose sole
    primary key is ``id INTEGER`` as the rowid alias (no primary-key-origin index).
    """
    conn = session.conn
    row = conn.execute(
        "SELECT type, sql FROM main.sqlite_master WHERE name = ? COLLATE NOCASE", ("cli_events",)
    ).fetchone()
    session.observe()
    if row is None:
        return "missing_table"
    sql = (row["sql"] or "").lstrip().upper()
    if row["type"] != "table" or sql.startswith("CREATE VIRTUAL"):
        return "incompatible_source_shape"
    info = conn.execute("PRAGMA main.table_info(cli_events)").fetchall()
    if not _CLI_COLUMNS <= {r["name"].lower() for r in info}:
        return "incompatible_source_shape"
    pk = [r for r in info if r["pk"] > 0]
    if len(pk) != 1 or pk[0]["name"].lower() != "id" or (pk[0]["type"] or "").upper() != "INTEGER":
        return "incompatible_source_shape"
    indexes = conn.execute("PRAGMA main.index_list(cli_events)").fetchall()
    if any(r["origin"] == "pk" for r in indexes):
        return "incompatible_source_shape"
    return None


def _decode_row(row: sqlite3.Row) -> CliInvocationRow | Literal["oversized", "malformed"]:
    """Decode one fetched row; a bad stored value is row-local, anything else propagates."""
    args_bytes = row["args_bytes"]
    if row["args"] is None:
        if isinstance(args_bytes, int) and args_bytes > MAX_ARGS_BYTES:
            return "oversized"
        return "malformed"
    try:
        args = json.loads(row["args"])
    except (ValueError, RecursionError):
        return "malformed"
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return "malformed"
    ident, ts, binary = row["id"], row["ts"], row["binary"]
    exit_code, duration = row["exit_code"], row["duration_ms"]
    if not (isinstance(ident, int) and isinstance(ts, str) and isinstance(binary, str)):
        return "malformed"
    if not all(
        v is None or (isinstance(v, int) and not isinstance(v, bool)) for v in (exit_code, duration)
    ):
        return "malformed"
    return CliInvocationRow(ident, ts, binary, tuple(args), exit_code, duration)


def _read_sprint_invocations(
    session: _Session, request: RecentSprintInvocations, target: LocalTarget
) -> HistoryReadResult:
    kind = request.kind
    conn, deadline = session.conn, session.deadline
    try:
        owned = _is_owned(target, request.project_root)
    except (OSError, RuntimeError) as exc:
        return _unavailable(kind, "path_resolution_failed", f"{type(exc).__name__}: {exc}")
    try:
        shape_reason = _check_cli_shape(session)
        if shape_reason is not None:
            return _unavailable(kind, shape_reason)
        if not owned:
            reason = "unscoped_store"
            coverage = HistoryReadCoverage(reasons=(reason,))
            return HistoryReadResult(
                "partial",
                reason,
                coverage=coverage,
                diagnostics=(_diagnostic(kind, "partial", reason),),
            )
        max_id = conn.execute(_MAX_ID_SQL).fetchone()["max_id"]
    except (sqlite3.Error, HistoryUnavailable) as exc:
        return _unavailable(kind, _failure_reason(exc, deadline), str(exc))
    if max_id is None:  # empty table: nothing ever recorded
        return HistoryReadResult("available", coverage=HistoryReadCoverage(reached_start=True))

    rows: list[CliInvocationRow] = []
    reasons: set[str] = set()
    completed_low: int | None = None
    attempted: tuple[int, int] | None = None
    visited = fetched_total = payload = malformed = oversized = 0
    lowest_allowed = max(1, max_id - MAX_ID_SPAN + 1)
    hi = max_id
    while hi >= lowest_allowed:
        if deadline.expired():
            reasons.add("deadline")
            break
        if fetched_total >= MAX_ROWS:
            reasons.add("row_cap")
            break
        lo = max(lowest_allowed, hi - WINDOW_WIDTH + 1)
        remaining = MAX_ROWS - fetched_total
        visited += hi - lo + 1  # upper bound: includes a window the deadline interrupts
        try:
            fetched = conn.execute(_WINDOW_SQL, (lo, hi, remaining + 1)).fetchall()
        except (sqlite3.Error, HistoryUnavailable) as exc:
            if deadline.expired():
                attempted = (lo, hi)
                reasons.add("deadline")
                break
            return _unavailable(kind, _failure_reason(exc, deadline), str(exc))
        capped = len(fetched) > remaining
        if capped:
            fetched = fetched[:remaining]
        fetched_total += len(fetched)
        interrupted = False
        for row in fetched:
            if deadline.expired():
                interrupted = True
                break
            decoded = _decode_row(row)
            if decoded == "oversized":
                oversized += 1
                reasons.add("payload_limit")
            elif decoded == "malformed":
                malformed += 1
                reasons.add("malformed_row")
            else:
                rows.append(decoded)
                payload += row["args_bytes"] or 0
        if interrupted or deadline.expired():
            attempted = (lo, hi)
            reasons.add("deadline")
            break
        if capped:
            completed_low = fetched[-1]["id"]
            reasons.add("row_cap")
            break
        completed_low = lo
        hi = lo - 1
    else:
        if lowest_allowed > 1:
            reasons.add("id_span_cap")

    reached_start = completed_low is not None and completed_low <= 1
    coverage = HistoryReadCoverage(
        max_id=max_id,
        completed_range=None if completed_low is None else (completed_low, max_id),
        attempted_range=attempted,
        visited_rows_upper_bound=visited,
        returned_rows=len(rows),
        skipped_malformed=malformed,
        skipped_oversized=oversized,
        payload_bytes=payload,
        reasons=tuple(r for r in _REASON_ORDER if r in reasons),
        reached_start=reached_start,
    )
    if not coverage.reasons:
        return HistoryReadResult("available", rows=tuple(rows), coverage=coverage)
    primary = coverage.reasons[0]
    detail = f"{len(rows)} rows retained, {malformed} malformed, {oversized} oversized"
    return HistoryReadResult(
        "partial",
        primary,
        rows=tuple(rows),
        coverage=coverage,
        diagnostics=(_diagnostic(kind, "partial", primary, detail),),
    )


# ------------------------------------------------------------------------ recommendations


def decode_recommendation_row(row: sqlite3.Row | Sequence[Any]) -> RecommendationEventRow | None:
    """Decode one ``RECOMMENDATION_EVENT_COLUMNS``-ordered row; ``None`` when a value is mistyped.

    SQLite is dynamically typed, so a NOT NULL ``TEXT`` column can still hold a blob or number.
    A mistyped row is never partially trusted.
    """
    values = tuple(row[i] for i in range(len(RECOMMENDATION_EVENT_COLUMNS)))
    (
        event_id,
        rec_id,
        kind,
        ts,
        project_key,
        session_id,
        invocation_id,
        as_of,
        rank,
        action_type,
        action_key,
        action_fingerprint,
        target,
        target_key,
        action_spec,
        requested_top,
        requested_types,
    ) = values
    text = (
        event_id,
        rec_id,
        kind,
        ts,
        project_key,
        invocation_id,
        as_of,
        action_type,
        action_key,
        action_fingerprint,
        target,
        target_key,
        action_spec,
        requested_types,
    )
    if not all(isinstance(v, str) for v in text):
        return None
    if session_id is not None and not isinstance(session_id, str):
        return None
    if isinstance(rank, bool) or not isinstance(rank, int):
        return None
    if requested_top is not None and (
        isinstance(requested_top, bool) or not isinstance(requested_top, int)
    ):
        return None
    return RecommendationEventRow(*values)


def _read_recommendation_schema(
    session: _Session, request: RecommendationSchemaProbe
) -> HistoryReadResult:
    kind = request.kind
    try:
        status = recommendation_schema_status(session.conn)
        session.observe()
    except (sqlite3.Error, HistoryUnavailable) as exc:
        return _unavailable(kind, _failure_reason(exc, session.deadline), str(exc))
    return HistoryReadResult("available", schema_status=status)


def _read_recommendation_lookup(
    session: _Session, request: RecommendationLookup
) -> HistoryReadResult:
    kind = request.kind
    conn = session.conn
    try:
        status = recommendation_schema_status(conn)
        session.observe()
        if not status.read_compatible:
            return _unavailable(kind, status.reason or "incompatible_table")
        fetched = conn.execute(
            RECOMMENDATION_LOOKUP_SQL, (request.rec_id, request.project_key)
        ).fetchall()
    except (sqlite3.Error, HistoryUnavailable) as exc:
        return _unavailable(kind, _failure_reason(exc, session.deadline), str(exc))
    rows: list[RecommendationEventRow] = []
    for raw in fetched:
        decoded = decode_recommendation_row(raw)
        if decoded is None:
            return _unavailable(kind, "malformed_event")
        rows.append(decoded)
    return HistoryReadResult(
        "available", rows=tuple(rows), coverage=HistoryReadCoverage(returned_rows=len(rows))
    )

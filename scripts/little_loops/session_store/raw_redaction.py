"""Bounded, rerunnable scrub of stored ``raw_events`` payload columns (ENH-3752).

``redact_raw_events`` re-applies the history redaction policy (:mod:`little_loops.pii`) to the
``raw_line`` and ``parsed_json`` columns of rows written before ingest sanitization existed.
It is explicit maintenance, not ingestion: no source file is read, every other column and every
cursor/watermark is left alone, and a column the policy does not change keeps its exact bytes
and SQL type. Both backends share one core: a local SQLite store (short explicit transactions)
or the configured libSQL project store (one atomic ``executemany`` per request).

Safety model:

- Rows are scanned by ``id`` keyset up to a ``MAX(id)`` captured once; each page is projected
  with ``typeof``/length/bounded-BLOB so no oversized or malformed value is ever decoded by the
  database driver, and each payload is decoded under hard byte/decompression caps.
- Writes are guarded by the original storage class, bytes and host/event-type context
  (``UPDATE ... WHERE id = ? AND typeof(...) AND CAST(... AS BLOB) IS ?``): a concurrent writer's
  change is reported as a conflict and is never overwritten.
- Short or lost acknowledgements are reconciled by bounded re-reads and at most one guarded
  retry per row. Counters distinguish acknowledged applications from observed-desired rows.
- Failures are content-free: only row id, column name and a fixed reason code are reported.

Logical guarantee only: derived/FTS/summary rows, original transcripts, backups, WAL/free pages
and provider history are not covered.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import sqlite3
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, NoReturn

from little_loops.pii import (
    HISTORY_ERROR_REASONS,
    HISTORY_REDACTION_VERSION,
    HistorySanitizationError,
    is_replay_safe_history_context,
    sanitize_history_payload,
)
from little_loops.session_store import remote_schema
from little_loops.session_store.backend import (
    HistoryError,
    HistoryTarget,
    HistoryUnavailable,
    LocalTarget,
    RemoteTarget,
    _resolve_once,
    connect_existing_writable,
    connect_readonly,
    open_history,
)
from little_loops.session_store.db import DEFAULT_DB_PATH
from little_loops.session_store.schema import SCHEMA_VERSION, _current_version
from little_loops.session_store.writers import _pack_payload

# -- vocabulary ------------------------------------------------------------------------------

RAW_REDACTION_REASONS: tuple[str, ...] = (
    *HISTORY_ERROR_REASONS,
    "unsupported_context",
    "unsupported_storage",
    "invalid_encoding",
    "invalid_compression",
    "invalid_json",
    "conflict",
    "vanished",
    "unconfirmed",
    "backend_failure",
    "backend_invariant",
    "schema_mismatch",
    "target_unavailable",
    "interrupted",
)

#: Why a run stopped before exhausting the snapshot (``None`` means it did not stop early).
RAW_REDACTION_STOP_REASONS: tuple[str, ...] = (
    "interrupted",
    "target_unavailable",
    "schema_mismatch",
    "backend_failure",
    "backend_invariant",
    "unconfirmed",
)

# -- bounds (not user settings; each keeps a conforming run inside the remote request limit) --

STORED_CAP = 1 << 20  # stored bytes per payload column: the largest value one page may fetch
DECODED_CAP = 4 << 20  # decompressed/decoded bytes per payload column (zlib-bomb ceiling)
CONTEXT_CAP = 256  # stored bytes of host / event_type
PAGE_ROWS_MAX = 8  # value-returning rows per page: 8 rows x 2 columns x STORED_CAP = 16 MiB
REPLACEMENT_BYTES_CAP = 8 << 20  # encoded replacements retained before a flush
REQUEST_BYTES_CAP = 8 << 20  # serialized outbound write request, including overhead
PROBLEM_CAP = 100  # retained diagnostics; further ones only increment ``omitted_problems``

UPDATE_SQL = (
    "UPDATE raw_events "
    "SET raw_line = COALESCE(?, raw_line), parsed_json = COALESCE(?, parsed_json) "
    "WHERE id = ? AND typeof(raw_line) = ? AND CAST(raw_line AS BLOB) IS ? "
    "AND typeof(parsed_json) = ? AND CAST(parsed_json AS BLOB) IS ? "
    "AND typeof(host) = 'text' AND host IS ? "
    "AND typeof(event_type) = 'text' AND event_type IS ?"
)

_COLUMNS = ("raw_line", "parsed_json")


# -- public types ----------------------------------------------------------------------------


class RawRedactionError(HistoryError):
    """Maintenance failure before a snapshot exists.

    ``reason`` is a fixed stop code; ``guidance`` is ``"migrate"`` / ``"upgrade"`` for a schema
    mismatch the operator can resolve, else ``None``. ``str()`` is the reason alone: backend
    messages, endpoints and credentials are never carried.
    """

    def __init__(self, reason: str, guidance: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.guidance = guidance


@dataclass(frozen=True)
class RawRedactionProblem:
    """One content-free diagnostic: row id (``None`` for an operation), column, reason code."""

    row_id: int | None
    column: str | None
    reason: str


@dataclass(frozen=True)
class RawRedactionReport:
    """Outcome of one ``redact_raw_events`` call.

    ``updates_applied`` counts acknowledged committed UPDATE applications (not distinct rows);
    ``unattributed_updates_applied`` is the part whose rule breakdown is unknown (a short
    acknowledgement). ``reconciled`` counts candidates later observed already desired.
    ``counts_by_column`` holds attributed rule counts (planned counts in preview).
    ``counts_complete`` is false when ambiguous commits keep the confirmed counters a lower
    bound. ``complete`` means the snapshot was exhausted with no failure, conflict, unconfirmed
    row or stop reason.
    """

    policy_version: int
    target: dict[str, str]
    dry_run: bool
    snapshot_max_id: int | None
    last_scanned_id: int | None
    scanned: int
    updates_applied: int
    would_change: int
    counts_by_column: dict[str, dict[str, int]]
    counts_complete: bool
    unattributed_updates_applied: int
    reconciled: int
    failed: int
    conflicts: int
    unconfirmed: int
    problems: tuple[RawRedactionProblem, ...]
    omitted_problems: int
    stop_reason: str | None
    complete: bool


# -- bounded strict decode -------------------------------------------------------------------


class _Refusal(Exception):
    """A content-free per-column refusal carrying a ``RAW_REDACTION_REASONS`` code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _refuse(reason: str) -> NoReturn:
    raise _Refusal(reason) from None


def _reject_constant(_name: str) -> NoReturn:
    raise ValueError("non-finite JSON constant")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def decode_payload(sql_type: str, data: bytes) -> dict[str, Any]:
    """Decode one stored payload column under the maintenance bounds.

    ``text`` is strict UTF-8; ``blob`` is a single complete zlib stream whose output is bounded
    to ``DECODED_CAP``. The JSON root must be an object with unique keys and finite numbers.
    Raises :class:`_Refusal` (fixed code, no chained context). The sanitizer's depth/node limits
    act after this decoder and do not bound structural allocation inside ``json.loads``.
    """
    if sql_type == "text":
        if len(data) > DECODED_CAP:
            _refuse("resource_limit")
        raw = data
    else:
        stream = zlib.decompressobj()
        try:
            raw = stream.decompress(data, DECODED_CAP + 1)
        except zlib.error:
            _refuse("invalid_compression")
        if len(raw) > DECODED_CAP:
            _refuse("resource_limit")
        if not stream.eof or stream.unconsumed_tail or stream.unused_data:
            _refuse("invalid_compression")  # truncated, trailing or concatenated stream
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _refuse("invalid_encoding")
    try:
        value = json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except RecursionError:
        _refuse("resource_limit")
    except ValueError:  # JSONDecodeError, duplicate keys, constants, long-integer conversion
        _refuse("invalid_json")
    if type(value) is not dict:
        _refuse("invalid_json")
    return value


# -- projections and keyset ------------------------------------------------------------------


@dataclass(frozen=True)
class _Col:
    sql_type: str
    length: int | None
    value: bytes | None  # NULL or over the cap when ``None`` (``length`` tells which)


@dataclass(frozen=True)
class _Observed:
    id: int
    raw: _Col
    parsed: _Col
    host: _Col
    event_type: _Col


def _projection(name: str, cap: int) -> str:
    return (
        f"typeof({name}), length(CAST({name} AS BLOB)), "
        f"CASE WHEN length(CAST({name} AS BLOB)) <= {int(cap)} THEN CAST({name} AS BLOB) END"
    )


def _projection_sql() -> str:
    return (
        f"SELECT id, {_projection('raw_line', STORED_CAP)}, {_projection('parsed_json', STORED_CAP)}, "
        f"{_projection('host', CONTEXT_CAP)}, {_projection('event_type', CONTEXT_CAP)} "
        "FROM raw_events"
    )


def _observed(row: Sequence[Any]) -> _Observed:
    cols = [_Col(row[i], row[i + 1], row[i + 2]) for i in (1, 4, 7, 10)]
    return _Observed(int(row[0]), *cols)


def _snapshot_max_id(conn: Any) -> int | None:
    """``MAX(id)`` without ``COALESCE``: ``None`` means an empty table."""
    value = conn.execute("SELECT MAX(id) FROM raw_events").fetchone()[0]
    return None if value is None else int(value)


def _fetch_page(conn: Any, *, snapshot: int, last_id: int | None, limit: int) -> list[_Observed]:
    if last_id is None:
        sql = f"{_projection_sql()} WHERE id <= ? ORDER BY id LIMIT ?"
        params: tuple[Any, ...] = (snapshot, limit)
    else:
        sql = f"{_projection_sql()} WHERE id <= ? AND id > ? ORDER BY id LIMIT ?"
        params = (snapshot, last_id, limit)
    return [_observed(r) for r in conn.execute(sql, params).fetchall()]


def _fetch_one(conn: Any, row_id: int) -> _Observed | None:
    row = conn.execute(f"{_projection_sql()} WHERE id = ?", (row_id,)).fetchone()
    return None if row is None else _observed(row)


# -- wire-byte upper bound -------------------------------------------------------------------

_ENVELOPE = 1024  # pipeline wrapper, baton/close request and JSON punctuation
_STEP = 256  # per statement/step: type tags, condition objects, separators
_ARG = 64  # per parameter: type tag and quoting
_CTRL_STEPS = 3  # begin / commit / rollback in an ``executemany`` batch
_CONTROL = re.compile(r"[\x00-\x1f]")


def _component_bytes(value: Any) -> int:
    """Conservative serialized size of one encoded Hrana parameter."""
    if value is None:
        return _ARG
    if isinstance(value, (bytes, bytearray)):
        return 4 * math.ceil(len(value) / 3) + _ARG  # base64
    if isinstance(value, str):
        if value.isascii():
            if _CONTROL.search(value) is None:
                return 2 * len(value) + _ARG  # only '"' and '\\' double
            return 6 * len(value) + _ARG  # control characters become \u00XX
        return 12 * len(value) + _ARG  # an astral code point is a 12-byte surrogate pair
    return len(json.dumps(value)) + _ARG


def _estimate_request_bytes(sql: str, rows: Sequence[Sequence[Any]], *, shape: str) -> int:
    """Upper bound of the pipeline body for ``shape`` in ``{"batch", "execute"}``.

    An estimate, not a serializer: it never builds the outbound body, and it is pinned against
    captured real request bodies in the test suite.
    """
    if shape not in ("batch", "execute"):
        raise ValueError(shape)
    sql_bytes = 2 * len(sql) + _STEP
    total = _ENVELOPE + (_CTRL_STEPS * _STEP if shape == "batch" else 0)
    for params in rows:
        total += sql_bytes + _STEP + sum(_component_bytes(p) for p in params)
    return total


# -- planning --------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Plan:
    obs: _Observed
    raw: bytes | None  # replacement bytes in the column's original storage class
    parsed: bytes | None
    counts: dict[str, dict[str, int]]
    params: tuple[Any, ...]
    replacement_bytes: int

    @property
    def changed(self) -> bool:
        return self.raw is not None or self.parsed is not None


def _context(obs: _Observed) -> tuple[str, str] | None:
    """Stored host/event_type if both are in-bounds UTF-8 TEXT the registry can protect."""
    decoded: list[str] = []
    for col in (obs.host, obs.event_type):
        if col.sql_type != "text" or col.value is None:
            return None
        try:
            decoded.append(col.value.decode("utf-8"))
        except UnicodeDecodeError:
            return None
    host, event_type = decoded
    if not is_replay_safe_history_context(host=host, event_type=event_type):
        return None
    return host, event_type


def _plan_column(col: _Col, host: str, event_type: str) -> tuple[bytes | None, dict[str, int]]:
    """Sanitize one column; ``(None, {})`` when the policy changes nothing."""
    if col.sql_type not in ("text", "blob"):
        _refuse("unsupported_storage")
    if col.value is None:
        _refuse("resource_limit")
    source = decode_payload(col.sql_type, col.value)
    try:
        result = sanitize_history_payload(source, host=host, event_type=event_type)
    except HistorySanitizationError as exc:
        _refuse(exc.reason)
    del source
    if not result.counts:
        return None, {}
    try:
        text = json.dumps(result.payload, ensure_ascii=True, allow_nan=False)
    except RecursionError:
        _refuse("resource_limit")
    except (TypeError, ValueError):
        _refuse("invalid_json")
    stored = text.encode("ascii") if col.sql_type == "text" else _pack_payload(text)
    if len(stored) > STORED_CAP:
        _refuse("resource_limit")
    decode_payload(col.sql_type, stored)  # a successful output must stay maintainable on rerun
    return stored, dict(result.counts)


def _update_params(
    obs: _Observed, new_raw: bytes | None, new_parsed: bytes | None
) -> tuple[Any, ...]:
    """Bind replacements in the original SQL type; ``None`` retains the sibling column."""

    def repl(col: _Col, new: bytes | None) -> Any:
        if new is None:
            return None
        return new.decode("ascii") if col.sql_type == "text" else new

    assert obs.host.value is not None and obs.event_type.value is not None
    return (
        repl(obs.raw, new_raw),
        repl(obs.parsed, new_parsed),
        obs.id,
        obs.raw.sql_type,
        obs.raw.value,
        obs.parsed.sql_type,
        obs.parsed.value,
        obs.host.value.decode("utf-8"),
        obs.event_type.value.decode("utf-8"),
    )


def _plan_row(obs: _Observed) -> tuple[_Plan | None, tuple[tuple[str | None, str], ...]]:
    """Validate a row and plan its replacements; ``(None, problems)`` leaves it unchanged."""
    ctx = _context(obs)
    if ctx is None:
        return None, ((None, "unsupported_context"),)
    host, event_type = ctx
    problems: list[tuple[str | None, str]] = []
    replacements: dict[str, bytes] = {}
    counts: dict[str, dict[str, int]] = {}
    for name, col in zip(_COLUMNS, (obs.raw, obs.parsed), strict=True):
        try:
            new, col_counts = _plan_column(col, host, event_type)
        except _Refusal as exc:
            problems.append((name, exc.reason))
            continue
        if new is not None:
            replacements[name] = new
            counts[name] = col_counts
    if problems:
        return None, tuple(problems)  # a failed sibling discards the other column's plan
    new_raw, new_parsed = replacements.get("raw_line"), replacements.get("parsed_json")
    if new_raw is None and new_parsed is None:
        return _Plan(obs, None, None, {}, (), 0), ()
    params = _update_params(obs, new_raw, new_parsed)
    if _estimate_request_bytes(UPDATE_SQL, [params], shape="batch") > REQUEST_BYTES_CAP:
        return None, ((None, "resource_limit"),)
    size = len(new_raw or b"") + len(new_parsed or b"")
    return _Plan(obs, new_raw, new_parsed, counts, params, size), ()


def _state(obs: _Observed) -> tuple[Any, ...]:
    return tuple((c.sql_type, c.value) for c in (obs.raw, obs.parsed, obs.host, obs.event_type))


def _desired_state(plan: _Plan) -> tuple[Any, ...]:
    o = plan.obs
    return (
        (o.raw.sql_type, plan.raw if plan.raw is not None else o.raw.value),
        (o.parsed.sql_type, plan.parsed if plan.parsed is not None else o.parsed.value),
        (o.host.sql_type, o.host.value),
        (o.event_type.sql_type, o.event_type.value),
    )


def _classify(plan: _Plan, seen: _Observed | None) -> str:
    if seen is None:
        return "vanished"
    state = _state(seen)
    if state == _desired_state(plan):
        return "desired"
    if state == _state(plan.obs):
        return "original"
    return "changed"


# -- accounting ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Tally:
    """All mutable report state in one immutable value.

    Every transition builds a new value and the run stores it with a single attribute
    assignment, so a signal between bytecodes sees the old or the new state, never half of each.
    """

    scanned: int = 0
    last_scanned_id: int | None = None
    would_change: int = 0
    updates_applied: int = 0
    unattributed: int = 0
    reconciled: int = 0
    counts_by_column: dict[str, dict[str, int]] = field(default_factory=dict)
    counts_complete: bool = True
    failed_ids: frozenset[int] = frozenset()
    conflict_ids: frozenset[int] = frozenset()
    unconfirmed_ids: frozenset[int] = frozenset()
    problems: tuple[RawRedactionProblem, ...] = ()
    omitted: int = 0
    stop_reason: str | None = None
    pending: tuple[int, ...] = ()  # ids of a unit whose acknowledgement is not yet accounted
    commit_issued: bool = False

    def problem(self, row_id: int | None, column: str | None, reason: str) -> _Tally:
        if len(self.problems) < PROBLEM_CAP:
            entry = RawRedactionProblem(row_id, column, reason)
            return replace(self, problems=(*self.problems, entry))
        return replace(self, omitted=self.omitted + 1)

    def with_counts(self, counts: dict[str, dict[str, int]]) -> _Tally:
        merged = {col: dict(rules) for col, rules in self.counts_by_column.items()}
        for col, rules in counts.items():
            slot = merged.setdefault(col, {})
            for rule, n in rules.items():
                slot[rule] = slot.get(rule, 0) + n
        return replace(self, counts_by_column=merged)

    def stopped(self, reason: str) -> _Tally:
        if self.stop_reason is not None:
            return self
        return replace(self, stop_reason=reason).problem(None, None, reason)


def _target_description(target: HistoryTarget) -> dict[str, str]:
    if isinstance(target, LocalTarget):
        return {"provider": "sqlite", "path": str(target.path)}
    return {"provider": target.config.provider, "project_id": target.config.project_id or ""}


# -- open and preflight ----------------------------------------------------------------------


def _open_error(exc: BaseException) -> RawRedactionError:
    if isinstance(exc, (HistoryUnavailable, sqlite3.Error)):
        return RawRedactionError("target_unavailable")
    return RawRedactionError("backend_failure")


def _version_error(version: int) -> RawRedactionError | None:
    if version < SCHEMA_VERSION:
        return RawRedactionError("schema_mismatch", "migrate")
    if version > SCHEMA_VERSION:
        return RawRedactionError("schema_mismatch", "upgrade")
    return None


def _payload_columns_not_null(conn: Any) -> bool:
    info = {r[1]: r[3] for r in conn.execute("PRAGMA table_info(raw_events)").fetchall()}
    return all(info.get(name) == 1 for name in _COLUMNS)


def _open_local(target: LocalTarget, dry_run: bool) -> Any:
    probe = None
    try:
        probe = connect_readonly(target)
        error = _version_error(_current_version(probe))
        if error is None and not _payload_columns_not_null(probe):
            error = RawRedactionError("schema_mismatch")
        if error is not None:
            raise error
        if dry_run:
            kept, probe = probe, None
            return kept
        probe.close()
        probe = None
        return connect_existing_writable(target)
    except RawRedactionError:
        raise
    except (HistoryError, sqlite3.Error) as exc:
        raise _open_error(exc) from None
    finally:
        if probe is not None:
            with contextlib.suppress(Exception):
                probe.close()


def _open_remote(target: RemoteTarget, dry_run: bool) -> Any:
    cfg = target.config
    try:
        conn: Any = connect_readonly(target) if dry_run else open_history(target)
        # A fresh read, never the process verification cache or the permissive read policy.
        state = remote_schema.read_state(conn.client)
        error = _version_error(state.version)
        if error is None and (not cfg.project_id or state.project_id is None):
            error = RawRedactionError("schema_mismatch", "migrate" if cfg.project_id else None)
        if error is None and state.project_id != cfg.project_id:
            error = RawRedactionError("schema_mismatch")
        if error is None and not _payload_columns_not_null(conn):
            error = RawRedactionError("schema_mismatch")
        if error is not None:
            raise error
        return conn
    except RawRedactionError:
        raise
    except HistoryError as exc:
        raise _open_error(exc) from None


# -- guarded writes --------------------------------------------------------------------------


def _commit(conn: Any) -> None:
    conn.execute("COMMIT")


class _Run:
    """One scan: planning, packing, guarded writes, reconciliation and accounting."""

    def __init__(
        self, conn: Any, target: HistoryTarget, snapshot: int | None, batch: int, dry_run: bool
    ) -> None:
        self.conn = conn
        self.target = target
        self.snapshot = snapshot
        self.limit = min(batch, PAGE_ROWS_MAX)
        self.dry_run = dry_run
        self.remote = isinstance(target, RemoteTarget)
        self.tally = _Tally()
        self.exhausted = snapshot is None
        self._group: list[_Plan] = []
        self._group_bytes = 0

    # transitions: each builds one new tally and assigns it once -------------------------

    def stop(self, reason: str) -> None:
        self.tally = self.tally.stopped(reason)

    def begin(self, ids: Sequence[int], *, commit_issued: bool = False) -> None:
        self.tally = replace(self.tally, pending=tuple(ids), commit_issued=commit_issued)

    def mark_commit_issued(self) -> None:
        self.tally = replace(self.tally, commit_issued=True)

    def settle_zero(self) -> None:
        self.tally = replace(self.tally, pending=(), commit_issued=False)

    def settle_ambiguous(self) -> None:
        """The outcome is unknown but a reconciliation read will classify every candidate."""
        self.tally = replace(self.tally, pending=(), commit_issued=False, counts_complete=False)

    def settle_unconfirmed(self) -> None:
        t = self.tally
        self.tally = replace(
            t,
            pending=(),
            commit_issued=False,
            counts_complete=False,
            unconfirmed_ids=t.unconfirmed_ids | frozenset(t.pending),
        )

    def acknowledge(self, plans: Sequence[_Plan], ack: int, *, attributed: bool) -> None:
        t = self.tally
        merged = t.with_counts(_merge_plan_counts(plans)) if attributed else t
        self.tally = replace(
            merged,
            updates_applied=t.updates_applied + ack,
            unattributed=t.unattributed + (0 if attributed else ack),
            counts_complete=t.counts_complete and (attributed or ack == 0),
            pending=(),
            commit_issued=False,
        )

    def resolve_pending(self) -> None:
        """Settle a unit left pending by an interrupt/error; never reconciles over the network."""
        if not self.tally.pending:
            return
        if getattr(self.conn, "in_transaction", False):
            try:
                self.conn.execute("ROLLBACK")
            except BaseException:
                self.settle_unconfirmed()
            else:
                self.settle_zero()
        elif self.tally.commit_issued:
            self.settle_unconfirmed()
        else:
            self.settle_zero()

    # scan -------------------------------------------------------------------------------------

    def scan(self) -> None:
        if self.snapshot is None:
            return
        last: int | None = None
        while True:
            try:
                page = _fetch_page(
                    self.conn, snapshot=self.snapshot, last_id=last, limit=self.limit
                )
            except (HistoryError, sqlite3.Error):
                self.stop("backend_failure")
                return
            if not page:
                self.exhausted = True
                return
            for obs in page:
                self._handle(obs)
                last = obs.id
                if self.tally.stop_reason is not None:
                    return
            self._flush()
            if self.tally.stop_reason is not None:
                return

    def _handle(self, obs: _Observed) -> None:
        plan, problems = _plan_row(obs)
        t = replace(self.tally, scanned=self.tally.scanned + 1, last_scanned_id=obs.id)
        if problems:
            for column, reason in problems:
                t = t.problem(obs.id, column, reason)
            t = replace(t, failed_ids=t.failed_ids | {obs.id})
        elif plan is not None and plan.changed:
            t = replace(t, would_change=t.would_change + 1)
            if self.dry_run:
                t = t.with_counts(plan.counts)
        self.tally = t
        if plan is not None and plan.changed and not self.dry_run:
            self._enqueue(plan)

    def _enqueue(self, plan: _Plan) -> None:
        if self._group:
            rows = [p.params for p in self._group] + [plan.params]
            over = (
                self._group_bytes + plan.replacement_bytes > REPLACEMENT_BYTES_CAP
                or _estimate_request_bytes(UPDATE_SQL, rows, shape="batch") > REQUEST_BYTES_CAP
            )
            if over:
                self._flush()
                if self.tally.stop_reason is not None:
                    return
        self._group.append(plan)
        self._group_bytes += plan.replacement_bytes

    def _flush(self) -> None:
        plans, self._group, self._group_bytes = self._group, [], 0
        if plans:
            self._apply(plans)

    def _apply(self, plans: list[_Plan]) -> None:
        try:
            ack = _write_unit(self, plans)
        except (HistoryError, sqlite3.Error):
            self.stop("backend_failure")
            return
        n = len(plans)
        if ack is not None and (ack < 0 or ack > n):
            self.tally = replace(self.tally, pending=(), commit_issued=False, counts_complete=False)
            self.stop("backend_invariant")
            return
        if ack == n:
            self.acknowledge(plans, ack, attributed=True)
            return
        if ack is not None:
            self.acknowledge(plans, ack, attributed=False)
        self._reconcile(plans)

    # reconciliation -----------------------------------------------------------------------

    def _reconcile(self, plans: list[_Plan]) -> None:
        for index, plan in enumerate(plans):
            try:
                self._reconcile_one(plan)
            except (HistoryError, sqlite3.Error):
                rest = plans[index:]
                t = self.tally
                t = replace(
                    t,
                    pending=(),
                    commit_issued=False,
                    counts_complete=False,
                    unconfirmed_ids=t.unconfirmed_ids | {p.obs.id for p in rest},
                )
                for p in rest:
                    t = t.problem(p.obs.id, None, "unconfirmed")
                self.tally = t.stopped("unconfirmed")
                return
            if self.tally.stop_reason is not None:
                return

    def _reconcile_one(self, plan: _Plan) -> None:
        row_id = plan.obs.id
        verdict = _classify(plan, _fetch_one(self.conn, row_id))
        if verdict == "original":
            self.begin([row_id], commit_issued=True)
            ack = self.conn.execute(UPDATE_SQL, plan.params).rowcount
            if ack == 1:
                self.acknowledge([plan], 1, attributed=True)
                return
            self.settle_zero()
            if ack != 0:
                self.stop("backend_invariant")
                return
            verdict = _classify(plan, _fetch_one(self.conn, row_id))
            if verdict == "original":
                verdict = "changed"  # a second zero is a conflict even if ABA restored it
        t = self.tally
        if verdict == "desired":
            self.tally = replace(t, reconciled=t.reconciled + 1)
        else:
            reason = "vanished" if verdict == "vanished" else "conflict"
            self.tally = replace(t, conflict_ids=t.conflict_ids | {row_id}).problem(
                row_id, None, reason
            )

    # report -------------------------------------------------------------------------------------

    def report(self) -> RawRedactionReport:
        t = self.tally
        complete = (
            self.exhausted
            and t.stop_reason is None
            and not (t.failed_ids or t.conflict_ids or t.unconfirmed_ids)
        )
        return RawRedactionReport(
            policy_version=HISTORY_REDACTION_VERSION,
            target=_target_description(self.target),
            dry_run=self.dry_run,
            snapshot_max_id=self.snapshot,
            last_scanned_id=t.last_scanned_id,
            scanned=t.scanned,
            updates_applied=t.updates_applied,
            would_change=t.would_change,
            counts_by_column={c: dict(r) for c, r in t.counts_by_column.items()},
            counts_complete=t.counts_complete,
            unattributed_updates_applied=t.unattributed,
            reconciled=t.reconciled,
            failed=len(t.failed_ids),
            conflicts=len(t.conflict_ids),
            unconfirmed=len(t.unconfirmed_ids),
            problems=t.problems,
            omitted_problems=t.omitted,
            stop_reason=t.stop_reason,
            complete=complete,
        )


def _merge_plan_counts(plans: Sequence[_Plan]) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = {}
    for plan in plans:
        for col, rules in plan.counts.items():
            slot = merged.setdefault(col, {})
            for rule, n in rules.items():
                slot[rule] = slot.get(rule, 0) + n
    return merged


def _write_unit(run: _Run, plans: list[_Plan]) -> int | None:
    """Run one guarded unit; return the acknowledged count, ``None`` if the outcome is unknown.

    Local: explicit BEGIN IMMEDIATE ... COMMIT; the count is only acknowledged after commit.
    Remote: one atomic ``executemany``; a transport failure is an ambiguous commit. The unit is
    left pending in the tally for the caller to account (so an interrupt between this return and
    that transition is still classified unconfirmed).
    """
    conn = run.conn
    params = [p.params for p in plans]
    ids = [p.obs.id for p in plans]
    if run.remote:
        run.begin(ids, commit_issued=True)  # in flight: the request may commit
        try:
            return int(conn.executemany(UPDATE_SQL, params).rowcount)
        except HistoryUnavailable:
            run.settle_ambiguous()
            return None
        except KeyboardInterrupt:
            run.resolve_pending()
            raise
        except BaseException:
            run.settle_zero()  # a server-side error response rolled the atomic batch back
            raise
    run.begin(ids)
    try:
        conn.execute("BEGIN IMMEDIATE")
        count = int(conn.executemany(UPDATE_SQL, params).rowcount)
        run.mark_commit_issued()
        _commit(conn)
    except BaseException:  # KeyboardInterrupt included: the pending unit is settled, never lost
        run.resolve_pending()
        raise
    return count


# -- entry point -----------------------------------------------------------------------------


def _validate_batch(batch_size: object) -> int:
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    return batch_size


def redact_raw_events(
    db: Path | str | HistoryTarget = DEFAULT_DB_PATH,
    *,
    batch_size: int = 2000,
    dry_run: bool = False,
) -> RawRedactionReport:
    """Scrub both stored raw payload columns under the current history policy.

    Resolves the target once (existing local/remote precedence, no fallback), requires an
    existing current-schema store (never creates or migrates), then scans every ``id`` up to a
    captured ``MAX(id)``. ``dry_run`` performs the same validation with no writes. Unchanged
    columns keep their exact bytes and SQL type; only payload columns are updated, in place.

    ``batch_size`` is a row ceiling per page and cannot exceed the internal byte/row bounds.

    Raises:
        ValueError: ``batch_size`` is not a positive ``int``.
        RawRedactionError: a fixed-code failure before a snapshot exists (target unavailable,
            schema mismatch, backend failure, interrupted). After the snapshot, failures and
            interruption return an incomplete report with ``stop_reason`` set instead.
    """
    batch = _validate_batch(batch_size)
    conn: Any = None
    run: _Run | None = None
    try:
        try:
            target = _resolve_once(db)
        except HistoryError:
            raise RawRedactionError("target_unavailable") from None
        conn = (
            _open_local(target, dry_run)
            if isinstance(target, LocalTarget)
            else _open_remote(target, dry_run)
        )
        try:
            snapshot = _snapshot_max_id(conn)
        except (HistoryError, sqlite3.Error):
            raise RawRedactionError("backend_failure") from None
        run = _Run(conn, target, snapshot, batch, dry_run)
        run.scan()
    except KeyboardInterrupt:
        if run is None:
            raise RawRedactionError("interrupted") from None
        run.resolve_pending()
        run.stop("interrupted")
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
    assert run is not None
    return run.report()

"""Isolated core for the ENH-3752 guarded raw_events redaction spike.

Speaks only the ``execute``/``executemany`` surface shared by ``sqlite3.Connection``
(``isolation_level=None``) and the public ``LibsqlConnection``. No sanitizer: callers
supply desired replacement bytes. See ``.ll/spikes/spike-ENH-3752.md``.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from little_loops.session_store.backend import HistoryUnavailable

PAYLOAD_CAP = 1 << 20  # 1 MiB stored payload
CONTEXT_CAP = 256
MAX_REQUEST_BYTES = 8 << 20

UPDATE_SQL = (
    "UPDATE raw_events "
    "SET raw_line = COALESCE(?, raw_line), parsed_json = COALESCE(?, parsed_json) "
    "WHERE id = ? AND typeof(raw_line) = ? AND CAST(raw_line AS BLOB) IS ? "
    "AND typeof(parsed_json) = ? AND CAST(parsed_json AS BLOB) IS ? "
    "AND typeof(host) = 'text' AND host IS ? "
    "AND typeof(event_type) = 'text' AND event_type IS ?"
)


# -- projections ---------------------------------------------------------


def _col(name: str, cap: int) -> str:
    cap = int(cap)
    return (
        f"typeof({name}), length(CAST({name} AS BLOB)), "
        f"CASE WHEN length(CAST({name} AS BLOB)) <= {cap} THEN CAST({name} AS BLOB) END"
    )


def projection_sql(cap: int = PAYLOAD_CAP) -> str:
    return (
        f"SELECT id, {_col('raw_line', cap)}, {_col('parsed_json', cap)}, "
        f"{_col('host', CONTEXT_CAP)}, {_col('event_type', CONTEXT_CAP)} FROM raw_events"
    )


@dataclass(frozen=True)
class Col:
    sql_type: str
    length: int | None
    value: bytes | None  # None => NULL or over the cap (length distinguishes)


@dataclass(frozen=True)
class Observed:
    id: int
    raw: Col
    parsed: Col
    host: Col
    event_type: Col


def _observed(row: Sequence[Any]) -> Observed:
    cols = [Col(row[i], row[i + 1], row[i + 2]) for i in (1, 4, 7, 10)]
    return Observed(int(row[0]), *cols)


def snapshot_max_id(conn: Any) -> int | None:
    """``MAX(id)`` with no COALESCE: ``None`` means an empty table."""
    return conn.execute("SELECT MAX(id) FROM raw_events").fetchone()[0]


def fetch_page(
    conn: Any, *, snapshot: int, last_id: int | None, limit: int, cap: int = PAYLOAD_CAP
) -> list[Observed]:
    if last_id is None:
        sql = f"{projection_sql(cap)} WHERE id <= ? ORDER BY id LIMIT ?"
        params: tuple[Any, ...] = (snapshot, limit)
    else:
        sql = f"{projection_sql(cap)} WHERE id <= ? AND id > ? ORDER BY id LIMIT ?"
        params = (snapshot, last_id, limit)
    return [_observed(r) for r in conn.execute(sql, params).fetchall()]


def fetch_one(conn: Any, row_id: int, cap: int = PAYLOAD_CAP) -> Observed | None:
    row = conn.execute(f"{projection_sql(cap)} WHERE id = ?", (row_id,)).fetchone()
    return None if row is None else _observed(row)


def context_supported(obs: Observed) -> bool:
    """Both context columns text-typed, within the cap and strict UTF-8."""
    for col in (obs.host, obs.event_type):
        if col.sql_type != "text" or col.value is None:
            return False
        try:
            col.value.decode("utf-8")
        except UnicodeDecodeError:
            return False
    return True


def has_not_null_payload_columns(conn: Any) -> bool:
    info = {r[1]: r[3] for r in conn.execute("PRAGMA table_info(raw_events)").fetchall()}
    return bool(info.get("raw_line")) and bool(info.get("parsed_json"))


# -- guarded update --------------------------------------------------------


def update_params(
    obs: Observed, new_raw: bytes | None, new_parsed: bytes | None
) -> tuple[Any, ...]:
    """Bind replacements in the *original* SQL type; NULL retains the sibling column."""
    for col in (obs.raw, obs.parsed, obs.host, obs.event_type):
        if col.value is None:
            raise ValueError("cannot guard a NULL/over-cap column")

    def repl(col: Col, new: bytes | None) -> Any:
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
        obs.host.value.decode(),
        obs.event_type.value.decode(),
    )


@dataclass(frozen=True)
class Desired:
    raw: bytes | None = None
    parsed: bytes | None = None


# -- accounting (atomic transitions) -------------------------------------


@dataclass(frozen=True)
class _State:
    applied: int = 0
    pending: tuple[int, ...] = ()
    commit_issued: bool = False
    unconfirmed: tuple[int, ...] = ()


@dataclass
class Accounting:
    """One attribute holds the whole state; each transition is a single STORE_ATTR, so a
    signal between bytecodes sees either the old or the new state, never half of each."""

    state: _State = field(default_factory=_State)

    def begin(self, ids: Sequence[int]) -> None:
        self.state = replace(self.state, pending=tuple(ids), commit_issued=False)

    def mark_commit_issued(self) -> None:
        self.state = replace(self.state, commit_issued=True)

    def acknowledge(self, n: int) -> None:
        self.state = replace(
            self.state, applied=self.state.applied + n, pending=(), commit_issued=False
        )

    def settle_zero(self) -> None:
        self.state = replace(self.state, pending=(), commit_issued=False)

    def settle_unconfirmed(self) -> None:
        self.state = replace(
            self.state,
            pending=(),
            commit_issued=False,
            unconfirmed=self.state.unconfirmed + self.state.pending,
        )

    def on_interrupt(self, conn: Any) -> None:
        """Resolve a pending unit after KeyboardInterrupt; never reconcile over the network."""
        if not self.state.pending:
            return
        if getattr(conn, "in_transaction", False):
            try:
                conn.execute("ROLLBACK")
            except Exception:
                self.settle_unconfirmed()
            else:
                self.settle_zero()
        elif self.state.commit_issued:
            self.settle_unconfirmed()
        else:
            self.settle_zero()


def apply_unit(
    conn: Any,
    observed: Sequence[Observed],
    desired: dict[int, Desired],
    acct: Accounting,
    *,
    before_commit: Callable[[], None] | None = None,
    after_commit: Callable[[], None] | None = None,
) -> int | None:
    """Run one guarded unit; return the acknowledged count, ``None`` if the outcome is unknown.

    Local: explicit BEGIN/COMMIT, count acknowledged only after commit. Remote:
    ``executemany`` (one atomic batch); a transport failure is an ambiguous commit.
    """
    params = [update_params(o, desired[o.id].raw, desired[o.id].parsed) for o in observed]
    acct.begin([o.id for o in observed])
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.executemany(UPDATE_SQL, params).rowcount
            if before_commit is not None:
                before_commit()
            acct.mark_commit_issued()
            conn.execute("COMMIT")
            if after_commit is not None:
                after_commit()
        except KeyboardInterrupt:
            acct.on_interrupt(conn)
            raise
        acct.acknowledge(count)
        return count
    try:
        count = conn.executemany(UPDATE_SQL, params).rowcount
    except HistoryUnavailable:
        acct.settle_unconfirmed()
        return None
    acct.acknowledge(count)
    return count


# -- reconciliation --------------------------------------------------------


@dataclass
class Counters:
    updates_applied: int = 0
    unattributed_updates_applied: int = 0
    reconciled: int = 0
    conflicts: int = 0
    vanished: int = 0
    unconfirmed: int = 0
    retries: int = 0
    counts_complete: bool = True


def _payload_state(obs: Observed) -> tuple[Any, ...]:
    return (
        (obs.raw.sql_type, obs.raw.value),
        (obs.parsed.sql_type, obs.parsed.value),
        (obs.host.sql_type, obs.host.value),
        (obs.event_type.sql_type, obs.event_type.value),
    )


def _desired_state(orig: Observed, want: Desired) -> tuple[Any, ...]:
    return (
        (orig.raw.sql_type, want.raw if want.raw is not None else orig.raw.value),
        (orig.parsed.sql_type, want.parsed if want.parsed is not None else orig.parsed.value),
        (orig.host.sql_type, orig.host.value),
        (orig.event_type.sql_type, orig.event_type.value),
    )


def _classify(orig: Observed, want: Desired, seen: Observed | None) -> str:
    if seen is None:
        return "vanished"
    state = _payload_state(seen)
    if state == _desired_state(orig, want):
        return "desired"
    if state == _payload_state(orig):
        return "original"
    return "changed"


def reconcile(conn: Any, orig: Observed, want: Desired, counters: Counters) -> str:
    """Classify one candidate; at most one guarded retry and one final bounded re-read."""
    try:
        verdict = _classify(orig, want, fetch_one(conn, orig.id))
        if verdict == "original":
            counters.retries += 1
            ack = conn.execute(UPDATE_SQL, update_params(orig, want.raw, want.parsed)).rowcount
            if ack == 1:
                counters.updates_applied += 1
                return "retried"
            if ack != 0:
                raise RuntimeError("backend_invariant: retry acknowledged an impossible count")
            verdict = _classify(orig, want, fetch_one(conn, orig.id))
            if verdict == "original":
                verdict = "changed"  # a second zero is a conflict even if still original (ABA)
    except HistoryUnavailable:
        counters.unconfirmed += 1
        return "unconfirmed"
    if verdict == "desired":
        counters.reconciled += 1
    elif verdict == "vanished":
        counters.vanished += 1
        counters.conflicts += 1
    else:
        counters.conflicts += 1
    return verdict


def process_unit(
    conn: Any,
    observed: Sequence[Observed],
    desired: dict[int, Desired],
    acct: Accounting,
    counters: Counters,
    *,
    after_apply: Callable[[], None] | None = None,
    **hooks: Callable[[], None],
) -> None:
    ack = apply_unit(conn, observed, desired, acct, **hooks)
    if after_apply is not None:
        after_apply()  # test seam: a concurrent writer acts between write and reconciliation
    n = len(observed)
    if ack is None:
        counters.counts_complete = False
    elif ack < 0 or ack > n:
        raise RuntimeError("backend_invariant: impossible acknowledgement")
    elif ack == n:
        counters.updates_applied += ack
        return
    else:
        counters.updates_applied += ack
        if ack > 0:
            counters.unattributed_updates_applied += ack
            counters.counts_complete = False
    for obs in observed:
        reconcile(conn, obs, desired[obs.id], counters)


# -- wire-byte upper bound -------------------------------------------------

_ENVELOPE = 1024
_STEP = 256
_ARG = 64
_CTRL_STEPS = 3  # begin / commit / rollback


def _component_bytes(value: Any) -> int:
    """Conservative serialized size of one encoded Hrana parameter."""
    if value is None:
        return _ARG
    if isinstance(value, (bytes, bytearray)):
        return 4 * math.ceil(len(value) / 3) + _ARG
    if isinstance(value, str):
        if value.isascii() and all(ord(c) >= 0x20 for c in value):
            return 2 * len(value) + _ARG  # only '"' and '\\' double
        if value.isascii():
            return 6 * len(value) + _ARG  # control chars become \u00XX
        return 12 * len(value) + _ARG  # astral code points become a \uXXXX surrogate pair
    return len(json.dumps(value)) + _ARG


def estimate_request_bytes(sql: str, rows: Sequence[Sequence[Any]], *, shape: str) -> int:
    """Upper bound of the pipeline body for ``shape`` in {"batch", "execute"}."""
    sql_bytes = 2 * len(sql) + _STEP
    total = _ENVELOPE
    if shape == "batch":
        total += _CTRL_STEPS * _STEP
    elif shape != "execute":
        raise ValueError(shape)
    for params in rows:
        total += sql_bytes + _STEP + sum(_component_bytes(p) for p in params)
    return total

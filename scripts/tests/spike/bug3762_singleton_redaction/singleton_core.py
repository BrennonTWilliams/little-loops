"""Isolated core for the BUG-3762 bounded single-row redaction spike.

Speaks only the ``execute``/``executemany`` surface shared by ``sqlite3.Connection``
(``isolation_level=None``) and the public ``LibsqlConnection``. The sanitizer is faked: callers
pass ``sanitize(payload) -> (payload, match_count)``. Built on the ENH-3752 spike core for the
typed guarded UPDATE, ``apply_unit`` and the wire estimator. See ``.ll/spikes/spike-BUG-3762.md``.
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NoReturn

from scripts.tests.spike.enh3752_raw_redaction.redaction_core import (
    UPDATE_SQL,
    Accounting,
    Col,
    Counters,
    Desired,
    Observed,
    apply_unit,
    context_supported,
    estimate_request_bytes,
    fetch_one,
    update_params,
)

from little_loops.session_store.backend import HistoryUnavailable

STORED_CAP = 1 << 20
DECODED_CAP = 4 << 20
PAGE_ROWS_MAX = 8
REQUEST_BYTES_CAP = 8 << 20
SINGLE_ROW_STORED_CAP = PAGE_ROWS_MAX * STORED_CAP  # 8 MiB: same payload bytes as one full page
SINGLE_ROW_DECODED_CAP = 2 * DECODED_CAP  # 8 MiB
COLUMNS = ("raw_line", "parsed_json")

Sanitize = Callable[[dict[str, Any]], tuple[dict[str, Any], int]]


# -- bounded strict decode -------------------------------------------------


class Refusal(Exception):
    """Content-free per-column refusal; byte-budget refusals carry stage + effective bound."""

    def __init__(
        self,
        reason: str,
        limit_kind: str | None = None,
        limit_bytes: int | None = None,
        stored_bytes: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.limit_kind = limit_kind
        self.limit_bytes = limit_bytes
        self.stored_bytes = stored_bytes


def _refuse(*args: Any, **kw: Any) -> NoReturn:
    raise Refusal(*args, **kw) from None


def _reject_constant(_name: str) -> NoReturn:
    raise ValueError("non-finite JSON constant")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def decode_payload(
    sql_type: str, data: bytes, *, decoded_cap: int = DECODED_CAP, kind: str = "decoded"
) -> dict[str, Any]:
    """Decode one stored payload under an explicit decoded-byte bound (default: ordinary 4 MiB).

    ``kind`` names the budget in a byte-limit refusal (``decoded`` or ``replacement_decoded``).
    The decompressor is asked for at most ``decoded_cap + 1`` bytes, so exhaustion is detected
    without ever materializing more than the bound.
    """
    if sql_type == "text":
        if len(data) > decoded_cap:
            _refuse("resource_limit", kind, decoded_cap)
        raw = data
    else:
        stream = zlib.decompressobj()
        try:
            raw = stream.decompress(data, decoded_cap + 1)
        except zlib.error:
            _refuse("invalid_compression")
        if len(raw) > decoded_cap:
            _refuse("resource_limit", kind, decoded_cap)
        if not stream.eof or stream.unconsumed_tail or stream.unused_data:
            _refuse("invalid_compression")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _refuse("invalid_encoding")
    del raw
    try:
        value = json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except RecursionError:
        _refuse("resource_limit")  # structural limit: no byte budget, never promotes
    except ValueError:
        _refuse("invalid_json")
    if type(value) is not dict:
        _refuse("invalid_json")
    return value


# -- singleton read --------------------------------------------------------


def fetch_singleton(conn: Any, row_id: int) -> Observed | None:
    """One coherent SELECT: both payload columns plus host/event_type, 8 MiB per payload."""
    return fetch_one(conn, row_id, cap=SINGLE_ROW_STORED_CAP)


# -- planning --------------------------------------------------------------


@dataclass(frozen=True)
class Problem:
    column: str | None
    reason: str
    limit_kind: str | None = None
    limit_bytes: int | None = None
    stored_bytes: int | None = None


@dataclass(frozen=True)
class Plan:
    obs: Observed
    raw: bytes | None
    parsed: bytes | None
    counts: dict[str, int]
    params: tuple[Any, ...]
    replacement_bytes: int

    @property
    def changed(self) -> bool:
        return self.raw is not None or self.parsed is not None

    @property
    def desired(self) -> Desired:
        return Desired(raw=self.raw, parsed=self.parsed)


def _pack(text: str, sql_type: str) -> bytes:
    return text.encode("ascii") if sql_type == "text" else zlib.compress(text.encode("utf-8"), 6)


def plan_column(
    col: Col, sanitize: Sanitize, *, stored_cap: int, decoded_cap: int
) -> tuple[bytes | None, int]:
    """Sanitize one column; ``(None, 0)`` when nothing matches."""
    if col.sql_type not in ("text", "blob"):
        _refuse("unsupported_storage")
    if col.value is None:
        _refuse("resource_limit", "stored", stored_cap, col.length)
    try:
        source = decode_payload(col.sql_type, col.value, decoded_cap=decoded_cap)
    except Refusal as exc:
        exc.stored_bytes = col.length
        raise
    result, matches = sanitize(source)
    del source
    if not matches:
        return None, 0
    try:
        text = json.dumps(result, ensure_ascii=True, allow_nan=False)
    except RecursionError:
        _refuse("resource_limit")
    del result
    stored = _pack(text, col.sql_type)
    del text
    if len(stored) > stored_cap:
        _refuse("resource_limit", "replacement_stored", stored_cap, col.length)
    try:
        decode_payload(col.sql_type, stored, decoded_cap=decoded_cap, kind="replacement_decoded")
    except Refusal as exc:
        exc.stored_bytes = col.length
        raise
    return stored, matches


def _estimate(obs: Observed, new_raw: bytes | None, new_parsed: bytes | None) -> int:
    """Request estimate with both complete originals; future replacements are ``None``."""
    params = update_params(obs, new_raw, new_parsed)
    return estimate_request_bytes(UPDATE_SQL, [params], shape="batch")


def plan_row(
    obs: Observed,
    sanitize: Sanitize,
    *,
    stored_cap: int = SINGLE_ROW_STORED_CAP,
    decoded_cap: int = SINGLE_ROW_DECODED_CAP,
    request_cap: int | None = REQUEST_BYTES_CAP,
) -> tuple[Plan | None, tuple[Problem, ...]]:
    """Validate a row and plan replacements; ``request_cap=None`` (local) skips the estimate."""
    if not context_supported(obs):
        return None, (Problem(None, "unsupported_context"),)
    problems: list[Problem] = []
    replacements: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    originals_complete = obs.raw.value is not None and obs.parsed.value is not None
    for name, col in zip(COLUMNS, (obs.raw, obs.parsed), strict=True):
        try:
            new, n = plan_column(col, sanitize, stored_cap=stored_cap, decoded_cap=decoded_cap)
        except Refusal as exc:
            problems.append(
                Problem(name, exc.reason, exc.limit_kind, exc.limit_bytes, exc.stored_bytes)
            )
            continue
        if new is None:
            continue
        if request_cap is not None and originals_complete:
            so_far = {**replacements, name: new}
            if _estimate(obs, so_far.get("raw_line"), so_far.get("parsed_json")) > request_cap:
                del new, so_far  # release the candidate; a wider read cannot make it fit
                return None, (Problem(None, "resource_limit", "request", request_cap),)
        replacements[name] = new
        counts[name] = n
    if problems:
        return None, tuple(problems)  # a failed sibling discards the other column's plan
    new_raw, new_parsed = replacements.get("raw_line"), replacements.get("parsed_json")
    if new_raw is None and new_parsed is None:
        return Plan(obs, None, None, {}, (), 0), ()
    params = update_params(obs, new_raw, new_parsed)
    size = len(new_raw or b"") + len(new_parsed or b"")
    return Plan(obs, new_raw, new_parsed, counts, params, size), ()


# -- expanded reconciliation -----------------------------------------------


def _state(obs: Observed) -> tuple[Any, ...]:
    return tuple((c.sql_type, c.value) for c in (obs.raw, obs.parsed, obs.host, obs.event_type))


def _desired_state(orig: Observed, want: Desired) -> tuple[Any, ...]:
    return (
        (orig.raw.sql_type, want.raw if want.raw is not None else orig.raw.value),
        (orig.parsed.sql_type, want.parsed if want.parsed is not None else orig.parsed.value),
        (orig.host.sql_type, orig.host.value),
        (orig.event_type.sql_type, orig.event_type.value),
    )


def classify(orig: Observed, want: Desired, seen: Observed | None) -> str:
    """A withheld (over-cap) value is ``None`` and equals neither original nor desired bytes."""
    if seen is None:
        return "vanished"
    state = _state(seen)
    if state == _desired_state(orig, want):
        return "desired"
    if state == _state(orig):
        return "original"
    return "changed"


def reconcile_expanded(
    conn: Any, orig: Observed, want: Desired, counters: Counters, *, read_cap: int
) -> str:
    """At most one guarded retry and one re-read, both through the ``read_cap`` projection."""
    try:
        verdict = classify(orig, want, fetch_one(conn, orig.id, cap=read_cap))
        if verdict == "original":
            counters.retries += 1
            ack = conn.execute(UPDATE_SQL, update_params(orig, want.raw, want.parsed)).rowcount
            if ack == 1:
                counters.updates_applied += 1
                return "retried"
            if ack != 0:
                raise RuntimeError("backend_invariant: retry acknowledged an impossible count")
            verdict = classify(orig, want, fetch_one(conn, orig.id, cap=read_cap))
            if verdict == "original":
                verdict = "changed"
    except HistoryUnavailable:
        counters.unconfirmed += 1
        return "unconfirmed"
    if verdict == "desired":
        counters.reconciled += 1
    else:
        counters.conflicts += 1
        if verdict == "vanished":
            counters.vanished += 1
    return verdict


def process_expanded(
    conn: Any,
    obs: Observed,
    want: Desired,
    acct: Accounting,
    counters: Counters,
    *,
    read_cap: int = SINGLE_ROW_STORED_CAP,
    after_apply: Callable[[], None] | None = None,
) -> str | None:
    """Apply one expanded plan immediately; reconcile a short/lost acknowledgement."""
    ack = apply_unit(conn, [obs], {obs.id: want}, acct)
    if after_apply is not None:
        after_apply()  # test seam: a concurrent writer acts between write and reconciliation
    if ack is None:
        counters.counts_complete = False
    elif ack not in (0, 1):
        raise RuntimeError("backend_invariant: impossible acknowledgement")
    elif ack == 1:
        counters.updates_applied += 1
        return None
    return reconcile_expanded(conn, obs, want, counters, read_cap=read_cap)


# -- fake sanitizer --------------------------------------------------------

SECRET = "mail bob@example.com"
CLEAN = "mail [EMAIL]"


def scrub_marker(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Replace ``SECRET`` in every string; returns ``(payload, matches)``."""
    total = 0

    def walk(value: Any) -> Any:
        nonlocal total
        if isinstance(value, str):
            n = value.count(SECRET)
            if n:
                total += n
                return value.replace(SECRET, CLEAN)
            return value
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    out = walk(payload)
    return out, total

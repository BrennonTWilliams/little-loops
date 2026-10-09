"""Bounded retained-input collection for the usage proof (ENH-3744).

The only module that feeds :func:`inspect_usage_candidates` from storage. It reads one
source's retained raw rows, the related-source rows and committed observations selected
by that source's native identities and exact raw links (never a host-wide observation
population), decodes every stored payload into a ``UsageReplayRecord`` or a bounded
``UsageReplayFailure``, and enforces whole-scope item and byte limits **before**
materializing packed expansions. Crossing a limit raises :class:`UsageProofLimit`; no
partial candidate success is ever returned. Prune and read-only consumers share it.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import zlib
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any

from little_loops.session_store.usage_proof import (
    UsageCandidateProof,
    UsageReplayFailure,
    inspect_usage_candidates,
    recognize_claude_usage,
)
from little_loops.session_store.writers import UsageReplayRecord, usage_replay_record_from_row


@dataclass(frozen=True)
class ProofLimits:
    """Private whole-scope bounds for one proof (tests shrink them)."""

    max_items: int = 10_000
    max_encoded_bytes: int = 64 << 20
    max_decoded_bytes: int = 64 << 20


PROOF_LIMITS = ProofLimits()


class UsageProofLimit(Exception):  # noqa: N818 - a bounded signal, not an error condition
    """A proof scope crossed a private limit; the whole affected scope stays retained."""


class UsageProofUnavailable(Exception):  # noqa: N818 - a bounded signal, not an error condition
    """The selected member is unknown, unsafe or lacks the proof tables: nothing is read.

    Never falls back to ``main``: two attached members never join by matching paths, native
    keys or raw IDs, so an unavailable member is reported, not substituted.
    """


def _member(conn: sqlite3.Connection, schema: str) -> str:
    """Validated schema qualifier for *schema* (generated-safe alias attached to *conn*)."""
    from little_loops.session_store.usage_source_state import _safe_schema, _table_exists

    safe = _safe_schema(conn, schema)
    if safe is None or not all(
        _table_exists(conn, safe, table) for table in ("raw_events", "usage_events")
    ):
        raise UsageProofUnavailable
    return safe


@dataclass(frozen=True)
class ProofScope:
    """Everything one source's proof needs, with related-source IDs separated."""

    source: str
    records: tuple[UsageReplayRecord | UsageReplayFailure, ...]
    observations: tuple[dict[str, Any], ...]
    related_raw_event_ids: frozenset[int]
    peer_failures: tuple[UsageReplayFailure, ...] = ()


def _row_select(schema: str) -> str:
    return (
        "SELECT typeof(raw_line), CAST(raw_line AS BLOB), source_path, host, host_basis, "
        f"event_type, ts, session_id, line_no, ordinal, usage_contract, id FROM {schema}.raw_events"
    )


_OBS_COLUMNS = (
    "id",
    "host",
    "session_id",
    "channel",
    "provenance",
    "model",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "observation_key",
    "source_raw_event_id",
    "source_path",
    "source_line_no",
    "source_ordinal",
    "request_id",
    "turn_id",
    "request_identity_basis",
    "usage_contract",
)
_CHUNK = 500


class _Budget:
    def __init__(self, limits: ProofLimits) -> None:
        self.limits = limits
        self.items = 0
        self.encoded = 0
        self.decoded = 0

    def item(self, count: int = 1) -> None:
        self.items += count
        if self.items > self.limits.max_items:
            raise UsageProofLimit

    def encode(self, size: int) -> None:
        self.encoded += size
        if self.encoded > self.limits.max_encoded_bytes:
            raise UsageProofLimit

    def remaining_decoded(self) -> int:
        return self.limits.max_decoded_bytes - self.decoded


def _chunks(values: Collection[Any]) -> Iterable[list[Any]]:
    ordered = sorted(values, key=repr)
    for start in range(0, len(ordered), _CHUNK):
        yield ordered[start : start + _CHUNK]


def _decode_payload(sql_type: str, data: Any, budget: _Budget) -> dict[str, Any] | str:
    """Decode one stored payload within budget; return the payload or a failure reason."""
    if sql_type not in {"blob", "text"} or not isinstance(data, bytes):
        return "invalid_payload"
    budget.encode(len(data))
    if sql_type == "blob":
        stream = zlib.decompressobj()
        try:
            raw = stream.decompress(data, budget.remaining_decoded() + 1)
        except zlib.error:
            return "invalid_compression"
        if len(raw) > budget.remaining_decoded():
            raise UsageProofLimit
        if not stream.eof or stream.unused_data:
            return "invalid_compression"
    else:
        raw = data
        if len(raw) > budget.remaining_decoded():
            raise UsageProofLimit
    budget.decoded += len(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "invalid_encoding"
    try:
        payload = json.loads(text)
    except RecursionError:
        return "recursion"
    except ValueError:
        return "invalid_json"
    return payload if isinstance(payload, dict) else "non_object_payload"


def _record(row: tuple[Any, ...], budget: _Budget) -> UsageReplayRecord | UsageReplayFailure:
    payload = _decode_payload(row[0], row[1], budget)
    if isinstance(payload, str):
        return UsageReplayFailure(
            source_label=str(row[2]),
            reason=payload,
            raw_event_id=row[11],
            line_no=row[8],
            ordinal=row[9],
            host=row[3],
            event_type=row[5],
        )
    return usage_replay_record_from_row(payload, (None, *row[2:]))


def _overlay_clause(deleted: Collection[str], cutoff: str | None) -> tuple[str, list[Any]]:
    """SQL excluding rows an earlier (virtual) source deletion removed."""
    if not deleted or cutoff is None:
        return "", []
    marks = ", ".join("?" for _ in deleted)
    return (
        f" AND NOT (source_path IN ({marks}) AND ts < ? AND compacted = 1)",
        [*sorted(deleted), cutoff],
    )


def _peer_keys(record: UsageReplayRecord | UsageReplayFailure) -> tuple[str | None, str | None]:
    """(Claude observation key, Codex response ID) a related-source row must match."""
    if isinstance(record, UsageReplayFailure):
        return None, None
    if record.event_type == "token_usage_record":
        response = record.payload.get("response_id")
        return None, response if isinstance(response, str) and response else None
    recognized = recognize_claude_usage(
        record.payload,
        host=record.host,
        host_basis=record.host_basis,
        usage_contract=record.usage_contract,
    )
    return (recognized.observation_key if recognized is not None else None), None


def collect_usage_proof_scope(
    conn: sqlite3.Connection,
    source: str,
    *,
    deleted_sources: Collection[str] = (),
    cutoff: str | None = None,
    limits: ProofLimits | None = None,
    schema: str = "main",
) -> ProofScope:
    """Collect one source's whole proof scope, bounded by *limits* (default ``PROOF_LIMITS``).

    *schema* selects one member (``main`` or a generated-safe attached alias); every raw,
    observation, related-source and exact-link query is qualified with it. An unknown,
    unsafe or table-less member raises :class:`UsageProofUnavailable`.

    *deleted_sources*/*cutoff* describe earlier planned deletions a dry run has not
    performed: their aged compacted rows are excluded so a later source sees the same
    evidence a real run would. Raises :class:`UsageProofLimit` on any crossed limit.
    """
    member = _member(conn, schema)
    row_select = _row_select(member)
    budget = _Budget(limits or PROOF_LIMITS)
    overlay_sql, overlay_params = _overlay_clause(deleted_sources, cutoff)

    count, encoded = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(CAST(raw_line AS BLOB))), 0) "
        f"FROM {member}.raw_events WHERE source_path = ?",
        (source,),
    ).fetchone()
    budget.item(count)
    if count > budget.limits.max_items or encoded > budget.limits.max_encoded_bytes:
        raise UsageProofLimit

    records: list[UsageReplayRecord | UsageReplayFailure] = []
    for row in conn.execute(
        f"{row_select} WHERE source_path = ? ORDER BY COALESCE(ordinal, line_no), line_no, id",
        (source,),
    ):
        records.append(_record(tuple(row), budget))

    own_ids = {r.raw_event_id for r in records if r.raw_event_id is not None}
    claude_keys: set[str] = set()
    response_ids: set[str] = set()
    sessions: set[str] = set()
    for record in records:
        key, response = _peer_keys(record)
        if key is not None:
            claude_keys.add(key)
        if response is not None:
            response_ids.add(response)
        if isinstance(record, UsageReplayRecord) and (key or response):
            if isinstance(record.session_id, str):
                sessions.add(record.session_id)
            payload_session = record.payload.get("sessionId") or record.payload.get("thread_id")
            if isinstance(payload_session, str):
                sessions.add(payload_session)

    observations = _load_observations(
        conn, source, own_ids, claude_keys, response_ids, budget, member
    )

    related: dict[int, UsageReplayRecord] = {}
    peer_failures: dict[int, UsageReplayFailure] = {}

    def examine(row: tuple[Any, ...], *, context: bool = False) -> None:
        """Decode one peer or peer-context row; every examined row consumes the budget."""
        raw_id = row[11]
        if raw_id in own_ids or raw_id in related or raw_id in peer_failures:
            return
        budget.item()
        candidate = _record(row, budget)
        if isinstance(candidate, UsageReplayFailure):
            # An unreadable peer cannot be ruled out as a conflicting copy: keep it as evidence.
            peer_failures[raw_id] = candidate
            return
        if context:
            related[raw_id] = candidate
            return
        key, response = _peer_keys(candidate)
        if (key is not None and key in claude_keys) or (
            response is not None and response in response_ids
        ):
            related[raw_id] = candidate

    for chunk in _chunks(sessions):
        marks = ", ".join("?" for _ in chunk)
        for row in conn.execute(
            f"{row_select} WHERE source_path != ? AND session_id IN ({marks}) "
            f"AND event_type IN ('assistant', 'token_usage_record'){overlay_sql} "
            "ORDER BY source_path, COALESCE(ordinal, line_no), line_no, id",
            (source, *chunk, *overlay_params),
        ):
            examine(tuple(row))
    links = {
        o["source_raw_event_id"]
        for o in observations
        if isinstance(o.get("source_raw_event_id"), int)
        and o["source_raw_event_id"] not in own_ids
        and o["source_raw_event_id"] not in related
    }
    for chunk in _chunks(links):
        marks = ", ".join("?" for _ in chunk)
        for row in conn.execute(
            f"{row_select} WHERE id IN ({marks}){overlay_sql}", (*chunk, *overlay_params)
        ):
            examine(tuple(row))
    # A Codex peer's identity, model and closure live in its header/turn/event rows, not in
    # the value record: load them (bounded by the same budget) so a copy is compared with
    # the context it actually consumed. Claude peers are self-contained.
    peer_sources = sorted(
        {r.source_label for r in related.values() if r.event_type == "token_usage_record"}
    )
    for chunk in _chunks(peer_sources):
        marks = ", ".join("?" for _ in chunk)
        for row in conn.execute(
            f"{row_select} WHERE source_path IN ({marks}) "
            f"AND event_type IN ('session_meta', 'turn_context', 'event_msg'){overlay_sql}",
            (*chunk, *overlay_params),
        ):
            examine(tuple(row), context=True)

    peers = sorted(
        related.values(),
        key=lambda r: (
            r.source_label,
            r.ordinal if r.ordinal is not None else (r.line_no or 0),
            r.line_no or 0,
            r.raw_event_id or 0,
        ),
    )
    ordered = [*records, *peers, *peer_failures.values()]
    return ProofScope(
        source=source,
        records=tuple(ordered),
        observations=tuple(observations),
        related_raw_event_ids=frozenset(related),
        peer_failures=tuple(peer_failures.values()),
    )


def _load_observations(
    conn: sqlite3.Connection,
    source: str,
    raw_ids: set[int],
    keys: set[str],
    response_ids: set[str],
    budget: _Budget,
    member: str = "main",
) -> list[dict[str, Any]]:
    """Committed observations selected by exact raw links and native identities only."""
    found: dict[int, dict[str, Any]] = {}
    columns = ", ".join(_OBS_COLUMNS)
    selectors: tuple[tuple[str, Collection[Any]], ...] = (
        ("source_raw_event_id", raw_ids),
        ("observation_key", keys),
        ("request_id", response_ids),
    )
    for column, values in selectors:
        for chunk in _chunks(values):
            marks = ", ".join("?" for _ in chunk)
            for row in conn.execute(
                f"SELECT {columns} FROM {member}.usage_events WHERE channel IS NOT 'live' "
                f"AND {column} IN ({marks})",
                tuple(chunk),
            ):
                if row[0] not in found:
                    budget.item()
                    found[row[0]] = dict(zip(_OBS_COLUMNS, row, strict=True))
    return list(found.values())


def inspect_retained_source(
    conn: sqlite3.Connection,
    source: str,
    *,
    deleted_sources: Collection[str] = (),
    cutoff: str | None = None,
    limits: ProofLimits | None = None,
    channel: str | None = None,
    schema: str = "main",
) -> tuple[UsageCandidateProof, ...]:
    """Prove every usage candidate retained in *source*; raises :class:`UsageProofLimit`.

    Read-only: nothing is written, so it is safe on a dry-run snapshot and for
    read-only consumers. Proofs of related-source rows used only as context are not
    returned.
    """
    scope = collect_usage_proof_scope(
        conn, source, deleted_sources=deleted_sources, cutoff=cutoff, limits=limits, schema=schema
    )
    return inspect_scope(scope, channel=channel)


def inspect_scope(
    scope: ProofScope, *, channel: str | None = None
) -> tuple[UsageCandidateProof, ...]:
    """Prove *scope*'s own candidates; an unreadable peer makes keyed candidates unprovable.

    Related rows are context only and are never returned. A peer row that failed to decode
    could be a conflicting copy of any keyed candidate, so those candidates cannot be
    proved represented (or missing) while it stays unreadable (ENH-3770).
    """
    proofs = [
        p
        for p in inspect_usage_candidates(scope.records, scope.observations, channel=channel)
        if p.source_label == scope.source
    ]
    if not scope.peer_failures:
        return tuple(proofs)
    return tuple(
        dataclasses.replace(p, correspondence="unprovable", reason="peer_context_unreadable")
        if p.native_key is not None and p.correspondence in {"represented", "missing"}
        else p
        for p in proofs
    )

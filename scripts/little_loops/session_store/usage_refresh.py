"""Conservative re-ingestion of session sources after a parser upgrade.

``raw_events`` stores normalized, history-policy-redacted payloads. A parser that
used to discard a field cannot recover it by replaying those rows; the original
source must be parsed again. Source and stored payloads are compared in their
canonical (sanitized) form, so legacy plaintext rows and redacted rows certify as
semantically compatible without this module scrubbing anything. This module refreshes only sources with verified handle-based
attribution. It deliberately leaves derived tables alone: callers must run
``rebuild`` after a successful refresh.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn, cast

from little_loops.pii import HistorySanitizationError, sanitize_history_payload
from little_loops.session_store.backend import refuse_on_remote
from little_loops.session_store.db import DEFAULT_DB_PATH
from little_loops.session_store.sessions import SessionEvent, SessionHandle, iter_events
from little_loops.session_store.usage_source_state import (
    AcquisitionBoundary,
    AcquisitionWitness,
    OriginalAcquisition,
    SourcePending,
    SourceScope,
    invalidate_usage_dependencies,
    pending_obligations,
    read_source_head,
    record_source_acquisition,
    record_source_pending,
    storage_available,
)
from little_loops.session_store.usage_source_tracking import (
    USAGE_ACQUISITION_VERSION,
    PhysicalAccounting,
    account_physical_lines,
    begin_attempt,
    record_failure_only,
    record_rejections,
)
from little_loops.session_store.writers import (
    _pack_payload,
    _unpack_payload,
    load_usage_replay_holds,
    usage_channel_for_host,
)


@dataclass(frozen=True)
class SourceRefresh:
    """Outcome for one original source path."""

    path: Path
    status: str  # refreshed, unchanged, or skipped
    reason: str | None = None
    rows: int = 0


@dataclass(frozen=True)
class RefreshResult:
    """Refresh outcomes for this call.

    ``needs_rebuild`` reflects the *committed* refresh obligations of the requested sources
    (ENH-3770), so an unchanged retry still reports work an earlier call left unresolved
    and a crash between the raw refresh and the derive cannot lose it. When the obligation
    storage is unavailable it falls back to "this call replaced rows".
    """

    sources: tuple[SourceRefresh, ...]
    _outstanding: bool | None = field(default=None, repr=False, compare=False)

    @property
    def needs_rebuild(self) -> bool:
        """Whether committed refresh work (cache or usage component) remains."""
        if self._outstanding is not None:
            return self._outstanding
        return any(source.status == "refreshed" for source in self.sources)


def _source_keys(path: Path) -> tuple[str, ...]:
    """Every stored spelling of *path* (its handle spelling and its resolved spelling)."""
    return tuple(dict.fromkeys((str(path), str(path.expanduser().resolve()))))


def outstanding_refresh_work(db: Path | str, paths: Iterable[Path | str]) -> bool | None:
    """Whether any requested source still owes parser-refresh cache or usage work.

    Authoritatively re-reads the committed shared pending state for every path and its
    lookup alias, including sources whose refresh was skipped or unchanged. ``None`` when
    the obligation storage is unavailable (callers then fall back to their own result).
    """
    import little_loops.session_store as store

    conn = store.connect(db)
    try:
        if not storage_available(conn):
            return None
        for path in paths:
            for key in _source_keys(Path(path)):
                for ob in pending_obligations(conn, key):
                    if ob.kind == "refresh" and (ob.raw_cache_pending or ob.usage_pending):
                        return True
        return False
    finally:
        conn.close()


def _source_version(path: Path) -> tuple[int, int] | None:
    """Return a cheap file-change witness, or None for a missing source."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns) if path.is_file() else None


_STORED_SELECT = (
    "SELECT line_no, ts, session_id, host, host_basis, ordinal, event_type, "
    "CAST(raw_line AS BLOB), CAST(parsed_json AS BLOB), usage_contract, compacted, "
    "summary_node_id, typeof(raw_line), typeof(parsed_json) "
    "FROM raw_events WHERE source_path = ? ORDER BY line_no"
)


def _refuse(reason: str) -> NoReturn:
    raise HistorySanitizationError(reason) from None


def _reject_constant(_name: str) -> NoReturn:
    _refuse("invalid_payload")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _refuse("invalid_payload")
        out[key] = value
    return out


def _decode_stored_payload(value: object, *, storage_type: str) -> dict[str, Any]:
    """Decode one stored payload column for comparison, refusing with a safe reason.

    *value* is the ``CAST(column AS BLOB)`` projection and *storage_type* the column's
    ``typeof``: TEXT is strict UTF-8 without decompression, BLOB is the existing zlib
    codec. Expected decode failures become content-free ``invalid_payload`` (or
    ``resource_limit`` for recursion overflow) with the original context suppressed.
    """
    if storage_type not in ("text", "blob") or not isinstance(value, bytes):
        _refuse("invalid_payload")
    try:
        text = value.decode("utf-8") if storage_type == "text" else _unpack_payload(value)
        decoded = json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant
        )
    except (zlib.error, UnicodeDecodeError, json.JSONDecodeError):
        _refuse("invalid_payload")
    except RecursionError:
        _refuse("resource_limit")
    if type(decoded) is not dict:
        _refuse("invalid_payload")
    return decoded


def _canonical_payload(
    payload: dict[str, Any], *, host: str | None, event_type: str | None
) -> dict[str, Any]:
    """The history-policy form of *payload* under the verified ``host``/``event_type``."""
    return sanitize_history_payload(payload, host=host, event_type=event_type).payload


def _payload_equal(left: object, right: object) -> bool:
    """Exact JSON equality: identical scalar types, so ``True``/``1``/``1.0`` differ."""
    stack: list[tuple[Any, Any]] = [(left, right)]
    while stack:
        a, b = stack.pop()
        if type(a) is not type(b):
            return False
        if type(a) is dict:
            if a.keys() != b.keys():
                return False
            stack.extend((value, b[key]) for key, value in a.items())
        elif type(a) is list:
            if len(a) != len(b):
                return False
            stack.extend(zip(a, b, strict=True))
        elif a != b:
            return False
    return True


def _preserves_fields(stored: object, parsed: object) -> bool:
    """Require a parser upgrade to retain every field already stored (type-sensitive)."""
    stack: list[tuple[Any, Any]] = [(stored, parsed)]
    while stack:
        before, after = stack.pop()
        if type(before) is not type(after):
            return False
        if type(before) is dict:
            for key, value in before.items():
                if key not in after:
                    return False
                stack.append((value, after[key]))
        elif type(before) is list:
            if len(before) != len(after):
                return False
            stack.extend(zip(before, after, strict=True))
        elif before != after:
            return False
    return True


def _stored_payloads(
    raw_line: object, raw_type: object, parsed_json: object, parsed_type: object
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decode both payload columns from their ``CAST(... AS BLOB)``/``typeof`` projections."""
    return (
        _decode_stored_payload(raw_line, storage_type=str(raw_type)),
        _decode_stored_payload(parsed_json, storage_type=str(parsed_type)),
    )


def _expected_contract(event: SessionEvent, handle: SessionHandle) -> str | None:
    from little_loops.session_store.claude_usage import claude_transcript_contract

    return claude_transcript_contract(event.payload, host=handle.host, host_basis="handle")


def _event_metadata(event: SessionEvent, handle: SessionHandle) -> tuple[object, ...]:
    """Relational identity of *event*: ts, session, ordinal, type (host/basis checked apart)."""
    return (
        event.timestamp,
        event.payload.get("sessionId") or handle.session_id,
        event.ordinal,
        event.type or "unknown",
    )


def _inserted_matches(
    row: tuple[object, ...],
    event: SessionEvent,
    handle: SessionHandle,
    expected_payload: dict[str, Any],
) -> bool:
    """Whether an inserted row has the source's identity, contract and sanitized payloads."""
    timestamp, session_id, ordinal, event_type = _event_metadata(event, handle)
    return (
        tuple(row[:7])
        == (event.line_no, timestamp, session_id, handle.host, "handle", ordinal, event_type)
        and row[9] == _expected_contract(event, handle)
        and all(
            _payload_equal(column, expected_payload)
            for column in _stored_payloads(row[7], row[12], row[8], row[13])
        )
    )


_REFUSAL_CODES = frozenset(
    {"invalid_payload", "key_collision", "unsafe_identity", "resource_limit"}
)


def _derive_version() -> str:
    from little_loops.session_store.lifecycle import _USAGE_DERIVE_VERSION

    return _USAGE_DERIVE_VERSION


def _record_preflight_decode_failure(db: Path | str, handle: SessionHandle, path: Path) -> None:
    """Persist a content-free decode failure raised before the source transaction opens."""
    import little_loops.session_store as store

    try:
        accounting = account_physical_lines(path)
    except OSError:
        accounting = PhysicalAccounting(0, 0)
    first = min(accounting.rejected, key=lambda r: r.first_offset, default=None)
    conn = store.connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        attempt = begin_attempt(conn, str(path), _derive_version(), host=handle.host)
        conn.rollback()
    finally:
        conn.close()
    record_failure_only(
        lambda: store.connect(db),
        attempt,
        reason=first.reason if first is not None else "decode_failure",
        first_line_no=first.first_line_no if first is not None else None,
        first_offset=first.first_offset if first is not None else None,
    )


def _record_rejections(conn: sqlite3.Connection, attempt: Any, path: Path) -> bool:
    """Record physically rejected lines of *path* as durable failure evidence (True if written)."""
    if attempt is None:
        return False
    try:
        accounting = account_physical_lines(path)
    except OSError:
        return False
    return record_rejections(conn, attempt, accounting)


def _invalidate_tracked_completion(
    conn: sqlite3.Connection, source_keys: tuple[str, ...], raw_source: str
) -> None:
    """Invalidate tracked completion consuming the observations a replacement will delete."""
    if not storage_available(conn):
        return
    placeholders = ", ".join("?" for _ in source_keys)
    ids = tuple(
        row[0]
        for row in conn.execute(
            "SELECT id FROM usage_events WHERE channel IS NOT 'live' AND ("
            f"source_path IN ({placeholders}) OR source_raw_event_id IN "
            "(SELECT id FROM raw_events WHERE source_path = ?))",
            (*source_keys, raw_source),
        )
    )
    scopes = tuple(
        head.scope for head in (read_source_head(conn, key) for key in source_keys) if head
    )
    # The observations stay (their raw rows are updated in place), so their supplier and
    # frontier witnesses are preserved; only completion that consumed them is invalidated.
    invalidate_usage_dependencies(
        conn, ids, scopes, reason="parser_refresh", preserve_witness_ids=ids
    )


def _acquisition_witness(path: Path, offset: int) -> AcquisitionWitness | None:
    """Cheap change-detection witness of *path* at *offset* (never prefix continuity)."""
    import hashlib

    try:
        stat = path.stat()
        with path.open("rb") as handle:
            handle.seek(max(0, offset - 64))
            digest = hashlib.sha256(handle.read(min(offset, 64))).hexdigest()
    except OSError:
        return None
    return AcquisitionWitness(stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, digest)


def _record_replacement_acquisition(conn: sqlite3.Connection, attempt: Any, path: Path) -> None:
    """Commit the verified original-source acquisition and both refresh obligations.

    Runs in the refresh transaction after raw rows were updated in place and appended. When
    the full physical range was acquired without rejection it creates the acquisition head
    -- even for a previously untracked raw-only or legacy source -- or advances it to cover
    verified appends, and records the content-free ``OriginalAcquisition`` authority with
    the ``raw_cache`` and ``usage`` components under the same generation and chained head
    revisions. This proves acquisition only: never usage completion or historical lineage,
    and ordinary replay cannot use it. Rejections are recorded as failure evidence instead
    and withhold the authority.
    """
    if attempt is None or not storage_available(conn):
        return
    try:
        accounting = account_physical_lines(path)
    except OSError:
        return
    if not accounting.clean:
        record_rejections(conn, attempt, accounting)
        return
    witness = _acquisition_witness(path, accounting.offset)
    if witness is None:
        return
    head = read_source_head(conn, str(path))
    scope = SourceScope(
        str(path),
        head.scope.generation_id if head is not None else attempt.scope.generation_id,
        attempt.scope.derive_version,
        attempt.scope.host,
        attempt.scope.session_id,
    )
    revision = record_source_acquisition(
        conn,
        scope,
        AcquisitionBoundary(USAGE_ACQUISITION_VERSION, accounting.offset, accounting.line_count),
        witness,
        expected_head_revision=head.revision if head is not None else None,
    )
    record_source_pending(
        conn,
        SourcePending(
            scope=scope,
            kind="refresh",
            reason="parser_refresh",
            range_kind="whole_source",
            raw_cache_pending=True,
            usage_pending=True,
            original_acquisition=OriginalAcquisition(
                scope, USAGE_ACQUISITION_VERSION, accounting.offset, accounting.line_count, revision
            ),
        ),
        expected_head_revision=revision,
    )


def refresh_raw_events(
    db: Path | str = DEFAULT_DB_PATH, *, handles: list[SessionHandle]
) -> RefreshResult:
    """Replace verified stored source rows from explicit original session handles.

    Each source is one transaction. Missing, empty, changed, legacy-attributed,
    compacted, usage-replay-held, or host-mismatched sources retain every existing row and receive
    a diagnostic. A failed insert rolls back the whole source. Repeated refresh
    with unchanged parser output does no write. This operation does not
    re-derive cache tables; call ``rebuild(db)`` when the result says
    ``needs_rebuild``. The source cursor and linked non-live usage rows are
    invalidated in the same transaction, and the derive checkpoint is cleared
    so the next incremental derive must replay all raw usage. A failed rebuild
    must be retried explicitly; a later unchanged refresh cannot detect that
    failure. It refuses remote stores because their raw source replacement
    contract is not yet defined.
    """
    import little_loops.session_store as store
    from little_loops.session_store.lifecycle import _backfill_raw_events

    refuse_on_remote(db, "refresh_raw_events")
    paths = [str(handle.path) for handle in handles]
    if len(set(paths)) != len(paths):
        raise ValueError("refresh_raw_events: duplicate source path")

    outcomes: list[SourceRefresh] = []
    for handle in handles:
        path = handle.path
        version = _source_version(path)
        if version is None:
            outcomes.append(SourceRefresh(path, "skipped", "original_missing"))
            continue
        try:
            events = list(iter_events(handle))
        except UnicodeDecodeError:
            _record_preflight_decode_failure(db, handle, path)
            raise
        if _source_version(path) != version:
            outcomes.append(SourceRefresh(path, "skipped", "source_changed"))
            continue
        if not events:
            outcomes.append(SourceRefresh(path, "skipped", "no_parsed_events"))
            continue
        positions = [event.line_no for event in events]
        if any(type(position) is not int or position < 1 for position in positions):
            outcomes.append(SourceRefresh(path, "skipped", "invalid_position"))
            continue
        if len(set(positions)) != len(positions) or any(
            event.host != handle.host for event in events
        ):
            outcomes.append(SourceRefresh(path, "skipped", "parser_mismatch"))
            continue

        conn = store.connect(db)
        attempt = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            attempt = begin_attempt(conn, str(path), _derive_version(), host=handle.host)
            rows = conn.execute(_STORED_SELECT, (str(path),)).fetchall()
            reason: str | None = None
            # BUG-3736: refreshing a held source would invalidate retained usage that
            # no surviving raw row can reproduce. Reject before touching anything.
            if load_usage_replay_holds(conn).holds(
                str(path), handle.host, usage_channel_for_host(handle.host)
            ):
                reason = "usage_replay_held"
            elif not rows:
                reason = "not_previously_ingested"
            elif any(row[4] != "handle" or row[3] != handle.host for row in rows):
                reason = "unverified_host_attribution"
            elif any(row[10] or row[11] is not None for row in rows):
                reason = "compacted_source"
            elif len(events) < len(rows):
                reason = "fewer_parsed_events"
            elif {row[2] for row in rows} != {
                event.payload.get("sessionId") or handle.session_id for event in events
            }:
                reason = "session_attribution_changed"
            elif _source_version(path) != version:
                reason = "source_changed"
            by_line = {event.line_no: event for event in events}
            promote = False
            if reason is None:
                # Per-line relational identity must survive before any payload is decoded.
                for row in rows:
                    event = by_line.get(cast(int, row[0]))
                    if event is None:
                        reason = "existing_payload_not_preserved"
                    elif tuple(row[i] for i in (1, 2, 5, 6)) != _event_metadata(event, handle):
                        reason = "source_metadata_changed"
                    if reason is not None:
                        break
            if reason is None:
                # Qualification is monotonic: NULL may be promoted from the original
                # source (by replacement); a persisted marker is never removed or changed.
                for row in rows:
                    expected_contract = _expected_contract(by_line[cast(int, row[0])], handle)
                    if row[9] == expected_contract:
                        continue
                    if row[9] is None:
                        promote = True
                    else:
                        reason = "usage_contract_changed"
                        break
            if reason is not None:
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", reason))
                continue

            # Canonical comparison: both stored columns and the source are sanitized under
            # the same verified context, so legacy plaintext and redacted rows agree.
            canonical_source = {
                line: _canonical_payload(
                    event.payload, host=handle.host, event_type=event.type or "unknown"
                )
                for line, event in by_line.items()
            }
            stored_canonical: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for row in rows:
                stored_canonical.append(
                    tuple(  # type: ignore[arg-type]
                        _canonical_payload(payload, host=str(row[3]), event_type=str(row[6]))
                        for payload in _stored_payloads(row[7], row[12], row[8], row[13])
                    )
                )
            if any(
                not _preserves_fields(column, canonical_source[cast(int, row[0])])
                for row, columns in zip(rows, stored_canonical, strict=True)
                for column in columns
            ):
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", "existing_payload_not_preserved"))
                continue
            if (
                not promote
                and len(events) == len(rows)
                and all(
                    _payload_equal(column, canonical_source[cast(int, row[0])])
                    for row, columns in zip(rows, stored_canonical, strict=True)
                    for column in columns
                )
            ):
                # Yielded events matching stored rows says nothing about physical lines the
                # parser skipped: account them, and keep content-free negative evidence.
                if _record_rejections(conn, attempt, path):
                    conn.commit()
                else:
                    conn.rollback()
                outcomes.append(SourceRefresh(path, "unchanged", rows=len(rows)))
                continue

            # ENH-3770: raw IDs are stable. Verified existing lines are updated in place
            # (parser payload additions, NULL -> marker contract recovery) and genuinely new
            # native lines are appended, so observation links, value-supplying provenance
            # and committed costs survive. Nothing is deleted or reallocated: the legacy
            # cursor, the observations, their search evidence and the global derive
            # checkpoint stay, and appended rows sit above the checkpoint for the next derive.
            source_keys = _source_keys(path)
            # ENH-3745: tracked completion that consumed these observations (this source or
            # a copy depending on its supplier) becomes pending in this same transaction;
            # the refreshed scope owes cache and usage work, reverse dependents usage only.
            _invalidate_tracked_completion(conn, source_keys, str(path))
            for row, columns in zip(rows, stored_canonical, strict=True):
                line = cast(int, row[0])
                event = by_line[line]
                expected_contract = _expected_contract(event, handle)
                if row[9] == expected_contract and all(
                    _payload_equal(column, canonical_source[line]) for column in columns
                ):
                    continue
                packed = _pack_payload(json.dumps(canonical_source[line]))
                conn.execute(
                    "UPDATE raw_events SET raw_line = ?, parsed_json = ?, usage_contract = ? "
                    "WHERE source_path = ? AND line_no = ?",
                    (packed, packed, expected_contract, str(path), line),
                )
            appended = _backfill_raw_events(conn, [handle])
            inserted = len(rows) + appended
            if inserted != len(events) or _source_version(path) != version:
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", "source_changed_during_refresh"))
                continue
            replaced = conn.execute(_STORED_SELECT, (str(path),)).fetchall()
            # Literal check: decode what was inserted and compare it, unsanitized, to the
            # expected sanitized source so a missed insertion seam cannot be masked.
            if len(replaced) != len(events) or not all(
                _inserted_matches(row, event, handle, canonical_source[event.line_no])
                for row, event in zip(
                    replaced, sorted(events, key=lambda e: cast(int, e.line_no)), strict=True
                )
            ):
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", "parser_changed_during_refresh"))
                continue
            _record_replacement_acquisition(conn, attempt, path)
            conn.commit()
            outcomes.append(SourceRefresh(path, "refreshed", rows=inserted))
        except HistorySanitizationError as exc:
            # Content-free reason; keeps earlier sources' commits and results. The whole-call
            # rollback stands; a separate guarded transaction records the bounded refusal.
            conn.rollback()
            record_failure_only(
                lambda: store.connect(db),
                attempt,
                reason="sanitization_refused",
                refusal_code=exc.reason if exc.reason in _REFUSAL_CODES else "invalid_payload",
            )
            outcomes.append(SourceRefresh(path, "skipped", exc.reason, rows=0))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    outstanding = outstanding_refresh_work(db, [handle.path for handle in handles])
    return RefreshResult(tuple(outcomes), _outstanding=outstanding)

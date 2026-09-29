"""Conservative re-ingestion of session sources after a parser upgrade.

``raw_events`` stores normalized payloads. A parser that used to discard a
field cannot recover it by replaying those rows; the original source must be
parsed again. This module refreshes only sources with verified handle-based
attribution. It deliberately leaves derived tables alone: callers must run
``rebuild`` after a successful refresh.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from little_loops.session_store.backend import refuse_on_remote
from little_loops.session_store.db import DEFAULT_DB_PATH
from little_loops.session_store.sessions import SessionEvent, SessionHandle, iter_events
from little_loops.session_store.writers import _unpack_payload


@dataclass(frozen=True)
class SourceRefresh:
    """Outcome for one original source path."""

    path: Path
    status: str  # refreshed, unchanged, or skipped
    reason: str | None = None
    rows: int = 0


@dataclass(frozen=True)
class RefreshResult:
    """Refresh outcomes for this call; no durable rebuild-pending state is stored."""

    sources: tuple[SourceRefresh, ...]

    @property
    def needs_rebuild(self) -> bool:
        """Whether this call changed raw rows and needs derived-row rebuild."""
        return any(source.status == "refreshed" for source in self.sources)


def _source_version(path: Path) -> tuple[int, int] | None:
    """Return a cheap file-change witness, or None for a missing source."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns) if path.is_file() else None


def _event_signature(event: SessionEvent, handle: SessionHandle) -> tuple[object, ...]:
    from little_loops.session_store.claude_usage import claude_transcript_contract

    return (
        event.line_no,
        event.timestamp,
        event.payload.get("sessionId") or handle.session_id,
        handle.host,
        "handle",
        event.ordinal,
        event.type or "unknown",
        event.payload,
        claude_transcript_contract(event.payload, host=handle.host, host_basis="handle"),
    )


def _stored_signatures(rows: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
    return [
        (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            json.loads(_unpack_payload(cast(str | bytes, row[7]))),
            row[9],
        )
        for row in rows
    ]


def _preserves_fields(stored: object, parsed: object) -> bool:
    """Require a parser upgrade to retain every field already stored."""
    if isinstance(stored, dict) and isinstance(parsed, dict):
        return all(
            key in parsed and _preserves_fields(value, parsed[key]) for key, value in stored.items()
        )
    if isinstance(stored, list) and isinstance(parsed, list):
        return len(stored) == len(parsed) and all(
            _preserves_fields(before, after) for before, after in zip(stored, parsed, strict=True)
        )
    return stored == parsed


def refresh_raw_events(
    db: Path | str = DEFAULT_DB_PATH, *, handles: list[SessionHandle]
) -> RefreshResult:
    """Replace verified stored source rows from explicit original session handles.

    Each source is one transaction. Missing, empty, changed, legacy-attributed,
    compacted, or host-mismatched sources retain every existing row and receive
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
        events = list(iter_events(handle))
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
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT line_no, ts, session_id, host, host_basis, ordinal, event_type, "
                "raw_line, parsed_json, usage_contract, compacted, summary_node_id "
                "FROM raw_events WHERE source_path = ? ORDER BY line_no",
                (str(path),),
            ).fetchall()
            reason: str | None = None
            if not rows:
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
            if reason is not None:
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", reason))
                continue

            expected = sorted(
                (_event_signature(event, handle) for event in events),
                key=lambda signature: cast(int, signature[0]),
            )
            stored = _stored_signatures(rows)
            parsed_by_line = {signature[0]: signature[7] for signature in expected}
            if any(
                row[0] not in parsed_by_line
                or not _preserves_fields(signature[7], parsed_by_line[row[0]])
                for row, signature in zip(rows, stored, strict=True)
            ):
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", "existing_payload_not_preserved"))
                continue
            if stored == expected and all(
                _unpack_payload(cast(str | bytes, row[8]))
                == _unpack_payload(cast(str | bytes, row[7]))
                for row in rows
            ):
                conn.rollback()
                outcomes.append(SourceRefresh(path, "unchanged", rows=len(rows)))
                continue

            # v58 source-tail proof and derived observations refer to the old
            # raw IDs. Invalidate them before replacement, in this transaction.
            # A cursor for the resolved path can coexist with older raw rows
            # stored under the handle's spelling.
            source_keys = tuple(dict.fromkeys((str(path), str(path.expanduser().resolve()))))
            placeholders = ", ".join("?" for _ in source_keys)
            conn.execute(
                f"DELETE FROM usage_source_cursors WHERE source_path IN ({placeholders})",
                source_keys,
            )
            conn.execute(
                "DELETE FROM usage_events WHERE channel IS NOT 'live' AND ("
                f"source_path IN ({placeholders}) OR source_raw_event_id IN "
                "(SELECT id FROM raw_events WHERE source_path = ?))",
                (*source_keys, str(path)),
            )
            conn.execute(
                f"DELETE FROM search_index WHERE kind = 'usage' AND anchor IN ({placeholders})",
                source_keys,
            )
            conn.execute(
                "DELETE FROM meta WHERE key IN ('usage_derive_version', 'usage_derive_raw_id')"
            )
            conn.execute("DELETE FROM raw_events WHERE source_path = ?", (str(path),))
            inserted = _backfill_raw_events(conn, [handle])
            if inserted != len(events) or _source_version(path) != version:
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", "source_changed_during_refresh"))
                continue
            replaced = conn.execute(
                "SELECT line_no, ts, session_id, host, host_basis, ordinal, event_type, "
                "raw_line, parsed_json, usage_contract, compacted, summary_node_id "
                "FROM raw_events WHERE source_path = ? ORDER BY line_no",
                (str(path),),
            ).fetchall()
            if _stored_signatures(replaced) != expected:
                conn.rollback()
                outcomes.append(SourceRefresh(path, "skipped", "parser_changed_during_refresh"))
                continue
            conn.commit()
            outcomes.append(SourceRefresh(path, "refreshed", rows=inserted))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return RefreshResult(tuple(outcomes))

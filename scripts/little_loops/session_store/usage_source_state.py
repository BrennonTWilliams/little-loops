"""Source-local derive completion, pending obligations and dependency witnesses (ENH-3745).

Internal storage seam over five append-only tables (schema v62). It separates three facts
that the legacy ``usage_source_cursors`` row conflates: how far a source was *ingested*,
how far it was *successfully derived* (a semantic boundary), and which obligations remain
(pending/failure). Writers operate only inside the caller's write transaction and never
commit or roll back; every head/obligation mutation is compare-and-swap on a persistent
revision, so a stale caller performs no write and raises :class:`UsageSourceConflict`.
Readers are pure ``SELECT``s over the supplied connection (optionally an attached member).
Nothing here parses sources, prices usage or invents continuity: positions are internal,
reasons are finite codes, and no rejected input bytes are ever stored.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

SOURCE_STATUSES = frozenset({"complete", "pending", "unprovable"})
PENDING_KINDS = frozenset(
    {"derive_gap", "acquisition_failure", "partial_tail", "refresh", "native_conflict"}
)
RANGE_KINDS = frozenset({"bounded", "whole_source"})
VALUE_STATUSES = frozenset({"known", "unavailable", "invalidated"})
QUALIFICATION_STATUSES = frozenset({"known", "not_consumed", "unavailable", "invalidated"})
DEPENDENCY_ROLES = frozenset({"model", "closure"})
COMPLETION_DEPENDENCY_KINDS = frozenset({"observation", "context"})
PENDING_COMPONENTS = frozenset({"usage", "raw_cache"})

# Finite, shareable reason codes. Internal positions and native identifiers never appear.
REASONS = frozenset(
    {
        "acquisition_ahead",
        "acquisition_unprovable",
        "decode_failure",
        "derive_pending",
        "held_source_skipped",
        "json_failure",
        "non_object_record",
        "not_yet_derived",
        "parser_refresh",
        "partial_tail",
        "rebuild",
        "codex_catchup",
        "sanitization_refused",
        "scope_changed",
        "source_recovery_pending",
        "storage_unavailable",
        "untracked",
        "usage_proof_limit",
        "usage_proof_unprovable",
        "usage_derive_gap",
        "native_conflict",
        "version_changed",
        "reconcile",
        "invalid_state",
    }
)
REFUSAL_CODES = frozenset({"invalid_payload", "key_collision", "unsafe_identity", "resource_limit"})

# invalidation reason -> (pending kind, raw_cache component, usage component)
_INVALIDATION_SHAPE: dict[str, tuple[str, bool, bool]] = {
    "parser_refresh": ("refresh", True, True),
    "rebuild": ("refresh", False, True),
    "codex_catchup": ("derive_gap", False, True),
    "native_conflict": ("native_conflict", False, True),
    "version_changed": ("derive_gap", False, True),
    # A guarded reconciliation changed a committed observation that completion consumed.
    "reconcile": ("derive_gap", False, True),
}

_INT64_MAX = 2**63 - 1
_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class UsageSourceConflict(Exception):  # noqa: N818 - a bounded signal, not an error condition
    """A compare-and-swap revision or scope check failed; the owner rolls back and retries."""


class UsageSourceInvalid(ValueError):
    """A record violated a storage invariant (bounded; never carries source bytes)."""


# -- Frozen records ----------------------------------------------------------


@dataclass(frozen=True)
class SourceScope:
    """Opaque generation/version scope of one source; host/session only when verified."""

    source_path: str
    generation_id: str
    derive_version: str
    host: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class AcquisitionWitness:
    """Cheap change-detection fields of a guarded acquisition (never prefix continuity)."""

    device: int | None = None
    inode: int | None = None
    size: int | None = None
    mtime_ns: int | None = None
    tail_sha256: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "device": self.device,
                "inode": self.inode,
                "size": self.size,
                "mtime_ns": self.mtime_ns,
                "tail_sha256": self.tail_sha256,
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class AcquisitionBoundary:
    """Physical range ``[0, offset)`` acquired under ``acquisition_version`` (None = unknown)."""

    acquisition_version: str
    offset: int | None
    line_no: int | None


@dataclass(frozen=True)
class DerivedBoundary:
    """A successful derived boundary; every position nullable (unavailable)."""

    scope: SourceScope
    acquisition_version: str | None
    offset: int | None
    line_no: int | None
    raw_id: int | None
    at: str | None


@dataclass(frozen=True)
class OriginalAcquisition:
    """Verified canonical original-source comparison range (ENH-3770 recovery evidence)."""

    scope: SourceScope
    acquisition_version: str
    offset: int
    line_no: int
    source_revision: int

    def to_json(self) -> str:
        return json.dumps(
            {
                "source_path": self.scope.source_path,
                "generation_id": self.scope.generation_id,
                "derive_version": self.scope.derive_version,
                "acquisition_version": self.acquisition_version,
                "offset": self.offset,
                "line_no": self.line_no,
                "source_revision": self.source_revision,
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class SourcePending:
    """One unresolved obligation. ``None`` bounds mean unavailable, never zero."""

    scope: SourceScope
    kind: str
    reason: str
    range_kind: str = "whole_source"
    refusal_code: str | None = None
    affected_usage_event_id: int | None = None
    first_raw_id: int | None = None
    last_raw_id: int | None = None
    first_line_no: int | None = None
    last_line_no: int | None = None
    first_offset: int | None = None
    end_offset: int | None = None
    raw_cache_pending: bool = False
    usage_pending: bool = True
    original_acquisition: OriginalAcquisition | None = None
    obligation_id: str | None = None


@dataclass(frozen=True)
class ConsumedRange:
    """What a recovery actually consumed; ``full_scope`` proves the whole source was covered."""

    scope: SourceScope
    first_raw_id: int | None = None
    last_raw_id: int | None = None
    first_line_no: int | None = None
    last_line_no: int | None = None
    first_offset: int | None = None
    end_offset: int | None = None
    full_scope: bool = False


@dataclass(frozen=True)
class PendingRecovery:
    """One outstanding obligation with the revisions and authority recovery must validate.

    ``head_revision`` and ``obligation_revision`` are the two compare-and-swap revisions an
    acknowledgement needs (never the acquisition revision stored in the authority).
    ``original_acquisition`` is the persisted authority only when it decodes, is typed and
    names this obligation's exact source/generation/derive version (ENH-3770); otherwise
    it is ``None`` -- permission is withheld while the obligation stays outstanding.
    """

    pending: SourcePending
    head_revision: int
    obligation_revision: int
    original_acquisition: OriginalAcquisition | None = None


@dataclass(frozen=True)
class QualificationDependency:
    """One native context position a qualification consumed (finite frontier)."""

    role: str
    source_path: str
    generation_id: str
    derive_version: str
    line_no: int
    host: str | None = None
    session_id: str | None = None
    ordinal: int | None = None
    raw_event_id: int | None = None


@dataclass(frozen=True)
class ObservationWitness:
    """Actual applied-value supplier and consumed qualification frontier of an observation."""

    usage_event_id: int
    value_status: str = "unavailable"
    qualification_status: str = "unavailable"
    supplier_source_path: str | None = None
    supplier_host: str | None = None
    supplier_session_id: str | None = None
    supplier_generation_id: str | None = None
    supplier_derive_version: str | None = None
    supplier_line_no: int | None = None
    supplier_ordinal: int | None = None
    supplier_raw_id: int | None = None
    qualification_dependencies: tuple[QualificationDependency, ...] = ()


@dataclass(frozen=True)
class CompletionDependency:
    """One observation/supplier or raw-context fact consumed by the last positive proof."""

    dependency_id: str
    kind: str
    usage_event_id: int | None = None
    dependency_source_path: str | None = None
    dependency_generation_id: str | None = None
    dependency_derive_version: str | None = None
    line_no: int | None = None
    ordinal: int | None = None
    raw_event_id: int | None = None


@dataclass(frozen=True)
class SourceDeriveCompletion:
    """Committed source completion. ``basis`` is ``semantic`` only for proved complete state.

    ``outstanding`` is ``none``, ``usage``, ``raw_cache`` or ``both`` (unresolved work
    components) or ``unknown`` when it cannot be read.
    """

    status: Literal["complete", "pending", "unprovable"]
    reason: str | None
    basis: Literal["semantic", "none"]
    scope: SourceScope | None = None
    revision: int | None = None
    boundary: DerivedBoundary | None = None
    outstanding: str = "unknown"


@dataclass(frozen=True)
class HeadState:
    """Raw head row, for owners that need acquisition fields (internal)."""

    scope: SourceScope
    revision: int
    status: str
    reason: str | None
    acquisition_version: str | None
    acquired_offset: int | None
    acquired_line_no: int | None
    acquisition_witness: dict[str, object] | None
    successful: DerivedBoundary | None


@dataclass(frozen=True)
class _PendingRow:
    obligation_id: str
    revision: int
    kind: str
    reason: str
    range_kind: str
    first_raw_id: int | None
    last_raw_id: int | None
    first_line_no: int | None
    last_line_no: int | None
    first_offset: int | None
    end_offset: int | None
    raw_cache_pending: bool
    usage_pending: bool


# -- Validation helpers ------------------------------------------------------


def new_generation_id() -> str:
    """An opaque durable generation token (no native-order or trust meaning)."""
    return uuid.uuid4().hex


def new_obligation_id() -> str:
    return uuid.uuid4().hex


def _int_ok(value: object, *, minimum: int = 0) -> bool:
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= _INT64_MAX
    )


def _require(condition: bool, what: str) -> None:
    if not condition:
        raise UsageSourceInvalid(what)


def _validate_scope(scope: SourceScope) -> None:
    _require(isinstance(scope.source_path, str) and bool(scope.source_path), "source_path")
    _require(isinstance(scope.generation_id, str) and bool(scope.generation_id), "generation_id")
    _require(isinstance(scope.derive_version, str) and bool(scope.derive_version), "derive_version")


def _validate_reason(reason: str | None) -> None:
    _require(reason is None or reason in REASONS, "reason")


def _validate_pending(pending: SourcePending) -> None:
    _validate_scope(pending.scope)
    _require(pending.kind in PENDING_KINDS, "kind")
    _validate_reason(pending.reason)
    _require(pending.reason is not None, "reason")
    _require(pending.range_kind in RANGE_KINDS, "range_kind")
    _require(pending.refusal_code is None or pending.refusal_code in REFUSAL_CODES, "refusal_code")
    for name in (
        "affected_usage_event_id",
        "first_raw_id",
        "last_raw_id",
        "first_offset",
        "end_offset",
    ):
        _require(_int_ok(getattr(pending, name)), name)
    for name in ("first_line_no", "last_line_no"):
        _require(_int_ok(getattr(pending, name), minimum=1), name)
    _require(pending.raw_cache_pending or pending.usage_pending, "components")
    if pending.range_kind == "bounded":
        # A bounded obligation needs at least one proved complete bound pair.
        pairs = (
            (pending.first_raw_id, pending.last_raw_id),
            (pending.first_line_no, pending.last_line_no),
            (pending.first_offset, pending.end_offset),
        )
        _require(any(a is not None and b is not None for a, b in pairs), "bounds")
        for a, b in pairs:
            _require(a is None or b is None or a <= b, "bounds")


def _scope_of(row: tuple[object, ...]) -> SourceScope:
    return SourceScope(
        source_path=str(row[0]),
        generation_id=str(row[1]),
        derive_version=str(row[2]),
        host=row[3] if isinstance(row[3], str) else None,  # type: ignore[arg-type]
        session_id=row[4] if isinstance(row[4], str) else None,  # type: ignore[arg-type]
    )


def _now_iso() -> str:
    from little_loops.session_store.writers import _now

    return _now()


# -- Schema-qualified access -------------------------------------------------


def _safe_schema(conn: sqlite3.Connection, schema: str) -> str | None:
    """Return *schema* only for a generated-safe alias that is attached to *conn*."""
    if schema == "main":
        return "main"
    if not _ALIAS_RE.match(schema):
        return None
    try:
        names = {row[1] for row in conn.execute("PRAGMA database_list")}
    except sqlite3.Error:
        return None
    return schema if schema in names else None


def _table_exists(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    try:
        return (
            conn.execute(
                f"SELECT 1 FROM {schema}.sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            is not None
        )
    except sqlite3.Error:
        return False


def storage_available(conn: sqlite3.Connection, schema: str = "main") -> bool:
    """Whether the five tables exist on the (validated) member."""
    safe = _safe_schema(conn, schema)
    return safe is not None and all(
        _table_exists(conn, safe, table)
        for table in (
            "usage_source_state",
            "usage_source_pending",
            "usage_observation_witnesses",
            "usage_observation_dependencies",
            "usage_completion_dependencies",
        )
    )


def has_prior_semantic_success(conn: sqlite3.Connection) -> bool:
    """Whether any source ever published a successful semantic derived boundary."""
    if not _table_exists(conn, "main", "usage_source_state"):
        return False
    return (
        conn.execute(
            "SELECT 1 FROM usage_source_state WHERE successful_generation_id IS NOT NULL LIMIT 1"
        ).fetchone()
        is not None
    )


# -- Source head -------------------------------------------------------------

_HEAD_COLUMNS = (
    "source_path, generation_id, derive_version, host, session_id, revision, status, reason, "
    "acquisition_version, acquired_offset, acquired_line_no, acquisition_witness_json, "
    "successful_host, successful_session_id, successful_generation_id, "
    "successful_derive_version, successful_acquisition_version, successful_offset, "
    "successful_line_no, successful_raw_id, successful_at"
)


def _head_from_row(row: tuple[object, ...]) -> HeadState:
    witness: dict[str, object] | None = None
    if isinstance(row[11], str):
        try:
            loaded = json.loads(row[11])
            witness = loaded if isinstance(loaded, dict) else None
        except ValueError:
            witness = None
    successful: DerivedBoundary | None = None
    if isinstance(row[14], str) and isinstance(row[15], str):
        successful = DerivedBoundary(
            scope=SourceScope(
                source_path=str(row[0]),
                generation_id=row[14],
                derive_version=row[15],
                host=row[12] if isinstance(row[12], str) else None,  # type: ignore[arg-type]
                session_id=row[13] if isinstance(row[13], str) else None,  # type: ignore[arg-type]
            ),
            acquisition_version=row[16] if isinstance(row[16], str) else None,  # type: ignore[arg-type]
            offset=row[17] if isinstance(row[17], int) else None,  # type: ignore[arg-type]
            line_no=row[18] if isinstance(row[18], int) else None,  # type: ignore[arg-type]
            raw_id=row[19] if isinstance(row[19], int) else None,  # type: ignore[arg-type]
            at=row[20] if isinstance(row[20], str) else None,  # type: ignore[arg-type]
        )
    return HeadState(
        scope=_scope_of((row[0], row[1], row[2], row[3], row[4])),
        revision=int(row[5]),  # type: ignore[call-overload]
        status=str(row[6]),
        reason=row[7] if isinstance(row[7], str) else None,  # type: ignore[arg-type]
        acquisition_version=row[8] if isinstance(row[8], str) else None,  # type: ignore[arg-type]
        acquired_offset=row[9] if isinstance(row[9], int) else None,  # type: ignore[arg-type]
        acquired_line_no=row[10] if isinstance(row[10], int) else None,  # type: ignore[arg-type]
        acquisition_witness=witness,
        successful=successful,
    )


def read_source_head(
    conn: sqlite3.Connection, source_path: str, *, schema: str = "main"
) -> HeadState | None:
    """The durable source head, or None when absent/unavailable (no write, no migration)."""
    safe = _safe_schema(conn, schema)
    if safe is None or not _table_exists(conn, safe, "usage_source_state"):
        return None
    row = conn.execute(
        f"SELECT {_HEAD_COLUMNS} FROM {safe}.usage_source_state WHERE source_path = ?",
        (source_path,),
    ).fetchone()
    return _head_from_row(tuple(row)) if row is not None else None


def head_revision(conn: sqlite3.Connection, source_path: str) -> int | None:
    """Current persistent head revision (None = absent-head sentinel)."""
    head = read_source_head(conn, source_path)
    return head.revision if head is not None else None


def _check_head(
    conn: sqlite3.Connection, source_path: str, expected: int | None
) -> HeadState | None:
    head = read_source_head(conn, source_path)
    current = head.revision if head is not None else None
    if current != expected:
        raise UsageSourceConflict("head_revision")
    return head


def _bump(
    conn: sqlite3.Connection, source_path: str, expected: int, assignments: str, params: tuple
) -> int:
    cur = conn.execute(
        f"UPDATE usage_source_state SET {assignments}, revision = revision + 1 "
        "WHERE source_path = ? AND revision = ?",
        (*params, source_path, expected),
    )
    if cur.rowcount != 1:
        raise UsageSourceConflict("head_revision")
    return expected + 1


def _insert_head(
    conn: sqlite3.Connection,
    scope: SourceScope,
    *,
    status: str,
    reason: str | None,
    acquisition: AcquisitionBoundary | None = None,
    witness: AcquisitionWitness | None = None,
) -> int:
    conn.execute(
        "INSERT INTO usage_source_state(source_path, generation_id, derive_version, revision, "
        "host, session_id, status, reason, acquisition_version, acquired_offset, "
        "acquired_line_no, acquisition_witness_json) "
        "VALUES(?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            scope.source_path,
            scope.generation_id,
            scope.derive_version,
            scope.host,
            scope.session_id,
            status,
            reason,
            acquisition.acquisition_version if acquisition else None,
            acquisition.offset if acquisition else None,
            acquisition.line_no if acquisition else None,
            witness.to_json() if witness else None,
        ),
    )
    return 1


def record_source_acquisition(
    conn: sqlite3.Connection,
    scope: SourceScope,
    acquired: AcquisitionBoundary,
    witness: AcquisitionWitness,
    *,
    expected_head_revision: int | None,
) -> int:
    """Account for acquired physical bounds without publishing completion; return the revision.

    ``expected_head_revision=None`` means insert-if-absent and never resets an existing head.
    A complete head whose acquisition moved past its success becomes ``pending``; a changed
    generation starts fresh acquisition scope while the older success stays historical.
    """
    _validate_scope(scope)
    _require(_int_ok(acquired.offset) and _int_ok(acquired.line_no), "acquisition")
    head = _check_head(conn, scope.source_path, expected_head_revision)
    if head is None:
        try:
            return _insert_head(
                conn,
                scope,
                status="pending",
                reason="not_yet_derived",
                acquisition=acquired,
                witness=witness,
            )
        except sqlite3.IntegrityError as exc:
            raise UsageSourceConflict("head_revision") from exc
    assert expected_head_revision is not None
    same_scope = (
        head.scope.generation_id == scope.generation_id
        and head.scope.derive_version == scope.derive_version
    )
    status, reason = head.status, head.reason
    successful_offset = head.successful.offset if head.successful else None
    if not same_scope:
        status, reason = "pending", "scope_changed"
    elif head.status == "complete" and (
        acquired.offset is None
        or successful_offset is None
        or acquired.offset > successful_offset
        or acquired.acquisition_version != head.acquisition_version
    ):
        status, reason = "pending", "acquisition_ahead"
    return _bump(
        conn,
        scope.source_path,
        expected_head_revision,
        "generation_id = ?, derive_version = ?, host = COALESCE(?, host), "
        "session_id = COALESCE(?, session_id), status = ?, reason = ?, acquisition_version = ?, "
        "acquired_offset = ?, acquired_line_no = ?, acquisition_witness_json = ?",
        (
            scope.generation_id,
            scope.derive_version,
            scope.host,
            scope.session_id,
            status,
            reason,
            acquired.acquisition_version,
            acquired.offset,
            acquired.line_no,
            witness.to_json(),
        ),
    )


# -- Pending obligations -----------------------------------------------------


def _pending_rows(
    conn: sqlite3.Connection, source_path: str, *, schema: str = "main"
) -> list[_PendingRow]:
    safe = _safe_schema(conn, schema)
    if safe is None or not _table_exists(conn, safe, "usage_source_pending"):
        return []
    return [
        _PendingRow(
            obligation_id=row[0],
            revision=row[1],
            kind=row[2],
            reason=row[3],
            range_kind=row[4],
            first_raw_id=row[5],
            last_raw_id=row[6],
            first_line_no=row[7],
            last_line_no=row[8],
            first_offset=row[9],
            end_offset=row[10],
            raw_cache_pending=bool(row[11]),
            usage_pending=bool(row[12]),
        )
        for row in conn.execute(
            "SELECT obligation_id, revision, kind, reason, range_kind, first_raw_id, last_raw_id, "
            "first_line_no, last_line_no, first_offset, end_offset, raw_cache_pending, "
            f"usage_pending FROM {safe}.usage_source_pending WHERE source_path = ? "
            "ORDER BY obligation_id",
            (source_path,),
        )
    ]


def pending_obligations(
    conn: sqlite3.Connection, source_path: str, *, schema: str = "main"
) -> tuple[SourcePending, ...]:
    """Unresolved obligations of *source_path* (current and older generations)."""
    safe = _safe_schema(conn, schema)
    if safe is None or not _table_exists(conn, safe, "usage_source_pending"):
        return ()
    out: list[SourcePending] = []
    for row in conn.execute(
        "SELECT obligation_id, source_path, generation_id, derive_version, kind, reason, "
        "range_kind, refusal_code, affected_usage_event_id, first_raw_id, last_raw_id, "
        "first_line_no, last_line_no, first_offset, end_offset, raw_cache_pending, "
        f"usage_pending FROM {safe}.usage_source_pending WHERE source_path = ? "
        "ORDER BY obligation_id",
        (source_path,),
    ):
        out.append(
            SourcePending(
                scope=SourceScope(row[1], row[2], row[3]),
                kind=row[4],
                reason=row[5],
                range_kind=row[6],
                refusal_code=row[7],
                affected_usage_event_id=row[8],
                first_raw_id=row[9],
                last_raw_id=row[10],
                first_line_no=row[11],
                last_line_no=row[12],
                first_offset=row[13],
                end_offset=row[14],
                raw_cache_pending=bool(row[15]),
                usage_pending=bool(row[16]),
                obligation_id=row[0],
            )
        )
    return tuple(out)


def _decode_original_acquisition(
    raw: object, scope: SourceScope, head_revision_now: int
) -> OriginalAcquisition | None:
    """Validate a persisted ``OriginalAcquisition`` against its obligation's scope.

    Returns ``None`` for anything that is not exactly the typed record this module writes:
    malformed JSON, wrong types (booleans are not integers), negative positions, an empty
    version, another scope, or an acquisition revision beyond the current head revision.
    """
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    text_fields = ("source_path", "generation_id", "derive_version", "acquisition_version")
    if not all(isinstance(data.get(name), str) and data[name] for name in text_fields):
        return None
    if (data["source_path"], data["generation_id"], data["derive_version"]) != (
        scope.source_path,
        scope.generation_id,
        scope.derive_version,
    ):
        return None
    offset, line_no, revision = data.get("offset"), data.get("line_no"), data.get("source_revision")
    if not (_int_ok(offset) and _int_ok(line_no) and _int_ok(revision, minimum=1)):
        return None
    assert isinstance(offset, int) and isinstance(line_no, int) and isinstance(revision, int)
    if revision > head_revision_now:
        return None
    return OriginalAcquisition(
        scope=scope,
        acquisition_version=data["acquisition_version"],
        offset=offset,
        line_no=line_no,
        source_revision=revision,
    )


def read_pending_recovery(
    conn: sqlite3.Connection, source_path: str, *, schema: str = "main"
) -> tuple[PendingRecovery, ...]:
    """Outstanding obligations of *source_path* with revisions and validated authority.

    A pure ``SELECT`` over the supplied member (ENH-3770): empty for an unsafe alias or a
    pre-migration store, ordered like :func:`pending_obligations`. Malformed, wrong-scope or
    future-revision authority yields ``original_acquisition=None`` while the obligation is
    still returned, so a caller can never mistake absence of permission for absence of work.
    """
    safe = _safe_schema(conn, schema)
    if (
        safe is None
        or not _table_exists(conn, safe, "usage_source_pending")
        or not _table_exists(conn, safe, "usage_source_state")
    ):
        return ()
    head = conn.execute(
        f"SELECT revision FROM {safe}.usage_source_state WHERE source_path = ?", (source_path,)
    ).fetchone()
    head_rev = int(head[0]) if head is not None else 0
    out: list[PendingRecovery] = []
    for row in conn.execute(
        "SELECT obligation_id, source_path, generation_id, derive_version, kind, reason, "
        "range_kind, refusal_code, affected_usage_event_id, first_raw_id, last_raw_id, "
        "first_line_no, last_line_no, first_offset, end_offset, raw_cache_pending, "
        f"usage_pending, revision, original_acquisition_json FROM {safe}.usage_source_pending "
        "WHERE source_path = ? ORDER BY obligation_id",
        (source_path,),
    ):
        scope = SourceScope(row[1], row[2], row[3])
        authority = _decode_original_acquisition(row[18], scope, head_rev)
        out.append(
            PendingRecovery(
                pending=SourcePending(
                    scope=scope,
                    kind=row[4],
                    reason=row[5],
                    range_kind=row[6],
                    refusal_code=row[7],
                    affected_usage_event_id=row[8],
                    first_raw_id=row[9],
                    last_raw_id=row[10],
                    first_line_no=row[11],
                    last_line_no=row[12],
                    first_offset=row[13],
                    end_offset=row[14],
                    raw_cache_pending=bool(row[15]),
                    usage_pending=bool(row[16]),
                    original_acquisition=authority,
                    obligation_id=row[0],
                ),
                head_revision=head_rev,
                obligation_revision=int(row[17]),
                original_acquisition=authority,
            )
        )
    return tuple(out)


def _min_known(a: int | None, b: int | None) -> int | None:
    known = [v for v in (a, b) if v is not None]
    return min(known) if known else None


def _max_known(a: int | None, b: int | None) -> int | None:
    known = [v for v in (a, b) if v is not None]
    return max(known) if known else None


def _merge_pending(conn: sqlite3.Connection, pending: SourcePending) -> str:
    """Insert or merge one obligation (min first bounds, max last bounds, component union)."""
    scope = pending.scope
    existing = conn.execute(
        "SELECT obligation_id, range_kind, first_raw_id, last_raw_id, first_line_no, "
        "last_line_no, first_offset, end_offset, raw_cache_pending, usage_pending, "
        "original_acquisition_json FROM usage_source_pending WHERE source_path = ? "
        "AND generation_id = ? AND derive_version = ? AND kind = ? AND reason = ? "
        "AND COALESCE(affected_usage_event_id, -1) = COALESCE(?, -1)",
        (
            scope.source_path,
            scope.generation_id,
            scope.derive_version,
            pending.kind,
            pending.reason,
            pending.affected_usage_event_id,
        ),
    ).fetchone()
    original = pending.original_acquisition.to_json() if pending.original_acquisition else None
    if existing is None:
        obligation_id = pending.obligation_id or new_obligation_id()
        conn.execute(
            "INSERT INTO usage_source_pending(obligation_id, source_path, generation_id, "
            "derive_version, kind, reason, range_kind, refusal_code, affected_usage_event_id, "
            "first_raw_id, last_raw_id, first_line_no, last_line_no, first_offset, end_offset, "
            "revision, raw_cache_pending, usage_pending, original_acquisition_json) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (
                obligation_id,
                scope.source_path,
                scope.generation_id,
                scope.derive_version,
                pending.kind,
                pending.reason,
                pending.range_kind,
                pending.refusal_code,
                pending.affected_usage_event_id,
                pending.first_raw_id,
                pending.last_raw_id,
                pending.first_line_no,
                pending.last_line_no,
                pending.first_offset,
                pending.end_offset,
                int(pending.raw_cache_pending),
                int(pending.usage_pending),
                original,
            ),
        )
        return obligation_id
    (oid, range_kind, f_raw, l_raw, f_line, l_line, f_off, e_off, cache, usage, prev_orig) = (
        existing
    )
    whole = "whole_source" if "whole_source" in (range_kind, pending.range_kind) else "bounded"
    conn.execute(
        "UPDATE usage_source_pending SET range_kind = ?, first_raw_id = ?, last_raw_id = ?, "
        "first_line_no = ?, last_line_no = ?, first_offset = ?, end_offset = ?, "
        "raw_cache_pending = ?, usage_pending = ?, refusal_code = COALESCE(?, refusal_code), "
        "original_acquisition_json = COALESCE(?, original_acquisition_json), "
        "revision = revision + 1 WHERE obligation_id = ?",
        (
            whole,
            _min_known(f_raw, pending.first_raw_id),
            _max_known(l_raw, pending.last_raw_id),
            _min_known(f_line, pending.first_line_no),
            _max_known(l_line, pending.last_line_no),
            _min_known(f_off, pending.first_offset),
            _max_known(e_off, pending.end_offset),
            int(bool(cache) or pending.raw_cache_pending),
            int(bool(usage) or pending.usage_pending),
            pending.refusal_code,
            original if original is not None else prev_orig,
            oid,
        ),
    )
    return str(oid)


def record_source_pending(
    conn: sqlite3.Connection, pending: SourcePending, *, expected_head_revision: int | None
) -> int:
    """Merge an obligation and downgrade the head in the caller's transaction.

    A first failure uses ``expected_head_revision=None`` (absent-head sentinel) and
    inserts the head only if still absent. Returns the new head revision.
    """
    _validate_pending(pending)
    scope = pending.scope
    head = _check_head(conn, scope.source_path, expected_head_revision)
    _merge_pending(conn, pending)
    status = (
        "unprovable" if pending.kind in {"acquisition_failure", "native_conflict"} else "pending"
    )
    if head is None:
        try:
            return _insert_head(conn, scope, status=status, reason=pending.reason)
        except sqlite3.IntegrityError as exc:
            raise UsageSourceConflict("head_revision") from exc
    assert expected_head_revision is not None
    keep_unprovable = head.status == "unprovable" and status != "unprovable"
    same_scope = (
        head.scope.generation_id == scope.generation_id
        and head.scope.derive_version == scope.derive_version
    )
    new_status = head.status if keep_unprovable and same_scope else status
    return _bump(
        conn,
        scope.source_path,
        expected_head_revision,
        "status = ?, reason = ?",
        (new_status, pending.reason if new_status == status else head.reason),
    )


def acknowledge_source_pending(
    conn: sqlite3.Connection,
    obligation_id: str,
    consumed: ConsumedRange,
    *,
    expected_head_revision: int,
    expected_obligation_revision: int,
    components: frozenset[str],
) -> bool:
    """Clear covered components of an obligation; False (no change) unless fully covered.

    Both captured revisions must match. A whole-source obligation needs proved full-scope
    consumption; a bounded one needs every populated bound pair covered by the consumed
    range. Partial coverage retains the entire obligation. The row is deleted only when
    both components are clear. An older-generation obligation never clears for a current
    generation consumer (the scope must match exactly).
    """
    _require(components <= PENDING_COMPONENTS and bool(components), "components")
    row = conn.execute(
        "SELECT source_path, generation_id, derive_version, range_kind, first_raw_id, "
        "last_raw_id, first_line_no, last_line_no, first_offset, end_offset, revision, "
        "raw_cache_pending, usage_pending FROM usage_source_pending WHERE obligation_id = ?",
        (obligation_id,),
    ).fetchone()
    if row is None:
        return False
    (source, generation, version, range_kind, f_raw, l_raw, f_line, l_line, f_off, e_off) = row[:10]
    obligation_revision, cache, usage = row[10], bool(row[11]), bool(row[12])
    scope = consumed.scope
    if (source, generation, version) != (
        scope.source_path,
        scope.generation_id,
        scope.derive_version,
    ):
        return False
    head = read_source_head(conn, source)
    if head is None or head.revision != expected_head_revision:
        return False
    if obligation_revision != expected_obligation_revision:
        return False
    if head.scope.generation_id != generation or head.scope.derive_version != version:
        return False

    def covered(
        first: int | None, last: int | None, c_first: int | None, c_last: int | None
    ) -> bool:
        if first is None and last is None:
            return True
        if first is None or last is None or c_first is None or c_last is None:
            return False
        return c_first <= first and last <= c_last

    if range_kind == "whole_source":
        if not consumed.full_scope:
            return False
    elif not consumed.full_scope:
        pairs = (
            (f_raw, l_raw, consumed.first_raw_id, consumed.last_raw_id),
            (f_line, l_line, consumed.first_line_no, consumed.last_line_no),
            (f_off, e_off, consumed.first_offset, consumed.end_offset),
        )
        populated = [p for p in pairs if p[0] is not None or p[1] is not None]
        if not populated or not all(covered(*p) for p in populated):
            return False
    new_cache = cache and "raw_cache" not in components
    new_usage = usage and "usage" not in components
    if new_cache or new_usage:
        conn.execute(
            "UPDATE usage_source_pending SET raw_cache_pending = ?, usage_pending = ?, "
            "revision = revision + 1 WHERE obligation_id = ?",
            (int(new_cache), int(new_usage), obligation_id),
        )
    else:
        conn.execute("DELETE FROM usage_source_pending WHERE obligation_id = ?", (obligation_id,))
    _bump(conn, source, expected_head_revision, "status = status", ())
    return True


def _usage_outstanding(conn: sqlite3.Connection, source_path: str, schema: str = "main") -> str:
    rows = _pending_rows(conn, source_path, schema=schema)
    usage = any(r.usage_pending for r in rows)
    cache = any(r.raw_cache_pending for r in rows)
    return "both" if usage and cache else "usage" if usage else "raw_cache" if cache else "none"


# -- Completion publication --------------------------------------------------


def publish_source_completion(
    conn: sqlite3.Connection,
    completion: SourceDeriveCompletion,
    dependencies: tuple[CompletionDependency, ...],
    *,
    expected_head_revision: int,
) -> int:
    """Publish positive completion and replace its bounded dependency set; return revision.

    Refuses (no write, :class:`UsageSourceConflict`) unless the head still has the expected
    revision and scope, acquisition coverage reaches the boundary under a matching
    acquisition version, and no usage-component obligation remains.
    """
    _require(completion.status == "complete" and completion.basis == "semantic", "completion")
    boundary = completion.boundary
    _require(boundary is not None, "boundary")
    assert boundary is not None
    scope = boundary.scope
    _validate_scope(scope)
    _require(
        all(_int_ok(v) for v in (boundary.offset, boundary.line_no, boundary.raw_id)), "boundary"
    )
    _require(boundary.offset is not None and boundary.acquisition_version is not None, "boundary")
    for dep in dependencies:
        _require(dep.kind in COMPLETION_DEPENDENCY_KINDS and bool(dep.dependency_id), "dependency")
    head = _check_head(conn, scope.source_path, expected_head_revision)
    if head is None:
        raise UsageSourceConflict("head_revision")
    if (
        head.scope.generation_id != scope.generation_id
        or head.scope.derive_version != scope.derive_version
    ):
        raise UsageSourceConflict("scope")
    assert boundary.offset is not None
    if (
        head.acquisition_version != boundary.acquisition_version
        or head.acquired_offset is None
        or head.acquired_offset < boundary.offset
    ):
        raise UsageSourceConflict("acquisition")
    if any(r.usage_pending for r in _pending_rows(conn, scope.source_path)):
        raise UsageSourceConflict("usage_pending")
    conn.execute(
        "DELETE FROM usage_completion_dependencies WHERE source_path = ? AND generation_id = ? "
        "AND derive_version = ?",
        (scope.source_path, scope.generation_id, scope.derive_version),
    )
    for dep in dependencies:
        conn.execute(
            "INSERT INTO usage_completion_dependencies(source_path, generation_id, "
            "derive_version, dependency_id, kind, usage_event_id, dependency_source_path, "
            "dependency_generation_id, dependency_derive_version, line_no, ordinal, "
            "raw_event_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scope.source_path,
                scope.generation_id,
                scope.derive_version,
                dep.dependency_id,
                dep.kind,
                dep.usage_event_id,
                dep.dependency_source_path,
                dep.dependency_generation_id,
                dep.dependency_derive_version,
                dep.line_no,
                dep.ordinal,
                dep.raw_event_id,
            ),
        )
    return _bump(
        conn,
        scope.source_path,
        expected_head_revision,
        "status = 'complete', reason = NULL, host = COALESCE(?, host), "
        "session_id = COALESCE(?, session_id), successful_host = ?, successful_session_id = ?, "
        "successful_generation_id = ?, successful_derive_version = ?, "
        "successful_acquisition_version = ?, successful_offset = ?, successful_line_no = ?, "
        "successful_raw_id = ?, successful_at = ?",
        (
            scope.host,
            scope.session_id,
            scope.host,
            scope.session_id,
            scope.generation_id,
            scope.derive_version,
            boundary.acquisition_version,
            boundary.offset,
            boundary.line_no,
            boundary.raw_id,
            boundary.at or _now_iso(),
        ),
    )


# -- Witnesses and invalidation ---------------------------------------------


def write_observation_witness(conn: sqlite3.Connection, witness: ObservationWitness) -> None:
    """Atomically write the actual supplier and replace its entire qualification frontier.

    ``invalidated`` may retain the independently valid, uncontradicted context a conflict
    proof left standing (ENH-3770). That residual frontier is bookkeeping only: the status
    stays non-affirmative, so it can neither qualify a row nor prove a figure as-of.
    """
    _require(_int_ok(witness.usage_event_id, minimum=1), "usage_event_id")
    _require(witness.value_status in VALUE_STATUSES, "value_status")
    _require(witness.qualification_status in QUALIFICATION_STATUSES, "qualification_status")
    for name in ("supplier_line_no", "supplier_ordinal", "supplier_raw_id"):
        _require(_int_ok(getattr(witness, name)), name)
    if witness.qualification_status in {"unavailable", "not_consumed"}:
        # Unavailable evidence cannot be encoded as an empty proved frontier.
        _require(not witness.qualification_dependencies, "frontier")
    for dep in witness.qualification_dependencies:
        _require(dep.role in DEPENDENCY_ROLES, "role")
        _require(_int_ok(dep.line_no, minimum=1) and dep.line_no is not None, "line_no")
        _require(_int_ok(dep.ordinal) and _int_ok(dep.raw_event_id), "dependency")
    conn.execute(
        "DELETE FROM usage_observation_dependencies WHERE usage_event_id = ?",
        (witness.usage_event_id,),
    )
    conn.execute(
        "INSERT INTO usage_observation_witnesses(usage_event_id, supplier_source_path, "
        "supplier_host, supplier_session_id, supplier_generation_id, supplier_derive_version, "
        "supplier_line_no, supplier_ordinal, supplier_raw_id, value_status, "
        "qualification_status) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(usage_event_id) DO UPDATE SET "
        "supplier_source_path = excluded.supplier_source_path, "
        "supplier_host = excluded.supplier_host, "
        "supplier_session_id = excluded.supplier_session_id, "
        "supplier_generation_id = excluded.supplier_generation_id, "
        "supplier_derive_version = excluded.supplier_derive_version, "
        "supplier_line_no = excluded.supplier_line_no, "
        "supplier_ordinal = excluded.supplier_ordinal, "
        "supplier_raw_id = excluded.supplier_raw_id, value_status = excluded.value_status, "
        "qualification_status = excluded.qualification_status",
        (
            witness.usage_event_id,
            witness.supplier_source_path,
            witness.supplier_host,
            witness.supplier_session_id,
            witness.supplier_generation_id,
            witness.supplier_derive_version,
            witness.supplier_line_no,
            witness.supplier_ordinal,
            witness.supplier_raw_id,
            witness.value_status,
            witness.qualification_status,
        ),
    )
    for dep in witness.qualification_dependencies:
        conn.execute(
            "INSERT INTO usage_observation_dependencies(usage_event_id, role, source_path, "
            "generation_id, derive_version, line_no, host, session_id, ordinal, raw_event_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                witness.usage_event_id,
                dep.role,
                dep.source_path,
                dep.generation_id,
                dep.derive_version,
                dep.line_no,
                dep.host,
                dep.session_id,
                dep.ordinal,
                dep.raw_event_id,
            ),
        )


def read_observation_witness(
    conn: sqlite3.Connection, usage_event_id: int, *, schema: str = "main"
) -> ObservationWitness:
    """Stored supplier/frontier facts; legacy or missing storage reads as explicit unavailable."""
    unavailable = ObservationWitness(usage_event_id)
    safe = _safe_schema(conn, schema)
    if (
        safe is None
        or not _table_exists(conn, safe, "usage_observation_witnesses")
        or not _table_exists(conn, safe, "usage_observation_dependencies")
    ):
        return unavailable
    row = conn.execute(
        "SELECT supplier_source_path, supplier_host, supplier_session_id, supplier_generation_id, "
        "supplier_derive_version, supplier_line_no, supplier_ordinal, supplier_raw_id, "
        f"value_status, qualification_status FROM {safe}.usage_observation_witnesses "
        "WHERE usage_event_id = ?",
        (usage_event_id,),
    ).fetchone()
    if row is None:
        return unavailable
    deps = tuple(
        QualificationDependency(
            role=d[0],
            source_path=d[1],
            generation_id=d[2],
            derive_version=d[3],
            line_no=d[4],
            host=d[5],
            session_id=d[6],
            ordinal=d[7],
            raw_event_id=d[8],
        )
        for d in conn.execute(
            "SELECT role, source_path, generation_id, derive_version, line_no, host, "
            f"session_id, ordinal, raw_event_id FROM {safe}.usage_observation_dependencies "
            "WHERE usage_event_id = ? ORDER BY role, source_path, generation_id, "
            "derive_version, line_no",
            (usage_event_id,),
        )
    )
    return ObservationWitness(
        usage_event_id=usage_event_id,
        supplier_source_path=row[0],
        supplier_host=row[1],
        supplier_session_id=row[2],
        supplier_generation_id=row[3],
        supplier_derive_version=row[4],
        supplier_line_no=row[5],
        supplier_ordinal=row[6],
        supplier_raw_id=row[7],
        value_status=row[8],
        qualification_status=row[9],
        qualification_dependencies=deps,
    )


def invalidate_usage_dependencies(
    conn: sqlite3.Connection,
    usage_event_ids: tuple[int, ...],
    source_scopes: tuple[SourceScope, ...],
    *,
    reason: str,
    preserve_witness_ids: Collection[int] = (),
    contradicted: Mapping[int, frozenset[str]] | None = None,
) -> None:
    """Invalidate tracked completion that consumed the affected observations/sources.

    Call *before* the mutation, in the mutating transaction. Enumerates reverse
    dependencies first (including sources whose dedup supplier is elsewhere), downgrades
    every affected tracked head to ``pending`` with usage-pending disposition, preserves
    older success tuples as historical, then settles the observations' witness rows.
    Untracked sources are untouched (negative tracking only).

    Only a source named in *source_scopes* -- one whose own raw rows change -- owes
    ``raw_cache`` work for a parser refresh; a reverse dependent (for example a copy that
    only consumed another source's usage or context) owes usage recovery alone.

    Witness handling (ENH-3770): an id in *preserve_witness_ids* keeps its supplier and
    frontier rows (the writer replaces them atomically when a permitted change lands); an
    id in *contradicted* keeps its supplier and value evidence, drops only the listed
    dependency roles and becomes ``invalidated`` when it was ``known`` (a witness that does
    not exist is never created); every other id loses its witness and frontier as before.
    Both kinds of id still invalidate their dependents.
    """
    shape = _INVALIDATION_SHAPE.get(reason)
    _require(shape is not None, "reason")
    assert shape is not None
    kind, cache, usage = shape
    narrowed = dict(contradicted or {})
    for roles in narrowed.values():
        _require(bool(roles) and roles <= DEPENDENCY_ROLES, "contradicted_roles")
    if not storage_available(conn):
        return
    keep = frozenset(preserve_witness_ids)
    ids = tuple(dict.fromkeys((*usage_event_ids, *narrowed)))
    affected: dict[tuple[str, str, str], SourceScope] = {}
    for scope in source_scopes:
        _validate_scope(scope)
        affected[(scope.source_path, scope.generation_id, scope.derive_version)] = scope
    sources = {scope.source_path for scope in source_scopes}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        marks = ", ".join("?" for _ in chunk)
        for row in conn.execute(
            "SELECT DISTINCT source_path, generation_id, derive_version "
            f"FROM usage_completion_dependencies WHERE usage_event_id IN ({marks})",
            chunk,
        ):
            affected.setdefault(tuple(row), SourceScope(*row))  # type: ignore[arg-type]
    for source in sorted(sources):
        for row in conn.execute(
            "SELECT DISTINCT source_path, generation_id, derive_version "
            "FROM usage_completion_dependencies WHERE dependency_source_path = ?",
            (source,),
        ):
            affected.setdefault(tuple(row), SourceScope(*row))  # type: ignore[arg-type]
    for source_path, generation, version in sorted(affected):
        head = read_source_head(conn, source_path)
        if head is None:
            continue
        record_source_pending(
            conn,
            SourcePending(
                scope=SourceScope(source_path, head.scope.generation_id, head.scope.derive_version),
                kind=kind,
                reason=reason if reason in REASONS else "invalid_state",
                range_kind="whole_source",
                raw_cache_pending=cache and source_path in sources,
                usage_pending=usage,
            ),
            expected_head_revision=head.revision,
        )
        conn.execute(
            "DELETE FROM usage_completion_dependencies WHERE source_path = ? AND generation_id = ? "
            "AND derive_version = ?",
            (source_path, generation, version),
        )
    doomed = tuple(i for i in ids if i not in keep and i not in narrowed)
    for start in range(0, len(doomed), 500):
        chunk = doomed[start : start + 500]
        marks = ", ".join("?" for _ in chunk)
        conn.execute(
            f"DELETE FROM usage_observation_witnesses WHERE usage_event_id IN ({marks})", chunk
        )
        conn.execute(
            f"DELETE FROM usage_observation_dependencies WHERE usage_event_id IN ({marks})", chunk
        )
    for event_id, roles in sorted(narrowed.items()):
        conn.execute(
            "UPDATE usage_observation_witnesses SET qualification_status = 'invalidated' "
            "WHERE usage_event_id = ? AND qualification_status = 'known'",
            (event_id,),
        )
        marks = ", ".join("?" for _ in roles)
        conn.execute(
            "DELETE FROM usage_observation_dependencies WHERE usage_event_id = ? "
            f"AND role IN ({marks}) AND EXISTS (SELECT 1 FROM usage_observation_witnesses "
            "WHERE usage_event_id = ? AND qualification_status = 'invalidated')",
            (event_id, *sorted(roles), event_id),
        )


# -- Pure completion reader --------------------------------------------------


def _unprovable(reason: str) -> SourceDeriveCompletion:
    return SourceDeriveCompletion(status="unprovable", reason=reason, basis="none")


def read_source_derive_completion(
    conn: sqlite3.Connection, source_path: str, *, schema: str = "main"
) -> SourceDeriveCompletion:
    """Committed-state completion of *source_path*; never stats, parses, prices or writes.

    ``basis`` is ``semantic`` only for a proved complete head whose success tuple matches
    its current generation, derive version and acquisition version, with no usage-component
    obligation. Missing storage/state is ``unprovable`` with a bounded reason; ``legacy``
    never appears here.
    """
    safe = _safe_schema(conn, schema)
    if safe is None or not _table_exists(conn, safe, "usage_source_state"):
        return _unprovable("storage_unavailable")
    try:
        head = read_source_head(conn, source_path, schema=safe)
    except sqlite3.Error:
        return _unprovable("storage_unavailable")
    if head is None:
        return _unprovable("untracked")
    outstanding = _usage_outstanding(conn, source_path, safe)
    reason = head.reason if head.reason in REASONS else None
    if head.status != "complete":
        status: Literal["pending", "unprovable"] = (
            "pending" if head.status == "pending" else "unprovable"
        )
        return SourceDeriveCompletion(
            status=status,
            reason=reason or "invalid_state",
            basis="none",
            scope=head.scope,
            revision=head.revision,
            boundary=head.successful,
            outstanding=outstanding,
        )
    from little_loops.session_store.lifecycle import _USAGE_DERIVE_VERSION

    good = (
        head.successful is not None
        and head.successful.scope.generation_id == head.scope.generation_id
        and head.successful.scope.derive_version == head.scope.derive_version
        and head.scope.derive_version == _USAGE_DERIVE_VERSION
        and head.successful.acquisition_version == head.acquisition_version
        and head.successful.offset is not None
        and head.acquired_offset is not None
        and head.acquired_offset >= head.successful.offset
        and outstanding in {"none", "raw_cache"}
    )
    if not good:
        return SourceDeriveCompletion(
            status="unprovable",
            reason="version_changed"
            if head.scope.derive_version != _USAGE_DERIVE_VERSION
            else "invalid_state",
            basis="none",
            scope=head.scope,
            revision=head.revision,
            boundary=head.successful,
            outstanding=outstanding,
        )
    return SourceDeriveCompletion(
        status="complete",
        reason=None,
        basis="semantic",
        scope=head.scope,
        revision=head.revision,
        boundary=head.successful,
        outstanding=outstanding,
    )

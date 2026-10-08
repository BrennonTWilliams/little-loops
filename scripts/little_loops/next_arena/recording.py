"""Recommendation recording, explicit acceptance and feedback lookup for ``ll-next`` (FEAT-3711).

Three small seams over the ``recommendation_events`` table, all **local SQLite, existing store
only**:

* :func:`record_shown` persists the offered rows in one atomic batch *before* output is rendered,
  so the CLI exposes ``rec_id`` values only for rows that were actually saved. It never creates or
  migrates the store: an unprepared schema reports ``unavailable(schema_not_ready)``.
* :func:`record_accepted` appends an idempotent ``accepted_explicit`` acknowledgement copied from
  the immutable shown row, in one ``BEGIN IMMEDIATE`` transaction with an in-transaction readback.
* :func:`lookup_feedback` is pure over a :class:`~little_loops.next_arena.history.HistorySnapshot`
  that carries a ``recommendation_lookup`` result; it reports ``accepted`` or ``unknown`` for a
  found offer and never an ``ignored`` state.

Writers open the store through ``session_store.backend.connect_existing_writable`` (``mode=rw``,
no creation, no pragmas, no migration) with a 250 ms busy timeout and own the explicit
transaction, rollback and close. There is no total-write-deadline guarantee: the busy timeout
applies per operation. Acceptance proves neither causation nor that work started or succeeded.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from little_loops.next_arena.actions import (
    ActionSpec,
    ActionSpecError,
    UnknownVariantError,
    spec_from_dict,
    spec_to_dict,
)
from little_loops.next_arena.candidates import Candidate
from little_loops.next_arena.history import (
    HistorySnapshot,
    RecommendationEventRow,
    RecommendationLookup,
    RecommendationSchemaProbe,
    decode_recommendation_row,
    read_history_snapshot,
)
from little_loops.next_arena.render import format_instant
from little_loops.session_store.backend import (
    HistoryError,
    HistoryTarget,
    LocalTarget,
    RemoteTarget,
    connect_existing_writable,
)
from little_loops.session_store.db import DEFAULT_DB_PATH, resolve_history_target
from little_loops.session_store.queries import (
    RECOMMENDATION_EVENT_COLUMNS,
    RECOMMENDATION_LOOKUP_SQL,
    recommendation_schema_status,
)
from little_loops.session_store.writers import (
    _analytics_capture_disabled,
    acknowledge_recommendation_event,
    insert_shown_recommendation_events,
)

__all__ = [
    "AcceptanceWriteResult",
    "FeedbackResult",
    "FeedbackUnavailable",
    "RecommendationEvent",
    "RecordingResult",
    "RecordingStatus",
    "WRITE_BUSY_TIMEOUT_SECONDS",
    "automatic_recording_gate",
    "build_shown_rows",
    "canonical_rec_id",
    "freeze_history_target",
    "lookup_feedback",
    "new_invocation_id",
    "offer_problem",
    "project_key_for",
    "record_accepted",
    "record_shown",
]

#: One stored row; the reader row type doubles as the offer record ``feedback`` renders.
RecommendationEvent = RecommendationEventRow

#: SQLite busy timeout for the writers (seconds), per operation -- not a total write deadline.
WRITE_BUSY_TIMEOUT_SECONDS = 0.25

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
#: Copied from the shown row to its acknowledgement; every other column is the accept run's own.
_OWN_COLUMNS = frozenset({"event_id", "kind", "ts", "invocation_id"})
_COPIED_COLUMNS = tuple(c for c in RECOMMENDATION_EVENT_COLUMNS if c not in _OWN_COLUMNS)
#: Open/preflight failures that mean "the existing store is not prepared", not a write fault.
_NOT_READY_REASONS = frozenset(
    {
        "schema_not_ready",
        "store_missing",
        "store_unavailable",
        "missing_table",
        "incompatible_table",
        "incompatible_index",
    }
)


# ------------------------------------------------------------------------------ identities


def canonical_rec_id(text: str) -> str:
    """Normalize a user-supplied ``REC_ID`` to the stored canonical lowercase hyphenated UUID.

    Only the 8-4-4-4-12 hyphenated form is accepted (case-insensitively). Braces, ``urn:uuid:``
    prefixes and unhyphenated hex are rejected so a mangled paste is a usage error, never a
    silently normalized (or falsely unknown) identity.

    Raises:
        ValueError: *text* is not a hyphenated UUID.
    """
    if not _UUID_RE.match(text):
        raise ValueError(f"{text!r} is not a hyphenated 8-4-4-4-12 UUID")
    return str(uuid.UUID(text))


def new_invocation_id() -> str:
    """A fresh ``uuid4`` for one ``ll-next`` run, shared by every row that run writes."""
    return str(uuid.uuid4())


def project_key_for(root: Path) -> str:
    """SHA-256 of the canonical resolved project root (an identity, not a privacy mechanism).

    Independent of the history DB location: a subdirectory invocation shares the key, a
    different checkout does not even when both point at one SQLite file.
    """
    return hashlib.sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()


def freeze_history_target(root: Path) -> tuple[HistoryTarget, dict[str, str]]:
    """Resolve the history target once and freeze a relative local path to an absolute spelling.

    A relative ``LL_HISTORY_DB`` keeps its cwd-relative meaning (resolved against the current
    directory at this single point); the returned target is then passed unchanged through
    preflight and write so no later cwd change can select another store. Also returns the
    ``{"store", "source"}`` provenance reported by ``feedback``.
    """
    target = resolve_history_target(DEFAULT_DB_PATH, root=root)
    if isinstance(target, RemoteTarget):
        return target, {"store": f"remote:{target.provider}", "source": "history.backend"}
    path = target.path if target.path.is_absolute() else Path(os.path.abspath(target.path))
    if os.environ.get("LL_HISTORY_DB"):
        source = "LL_HISTORY_DB"
    elif path == Path(root).resolve() / ".ll" / "history.db":
        source = "default"
    else:
        source = "history.db_path"
    return LocalTarget(path), {"store": str(path), "source": source}


# ------------------------------------------------------------------------------ the gate


def automatic_recording_gate(
    config: Any, *, no_record: bool, explain: bool, has_offers: bool
) -> str | None:
    """Reason automatic recording is disabled, or ``None`` when it may proceed.

    Checked in contract order before any target resolution or write connection:
    ``no_record``, ``explain``, ``config_disabled``, ``env_kill_switch``, ``analytics_disabled``,
    ``command_not_captured``, ``nothing_to_record``. Explicit ``accept`` bypasses all of this.

    Raises:
        NextConfigError: ``next.recording`` is malformed (the caller exits 2).
    """
    from little_loops.config.features import feature_enabled_for

    if no_record:
        return "no_record"
    if explain:
        return "explain"
    if not config.next.resolve_recording_enabled():
        return "config_disabled"
    if _analytics_capture_disabled():
        return "env_kill_switch"
    if config.analytics_opted_out:
        return "analytics_disabled"
    capture = config.analytics_capture
    if not feature_enabled_for({"cli_commands": capture.cli_commands}, "cli_commands", "ll-next"):
        return "command_not_captured"
    if not has_offers:
        return "nothing_to_record"
    return None


# --------------------------------------------------------------------------------- results


@dataclass(frozen=True)
class RecordingStatus:
    """Envelope ``recording`` object: ``recorded`` | ``disabled`` | ``unavailable`` + reason."""

    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason}


@dataclass(frozen=True)
class RecordingResult:
    """Outcome of :func:`record_shown`; ``rec_ids`` is non-empty only for a committed batch."""

    recording: RecordingStatus
    rec_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceWriteResult:
    """Outcome of :func:`record_accepted`.

    ``status``: ``accepted`` | ``already_accepted`` | ``unknown`` (absent in this project) |
    ``unavailable`` (schema/storage/remote/offer failure, ``reason`` set). ``offer`` and
    ``accepted_at`` are present for the first two.
    """

    status: str
    reason: str | None = None
    offer: RecommendationEventRow | None = None
    accepted_at: str | None = None


@dataclass(frozen=True)
class FeedbackResult:
    """A completed lookup: ``found`` with ``state`` ``accepted``/``unknown``, or not found.

    ``unknown`` means *offer found, acceptance unknown*. An absent (or foreign-project) identity
    is ``found=False``, ``state=None``, ``reason='rec_id_not_found'`` -- no third state name.
    """

    found: bool
    state: str | None
    offer: RecommendationEventRow | None
    accepted_at: str | None
    read_observed_at: datetime | None
    provenance: Mapping[str, str] | None
    reason: str | None


@dataclass(frozen=True)
class FeedbackUnavailable:
    """Storage/schema/remote/offer failure (exit 2); never a lookup state."""

    reason: str
    read_observed_at: datetime | None = None
    provenance: Mapping[str, str] | None = None


# ----------------------------------------------------------------------- offer validation


def offer_problem(row: RecommendationEventRow) -> str | None:
    """Why a stored offer cannot be trusted, or ``None``.

    ``unsupported_action_spec``: a well-formed payload naming an unregistered variant (only that
    identity is affected). ``malformed_offer``: a recognized variant (or no usable discriminator)
    with an invalid payload or ``requested_types``. Validation checks the registered shape and
    scope only, never live executable equivalence, and never recomputes the fingerprint.
    """
    try:
        data = json.loads(row.action_spec)
    except (ValueError, RecursionError):
        return "malformed_offer"
    if not isinstance(data, Mapping) or not isinstance(data.get("variant"), str):
        return "malformed_offer"
    try:
        spec_from_dict(data)
    except UnknownVariantError:
        return "unsupported_action_spec"
    except ActionSpecError:
        return "malformed_offer"
    try:
        requested = json.loads(row.requested_types)
    except (ValueError, RecursionError):
        return "malformed_offer"
    if not isinstance(requested, list) or not all(isinstance(t, str) for t in requested):
        return "malformed_offer"
    return None


def _pair(
    rows: Sequence[RecommendationEventRow],
) -> tuple[RecommendationEventRow | None, RecommendationEventRow | None]:
    shown = next((r for r in rows if r.kind == "shown"), None)
    accepted = next((r for r in rows if r.kind == "accepted_explicit"), None)
    return shown, accepted


def _pair_problem(
    shown: RecommendationEventRow | None, accepted: RecommendationEventRow | None
) -> str | None:
    """Storage-failure reason for an inconsistent shown/acknowledgement pair, else ``None``."""
    if shown is None:
        return "inconsistent_acknowledgement" if accepted is not None else None
    if accepted is None:
        return None
    for column in _COPIED_COLUMNS:
        if getattr(shown, column) != getattr(accepted, column):
            return "inconsistent_acknowledgement"
    return None


# --------------------------------------------------------------------------- shown rows


def build_shown_rows(
    offers: Sequence[Candidate],
    *,
    project_key: str,
    invocation_id: str,
    as_of: datetime,
    ts: datetime,
    requested_top: int | None,
    requested_types: Sequence[str],
) -> list[RecommendationEventRow]:
    """One ``shown`` row per offered recommendation, each with a fresh ``rec_id``/``event_id``.

    ``rank`` is the 1-based position in this invocation's output. The typed ``action_spec`` is
    serialized losslessly (canonical JSON of ``spec_to_dict``); fingerprint equality with an
    earlier offer never reuses an identity.
    """
    types_json = json.dumps(list(requested_types), ensure_ascii=False)
    return [
        RecommendationEventRow(
            event_id=str(uuid.uuid4()),
            rec_id=str(uuid.uuid4()),
            kind="shown",
            ts=format_instant(ts),
            project_key=project_key,
            session_id=None,
            invocation_id=invocation_id,
            as_of=format_instant(as_of),
            rank=rank,
            action_type=offer.action_type,
            action_key=offer.action_key,
            action_fingerprint=offer.action_fingerprint,
            target=offer.target,
            target_key=offer.target_key,
            action_spec=_canonical_spec_json(offer.action_spec),
            requested_top=requested_top,
            requested_types=types_json,
        )
        for rank, offer in enumerate(offers, start=1)
    ]


def _canonical_spec_json(spec: ActionSpec) -> str:
    return json.dumps(spec_to_dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_values(row: RecommendationEventRow) -> dict[str, Any]:
    return {column: getattr(row, column) for column in RECOMMENDATION_EVENT_COLUMNS}


# ------------------------------------------------------------------------ write plumbing


def _preflight_reason(target: HistoryTarget, now: Callable[[], datetime]) -> str | None:
    """``None`` when the existing local store is write-ready, else a stable reason code.

    Uses the strict read-only seam (no creation, migration or pragma); the in-transaction
    recheck is authoritative for a preflight/write race.
    """
    snapshot = read_history_snapshot(
        target, as_of=now(), requests=[RecommendationSchemaProbe()], now=now
    )
    result = snapshot.results_by_request["recommendation_schema"]
    if result.availability == "unavailable":
        reason = result.reason or "write_failed"
        return "schema_not_ready" if reason in _NOT_READY_REASONS else "write_failed"
    status = result.schema_status
    if status is None or not status.write_ready:
        return "schema_not_ready"
    return None


class _NotReady(Exception):
    """The in-transaction schema recheck found the store unprepared."""


def _begin_write(target: LocalTarget) -> sqlite3.Connection:
    """Open the existing store writable, own row access and ``BEGIN IMMEDIATE``.

    Raises on any failure with the connection closed; on success the caller owns commit,
    rollback and close.
    """
    conn = connect_existing_writable(target, timeout=WRITE_BUSY_TIMEOUT_SECONDS)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        if not recommendation_schema_status(conn).write_ready:
            conn.execute("ROLLBACK")
            raise _NotReady
    except BaseException:
        _rollback(conn)
        conn.close()
        raise
    return conn


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _write_failure_reason(target: LocalTarget, exc: BaseException) -> str:
    if isinstance(exc, _NotReady):
        return "schema_not_ready"
    # A store removed between preflight and write is "not prepared", never recreated.
    if isinstance(exc, HistoryError) and not target.path.exists():
        return "schema_not_ready"
    return "write_failed"


def record_shown(
    offers: Sequence[Candidate],
    *,
    target: HistoryTarget,
    project_key: str,
    invocation_id: str,
    as_of: datetime,
    requested_top: int | None,
    requested_types: Sequence[str],
    now: Callable[[], datetime],
) -> RecordingResult:
    """Persist *offers* as ``shown`` rows in one atomic plain-``INSERT`` batch.

    *target* is the once-frozen absolute target (never re-resolved from the cwd). Any constraint
    or UUID collision rolls the whole batch back and reports ``unavailable(write_failed)`` with no
    usable IDs. ``shown.ts`` is stamped once for the attempt, separately from the feature-read
    *as_of*. A committed row means an offer was prepared for output, not that it was displayed.
    """
    if not offers:
        return RecordingResult(RecordingStatus("disabled", "nothing_to_record"))
    if isinstance(target, RemoteTarget):
        return RecordingResult(RecordingStatus("unavailable", "remote_unsupported_v1"))
    try:
        reason = _preflight_reason(target, now)
    except Exception:  # best-effort recording: a probe fault never changes the recommendations
        reason = "write_failed"
    if reason is not None:
        return RecordingResult(RecordingStatus("unavailable", reason))
    rows = build_shown_rows(
        offers,
        project_key=project_key,
        invocation_id=invocation_id,
        as_of=as_of,
        ts=now(),
        requested_top=requested_top,
        requested_types=requested_types,
    )
    conn: sqlite3.Connection | None = None
    try:
        conn = _begin_write(target)
        try:
            insert_shown_recommendation_events(conn, [_row_values(r) for r in rows])
            conn.execute("COMMIT")
        except BaseException:
            _rollback(conn)
            raise
    except Exception as exc:
        return RecordingResult(RecordingStatus("unavailable", _write_failure_reason(target, exc)))
    finally:
        if conn is not None:
            conn.close()
    return RecordingResult(RecordingStatus("recorded"), tuple(r.rec_id for r in rows))


def _read_pair(
    conn: sqlite3.Connection, rec_id: str, project_key: str
) -> tuple[RecommendationEventRow | None, RecommendationEventRow | None] | str:
    """The project's shown/acknowledgement rows for *rec_id*, or a storage-failure reason."""
    decoded: list[RecommendationEventRow] = []
    for raw in conn.execute(RECOMMENDATION_LOOKUP_SQL, (rec_id, project_key)).fetchall():
        row = decode_recommendation_row(raw)
        if row is None:
            return "malformed_event"
        decoded.append(row)
    return _pair(decoded)


def record_accepted(
    rec_id: str,
    *,
    target: HistoryTarget,
    project_key: str,
    invocation_id: str,
    now: Callable[[], datetime],
) -> AcceptanceWriteResult:
    """Explicitly acknowledge the stored offer *rec_id* (already canonical) in this project.

    One ``BEGIN IMMEDIATE`` transaction: require a valid shown row owned by *project_key*, insert
    an acknowledgement copied from it with the targeted ``ON CONFLICT ... DO NOTHING`` and read
    the pair back before commit. A replay returns the original stored acknowledgement time.
    Unknown/foreign IDs are ``unknown``; a missing or inconsistent acknowledgement is a storage
    failure, never success. Independent of automatic-capture gates but needs real storage.
    """
    if isinstance(target, RemoteTarget):
        return AcceptanceWriteResult("unavailable", "remote_unsupported_v1")
    try:
        reason = _preflight_reason(target, now)
    except Exception:
        reason = "write_failed"
    if reason is not None:
        return AcceptanceWriteResult("unavailable", reason)
    ts = format_instant(now())
    conn: sqlite3.Connection | None = None
    try:
        conn = _begin_write(target)
        try:
            outcome = _accept_in_transaction(conn, rec_id, project_key, invocation_id, ts)
        except BaseException:
            _rollback(conn)
            raise
        if outcome.status in {"accepted", "already_accepted"}:
            conn.execute("COMMIT")
        else:
            _rollback(conn)
        return outcome
    except Exception as exc:
        return AcceptanceWriteResult("unavailable", _write_failure_reason(target, exc))
    finally:
        if conn is not None:
            conn.close()


def _accept_in_transaction(
    conn: sqlite3.Connection, rec_id: str, project_key: str, invocation_id: str, ts: str
) -> AcceptanceWriteResult:
    before = _read_pair(conn, rec_id, project_key)
    if isinstance(before, str):
        return AcceptanceWriteResult("unavailable", before)
    shown, existing = before
    if shown is None:
        if existing is not None:  # an acknowledgement with no offer behind it
            return AcceptanceWriteResult("unavailable", "inconsistent_acknowledgement")
        return AcceptanceWriteResult("unknown")
    problem = offer_problem(shown)
    if problem is not None:
        return AcceptanceWriteResult("unavailable", problem)
    acknowledge_recommendation_event(
        conn,
        rec_id=rec_id,
        project_key=project_key,
        event_id=str(uuid.uuid4()),
        ts=ts,
        invocation_id=invocation_id,
    )
    after = _read_pair(conn, rec_id, project_key)
    if isinstance(after, str):
        return AcceptanceWriteResult("unavailable", after)
    shown_after, accepted = after
    if shown_after is None or accepted is None:
        return AcceptanceWriteResult("unavailable", "acknowledgement_missing")
    if shown_after != shown:
        return AcceptanceWriteResult("unavailable", "inconsistent_acknowledgement")
    bad = _pair_problem(shown_after, accepted)
    if bad is not None:
        return AcceptanceWriteResult("unavailable", bad)
    status = "already_accepted" if existing is not None else "accepted"
    return AcceptanceWriteResult(status, None, shown_after, accepted.ts)


# --------------------------------------------------------------------------------- feedback


def lookup_feedback(
    snapshot: HistorySnapshot,
    rec_id: str,
    *,
    provenance: Mapping[str, str] | None = None,
) -> FeedbackResult | FeedbackUnavailable:
    """Pure feedback verdict from a snapshot holding a ``recommendation_lookup`` result.

    A shown row with no acknowledgement is ``unknown`` (found, acceptance unknown); with a
    consistent acknowledgement it is ``accepted`` at the acknowledgement's stored time. An
    identity absent from the project (including a foreign project's) is ``found=False`` with
    ``rec_id_not_found``. Query failure, an unsupported or malformed offer, or an inconsistent
    pair is :class:`FeedbackUnavailable`, never ``unknown`` or ``accepted``.
    """
    observed = snapshot.read_observed_at
    result = snapshot.results_by_request.get(RecommendationLookup.kind)
    if result is None or result.availability == "unavailable":
        reason = (result.reason if result is not None else None) or "lookup_unavailable"
        if reason in _NOT_READY_REASONS:  # same remedy as recording/accept: `ll-session migrate`
            reason = "schema_not_ready"
        return FeedbackUnavailable(reason, observed, provenance)
    rows = [r for r in result.rows if isinstance(r, RecommendationEventRow)]
    shown, accepted = _pair(rows)
    if shown is None:
        if accepted is not None:
            return FeedbackUnavailable("inconsistent_acknowledgement", observed, provenance)
        return FeedbackResult(False, None, None, None, observed, provenance, "rec_id_not_found")
    problem = offer_problem(shown) or _pair_problem(shown, accepted)
    if problem is not None:
        return FeedbackUnavailable(problem, observed, provenance)
    state = "accepted" if accepted is not None else "unknown"
    return FeedbackResult(
        True,
        state,
        shown,
        accepted.ts if accepted is not None else None,
        observed,
        provenance,
        None,
    )

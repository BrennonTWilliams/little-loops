"""Acquisition accounting and completion publication for the source refresh paths (ENH-3745).

Glue between ``lifecycle``'s two source refresh writers and the
:mod:`~little_loops.session_store.usage_source_state` storage seam. It never parses a
source into history rows, prices usage or invents continuity:

* :func:`account_physical_lines` classifies every complete physical line of a native
  source (valid record, blank/benign, JSON failure, strict-UTF-8 failure, non-object)
  *before* any parser skips it, so rejected input cannot vanish. Rejected bytes are never
  retained, logged or placed in an exception.
* :func:`finalize_source_refresh` runs in the refresh's own ``BEGIN IMMEDIATE`` transaction:
  it accounts the acquisition, records durable pending/failure obligations and, only when
  acquisition coverage is zero-origin (or verified) and ENH-3744's correspondence proof
  read back from the *publishing connection* is clean, publishes semantic completion.
* :func:`record_failure_only` persists a content-free diagnostic in a *separate* guarded
  transaction after the ingestion transaction rolled back (sanitizer refusal, decode
  failure), compare-and-swapping against the failed attempt's captured head revision.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from little_loops.session_store.usage_proof_scope import UsageProofLimit, inspect_retained_source
from little_loops.session_store.usage_source_state import (
    AcquisitionBoundary,
    AcquisitionWitness,
    CompletionDependency,
    ConsumedRange,
    DerivedBoundary,
    HeadState,
    SourceDeriveCompletion,
    SourcePending,
    SourceScope,
    UsageSourceConflict,
    acknowledge_source_pending,
    new_generation_id,
    pending_obligations,
    publish_source_completion,
    read_source_head,
    record_source_acquisition,
    record_source_pending,
    storage_available,
)

# Physical-line accounting/canonical acquisition evidence version, independent of
# ``_USAGE_DERIVE_VERSION`` and the rebuild fingerprint. A mismatch leaves acquisition
# evidence unprovable without certifying or mutating it.
USAGE_ACQUISITION_VERSION = "enh3745-v1"

REJECTION_REASONS = frozenset({"decode_failure", "json_failure", "non_object_record"})

# Obligations the owner may clear itself once ENH-3744's committed correspondence is clean
# over the whole retained source (retained derive-pending recovery needs no native file).
_REPROVABLE_KIND = "derive_gap"


@dataclass(frozen=True)
class RejectedRange:
    """One rejection class' first/last physical line and byte range (never the bytes)."""

    reason: str  # decode_failure | json_failure | non_object_record
    first_line_no: int
    last_line_no: int
    first_offset: int
    end_offset: int


@dataclass(frozen=True)
class PhysicalAccounting:
    """Complete-line accounting of ``[0, offset)`` plus any unterminated tail."""

    offset: int
    line_count: int
    rejected: tuple[RejectedRange, ...] = ()
    partial_tail: tuple[int, int] | None = None  # (start, end) of an unterminated tail

    @property
    def clean(self) -> bool:
        return not self.rejected and self.partial_tail is None


def account_physical_lines(path: Path, *, limit: int | None = None) -> PhysicalAccounting:
    """Classify every complete physical line of *path* (up to byte *limit* when given).

    A line is a record, a blank/benign line (whitespace only), or rejected as
    ``decode_failure`` (invalid UTF-8), ``json_failure`` or ``non_object_record``.
    Counting starts at offset zero so coverage is zero-origin by construction.
    """
    ranges: dict[str, list[int]] = {}
    offset = 0
    line_no = 0
    partial: tuple[int, int] | None = None
    with path.open("rb") as handle:
        while True:
            raw = handle.readline()
            if not raw:
                break
            if limit is not None and offset + len(raw) > limit:
                break
            if not raw.endswith(b"\n"):
                partial = (offset, offset + len(raw))
                break
            line_no += 1
            end = offset + len(raw)
            reason = _classify(raw)
            if reason is not None:
                found = ranges.get(reason)
                if found is None:
                    ranges[reason] = [line_no, line_no, offset, end]
                else:
                    found[1], found[3] = line_no, end
            offset = end
    rejected = tuple(
        RejectedRange(reason, first, last, start, stop)
        for reason, (first, last, start, stop) in sorted(ranges.items())
    )
    return PhysicalAccounting(offset, line_no, rejected, partial)


def _classify(raw: bytes) -> str | None:
    if not raw.strip():
        return None  # blank line: recognized benign
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "decode_failure"
    try:
        record = json.loads(text)
    except (ValueError, RecursionError):
        return "json_failure"
    return None if isinstance(record, dict) else "non_object_record"


def sticky_rejection_lines(conn: sqlite3.Connection, source_path: str) -> frozenset[int]:
    """Endpoint lines of unresolved rejection ranges (the only positions a repair may add).

    Interior lines of a multi-line range are unknown, so they are never exempted from the
    retained-prefix requirement: a missing interior position stays uncheckable.
    """
    lines: set[int] = set()
    for ob in pending_obligations(conn, source_path):
        if ob.kind == "acquisition_failure" and ob.reason in REJECTION_REASONS:
            lines.update(n for n in (ob.first_line_no, ob.last_line_no) if n is not None)
    return frozenset(lines)


def verify_claude_prefix(
    conn: sqlite3.Connection,
    path: Path,
    upto_offset: int,
    *,
    retained_before: frozenset[int] | None = None,
    prior_line_no: int = 0,
    exempt_lines: frozenset[int] = frozenset(),
) -> bool:
    """Whether every complete line of ``path[0:upto_offset]`` canonically matches retained raw.

    Full re-acquisition from offset zero compared, line by line, against the retained rows
    (legacy plaintext and redacted rows certify through the same canonical form). False for
    any missing/pruned position, extra retained row, payload difference or undecodable
    stored payload: an uncheckable prefix is never certified. When a re-acquisition may have
    re-inserted missing rows, *retained_before* (the rows retained before it) must already
    contain every position up to *prior_line_no* other than *exempt_lines* -- a position
    restored from the native source proves nothing about the retained prior prefix. Rejected lines have no row by
    construction and are accounted separately. Device/inode/size/mtime/tail alone prove
    nothing here.
    """
    from little_loops.pii import HistorySanitizationError
    from little_loops.session_store.usage_refresh import (
        _canonical_payload,
        _payload_equal,
        _stored_payloads,
    )

    expected: dict[int, tuple[str, dict[str, object]]] = {}
    line_no = 0
    offset = 0
    try:
        with path.open("rb") as handle:
            while offset < upto_offset:
                raw = handle.readline()
                if not raw or not raw.endswith(b"\n") or offset + len(raw) > upto_offset:
                    return False
                offset += len(raw)
                line_no += 1
                if _classify(raw) is not None or not raw.strip():
                    continue
                record = json.loads(raw)
                event_type = str(record.get("type") or "unknown")
                expected[line_no] = (
                    event_type,
                    _canonical_payload(record, host="claude-code", event_type=event_type),
                )
        if retained_before is not None and any(
            n <= prior_line_no and n not in retained_before and n not in exempt_lines
            for n in expected
        ):
            return False
        rows = conn.execute(
            "SELECT line_no, event_type, CAST(raw_line AS BLOB), CAST(parsed_json AS BLOB), "
            "typeof(raw_line), typeof(parsed_json), host, host_basis FROM raw_events "
            "WHERE source_path = ? AND line_no <= ? ORDER BY line_no",
            (str(path), line_no),
        ).fetchall()
        if len(rows) != len(expected):
            return False
        for row in rows:
            want = expected.get(row[0])
            if want is None or row[1] != want[0] or row[7] != "handle":
                return False
            for column in _stored_payloads(row[2], row[4], row[3], row[5]):
                if not _payload_equal(
                    _canonical_payload(column, host=str(row[6]), event_type=str(row[1])), want[1]
                ):
                    return False
    except (OSError, HistorySanitizationError, ValueError, RecursionError):
        return False
    return True


@dataclass(frozen=True)
class Attempt:
    """What a refresh captured before it mutated anything (inside its write lock)."""

    scope: SourceScope
    head_revision: int | None


def has_sticky_rejection(conn: sqlite3.Connection, source_path: str) -> bool:
    """Whether *source_path* carries an unresolved rejected-line failure needing re-acquisition."""
    return any(
        ob.kind == "acquisition_failure" and ob.reason in REJECTION_REASONS
        for ob in pending_obligations(conn, source_path)
    )


def begin_attempt(
    conn: sqlite3.Connection,
    source_path: str,
    derive_version: str,
    *,
    host: str | None = None,
    session_id: str | None = None,
) -> Attempt | None:
    """Capture the head revision and scope; None when the source-state tables are absent."""
    if not storage_available(conn):
        return None
    head = read_source_head(conn, source_path)
    generation = head.scope.generation_id if head is not None else new_generation_id()
    return Attempt(
        SourceScope(
            source_path,
            generation,
            derive_version,
            host or (head.scope.host if head else None),
            session_id or (head.scope.session_id if head else None),
        ),
        head.revision if head is not None else None,
    )


def _failure_pending(scope: SourceScope, rejected: RejectedRange) -> SourcePending:
    return SourcePending(
        scope=scope,
        kind="acquisition_failure",
        reason=rejected.reason,
        range_kind="bounded",
        first_line_no=rejected.first_line_no,
        last_line_no=rejected.last_line_no,
        first_offset=rejected.first_offset,
        end_offset=rejected.end_offset,
    )


def record_rejections(
    conn: sqlite3.Connection, attempt: Attempt, accounting: PhysicalAccounting
) -> bool:
    """Record every rejected range as durable, content-free failure evidence in *conn*'s txn."""
    if not accounting.rejected:
        return False
    head = read_source_head(conn, attempt.scope.source_path)
    rev = head.revision if head is not None else attempt.head_revision
    for rejected in accounting.rejected:
        rev = record_source_pending(
            conn, _failure_pending(attempt.scope, rejected), expected_head_revision=rev
        )
    return True


def record_failure_only(
    connect: Callable[[], sqlite3.Connection],
    attempt: Attempt | None,
    *,
    reason: str,
    refusal_code: str | None = None,
    first_line_no: int | None = None,
    first_offset: int | None = None,
) -> bool:
    """Persist a content-free failure in its own guarded transaction; True when written.

    Called only after the failed ingestion transaction has fully rolled back. The write
    compares against the attempt's captured head revision, so a concurrent or newer
    successful refresh invalidates the comparison and the delayed failure is dropped
    rather than tainting newer state. Writes failure evidence only: no completion, no
    cursor, no checkpoint. Any storage error returns False (the caller keeps its
    rollback and surfaces its original, bounded error).
    """
    if attempt is None:
        return False
    pending = SourcePending(
        scope=attempt.scope,
        kind="acquisition_failure",
        reason=reason,
        range_kind="bounded"
        if first_line_no is not None or first_offset is not None
        else "whole_source",
        refusal_code=refusal_code,
        first_line_no=first_line_no,
        last_line_no=first_line_no,
        first_offset=first_offset,
        end_offset=first_offset,
    )
    try:
        conn = connect()
    except Exception:
        return False
    try:
        conn.execute("BEGIN IMMEDIATE")
        record_source_pending(conn, pending, expected_head_revision=attempt.head_revision)
        conn.commit()
        return True
    except UsageSourceConflict:
        conn.rollback()
        return False
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def record_held_pending(
    conn: sqlite3.Connection,
    derive_version: str,
    held: tuple[tuple[str, int, int], ...],
) -> None:
    """Record held-source appends the replay writer skipped; they stay pending (ENH-3770)."""
    for source, first, last in held:
        head = read_source_head(conn, source)
        scope = SourceScope(
            source,
            head.scope.generation_id if head is not None else new_generation_id(),
            derive_version,
            head.scope.host if head else None,
            head.scope.session_id if head else None,
        )
        record_source_pending(
            conn,
            SourcePending(
                scope=scope,
                kind="derive_gap",
                reason="held_source_skipped",
                range_kind="bounded",
                first_raw_id=first,
                last_raw_id=last,
            ),
            expected_head_revision=head.revision if head is not None else None,
        )


_GAP_REASONS = {
    "evidence_limited": "usage_proof_limit",
    "overlap_ambiguous": "held_source_skipped",
}


def _outcome_reason(reasons: set[str]) -> str:
    """Finite pending reason for the bounded replay reasons a source accrued."""
    for reason, mapped in _GAP_REASONS.items():
        if reason in reasons:
            return mapped
    return "usage_proof_unprovable"


def _pending_covered(conn: sqlite3.Connection, pending: SourcePending) -> bool:
    """Whether an identical, at-least-as-wide obligation already exists (no churn to poll it)."""
    scope = pending.scope
    row = conn.execute(
        "SELECT range_kind, first_raw_id, last_raw_id, raw_cache_pending, usage_pending "
        "FROM usage_source_pending WHERE source_path = ? AND generation_id = ? "
        "AND derive_version = ? AND kind = ? AND reason = ? "
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
    if row is None:
        return False
    range_kind, first, last, cache, usage = row
    if pending.raw_cache_pending and not cache:
        return False
    if pending.usage_pending and not usage:
        return False
    if range_kind == "whole_source":
        return True
    if pending.range_kind == "whole_source":
        return False
    if first is None or last is None or pending.first_raw_id is None or pending.last_raw_id is None:
        return False
    return first <= pending.first_raw_id and pending.last_raw_id <= last


def record_replay_outcomes(
    conn: sqlite3.Connection,
    derive_version: str,
    outcomes: Iterable[Any],
    *,
    attempt: Attempt | None = None,
) -> None:
    """Persist every scanned scope a guarded replay left incomplete (ENH-3770).

    Runs in the caller's write transaction, before the scan high-water is published, so
    the unresolved work and the advance commit or roll back together. An identical
    obligation that already covers the range is not merged again, so repeated identical
    failures neither churn revisions nor lose their retry range. A source without a head
    uses the refresh attempt's generation when it is that source, else a fresh one.
    """
    if not storage_available(conn):
        return
    for outcome in sorted(outcomes, key=lambda o: (o.source_path, o.kind)):
        source = outcome.source_path
        head = read_source_head(conn, source)
        if head is not None:
            generation = head.scope.generation_id
            host, session = head.scope.host, head.scope.session_id
        elif attempt is not None and attempt.scope.source_path == source:
            generation = attempt.scope.generation_id
            host, session = attempt.scope.host, attempt.scope.session_id
        else:
            generation, host, session = new_generation_id(), None, None
        scope = SourceScope(source, generation, derive_version, host, session)
        bounded = outcome.first_raw_id is not None and outcome.last_raw_id is not None
        base = {
            "scope": scope,
            "range_kind": "bounded" if bounded else "whole_source",
            "first_raw_id": outcome.first_raw_id if bounded else None,
            "last_raw_id": outcome.last_raw_id if bounded else None,
        }
        if outcome.kind == "native_conflict":
            pendings = [
                SourcePending(
                    kind="native_conflict",
                    reason="native_conflict",
                    affected_usage_event_id=affected,
                    **base,  # type: ignore[arg-type]
                )
                for affected in (sorted(outcome.affected) or [None])
            ]
        else:
            pendings = [
                SourcePending(
                    kind="derive_gap",
                    reason=_outcome_reason(outcome.reasons),
                    **base,  # type: ignore[arg-type]
                )
            ]
        for pending in pendings:
            if _pending_covered(conn, pending):
                continue
            current = read_source_head(conn, source)
            record_source_pending(
                conn, pending, expected_head_revision=current.revision if current else None
            )


# Obligations whose usage component a clean guarded replay plus clean retained proof resolves.
# Acquisition failures, partial tails and "acquisition_unprovable" gaps are resolved by
# re-acquisition, and a native conflict is never resolved by replaying it.
RETRYABLE_USAGE_REASONS = frozenset(
    {
        "usage_proof_unprovable",
        "usage_proof_limit",
        "usage_derive_gap",
        "held_source_skipped",
        "codex_catchup",
        "rebuild",
        "parser_refresh",
        "reconcile",
        "derive_pending",
    }
)


def stage_raw_only_source(
    conn: sqlite3.Connection,
    attempt: Attempt | None,
    *,
    accounting: PhysicalAccounting,
    witness: AcquisitionWitness,
    coverage_proved: bool,
) -> bool:
    """Stage a verified raw-only acquisition and its usage-pending handoff (ENH-3770).

    Raw ingestion committed on its own proved canonical coverage, native identity and source
    stability, so it records the acquisition head and one durable whole-source usage-pending
    obligation. Acquisition alone never publishes completion: a later retained-only derive
    resolves the obligation from committed rows (no original-file stat or reparse) and
    publishes from post-write proof. Returns whether a head was staged.
    """
    staged = stage_source_acquisition(
        conn, attempt, accounting=accounting, witness=witness, coverage_proved=coverage_proved
    )
    if staged is None:
        return False
    pending = SourcePending(staged.scope, "derive_gap", "derive_pending", "whole_source")
    if not _pending_covered(conn, pending):
        record_source_pending(conn, pending, expected_head_revision=staged.head_revision)
    return True


def retained_proof_is_clean(conn: sqlite3.Connection, source_path: str) -> bool:
    """Whether the post-write retained proof leaves *source_path* with nothing missing.

    ENH-3744 correspondence read back from the connection's committed rows; a proof limit
    or an unprovable candidate is not clean.
    """
    return _proof_outcome(conn, source_path)[0] is None


def publish_retained_completion(conn: sqlite3.Connection, source_path: str) -> bool:
    """Publish semantic completion from retained proof against committed acquisition.

    Only when the head already carries a verified acquisition (never manufactured from the
    original file, which is not reread), no usage-component obligation of any generation
    remains, and the post-write retained proof is clean. The boundary is the acquisition the
    head already certified, so completion cannot reach past it.
    """
    head = read_source_head(conn, source_path)
    if (
        head is None
        or head.acquisition_version != USAGE_ACQUISITION_VERSION
        or head.acquired_offset is None
        or head.acquired_line_no is None
    ):
        return False
    if any(ob.usage_pending for ob in pending_obligations(conn, source_path)):
        return False
    reason, _bounds, deps = _proof_outcome(conn, source_path)
    if reason is not None:
        return False
    max_raw_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM raw_events WHERE source_path = ?", (source_path,)
    ).fetchone()[0]
    publish_source_completion(
        conn,
        SourceDeriveCompletion(
            status="complete",
            reason=None,
            basis="semantic",
            scope=head.scope,
            boundary=DerivedBoundary(
                head.scope,
                head.acquisition_version,
                head.acquired_offset,
                head.acquired_line_no,
                max_raw_id,
                None,
            ),
        ),
        deps,
        expected_head_revision=head.revision,
    )
    return True


def resolve_usage_obligations(conn: sqlite3.Connection, source_path: str) -> int:
    """Acknowledge the usage component of *source_path*'s resolved retryable obligations.

    Only after the post-write retained proof (ENH-3744 correspondence over the committed
    rows) is clean, and only for obligations in the head's current generation/derive
    version; every acknowledgement is compare-and-swap on both captured revisions, and the
    ``raw_cache`` component of a parser refresh is never touched. Returns how many
    obligations changed. Count-only success never resolves pending work.
    """
    head = read_source_head(conn, source_path)
    if head is None:
        return 0
    reason, _bounds, _deps = _proof_outcome(conn, source_path)
    if reason is not None:
        return 0
    resolved = 0
    for ob in pending_obligations(conn, source_path):
        if (
            ob.kind not in {"derive_gap", "refresh"}
            or ob.reason not in RETRYABLE_USAGE_REASONS
            or not ob.usage_pending
            or ob.obligation_id is None
        ):
            continue
        current = read_source_head(conn, source_path)
        row = conn.execute(
            "SELECT revision FROM usage_source_pending WHERE obligation_id = ?",
            (ob.obligation_id,),
        ).fetchone()
        if current is None or row is None:
            continue
        if acknowledge_source_pending(
            conn,
            ob.obligation_id,
            ConsumedRange(ob.scope, full_scope=True),
            expected_head_revision=current.revision,
            expected_obligation_revision=row[0],
            components=frozenset({"usage"}),
        ):
            resolved += 1
    if resolved:
        publish_retained_completion(conn, source_path)
    return resolved


def resolve_cache_obligations(conn: sqlite3.Connection, source_path: str) -> int:
    """Acknowledge the ``raw_cache`` component of *source_path*'s parser-refresh obligations.

    Called only by a replay that has just consumed the whole retained source into the
    deterministic parser-derived caches, in the same transaction as those writes, and only
    for the head's current generation/derive version. The ``usage`` component is untouched
    and every acknowledgement is compare-and-swap on both captured revisions.
    """
    head = read_source_head(conn, source_path)
    if head is None:
        return 0
    resolved = 0
    for ob in pending_obligations(conn, source_path):
        if ob.kind != "refresh" or not ob.raw_cache_pending or ob.obligation_id is None:
            continue
        current = read_source_head(conn, source_path)
        row = conn.execute(
            "SELECT revision FROM usage_source_pending WHERE obligation_id = ?",
            (ob.obligation_id,),
        ).fetchone()
        if current is None or row is None:
            continue
        if acknowledge_source_pending(
            conn,
            ob.obligation_id,
            ConsumedRange(ob.scope, full_scope=True),
            expected_head_revision=current.revision,
            expected_obligation_revision=row[0],
            components=frozenset({"raw_cache"}),
        ):
            resolved += 1
    return resolved


def _proof_outcome(
    conn: sqlite3.Connection, source_path: str
) -> tuple[str | None, tuple[int, int] | None, tuple[CompletionDependency, ...]]:
    """``(blocking reason, raw bounds of missing work, dependencies)`` from committed rows.

    Reads back the publishing connection's actual rows through the shared bounded
    adapter; a planned insert is never representation. ``None`` reason means every
    retained candidate is represented, a recognized omission or an excluded channel.
    """
    try:
        proofs = inspect_retained_source(conn, source_path)
    except UsageProofLimit:
        return "usage_proof_limit", None, ()
    missing = [p for p in proofs if p.correspondence == "missing"]
    unprovable = [p for p in proofs if p.correspondence == "unprovable"]
    if unprovable:
        return "usage_proof_unprovable", None, ()
    if missing:
        ids = [p.raw_event_id for p in missing if p.raw_event_id is not None]
        bounds = (min(ids), max(ids)) if len(ids) == len(missing) and ids else None
        return "usage_derive_gap", bounds, ()
    deps: dict[str, CompletionDependency] = {}
    for proof in proofs:
        for obs_id in proof.matched_observation_ids:
            deps[f"obs:{obs_id}"] = CompletionDependency(
                f"obs:{obs_id}", "observation", usage_event_id=obs_id
            )
        for raw_id in proof.context_raw_event_ids:
            row = conn.execute(
                "SELECT source_path, line_no FROM raw_events WHERE id = ?", (raw_id,)
            ).fetchone()
            if row is None:
                continue
            other = read_source_head(conn, row[0])
            deps[f"ctx:{raw_id}"] = CompletionDependency(
                f"ctx:{raw_id}",
                "context",
                dependency_source_path=row[0],
                dependency_generation_id=other.scope.generation_id if other else None,
                dependency_derive_version=other.scope.derive_version if other else None,
                line_no=row[1],
                raw_event_id=raw_id,
            )
    return None, None, tuple(deps[key] for key in sorted(deps))


@dataclass(frozen=True)
class StagedAcquisition:
    """A verified acquisition already recorded in this transaction (ENH-3770).

    ``head_revision`` is the head revision the staging left behind. It proves acquisition
    only: staging never publishes semantic completion and grants no mutation authority.
    """

    scope: SourceScope
    boundary: AcquisitionBoundary
    witness: AcquisitionWitness
    head_revision: int


def _acquisition_recorded(
    head: HeadState | None,
    scope: SourceScope,
    boundary: AcquisitionBoundary,
    witness: AcquisitionWitness,
) -> bool:
    """Whether *head* already carries exactly this acquisition (so rewriting it is churn)."""
    if head is None:
        return False
    return (
        head.scope.generation_id == scope.generation_id
        and head.scope.derive_version == scope.derive_version
        and (scope.host is None or head.scope.host == scope.host)
        and (scope.session_id is None or head.scope.session_id == scope.session_id)
        and head.acquisition_version == boundary.acquisition_version
        and head.acquired_offset == boundary.offset
        and head.acquired_line_no == boundary.line_no
        and head.acquisition_witness == json.loads(witness.to_json())
    )


def stage_source_acquisition(
    conn: sqlite3.Connection,
    attempt: Attempt | None,
    *,
    accounting: PhysicalAccounting,
    witness: AcquisitionWitness,
    coverage_proved: bool,
) -> StagedAcquisition | None:
    """Record a verified, clean acquisition before reconciliation needs generation authority.

    Runs in the caller's write transaction and writes only the source head's acquisition
    fields through :func:`record_source_acquisition`. Returns ``None`` -- writing nothing --
    without an attempt, without proved zero-origin/verified coverage, or when the
    accounting has rejected lines or an unterminated tail: such an acquisition is not a
    verified scope. An identical acquisition already on the head is reused without another
    write, so an unchanged retry never churns the head revision.
    """
    if attempt is None or not coverage_proved or not accounting.clean:
        return None
    scope = attempt.scope
    boundary = AcquisitionBoundary(
        USAGE_ACQUISITION_VERSION, accounting.offset, accounting.line_count
    )
    head = read_source_head(conn, scope.source_path)
    if _acquisition_recorded(head, scope, boundary, witness):
        assert head is not None
        return StagedAcquisition(scope, boundary, witness, head.revision)
    revision = record_source_acquisition(
        conn,
        scope,
        boundary,
        witness,
        expected_head_revision=head.revision if head is not None else None,
    )
    return StagedAcquisition(scope, boundary, witness, revision)


@dataclass(frozen=True)
class FinalizeResult:
    """Truthful bounded outcome of one finalization (never carries source content)."""

    complete: bool
    reason: str | None = None


def finalize_source_refresh(
    conn: sqlite3.Connection,
    attempt: Attempt | None,
    *,
    accounting: PhysicalAccounting,
    witness: AcquisitionWitness,
    coverage_proved: bool,
    derive_status: str,
    derive_reason: str | None,
    held_skipped: tuple[tuple[str, int, int], ...],
    source_max_raw_id: int,
    now: str,
    ingest_from: int = 0,
    reacquired_from_zero: bool = False,
) -> FinalizeResult:
    """Account the acquisition and publish completion only when every condition holds.

    Must run inside the refresh's write transaction, after eligible usage writes executed.
    ``coverage_proved`` is True when acquisition began at offset zero or the retained prior
    prefix was fully re-verified; otherwise the older boundary is retained and the new
    completion stays pending. Obligations commit with the same transaction as the scan.
    """
    if attempt is None:
        return FinalizeResult(False, "storage_unavailable")
    scope = attempt.scope
    version = scope.derive_version
    # The refresh holds the write lock since its attempt began, so the head can only have
    # moved through this transaction's own writes (e.g. catch-up invalidation). The
    # attempt's captured revision exists for the separate failure-only transaction.
    current = read_source_head(conn, scope.source_path)
    expected = current.revision if current is not None else None
    if not coverage_proved and expected is None and accounting.clean and derive_status == "derived":
        # Nothing negative to report and no prior semantic tracking: leave the source on the
        # legacy public fallback rather than inventing an unprovable semantic head.
        record_held_pending(conn, version, held_skipped)
        return FinalizeResult(False, "acquisition_unprovable")
    if coverage_proved:
        boundary = AcquisitionBoundary(
            USAGE_ACQUISITION_VERSION, accounting.offset, accounting.line_count
        )
        # ENH-3770: an identical acquisition already on the head -- staged earlier in this
        # transaction or recorded by an unchanged retry -- is reused as is; the head is
        # rewritten only when the acquisition actually advanced.
        if _acquisition_recorded(current, scope, boundary, witness):
            assert current is not None
            rev = current.revision
        else:
            rev = record_source_acquisition(
                conn, scope, boundary, witness, expected_head_revision=expected
            )
    else:
        rev = record_source_pending(
            conn,
            SourcePending(scope, "derive_gap", "acquisition_unprovable"),
            expected_head_revision=expected,
        )
    for rejected in accounting.rejected:
        rev = record_source_pending(
            conn, _failure_pending(scope, rejected), expected_head_revision=rev
        )
    # A sanitizer refusal advanced nothing, so the prior cursor stayed valid: it clears only
    # when this refresh re-ingested the refused position under that same continuity.
    for ob in pending_obligations(conn, scope.source_path):
        if (
            ob.kind == "acquisition_failure"
            and ob.reason == "sanitization_refused"
            and ob.scope.generation_id == scope.generation_id
            and (ob.first_offset is None or ingest_from <= ob.first_offset < accounting.offset)
        ):
            rev = _ack(conn, ob.obligation_id, scope, rev, full=True)
    # An advanced decode/JSON/non-object gap clears only after full re-acquisition from offset
    # zero canonically matched the retained prior raw prefix (coverage_proved) AND the failed
    # range is repaired (no rejected line of that class remains). An uncheckable or pruned
    # prefix keeps the marker; matching tail bytes or device/inode alone prove nothing.
    if coverage_proved and reacquired_from_zero:
        still = {r.reason for r in accounting.rejected}
        for ob in pending_obligations(conn, scope.source_path):
            if (
                ob.kind == "acquisition_failure"
                and ob.reason in REJECTION_REASONS
                and ob.reason not in still
                and ob.scope.generation_id == scope.generation_id
            ):
                rev = _ack(conn, ob.obligation_id, scope, rev, full=True)
    tail_obligations = [
        ob for ob in pending_obligations(conn, scope.source_path) if ob.kind == "partial_tail"
    ]
    if accounting.partial_tail is not None:
        start, end = accounting.partial_tail
        rev = record_source_pending(
            conn,
            SourcePending(
                scope,
                "partial_tail",
                "partial_tail",
                "bounded",
                first_offset=start,
                end_offset=end,
            ),
            expected_head_revision=rev,
        )
    else:
        for ob in tail_obligations:
            rev = _ack(conn, ob.obligation_id, scope, rev, full=True)
    if derive_status != "derived":
        record_source_pending(
            conn,
            SourcePending(scope, "derive_gap", "derive_pending"),
            expected_head_revision=rev,
        )
        record_held_pending(conn, version, held_skipped)
        return FinalizeResult(False, derive_reason or "derive_pending")
    record_held_pending(conn, version, held_skipped)
    head = read_source_head(conn, scope.source_path)
    assert head is not None
    rev = head.revision
    if not accounting.clean:
        return FinalizeResult(
            False, "acquisition_failure" if accounting.rejected else "partial_tail"
        )
    if not coverage_proved:
        return FinalizeResult(False, "acquisition_unprovable")
    reason, bounds, deps = _proof_outcome(conn, scope.source_path)
    if reason is not None:
        rev = record_source_pending(
            conn,
            SourcePending(
                scope,
                "derive_gap",
                reason,
                "bounded" if bounds is not None else "whole_source",
                first_raw_id=bounds[0] if bounds else None,
                last_raw_id=bounds[1] if bounds else None,
            ),
            expected_head_revision=rev,
        )
        return FinalizeResult(False, reason)
    # Correspondence is clean over the whole retained source: re-provable derive-pending
    # obligations are resolved by committed proof, not by time or later appends.
    for ob in pending_obligations(conn, scope.source_path):
        if ob.kind == _REPROVABLE_KIND and ob.scope.generation_id == scope.generation_id:
            current = read_source_head(conn, scope.source_path)
            assert current is not None
            row = conn.execute(
                "SELECT revision FROM usage_source_pending WHERE obligation_id = ?",
                (ob.obligation_id,),
            ).fetchone()
            if row is None:
                continue
            ok = acknowledge_source_pending(
                conn,
                str(ob.obligation_id),
                ConsumedRange(scope, full_scope=True),
                expected_head_revision=current.revision,
                expected_obligation_revision=row[0],
                components=frozenset({"usage", "raw_cache"})
                if ob.raw_cache_pending
                else frozenset({"usage"}),
            )
            del ok
    head = read_source_head(conn, scope.source_path)
    assert head is not None
    if any(ob.usage_pending for ob in pending_obligations(conn, scope.source_path)):
        return FinalizeResult(False, "derive_pending")
    publish_source_completion(
        conn,
        SourceDeriveCompletion(
            status="complete",
            reason=None,
            basis="semantic",
            scope=scope,
            boundary=DerivedBoundary(
                scope,
                USAGE_ACQUISITION_VERSION,
                accounting.offset,
                accounting.line_count,
                source_max_raw_id,
                now,
            ),
        ),
        deps,
        expected_head_revision=head.revision,
    )
    return FinalizeResult(True)


def _ack(
    conn: sqlite3.Connection, obligation_id: str | None, scope: SourceScope, rev: int, *, full: bool
) -> int:
    if obligation_id is None:
        return rev
    row = conn.execute(
        "SELECT revision FROM usage_source_pending WHERE obligation_id = ?", (obligation_id,)
    ).fetchone()
    if row is None:
        return rev
    acknowledge_source_pending(
        conn,
        obligation_id,
        ConsumedRange(scope, full_scope=full),
        expected_head_revision=rev,
        expected_obligation_revision=row[0],
        components=frozenset({"usage", "raw_cache"}),
    )
    head = read_source_head(conn, scope.source_path)
    return head.revision if head is not None else rev

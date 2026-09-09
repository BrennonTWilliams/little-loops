"""Persisted queue-entry store for ``ll-queue`` (FEAT-2682).

Schema: ``{id, action: ActionSpec, enqueuedAt, priority, status, result}``,
persisted to a dedicated ``.ll/queue.db`` sqlite database. Modeled directly on
:mod:`little_loops.session_store`'s migration/connect/ensure_db shape (see
that module's docstring for the concurrency rationale) — this module copies
the same ``_configure_connection``/``_apply_migrations``/``ensure_db``/
``connect`` bodies rather than sharing them, matching every other sqlite
consumer in this codebase (no parameterized/shared version exists to import).

Priority ordering replicates :class:`~little_loops.parallel.types.QueuedIssue`'s
``(priority, timestamp)`` tuple comparator (lower priority int = higher
precedence, P0=0 .. P5=5; ties broken FIFO by ``enqueued_at``) via a plain
``ORDER BY priority ASC, enqueued_at ASC`` — the class itself isn't reusable
here since it's typed concretely against ``IssueInfo``.

This module owns persistence and CRUD only (add/list/get/remove). Dequeuing
and executing entries is FEAT-2683's worker loop; the ``ll-loop queue``
PID-liveness marker mechanism is a distinct, non-overlapping surface for FSM
lock contention, preserved unchanged as a compat shim by FEAT-2684 rather
than migrated into this store.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.runner_spec import ActionSpec, RunnerType, scope_runner_error

__all__ = [
    "DEFAULT_DB_PATH",
    "QueueEntry",
    "AmbiguousEntryIdError",
    "PRIORITY_TIERS",
    "QUEUE_STATUSES",
    "QUEUE_TERMINAL_STATUSES",
    "QUEUE_RETRYABLE_REASONS",
    "QUEUE_MAX_ATTEMPTS",
    "QUEUE_BACKOFF_BASE_S",
    "QUEUE_BACKOFF_CEILING_S",
    "ensure_db",
    "connect",
    "add_entry",
    "list_entries",
    "get_entry",
    "resolve_entry",
    "remove_entry",
    "update_entry_result",
    "claim_entry",
    "reset_to_pending",
    "compute_backoff_s",
    "schedule_retry",
    "dead_letter_entry",
    "cancel_entry",
    "revive_entry",
]

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(".ll/queue.db")


def _is_default_shaped(path: Path | str) -> bool:
    """True when *path* names the default queue DB location (ENH-2927).

    Mirrors ``session_store.db._is_default_shaped``: matched by basename +
    parent (not strict equality), so an already-absolute cwd-based
    ``.ll/queue.db`` a caller constructed still routes through resolution. Any
    other path is a deliberate override and is returned verbatim.
    """
    p = Path(path)
    if p == DEFAULT_DB_PATH:
        return True
    return p.name == "queue.db" and p.parent.name == ".ll"


def _resolve_queue_db_path(path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None) -> Path:
    """Resolve *path* to an absolute location, anchoring the default at the
    resolved project root (ENH-2927) instead of a bare cwd-relative path.

    A deliberate (non-default-shaped) override is returned verbatim. For the
    default, delegates to :func:`~little_loops.paths.resolve_ll_dir`; when no
    project root resolves at all, falls back to a cwd-absolute form of the
    legacy default rather than inventing a root.

    *root* (mirrors ``session_store.db.resolve_history_db``'s BUG-3181 fix) anchors
    ``resolve_ll_dir`` at a known project root instead of walking up from
    ``Path.cwd()`` — needed by callers (e.g. ll-mcp) whose process cwd can differ from
    the project root they were told to operate against. Omitted, behavior is unchanged.
    """
    p = Path(path)
    if not _is_default_shaped(p):
        return p
    from little_loops.paths import resolve_ll_dir

    ll_dir = resolve_ll_dir(root)
    if ll_dir is not None:
        return ll_dir / "queue.db"
    return (root or Path.cwd()) / DEFAULT_DB_PATH


# Lower-is-higher-precedence tiers, mirroring
# ``IssuePriorityQueue.DEFAULT_PRIORITIES`` (parallel/priority_queue.py).
PRIORITY_TIERS: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4", "P5")

_BUSY_TIMEOUT_MS = 5000

SCHEMA_VERSION = 3

_MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS queue_entries (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        enqueued_at TEXT NOT NULL,
        priority INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        result TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_queue_entries_order
        ON queue_entries(priority, enqueued_at);
    """,
    # FEAT-2930: ownership tracking for the --watch long-lived drainer's
    # stale-entry reclaim. Both nullable — existing rows are unaffected, and a
    # `done`/`failed` entry has neither set once update_entry_result runs.
    """
    ALTER TABLE queue_entries ADD COLUMN claimed_at TEXT;
    ALTER TABLE queue_entries ADD COLUMN owner_pid INTEGER;
    """,
    # ENH-3416: attempt budget + backoff. `attempt` is incremented at claim
    # time (survives a dead drainer with no extra bookkeeping) and defaults to
    # 0 so pre-existing rows read back unchanged. `next_attempt_at` gates
    # claim_entry's eligibility filter; NULL means immediately eligible.
    """
    ALTER TABLE queue_entries ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE queue_entries ADD COLUMN next_attempt_at TEXT;
    """,
]

# Status vocabulary (ENH-3416): declared once, every enumeration elsewhere
# (`_STATUS_COLOR`, the `queue_list` MCP description, docs) derives from or is
# locked against these.
QUEUE_STATUSES = frozenset({"pending", "running", "done", "failed", "dead_letter", "cancelled"})
QUEUE_TERMINAL_STATUSES = frozenset({"done", "failed", "dead_letter", "cancelled"})

# Reasons from issue_lifecycle.classify_failure() that make a queue dispatch
# failure retryable. Deliberately a narrow allowlist, not "any TRANSIENT": the
# classifier was written for host-CLI stderr, and a queue entry's stderr is
# arbitrary program output (an `ll-loop run` log, a pytest run) whose broad
# substrings ("timeout", "429") fire on unrelated text (see ENH-3416 Design
# Decisions). Gated on the `reason` string, not `FailureType`, for the same
# reason.
QUEUE_RETRYABLE_REASONS = frozenset(
    {
        "API quota or rate limit exceeded",
        "Network or connectivity error",
        "API server error",
        "Infra teardown: SIGTERM after result event",  # INFRA_RETRY
    }
)

# ENH-3416 policy constants (module constants, not config — see Design
# Decisions for the trade-off accepted by each).
QUEUE_MAX_ATTEMPTS = 5  # bounds a poison entry to 5 dispatches / 4 reclaims
QUEUE_BACKOFF_BASE_S = 5  # 5, 10, 20, 40 s between attempts 1..4
QUEUE_BACKOFF_CEILING_S = 300  # worst-case wait bounded at 5 min


def _utcnow() -> str:
    """Return the current UTC time in the store's persisted timestamp format.

    The single "current time" seam for this module (ENH-3416): every read of
    "now" in ``queue_store.py``/``cli/queue.py`` goes through this function so
    tests can patch one call site instead of each ``datetime.now`` use.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_backoff_s(attempt: int) -> int:
    """Return the backoff delay, in seconds, before retrying *attempt*.

    Non-jittered iterative doubling: ``base * 2**(attempt-1)``, capped at
    ``QUEUE_BACKOFF_CEILING_S`` (see ENH-3416 Decision Rationale — every other
    non-jittered backoff site in this codebase is local/same-machine, matching
    ``ll-queue``'s single-writer-SQLite shape).
    """
    return min(QUEUE_BACKOFF_BASE_S * 2 ** (attempt - 1), QUEUE_BACKOFF_CEILING_S)


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply concurrency pragmas to a freshly opened connection.

    See :func:`little_loops.session_store._configure_connection` for the
    rationale (busy_timeout avoids instant "database is locked" failures under
    concurrent ll-auto/ll-loop/ll-parallel workers; WAL lets readers and
    writers proceed concurrently). Both pragmas are best-effort.
    """
    try:
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        logger.debug("queue_store: could not apply connection pragmas", exc_info=True)


def _split_sql_statements(script: str) -> list[str]:
    """Split a migration's SQL into individual statements on ``;`` boundaries.

    See :func:`little_loops.session_store._split_sql_statements` — avoids
    ``executescript``'s implicit ``COMMIT``, which would drop the write lock
    held across the migration sequence.
    """
    return [stmt for raw in script.split(";") if (stmt := raw.strip())]


def _current_version(conn: sqlite3.Connection) -> int:
    """Return the applied schema version, or 0 if the meta table is absent."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
    return int(row[0]) if row else 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply every migration newer than the database's current version.

    See :func:`little_loops.session_store._apply_migrations` for the full
    concurrency rationale (single ``BEGIN IMMEDIATE`` transaction, fast-path
    skip when already current).
    """
    if _current_version(conn) >= len(_MIGRATIONS):
        return
    prior_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            version = _current_version(conn)
            for index in range(version, len(_MIGRATIONS)):
                for statement in _split_sql_statements(_MIGRATIONS[index]):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(index + 1),),
                )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = prior_isolation


def ensure_db(path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None) -> Path:
    """Create the database at *path* (if needed) and apply pending migrations.

    Idempotent: safe to call on every invocation. The parent directory is
    created if absent. Returns the resolved database path. *root* is forwarded to
    :func:`_resolve_queue_db_path` (see its docstring).
    """
    db_path = _resolve_queue_db_path(path, root=root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _configure_connection(conn)
        _apply_migrations(conn)
    finally:
        conn.close()
    return db_path


def connect(path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None) -> sqlite3.Connection:
    """Open a connection to the queue database, ensuring the schema first.

    Rows are returned as :class:`sqlite3.Row` so callers can index by name. *root* is
    forwarded to :func:`_resolve_queue_db_path` (see its docstring).
    """
    db_path = ensure_db(path, root=root)
    conn = sqlite3.connect(str(db_path))
    _configure_connection(conn)
    conn.row_factory = sqlite3.Row
    return conn


def _priority_rank(priority: str) -> int:
    """Return the numeric rank (0=P0 highest .. 5=P5 lowest) for *priority*."""
    try:
        return PRIORITY_TIERS.index(priority.upper())
    except ValueError as exc:
        raise ValueError(f"Invalid priority {priority!r}; must be one of {PRIORITY_TIERS}") from exc


def _serialize_action(action: ActionSpec) -> str:
    return json.dumps(
        {
            "name": action.name,
            "runner": action.runner.value,
            "target": action.target,
            "args": action.args,
            "timeout": action.timeout,
            "scopes": sorted(action.scopes) if action.scopes is not None else None,
        }
    )


def _deserialize_action(text: str) -> ActionSpec:
    data = json.loads(text)
    scopes = data.get("scopes")
    return ActionSpec(
        name=data["name"],
        runner=RunnerType(data["runner"]),
        target=data["target"],
        args=data.get("args", {}),
        timeout=data.get("timeout", 120),
        scopes=frozenset(scopes) if scopes is not None else None,
    )


@dataclass
class QueueEntry:
    """One persisted queue entry."""

    id: str
    action: ActionSpec
    enqueued_at: str
    priority: str
    status: str
    result: dict[str, Any] | None = None
    claimed_at: str | None = None
    owner_pid: int | None = None
    attempt: int = 0
    next_attempt_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": {
                "name": self.action.name,
                "runner": self.action.runner.value,
                "target": self.action.target,
                "args": self.action.args,
                "timeout": self.action.timeout,
                "scopes": sorted(self.action.scopes) if self.action.scopes is not None else None,
            },
            "enqueuedAt": self.enqueued_at,
            "priority": self.priority,
            "status": self.status,
            "result": self.result,
            "claimedAt": self.claimed_at,
            "ownerPid": self.owner_pid,
            "attempt": self.attempt,
            "nextAttemptAt": self.next_attempt_at,
        }

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> QueueEntry:
        return cls(
            id=row["id"],
            action=_deserialize_action(row["action"]),
            enqueued_at=row["enqueued_at"],
            priority=PRIORITY_TIERS[row["priority"]],
            status=row["status"],
            result=json.loads(row["result"]) if row["result"] else None,
            claimed_at=row["claimed_at"],
            owner_pid=row["owner_pid"],
            attempt=row["attempt"],
            next_attempt_at=row["next_attempt_at"],
        )


class AmbiguousEntryIdError(ValueError):
    """Raised by :func:`resolve_entry` when a short id prefix matches >1 entry."""


def add_entry(
    action: ActionSpec,
    priority: str = "P3",
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    root: Path | None = None,
) -> QueueEntry:
    """Persist a new queue entry and return it. *root* is forwarded to :func:`connect`.

    Raises :class:`ValueError` (ENH-3403) for a scoped SKILL/PROMPT/MCP
    *action*: those runners never enforce ``scopes``, so rejecting at enqueue
    time is preferable to persisting an entry that will silently dispatch
    unscoped (or fail loud later) at drain.
    """
    scope_error = scope_runner_error(action)
    if scope_error is not None:
        raise ValueError(scope_error)
    entry_id = str(uuid.uuid4())
    enqueued_at = _utcnow()
    rank = _priority_rank(priority)
    conn = connect(db_path, root=root)
    try:
        conn.execute(
            "INSERT INTO queue_entries(id, action, enqueued_at, priority, status, result) "
            "VALUES (?, ?, ?, ?, 'pending', NULL)",
            (entry_id, _serialize_action(action), enqueued_at, rank),
        )
        conn.commit()
    finally:
        conn.close()
    return QueueEntry(
        id=entry_id,
        action=action,
        enqueued_at=enqueued_at,
        priority=PRIORITY_TIERS[rank],
        status="pending",
        result=None,
    )


def list_entries(
    db_path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None
) -> list[QueueEntry]:
    """Return all entries ordered by priority tier, then FIFO within tier."""
    conn = connect(db_path, root=root)
    try:
        rows = conn.execute(
            "SELECT * FROM queue_entries ORDER BY priority ASC, enqueued_at ASC"
        ).fetchall()
    finally:
        conn.close()
    return [QueueEntry._from_row(row) for row in rows]


def get_entry(
    entry_id: str, db_path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None
) -> QueueEntry | None:
    """Return the entry with the exact *entry_id*, or None."""
    conn = connect(db_path, root=root)
    try:
        row = conn.execute("SELECT * FROM queue_entries WHERE id = ?", (entry_id,)).fetchone()
    finally:
        conn.close()
    return QueueEntry._from_row(row) if row else None


def resolve_entry(
    target_id: str, db_path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None
) -> QueueEntry | None:
    """Resolve *target_id* by exact id or an 8+-char prefix (mirrors ``ll-loop queue``).

    Returns None if no entry matches. Raises :class:`AmbiguousEntryIdError` if
    a prefix (shorter than the full uuid) matches more than one entry.
    """
    exact = get_entry(target_id, db_path, root=root)
    if exact is not None:
        return exact
    if len(target_id) < 8:
        return None
    entries = list_entries(db_path, root=root)
    matches = [e for e in entries if e.id.startswith(target_id)]
    if len(matches) > 1:
        raise AmbiguousEntryIdError(
            f"Prefix {target_id!r} matches {len(matches)} entries; use a longer prefix"
        )
    return matches[0] if matches else None


def remove_entry(
    entry_id: str, db_path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None
) -> bool:
    """Delete the entry with the exact *entry_id*. Returns True if a row was deleted."""
    conn = connect(db_path, root=root)
    try:
        cur = conn.execute("DELETE FROM queue_entries WHERE id = ?", (entry_id,))
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def reset_to_pending(
    entry_id: str, db_path: Path | str = DEFAULT_DB_PATH, *, root: Path | None = None
) -> bool:
    """Return a ``running`` entry to ``pending``, clearing ``claimed_at``/``owner_pid``.

    Shared by FEAT-2930's ``_reclaim_stale`` sweep and ``ll-queue requeue``.
    Only ``running`` entries transition — a ``pending``/``done``/``failed``
    entry is left untouched. Returns True iff a row was updated.

    This is the *reclaim* path (ENH-3416): it does not touch ``attempt`` or
    ``next_attempt_at``. An owner death is a slot to refill, not a
    backoff-eligible failure — the caller (``_reclaim_stale``) decides
    separately whether the entry's attempt budget is exhausted and routes to
    :func:`dead_letter_entry` instead when it is.
    """
    conn = connect(db_path, root=root)
    try:
        cur = conn.execute(
            "UPDATE queue_entries SET status = 'pending', claimed_at = NULL, owner_pid = NULL "
            "WHERE id = ? AND status = 'running'",
            (entry_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def update_entry_result(
    entry_id: str,
    status: str,
    result: dict[str, Any] | None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Update *entry_id*'s ``status``/``result`` (for the FEAT-2683 worker). Returns True if updated.

    Also nulls ``owner_pid``/``claimed_at`` (FEAT-2930): a ``done``/``failed``
    entry is never a candidate for :func:`_reclaim_stale`'s
    ``WHERE status = 'running'`` sweep either way, but leaving a stale
    ``owner_pid`` on a finished entry is a data-hygiene footgun for anything
    that later reads it directly.

    The write is guarded with ``AND status = 'running'`` (ENH-3416): only a
    row this caller's drainer actually claimed is a valid completion target.
    Returns False (no-op, row unchanged) if the entry was cancelled or
    reclaimed out from under the drainer between claim and completion — the
    caller should re-read the row and record its actual status rather than
    assume this write landed.
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE queue_entries SET status = ?, result = ?, claimed_at = NULL, "
            "owner_pid = NULL WHERE id = ? AND status = 'running'",
            (status, json.dumps(result) if result is not None else None, entry_id),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def schedule_retry(
    entry_id: str,
    error: str,
    next_attempt_at: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Return a ``running`` entry to ``pending`` with a backoff deadline (ENH-3416).

    Used for a retryable dispatch failure with budget remaining. Guarded with
    ``AND status = 'running'`` like :func:`update_entry_result`; returns False
    on a guard miss (cancelled/reclaimed mid-dispatch).
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE queue_entries SET status = 'pending', next_attempt_at = ?, "
            "result = ?, claimed_at = NULL, owner_pid = NULL "
            "WHERE id = ? AND status = 'running'",
            (next_attempt_at, json.dumps({"error": error}), entry_id),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def dead_letter_entry(
    entry_id: str,
    error: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Move a ``running`` entry to terminal ``dead_letter`` (ENH-3416).

    Used when a retryable failure exhausts the attempt budget, or an
    owner-death reclaim finds ``attempt >= QUEUE_MAX_ATTEMPTS``. Guarded with
    ``AND status = 'running'`` like :func:`update_entry_result`; returns False
    on a guard miss.
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE queue_entries SET status = 'dead_letter', result = ?, "
            "claimed_at = NULL, owner_pid = NULL WHERE id = ? AND status = 'running'",
            (json.dumps({"error": error}), entry_id),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def cancel_entry(
    entry_id: str,
    reason: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Move a ``pending`` or ``running`` entry to terminal ``cancelled`` (ENH-3416).

    Does not signal an in-flight process — see ``ll-queue cancel``'s docs for
    the cancel-vs-dispatch rationale. *extra* (the dispatch's
    ``exit_code``/``stdout``/``stderr`` when cancelling mid-dispatch via the
    ``force_stop`` path) is merged under ``reason`` so partial output is not
    lost. Guarded with ``AND status IN ('pending', 'running')``; returns False
    if the entry already reached a terminal status.
    """
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE queue_entries SET status = 'cancelled', result = ?, "
            "claimed_at = NULL, owner_pid = NULL "
            "WHERE id = ? AND status IN ('pending', 'running')",
            (json.dumps({**(extra or {}), "reason": reason}), entry_id),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def revive_entry(
    entry_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    root: Path | None = None,
) -> bool:
    """Return a terminal entry to ``pending`` with a fresh attempt budget (ENH-3416).

    Used by ``ll-queue requeue`` for ``dead_letter``/``failed``/``cancelled``
    entries (the ``running`` case stays on :func:`reset_to_pending`). Resets
    ``attempt`` to 0 and clears ``next_attempt_at``; the prior ``result`` (if
    any) is preserved under ``result.previous`` rather than discarded.

    *root* (mirrors :func:`reset_to_pending`) anchors the default db path at
    a known project root instead of the process cwd — needed by the MCP
    server's ``queue_requeue`` tool.
    """
    conn = connect(db_path, root=root)
    try:
        row = conn.execute("SELECT result FROM queue_entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return False
        prior = json.loads(row["result"]) if row["result"] else None
        new_result = {"previous": prior} if prior is not None else None
        cur = conn.execute(
            "UPDATE queue_entries SET status = 'pending', attempt = 0, next_attempt_at = NULL, "
            "result = ?, claimed_at = NULL, owner_pid = NULL WHERE id = ?",
            (json.dumps(new_result) if new_result is not None else None, entry_id),
        )
        conn.commit()
    finally:
        conn.close()
    return cur.rowcount > 0


def claim_entry(
    entry_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    owner_pid: int | None = None,
    now: str | None = None,
) -> bool:
    """Atomically transition *entry_id* from ``pending`` to ``running``.

    Returns True iff this caller won the claim. Uses ``BEGIN IMMEDIATE``
    (mirroring :func:`_apply_migrations`) so the pending-check and the write
    happen inside one transaction, closing the TOCTOU race a Python-side
    read-then-write against :func:`update_entry_result` would leave open when
    multiple drainers race for the same entry (BUG-2929).

    *owner_pid* (FEAT-2930), when given, is stamped alongside ``claimed_at``
    so a later :func:`_reclaim_stale <little_loops.cli.queue._reclaim_stale>`
    sweep can tell whether the claiming process is still alive. Defaults to
    ``os.getpid()``.

    Increments ``attempt`` (ENH-3416) so a dead drainer's reclaim consumes
    budget with no extra bookkeeping. The WHERE clause also requires
    ``next_attempt_at`` to be unset or already elapsed against *now*
    (defaults to :func:`_utcnow`, injectable for tests) — a row backing off
    is not claimable yet.
    """
    pid = owner_pid if owner_pid is not None else os.getpid()
    claimed_at = _utcnow()
    effective_now = now if now is not None else claimed_at
    conn = connect(db_path)
    prior_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "UPDATE queue_entries SET status = 'running', claimed_at = ?, owner_pid = ?, "
                "attempt = attempt + 1 "
                "WHERE id = ? AND status = 'pending' "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= ?)",
                (claimed_at, pid, entry_id, effective_now),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = prior_isolation
        conn.close()
    return cur.rowcount > 0

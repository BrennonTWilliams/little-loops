"""Schema migration and open-time policy for a remote libSQL history store (FEAT-3535).

Opens never migrate. The only path that changes a remote schema is
:func:`migrate_remote` (``ll-session migrate``), which sends **each pending migration as one
atomic Hrana ``batch``** instead of an interactive transaction (interactive streams expire
and do not serialize concurrent initializers, FEAT-3524's F4/F6)::

    begin immediate
    guard            -- errors unless the recorded version is still the one we read
    <migration statements>
    version upsert
    commit           -- only if every step above succeeded
    rollback         -- only if the commit did not run

The guard is what preserves the local ``_apply_migrations`` re-read-under-lock semantics:
``begin immediate`` makes concurrent runners queue on the server, and the guard makes a
runner that lost the race fail cleanly (it then re-reads the version and carries on)
instead of re-applying a migration.

:func:`check_access` is the open-time policy, evaluated once per process and endpoint.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from little_loops.session_store.backend import HistoryUnsupported
from little_loops.session_store.hrana import (
    BatchStep,
    HranaClient,
    HranaUnavailable,
    classify_error,
    cond_not,
    cond_ok,
)

if TYPE_CHECKING:
    from little_loops.session_store.targets import BackendConfig

_MIGRATE_HINT = "run `ll-session migrate`"
# ``abs(-9223372036854775808)`` overflows, so SQLite raises: a portable "assert false".
_FAIL = "abs(-9223372036854775808)"


def _migrations() -> list[str]:
    from little_loops.session_store import schema

    return schema._MIGRATIONS


def _statements(script: str) -> list[str]:
    from little_loops.session_store import schema

    return schema._split_sql_statements(script)


@dataclass(frozen=True)
class RemoteState:
    """What the remote store records about itself."""

    version: int
    project_id: str | None


@dataclass(frozen=True)
class MigrationReport:
    before: int
    after: int
    applied: int


def read_state(client: HranaClient) -> RemoteState:
    """Read the recorded schema version and ``project_id`` in one round trip.

    An empty store (no ``meta`` table) is version 0 with no project; this is detected from
    ``sqlite_master``, never by matching an error message.
    """
    result = client.batch(
        [
            BatchStep("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"),
            BatchStep(
                "SELECT key, value FROM meta WHERE key IN ('schema_version', 'project_id')",
                condition=cond_ok(0),
            ),
        ]
    )
    exists = result.step_results[0]
    if exists is None or not exists.rows:
        return RemoteState(0, None)
    meta = result.step_results[1]
    if meta is None:
        err = result.first_error() or {}
        raise classify_error(err.get("code"), str(err.get("message", "could not read meta")))
    kv = dict(meta.rows)
    return RemoteState(int(kv.get("schema_version") or 0), kv.get("project_id"))


def _migration_steps(index: int, version_guard: BatchStep) -> list[BatchStep]:
    steps = [BatchStep("begin immediate"), version_guard]
    for statement in _statements(_migrations()[index]):
        steps.append(BatchStep(statement, condition=cond_ok(len(steps) - 1)))
    steps.append(
        BatchStep(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(index + 1),),
            cond_ok(len(steps) - 1),
        )
    )
    steps.append(BatchStep("commit", condition=cond_ok(len(steps) - 1)))
    steps.append(BatchStep("rollback", condition=cond_not(cond_ok(len(steps) - 1))))
    return steps


def _guard(index: int) -> BatchStep:
    if index == 0:  # fresh store: fail if another runner already created ``meta``
        sql = (
            f"SELECT CASE WHEN EXISTS(SELECT 1 FROM sqlite_master WHERE name = 'meta') "
            f"THEN {_FAIL} ELSE 1 END"
        )
        return BatchStep(sql, condition=cond_ok(0))
    sql = (
        f"SELECT CASE WHEN (SELECT value FROM meta WHERE key = 'schema_version') = ? "
        f"THEN 1 ELSE {_FAIL} END"
    )
    return BatchStep(sql, (str(index),), cond_ok(0))


def _apply_one(client: HranaClient, index: int) -> bool:
    """Apply migration *index*; ``True`` when this call committed it, ``False`` when a
    concurrent runner got there first (the guard failed)."""
    steps = _migration_steps(index, _guard(index))
    commit_at = len(steps) - 2
    try:
        result = client.batch(steps)
    except HranaUnavailable:
        # Ambiguous commit (connection lost mid-batch): re-read the idempotent marker.
        if read_state(client).version > index:
            return True
        raise
    if result.step_results[commit_at] is not None:
        return True
    err = result.first_error()
    if result.step_errors[1] is not None:  # the guard step
        return False
    assert err is not None
    raise classify_error(err.get("code"), str(err.get("message", "migration failed")))


def _check_project(state: RemoteState, project_id: str | None) -> None:
    if state.project_id is not None and state.project_id != project_id:
        raise HistoryUnsupported(
            f"remote store belongs to project_id {state.project_id!r}, not "
            f"{project_id!r}; refusing to share one store across projects",
            operation="open",
        )


def migrate_remote(
    client: HranaClient, project_id: str | None, *, upto: int | None = None
) -> MigrationReport:
    """Bring the remote schema to the installed version and stamp ``meta.project_id``.

    Args:
        client: An authenticated client for the remote store.
        project_id: ``history.backend.project_id``; stamped on first migrate, compared after.
        upto: Stop after this version (used by tests to build a store that is behind).

    Raises:
        HistoryUnsupported: the store is ahead of this install, or belongs to another project.
    """
    if not project_id:
        raise HistoryUnsupported(
            "history.backend.project_id is required when provider is 'libsql'", operation="migrate"
        )
    total = len(_migrations())
    goal = total if upto is None else min(upto, total)
    state = read_state(client)
    _check_project(state, project_id)
    if state.version > total:
        raise HistoryUnsupported(
            f"remote store is at schema v{state.version}, ahead of this install's v{total}; "
            "upgrade little-loops",
            operation="migrate",
        )
    before = recorded = state.version
    applied = 0
    while recorded < goal:
        if _apply_one(client, recorded):
            applied += 1
            recorded += 1
            continue
        fresh = read_state(client).version
        if fresh <= recorded:  # guard failed but nobody advanced: unexpected, do not spin
            raise HistoryUnsupported(
                f"remote schema changed unexpectedly during migration {recorded}",
                operation="migrate",
            )
        recorded = fresh
    client.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES('project_id', ?)", (project_id,)
    ) if recorded > 0 else None
    final = read_state(client)
    _check_project(final, project_id)
    clear_verification_cache()
    return MigrationReport(before=before, after=final.version, applied=applied)


# -- open-time policy ------------------------------------------------------

_VERIFIED: dict[tuple[str, str | None], RemoteState] = {}
_LOCK = threading.Lock()


def clear_verification_cache() -> None:
    with _LOCK:
        _VERIFIED.clear()


def check_access(client: HranaClient, cfg: BackendConfig, *, write: bool) -> RemoteState:
    """Apply the open-time policy for one statement (state is read once per process).

    * ``project_id`` is required, and a store stamped for another project is refused for
      reads and writes alike.
    * Writes need a store at exactly the installed version: behind means "run the migrate
      command", ahead means "upgrade little-loops". Strict reads proceed either way.
    """
    if not cfg.project_id:
        raise HistoryUnsupported(
            "history.backend.project_id is required when provider is 'libsql'", operation="open"
        )
    key = (client.base_url, cfg.project_id)
    with _LOCK:
        state = _VERIFIED.get(key)
    if state is None:
        state = read_state(client)
        with _LOCK:
            _VERIFIED[key] = state
    _check_project(state, cfg.project_id)
    if write:
        total = len(_migrations())
        if state.version < total:
            raise HistoryUnsupported(
                f"remote store is at schema v{state.version}, behind this install's v{total}; "
                f"{_MIGRATE_HINT}",
                operation="write",
            )
        if state.version > total:
            raise HistoryUnsupported(
                f"remote store is at schema v{state.version}, ahead of this install's v{total}; "
                "upgrade little-loops",
                operation="write",
            )
        if state.project_id is None:
            raise HistoryUnsupported(
                f"remote store has no project_id stamp; {_MIGRATE_HINT}", operation="write"
            )
    return state


__all__: list[Any] = [
    "MigrationReport",
    "RemoteState",
    "check_access",
    "clear_verification_cache",
    "migrate_remote",
    "read_state",
]

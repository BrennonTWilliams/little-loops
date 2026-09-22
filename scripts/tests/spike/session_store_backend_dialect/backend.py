"""Spike for FEAT-3524: the session_store backend/dialect abstraction chokepoint.

Proves a ``Backend`` protocol + lazy-import dialect registry (mirroring
``codequery.core.resolve_provider``) can drive the exact locking sequence
``session_store.schema._apply_migrations`` relies on (``BEGIN IMMEDIATE`` /
manual ``isolation_level`` / statement-split, never ``executescript``) with
dialect-parameterized DDL, plus a capability-gated degradation path for
SQLite-only features. See ``.ll/spikes/spike-FEAT-3524.md`` for the plan.
"""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

_BUSY_TIMEOUT_MS = 5000


@runtime_checkable
class Backend(Protocol):
    kind: str

    def connect(self) -> sqlite3.Connection: ...
    def connect_readonly(self) -> sqlite3.Connection: ...
    def ensure_schema(self) -> None: ...
    def supports(self, capability: str) -> bool: ...
    def migrations(self) -> list[str]: ...


class UnsupportedCapability(Exception):
    """Raised when a caller requests a feature the backend does not support."""


# Lazy-import registry: dialect name -> (module path, class name). The
# concrete dialect classes in dialects.py import apply_migrations back from
# this module, so eager import here would cycle -- same rationale as
# codequery.core._PROVIDER_MAP.
_BACKEND_MAP: dict[str, tuple[str, str]] = {
    "sqlite": (
        "scripts.tests.spike.session_store_backend_dialect.dialects",
        "SqliteBackend",
    ),
    "stub_remote": (
        "scripts.tests.spike.session_store_backend_dialect.dialects",
        "StubRemoteBackend",
    ),
}


def resolve_backend(kind: str, db_path: Path) -> Backend:
    if kind not in _BACKEND_MAP:
        raise ValueError(f"Unknown backend kind: {kind!r}")
    module_path, class_name = _BACKEND_MAP[kind]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(db_path)


def configure_connection(conn: sqlite3.Connection, backend: Backend) -> None:
    """Best-effort pragmas, gated by capability instead of a bare try/except
    around a SQLite-specific pragma the dialect may not support."""
    try:
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    except sqlite3.OperationalError:
        pass
    if backend.supports("wal"):
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            pass


def require_capability(backend: Backend, capability: str) -> None:
    """The degradation path: a clear, catchable error instead of a feature
    failing deep inside a dialect that never claimed to support it."""
    if not backend.supports(capability):
        raise UnsupportedCapability(
            f"{capability!r} is not supported by backend {backend.kind!r}"
        )


def _split_sql_statements(script: str) -> list[str]:
    """Mirrors session_store.schema._split_sql_statements: split on ';'
    rather than executescript(), whose implicit COMMIT would release the
    write lock mid-migration."""
    return [stmt for raw in script.split(";") if (stmt := raw.strip())]


def _current_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
    return int(row[0]) if row else 0


def apply_migrations(conn: sqlite3.Connection, backend: Backend) -> None:
    """Dialect-parameterized twin of session_store.schema._apply_migrations:
    same BEGIN IMMEDIATE / manual isolation_level / statement-split locking
    sequence, sourcing DDL from backend.migrations() instead of a
    module-level constant.
    """
    migrations = backend.migrations()
    recorded = _current_version(conn)
    if recorded == len(migrations):
        return
    prior_isolation = conn.isolation_level
    conn.isolation_level = None  # manual transaction control
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            in_lock_recorded = _current_version(conn)
            version = min(in_lock_recorded, len(migrations))
            for index in range(version, len(migrations)):
                for statement in _split_sql_statements(migrations[index]):
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

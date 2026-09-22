"""Two dialects proving the backend abstraction diverges correctly.

Both run on real sqlite3 connections -- proving a network driver is not
needed to validate the abstraction shape. ``sqlite`` mirrors today's
production capabilities/DDL; ``stub_remote`` stands in for "a real
non-SQLite dialect" with a reduced capability set and migration DDL that
avoids SQLite-only syntax, the way a real Postgres/libSQL dialect would have
to. A genuine network-backed dialect is `/ll:explore-api` work, out of scope
here (see the plan's Out of Scope section).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.tests.spike.session_store_backend_dialect.backend import (
    apply_migrations,
    configure_connection,
)

_SQLITE_MIGRATIONS: list[str] = [
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE widgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    );
    """,
]

# Most non-SQLite dialects (Postgres SERIAL, libSQL's rowid-reuse semantics)
# reject AUTOINCREMENT outright -- a real remote dialect needs an equivalent
# per-dialect DDL swap here.
_STUB_REMOTE_MIGRATIONS: list[str] = [
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE widgets (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """,
]

_SQLITE_CAPABILITIES = frozenset({"fts5", "wal", "vacuum"})
_STUB_REMOTE_CAPABILITIES: frozenset[str] = frozenset()


class SqliteBackend:
    kind = "sqlite"
    _capabilities = _SQLITE_CAPABILITIES
    _migrations = _SQLITE_MIGRATIONS

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def migrations(self) -> list[str]:
        return self._migrations

    def supports(self, capability: str) -> bool:
        return capability in self._capabilities

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        configure_connection(conn, self)
        return conn

    def connect_readonly(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        return conn

    def ensure_schema(self) -> None:
        conn = self.connect()
        try:
            apply_migrations(conn, self)
        finally:
            conn.close()


class StubRemoteBackend(SqliteBackend):
    kind = "stub_remote"
    _capabilities = _STUB_REMOTE_CAPABILITIES
    _migrations = _STUB_REMOTE_MIGRATIONS

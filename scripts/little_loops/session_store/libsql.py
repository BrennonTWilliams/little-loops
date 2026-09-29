"""Remote libSQL history backend over the stdlib Hrana client (FEAT-3535).

:class:`LibsqlBackend` is the second provider behind the ``Backend`` protocol. It hands out
:class:`LibsqlConnection` objects that satisfy the ``HistoryConnection`` /
``HistoryCursor`` / ``HistoryRow`` protocols on top of :class:`~.hrana.HranaClient`.

Scope and deliberate differences from local SQLite:

- **Autocommit.** Every ``execute`` is one HTTP round trip and is durable on return;
  ``commit``/``rollback`` are no-ops and ``in_transaction`` is always ``False``. Atomic
  multi-row writes use ``executemany`` (one atomic ``batch``).
- **No WAL / busy_timeout setup.** The remote server rejects those pragmas
  (``SQL_PARSE_ERROR``), so ``connect`` never sends them.
- **Opens do not migrate.** Schema changes happen only through ``ll-session migrate``
  (see :mod:`.remote_schema`).
- **No sqlite3 specifics.** ``supports()`` is ``False`` for every capability, so callers
  that need ``ATTACH``, ``VACUUM`` or ``create_function`` gate on it first.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from little_loops.session_store.backend import (
    HistoryTarget,
    HistoryUnsupported,
    RemoteTarget,
)
from little_loops.session_store.hrana import HranaClient, HranaResult

DEFAULT_TIMEOUT_S = 10.0

_READ_ONLY_PREFIXES = ("select", "with", "explain", "values", "pragma table_")


class LibsqlRow:
    """A result row with index, name, ``keys()`` and ``dict()`` access (like ``sqlite3.Row``)."""

    __slots__ = ("_cols", "_values")

    def __init__(self, cols: Sequence[str], values: Sequence[Any]) -> None:
        self._cols = tuple(cols)
        self._values = tuple(values)

    def keys(self) -> list[str]:
        return list(self._cols)

    def __getitem__(self, key: int | str | slice) -> Any:
        if isinstance(key, str):
            try:
                return self._values[self._cols.index(key)]
            except ValueError:
                raise IndexError(f"No item with that key: {key!r}") from None
        return self._values[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LibsqlRow):
            return self._cols == other._cols and self._values == other._values
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._cols, self._values))

    def __repr__(self) -> str:
        return f"LibsqlRow({dict(zip(self._cols, self._values, strict=True))!r})"


class LibsqlCursor:
    """Materialised result of one statement."""

    def __init__(self, result: HranaResult | None = None, rowcount: int | None = None) -> None:
        result = result or HranaResult()
        self._rows = [LibsqlRow(result.cols, r) for r in result.rows]
        self._pos = 0
        self.description: Any = (
            tuple((name, None, None, None, None, None, None) for name in result.cols)
            if result.cols
            else None
        )
        self.lastrowid: int | None = result.last_insert_rowid
        self.rowcount: int = result.affected_row_count if rowcount is None else rowcount

    def fetchone(self) -> LibsqlRow | None:
        if self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def fetchall(self) -> list[LibsqlRow]:
        rows = self._rows[self._pos :]
        self._pos = len(self._rows)
        return rows

    def fetchmany(self, size: int = 1) -> list[LibsqlRow]:
        rows = self._rows[self._pos : self._pos + size]
        self._pos += len(rows)
        return rows

    def __iter__(self) -> Iterator[LibsqlRow]:
        while (row := self.fetchone()) is not None:
            yield row


class LibsqlConnection:
    """``HistoryConnection`` over a :class:`HranaClient` (autocommit; see module docs)."""

    in_transaction = False

    def __init__(self, client: HranaClient, *, read_only: bool = False) -> None:
        self._client = client
        self._read_only = read_only
        # Legacy callers assign ``conn.row_factory = sqlite3.Row``; rows are always
        # name-and-index addressable here, so the assignment is accepted and ignored.
        self.row_factory: Any = None

    @property
    def client(self) -> HranaClient:
        return self._client

    def _guard_write(self, sql: str) -> None:
        if self._read_only and not sql.lstrip().lower().startswith(_READ_ONLY_PREFIXES):
            raise HistoryUnsupported(
                "this connection is read-only; refusing a write before any network call",
                operation="write",
            )

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> LibsqlCursor:
        self._guard_write(sql)
        return LibsqlCursor(self._client.execute(sql, parameters))

    def executemany(self, sql: str, seq_of_parameters: Iterable[Sequence[Any]]) -> LibsqlCursor:
        self._guard_write(sql)
        return LibsqlCursor(rowcount=self._client.execute_many(sql, seq_of_parameters))

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def _remote(target: Path | HistoryTarget, operation: str) -> RemoteTarget:
    if isinstance(target, RemoteTarget):
        return target
    raise HistoryUnsupported(
        f"LibsqlBackend.{operation} needs a remote target, not a local path", operation=operation
    )


class LibsqlBackend:
    """A history-store backend for a remote libSQL endpoint (sqld or Turso Cloud)."""

    provider = "libsql"

    def supports(self, capability: str) -> bool:
        return False

    def _client(self, target: RemoteTarget, *, timeout: float = DEFAULT_TIMEOUT_S) -> HranaClient:
        cfg = target.config
        return HranaClient(cfg.endpoint(), cfg.auth_token(), timeout=timeout)

    def connect(
        self, target: Path | HistoryTarget, *, check_same_thread: bool = True
    ) -> LibsqlConnection:
        """Open a remote connection. Never migrates and never sends WAL pragmas.

        ``check_same_thread`` is accepted for protocol parity; the client is stateless and
        thread-safe, so it has no effect.
        """
        return LibsqlConnection(self._client(_remote(target, "connect")))

    def connect_readonly(self, target: Path | HistoryTarget) -> LibsqlConnection:
        """Read-only connection: writes are refused client-side before any network call."""
        return LibsqlConnection(self._client(_remote(target, "connect_readonly")), read_only=True)

    def ensure_schema(self, target: Path | HistoryTarget) -> None:
        """Verify the remote schema is usable; never migrates (see ``ll-session migrate``)."""
        _remote(target, "ensure_schema")

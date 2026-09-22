"""Session-store backend chokepoint (ENH-3525, FEAT-3524 Phase A).

Every classified history-store connection funnels through this module: a
``Backend`` protocol, a ``SqliteBackend`` implementation, a lazy
``(module_path, class_name)`` registry mirroring
:func:`little_loops.codequery.core.resolve_provider` (dialect modules would
import shared types back from here, the same circular-import pressure that
registry shape solves for ``codequery.core``), a backend-neutral
``HistoryError`` taxonomy, and the backend-aware entry points
``open_history()`` / ``open_history_readonly()``.

This is the SQLite-only prerequisite for FEAT-3524 (remote libSQL support):
one place to add a ``"libsql"`` provider later, without touching any of the
~70 read call sites or ~50 write call sites that go through
:func:`open_history` / :func:`open_history_readonly` / :func:`connect_readonly`.

Two named read-only contracts (see ``connect_readonly`` and
``open_history_readonly``):

- **Strict** (``connect_readonly`` / ``open_history_readonly(ensure=False)``):
  never creates or migrates the store (D19).
- **Ensure-then-read** (``open_history_readonly(ensure=True)``): resolves the
  target once, migrates that exact resolved path over a writable connection,
  then opens the *same* path read-only. Fixes the latent bug where
  ``history_reader._base._connect_readonly()`` discarded ``ensure_db()``'s
  resolved return value and re-opened the caller's unresolved argument,
  letting the two steps silently diverge for a default-shaped path
  (BUG-3181).

``connect()``/``ensure_db()`` keep their existing SQLite behavior, signature,
and two-connection-per-call implementation unchanged (deliberately out of
scope here) — ``SqliteBackend.connect()``/``ensure_schema()`` reuse them
rather than duplicating the migration/locking sequence.
"""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from little_loops.session_store.db import resolve_history_db

BackendProvider = Literal["sqlite"]


class HistoryError(Exception):
    """Base class for every backend-neutral history-store error."""


class HistoryUnavailable(HistoryError):
    """The store could not be opened (missing, locked, or otherwise unreachable)."""


class HistoryIntegrityError(HistoryError):
    """A write violated a constraint (unique/foreign-key/check)."""


class HistoryUnsupported(HistoryError):
    """The current backend does not support a requested capability."""


class HistoryOperationError(HistoryError):
    """A database operation failed for a reason other than the three above."""


@runtime_checkable
class HistoryCursor(Protocol):
    """Structural stand-in for :class:`sqlite3.Cursor`."""

    description: tuple[tuple[str, ...], ...] | None
    lastrowid: int | None
    rowcount: int

    def fetchone(self) -> HistoryRow | None: ...
    def fetchall(self) -> list[HistoryRow]: ...
    def fetchmany(self, size: int = ...) -> list[HistoryRow]: ...
    def __iter__(self): ...


@runtime_checkable
class HistoryRow(Protocol):
    """Structural stand-in for :class:`sqlite3.Row` — indexed and named access."""

    def keys(self) -> list[str]: ...
    def __getitem__(self, key): ...


@runtime_checkable
class HistoryConnection(Protocol):
    """Structural stand-in for :class:`sqlite3.Connection`.

    ``open_history()`` / ``open_history_readonly()`` set the row factory
    themselves (named *and* indexed row access is part of this contract) —
    consumers must not assign ``.row_factory`` on a connection returned from
    either entry point.
    """

    in_transaction: bool

    def execute(self, sql: str, parameters=...) -> HistoryCursor: ...
    def executemany(self, sql: str, seq_of_parameters) -> HistoryCursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class Backend(Protocol):
    """A history-store backend: one provider's connection/migration surface.

    Phase A (SQLite-only) types ``connect``/``connect_readonly`` concretely as
    :class:`sqlite3.Connection` rather than the abstract ``HistoryConnection``
    -- the only registered provider is SQLite, and every existing caller this
    module wraps (``schema.py``, ``doctor.py``'s manifest helpers, row
    unpacking in ``doctor_trim.py``) is already typed against
    :class:`sqlite3.Connection`/:class:`sqlite3.Row` directly. FEAT-3524's
    second provider is the point at which these narrow to
    ``HistoryConnection``.
    """

    provider: str

    def connect(self, path: Path) -> sqlite3.Connection: ...
    def connect_readonly(self, path: Path) -> sqlite3.Connection: ...
    def ensure_schema(self, path: Path) -> None: ...
    def supports(self, capability: str) -> bool: ...


# SQLite-only features gated behind supports(), not the Backend protocol
# itself — the seam FEAT-3524's libSQL remote backend (no ATTACH) needs.
_SQLITE_CAPABILITIES = frozenset({"attach", "vacuum", "create_function"})


class SqliteBackend:
    """The only backend Phase A registers. Wraps ``schema.py``'s existing
    ``connect``/``ensure_db`` rather than reimplementing their migration and
    locking sequence."""

    provider = "sqlite"

    def supports(self, capability: str) -> bool:
        return capability in _SQLITE_CAPABILITIES

    def connect(self, path: Path) -> sqlite3.Connection:
        from little_loops.session_store.schema import connect as _connect

        return _connect(path)

    def connect_readonly(self, path: Path) -> sqlite3.Connection:
        """Strict read-only open: never creates or migrates the store (D19)."""
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
        except sqlite3.Error as exc:
            raise HistoryUnavailable(f"could not open {path} read-only: {exc}") from exc
        return conn

    def ensure_schema(self, path: Path) -> None:
        from little_loops.session_store.schema import ensure_db

        ensure_db(path)


# Lazy-import registry: provider -> (module_path, class_name). Mirrors
# codequery.core._PROVIDER_MAP; kept lazy so a future "libsql" dialect module
# that imports HistoryError/Backend back from this module does not cycle.
_BACKEND_MAP: dict[str, tuple[str, str]] = {
    "sqlite": ("little_loops.session_store.backend", "SqliteBackend"),
}


def resolve_backend(provider: str = "sqlite") -> Backend:
    """Return a :class:`Backend` instance for *provider*.

    Raises:
        HistoryUnsupported: *provider* is not registered.
    """
    entry = _BACKEND_MAP.get(provider)
    if entry is None:
        raise HistoryUnsupported(
            f"Provider {provider!r} is not registered. Available: {sorted(_BACKEND_MAP)}."
        )
    module_path, class_name = entry
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


def _resolve_once(target: Path | str | None) -> Path:
    """Resolve *target* via :func:`resolve_history_db`, except for an
    already-absolute path, which is returned verbatim (BUG-3181).

    An absolute path is, by construction, either a deliberate override (a
    test fixture, a scratch export target) or was already resolved by an
    upstream root-aware caller (e.g. an MCP tool resolving with
    ``root=project_root``, which this module has no way to reconstruct).
    ``resolve_history_db``'s own default-shaped heuristic matches *any* path
    named ``.ll/history.db`` regardless of whether it is absolute (by
    design, for callers like hooks that construct a cwd-absolute path and
    still want env/config to be able to redirect it) — but re-applying that
    heuristic a second time here, with no ``root=`` context, is exactly the
    failure mode this guards against: a caller-supplied absolute path,
    resolved once under the correct root, must never be silently redirected
    by a second, root-less resolution under a different (or foreign) cwd.
    Only a genuinely unresolved argument (``None``, or a relative path) goes
    through the full env -> config -> default precedence here.
    """
    if target is None or not Path(target).is_absolute():
        return resolve_history_db(target)
    return Path(target)


def connect_readonly(target: Path | str | None = None) -> sqlite3.Connection:
    """Strict read-only open of the resolved history store (D19: never
    creates or migrates). Raises :class:`HistoryUnavailable` on failure.

    An already-absolute *target* is honored verbatim (BUG-3181, see
    :func:`_resolve_once`); ``None`` or a relative *target* resolves via the
    ``LL_HISTORY_DB`` -> ``history.db_path`` -> default precedence (see
    :func:`resolve_history_db`).
    """
    resolved = _resolve_once(target)
    return resolve_backend().connect_readonly(resolved)


def open_history(target: Path | str | None = None) -> sqlite3.Connection:
    """Open a writable connection, ensuring the schema first.

    An explicit *target* opens that file; a default-shaped *target* resolves
    via the existing ``resolve_history_db()`` precedence.
    """
    resolved = _resolve_once(target)
    return resolve_backend().connect(resolved)


def open_history_readonly(
    target: Path | str | None = None, *, ensure: bool = False
) -> sqlite3.Connection:
    """Open a read-only connection to the resolved history store.

    Resolves *target* exactly once (BUG-3181: an already-resolved absolute
    path is never re-resolved — resolution happens here, not again inside
    the backend calls this makes). With ``ensure=False`` (default), this is
    the strict contract: never creates or migrates (D19). With
    ``ensure=True``, runs :meth:`Backend.ensure_schema` on the resolved path
    over a separate writable connection, then opens that *same* path
    read-only — the caller always reads a current-schema store, and the
    migrate step and the read step can never target different files (the
    latent bug ``history_reader._base._connect_readonly()`` had before this
    module existed).

    Raises:
        HistoryUnavailable: the store could not be opened (or migrated, when
            ``ensure=True``).
    """
    resolved = _resolve_once(target)
    backend = resolve_backend()
    if ensure:
        try:
            backend.ensure_schema(resolved)
        except sqlite3.Error as exc:
            raise HistoryUnavailable(f"could not ensure schema for {resolved}: {exc}") from exc
    return backend.connect_readonly(resolved)

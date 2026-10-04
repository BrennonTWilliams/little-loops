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
import math
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from little_loops.session_store.db import resolve_history_target
from little_loops.session_store.deadline import PROGRESS_INTERVAL, Deadline
from little_loops.session_store.targets import (  # noqa: F401 - re-exported
    BackendConfig,
    HistoryTarget,
    LocalTarget,
    RemoteTarget,
)

BackendProvider = Literal["sqlite", "libsql"]


class HistoryError(Exception):
    """Base class for every backend-neutral history-store error."""


class HistoryUnavailable(HistoryError):
    """The store could not be opened (missing, locked, or otherwise unreachable)."""


class HistorySuppressed(HistoryUnavailable):
    """A best-effort write was skipped on purpose (unreachable marker, or a store that needs
    ``ll-session migrate``). Already reported once; callers log it at debug level only."""


class HistoryIntegrityError(HistoryError):
    """A write violated a constraint (unique/foreign-key/check)."""


class HistoryUnsupported(HistoryError):
    """The current backend does not support a requested capability.

    ``operation`` (FEAT-3535, keyword-only, optional) names the refused operation so a
    caller or user sees *what* was rejected, not just that something was.
    """

    def __init__(self, message: str = "", *, operation: str | None = None) -> None:
        super().__init__(message)
        self.operation = operation


class HistoryBackendNotLocal(HistoryUnsupported):
    """A filesystem path was requested for a store that has none (a remote target)."""


class HistoryOperationError(HistoryError):
    """A database operation failed for a reason other than the three above."""


# Why each operation is rejected under a remote store (Proposed Design, operation matrix).
_REMOTE_REFUSALS = {
    "rebuild": "it deletes derived tables globally with no concurrency guarantee",
    "backfill": "a full backfill overwrites rows other machines wrote",
    "prune": "it deletes raw_events other machines still use",
    "compact": "it rewrites raw_events other machines still use",
    "recompress": "it rewrites raw_events other machines still use",
    "snapshot_export": "it needs ATTACH to a local destination, which a remote store lacks",
}


def refuse_on_remote(db: Path | str | HistoryTarget | None, operation: str) -> None:
    """Raise :class:`HistoryUnsupported` naming *operation* when *db* resolves to a remote
    store, before anything is read or written (no network call is made).

    Local targets, including an explicit non-default path under a remote provider, pass.
    """
    target = resolve_history_target(db)
    if isinstance(target, RemoteTarget):
        why = _REMOTE_REFUSALS.get(operation, "it is a local-file operation")
        raise HistoryUnsupported(
            f"{operation} is not supported under history.backend provider "
            f"{target.provider!r}: {why}",
            operation=operation,
        )


def _describe(target: HistoryTarget) -> str:
    return str(target.path) if isinstance(target, LocalTarget) else f"{target.provider} store"


def _local_path(target: Path | str | HistoryTarget, operation: str) -> Path:
    """Return the filesystem path of a SQLite target, coercing a bare ``Path``.

    Raises:
        HistoryUnsupported: *target* is a :class:`RemoteTarget`.
    """
    if isinstance(target, RemoteTarget):
        raise HistoryUnsupported(
            f"SqliteBackend.{operation} does not support a {target.provider!r} target."
        )
    if isinstance(target, LocalTarget):
        return target.path
    return Path(target)


@contextmanager
def translate_sqlite_errors() -> Iterator[None]:
    """Translate a raw ``sqlite3`` exception raised inside the block into the
    matching :class:`HistoryError` subclass, preserving the original as
    ``__cause__``.

    Generalizes :meth:`SqliteBackend.connect_readonly`'s inline
    ``try/except sqlite3.Error`` wrap (ENH-3525's Option (a): narrow
    translation around driver calls, no ``HistoryConnection`` runtime wrapper)
    so a write call site with several ``execute()``/``commit()`` calls under
    one best-effort degrade boundary does not hand-roll the same
    try/except chain (ENH-3526).
    """
    try:
        yield
    except sqlite3.IntegrityError as exc:
        raise HistoryIntegrityError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise HistoryOperationError(str(exc)) from exc


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

    ENH-3650: the methods take ``Path | HistoryTarget`` (a bare ``Path`` is a
    :class:`LocalTarget`), so a remote store, which has no path, can be
    expressed at this seam.

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

    def connect(
        self, target: Path | HistoryTarget, *, check_same_thread: bool = True
    ) -> sqlite3.Connection: ...
    def connect_readonly(
        self,
        target: Path | HistoryTarget,
        *,
        timeout: float = 5.0,
        deadline: Deadline | None = None,
    ) -> sqlite3.Connection: ...
    def ensure_schema(self, target: Path | HistoryTarget) -> None: ...
    def supports(self, capability: str) -> bool: ...


# Closed set of capability names (FEAT-3535). ``wal`` covers the ``journal_mode`` and
# ``busy_timeout`` pragmas; ``snapshot_export`` covers exporting a local copy (ATTACH to a
# local destination). Gated behind supports(), not the Backend protocol itself.
CAPABILITIES = frozenset({"attach", "vacuum", "create_function", "wal", "snapshot_export"})
_SQLITE_CAPABILITIES = CAPABILITIES


_T = TypeVar("_T")

_LOCK_ERROR_CODES = frozenset({sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})


class _DeadlineConnection(sqlite3.Connection):
    """A strict read-only connection bound to one :class:`Deadline` for its whole lifetime.

    Opt-in only (``connect_readonly(..., deadline=...)``): ordinary connections are plain
    :class:`sqlite3.Connection` objects with no handler or cursor adapter. A progress handler
    installed for the connection's lifetime cancels execution *and* later fetching/iteration
    (``_DeadlineCursor`` keeps it active); the busy timeout is re-clamped to the remaining
    budget before every statement. Reuse after expiry is refused.
    """

    _deadline: Deadline
    _lock_timeout: float
    _lock_clamped: bool
    _tripped: bool

    def _bind(self, deadline: Deadline, lock_timeout: float) -> None:
        self._deadline = deadline
        self._lock_timeout = lock_timeout
        self._lock_clamped = False
        self._tripped = False
        self.set_progress_handler(self._progress, PROGRESS_INTERVAL)

    def _progress(self) -> int:
        if self._deadline.expired():
            self._tripped = True
            return 1
        return 0

    def _check_expired(self, what: str) -> None:
        if self._tripped or self._deadline.expired():
            self._tripped = True
            raise HistoryUnavailable(f"history read deadline expired before {what}")

    def _start_statement(self) -> None:
        """Refuse an expired connection and clamp the lock wait to the remaining budget."""
        self._check_expired("starting a statement")
        remaining = self._deadline.remaining()
        self._lock_clamped = remaining < self._lock_timeout
        wait = min(self._lock_timeout, remaining)
        plain = super().cursor(sqlite3.Cursor)  # bypass the guarded cursor: no recursion
        plain.execute(f"PRAGMA busy_timeout = {max(1, math.ceil(wait * 1000))}")

    def _translate(self, exc: sqlite3.Error) -> HistoryUnavailable | None:
        """The ``HistoryUnavailable`` for a deadline-caused failure, else ``None``."""
        code = getattr(exc, "sqlite_errorcode", None)
        if self._tripped or (code == sqlite3.SQLITE_INTERRUPT and self._deadline.expired()):
            self._tripped = True
            return HistoryUnavailable(f"history read deadline expired: {exc}")
        if self._lock_clamped and code in _LOCK_ERROR_CODES:
            self._tripped = self._deadline.expired()
            return HistoryUnavailable(f"history read deadline exhausted waiting on a lock: {exc}")
        return None

    def _run(self, call: Callable[[], _T]) -> _T:
        try:
            return call()
        except sqlite3.Error as exc:
            translated = self._translate(exc)
            if translated is None:
                raise
            raise translated from exc

    def _statement(self, call: Callable[[], _T]) -> _T:
        self._start_statement()
        return self._run(call)

    def cursor(self, factory: Any = None) -> Any:  # type: ignore[override]
        return super().cursor(_DeadlineCursor if factory is None else factory)

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        cur = self.cursor()
        return cur.execute(sql, parameters)  # type: ignore[no-any-return]

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> sqlite3.Cursor:
        cur = self.cursor()
        return cur.executemany(sql, seq_of_parameters)  # type: ignore[no-any-return]

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        cur = self.cursor()
        return cur.executescript(sql_script)  # type: ignore[no-any-return]

    def close(self) -> None:
        try:
            self.set_progress_handler(None, 0)
        except sqlite3.ProgrammingError:
            pass  # already closed
        super().close()


class _DeadlineCursor(sqlite3.Cursor):
    """Cursor of a :class:`_DeadlineConnection`: statements and fetches share its budget."""

    connection: _DeadlineConnection  # type: ignore[assignment]

    def execute(self, sql: str, parameters: Any = (), /) -> _DeadlineCursor:
        conn = self.connection
        conn._statement(lambda: super(_DeadlineCursor, self).execute(sql, parameters))
        return self

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> _DeadlineCursor:
        conn = self.connection
        conn._statement(lambda: super(_DeadlineCursor, self).executemany(sql, seq_of_parameters))
        return self

    def executescript(self, sql_script: str, /) -> _DeadlineCursor:
        conn = self.connection
        conn._statement(lambda: super(_DeadlineCursor, self).executescript(sql_script))
        return self

    def _fetch(self, call: Callable[[], _T]) -> _T:
        conn = self.connection
        conn._check_expired("fetching rows")
        result = conn._run(call)
        conn._check_expired("returning rows")
        return result

    def fetchone(self) -> Any:
        return self._fetch(lambda: super(_DeadlineCursor, self).fetchone())

    def fetchmany(self, size: int | None = None) -> list[Any]:
        count = self.arraysize if size is None else size
        return self._fetch(lambda: super(_DeadlineCursor, self).fetchmany(count))

    def fetchall(self) -> list[Any]:
        return self._fetch(lambda: super(_DeadlineCursor, self).fetchall())

    def __iter__(self) -> _DeadlineCursor:
        return self

    def __next__(self) -> Any:
        return self._fetch(lambda: super(_DeadlineCursor, self).__next__())


class SqliteBackend:
    """The only backend Phase A registers. Wraps ``schema.py``'s existing
    ``connect``/``ensure_db`` rather than reimplementing their migration and
    locking sequence."""

    provider = "sqlite"

    def supports(self, capability: str) -> bool:
        return capability in _SQLITE_CAPABILITIES

    def connect(
        self, target: Path | HistoryTarget, *, check_same_thread: bool = True
    ) -> sqlite3.Connection:
        """Open a writable connection, ensuring the schema first.

        ``check_same_thread=False`` opens a connection for a caller that
        manages its own cross-thread synchronization (``SQLiteTransport``
        keeps one long-lived connection shared across threads behind its own
        lock, ENH-3526) -- ``schema.connect()``'s two-connection-per-call
        shape has no such parameter and stays unchanged for every other
        caller (the default path here delegates to it verbatim).

        Raises:
            HistoryUnsupported: *target* is a :class:`RemoteTarget`.
        """
        path = _local_path(target, "connect")
        if check_same_thread:
            from little_loops.session_store.schema import connect as _connect

            return _connect(path)
        from little_loops.session_store.schema import _configure_connection, ensure_db

        try:
            ensure_db(path)
            conn = sqlite3.connect(str(path), check_same_thread=False)
            _configure_connection(conn)
        except sqlite3.Error as exc:
            raise HistoryUnavailable(f"could not open {path}: {exc}") from exc
        return conn

    def connect_readonly(
        self,
        target: Path | HistoryTarget,
        *,
        timeout: float = 5.0,
        deadline: Deadline | None = None,
    ) -> sqlite3.Connection:
        """Strict read-only open: never creates or migrates the store (D19).

        *timeout* is sqlite's busy timeout in seconds (default matches sqlite's own).
        *deadline* (ENH-3720, opt-in) binds the connection to one absolute expiry for its whole
        lifetime: opening, execution, fetching and iteration all spend it, lock waits are
        re-clamped to the remaining budget before each statement, and expiry raises
        :class:`HistoryUnavailable` (SQLite cause preserved). A connection opened without one is
        a plain :class:`sqlite3.Connection`.
        """
        path = _local_path(target, "connect_readonly")
        if deadline is not None:
            return self._connect_readonly_bound(path, timeout, deadline)
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
        except sqlite3.Error as exc:
            raise HistoryUnavailable(f"could not open {path} read-only: {exc}") from exc
        return conn

    @staticmethod
    def _connect_readonly_bound(
        path: Path, timeout: float, deadline: Deadline
    ) -> sqlite3.Connection:
        if deadline.expired():
            raise HistoryUnavailable(f"history read deadline expired before opening {path}")
        conn: _DeadlineConnection | None = None
        try:
            conn = sqlite3.connect(
                f"file:{path}?mode=ro",
                uri=True,
                timeout=min(timeout, deadline.remaining()),
                factory=_DeadlineConnection,
            )
            conn.row_factory = sqlite3.Row
            conn._bind(deadline, timeout)
            conn.execute("PRAGMA query_only = ON")
            conn._check_expired("completing the open")
        except (sqlite3.Error, HistoryUnavailable) as exc:
            if conn is not None:
                conn.close()
            if isinstance(exc, HistoryUnavailable):
                raise
            raise HistoryUnavailable(f"could not open {path} read-only: {exc}") from exc
        return conn

    def ensure_schema(self, target: Path | HistoryTarget) -> None:
        from little_loops.session_store.schema import ensure_db

        ensure_db(_local_path(target, "ensure_schema"))


# Lazy-import registry: provider -> (module_path, class_name). Mirrors
# codequery.core._PROVIDER_MAP; kept lazy so a future "libsql" dialect module
# that imports HistoryError/Backend back from this module does not cycle.
_BACKEND_MAP: dict[str, tuple[str, str]] = {
    "sqlite": ("little_loops.session_store.backend", "SqliteBackend"),
    "libsql": ("little_loops.session_store.libsql", "LibsqlBackend"),
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


def _resolve_once(
    target: Path | str | HistoryTarget | None, *, reresolve_absolute: bool = False
) -> HistoryTarget:
    """Resolve *target* to a :class:`HistoryTarget`.

    A :class:`RemoteTarget` is produced only when ``history.backend.provider`` is a remote
    provider and *target* is default-shaped (``None`` or ``.ll/history.db``) with
    ``LL_HISTORY_DB`` unset (FEAT-3535); every other input yields a :class:`LocalTarget`.

    An already-typed target passes through untouched. Otherwise the path is
    resolved via :func:`resolve_history_db`, except for an already-absolute
    path, which is returned verbatim (BUG-3181).

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

    ``reresolve_absolute=True`` is for the ``schema.connect``/``ensure_db``
    seam only: it applies the full precedence to an absolute path as well,
    which is exactly what ``ensure_db`` always did (the hooks hand it a
    cwd-absolute ``.ll/history.db`` and rely on env/config redirecting it).
    """
    if isinstance(target, (LocalTarget, RemoteTarget)):
        return target
    if target is None or reresolve_absolute or not Path(target).is_absolute():
        return resolve_history_target(target)
    return LocalTarget(Path(target))


def connect_readonly(
    target: Path | str | HistoryTarget | None = None,
    *,
    timeout: float = 5.0,
    deadline: Deadline | None = None,
) -> sqlite3.Connection:
    """Strict read-only open of the resolved history store (D19: never
    creates or migrates). Raises :class:`HistoryUnavailable` on failure.
    *timeout* is the sqlite busy timeout in seconds (ignored by remote backends).
    *deadline* (ENH-3720, opt-in) is one absolute :class:`~little_loops.session_store.deadline.Deadline`
    spent across the connection's whole lifetime — opening, remote access verification and every
    later read; expiry raises :class:`HistoryUnavailable` (``HranaUnavailable`` remotely) and an
    expired connection refuses further reads. Omitted, behavior is unchanged.

    An already-absolute *target* is honored verbatim (BUG-3181, see
    :func:`_resolve_once`); ``None`` or a relative *target* resolves via the
    ``LL_HISTORY_DB`` -> ``history.db_path`` -> default precedence (see
    :func:`resolve_history_db`).
    """
    resolved = _resolve_once(target)
    return resolve_backend(resolved.provider).connect_readonly(
        resolved, timeout=timeout, deadline=deadline
    )


def open_history(
    target: Path | str | HistoryTarget | None = None,
    *,
    check_same_thread: bool = True,
    telemetry: bool = False,
) -> sqlite3.Connection:
    """Open a writable connection, ensuring the schema first.

    An explicit *target* opens that file; a default-shaped *target* resolves
    via the existing ``resolve_history_db()`` precedence. ``check_same_thread``
    is forwarded to :meth:`Backend.connect` (ENH-3526: ``SQLiteTransport``'s
    long-lived cross-thread connection). ``telemetry=True`` (FEAT-3535) marks a best-effort
    caller: a remote backend then applies its telemetry latency budget; SQLite ignores it.
    """
    resolved = _resolve_once(target)
    backend = resolve_backend(resolved.provider)
    if telemetry and hasattr(backend, "connect_telemetry"):
        return backend.connect_telemetry(resolved)  # type: ignore[no-any-return]
    return backend.connect(resolved, check_same_thread=check_same_thread)


def open_history_readonly(
    target: Path | str | HistoryTarget | None = None, *, ensure: bool = False
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
    backend = resolve_backend(resolved.provider)
    if ensure:
        try:
            backend.ensure_schema(resolved)
        except sqlite3.Error as exc:
            raise HistoryUnavailable(
                f"could not ensure schema for {_describe(resolved)}: {exc}"
            ) from exc
    return backend.connect_readonly(resolved)

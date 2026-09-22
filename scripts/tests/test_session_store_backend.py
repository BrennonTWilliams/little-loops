"""Tests for the session-store backend chokepoint (ENH-3525, FEAT-3524 Phase A).

Promotes the registry/protocol-conformance shape from
``test_codequery_core.py::TestResolveProvider`` and the locking-sequence /
idempotent-``ensure_schema`` / concurrent-migration / capability-gate tests
from the spike at ``scripts/tests/spike/session_store_backend_dialect/``,
adapted from the spike's ``resolve_backend(kind, db_path)`` shape to the
promoted module's ``resolve_backend(provider="sqlite")`` (path passed
per-call, not to the constructor).
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from little_loops.session_store.backend import (
    Backend,
    HistoryConnection,
    HistoryUnavailable,
    HistoryUnsupported,
    SqliteBackend,
    connect_readonly,
    open_history,
    open_history_readonly,
    resolve_backend,
)


def _mark(db_path, value: str) -> None:
    """Write a distinguishing `meta` row so a test can prove *which* file a
    connection actually opened."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('which', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (value,),
        )
        conn.commit()
    finally:
        conn.close()


class TestResolveBackend:
    def test_sqlite_resolves(self) -> None:
        backend = resolve_backend("sqlite")
        assert isinstance(backend, SqliteBackend)
        assert backend.provider == "sqlite"

    def test_default_provider_is_sqlite(self) -> None:
        assert isinstance(resolve_backend(), SqliteBackend)

    def test_unknown_provider_raises_typed_error(self) -> None:
        with pytest.raises(HistoryUnsupported, match="not registered"):
            resolve_backend("postgres")


class TestProtocolConformance:
    """Mirrors test_codequery_core.py::TestProtocolConformance -- extend this
    class for a later "libsql" provider (FEAT-3524)."""

    def test_sqlite_backend_satisfies_backend_protocol(self) -> None:
        assert isinstance(SqliteBackend(), Backend)

    def test_connection_satisfies_history_connection_protocol(self, tmp_path) -> None:
        db_path = tmp_path / "history.db"
        backend = resolve_backend("sqlite")
        backend.ensure_schema(db_path)
        conn = backend.connect(db_path)
        try:
            assert isinstance(conn, HistoryConnection)
        finally:
            conn.close()


class TestDialectMigration:
    def test_sqlite_backend_migrates_and_reports_current_version(self, tmp_path) -> None:
        db_path = tmp_path / "history.db"
        backend = resolve_backend("sqlite")

        backend.ensure_schema(db_path)

        conn = backend.connect(db_path)
        try:
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert int(version) > 0
        finally:
            conn.close()

    def test_rerunning_ensure_schema_is_idempotent(self, tmp_path) -> None:
        db_path = tmp_path / "history.db"
        backend = resolve_backend("sqlite")

        backend.ensure_schema(db_path)
        conn = backend.connect(db_path)
        try:
            first_version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
        finally:
            conn.close()

        # A second ensure_schema() against the same file must not re-run
        # migrations or raise "table already exists".
        backend.ensure_schema(db_path)
        conn = backend.connect(db_path)
        try:
            second_version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert second_version == first_version


class TestCapabilityGate:
    def test_sqlite_supports_expected_capabilities(self) -> None:
        backend = resolve_backend("sqlite")
        assert backend.supports("attach") is True
        assert backend.supports("vacuum") is True
        assert backend.supports("create_function") is True

    def test_sqlite_does_not_support_unknown_capability(self) -> None:
        backend = resolve_backend("sqlite")
        assert backend.supports("network_replication") is False


class TestConcurrentMigration:
    def test_concurrent_ensure_schema_race_still_serializes(self, tmp_path) -> None:
        db_path = tmp_path / "race.db"
        errors: list[BaseException] = []
        barrier = threading.Barrier(4)

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                resolve_backend("sqlite").ensure_schema(db_path)
            except BaseException as exc:  # noqa: BLE001 - capture for assertion
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"concurrent ensure_schema raised: {errors}"

        conn = sqlite3.connect(str(db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert count == 1
        finally:
            conn.close()


class TestConnectReadonlyStrict:
    """D19: never creates or migrates the store."""

    def test_missing_store_raises_history_unavailable(self, tmp_path) -> None:
        db_path = tmp_path / "does-not-exist" / "history.db"
        with pytest.raises(HistoryUnavailable):
            connect_readonly(db_path)
        assert not db_path.parent.exists(), "strict connect_readonly must not create anything"

    def test_existing_store_is_byte_identical_before_and_after(self, tmp_path) -> None:
        import hashlib

        db_path = tmp_path / "history.db"
        resolve_backend("sqlite").ensure_schema(db_path)
        before = hashlib.sha256(db_path.read_bytes()).hexdigest()

        conn = connect_readonly(db_path)
        conn.execute("SELECT 1").fetchone()
        conn.close()

        after = hashlib.sha256(db_path.read_bytes()).hexdigest()
        assert after == before

    def test_write_attempt_is_rejected(self, tmp_path) -> None:
        db_path = tmp_path / "history.db"
        resolve_backend("sqlite").ensure_schema(db_path)

        conn = connect_readonly(db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO meta(key, value) VALUES ('x', 'y')")
        finally:
            conn.close()

    def test_explicit_non_default_shaped_path_bypasses_env_override(self, tmp_path, monkeypatch):
        """A deliberate override path (not named `.ll/history.db`) is
        honored verbatim -- LL_HISTORY_DB only redirects a *default-shaped*
        argument (`resolve_history_db`'s own contract)."""
        explicit = tmp_path / "explicit.db"
        resolve_backend("sqlite").ensure_schema(explicit)
        _mark(explicit, "explicit")

        elsewhere = tmp_path / "elsewhere.db"
        resolve_backend("sqlite").ensure_schema(elsewhere)
        _mark(elsewhere, "elsewhere")
        monkeypatch.setenv("LL_HISTORY_DB", str(elsewhere))

        conn = connect_readonly(explicit)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'which'").fetchone()
            assert row[0] == "explicit"
        finally:
            conn.close()


class TestOpenHistoryReadonlyEnsureThenRead:
    def test_ensure_true_migrates_and_opens_same_resolved_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        db_path = tmp_path / "history.db"
        assert not db_path.exists()

        conn = open_history_readonly(db_path, ensure=True)
        try:
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert int(version) > 0
        finally:
            conn.close()
        assert db_path.exists()

    def test_ensure_false_is_strict_and_raises_on_missing_store(self, tmp_path):
        db_path = tmp_path / "history.db"
        with pytest.raises(HistoryUnavailable):
            open_history_readonly(db_path, ensure=False)
        assert not db_path.exists()

    def test_single_resolve_migrates_and_opens_the_same_target(self, tmp_path, monkeypatch):
        """The latent bug this fixes: the old history_reader._base inline
        implementation called ensure_db(db_path) (which re-resolves a
        default-shaped path via LL_HISTORY_DB), discarded the resolved
        return value, and reopened the caller's unresolved db_path -- so a
        default-shaped argument could migrate one file and open another.
        open_history_readonly resolves once and uses that same path for both
        steps."""
        real_target = tmp_path / "real.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(real_target))

        # A default-shaped argument (None) resolves to LL_HISTORY_DB's target.
        conn = open_history_readonly(None, ensure=True)
        try:
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        finally:
            conn.close()
        assert real_target.exists()


class TestOpenHistory:
    def test_open_history_ensures_schema_and_returns_writable_connection(self, tmp_path):
        db_path = tmp_path / "history.db"
        conn = open_history(db_path)
        try:
            conn.execute("INSERT INTO meta(key, value) VALUES ('probe', '1')")
            conn.commit()
        finally:
            conn.close()


class TestHistoryDbUnavailableSubclass:
    def test_history_db_unavailable_is_a_history_unavailable(self) -> None:
        from little_loops.issue_history.parsing import HistoryDbUnavailable

        assert issubclass(HistoryDbUnavailable, HistoryUnavailable)

        def raiser():
            raise HistoryDbUnavailable("boom")

        with pytest.raises(HistoryUnavailable):
            raiser()

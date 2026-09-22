"""AC suite for the FEAT-3524 session_store backend/dialect abstraction spike.

Retires the issue's flagged risk: no dialect abstraction exists anywhere in
the codebase today, and no existing test exercises a capability-flag-gated
feature degrading instead of crashing. See
``.ll/spikes/spike-FEAT-3524.md``.
"""

from __future__ import annotations

import ast
import sqlite3
import threading
from pathlib import Path

import pytest

from scripts.tests.spike.session_store_backend_dialect.backend import (
    UnsupportedCapability,
    require_capability,
    resolve_backend,
)


class TestDialectMigration:
    def test_sqlite_backend_migrates_with_existing_locking_sequence(self, tmp_path):
        backend = resolve_backend("sqlite", tmp_path / "sqlite.db")

        backend.ensure_schema()

        conn = backend.connect()
        try:
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert int(version) == len(backend.migrations())

            widgets_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'widgets'"
            ).fetchone()[0]
            assert "AUTOINCREMENT" in widgets_sql

            conn.execute("INSERT INTO widgets(name) VALUES ('gizmo')")
            conn.commit()
            row = conn.execute("SELECT name FROM widgets").fetchone()
            assert row[0] == "gizmo"
        finally:
            conn.close()

    def test_stub_remote_backend_uses_dialect_specific_ddl(self, tmp_path):
        backend = resolve_backend("stub_remote", tmp_path / "remote.db")

        backend.ensure_schema()

        conn = backend.connect()
        try:
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert int(version) == len(backend.migrations())

            widgets_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'widgets'"
            ).fetchone()[0]
            assert "AUTOINCREMENT" not in widgets_sql

            # Still a working schema despite the different DDL.
            conn.execute("INSERT INTO widgets(name) VALUES ('gizmo')")
            conn.commit()
            row = conn.execute("SELECT name FROM widgets").fetchone()
            assert row[0] == "gizmo"
        finally:
            conn.close()

    def test_rerunning_ensure_schema_is_idempotent(self, tmp_path):
        db_path = tmp_path / "sqlite.db"
        resolve_backend("sqlite", db_path).ensure_schema()

        # A second backend instance against the same file must not re-run
        # migrations or raise "table already exists".
        resolve_backend("sqlite", db_path).ensure_schema()

        conn = sqlite3.connect(str(db_path))
        try:
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert int(version) == 2
        finally:
            conn.close()


class TestCapabilityGate:
    def test_capability_check_gates_unsupported_feature(self, tmp_path):
        remote = resolve_backend("stub_remote", tmp_path / "remote.db")
        assert remote.supports("fts5") is False

        with pytest.raises(UnsupportedCapability, match="'fts5'.*'stub_remote'"):
            require_capability(remote, "fts5")

    def test_capability_check_passes_for_supported_feature(self, tmp_path):
        sqlite_backend = resolve_backend("sqlite", tmp_path / "sqlite.db")
        assert sqlite_backend.supports("fts5") is True

        require_capability(sqlite_backend, "fts5")  # must not raise


class TestConcurrentMigration:
    def test_concurrent_migration_race_still_serializes(self, tmp_path):
        db_path = tmp_path / "race.db"
        errors: list[BaseException] = []
        barrier = threading.Barrier(4)

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                resolve_backend("sqlite", db_path).ensure_schema()
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
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert int(version) == 2
            # Exactly one meta row for schema_version -- no duplicate-insert
            # races slipped past the BEGIN IMMEDIATE lock.
            count = conn.execute(
                "SELECT COUNT(*) FROM meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            assert count == 1
        finally:
            conn.close()


class TestSpikeIsolation:
    def test_spike_does_not_import_production_session_store(self):
        spike_dir = Path(__file__).parent
        for source_file in ("backend.py", "dialects.py"):
            tree = ast.parse((spike_dir / source_file).read_text(encoding="utf-8"))
            imported_names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported_names.add(node.module)
                elif isinstance(node, ast.Import):
                    imported_names.update(alias.name for alias in node.names)

            assert not any(
                name == "little_loops.session_store" or name.startswith("little_loops.session_store.")
                for name in imported_names
            ), f"{source_file} imports production little_loops.session_store: {imported_names}"

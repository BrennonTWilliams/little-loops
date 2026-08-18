"""Tests for cli/doctor.py's install-surface checks (FEAT-2794)."""

from __future__ import annotations

from pathlib import Path

from little_loops.cli.doctor import (
    _decisions_store_data,
    _entry_points_data,
    _history_db_data,
    _skills_commands_data,
)


class TestEntryPoints:
    """Tests for `_entry_points_data()`."""

    def _write_pyproject(self, tmp_path: Path, scripts: dict[str, str]) -> Path:
        pyproject = tmp_path / "pyproject.toml"
        lines = ["[project.scripts]"]
        lines.extend(f'{name} = "{target}"' for name, target in scripts.items())
        pyproject.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return pyproject

    def test_resolvable_entry_point_is_full(self, tmp_path: Path) -> None:
        pyproject = self._write_pyproject(tmp_path, {"ll-doctor": "little_loops.cli:main_doctor"})
        rows = _entry_points_from_pyproject(pyproject)
        assert rows == [{"name": "ll-doctor", "status": "full", "note": ""}]

    def test_missing_module_reports_unsupported(self, tmp_path: Path) -> None:
        pyproject = self._write_pyproject(tmp_path, {"ll-fake": "no_such_module_xyz:main"})
        rows = _entry_points_from_pyproject(pyproject)
        assert rows[0]["status"] == "unsupported"
        assert "module not found" in rows[0]["note"]

    def test_missing_function_reports_unsupported(self, tmp_path: Path) -> None:
        pyproject = self._write_pyproject(tmp_path, {"ll-fake": "little_loops.cli:no_such_func"})
        rows = _entry_points_from_pyproject(pyproject)
        assert rows[0]["status"] == "unsupported"
        assert "not found" in rows[0]["note"]

    def test_real_pyproject_all_entry_points_resolve(self) -> None:
        """Against the real repo, every declared entry point should resolve."""
        rows = _entry_points_data()
        assert rows, "expected at least one [project.scripts] entry"
        failures = [r for r in rows if r["status"] != "full"]
        assert failures == []


def _entry_points_from_pyproject(pyproject_path: Path) -> list[dict[str, str]]:
    """Test helper: run the same import-resolution logic against a tmp pyproject."""
    import importlib
    import tomllib

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    scripts: dict[str, str] = data.get("project", {}).get("scripts", {})

    rows: list[dict[str, str]] = []
    for name, target in sorted(scripts.items()):
        module_path, _, func_name = target.partition(":")
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            rows.append({"name": name, "status": "unsupported", "note": f"module not found: {exc}"})
            continue
        if not hasattr(module, func_name):
            rows.append(
                {
                    "name": name,
                    "status": "unsupported",
                    "note": f"{module_path}.{func_name} not found (function renamed/removed)",
                }
            )
            continue
        rows.append({"name": name, "status": "full", "note": ""})
    return rows


class TestSkillsCommands:
    """Tests for `_skills_commands_data()`."""

    def test_patches_assemble_tool_catalog_at_import_site(self, monkeypatch) -> None:
        """Per AC: patch assemble_tool_catalog() at the cli.doctor import site,
        not re-derive test_tool_catalog.py's coverage."""
        import little_loops.tool_catalog as tool_catalog_mod

        fake_entries = [object(), object(), object()]
        monkeypatch.setattr(
            tool_catalog_mod, "assemble_tool_catalog", lambda project_root: fake_entries
        )

        data = _skills_commands_data()

        assert data["status"] == "full"
        assert data["total"] == 3

    def test_oserror_reports_unsupported(self, monkeypatch) -> None:
        import little_loops.tool_catalog as tool_catalog_mod

        def _boom(project_root: Path) -> list:
            raise OSError("disk gone")

        monkeypatch.setattr(tool_catalog_mod, "assemble_tool_catalog", _boom)

        data = _skills_commands_data()

        assert data["status"] == "unsupported"
        assert "catalog load failed" in data["note"]


class TestDecisionsStore:
    """Tests for `_decisions_store_data()`. Mirrors test_verify_decisions.py's fixtures."""

    def test_absent_is_informational(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        data = _decisions_store_data()
        assert data == {
            "status": "unsupported",
            "severity": "informational",
            "note": "not configured (optional)",
        }

    def test_valid_flat_file_is_healthy(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "decisions.yaml").write_text("entries: []\n", encoding="utf-8")

        data = _decisions_store_data()

        assert data["status"] == "full"
        assert data["severity"] == "error"

    def test_yaml_corruption_reports_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "decisions.yaml").write_text('rationale: "abc "" def"\n', encoding="utf-8")

        data = _decisions_store_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "error"

    def test_corrupt_fragment_reports_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        frag_dir = tmp_path / ".ll" / "decisions.d"
        frag_dir.mkdir(parents=True)
        (frag_dir / "bad.json").write_text("{not valid json", encoding="utf-8")

        data = _decisions_store_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "error"


class TestHistoryDb:
    """Tests for `_history_db_data()`."""

    def test_absent_is_informational_and_does_not_create(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        data = _history_db_data()

        assert data == {
            "status": "unsupported",
            "severity": "informational",
            "note": "not yet created",
        }
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_present_and_readable_is_full(self, tmp_path: Path, monkeypatch) -> None:
        import sqlite3

        monkeypatch.chdir(tmp_path)
        db_dir = tmp_path / ".ll"
        db_dir.mkdir()
        db_path = db_dir / "history.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()

        data = _history_db_data()

        assert data["status"] == "full"
        assert data["severity"] == "error"

    def test_present_but_corrupt_reports_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        db_dir = tmp_path / ".ll"
        db_dir.mkdir()
        db_path = db_dir / "history.db"
        db_path.write_bytes(b"not a sqlite file at all, just garbage bytes 1234567890")

        data = _history_db_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "error"


def _bootstrap_at(db: Path, version: int) -> None:
    """Bootstrap a database at an exact historical schema *version*.

    Mirrors ``test_session_store_schema.py::_bootstrap_schema_at`` — kept as a
    separate copy since that module isn't a public import surface for this file.
    """
    import sqlite3

    from little_loops.session_store.schema import _MIGRATIONS, _split_sql_statements

    conn = sqlite3.connect(str(db))
    try:
        for script in _MIGRATIONS[:version]:
            for stmt in _split_sql_statements(script):
                conn.execute(stmt)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
    finally:
        conn.close()


class TestSchemaDrift:
    """Tests for `_schema_drift_data()` (ENH-3242 piece 2)."""

    def test_absent_is_informational_and_does_not_create(self, tmp_path: Path, monkeypatch) -> None:
        from little_loops.cli.doctor import _schema_drift_data

        monkeypatch.chdir(tmp_path)

        data = _schema_drift_data()

        assert data == {
            "status": "unsupported",
            "severity": "informational",
            "note": "not yet created",
        }
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_healthy_current_version_is_full(self, tmp_path: Path, monkeypatch) -> None:
        from little_loops.cli.doctor import _schema_drift_data
        from little_loops.session_store import ensure_db

        monkeypatch.chdir(tmp_path)
        ensure_db(tmp_path / ".ll" / "history.db")

        data = _schema_drift_data()

        assert data["status"] == "full"
        assert data["severity"] == "error"

    def test_missing_meta_table_is_informational(self, tmp_path: Path, monkeypatch) -> None:
        import sqlite3

        from little_loops.cli.doctor import _schema_drift_data

        monkeypatch.chdir(tmp_path)
        db_dir = tmp_path / ".ll"
        db_dir.mkdir()
        db_path = db_dir / "history.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
        conn.commit()
        conn.close()

        data = _schema_drift_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"
        assert "uninitialized" in data["note"]

    def test_dropped_view_column_is_reported(self, tmp_path: Path, monkeypatch) -> None:
        """BUG-3236 shape: a view stamped current but missing a column."""
        import sqlite3

        from little_loops.cli.doctor import _schema_drift_data
        from little_loops.session_store import SCHEMA_VERSION, ensure_db

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        ensure_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP VIEW issue_sessions")
        conn.execute(
            """
            CREATE VIEW issue_sessions AS
            SELECT ie.issue_id, me.session_id, s.jsonl_path, MIN(me.ts) AS first_message_ts
            FROM issue_events ie
            JOIN message_events me ON me.ts >= ie.captured_at
            LEFT JOIN sessions s ON s.session_id = me.session_id
            WHERE ie.captured_at IS NOT NULL
            GROUP BY ie.issue_id, me.session_id
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
        conn.close()

        data = _schema_drift_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "error"
        assert "issue_sessions" in data["note"]

    def test_dropped_index_is_reported(self, tmp_path: Path, monkeypatch) -> None:
        """BUG-3241 shape: an index missing from a database stamped current."""
        import sqlite3

        from little_loops.cli.doctor import _schema_drift_data
        from little_loops.session_store import ensure_db

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        ensure_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP INDEX idx_assistant_messages_dedup")
        conn.commit()
        conn.close()

        data = _schema_drift_data()

        assert data["status"] == "unsupported"
        assert "idx_assistant_messages_dedup" in data["note"]

    def test_degraded_index_losing_unique_is_reported(self, tmp_path: Path, monkeypatch) -> None:
        """The name-only-manifest blind spot BUG-3241 needed caught: an index
        present by name but no longer UNIQUE."""
        import sqlite3

        from little_loops.cli.doctor import _schema_drift_data
        from little_loops.session_store import ensure_db

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        ensure_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP INDEX idx_assistant_messages_dedup")
        conn.execute(
            "CREATE INDEX idx_assistant_messages_dedup "
            "ON assistant_messages(session_id, ts, content)"
        )
        conn.commit()
        conn.close()

        data = _schema_drift_data()

        assert data["status"] == "unsupported"
        assert "idx_assistant_messages_dedup" in data["note"]

    def test_behind_clean_database_reports_no_drift(self, tmp_path: Path, monkeypatch) -> None:
        from little_loops.cli.doctor import _schema_drift_data

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir()
        _bootstrap_at(db_path, 41)

        data = _schema_drift_data()

        assert data["status"] == "full"
        assert "behind" in data["note"]

    def test_behind_drifted_database_reports_drift(self, tmp_path: Path, monkeypatch) -> None:
        import sqlite3

        from little_loops.cli.doctor import _schema_drift_data

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir()
        _bootstrap_at(db_path, 41)
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP INDEX idx_assistant_messages_dedup")
        conn.commit()
        conn.close()

        data = _schema_drift_data()

        assert data["status"] == "unsupported"
        assert "idx_assistant_messages_dedup" in data["note"]

    def test_version_ahead_is_a_finding_not_informational(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A recorded version beyond what this install's migrations know about
        is a read-only detection finding (BUG-3255's guarded clamp only fires
        via `ensure_db()`, which this check never calls)."""
        import sqlite3

        from little_loops.cli.doctor import _schema_drift_data
        from little_loops.session_store import SCHEMA_VERSION, ensure_db

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        ensure_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 2),),
        )
        conn.commit()
        conn.close()

        data = _schema_drift_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "error"
        assert str(SCHEMA_VERSION) in data["note"]
        assert str(SCHEMA_VERSION + 2) in data["note"]

    def test_never_creates_or_migrates_database(self, tmp_path: Path, monkeypatch) -> None:
        from little_loops.cli.doctor import _schema_drift_data

        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir()
        _bootstrap_at(db_path, 41)
        before = db_path.read_bytes()

        _schema_drift_data()

        assert db_path.read_bytes() == before


class TestLoopValidity:
    """Tests for `_loop_validity_data()`."""

    def test_no_loops_is_informational(self, tmp_path: Path, monkeypatch) -> None:
        import little_loops.cli.doctor as doctor_mod

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "little_loops.cli.loop._helpers.get_builtin_loops_dir",
            lambda: tmp_path / "no-such-builtin-loops",
        )

        data = doctor_mod._loop_validity_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "informational"
        assert data["total"] == 0

    def test_valid_loop_reports_full(self, tmp_path: Path, monkeypatch) -> None:
        import little_loops.cli.doctor as doctor_mod

        monkeypatch.chdir(tmp_path)
        builtin_dir = tmp_path / "builtin-loops"
        builtin_dir.mkdir()
        (builtin_dir / "good.yaml").write_text(
            "name: good\ndescription: test\ninitial: start\nstates:\n"
            "  start:\n    terminal: true\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "little_loops.cli.loop._helpers.get_builtin_loops_dir", lambda: builtin_dir
        )

        data = doctor_mod._loop_validity_data()

        assert data["status"] == "full"
        assert data["total"] == 1

    def test_invalid_loop_reports_error(self, tmp_path: Path, monkeypatch) -> None:
        import little_loops.cli.doctor as doctor_mod

        monkeypatch.chdir(tmp_path)
        builtin_dir = tmp_path / "builtin-loops"
        builtin_dir.mkdir()
        (builtin_dir / "bad.yaml").write_text(
            "name: bad\ninitial: nonexistent_state\nstates:\n  start:\n    type: terminal\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "little_loops.cli.loop._helpers.get_builtin_loops_dir", lambda: builtin_dir
        )

        data = doctor_mod._loop_validity_data()

        assert data["status"] == "unsupported"
        assert data["severity"] == "error"
        assert data["invalid"]

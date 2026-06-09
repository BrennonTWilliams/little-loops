"""Tests for correction retirement: record_retirement() + list_retirements() (ENH-2046)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _make_test_db(tmp_path: Path) -> Path:
    from little_loops.session_store import ensure_db

    db = tmp_path / "test.db"
    ensure_db(db)
    return db


class TestCorrectionRetirement:
    """Tests for record_retirement() and list_retirements()."""

    def test_list_retirements_empty(self, tmp_path: Path) -> None:
        """Empty DB returns an empty list."""
        db = _make_test_db(tmp_path)
        from little_loops.session_store import list_retirements

        result = list_retirements(db)
        assert result == []

    def test_record_retirement_persists(self, tmp_path: Path) -> None:
        """record_retirement() writes a record that list_retirements() returns."""
        db = _make_test_db(tmp_path)
        from little_loops.session_store import list_retirements, record_retirement

        record_retirement(db, "abc123fingerprint", rule_id="RULE-001", session_id="sess-xyz")
        rows = list_retirements(db)
        assert len(rows) == 1
        assert rows[0]["topic_fingerprint"] == "abc123fingerprint"
        assert rows[0]["rule_id"] == "RULE-001"
        assert rows[0]["session_id"] == "sess-xyz"
        assert rows[0]["addressed_at"]  # non-empty timestamp

    def test_record_retirement_idempotent(self, tmp_path: Path) -> None:
        """Second record_retirement() for same fingerprint replaces, not duplicates."""
        db = _make_test_db(tmp_path)
        from little_loops.session_store import list_retirements, record_retirement

        record_retirement(db, "fp1", rule_id="RULE-001")
        record_retirement(db, "fp1", rule_id="RULE-002")  # replace
        rows = list_retirements(db)
        assert len(rows) == 1
        assert rows[0]["rule_id"] == "RULE-002"

    def test_record_retirement_survives_reopen(self, tmp_path: Path) -> None:
        """Retirement record persists across close/reopen."""
        db = _make_test_db(tmp_path)
        from little_loops.session_store import list_retirements, record_retirement

        record_retirement(db, "persistent-fp", rule_id="RULE-003")

        # Re-import and re-query simulates a new process
        rows = list_retirements(db)
        assert any(r["topic_fingerprint"] == "persistent-fp" for r in rows)

    def test_record_retirement_optional_fields(self, tmp_path: Path) -> None:
        """record_retirement() works with only fingerprint (rule_id + session_id optional)."""
        db = _make_test_db(tmp_path)
        from little_loops.session_store import list_retirements, record_retirement

        record_retirement(db, "bare-fp")
        rows = list_retirements(db)
        assert len(rows) == 1
        assert rows[0]["topic_fingerprint"] == "bare-fp"

    def test_multiple_retirements(self, tmp_path: Path) -> None:
        """Multiple distinct fingerprints are stored independently."""
        db = _make_test_db(tmp_path)
        from little_loops.session_store import list_retirements, record_retirement

        record_retirement(db, "fp-a", rule_id="RULE-010")
        record_retirement(db, "fp-b", rule_id="RULE-011")
        rows = list_retirements(db)
        fingerprints = {r["topic_fingerprint"] for r in rows}
        assert fingerprints == {"fp-a", "fp-b"}

    def test_retirement_table_created_by_migration(self, tmp_path: Path) -> None:
        """The correction_retirements table exists after ensure_db()."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='correction_retirements'"
            ).fetchone()
            assert result is not None, "correction_retirements table not found"
        finally:
            conn.close()

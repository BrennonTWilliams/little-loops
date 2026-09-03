"""Tests for digest.py: project-digest section providers (ENH-1907) (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.history_reader import (
    project_digest,
    render_project_context,
)
from little_loops.session_store import (
    connect,
    ensure_db,
    record_correction,
)


class TestProjectDigest:
    """Tests for project_digest() and render_project_context() (ENH-1907)."""

    def _insert_file_event(self, db: Path, path: str, ts: str | None = None) -> None:
        # Default to a recent timestamp so "fresh row" assertions stay inside the
        # digest's day window regardless of the wall-clock date the suite runs on.
        ts = ts or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-1", path, "Write"),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_issue_event(
        self, db: Path, issue_id: str, transition: str, ts: str | None = None
    ) -> None:
        ts = ts or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, issue_type, priority) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, issue_id, transition, "ENH", "P3"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_missing_db_returns_empty_digest(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        digest = project_digest(db)
        assert digest.empty

    def test_empty_tables_returns_empty_digest(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        digest = project_digest(db)
        assert digest.empty

    def test_populated_db_touched_files_section(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        digest = project_digest(db, days=30)
        assert not digest.empty
        section_names = [name for name, _ in digest.sections]
        assert "touched_files" in section_names

    def test_stale_rows_excluded_from_digest(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        old_ts = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._insert_file_event(db, "scripts/stale.py", ts=old_ts)
        digest = project_digest(db, days=5)
        assert digest.empty

    def test_completed_issues_section_done(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_issue_event(db, "ENH-999", "done")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "completed_issues" in section_names
        _, lines = next(s for s in digest.sections if s[0] == "completed_issues")
        assert any("ENH-999" in line for line in lines)

    def test_completed_issues_section_cancelled(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_issue_event(db, "BUG-777", "cancelled")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "completed_issues" in section_names

    def test_open_issues_excluded_from_completed(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_issue_event(db, "FEAT-555", "open")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "completed_issues" not in section_names

    def test_recurring_corrections_section(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        record_correction(db, "sess-1", "no Co-Authored-By trailers", "user")
        record_correction(db, "sess-2", "no Co-Authored-By trailers", "user")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "recurring_corrections" in section_names

    def test_section_ordering_respected(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        self._insert_issue_event(db, "ENH-1", "done")
        digest = project_digest(db, days=30, sections=["completed_issues", "touched_files"])
        section_names = [name for name, _ in digest.sections]
        assert section_names[0] == "completed_issues"
        assert section_names[1] == "touched_files"

    def test_omitted_section_absent(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        record_correction(db, "sess-1", "some correction text", "user")
        digest = project_digest(db, days=30, sections=["touched_files"])
        section_names = [name for name, _ in digest.sections]
        assert "touched_files" in section_names
        assert "recurring_corrections" not in section_names

    def test_empty_sections_list_renders_all_sections(self, tmp_path: Path) -> None:
        # An empty sections list is treated the same as None (the config default):
        # render all registered providers, per project_digest()'s documented contract.
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        digest = project_digest(db, days=30, sections=[])
        assert not digest.empty
        section_names = [name for name, _ in digest.sections]
        assert "touched_files" in section_names

    def test_render_nonempty_digest_wraps_in_tags(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        digest = project_digest(db, days=30)
        block = render_project_context(digest)
        assert block.startswith("<project_context>")
        assert block.endswith("</project_context>")
        assert "scripts/foo.py" in block

    def test_render_empty_digest_returns_empty_string(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        digest = project_digest(db)
        assert render_project_context(digest) == ""

    def test_char_cap_enforced(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        for i in range(30):
            self._insert_file_event(db, f"scripts/module_{i}_with_long_path_name.py")
        digest = project_digest(db, days=30)
        block = render_project_context(digest, char_cap=200)
        assert len(block) <= 200
        assert "<project_context>" in block
        assert "</project_context>" in block

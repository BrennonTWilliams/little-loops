"""Tests for cli/history_context.py - ll-history-context CLI entry point."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.history_context import main_history_context
from little_loops.session_store import connect, ensure_db, record_correction


class TestArgumentParsing:
    """Argparse unit tests via sys.argv, no filesystem."""

    def test_missing_issue_id_exits(self) -> None:
        # issue_id is now nargs="?", so argparse no longer rejects bare invocation;
        # the mutual-exclusion guard in main_history_context() raises SystemExit instead.
        with patch("sys.argv", ["ll-history-context"]):
            with pytest.raises(SystemExit):
                main_history_context()

    def test_issue_id_accepted(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999"]):
            assert main_history_context() == 0

    def test_file_arg_is_optional(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999"]):
            assert main_history_context() == 0


class TestHistoryContextWithMatches:
    """DB seeded with correction rows; assert ## Historical Context in stdout."""

    def test_outputs_historical_context_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        record_correction(db, "sess-1", "Fix ENH-1708 by wiring corrections into refine", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Historical Context" in out

    def test_outputs_correction_content(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        record_correction(db, "sess-1", "Fix ENH-1708 by wiring corrections into refine", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            main_history_context()
        out = capsys.readouterr().out
        assert "wiring corrections into refine" in out

    def test_caps_at_five_rows(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "history.db"
        for i in range(10):
            record_correction(db, f"sess-{i}", f"correction ENH-1708 unique item {i}", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            main_history_context()
        out = capsys.readouterr().out
        bullet_lines = [line for line in out.splitlines() if line.startswith("- ")]
        assert len(bullet_lines) <= 5


class TestHistoryContextNoMatches:
    """DB present but empty; assert empty stdout."""

    def test_empty_stdout_on_no_matches(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestHistoryContextDBMissing:
    """No DB file; assert empty stdout, exit 0."""

    def test_missing_db_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "nonexistent.db"
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestHistoryContextStaleRows:
    """All rows older than 30 days; assert empty stdout."""

    def _insert_old_correction(self, db: Path, topic: str, days_old: int) -> None:
        conn = connect(db)
        try:
            ts = (datetime.now(UTC) - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-1", f"correction for {topic}", "user"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_stale_rows_produce_empty_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._insert_old_correction(db, "ENH-1708", days_old=31)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestDeduplication:
    """Same content from two queries; assert deduped in output."""

    def test_duplicate_content_appears_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        # record_correction writes to both user_corrections AND search_index,
        # so the same row appears in both find_user_corrections() and search() results.
        record_correction(db, "sess-1", "Fix ENH-1708 dedup test content", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            main_history_context()
        out = capsys.readouterr().out
        count = out.count("dedup test content")
        assert count == 1, f"Expected 1 occurrence of deduped content, got {count}"


class TestProjectMode:
    """Tests for ll-history-context --project (ENH-1907)."""

    def test_project_flag_prints_block_when_populated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        record_correction(db, "sess-1", "no Co-Authored-By trailers please", "user")
        with patch("sys.argv", ["ll-history-context", "--project", "--db", str(db)]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "<project_context>" in out
        assert "</project_context>" in out

    def test_project_flag_empty_db_no_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--project", "--db", str(db)]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""

    def test_project_flag_missing_db_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "nonexistent.db"
        with patch("sys.argv", ["ll-history-context", "--project", "--db", str(db)]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""

    def test_project_and_issue_id_mutually_exclusive(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--project", "--db", str(db), "ENH-1708"]):
            with pytest.raises(SystemExit):
                main_history_context()


class TestHistoryContextEffortFlag:
    """Tests for --effort flag in ll-history-context (ENH-1905)."""

    def _setup_issue_session(self, db: Path, issue_id: str, session_id: str, ts: str) -> None:
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, issue_id, "open", ts, None),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                (ts, session_id, "working on it"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, f"/path/{session_id}.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_effort_flag_accepted_with_sessions(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._setup_issue_session(db, "ENH-1905", "sess-001", "2026-01-10T10:00:00Z")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1905", "--effort"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Effort Context" in out

    def test_effort_flag_empty_db_returns_zero_empty_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999", "--effort"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""

    def test_effort_flag_missing_db_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "nonexistent.db"
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1905", "--effort"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestForSkillFlag:
    """Tests for --for-skill flag in ll-history-context (ENH-1909)."""

    def _write_config(self, tmp_path: Path, planning_skills: list) -> None:
        import json

        config = {"history": {"planning_skills": planning_skills}}
        (tmp_path / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")

    def _setup_issue_session(self, db: Path, issue_id: str, session_id: str, ts: str) -> None:
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, issue_id, "open", ts, None),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                (ts, session_id, "working on it"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, f"/path/{session_id}.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_skill_in_default_list_proceeds_normally(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path, ["create-sprint", "scope-epic", "manage-issue", "review-epic"])
        db = tmp_path / "history.db"
        ensure_db(db)
        self._setup_issue_session(db, "ENH-1909", "sess-001", "2026-01-10T10:00:00Z")
        with patch(
            "sys.argv",
            [
                "ll-history-context",
                "--for-skill",
                "manage-issue",
                "--effort",
                "--db",
                str(db),
                "ENH-1909",
            ],
        ):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Effort Context" in out

    def test_skill_not_in_list_returns_zero_empty_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path, ["create-sprint", "scope-epic", "review-epic"])
        db = tmp_path / "history.db"
        ensure_db(db)
        self._setup_issue_session(db, "ENH-1909", "sess-002", "2026-01-10T10:00:00Z")
        with patch(
            "sys.argv",
            [
                "ll-history-context",
                "--for-skill",
                "manage-issue",
                "--effort",
                "--db",
                str(db),
                "ENH-1909",
            ],
        ):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""

    def test_empty_planning_skills_list_returns_zero_empty_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path, [])
        db = tmp_path / "history.db"
        ensure_db(db)
        self._setup_issue_session(db, "ENH-1909", "sess-003", "2026-01-10T10:00:00Z")
        with patch(
            "sys.argv",
            [
                "ll-history-context",
                "--for-skill",
                "create-sprint",
                "--effort",
                "--db",
                str(db),
                "ENH-1909",
            ],
        ):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestHistoryContextSnapshot:
    """ENH-2151: ll-history-context falls back to issue_snapshots when source .md is missing."""

    def _seed_snapshot(self, db: Path, issue_id: str, body: str) -> None:
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_snapshots(ts, issue_id, transition, title, body) "
                "VALUES(?, ?, ?, ?, ?)",
                ("2026-01-01T00:00:00Z", issue_id, "done", f"Title for {issue_id}", body),
            )
            conn.commit()
        finally:
            conn.close()

    def test_snapshot_body_shown_when_no_other_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._seed_snapshot(db, "ENH-2151", "Snapshot body text for ENH-2151.")

        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2151"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "Snapshot body text for ENH-2151" in out

    def test_snapshot_not_shown_when_corrections_exist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        record_correction(db, "sess-1", "Fix ENH-2151 correction content", "user")
        self._seed_snapshot(db, "ENH-2151", "Snapshot body text for ENH-2151.")

        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2151"]):
            main_history_context()
        out = capsys.readouterr().out
        assert "Fix ENH-2151 correction content" in out


class TestRenderLearningTestSection:
    """Unit tests for _render_learning_test_section helper (ENH-2217)."""

    def test_returns_none_when_no_targets(self, tmp_path: Path) -> None:
        from little_loops.cli.history_context import _render_learning_test_section

        assert _render_learning_test_section([], base_dir=tmp_path / "lt") is None

    def test_returns_none_when_record_missing(self, tmp_path: Path) -> None:
        from little_loops.cli.history_context import _render_learning_test_section

        lt_dir = tmp_path / ".ll" / "learning-tests"
        lt_dir.mkdir(parents=True)
        assert _render_learning_test_section(["unknown-lib"], base_dir=lt_dir) is None

    def test_formats_table_with_assertion_counts(self, tmp_path: Path) -> None:
        import datetime

        from little_loops.cli.history_context import _render_learning_test_section
        from little_loops.learning_tests import Assertion, LearnTestRecord, write_record

        lt_dir = tmp_path / ".ll" / "learning-tests"
        lt_dir.mkdir(parents=True)
        fresh_date = datetime.date.today().isoformat()
        record = LearnTestRecord(
            target="anthropic",
            date=fresh_date,
            status="proven",
            assertions=[
                Assertion(claim="works", result="pass"),
                Assertion(claim="fails on X", result="fail"),
                Assertion(claim="untested", result="untested"),
            ],
            raw_output_path=None,
        )
        write_record(record, base_dir=lt_dir)
        result = _render_learning_test_section(["anthropic"], base_dir=lt_dir)
        assert result is not None
        assert "## Learning Test Evidence" in result
        assert "anthropic" in result
        assert "proven" in result
        assert fresh_date in result
        assert "1/1/1" in result

    def test_stale_overrides_on_disk_status(self, tmp_path: Path) -> None:
        from little_loops.cli.history_context import _render_learning_test_section
        from little_loops.learning_tests import LearnTestRecord, write_record

        lt_dir = tmp_path / ".ll" / "learning-tests"
        lt_dir.mkdir(parents=True)
        record = LearnTestRecord(
            target="httpx",
            date="2026-01-01",
            status="proven",
            assertions=[],
            raw_output_path=None,
        )
        write_record(record, base_dir=lt_dir)
        result = _render_learning_test_section(["httpx"], stale_after_days=30, base_dir=lt_dir)
        assert result is not None
        assert "stale" in result
        assert "proven" not in result

    def test_no_table_when_all_targets_missing_records(self, tmp_path: Path) -> None:
        from little_loops.cli.history_context import _render_learning_test_section

        lt_dir = tmp_path / ".ll" / "learning-tests"
        lt_dir.mkdir(parents=True)
        assert _render_learning_test_section(["lib-a", "lib-b"], base_dir=lt_dir) is None


class TestLearningTestEvidenceIntegration:
    """Integration tests for Learning Test Evidence in ll-history-context (ENH-2217)."""

    def _write_lt_config(
        self, tmp_path: Path, *, enabled: bool, stale_after_days: int = 30
    ) -> None:
        import json

        config = {"learning_tests": {"enabled": enabled, "stale_after_days": stale_after_days}}
        (tmp_path / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")

    def _write_issue_file(self, tmp_path: Path, issue_id: str, targets: list[str]) -> None:
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        lines = [
            "---",
            f"id: {issue_id}",
            "title: Test Issue",
            "type: enhancement",
            "priority: P4",
            "status: open",
        ]
        if targets:
            lines.append("learning_tests_required:")
            for t in targets:
                lines.append(f"  - {t}")
        lines += ["---", "", "# Test Issue", ""]
        (issues_dir / f"P4-{issue_id}-test-issue.md").write_text("\n".join(lines))

    def _write_lt_record(self, tmp_path: Path, target: str, status: str, date: str) -> None:
        import yaml

        from little_loops.issue_parser import slugify

        lt_dir = tmp_path / ".ll" / "learning-tests"
        lt_dir.mkdir(parents=True, exist_ok=True)
        data: dict = {
            "target": target,
            "date": date,
            "status": status,
            "assertions": [{"claim": "it works", "result": "pass"}],
            "raw_output_path": None,
        }
        fm_text = yaml.dump(data, default_flow_style=False, sort_keys=False).strip()
        (lt_dir / f"{slugify(target)}.md").write_text(f"---\n{fm_text}\n---\n")

    def test_section_present_when_record_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_lt_config(tmp_path, enabled=True)
        self._write_issue_file(tmp_path, "ENH-2217", ["anthropic"])
        self._write_lt_record(tmp_path, "anthropic", "proven", "2026-06-15")
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2217"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Learning Test Evidence" in out
        assert "anthropic" in out

    def test_stale_record_shows_stale_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_lt_config(tmp_path, enabled=True, stale_after_days=30)
        self._write_issue_file(tmp_path, "ENH-2217", ["httpx"])
        self._write_lt_record(tmp_path, "httpx", "proven", "2026-01-01")
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2217"]):
            main_history_context()
        out = capsys.readouterr().out
        assert "stale" in out
        assert "## Learning Test Evidence" in out

    def test_no_section_when_learning_tests_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_lt_config(tmp_path, enabled=False)
        self._write_issue_file(tmp_path, "ENH-2217", ["anthropic"])
        self._write_lt_record(tmp_path, "anthropic", "proven", "2026-06-15")
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2217"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Learning Test Evidence" not in out

    def test_no_section_when_no_learning_tests_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_lt_config(tmp_path, enabled=True)
        self._write_issue_file(tmp_path, "ENH-2217", [])  # no targets
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2217"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Learning Test Evidence" not in out

    def test_no_section_when_no_matching_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._write_lt_config(tmp_path, enabled=True)
        self._write_issue_file(tmp_path, "ENH-2217", ["nonexistent-lib"])
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2217"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Learning Test Evidence" not in out

    def test_section_present_even_without_historical_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """LT section emitted even when Historical Context is empty."""
        monkeypatch.chdir(tmp_path)
        self._write_lt_config(tmp_path, enabled=True)
        self._write_issue_file(tmp_path, "ENH-2217", ["anthropic"])
        self._write_lt_record(tmp_path, "anthropic", "proven", "2026-06-15")
        db = tmp_path / "history.db"
        ensure_db(db)  # empty DB → no historical context rows
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-2217"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Historical Context" not in out
        assert "## Learning Test Evidence" in out

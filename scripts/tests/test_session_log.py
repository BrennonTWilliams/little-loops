"""Tests for session_log module."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from little_loops.session_log import append_session_log_entry, get_current_session_jsonl


class TestGetCurrentSessionJsonl:
    """Tests for get_current_session_jsonl."""

    def test_returns_none_when_no_project_folder(self) -> None:
        with patch("little_loops.session_log.get_project_folder", return_value=None):
            assert get_current_session_jsonl() is None

    def test_returns_none_when_no_jsonl_files(self, tmp_path: Path) -> None:
        with patch("little_loops.session_log.get_project_folder", return_value=tmp_path):
            assert get_current_session_jsonl() is None

    def test_returns_most_recent_jsonl(self, tmp_path: Path) -> None:
        old_file = tmp_path / "old.jsonl"
        old_file.write_text("{}")
        time.sleep(0.05)
        new_file = tmp_path / "new.jsonl"
        new_file.write_text("{}")

        with patch("little_loops.session_log.get_project_folder", return_value=tmp_path):
            result = get_current_session_jsonl()
            assert result == new_file

    def test_excludes_agent_session_files(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "agent-coding.jsonl"
        agent_file.write_text("{}")
        time.sleep(0.05)
        session_file = tmp_path / "abc123.jsonl"
        session_file.write_text("{}")

        with patch("little_loops.session_log.get_project_folder", return_value=tmp_path):
            result = get_current_session_jsonl()
            assert result == session_file

    def test_returns_none_when_only_agent_files(self, tmp_path: Path) -> None:
        (tmp_path / "agent-coding.jsonl").write_text("{}")

        with patch("little_loops.session_log.get_project_folder", return_value=tmp_path):
            assert get_current_session_jsonl() is None


class TestAppendSessionLogEntry:
    """Tests for append_session_log_entry."""

    def test_returns_false_when_no_session(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.md"
        issue.write_text("# Issue\n")

        with patch("little_loops.session_log.get_current_session_jsonl", return_value=None):
            assert append_session_log_entry(issue, "/ll:test") is False

    def test_creates_session_log_section(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.md"
        issue.write_text("# Issue\n\nContent here.\n\n---\n\n## Status\n\n**Open**\n")

        jsonl = tmp_path / "session.jsonl"
        result = append_session_log_entry(issue, "/ll:manage_issue", session_jsonl=jsonl)

        assert result is True
        content = issue.read_text()
        assert "## Session Log" in content
        assert "/ll:manage_issue" in content
        assert str(jsonl) in content
        # Session Log should be before Status
        assert content.index("## Session Log") < content.index("## Status")

    def test_appends_to_existing_section(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.md"
        issue.write_text(
            "# Issue\n\n## Session Log\n"
            "- `/ll:capture_issue` - 2026-01-01T00:00:00 - `/old.jsonl`\n\n"
            "---\n\n## Status\n\n**Open**\n"
        )

        jsonl = tmp_path / "new.jsonl"
        result = append_session_log_entry(issue, "/ll:format_issue", session_jsonl=jsonl)

        assert result is True
        content = issue.read_text()
        assert content.count("## Session Log") == 1
        assert "/ll:capture_issue" in content
        assert "/ll:format_issue" in content

    def test_appends_at_end_when_no_status_footer(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.md"
        issue.write_text("# Issue\n\nContent here.\n")

        jsonl = tmp_path / "session.jsonl"
        result = append_session_log_entry(issue, "/ll:scan_codebase", session_jsonl=jsonl)

        assert result is True
        content = issue.read_text()
        assert "## Session Log" in content
        assert content.endswith("\n")

    def test_multiple_appends_create_multiple_entries(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.md"
        issue.write_text("# Issue\n\n---\n\n## Status\n\n**Open**\n")

        jsonl = tmp_path / "s.jsonl"
        append_session_log_entry(issue, "/ll:capture_issue", session_jsonl=jsonl)
        append_session_log_entry(issue, "/ll:format_issue", session_jsonl=jsonl)

        content = issue.read_text()
        assert content.count("## Session Log") == 1
        assert "/ll:capture_issue" in content
        assert "/ll:format_issue" in content

    def test_entry_format(self, tmp_path: Path) -> None:
        issue = tmp_path / "issue.md"
        issue.write_text("# Issue\n")

        jsonl = tmp_path / "abc.jsonl"
        append_session_log_entry(issue, "/ll:test", session_jsonl=jsonl)

        content = issue.read_text()
        # Entry should have format: - `command` - timestamp - `path`
        lines = [line for line in content.split("\n") if line.startswith("- `")]
        assert len(lines) == 1
        assert lines[0].startswith("- `/ll:test` - ")
        assert lines[0].endswith(f"- `{jsonl}`")

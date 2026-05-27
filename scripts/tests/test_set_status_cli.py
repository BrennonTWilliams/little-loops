"""Tests for ll-issues set-status sub-command (ENH-1725)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestIssuesCLISetStatus:
    """Tests for ll-issues set-status sub-command."""

    def test_set_status_writes_new_status(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status updates the status field and prints the transition."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\nid: BUG-001\nstatus: open\n---\n# BUG-001: Critical crash on startup\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "BUG-001",
                "in_progress",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "status: in_progress" in content

    def test_set_status_prints_transition(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """set-status prints 'old → new' to stdout on success."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text("---\nid: BUG-001\nstatus: open\n---\n# BUG-001: Critical crash\n")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-001", "done", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "open" in captured.out
        assert "done" in captured.out

    def test_set_status_preserves_unrelated_fields(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status only updates status; other frontmatter fields are unchanged."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\n"
            "id: BUG-001\n"
            "status: open\n"
            "captured_at: '2026-01-01T00:00:00Z'\n"
            "confidence_score: 88\n"
            "---\n"
            "# BUG-001: Critical crash\n"
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-001", "blocked", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "status: blocked" in content
        assert "captured_at" in content
        assert "confidence_score: 88" in content

    def test_set_status_nonexistent_issue_returns_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status returns exit code 1 when the issue ID does not exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-999", "done", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_set_status_invalid_value_rejected(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status with an invalid status value causes argparse to exit with code 2."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-001", "wip", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            with pytest.raises(SystemExit) as exc_info:
                main_issues()

        assert exc_info.value.code == 2

"""Tests for ll-issues set-scores sub-command (BUG-1307)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestIssuesCLISetScores:
    """Tests for ll-issues set-scores sub-command."""

    def test_set_scores_writes_all_fields(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-scores writes all six score fields to frontmatter when none exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-scores",
                "BUG-001",
                "--confidence", "95",
                "--outcome", "80",
                "--score-complexity", "22",
                "--score-test-coverage", "20",
                "--score-ambiguity", "25",
                "--score-change-surface", "15",
                "--config", str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "confidence_score: 95" in content
        assert "outcome_confidence: 80" in content
        assert "score_complexity: 22" in content
        assert "score_test_coverage: 20" in content
        assert "score_ambiguity: 25" in content
        assert "score_change_surface: 15" in content

    def test_set_scores_updates_existing_fields_without_disturbing_others(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-scores overwrites existing score fields but leaves unrelated keys intact."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\n"
            "captured_at: '2026-01-01T00:00:00Z'\n"
            "confidence_score: 50\n"
            "outcome_confidence: 40\n"
            "---\n"
            "# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch."
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-scores",
                "BUG-001",
                "--confidence", "90",
                "--outcome", "75",
                "--config", str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "confidence_score: 90" in content
        assert "outcome_confidence: 75" in content
        # Unrelated field must be preserved
        assert "captured_at" in content

    def test_set_scores_partial_update(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-scores with only --confidence updates that field and leaves others unchanged."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\n"
            "confidence_score: 50\n"
            "outcome_confidence: 40\n"
            "---\n"
            "# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch."
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-scores",
                "BUG-001",
                "--confidence", "85",
                "--config", str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "confidence_score: 85" in content
        # outcome_confidence must remain at original value
        assert "outcome_confidence: 40" in content

    def test_set_scores_nonexistent_issue_returns_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-scores returns exit code 1 when the issue ID does not exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-scores",
                "BUG-999",
                "--confidence", "80",
                "--config", str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_set_scores_no_flags_returns_0_with_warning(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """set-scores with no score flags returns 0 and prints a warning."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-scores", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Warning" in captured.err

    def test_set_scores_verify_via_show_json(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """After set-scores, ll-issues show --json returns the updated values."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-scores",
                "BUG-001",
                "--confidence", "88",
                "--outcome", "72",
                "--config", str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "show", "BUG-001", "--json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            show_result = main_issues()

        assert show_result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["confidence"] == "88"
        assert data["outcome"] == "72"

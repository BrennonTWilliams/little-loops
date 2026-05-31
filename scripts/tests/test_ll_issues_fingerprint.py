"""Tests for ll-issues fingerprint sub-command (ENH-1801)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestIssuesCLIFingerprint:
    """Tests for ll-issues fingerprint sub-command."""

    def test_fingerprint_output_is_valid_json(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fingerprint outputs valid JSON with required keys."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fingerprint",
                str(issue_file),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "id" in data
        assert "files_to_modify" in data
        assert "key_terms" in data
        assert isinstance(data["files_to_modify"], list)
        assert isinstance(data["key_terms"], list)

    def test_fingerprint_id_from_filename(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fingerprint parses issue ID from filename when frontmatter has no id field."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fingerprint",
                str(issue_file),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["id"] == "BUG-001"

    def test_fingerprint_id_from_frontmatter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fingerprint reads id from YAML frontmatter when present."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text("---\nid: ENH-999\nstatus: open\n---\n# ENH-999: test\n\n## Summary\nTest issue.\n")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fingerprint",
                str(issue_file),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["id"] == "ENH-999"

    def test_fingerprint_extracts_files_to_modify(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fingerprint extracts file paths from the Integration Map section."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\nid: BUG-001\nstatus: open\n---\n\n"
            "## Integration Map\n\n"
            "### Files to Modify\n"
            "- `scripts/config.py`\n"
            "- `scripts/utils.py`\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fingerprint",
                str(issue_file),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "scripts/config.py" in data["files_to_modify"]
        assert "scripts/utils.py" in data["files_to_modify"]

    def test_fingerprint_extracts_key_terms(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fingerprint extracts stop-word-filtered key terms from issue content."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\nid: BUG-001\nstatus: open\n---\n\n"
            "# BUG-001: authentication error\n\n"
            "## Summary\n\n"
            "The authentication middleware fails on token refresh.\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fingerprint",
                str(issue_file),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "authentication" in data["key_terms"]

    def test_fingerprint_missing_file_returns_error(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """fingerprint returns exit code 1 when the issue file does not exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fingerprint",
                str(temp_project_dir / "nonexistent.md"),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_fingerprint_fp_alias(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """fingerprint is accessible via the 'fp' alias."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "fp",
                str(issue_file),
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "id" in data

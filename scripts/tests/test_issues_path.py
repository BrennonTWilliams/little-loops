"""Tests for ll-issues path sub-command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _write_config(temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))


def _make_issue(directory: Path, filename: str, title: str) -> None:
    """Write a minimal issue file."""
    content = (
        f"---\nid: {title.split(':')[0].strip()}\n---\n\n# {title}\n\n## Summary\nTest issue.\n"
    )
    (directory / filename).write_text(content)


def _setup_dirs(temp_project_dir: Path) -> tuple[Path, Path, Path]:
    """Create standard issue directory structure and return (features_dir, completed_dir, deferred_dir)."""
    features_dir = temp_project_dir / ".issues" / "features"
    bugs_dir = temp_project_dir / ".issues" / "bugs"
    completed_dir = temp_project_dir / ".issues" / "completed"
    deferred_dir = temp_project_dir / ".issues" / "deferred"
    for d in (features_dir, bugs_dir, completed_dir, deferred_dir):
        d.mkdir(parents=True, exist_ok=True)
    return features_dir, completed_dir, deferred_dir


class TestPathResolveFormats:
    """Tests for resolving all three ID input formats."""

    def test_numeric_id_resolves(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Numeric-only ID (e.g., 1009) resolves to correct file."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "path", "1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out.endswith("P3-FEAT-1009-my-feature.md")

    def test_type_id_format_resolves(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """TYPE-NNN format (e.g., FEAT-1009) resolves to correct file."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "path", "FEAT-1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out.endswith("P3-FEAT-1009-my-feature.md")

    def test_full_format_resolves(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """P-TYPE-NNN format (e.g., P3-FEAT-1009) resolves to correct file."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "path", "P3-FEAT-1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out.endswith("P3-FEAT-1009-my-feature.md")

    def test_path_is_relative(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Output is a relative path (does not start with /)."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "path", "FEAT-1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert not out.startswith("/")
        assert ".issues/features/P3-FEAT-1009-my-feature.md" in out


class TestPathNotFound:
    """Tests for not-found behavior."""

    def test_not_found_returns_exit_code_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns exit code 1 when issue is not found."""
        _write_config(temp_project_dir, sample_config)
        _setup_dirs(temp_project_dir)

        with patch.object(
            sys, "argv", ["ll-issues", "path", "9999", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_not_found_message_on_stderr(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error message goes to stderr, not stdout."""
        _write_config(temp_project_dir, sample_config)
        _setup_dirs(temp_project_dir)

        with patch.object(
            sys, "argv", ["ll-issues", "path", "FEAT-9999", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.out.strip() == ""
        assert "9999" in captured.err or "not found" in captured.err.lower()


class TestPathJsonFlag:
    """Tests for --json output."""

    def test_json_emits_path_field(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs {"path": "..."} with relative path."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "path", "FEAT-1009", "--json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        data = json.loads(out)
        assert "path" in data
        assert data["path"].endswith("P3-FEAT-1009-my-feature.md")

    def test_json_path_is_relative(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json path value is relative to project root."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "path", "1009", "--json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            main_issues()

        out = capsys.readouterr().out
        data = json.loads(out)
        assert not data["path"].startswith("/")


class TestPathAlias:
    """Tests for alias 'p'."""

    def test_alias_p_works(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Alias 'p' resolves to the same command as 'path'."""
        _write_config(temp_project_dir, sample_config)
        features_dir, _, _ = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "p", "FEAT-1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out.endswith("P3-FEAT-1009-my-feature.md")


class TestPathSearchesAllDirs:
    """Tests that path searches completed and deferred directories."""

    def test_finds_issue_in_completed(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Finds issues in completed/ directory."""
        _write_config(temp_project_dir, sample_config)
        _, completed_dir, _ = _setup_dirs(temp_project_dir)
        _make_issue(completed_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "path", "1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert "completed" in out
        assert out.endswith("P3-FEAT-1009-my-feature.md")

    def test_finds_issue_in_deferred(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Finds issues in deferred/ directory."""
        _write_config(temp_project_dir, sample_config)
        _, _, deferred_dir = _setup_dirs(temp_project_dir)
        _make_issue(deferred_dir, "P3-FEAT-1009-my-feature.md", "FEAT-1009: My Feature")

        with patch.object(
            sys, "argv", ["ll-issues", "path", "FEAT-1009", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert "deferred" in out
        assert out.endswith("P3-FEAT-1009-my-feature.md")

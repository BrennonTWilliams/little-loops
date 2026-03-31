"""Tests for ll-issues next-issue sub-command."""

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


def _make_issue(
    directory: Path,
    filename: str,
    title: str,
    *,
    confidence_score: int | None = None,
    outcome_confidence: int | None = None,
) -> None:
    """Write a minimal issue file with optional frontmatter fields."""
    frontmatter_lines: list[str] = []
    if confidence_score is not None:
        frontmatter_lines.append(f"confidence_score: {confidence_score}")
    if outcome_confidence is not None:
        frontmatter_lines.append(f"outcome_confidence: {outcome_confidence}")

    parts: list[str] = []
    if frontmatter_lines:
        parts.append("---")
        parts.extend(frontmatter_lines)
        parts.append("---")
        parts.append("")

    parts.append(f"# {title}")
    parts.append("")
    parts.append("## Summary")
    parts.append("Test issue.")

    (directory / filename).write_text("\n".join(parts))


def _setup_dirs(temp_project_dir: Path) -> Path:
    """Create standard issue directory structure and return the features dir."""
    features_dir = temp_project_dir / ".issues" / "features"
    features_dir.mkdir(parents=True)
    (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
    (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)
    return features_dir


class TestNextIssueSorting:
    """Tests for sort order: outcome_confidence desc → confidence_score desc → priority_int asc."""

    def test_returns_highest_outcome_confidence(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Selects issue with highest outcome_confidence."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-001-low.md",
            "FEAT-001: Low",
            outcome_confidence=40,
            confidence_score=90,
        )
        _make_issue(
            features_dir,
            "P2-FEAT-002-high.md",
            "FEAT-002: High",
            outcome_confidence=90,
            confidence_score=50,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "FEAT-002" in out

    def test_tiebreak_by_confidence_score(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When outcome_confidence ties, selects issue with higher confidence_score."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-001-low.md",
            "FEAT-001: Low cs",
            outcome_confidence=80,
            confidence_score=50,
        )
        _make_issue(
            features_dir,
            "P2-FEAT-002-high.md",
            "FEAT-002: High cs",
            outcome_confidence=80,
            confidence_score=90,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "FEAT-002" in out

    def test_tiebreak_by_priority(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When both scores tie, selects issue with lower priority_int (higher priority)."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P3-FEAT-001-lower.md",
            "FEAT-001: P3",
            outcome_confidence=80,
            confidence_score=80,
        )
        _make_issue(
            features_dir,
            "P1-FEAT-002-higher.md",
            "FEAT-002: P1",
            outcome_confidence=80,
            confidence_score=80,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "FEAT-002" in out

    def test_unscored_issues_rank_last(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Issues missing both scores are ranked below scored issues."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(features_dir, "P0-FEAT-001-unscored.md", "FEAT-001: No scores")
        _make_issue(
            features_dir,
            "P3-FEAT-002-scored.md",
            "FEAT-002: Scored",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "FEAT-002" in out


class TestNextIssueOutputFlags:
    """Tests for --json and --path output flags."""

    def test_default_prints_issue_id(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default output is just the issue ID."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=80,
            confidence_score=80,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out == "FEAT-001"

    def test_json_flag_output_shape(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs a JSON object with expected fields."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=85,
            confidence_score=75,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        data = json.loads(out)
        assert data["id"] == "FEAT-001"
        assert data["outcome_confidence"] == 85
        assert data["confidence_score"] == 75
        assert data["priority"] == "P2"
        assert "path" in data

    def test_path_flag_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--path outputs only the file path."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=80,
            confidence_score=80,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--path", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out.endswith("P2-FEAT-001-test.md")

    def test_json_unscored_fields_are_null(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json output for an unscored issue has null score fields."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        _make_issue(features_dir, "P2-FEAT-001-unscored.md", "FEAT-001: Unscored")

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        data = json.loads(out)
        assert data["outcome_confidence"] is None
        assert data["confidence_score"] is None


class TestNextIssueEdgeCases:
    """Tests for edge cases."""

    def test_empty_issue_dir_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Exits with code 1 when there are no active issues."""
        _write_config(temp_project_dir, sample_config)
        _setup_dirs(temp_project_dir)

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        assert capsys.readouterr().out == ""

    def test_nx_alias_works(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The 'nx' alias resolves to the same command."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=80,
            confidence_score=80,
        )

        with patch.object(sys, "argv", ["ll-issues", "nx", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out == "FEAT-001"

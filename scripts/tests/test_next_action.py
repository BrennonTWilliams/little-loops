"""Tests for ll-issues next-action sub-command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _write_config(temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))


def _make_issue(
    directory: Path,
    filename: str,
    title: str,
    *,
    confidence_score: int | None = None,
    outcome_confidence: int | None = None,
    session_commands: list[str] | None = None,
) -> None:
    """Write a minimal issue file with optional frontmatter and Session Log."""
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

    if session_commands:
        parts.append("")
        parts.append("## Session Log")
        for cmd in session_commands:
            parts.append(f"- `{cmd}` - 2026-01-01T00:00:00 - `/session.jsonl`")

    (directory / filename).write_text("\n".join(parts))


def _setup_dirs(temp_project_dir: Path) -> Path:
    """Create standard issue directory structure and return the bugs dir."""
    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
    (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)
    return bugs_dir


class TestIssuesCLINextAction:
    """Tests for next-action sub-command."""

    def test_needs_format(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns NEEDS_FORMAT for an issue without /ll:format-issue in session log."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        _make_issue(bugs_dir, "P3-BUG-001-test.md", "BUG-001: Test issue")

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 1
        assert "NEEDS_FORMAT BUG-001" in out

    def test_needs_verify(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns NEEDS_VERIFY for a formatted issue without /ll:verify-issues."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            bugs_dir,
            "P3-BUG-001-test.md",
            "BUG-001: Test issue",
            session_commands=["/ll:format-issue"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 1
        assert "NEEDS_VERIFY BUG-001" in out

    def test_needs_score(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns NEEDS_SCORE for a formatted+verified issue with missing confidence fields."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            bugs_dir,
            "P3-BUG-001-test.md",
            "BUG-001: Test issue",
            session_commands=["/ll:format-issue", "/ll:verify-issues"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 1
        assert "NEEDS_SCORE BUG-001" in out

    def test_needs_refine(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns NEEDS_REFINE for an issue with scores below threshold."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            bugs_dir,
            "P3-BUG-001-test.md",
            "BUG-001: Test issue",
            confidence_score=50,
            outcome_confidence=50,
            session_commands=["/ll:format-issue", "/ll:verify-issues"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 1
        assert "NEEDS_REFINE BUG-001" in out

    def test_all_done(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns ALL_DONE when all issues meet quality thresholds."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            bugs_dir,
            "P3-BUG-001-test.md",
            "BUG-001: Test issue",
            confidence_score=90,
            outcome_confidence=80,
            session_commands=["/ll:format-issue", "/ll:verify-issues"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "ALL_DONE" in out

    def test_all_done_no_issues(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Returns ALL_DONE when there are no active issues."""
        _write_config(temp_project_dir, sample_config)
        _setup_dirs(temp_project_dir)

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "ALL_DONE" in out

    def test_graduates_after_refine_cap(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Graduates an issue that has hit the refine cap even if scores are below threshold."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        # 5 refine calls, scores still below threshold → graduated
        _make_issue(
            bugs_dir,
            "P3-BUG-001-test.md",
            "BUG-001: Test issue",
            confidence_score=50,
            outcome_confidence=50,
            session_commands=[
                "/ll:format-issue",
                "/ll:verify-issues",
                "/ll:refine-issue",
                "/ll:refine-issue",
                "/ll:refine-issue",
                "/ll:refine-issue",
                "/ll:refine-issue",
            ],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-action", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "ALL_DONE" in out

    def test_custom_thresholds(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Custom thresholds are respected."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = _setup_dirs(temp_project_dir)

        # scores of 60 pass when thresholds are lowered to 50/50
        _make_issue(
            bugs_dir,
            "P3-BUG-001-test.md",
            "BUG-001: Test issue",
            confidence_score=60,
            outcome_confidence=60,
            session_commands=["/ll:format-issue", "/ll:verify-issues"],
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-action",
                "--ready-threshold",
                "50",
                "--outcome-threshold",
                "50",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "ALL_DONE" in out

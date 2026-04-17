"""Tests for ll-issues next-issues sub-command."""

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


class TestNextIssuesRankedOrder:
    """Tests for ranked order output."""

    def test_returns_all_issues_in_ranked_order(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """All issues are returned, sorted by outcome_confidence desc then confidence_score desc."""
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
        _make_issue(
            features_dir,
            "P2-FEAT-003-mid.md",
            "FEAT-003: Mid",
            outcome_confidence=70,
            confidence_score=70,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        lines = out.strip().splitlines()
        assert result == 0
        assert len(lines) == 3
        assert lines[0] == "FEAT-002"
        assert lines[1] == "FEAT-003"
        assert lines[2] == "FEAT-001"

    def test_default_output_is_ids_one_per_line(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default output prints one issue ID per line."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P1-FEAT-001-a.md",
            "FEAT-001: A",
            outcome_confidence=80,
            confidence_score=80,
        )
        _make_issue(
            features_dir,
            "P2-FEAT-002-b.md",
            "FEAT-002: B",
            outcome_confidence=80,
            confidence_score=70,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        lines = out.strip().splitlines()
        assert result == 0
        assert lines == ["FEAT-001", "FEAT-002"]


class TestNextIssuesStrategy:
    """Regression tests for config-driven selection strategy on the ranked list command."""

    def test_priority_first_strategy_overrides_default(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Under priority_first the ranked output orders by priority_int first, so the
        higher-priority issue appears before a lower-priority but higher-confidence one."""
        config_with_strategy = {
            **sample_config,
            "issues": {
                **sample_config["issues"],
                "next_issue": {"strategy": "priority_first"},
            },
        }
        _write_config(temp_project_dir, config_with_strategy)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P1-FEAT-001-high-pri.md",
            "FEAT-001: High priority",
            outcome_confidence=40,
            confidence_score=40,
        )
        _make_issue(
            features_dir,
            "P3-FEAT-002-high-conf.md",
            "FEAT-002: High confidence",
            outcome_confidence=95,
            confidence_score=95,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        lines = out.strip().splitlines()
        assert result == 0
        assert lines[0] == "FEAT-001"
        assert lines[1] == "FEAT-002"


class TestNextIssuesCountArg:
    """Tests for the optional count positional argument."""

    def test_count_caps_results(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Positional count argument caps the number of results returned."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        for i in range(1, 5):
            _make_issue(
                features_dir,
                f"P2-FEAT-00{i}-item.md",
                f"FEAT-00{i}: Item",
                outcome_confidence=90 - i * 10,
                confidence_score=80,
            )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issues", "2", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        lines = out.strip().splitlines()
        assert result == 0
        assert len(lines) == 2


class TestNextIssuesOutputFlags:
    """Tests for --json and --path output flags."""

    def test_json_flag_returns_array(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs a JSON array with expected fields per item."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=85,
            confidence_score=75,
        )
        _make_issue(
            features_dir,
            "P3-FEAT-002-test.md",
            "FEAT-002: Test",
            outcome_confidence=60,
            confidence_score=60,
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issues", "--json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 2
        first = data[0]
        assert first["id"] == "FEAT-001"
        assert first["outcome_confidence"] == 85
        assert first["confidence_score"] == 75
        assert first["priority"] == "P2"
        assert "path" in first

    def test_path_flag_returns_paths(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--path outputs one file path per line."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=80,
            confidence_score=80,
        )
        _make_issue(
            features_dir,
            "P3-FEAT-002-test.md",
            "FEAT-002: Test",
            outcome_confidence=60,
            confidence_score=60,
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issues", "--path", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        lines = out.strip().splitlines()
        assert result == 0
        assert len(lines) == 2
        assert lines[0].endswith("P2-FEAT-001-test.md")
        assert lines[1].endswith("P3-FEAT-002-test.md")


class TestNextIssuesEdgeCases:
    """Tests for edge cases."""

    def test_empty_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Exits with code 1 when there are no active issues."""
        _write_config(temp_project_dir, sample_config)
        _setup_dirs(temp_project_dir)

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        assert capsys.readouterr().out == ""

    def test_nxs_alias_works(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The 'nxs' alias resolves to the same command."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        _make_issue(
            features_dir,
            "P2-FEAT-001-test.md",
            "FEAT-001: Test",
            outcome_confidence=80,
            confidence_score=80,
        )

        with patch.object(sys, "argv", ["ll-issues", "nxs", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out == "FEAT-001"

"""Tests for ll-issues CLI entry point and sub-commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestIssuesCLINextId:
    """Tests for ll-issues next-id sub-command."""

    def test_next_id_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """next-id returns 001 for an empty project."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-issues", "next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "001"

    def test_next_id_with_existing_issues(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """next-id returns correct next number when issues exist."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # issues_dir fixture has BUG-001, BUG-002, BUG-003, FEAT-001, FEAT-002
        assert captured.out.strip() == "004"

    def test_next_id_matches_ll_next_id(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-issues next-id output matches ll-next-id output."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)
        (temp_project_dir / ".issues" / "bugs" / "P0-BUG-005-test.md").write_text("# BUG-005")

        with patch.object(sys, "argv", ["ll-issues", "next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            main_issues()
        issues_out = capsys.readouterr().out.strip()

        with patch.object(sys, "argv", ["ll-next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_next_id

            main_next_id()
        next_id_out = capsys.readouterr().out.strip()

        assert issues_out == next_id_out == "006"


@pytest.fixture
def issues_dir_with_enh(issues_dir: Path) -> Path:
    """Extend issues_dir fixture with a sample ENH issue."""
    enh_dir = issues_dir / "enhancements"
    enh_dir.mkdir(parents=True, exist_ok=True)
    (enh_dir / "P3-ENH-010-improve-output.md").write_text(
        "# ENH-010: Improve output formatting\n\n## Summary\nBetter formatting."
    )
    return issues_dir


class TestIssuesCLIList:
    """Tests for ll-issues list sub-command."""

    def test_list_all_issues(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list outputs all active issues grouped by type."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "list", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "FEAT-001" in captured.out

    def test_list_grouped_output_has_headers(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir_with_enh: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list default output groups issues with type headers and counts."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "list", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Bugs (3)" in captured.out
        assert "Features (2)" in captured.out
        assert "Enhancements (1)" in captured.out
        assert "Total: 6 active issues" in captured.out

    def test_list_grouped_output_line_format(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list default output formats each line as '  Pn  TYPE-NNN  Title'."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "list", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "  P0  BUG-001  " in captured.out
        assert "  P1  FEAT-001  " in captured.out

    def test_list_flat_backward_compatibility(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --flat produces original filename + title format."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--flat", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # Flat format shows full filename
        assert "P0-BUG-001-critical-crash.md" in captured.out
        assert "P1-FEAT-001-dark-mode.md" in captured.out
        # No group headers in flat mode
        assert "Bugs (" not in captured.out
        assert "Total:" not in captured.out

    def test_list_filter_by_type(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --type BUG shows only bug issues."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--type", "BUG", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "BUG-002" in captured.out
        assert "FEAT-001" not in captured.out

    def test_list_filter_by_priority(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --priority P0 shows only P0 issues."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "list", "--priority", "P0", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out  # BUG-001 is P0
        assert "BUG-002" not in captured.out  # BUG-002 is P1

    def test_list_empty_groups_shown(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list shows all type groups including empty ones (e.g. ENH when no ENH issues)."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "list", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # issues_dir has no ENH issues — group should still appear with count 0
        assert "Enhancements (0)" in captured.out

    def test_list_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list with no issues prints a message and returns 0."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-issues", "list", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "No active issues" in captured.out


class TestIssuesCLISequence:
    """Tests for ll-issues sequence sub-command."""

    def test_sequence_basic(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence outputs issues in priority order."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "sequence", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "no blockers" in captured.out

    def test_sequence_limit(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --limit 2 shows at most 2 issues."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "sequence", "--limit", "2", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # Should show 2 of 5 issues
        assert "+3 more" in captured.out

    def test_sequence_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence with no issues prints a message and returns 0."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)

        with patch.object(
            sys, "argv", ["ll-issues", "sequence", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "No active issues" in captured.out


class TestIssuesCLIImpactEffort:
    """Tests for ll-issues impact-effort sub-command."""

    def test_impact_effort_renders_grid(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort renders the 2x2 ASCII grid."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "EFFORT" in captured.out
        assert "IMPACT" in captured.out
        assert "QUICK WINS" in captured.out
        assert "MAJOR PROJECTS" in captured.out
        assert "FILL-INS" in captured.out
        assert "THANKLESS" in captured.out

    def test_impact_effort_shows_issue_ids(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort grid contains issue IDs."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            main_issues()

        captured = capsys.readouterr()
        # P0 and P1 issues → high impact → should appear somewhere in top half
        assert "BUG-001" in captured.out or "BUG-002" in captured.out

    def test_impact_effort_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort with no issues prints a message and returns 0."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "No active issues" in captured.out

    def test_impact_effort_frontmatter_override(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort uses frontmatter effort/impact when present."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        # P5 (would normally be low impact) but frontmatter says impact: 3
        (bugs_dir / "P5-BUG-010-low-priority.md").write_text(
            "---\neffort: 1\nimpact: 3\n---\n# BUG-010: Low priority high impact\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            main_issues()

        captured = capsys.readouterr()
        # BUG-010 should appear in QUICK WINS (high impact, low effort)
        assert "BUG-010" in captured.out
        assert "QUICK WINS" in captured.out


class TestIssuesCLIShow:
    """Tests for ll-issues show sub-command."""

    def test_show_by_numeric_id(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show finds issue by numeric ID only."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "001", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "Critical crash on startup" in captured.out

    def test_show_by_type_and_id(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show finds issue by TYPE-NNN format."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-001", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "FEAT-001" in captured.out
        assert "Add dark mode" in captured.out

    def test_show_by_full_prefix(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show finds issue by P-TYPE-NNN format."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "P0-BUG-001", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "Priority: P0" in captured.out

    def test_show_not_found(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show returns 1 and prints error when issue not found."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "999", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_show_completed_issue(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays Completed status for issues in completed/ directory."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        completed_dir = temp_project_dir / ".issues" / "completed"
        (completed_dir / "P2-BUG-050-fixed-issue.md").write_text(
            "# BUG-050: Fixed issue\n\n## Summary\nThis was fixed."
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "BUG-050", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Status: Completed" in captured.out

    def test_show_with_frontmatter_scores(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays confidence_score and outcome_confidence from frontmatter."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P1-FEAT-099-scored-issue.md").write_text(
            "---\nconfidence_score: 85\noutcome_confidence: 78\neffort: Small\n---\n"
            "# FEAT-099: Scored issue\n\n## Summary\nHas scores."
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-099", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Confidence: 85" in captured.out
        assert "Outcome: 78" in captured.out
        assert "Effort: Small" in captured.out

    def test_show_missing_frontmatter_graceful(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show handles issues without frontmatter scores gracefully."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "BUG-002", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-002" in captured.out
        # Should not contain confidence/outcome lines when not in frontmatter
        assert "Confidence:" not in captured.out
        assert "Outcome:" not in captured.out

    def test_show_box_drawing_characters(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show uses box-drawing characters for card border."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "BUG-001", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            main_issues()

        captured = capsys.readouterr()
        assert "\u250c" in captured.out  # ┌
        assert "\u2510" in captured.out  # ┐
        assert "\u2514" in captured.out  # └
        assert "\u2518" in captured.out  # ┘
        assert "\u2502" in captured.out  # │
        assert "\u2500" in captured.out  # ─


class TestIssuesCLIHelp:
    """Tests for ll-issues help and no-command behavior."""

    def test_no_subcommand_returns_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Running ll-issues with no sub-command returns exit code 1."""
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues"]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

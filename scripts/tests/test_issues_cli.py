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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "next-id", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # issues_dir fixture has BUG-001, BUG-002, BUG-003, FEAT-001, FEAT-002
        assert captured.out.strip() == "004"


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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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

    def test_list_filter_by_priority_multi_value(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --priority P0,P1 shows issues matching either priority."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "list", "--priority", "P0,P1", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out  # BUG-001 is P0
        assert "BUG-002" in captured.out  # BUG-002 is P1
        assert "BUG-003" not in captured.out  # BUG-003 is P2

    def test_list_empty_groups_shown(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list shows all type groups including empty ones (e.g. ENH when no ENH issues)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-issues", "list", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "No active issues" in captured.out

    def test_list_json_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --json outputs a valid JSON array with required fields."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) > 0
        item = data[0]
        assert "id" in item
        assert "priority" in item
        assert "type" in item
        assert "title" in item
        assert "path" in item
        ids = [entry["id"] for entry in data]
        assert "BUG-001" in ids
        assert "FEAT-001" in ids

    def test_list_json_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --json with no issues outputs empty JSON array."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "No active issues" in captured.out

    def test_list_json_no_color_codes(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --json output contains no ANSI color codes."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out
        # Verify it's still valid JSON
        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_limit_caps_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --limit N returns at most N issues."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "list", "--flat", "--limit", "2", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.splitlines() if line.strip()]
        assert len(lines) == 2

    def test_limit_short_flag(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list -n N works as short alias for --limit."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "list", "--flat", "-n", "2", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.splitlines() if line.strip()]
        assert len(lines) == 2

    def test_limit_zero_raises_error(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --limit 0 returns exit code 1 with an error message."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--limit", "0", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_limit_negative_raises_error(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --limit -1 returns exit code 1 with an error message."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--limit", "-1", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_limit_omitted_returns_all(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list without --limit returns all issues unchanged."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "--flat", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line for line in captured.out.splitlines() if line.strip()]
        # issues_dir has 5 issues (3 bugs + 2 features)
        assert len(lines) == 5


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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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

    def test_sequence_json_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --json outputs a valid JSON array with required fields."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "sequence", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) > 0
        item = data[0]
        assert "id" in item
        assert "priority" in item
        assert "title" in item
        assert "path" in item
        assert "blocked_by" in item
        assert "blocks" in item
        assert isinstance(item["blocked_by"], list)

    def test_sequence_json_no_color_codes(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --json output contains no ANSI color codes."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "sequence", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out
        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_sequence_type_filter_bug(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --type BUG shows only bug issues."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "sequence", "--type", "BUG", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "BUG-002" in captured.out
        assert "FEAT-001" not in captured.out
        assert "FEAT-002" not in captured.out

    def test_sequence_type_filter_feat(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --type FEAT shows only feature issues."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "sequence", "--type", "FEAT", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "FEAT-001" in captured.out
        assert "FEAT-002" in captured.out
        assert "BUG-001" not in captured.out

    def test_sequence_type_filter_no_matches(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --type ENH shows 'No active issues' when no enhancements exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        (issues_dir / "enhancements").mkdir(parents=True, exist_ok=True)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "sequence", "--type", "ENH", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "No active issues" in captured.out

    def test_sequence_json_type_filter_included(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """sequence --type BUG --json includes type_filter in each item."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "sequence",
                "--type",
                "BUG",
                "--json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert all(item.get("type_filter") == "BUG" for item in data)
        assert all(item["id"].startswith("BUG-") for item in data)


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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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

    def test_impact_effort_no_ansi_when_no_color(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort produces no ANSI escape codes when NO_COLOR is active."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        import little_loops.cli.output as output_mod

        original = output_mod._USE_COLOR
        try:
            output_mod._USE_COLOR = False
            with patch.object(
                sys, "argv", ["ll-issues", "impact-effort", "--config", str(temp_project_dir)]
            ):
                from little_loops.cli import main_issues

                result = main_issues()
        finally:
            output_mod._USE_COLOR = original

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out

    def test_impact_effort_shows_total_count(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort prints a summary line with total issue count."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "issue" in captured.out

    def test_impact_effort_frontmatter_override(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort uses frontmatter effort/impact when present."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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

    def test_impact_effort_filter_by_type(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort --type BUG shows only bugs in the matrix."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "impact-effort", "--type", "BUG", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out or "BUG-002" in captured.out or "BUG-003" in captured.out
        assert "FEAT-001" not in captured.out
        assert "FEAT-002" not in captured.out

    def test_impact_effort_json_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """impact-effort --json returns valid object with all four quadrant keys."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "quick_wins" in data
        assert "major_projects" in data
        assert "fill_ins" in data
        assert "thankless_tasks" in data
        all_issues = (
            data["quick_wins"] + data["major_projects"] + data["fill_ins"] + data["thankless_tasks"]
        )
        assert len(all_issues) == 5
        for item in all_issues:
            assert "id" in item
            assert "title" in item
            assert "priority" in item
            assert "effort" in item
            assert "impact" in item

    def test_impact_effort_json_quadrant_correctness(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """P5 issue with effort:1, impact:3 frontmatter appears in quick_wins."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P5-BUG-010-low-priority.md").write_text(
            "---\neffort: 1\nimpact: 3\n---\n# BUG-010: Low priority high impact\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        quick_win_ids = [item["id"] for item in data["quick_wins"]]
        assert "BUG-010" in quick_win_ids

    def test_impact_effort_json_type_filter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--type BUG --json emits no FEAT ids in any quadrant."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "impact-effort",
                "--type",
                "BUG",
                "--json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        all_ids = [item["id"] for q in data.values() for item in q]
        assert all(not id_.startswith("FEAT") for id_ in all_ids)
        assert any(id_.startswith("BUG") for id_ in all_ids)

    def test_impact_effort_json_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-j short form returns a dict with the four quadrant keys."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "-j", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert set(data.keys()) == {"quick_wins", "major_projects", "fill_ins", "thankless_tasks"}

    def test_impact_effort_json_suppresses_ascii(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ASCII grid is suppressed when --json is passed."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "impact-effort", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "EFFORT" not in captured.out
        assert "QUICK WINS" not in captured.out


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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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
        config_path = temp_project_dir / ".ll" / "ll-config.json"
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

    def test_show_with_summary(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays summary text from ## Summary section."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-200-with-summary.md").write_text(
            "# FEAT-200: Feature with summary\n\n"
            "## Summary\n\nThis is a detailed summary of the feature.\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-200", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "This is a detailed summary of the feature." in captured.out

    def test_show_with_long_summary(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays full summary without truncation."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        long_text = "A" * 100
        (features_dir / "P2-FEAT-201-long-summary.md").write_text(
            f"# FEAT-201: Long summary\n\n## Summary\n\n{long_text}\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-201", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # Full text should appear without truncation
        assert long_text in captured.out
        assert "..." not in captured.out

    def test_show_with_multiline_summary(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays multi-line summary in its own section."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-203-multiline-summary.md").write_text(
            "# FEAT-203: Multi-line summary\n\n"
            "## Summary\n\n"
            "First line of the summary.\n"
            "Second line of the summary.\n"
            "Third line of the summary.\n\n"
            "## Details\n\nMore info here.\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-203", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "First line of the summary." in captured.out
        assert "Second line of the summary." in captured.out
        assert "Third line of the summary." in captured.out

    def test_show_with_integration_files(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays integration file count from ### Files to Modify."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-202-with-integration.md").write_text(
            "# FEAT-202: With integration map\n\n"
            "## Integration Map\n\n"
            "### Files to Modify\n"
            "- `src/foo.py` - update handler\n"
            "- `src/bar.py` - add new function\n"
            "- `tests/test_foo.py` - add tests\n\n"
            "### Dependent Files\n"
            "- `src/baz.py`\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-202", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Integration: 3 files" in captured.out

    def test_show_with_risk(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays risk level from ## Impact section."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        bugs_dir = temp_project_dir / ".issues" / "bugs"
        (bugs_dir / "P1-BUG-203-with-risk.md").write_text(
            "# BUG-203: Bug with risk\n\n## Impact\n\n- **Effort**: Medium\n- **Risk**: High\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "BUG-203", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # Risk is shown in metadata section
        assert "Risk: High" in captured.out

    def test_show_with_labels(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays labels from ## Labels section."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-204-with-labels.md").write_text(
            "# FEAT-204: Feature with labels\n\n## Labels\n\n`cli`, `enhancement`, `docs`\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-204", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Labels: cli, enhancement, docs" in captured.out

    def test_show_with_session_log(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays session log history with deduped command counts."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-205-with-log.md").write_text(
            "# FEAT-205: Feature with session log\n\n"
            "## Session Log\n"
            "- `/ll:capture-issue` - 2026-03-01 - `~/.claude/sess1.jsonl`\n"
            "- `/ll:refine-issue` - 2026-03-01 - `~/.claude/sess2.jsonl`\n"
            "- `/ll:refine-issue` - 2026-03-01 - `~/.claude/sess3.jsonl`\n"
            "- `/ll:refine-issue` - 2026-03-01 - `~/.claude/sess4.jsonl`\n"
            "\n---\n\n## Status\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-205", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "History: " in captured.out
        assert "/ll:capture-issue" in captured.out
        assert "/ll:refine-issue (3)" in captured.out

    def test_show_relative_path(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays relative path instead of absolute."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "BUG-001", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Path: .issues/" in captured.out
        # Should NOT contain absolute path
        assert "Path: /" not in captured.out

    def test_show_new_fields_absent_gracefully(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show omits new fields when not present in issue file."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        # Create a minimal issue with no Summary, Impact, Labels, Session Log, or Integration Map
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        (bugs_dir / "P1-BUG-300-minimal.md").write_text("# BUG-300: Minimal issue\n")

        with patch.object(
            sys, "argv", ["ll-issues", "show", "BUG-300", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-300" in captured.out
        assert "Summary:" not in captured.out
        assert "Integration:" not in captured.out
        assert "Risk:" not in captured.out
        assert "Labels:" not in captured.out
        assert "History:" not in captured.out
        # Source is absent (no discovered_by in frontmatter); Norm/Fmt still appear
        assert "Source:" not in captured.out

    def test_show_json_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show --json outputs valid JSON with required card fields."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "show", "--json", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, dict)
        assert data.get("issue_id") == "BUG-001"
        assert "title" in data
        assert "priority" in data
        assert "path" in data

    def test_show_json_no_color_codes(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show --json output contains no ANSI color codes."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "show", "--json", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out
        data = json.loads(captured.out)
        assert isinstance(data, dict)

    def test_show_json_not_found(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show --json returns 1 when issue not found (JSON flag does not suppress error)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "show", "--json", "999", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_show_with_source_norm_fmt(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays Source, Norm, and Fmt fields from frontmatter and filename."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        enh_dir = temp_project_dir / ".issues" / "enhancements"
        enh_dir.mkdir(parents=True, exist_ok=True)
        (enh_dir / "P3-ENH-400-source-test.md").write_text(
            "---\ndiscovered_by: /ll:capture-issue\n---\n# ENH-400: Source test\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "ENH-400", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Source: capture" in captured.out
        assert "Norm: \u2713" in captured.out

    def test_show_json_includes_source_norm_fmt(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show --json output includes source, norm, and fmt keys."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        enh_dir = temp_project_dir / ".issues" / "enhancements"
        enh_dir.mkdir(parents=True, exist_ok=True)
        (enh_dir / "P3-ENH-401-json-fields-test.md").write_text(
            "---\ndiscovered_by: /ll:scan-codebase\n---\n# ENH-401: JSON fields test\n"
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "show", "--json", "ENH-401", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "source" in data
        assert "norm" in data
        assert "fmt" in data
        assert data["source"] == "scan"

    def test_show_dim_scores_present(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show displays dimension score line when all four fields are in frontmatter."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-500-dim-scores.md").write_text(
            "---\n"
            "confidence_score: 85\n"
            "outcome_confidence: 72\n"
            "score_complexity: 22\n"
            "score_test_coverage: 24\n"
            "score_ambiguity: 25\n"
            "score_change_surface: 22\n"
            "---\n"
            "# FEAT-500: With dimension scores\n\n"
            "## Summary\nHas all four dimension scores."
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-500", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Cmplx: 22" in captured.out
        assert "Tcov: 24" in captured.out
        assert "Ambig: 25" in captured.out
        assert "Chsrf: 22" in captured.out

    def test_show_dim_scores_absent(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show omits dimension score line when dimension fields are absent (backward-compat)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-501-no-dim-scores.md").write_text(
            "---\nconfidence_score: 80\noutcome_confidence: 70\n---\n"
            "# FEAT-501: Without dimension scores\n"
        )

        with patch.object(
            sys, "argv", ["ll-issues", "show", "FEAT-501", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Confidence: 80" in captured.out
        assert "Cmplx:" not in captured.out
        assert "Tcov:" not in captured.out
        assert "Ambig:" not in captured.out
        assert "Chsrf:" not in captured.out

    def test_show_json_includes_dim_scores(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """show --json output includes all four dimension score keys with correct values."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        features_dir = temp_project_dir / ".issues" / "features"
        (features_dir / "P2-FEAT-502-json-dim-scores.md").write_text(
            "---\n"
            "confidence_score: 90\n"
            "outcome_confidence: 80\n"
            "score_complexity: 20\n"
            "score_test_coverage: 23\n"
            "score_ambiguity: 21\n"
            "score_change_surface: 19\n"
            "---\n"
            "# FEAT-502: JSON dimension scores\n"
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "show", "--json", "FEAT-502", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("score_complexity") == "20"
        assert data.get("score_test_coverage") == "23"
        assert data.get("score_ambiguity") == "21"
        assert data.get("score_change_surface") == "19"


class TestIssuesCLICount:
    """Tests for ll-issues count sub-command."""

    def test_count_all_issues(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count outputs total number of active issues."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "count", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

    def test_count_filter_by_type(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --type BUG shows only bug count."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "count", "--type", "BUG", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "3"

    def test_count_filter_by_priority(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --priority P0 shows only P0 count."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "count", "--priority", "P0", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

    def test_count_filter_by_priority_multi_value(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --priority P0,P1 counts issues matching either priority."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "count", "--priority", "P0,P1", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "3"  # BUG-001 (P0) + BUG-002 (P1) + FEAT-001 (P1)

    def test_count_json_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --json outputs valid JSON with total, by_type, and by_priority."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "count", "--json", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] == 5
        assert data["by_type"]["BUG"] == 3
        assert data["by_type"]["FEAT"] == 2
        assert data["by_type"]["ENH"] == 0
        assert data["by_priority"]["P0"] == 1
        assert data["by_priority"]["P1"] == 2
        assert data["by_priority"]["P2"] == 2

    def test_count_json_with_type_filter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --type BUG --json filters JSON output to bugs only."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "count", "--type", "BUG", "--json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] == 3
        assert data["by_type"]["BUG"] == 3
        assert data["by_type"]["FEAT"] == 0

    def test_count_empty_project(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count with no issues outputs 0."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-issues", "count", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"

    def test_count_alias_c(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count alias 'c' works the same as 'count'."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues", "c", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

    def test_count_status_completed(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --status completed counts issues in the completed directory."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        completed_dir = issues_dir / "completed"
        (completed_dir / "P1-BUG-010-fixed-crash.md").write_text(
            "# BUG-010: Fixed crash\n\n## Summary\nWas crashing."
        )
        (completed_dir / "P2-FEAT-011-shipped-feature.md").write_text(
            "# FEAT-011: Shipped feature\n\n## Summary\nShipped."
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "count", "--status", "completed", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "2"

    def test_count_status_deferred(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --status deferred counts issues in the deferred directory."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        deferred_dir = issues_dir / "deferred"
        (deferred_dir / "P3-FEAT-020-parked.md").write_text(
            "# FEAT-020: Parked feature\n\n## Summary\nParked for now."
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "count", "--status", "deferred", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

    def test_count_status_all(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --status all counts across active, completed, and deferred."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        completed_dir = issues_dir / "completed"
        deferred_dir = issues_dir / "deferred"
        (completed_dir / "P1-BUG-010-fixed.md").write_text("# BUG-010: Fixed\n\n## Summary\nFixed.")
        (deferred_dir / "P3-FEAT-020-parked.md").write_text(
            "# FEAT-020: Parked\n\n## Summary\nParked."
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "count", "--status", "all", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # 5 active + 1 completed + 1 deferred = 7
        assert captured.out.strip() == "7"

    def test_count_status_active_default_unchanged(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count default (no --status) still only counts active issues."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        completed_dir = issues_dir / "completed"
        (completed_dir / "P1-BUG-010-fixed.md").write_text("# BUG-010: Fixed\n\n## Summary\nFixed.")

        with patch.object(sys, "argv", ["ll-issues", "count", "--config", str(temp_project_dir)]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

    def test_count_json_includes_status(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """count --json --status completed includes status field in output."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        completed_dir = issues_dir / "completed"
        (completed_dir / "P1-BUG-010-fixed.md").write_text("# BUG-010: Fixed\n\n## Summary\nFixed.")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "count",
                "--status",
                "completed",
                "--json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] == 1
        assert data["status"] == "completed"


class TestIssuesAppendLog:
    """Tests for ll-issues append-log sub-command."""

    def test_append_log_writes_entry(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """append-log writes a correctly-formatted entry parseable by count_session_commands."""
        import tempfile
        from unittest.mock import patch as mock_patch

        from little_loops.session_log import count_session_commands

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            jsonl_path = Path(f.name)

        try:
            with mock_patch(
                "little_loops.session_log.get_current_session_jsonl",
                return_value=jsonl_path,
            ):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "ll-issues",
                        "append-log",
                        str(issue_file),
                        "/ll:refine-issue",
                        "--config",
                        str(temp_project_dir),
                    ],
                ):
                    from little_loops.cli import main_issues

                    result = main_issues()

            assert result == 0
            content = issue_file.read_text()
            counts = count_session_commands(content)
            assert counts.get("/ll:refine-issue", 0) == 1
        finally:
            jsonl_path.unlink(missing_ok=True)

    def test_append_log_returns_1_when_no_jsonl(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """append-log returns exit code 1 when session JSONL cannot be resolved."""
        from unittest.mock import patch as mock_patch

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        original_content = issue_file.read_text()

        with mock_patch(
            "little_loops.session_log.get_current_session_jsonl",
            return_value=None,
        ):
            with patch.object(
                sys,
                "argv",
                [
                    "ll-issues",
                    "append-log",
                    str(issue_file),
                    "/ll:refine-issue",
                    "--config",
                    str(temp_project_dir),
                ],
            ):
                from little_loops.cli import main_issues

                result = main_issues()

        assert result == 1
        # File should be unmodified when session JSONL can't be resolved
        assert issue_file.read_text() == original_content


@pytest.fixture
def list_sort_issues_dir(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Create issue directories with varied frontmatter for list --sort tests."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config, indent=2))

    issues_base = temp_project_dir / ".issues"
    bugs_dir = issues_base / "bugs"
    features_dir = issues_base / "features"
    for d in (bugs_dir, features_dir):
        d.mkdir(parents=True, exist_ok=True)

    # P0, confidence=90, outcome=80, 2 refinement commands, oldest date
    (bugs_dir / "P0-BUG-001-critical.md").write_text(
        "---\nid: BUG-001\ndiscovered_date: 2026-01-10\nconfidence_score: 90\noutcome_confidence: 80\n---\n"
        "# BUG-001: Critical crash\n\n## Summary\nApp crashes.\n\n"
        "## Session Log\n"
        "- `/ll:refine-issue` - 2026-01-11T00:00:00Z\n"
        "- `/ll:verify-issues` - 2026-01-12T00:00:00Z\n"
    )
    # P2, confidence=50, outcome=95, 0 refinements, newest date
    (bugs_dir / "P2-BUG-002-caching.md").write_text(
        "---\nid: BUG-002\ndiscovered_date: 2026-03-01\nconfidence_score: 50\noutcome_confidence: 95\n---\n"
        "# BUG-002: Caching issue\n\n## Summary\nCache broken.\n"
    )
    # P1, confidence=70, outcome=60, 1 refinement, middle date
    (features_dir / "P1-FEAT-010-dark-mode.md").write_text(
        "---\nid: FEAT-010\ndiscovered_date: 2026-02-15\nconfidence_score: 70\noutcome_confidence: 60\n---\n"
        "# FEAT-010: Dark mode\n\n## Summary\nDark theme.\n\n"
        "## Session Log\n"
        "- `/ll:refine-issue` - 2026-02-16T00:00:00Z\n"
    )

    return issues_base


class TestListSorting:
    """Tests for ll-issues list --sort argument."""

    def test_sort_by_priority_default(
        self,
        temp_project_dir: Path,
        list_sort_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default sort is priority ascending: P0 < P1 < P2."""
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "list", "--flat", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [ln for ln in captured.out.splitlines() if ln.strip()]
        p0_idx = next(i for i, ln in enumerate(lines) if "BUG-001" in ln)
        p1_idx = next(i for i, ln in enumerate(lines) if "FEAT-010" in ln)
        p2_idx = next(i for i, ln in enumerate(lines) if "BUG-002" in ln)
        assert p0_idx < p1_idx < p2_idx

    def test_sort_by_confidence_asc(
        self,
        temp_project_dir: Path,
        list_sort_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--sort confidence --asc orders by confidence_score ascending: 50 < 70 < 90."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "list",
                "--flat",
                "--sort",
                "confidence",
                "--asc",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [ln for ln in captured.out.splitlines() if ln.strip()]
        bug002_idx = next(i for i, ln in enumerate(lines) if "BUG-002" in ln)
        feat010_idx = next(i for i, ln in enumerate(lines) if "FEAT-010" in ln)
        bug001_idx = next(i for i, ln in enumerate(lines) if "BUG-001" in ln)
        assert bug002_idx < feat010_idx < bug001_idx

    def test_sort_by_created_default_desc(
        self,
        temp_project_dir: Path,
        list_sort_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--sort created defaults to descending (newest first): 2026-03-01 > 2026-02-15 > 2026-01-10."""
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "list", "--flat", "--sort", "created", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [ln for ln in captured.out.splitlines() if ln.strip()]
        bug002_idx = next(i for i, ln in enumerate(lines) if "BUG-002" in ln)
        feat010_idx = next(i for i, ln in enumerate(lines) if "FEAT-010" in ln)
        bug001_idx = next(i for i, ln in enumerate(lines) if "BUG-001" in ln)
        assert bug002_idx < feat010_idx < bug001_idx

    def test_sort_desc_flag(
        self,
        temp_project_dir: Path,
        list_sort_issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--sort priority --desc reverses priority order: P2 > P1 > P0."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "list",
                "--flat",
                "--sort",
                "priority",
                "--desc",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 0
        lines = [ln for ln in captured.out.splitlines() if ln.strip()]
        p0_idx = next(i for i, ln in enumerate(lines) if "BUG-001" in ln)
        p1_idx = next(i for i, ln in enumerate(lines) if "FEAT-010" in ln)
        p2_idx = next(i for i, ln in enumerate(lines) if "BUG-002" in ln)
        assert p2_idx < p1_idx < p0_idx


class TestIssuesCLIHelp:
    """Tests for ll-issues help and no-command behavior."""

    def test_no_subcommand_returns_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Running ll-issues with no sub-command returns exit code 1."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(sys, "argv", ["ll-issues"]):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1


class TestIssuesCLIShortForms:
    """Tests for ll-issues short-form CLI options (ENH-908)."""

    def test_list_type_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-T is equivalent to --type on list."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "-T", "BUG", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "FEAT-001" not in captured.out

    def test_list_priority_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-p is equivalent to --priority on list."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "-p", "P0", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "BUG-002" not in captured.out

    def test_list_status_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-S is equivalent to --status on list."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "-S", "active", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out

    def test_list_json_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-j is equivalent to --json on list."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "-j", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_list_sort_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-s is equivalent to --sort on list."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "list", "-s", "id", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_search_type_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-T is equivalent to --type on search."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "search", "-T", "BUG", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "BUG" in captured.out
        assert "FEAT" not in captured.out

    def test_search_json_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-j is equivalent to --json on search."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "search", "-j", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)

    def test_search_format_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-f is equivalent to --format on search."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "search", "-f", "ids", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_search_limit_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-n is equivalent to --limit on search."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "search", "-n", "1", "-j", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) <= 1

    def test_count_json_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-j is equivalent to --json on count."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys, "argv", ["ll-issues", "count", "-j", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data

    def test_sequence_limit_short(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-n is equivalent to --limit on sequence."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "sequence", "-n", "2", "-j", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) <= 2


class TestIssuesSkip:
    """Tests for ll-issues skip sub-command."""

    def test_skip_renames_file_with_default_priority(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """skip renames P0-BUG-001 to P5-BUG-001 by default."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        original = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        expected = issues_dir / "bugs" / "P5-BUG-001-critical-crash.md"

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "skip", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert not original.exists(), "Original file should be gone after rename"
        assert expected.exists(), "Renamed file should exist with P5 prefix"

    def test_skip_appends_skip_log_section(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """skip appends a ## Skip Log section with timestamp to the issue file."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "skip", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        renamed = issues_dir / "bugs" / "P5-BUG-001-critical-crash.md"
        content = renamed.read_text()
        assert "## Skip Log" in content
        assert "**Date**:" in content
        assert "**Reason**:" in content

    def test_skip_custom_priority_and_reason(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """skip --priority P3 --reason 'text' renames to P3 and records reason."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        expected = issues_dir / "bugs" / "P3-BUG-001-critical-crash.md"

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "skip",
                "BUG-001",
                "--priority",
                "P3",
                "--reason",
                "retry after CI fix",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert expected.exists()
        content = expected.read_text()
        assert "retry after CI fix" in content

    def test_skip_prints_new_path_to_stdout(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """skip prints the new file path to stdout on success."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "skip", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "P5-BUG-001-critical-crash.md" in captured.out

    def test_skip_not_found_returns_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """skip returns exit code 1 when the issue ID does not exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "skip", "BUG-999", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_skip_lowers_ranking(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """After skipping P0-BUG-001 to P5, the P1 issue now outranks it."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        original = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        skipped = issues_dir / "bugs" / "P5-BUG-001-critical-crash.md"
        lower_priority = issues_dir / "bugs" / "P1-BUG-002-slow-query.md"

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "skip", "BUG-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        # BUG-001 now lives at P5 — the lower-priority P1 issue still exists
        assert not original.exists(), "P0 file should be renamed"
        assert skipped.exists(), "P5 file should now exist"
        assert lower_priority.exists(), "P1-BUG-002 is unaffected"
        # P5 sorts after P1 — verify by filename comparison
        assert skipped.name > lower_priority.name

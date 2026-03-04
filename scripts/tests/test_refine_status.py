"""Tests for ll-issues refine-status sub-command."""

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


class TestRefineStatusTable:
    """Tests for refine-status table output."""

    def test_no_issues(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """refine-status prints message when no active issues exist."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert "No active issues found" in capsys.readouterr().out

    def test_table_has_header_and_separator(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """refine-status table output has header row and separator line."""
        _write_config(temp_project_dir, sample_config)

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert any("ID" in ln and "Pri" in ln and "Title" in ln for ln in lines), (
            "Header row missing"
        )
        assert any(set(ln.strip()).issubset({"-", " "}) and len(ln.strip()) > 5 for ln in lines), (
            "Separator line missing"
        )

    def test_table_shows_issue_ids(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """refine-status table contains issue IDs from active issues."""
        _write_config(temp_project_dir, sample_config)

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "BUG-001" in out
        assert "FEAT-001" in out

    def test_sort_order_by_total_desc(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Issues with more session commands appear before those with fewer."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        # BUG-010: 3 session commands; BUG-011: 0 commands
        _make_issue(
            bugs_dir,
            "P2-BUG-010-refined.md",
            "BUG-010: Refined issue",
            session_commands=["/ll:scan-codebase", "/ll:refine-issue", "/ll:ready-issue"],
        )
        _make_issue(bugs_dir, "P2-BUG-011-new.md", "BUG-011: Brand new issue")

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        lines = out.splitlines()
        positions = {
            line: i for i, line in enumerate(lines) if "BUG-010" in line or "BUG-011" in line
        }
        bug010_pos = next((i for line, i in positions.items() if "BUG-010" in line), None)
        bug011_pos = next((i for line, i in positions.items() if "BUG-011" in line), None)
        assert bug010_pos is not None
        assert bug011_pos is not None
        assert bug010_pos < bug011_pos, "Higher Total should sort first"

    def test_refine_column_shows_integer_count(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Refine column shows integer count (1 for refined once, 0 for untouched)."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P1-BUG-020-partially-refined.md",
            "BUG-020: Partially refined",
            session_commands=["/ll:refine-issue"],
        )
        _make_issue(bugs_dir, "P2-BUG-021-untouched.md", "BUG-021: Untouched")

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        lines = out.splitlines()
        bug020_line = next((ln for ln in lines if "BUG-020" in ln), None)
        bug021_line = next((ln for ln in lines if "BUG-021" in ln), None)
        assert bug020_line is not None
        assert bug021_line is not None
        assert "1" in bug020_line, "Refined once should show '1' in refine column"
        assert "0" in bug021_line, "Untouched should show '0' in refine column"

    def test_refine_column_shows_count_for_multiple_runs(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Refine column shows count > 1 when /ll:refine-issue appears multiple times."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P2-BUG-022-multi-refined.md",
            "BUG-022: Multi refined",
            session_commands=[
                "/ll:refine-issue",
                "/ll:refine-issue",
                "/ll:refine-issue",
            ],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        lines = out.splitlines()
        bug022_line = next((ln for ln in lines if "BUG-022" in ln), None)
        assert bug022_line is not None
        assert "3" in bug022_line, "Three refine runs should show '3' in refine column"

    def test_ready_and_outconf_columns(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """confidence_score and outcome_confidence are shown in Ready/OutConf columns."""
        _write_config(temp_project_dir, sample_config)
        features_dir = temp_project_dir / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            features_dir,
            "P2-FEAT-030-scored.md",
            "FEAT-030: Scored feature",
            confidence_score=88,
            outcome_confidence=72,
            session_commands=["/ll:confidence-check"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "88" in out, "confidence_score should appear"
        assert "72" in out, "outcome_confidence should appear"

    def test_type_filter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--type BUG filters to bugs only."""
        _write_config(temp_project_dir, sample_config)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--type", "BUG", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "BUG-001" in out
        assert "FEAT-001" not in out

    def test_norm_column_header_present(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """refine-status table header includes 'Norm' column."""
        _write_config(temp_project_dir, sample_config)

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "norm" in out, "norm column header should appear"

    def test_norm_checkmark_for_normalized_filename(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """✓ appears in Norm column for filenames matching naming convention."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(bugs_dir, "P2-BUG-080-normalized.md", "BUG-080: Normalized filename")

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        # ✓ from Norm column (and possibly from cmd columns too, but ✗ must not appear)
        assert "\u2713" in out, "Checkmark ✓ should appear for normalized filename"
        assert "\u2717" not in out, "X ✗ should not appear when all filenames are normalized"

    def test_norm_x_for_non_normalized_filename(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """✗ appears in Norm column for filenames not matching naming convention."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(bugs_dir, "invalid-filename.md", "Non-normalized issue")

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "\u2717" in out, "X ✗ should appear for non-normalized filename"

    def test_key_section_in_default_output(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Key section appears after the table in default (table) mode."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P2-BUG-100-with-cmd.md",
            "BUG-100: Key section test",
            session_commands=["/ll:format-issue"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "Key:" in out, "Key section header should appear"
        assert "source" in out, "source column entry should appear in Key"
        assert "/ll:format-issue" in out, (
            "Full command name should appear in Key for non-source cmds"
        )
        assert "Readiness score" in out, "Ready explanation should appear in Key"
        assert "Outcome confidence" in out, "OutConf explanation should appear in Key"

    def test_no_key_flag_suppresses_key_section(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--no-key suppresses the Key section."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P2-BUG-101-no-key.md",
            "BUG-101: No key test",
            session_commands=["/ll:scan-codebase"],
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--no-key", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "Key:" not in out, "--no-key should suppress the Key section"

    def test_json_output_omits_key_section(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--format json output does not include a Key section."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P2-BUG-102-json-key.md",
            "BUG-102: JSON no key",
            session_commands=["/ll:scan-codebase"],
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--format", "json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "Key:" not in out, "JSON output should not include Key section"

    def test_dynamic_columns_from_session_log(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Column headers are derived from session log commands, not hardcoded."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P1-BUG-040-with-cmd.md",
            "BUG-040: Issue with unusual command",
            session_commands=["/ll:my-custom-cmd"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        # Header should contain (at least the prefix of) the short command name
        # "my-custom-cmd" stripped of "/ll:" is "my-custom-cmd"; truncated to _CMD_WIDTH=8 → "my-cust…"
        assert "my-cust" in out

    def test_tradeoff_column_shows_checkmark(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """tradeoff column appears and shows ✓ only for issues that had tradeoff-review run."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P1-BUG-110-tradeoff.md",
            "BUG-110: Tradeoff reviewed",
            session_commands=["/ll:tradeoff-review-issues"],
        )
        _make_issue(bugs_dir, "P2-BUG-111-no-tradeoff.md", "BUG-111: No tradeoff review")

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "tradeoff" in out, "'tradeoff' column header should appear"
        lines = out.splitlines()
        bug110_line = next((ln for ln in lines if "BUG-110" in ln), None)
        assert bug110_line is not None
        assert "\u2713" in bug110_line, "BUG-110 should show ✓ in tradeoff column"

    def test_map_column_shows_checkmark(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """map column appears and shows ✓ only for issues that had map-dependencies run."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P1-BUG-120-mapped.md",
            "BUG-120: Dependencies mapped",
            session_commands=["/ll:map-dependencies"],
        )
        _make_issue(bugs_dir, "P2-BUG-121-no-map.md", "BUG-121: No dependency map")

        with patch.object(
            sys, "argv", ["ll-issues", "refine-status", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        assert "map" in out, "'map' column header should appear"
        lines = out.splitlines()
        bug120_line = next((ln for ln in lines if "BUG-120" in ln), None)
        assert bug120_line is not None
        assert "\u2713" in bug120_line, "BUG-120 should show ✓ in map column"

    def test_table_row_width_fits_terminal(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Table rows must not exceed the terminal width."""
        from unittest.mock import patch

        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        # Issue with several cmd columns to stress-test width calculation
        _make_issue(
            bugs_dir,
            "P2-BUG-200-width-test.md",
            "BUG-200: Width test issue with a moderately long title",
            session_commands=[
                "/ll:format-issue",
                "/ll:verify-issues",
                "/ll:refine-issue",
                "/ll:tradeoff-review-issues",
            ],
        )

        import os

        terminal_width = 120
        fake_size = os.terminal_size((terminal_width, 40))

        with (
            patch("shutil.get_terminal_size", return_value=fake_size),
            patch.object(
                sys,
                "argv",
                ["ll-issues", "refine-status", "--no-key", "--config", str(temp_project_dir)],
            ),
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        data_lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("\n")]
        for line in data_lines:
            assert len(line) <= terminal_width, (
                f"Row width {len(line)} exceeds terminal width {terminal_width}: {line!r}"
            )


class TestRefineStatusJson:
    """Tests for refine-status --format json output."""

    def test_json_output_is_jsonl(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--format json emits one JSON object per line (JSONL)."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P1-BUG-050-json-test.md",
            "BUG-050: JSON test issue",
            confidence_score=90,
            outcome_confidence=80,
            session_commands=["/ll:refine-issue", "/ll:ready-issue"],
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--format", "json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["id"] == "BUG-050"
        assert record["priority"] == "P1"
        assert record["confidence_score"] == 90
        assert record["outcome_confidence"] == 80
        assert "refine-issue" in record["commands"][0]
        assert record["total"] == 2
        assert record["refine_count"] == 1

    def test_json_missing_scores_are_null(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output uses null for absent confidence/outcome scores."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(bugs_dir, "P3-BUG-060-no-scores.md", "BUG-060: No scores")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--format", "json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        out = capsys.readouterr().out
        record = json.loads(out.strip())
        assert record["confidence_score"] is None
        assert record["outcome_confidence"] is None
        assert record["total"] == 0

    def test_json_normalized_field(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output includes 'normalized' boolean field per record."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(bugs_dir, "P1-BUG-090-normal.md", "BUG-090: Normalized")
        _make_issue(bugs_dir, "invalid-filename.md", "Non-normalized issue")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--format", "json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
        records = [json.loads(ln) for ln in lines]
        by_id = {r["id"]: r for r in records if "id" in r}

        # BUG-090 has normalized filename
        assert "BUG-090" in by_id
        assert by_id["BUG-090"]["normalized"] is True

        # The invalid-filename.md issue won't have a standard ID, check via normalized=False
        non_norm = [r for r in records if r.get("normalized") is False]
        assert len(non_norm) == 1, "One record should have normalized=False"

    def test_json_sort_order(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output is sorted descending by total, then ascending by priority."""
        _write_config(temp_project_dir, sample_config)
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "deferred").mkdir(parents=True, exist_ok=True)

        _make_issue(
            bugs_dir,
            "P2-BUG-070-many-cmds.md",
            "BUG-070: Many commands",
            session_commands=["/ll:refine-issue", "/ll:ready-issue", "/ll:confidence-check"],
        )
        _make_issue(bugs_dir, "P1-BUG-071-no-cmds.md", "BUG-071: No commands")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "refine-status", "--format", "json", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
        records = [json.loads(ln) for ln in lines]
        assert records[0]["id"] == "BUG-070", "Highest total should be first"
        assert records[1]["id"] == "BUG-071"

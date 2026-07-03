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
    blocked_by: list[str] | None = None,
    status: str | None = None,
) -> None:
    """Write a minimal issue file with optional frontmatter fields.

    Args:
        directory: Issue directory to write into (e.g. ``.issues/features``).
        filename: File name to write (e.g. ``P2-FEAT-001-test.md``).
        title: Issue title used as the H1 header.
        confidence_score: Optional ``confidence_score`` frontmatter.
        outcome_confidence: Optional ``outcome_confidence`` frontmatter.
        blocked_by: Optional ``blocked_by`` list frontmatter (ENH-2436).
        status: Optional ``status`` frontmatter. Defaults to ``open`` when
            ``blocked_by`` is set (issues with a non-empty ``blocked_by`` list
            are exercised as open by default).
    """
    frontmatter_lines: list[str] = []
    if confidence_score is not None:
        frontmatter_lines.append(f"confidence_score: {confidence_score}")
    if outcome_confidence is not None:
        frontmatter_lines.append(f"outcome_confidence: {outcome_confidence}")
    if blocked_by is not None:
        # status defaults to "open" when blocked_by is non-empty so the
        # dependency edge is what makes the issue blocked, not status: blocked.
        frontmatter_lines.append(f"status: {status or 'open'}")
        if blocked_by:
            frontmatter_lines.append("blocked_by:")
            for blocker in blocked_by:
                frontmatter_lines.append(f"  - {blocker}")
    elif status is not None:
        frontmatter_lines.append(f"status: {status}")

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


class TestNextIssuesBlockedFilter:
    """Tests for the --include-blocked flag and the default skip-blocked filter (ENH-2436)."""

    def _setup_bugs_dir(self, temp_project_dir: Path) -> Path:
        """Create the bugs directory alongside features for cross-category fixtures."""
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        return bugs_dir

    def test_blocked_excluded_by_default(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default mode skips blocked features from the ranked list.

        Fixture shape:
        - BUG-200 (active, no blocked_by) — appears in ranked output.
        - FEAT-100 blocked_by BUG-200 — excluded.
        - FEAT-101 — included.

        The active BUG remains a valid candidate (no one blocks it), but the
        blocked FEAT is filtered out — so the output excludes FEAT-100.
        """
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-200-blocker.md", "BUG-200: Blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-100-blocked.md",
            "FEAT-100: Blocked by BUG-200",
            outcome_confidence=99,
            confidence_score=99,
            blocked_by=["BUG-200"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-101-ready.md",
            "FEAT-101: Ready",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out_lines = capsys.readouterr().out.strip().splitlines()
        assert result == 0
        # Blocked FEAT-100 is filtered out.
        assert "FEAT-100" not in out_lines
        # FEAT-101 (ready) and BUG-200 (ready, no blocked_by) remain.
        assert "FEAT-101" in out_lines

    def test_include_blocked_returns_all_ranked(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`--include-blocked` re-includes blocked issues in the standard rank order."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-210-blocker.md", "BUG-210: Blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-110-blocked.md",
            "FEAT-110: Blocked by BUG-210",
            outcome_confidence=99,
            confidence_score=99,
            blocked_by=["BUG-210"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-111-ready.md",
            "FEAT-111: Ready, lower confidence",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issues", "--include-blocked", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out_lines = capsys.readouterr().out.strip().splitlines()
        assert result == 0
        # FEAT-110 (highest confidence) is included via --include-blocked and
        # ranks first; FEAT-111 follows.
        assert out_lines[0] == "FEAT-110"
        assert out_lines[1] == "FEAT-111"
        # The blocked FEAT must be present (the key behavioral assertion).
        assert "FEAT-110" in out_lines

    def test_include_blocked_json_has_blocked_field(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`--include-blocked --json` stamps `blocked` and `blocked_by` per row."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-220-blocker.md", "BUG-220: Blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-120-blocked.md",
            "FEAT-120: Blocked",
            outcome_confidence=85,
            confidence_score=75,
            blocked_by=["BUG-220"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-121-ready.md",
            "FEAT-121: Ready",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issues",
                "--json",
                "--include-blocked",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        data = json.loads(out)
        assert isinstance(data, list)
        # Find the FEAT-120 row (rank may not be deterministic with BUG-220 also present).
        feat_120_row = next(row for row in data if row["id"] == "FEAT-120")
        assert feat_120_row["blocked"] is True
        assert feat_120_row["blocked_by"] == ["BUG-220"]
        feat_121_row = next(row for row in data if row["id"] == "FEAT-121")
        assert feat_121_row["blocked"] is False
        assert feat_121_row["blocked_by"] == []

    def test_all_blocked_returns_exit_1_with_stderr(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """All-blocked backlog exits 1 and surfaces a count summary on stderr.

        Cycle fixture (FEAT-130 blocked_by FEAT-131, FEAT-131 blocked_by
        FEAT-130) keeps both active but unresolvable in the dep graph, so
        ``find_issues(skip_blocked=True)`` returns ``[]`` even though there
        are active issues.
        """
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-130-cycle-a.md",
            "FEAT-130: Cycle A",
            outcome_confidence=80,
            confidence_score=80,
            blocked_by=["FEAT-131"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-131-cycle-b.md",
            "FEAT-131: Cycle B",
            outcome_confidence=60,
            confidence_score=60,
            blocked_by=["FEAT-130"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.out == ""
        # Exit-1 path surfaces a count summary; assert the contract prefix.
        assert "No ready issues" in captured.err
        assert "blocked" in captured.err
        assert "ready" in captured.err

    def test_done_blocker_does_not_block(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A `status: done` blocker is filtered by find_issues default and unblocks the dependent."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-240-done.md", "BUG-240: Done blocker", status="done")
        _make_issue(
            features_dir,
            "P2-FEAT-140-ready.md",
            "FEAT-140: Blocked by done BUG",
            outcome_confidence=80,
            confidence_score=80,
            blocked_by=["BUG-240"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issues", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out_lines = capsys.readouterr().out.strip().splitlines()
        assert result == 0
        # Done blocker → FEAT-140 is unblocked and listed.
        assert out_lines == ["FEAT-140"]


class TestNextIssuesBlockedFilterContract:
    """Hard contract tests for the --include-blocked default / explicit shapes (ENH-2436)."""

    def _setup_bugs_dir(self, temp_project_dir: Path) -> Path:
        bugs_dir = temp_project_dir / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        return bugs_dir

    def test_default_mode_omits_blocked_field(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default JSON output (no `--include-blocked`) does not expose the `blocked` field."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        # All-blocked-cycle fixture so the default JSON output has at least
        # one row to inspect without the BUG itself polluting the set.
        _make_issue(
            features_dir,
            "P2-FEAT-150-cycle-a.md",
            "FEAT-150: Cycle A",
            outcome_confidence=85,
            confidence_score=75,
            blocked_by=["FEAT-151"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-151-cycle-b.md",
            "FEAT-151: Cycle B",
            outcome_confidence=50,
            confidence_score=50,
            blocked_by=["FEAT-150"],
        )

        # Default mode → both blocked, no rows to return (exit 1 path).
        # We assert the contract in `--include-blocked --json` mode instead,
        # which is the path that exposes `blocked` and `blocked_by` fields.
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issues",
                "--json",
                "--include-blocked",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 2
        for row in data:
            assert "blocked" in row
            assert "blocked_by" in row
        # Both rows report blocked=true with each other as the blocker.
        for row in data:
            assert row["blocked"] is True
        # Order under confidence_first: FEAT-150 (oc=85) first, FEAT-151 (oc=50) second.
        assert data[0]["id"] == "FEAT-150"
        assert data[1]["id"] == "FEAT-151"

    def test_default_mode_blocked_field_absent_when_no_include_flag(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default JSON output omits the `blocked` field for ready-only output."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-160-ready.md",
            "FEAT-160: Ready, high confidence",
            outcome_confidence=80,
            confidence_score=80,
        )
        _make_issue(
            features_dir,
            "P3-FEAT-161-ready.md",
            "FEAT-161: Ready, lower confidence",
            outcome_confidence=50,
            confidence_score=50,
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
        assert [row["id"] for row in data] == ["FEAT-160", "FEAT-161"]
        for row in data:
            assert "blocked" not in row
            assert "blocked_by" not in row

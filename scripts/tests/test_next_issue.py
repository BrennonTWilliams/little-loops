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
    blocked_by: list[str] | None = None,
    depends_on: list[str] | None = None,
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
        depends_on: Optional ``depends_on`` list frontmatter (soft prerequisite,
            ENH-2635). Forces ``status: open`` when set (like ``blocked_by``) so
            the soft-dependency edge — not ``status: blocked`` — is what defers
            the issue.
        status: Optional ``status`` frontmatter. Defaults to ``open`` when
            ``blocked_by`` or ``depends_on`` is set (issues with a non-empty
            dependency list are exercised as open by default).
    """
    frontmatter_lines: list[str] = []
    if confidence_score is not None:
        frontmatter_lines.append(f"confidence_score: {confidence_score}")
    if outcome_confidence is not None:
        frontmatter_lines.append(f"outcome_confidence: {outcome_confidence}")
    if blocked_by is not None or depends_on is not None:
        # status defaults to "open" when a dependency edge is present so the
        # edge is what defers the issue, not status: blocked.
        frontmatter_lines.append(f"status: {status or 'open'}")
        if blocked_by:
            frontmatter_lines.append("blocked_by:")
            for blocker in blocked_by:
                frontmatter_lines.append(f"  - {blocker}")
        if depends_on:
            frontmatter_lines.append("depends_on:")
            for prereq in depends_on:
                frontmatter_lines.append(f"  - {prereq}")
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


class TestNextIssueStrategy:
    """Regression tests for config-driven selection strategy."""

    def test_priority_first_strategy_overrides_default(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Under priority_first, a lower-priority-but-higher-confidence issue loses to a
        higher-priority one. Under the default confidence_first it would win — this test
        proves the strategy knob is wired end-to-end."""
        config_with_strategy = {
            **sample_config,
            "issues": {
                **sample_config["issues"],
                "next_issue": {"strategy": "priority_first"},
            },
        }
        _write_config(temp_project_dir, config_with_strategy)
        features_dir = _setup_dirs(temp_project_dir)

        # FEAT-001 has higher priority (P1) but lower confidence scores.
        # FEAT-002 has lower priority (P3) but higher confidence scores.
        # confidence_first → FEAT-002; priority_first → FEAT-001.
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
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out
        assert result == 0
        assert "FEAT-001" in out


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


class TestNextIssueSkipFlag:
    """Tests for --skip flag excluding specific issue IDs."""

    def test_skip_excludes_top_issue(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Skipping the top-ranked issue returns the next eligible one."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-001-top.md",
            "FEAT-001: Top",
            outcome_confidence=90,
            confidence_score=90,
        )
        _make_issue(
            features_dir,
            "P2-FEAT-002-second.md",
            "FEAT-002: Second",
            outcome_confidence=70,
            confidence_score=70,
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issue", "--skip", "FEAT-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out == "FEAT-002"

    def test_skip_only_issue_returns_exit_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Skipping the only issue returns exit code 1."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(features_dir, "P2-FEAT-001-only.md", "FEAT-001: Only", outcome_confidence=80)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issue", "--skip", "FEAT-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        assert capsys.readouterr().out == ""

    def test_skip_multiple_ids(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Comma-separated skip list excludes all named IDs."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P1-FEAT-001-first.md",
            "FEAT-001: First",
            outcome_confidence=90,
            confidence_score=90,
        )
        _make_issue(
            features_dir,
            "P1-FEAT-002-second.md",
            "FEAT-002: Second",
            outcome_confidence=80,
            confidence_score=80,
        )
        _make_issue(
            features_dir,
            "P1-FEAT-003-third.md",
            "FEAT-003: Third",
            outcome_confidence=70,
            confidence_score=70,
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issue",
                "--skip",
                "FEAT-001,FEAT-002",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        assert out == "FEAT-003"


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


class TestNextIssueBlockedFilter:
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
        """Default mode skips the blocked FEAT and picks the next ready FEAT.

        Fixture shape (sorted by ``confidence_first`` by default):
        - BUG-100 (active, no ``blocked_by``) — ready; lowest rank.
        - FEAT-001 blocked_by BUG-100 — excluded by default.
        - FEAT-002 — ready; next-highest rank.

        With ``skip_blocked=True`` BUG-100 and FEAT-002 are both ready; FEAT-002
        wins on rank so ``next-issue`` returns FEAT-002.
        """
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-100-blocker.md", "BUG-100: Blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-001-blocked.md",
            "FEAT-001: Blocked by BUG-100",
            outcome_confidence=99,
            confidence_score=99,
            blocked_by=["BUG-100"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-002-ready.md",
            "FEAT-002: Ready",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        # Blocked FEAT-001 (highest confidence) is filtered; FEAT-002 wins.
        assert out == "FEAT-002"

    def test_include_blocked_returns_blocked_first(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`--include-blocked` re-includes blocked issues so the top-rank returns them."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-110-blocker.md", "BUG-110: Blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-003-blocked.md",
            "FEAT-003: Blocked but highest confidence",
            outcome_confidence=99,
            confidence_score=99,
            blocked_by=["BUG-110"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-004-ready.md",
            "FEAT-004: Ready, lower confidence",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "next-issue", "--include-blocked", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        # FEAT-003 wins on confidence when --include-blocked restores it.
        assert out == "FEAT-003"

    def test_include_blocked_json_has_blocked_field(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`--json --include-blocked` stamps `blocked` and `blocked_by` per row."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-120-blocker.md", "BUG-120: Blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-005-blocked.md",
            "FEAT-005: Blocked",
            outcome_confidence=85,
            confidence_score=75,
            blocked_by=["BUG-120"],
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issue",
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
        assert data["id"] == "FEAT-005"
        assert data["blocked"] is True
        assert data["blocked_by"] == ["BUG-120"]
        assert data["outcome_confidence"] == 85
        assert data["confidence_score"] == 75
        assert data["priority"] == "P2"

    def test_include_blocked_json_reports_pending_prerequisites(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`--include-blocked --json` surfaces soft `depends_on` deferrals (ENH-2635).

        The top pick has an open `depends_on` target but no hard `blocked_by`
        edge. It must be reported as `blocked: False` (hard-edge-only) while
        `pending_prerequisites` lists the unresolved soft prerequisite, so a
        soft-deferred pick is distinguishable from a genuinely ready one.
        """
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        # FEAT-008 (highest confidence) soft-depends on the still-open FEAT-009.
        _make_issue(
            features_dir,
            "P2-FEAT-008-soft-deferred.md",
            "FEAT-008: Soft-deferred, highest confidence",
            outcome_confidence=90,
            confidence_score=90,
            depends_on=["FEAT-009"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-009-prereq.md",
            "FEAT-009: Open prerequisite",
            outcome_confidence=50,
            confidence_score=50,
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issue",
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
        assert data["id"] == "FEAT-008"
        # Hard-blocked stays False — the deferral is soft, surfaced separately.
        assert data["blocked"] is False
        assert data["blocked_by"] == []
        assert data["pending_prerequisites"] == ["FEAT-009"]

    def test_include_blocked_json_prereq_empty_when_ready(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A genuinely ready top pick reports `pending_prerequisites: []` (ENH-2635)."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-010-ready.md",
            "FEAT-010: Ready",
            outcome_confidence=90,
            confidence_score=90,
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issue",
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
        assert data["id"] == "FEAT-010"
        assert data["blocked"] is False
        assert data["pending_prerequisites"] == []

    def test_include_blocked_json_done_prereq_not_pending(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A `status: done` `depends_on` target is not reported as pending (ENH-2635).

        Mirrors ``test_done_blocker_does_not_block``: a completed prerequisite is
        excluded from ``depends_on_edges`` at graph-build time, so the dependent
        is neither blocked nor soft-deferred.
        """
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        # FEAT-012 is done → dropped by find_issues default; FEAT-011 is ready.
        _make_issue(
            features_dir,
            "P2-FEAT-011-depends-on-done.md",
            "FEAT-011: Depends on done prereq",
            outcome_confidence=90,
            confidence_score=90,
            depends_on=["FEAT-012"],
        )
        _make_issue(features_dir, "P3-FEAT-012-done.md", "FEAT-012: Done prereq", status="done")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issue",
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
        assert data["id"] == "FEAT-011"
        assert data["blocked"] is False
        assert data["pending_prerequisites"] == []

    def test_include_blocked_json_mixed_hard_and_soft(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A pick with both a hard blocker and an open soft prereq reports both (ENH-2635)."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        _make_issue(bugs_dir, "P0-BUG-140-blocker.md", "BUG-140: Hard blocker", status="open")
        _make_issue(
            features_dir,
            "P2-FEAT-013-prereq.md",
            "FEAT-013: Open soft prereq",
            outcome_confidence=40,
            confidence_score=40,
        )
        _make_issue(
            features_dir,
            "P2-FEAT-014-mixed.md",
            "FEAT-014: Hard-blocked and soft-deferred",
            outcome_confidence=95,
            confidence_score=95,
            blocked_by=["BUG-140"],
            depends_on=["FEAT-013"],
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "next-issue",
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
        assert data["id"] == "FEAT-014"
        assert data["blocked"] is True
        assert data["blocked_by"] == ["BUG-140"]
        assert data["pending_prerequisites"] == ["FEAT-013"]

    def test_all_blocked_returns_exit_1_with_stderr(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """All-blocked backlog exits 1 and surfaces a count summary on stderr.

        Cycle fixture (FEAT-006 blocked_by FEAT-007, FEAT-007 blocked_by
        FEAT-006) keeps both active but unresolvable in the dep graph, so
        ``find_issues(skip_blocked=True)`` returns ``[]`` even though there are
        active issues.
        """
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)

        _make_issue(
            features_dir,
            "P2-FEAT-006-cycle-a.md",
            "FEAT-006: Cycle A",
            outcome_confidence=80,
            confidence_score=80,
            blocked_by=["FEAT-007"],
        )
        _make_issue(
            features_dir,
            "P3-FEAT-007-cycle-b.md",
            "FEAT-007: Cycle B",
            outcome_confidence=60,
            confidence_score=60,
            blocked_by=["FEAT-006"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.out == ""
        # The exit-1 path surfaces a count summary whose exact integer is
        # implementation-defined; assert the contract prefix instead.
        assert "No ready issues" in captured.err
        assert "blocked" in captured.err
        assert "ready" in captured.err

    def test_done_blocker_does_not_block(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A `status: done` blocker is filtered out by find_issues default and unblocks the dependent."""
        _write_config(temp_project_dir, sample_config)
        features_dir = _setup_dirs(temp_project_dir)
        bugs_dir = self._setup_bugs_dir(temp_project_dir)

        # BUG-130 is `done` → filtered by find_issues default (terminal). With
        # no active blocker, FEAT-007 is unblocked and picked.
        _make_issue(bugs_dir, "P0-BUG-130-done.md", "BUG-130: Done blocker", status="done")
        _make_issue(
            features_dir,
            "P2-FEAT-007-ready.md",
            "FEAT-007: Blocked by done BUG",
            outcome_confidence=80,
            confidence_score=80,
            blocked_by=["BUG-130"],
        )

        with patch.object(
            sys, "argv", ["ll-issues", "next-issue", "--config", str(temp_project_dir)]
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        out = capsys.readouterr().out.strip()
        assert result == 0
        # Done blocker → FEAT-007 is unblocked and selected.
        assert out == "FEAT-007"

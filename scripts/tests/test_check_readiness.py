"""Tests for `ll-issues check-readiness` and the shared `readiness_status()` helper.

BUG-3004: no existing test file covered this CLI/helper before; these establish
the exit-code baseline as well as pinning the new extraction's behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest


def _write_config(temp_project_dir: Path, config: dict[str, Any]) -> None:
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(config))


def _make_issue(
    directory: Path,
    filename: str,
    *,
    confidence_score: int | None = None,
    outcome_confidence: int | None = None,
) -> None:
    lines = ["---", "id: BUG-001", "title: Test issue"]
    if confidence_score is not None:
        lines.append(f"confidence_score: {confidence_score}")
    if outcome_confidence is not None:
        lines.append(f"outcome_confidence: {outcome_confidence}")
    lines.extend(["---", "", "# BUG-001: Test issue"])
    (directory / filename).write_text("\n".join(lines))


def _setup_dirs(temp_project_dir: Path) -> Path:
    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    return bugs_dir


def _run_check_readiness(temp_project_dir: Path, extra_args: list[str] | None = None) -> int:
    argv = [
        "ll-issues",
        "check-readiness",
        "BUG-001",
        "--config",
        str(temp_project_dir),
        *(extra_args or []),
    ]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", argv)
        from little_loops.cli import main_issues

        return main_issues()


class TestCheckReadinessExitCodes:
    """Baseline exit-code coverage — none existed before BUG-3004."""

    def test_both_thresholds_met_exits_0(self, temp_project_dir: Path) -> None:
        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=90, outcome_confidence=70)
        assert _run_check_readiness(temp_project_dir) == 0

    def test_confidence_below_threshold_exits_1(self, temp_project_dir: Path) -> None:
        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=80, outcome_confidence=70)
        assert _run_check_readiness(temp_project_dir) == 1

    def test_outcome_below_threshold_exits_1(self, temp_project_dir: Path) -> None:
        """`cmd_check_readiness` requires BOTH thresholds, unlike the ll-auto pre-gate."""
        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=90, outcome_confidence=50)
        assert _run_check_readiness(temp_project_dir) == 1

    def test_unresolvable_issue_exits_2(self, temp_project_dir: Path) -> None:
        """BUG-3294: an unresolvable issue is distinct from a genuine negative (exit 1)."""
        _setup_dirs(temp_project_dir)
        assert _run_check_readiness(temp_project_dir) == 2


class TestCheckReadinessEnabledIgnored:
    """`cmd_check_readiness` never reads `enabled` — it always compares (unchanged)."""

    def test_gate_disabled_still_compares(self, temp_project_dir: Path) -> None:
        config = {"commands": {"confidence_gate": {"enabled": False}}}
        _write_config(temp_project_dir, config)
        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=50, outcome_confidence=50)
        assert _run_check_readiness(temp_project_dir) == 1


class TestCheckReadinessCliArgFallback:
    """SCOPED OUT decision: readiness_status() keeps the absence-sensitive raw-JSON
    read verbatim, so CLI --readiness/--outcome must still win when config is absent,
    and the config value must still win when present."""

    def test_cli_args_win_when_config_absent(self, temp_project_dir: Path) -> None:
        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=60, outcome_confidence=60)
        assert _run_check_readiness(temp_project_dir, ["--readiness", "50", "--outcome", "50"]) == 0

    def test_config_value_wins_when_present(self, temp_project_dir: Path) -> None:
        config = {"commands": {"confidence_gate": {"readiness_threshold": 90}}}
        _write_config(temp_project_dir, config)
        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=85, outcome_confidence=70)
        # CLI default readiness (85) would pass; config's 90 must win and fail it.
        assert _run_check_readiness(temp_project_dir) == 1


class TestReadinessStatusRawConfidence:
    """BUG-3252 Part 1: raw_confidence/raw_outcome distinguish "absent" from
    the synthesized 0 that `confidence`/`outcome` still carry for backward
    compatibility. The gate decision (meets_readiness) is unaffected."""

    def test_absent_confidence_score_yields_none_raw(self, temp_project_dir: Path) -> None:
        from little_loops.cli.issues.check_readiness import readiness_status
        from little_loops.config import BRConfig

        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md")  # no confidence_score at all
        config = BRConfig(temp_project_dir)
        status = readiness_status(config, "BUG-001")

        assert status is not None
        assert status.raw_confidence is None
        assert status.raw_outcome is None
        # Backward-compat: confidence/outcome still synthesize 0 for existing callers.
        assert status.confidence == 0
        assert status.outcome == 0
        assert status.meets_readiness is False

    def test_scored_confidence_score_yields_int_raw(self, temp_project_dir: Path) -> None:
        from little_loops.cli.issues.check_readiness import readiness_status
        from little_loops.config import BRConfig

        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=40, outcome_confidence=30)
        config = BRConfig(temp_project_dir)
        status = readiness_status(config, "BUG-001")

        assert status is not None
        assert status.raw_confidence == 40
        assert status.raw_outcome == 30

    def test_explicit_zero_confidence_score_yields_zero_raw_not_none(
        self, temp_project_dir: Path
    ) -> None:
        """An explicit `confidence_score: 0` is a real (if bad) score, distinct
        from the key being absent — raw_confidence must be 0, not None."""
        from little_loops.cli.issues.check_readiness import readiness_status
        from little_loops.config import BRConfig

        bugs_dir = _setup_dirs(temp_project_dir)
        _make_issue(bugs_dir, "P2-BUG-001-test.md", confidence_score=0, outcome_confidence=0)
        config = BRConfig(temp_project_dir)
        status = readiness_status(config, "BUG-001")

        assert status is not None
        assert status.raw_confidence == 0
        assert status.raw_outcome == 0

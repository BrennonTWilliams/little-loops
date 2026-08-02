"""Tests for ll-issues set-flags sub-command and FLAG_RULES (ENH-2946)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _write_issue(
    issue_file: Path,
    *,
    outcome_confidence: int = 50,
    score_test_coverage: int | None = None,
    extra_frontmatter: str = "",
    body_extra: str = "",
    notes: str = "",
) -> None:
    fm = f"---\nid: BUG-001\nconfidence_score: 80\noutcome_confidence: {outcome_confidence}\n"
    if score_test_coverage is not None:
        fm += f"score_test_coverage: {score_test_coverage}\n"
    fm += extra_frontmatter
    fm += "---\n"
    body = f"# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch.\n{body_extra}\n"
    if notes:
        body += f"\n## Confidence Check Notes\n\n{notes}\n"
    issue_file.write_text(fm + body)


class TestApplyFlagsFromNotes:
    """Direct tests of apply_flags_from_notes / FLAG_RULES."""

    def test_decision_needed_phrase_sets_flag(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50)

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config, "BUG-001", "There is an open decision about approach.", dry_run=False
        )

        assert result.set_flags["decision_needed"] is True
        assert "open decision" in result.matched_phrases["decision_needed"]
        assert "decision_needed: true" in issue_file.read_text()

    def test_no_match_leaves_flags_unset(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50)

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(config, "BUG-001", "Nothing notable here.", dry_run=False)

        assert not any(result.set_flags.values())
        assert "decision_needed: true" not in issue_file.read_text()

    def test_precondition_blocks_when_outcome_confidence_high(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """No flags fire when outcome_confidence is above threshold, even with a matching phrase."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=90)

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config, "BUG-001", "There is an open decision.", dry_run=False
        )

        assert result.set_flags["decision_needed"] is False
        assert "decision_needed: true" not in issue_file.read_text()

    @pytest.mark.parametrize(
        ("flag", "phrase"),
        [
            ("decision_needed", "open decision"),
            ("missing_artifacts", "missing artifact"),
            ("implementation_order_risk", "test-first"),
        ],
    )
    def test_set_only_never_clears_existing_true_flag(
        self,
        flag: str,
        phrase: str,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """A re-run whose notes no longer match leaves an existing true flag intact."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50, extra_frontmatter=f"{flag}: true\n")

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(config, "BUG-001", "Nothing matches now.", dry_run=False)

        assert result.set_flags[flag] is True
        assert f"{flag}: true" in issue_file.read_text()

    def test_spike_needed_requires_low_test_coverage_score(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50, score_test_coverage=20)

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config, "BUG-001", "This is an unprecedented, novel mechanism.", dry_run=False
        )

        assert result.set_flags["spike_needed"] is False

        _write_issue(issue_file, outcome_confidence=50, score_test_coverage=5)
        result = apply_flags_from_notes(
            config, "BUG-001", "This is an unprecedented, novel mechanism.", dry_run=False
        )
        assert result.set_flags["spike_needed"] is True

    def test_spike_needed_never_re_flags_after_spike_attempted(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(
            issue_file,
            outcome_confidence=50,
            score_test_coverage=5,
            extra_frontmatter="spike_attempted: true\n",
        )

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config, "BUG-001", "This is an unprecedented, novel mechanism.", dry_run=False
        )

        assert result.set_flags["spike_needed"] is False

    def test_missing_artifacts_co_deliverable_suppression(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """A file listed under ### Files to Create suppresses missing_artifacts and fires
        implementation_order_risk instead."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(
            issue_file,
            outcome_confidence=50,
            body_extra=(
                "\n## Integration Map\n\n### Files to Create\n\n- scripts/little_loops/foo.py\n"
            ),
        )

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config,
            "BUG-001",
            "scripts/little_loops/foo.py does not exist yet.",
            dry_run=False,
        )

        assert result.set_flags["missing_artifacts"] is False
        assert "missing_artifacts" in result.suppressed
        assert result.set_flags["implementation_order_risk"] is True

    def test_missing_artifacts_without_co_deliverable_sets_flag(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50)

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config, "BUG-001", "scripts/little_loops/bar.py does not exist.", dry_run=False
        )

        assert result.set_flags["missing_artifacts"] is True
        assert not result.suppressed

    def test_default_notes_reads_own_confidence_check_notes_section(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50, notes="There is an open decision here.")

        config = BRConfig(temp_project_dir)
        via_default = apply_flags_from_notes(config, "BUG-001", None, dry_run=True)

        _write_issue(issue_file, outcome_confidence=50, notes="There is an open decision here.")
        via_piped = apply_flags_from_notes(
            config, "BUG-001", "There is an open decision here.", dry_run=True
        )

        assert via_default.set_flags == via_piped.set_flags

    def test_stacked_confidence_check_notes_uses_most_recent_section(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """Regression for BUG-2985: with two stacked `## Confidence Check Notes`
        sections, only the oldest containing decision-flag phrasing, `set-flags`
        (no `--from-notes`) must not fire the flag from the stale section."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50)
        issue_file.write_text(
            issue_file.read_text()
            + "\n## Confidence Check Notes\n\nThere is an open decision about approach.\n"
            + "\n## Confidence Check Notes\n\nEverything here is fully resolved.\n"
        )

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(config, "BUG-001", None, dry_run=False)

        assert result.set_flags["decision_needed"] is False
        assert "decision_needed: true" not in issue_file.read_text()

    def test_dry_run_does_not_write(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=50)

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(config, "BUG-001", "an open decision", dry_run=True)

        assert result.set_flags["decision_needed"] is True
        assert "decision_needed: true" not in issue_file.read_text()


class TestSetFlagsCLI:
    """CLI-level tests via ``ll-issues set-flags``."""

    def test_cli_writes_flag_and_json_distinguishes_suppression(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path, capsys
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(
            issue_file,
            outcome_confidence=50,
            body_extra=(
                "\n## Integration Map\n\n### Files to Create\n\n- scripts/little_loops/foo.py\n"
            ),
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-flags",
                "BUG-001",
                "--from-notes",
                "-",
                "--json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            with patch(
                "sys.stdin.read", return_value="scripts/little_loops/foo.py does not exist."
            ):
                from little_loops.cli import main_issues

                result = main_issues()

        assert result == 0
        out = json.loads(capsys.readouterr().out)
        assert out["set_flags"]["missing_artifacts"] is False
        assert "missing_artifacts" in out["suppressed"]
        assert out["set_flags"]["implementation_order_risk"] is True

    def test_cli_unknown_issue_returns_1(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-flags", "BUG-9999", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

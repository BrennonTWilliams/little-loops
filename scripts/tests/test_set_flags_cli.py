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

    def test_spike_needed_fires_on_unproven_mechanism_flag_bug_3349_shape(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """unproven_mechanism: true fires spike_needed directly (ENH-3350), bypassing both
        the score_test_coverage <= 10 numeric gate and the _SPIKE_NEEDED_PHRASES match —
        a faithful BUG-3349-shaped fixture: score_test_coverage above the numeric gate,
        and finding text that matches no existing phrase."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(
            issue_file,
            outcome_confidence=50,
            score_test_coverage=15,
            extra_frontmatter="unproven_mechanism: true\n",
        )

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config,
            "BUG-001",
            "No direct precedent confirming the combination works.",
            dry_run=False,
        )

        assert result.set_flags["spike_needed"] is True
        assert result.matched_phrases["spike_needed"] == []
        assert "spike_needed: true" in issue_file.read_text()

    def test_spike_needed_unproven_mechanism_suppressed_by_spike_completed(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """The unproven_mechanism trigger still respects _spike_not_already_flagged: a
        completed spike suppresses the flag even with unproven_mechanism: true."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(
            issue_file,
            outcome_confidence=50,
            score_test_coverage=15,
            extra_frontmatter="unproven_mechanism: true\nspike_completed: true\n",
        )

        config = BRConfig(temp_project_dir)
        result = apply_flags_from_notes(
            config,
            "BUG-001",
            "No direct precedent confirming the combination works.",
            dry_run=False,
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

    def test_struck_through_note_does_not_fire_flag(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """BUG-3537: a ~~struck~~ resolved note must not fire, even at low outcome."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=59)

        result = apply_flags_from_notes(
            BRConfig(temp_project_dir),
            "BUG-001",
            "~~Open decision: pick A or B~~ Resolved",
            dry_run=False,
        )

        assert result.set_flags["decision_needed"] is False

    def test_unpaired_strikethrough_does_not_suppress_later_line(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """BUG-3537: a stray `~~` on one line must not swallow a live Concern below."""
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=59)

        notes = "- coverage is ~~50% today\n- There is an open decision about approach.\n- ~~x"
        result = apply_flags_from_notes(BRConfig(temp_project_dir), "BUG-001", notes, dry_run=False)

        assert result.set_flags["decision_needed"] is True

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


_RULE_CASES = [
    ("decision_needed", "There is an open decision about approach.", None),
    ("missing_artifacts", "The helper module is not yet created.", None),
    ("implementation_order_risk", "We should do test-first here.", None),
    ("spike_needed", "There is no precedent for this.", 5),
]


class TestOutcomeThresholdResolution:
    """set-flags must evaluate against the loaded confidence-gate threshold (BUG-3757)."""

    @staticmethod
    def _run(
        project: Path,
        issues_dir: Path,
        *,
        outcome: int,
        flag: str = "decision_needed",
        notes: str = "There is an open decision about approach.",
        coverage: int | None = None,
    ) -> bool:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        _write_issue(issue_file, outcome_confidence=outcome, score_test_coverage=coverage)
        result = apply_flags_from_notes(BRConfig(project), "BUG-001", notes, dry_run=True)
        return result.set_flags[flag]

    @staticmethod
    def _base(sample_config: dict[str, Any], threshold: Any = None) -> dict[str, Any]:
        cfg = json.loads(json.dumps(sample_config))
        gate = cfg.setdefault("commands", {}).setdefault("confidence_gate", {})
        gate.pop("outcome_threshold", None)
        if threshold is not None:
            gate["outcome_threshold"] = threshold
        return cfg

    @pytest.fixture(autouse=True)
    def _isolate_host_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.delenv("LL_STATE_DIR", raising=False)

    @pytest.mark.parametrize(("flag", "notes", "coverage"), _RULE_CASES)
    @pytest.mark.parametrize(("outcome", "expected"), [(64, True), (65, False), (70, False)])
    def test_omitted_key_uses_canonical_default_65(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        flag: str,
        notes: str,
        coverage: int | None,
        outcome: int,
        expected: bool,
    ) -> None:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(
            json.dumps(self._base(sample_config))
        )
        assert (
            self._run(
                temp_project_dir,
                issues_dir,
                outcome=outcome,
                flag=flag,
                notes=notes,
                coverage=coverage,
            )
            is expected
        )

    @pytest.mark.parametrize(("flag", "notes", "coverage"), _RULE_CASES)
    @pytest.mark.parametrize(("outcome", "expected"), [(74, True), (75, False)])
    def test_explicit_75_keeps_74_75_boundary(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        flag: str,
        notes: str,
        coverage: int | None,
        outcome: int,
        expected: bool,
    ) -> None:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(
            json.dumps(self._base(sample_config, 75))
        )
        assert (
            self._run(
                temp_project_dir,
                issues_dir,
                outcome=outcome,
                flag=flag,
                notes=notes,
                coverage=coverage,
            )
            is expected
        )

    def test_no_config_file_uses_default(self, temp_project_dir: Path, issues_dir: Path) -> None:
        assert self._run(temp_project_dir, issues_dir, outcome=64) is True
        assert self._run(temp_project_dir, issues_dir, outcome=65) is False

    @pytest.mark.parametrize(
        ("base", "local", "outcome", "expected"),
        [
            (65, "outcome_threshold: 75", 70, True),
            (75, "outcome_threshold: 65", 70, False),
            (75, "outcome_threshold: null", 70, False),
            (75, "outcome_threshold: null", 64, True),
        ],
    )
    def test_local_override_governs(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        base: int,
        local: str,
        outcome: int,
        expected: bool,
    ) -> None:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(
            json.dumps(self._base(sample_config, base))
        )
        (temp_project_dir / ".ll" / "ll.local.md").write_text(
            f"---\ncommands:\n  confidence_gate:\n    {local}\n---\n"
        )
        assert self._run(temp_project_dir, issues_dir, outcome=outcome) is expected

    def test_root_level_config_location(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        (temp_project_dir / "ll-config.json").write_text(json.dumps(self._base(sample_config, 80)))
        assert self._run(temp_project_dir, issues_dir, outcome=78) is True
        assert self._run(temp_project_dir, issues_dir, outcome=80) is False

    def test_host_selected_config_location(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("LL_HOOK_HOST", "codex")
        (temp_project_dir / ".codex").mkdir()
        (temp_project_dir / ".codex" / "ll-config.json").write_text(
            json.dumps(self._base(sample_config, 80))
        )
        assert self._run(temp_project_dir, issues_dir, outcome=78) is True

    def test_numeric_string_threshold_is_coerced(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(
            json.dumps(self._base(sample_config, "75"))
        )
        assert self._run(temp_project_dir, issues_dir, outcome=74) is True
        assert self._run(temp_project_dir, issues_dir, outcome=75) is False

    def test_unconvertible_threshold_falls_back_to_65(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(
            json.dumps(self._base(sample_config, "high"))
        )
        assert self._run(temp_project_dir, issues_dir, outcome=64) is True
        assert self._run(temp_project_dir, issues_dir, outcome=65) is False

    def test_post_load_file_change_does_not_alter_evaluation(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        from little_loops.cli.issues.set_flags import apply_flags_from_notes
        from little_loops.config import BRConfig

        cfg_path = temp_project_dir / ".ll" / "ll-config.json"
        cfg_path.write_text(json.dumps(self._base(sample_config, 75)))
        _write_issue(issues_dir / "bugs" / "P0-BUG-001-critical-crash.md", outcome_confidence=70)
        config = BRConfig(temp_project_dir)
        cfg_path.write_text(json.dumps(self._base(sample_config, 60)))

        result = apply_flags_from_notes(config, "BUG-001", "an open decision", dry_run=True)

        assert result.set_flags["decision_needed"] is True

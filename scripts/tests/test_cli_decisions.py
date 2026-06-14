"""Tests for ll-issues decisions CLI subcommand."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.decisions import (
    CouplingEntry,
    DecisionEntry,
    ExceptionEntry,
    RuleEntry,
    list_entries,
    load_decisions,
    save_decisions,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def decisions_path(temp_project_dir: Path) -> Path:
    """Create .ll/ dir and return path to decisions.yaml (file NOT created)."""
    ll_dir = temp_project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    return ll_dir / "decisions.yaml"


@pytest.fixture
def sample_rule() -> RuleEntry:
    return RuleEntry(
        id="NAMING-001",
        type="rule",
        timestamp="2026-06-03T00:00:00Z",
        category="naming",
        labels=["style"],
        rationale="Consistent naming aids readability",
        rule="All PRs must link an issue ID",
        enforcement="required",
    )


@pytest.fixture
def sample_decision() -> DecisionEntry:
    return DecisionEntry(
        id="WORKFLOW-001",
        type="decision",
        timestamp="2026-06-03T00:00:00Z",
        category="workflow",
        labels=["storage"],
        rationale="Simpler than SQLite for this use case",
        rule="Use YAML over SQLite for decisions log",
        scope="project",
    )


@pytest.fixture
def sample_exception() -> ExceptionEntry:
    return ExceptionEntry(
        id="NAMING-EX-001",
        type="exception",
        timestamp="2026-06-03T00:00:00Z",
        category="naming",
        labels=["legacy"],
        rationale="Legacy issue predates the naming rule",
        rule_ref="NAMING-001",
        issue="BUG-042",
    )


@pytest.fixture
def sample_config(temp_project_dir: Path) -> dict[str, Any]:
    """Create a minimal ll-config.json with decisions.log_path set."""
    config: dict[str, Any] = {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest tests/",
            "lint_cmd": "ruff check .",
            "type_cmd": "mypy src/",
            "format_cmd": "ruff format .",
            "build_cmd": None,
            "run_cmd": None,
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            },
            "completed_dir": "completed",
            "deferred_dir": "deferred",
            "priorities": ["P0", "P1", "P2", "P3"],
        },
        "decisions": {
            "enabled": True,
            "log_path": ".ll/decisions.yaml",
        },
        "automation": {
            "timeout_seconds": 1800,
            "state_file": ".test-state.json",
            "worktree_base": ".worktrees",
            "max_workers": 2,
            "stream_output": False,
        },
        "orchestration": {},
    }
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(config))
    return config


# =============================================================================
# TestDecisionsCLIList
# =============================================================================


class TestDecisionsCLIList:
    """Tests for ll-issues decisions list sub-sub-command."""

    def test_list_empty(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list with no decisions.yaml prints '(no entries)' and returns 0."""
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "list", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "(no entries)" in captured.out

    def test_list_with_entries(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_rule: RuleEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list all entries shows NAMING-001."""
        save_decisions([sample_rule], decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "list", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "NAMING-001" in captured.out

    def test_list_filter_type(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_rule: RuleEntry,
        sample_decision: DecisionEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --type rule shows rule entries but not decision entries."""
        save_decisions([sample_rule, sample_decision], decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "list", "--type", "rule", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "NAMING-001" in captured.out
        assert "WORKFLOW-001" not in captured.out

    def test_list_no_outcome(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --no-outcome shows DecisionEntry records without an outcome."""
        save_decisions([sample_decision], decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "list", "--no-outcome", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "WORKFLOW-001" in captured.out

    def test_list_format_json(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_rule: RuleEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --format json outputs a valid JSON array."""
        save_decisions([sample_rule], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "list",
                "--format",
                "json",
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


# =============================================================================
# TestDecisionsCLIAdd
# =============================================================================


class TestDecisionsCLIAdd:
    """Tests for ll-issues decisions add sub-sub-command."""

    def test_add_rule(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type rule creates the decisions file and returns 0."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "rule",
                "--category",
                "naming",
                "--rule",
                "test rule text",
                "--rationale",
                "test rationale",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert decisions_path.exists()

    def test_add_decision(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type decision returns 0."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "decision",
                "--category",
                "arch",
                "--rule",
                "use postgres",
                "--rationale",
                "test rationale",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_add_exception(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type exception returns 0."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "exception",
                "--category",
                "naming",
                "--rule-ref",
                "NAMING-001",
                "--rationale",
                "test rationale",
                "--issue",
                "BUG-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_add_rule_missing_rule(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type rule without --rule returns 1."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "rule",
                "--category",
                "naming",
                "--rationale",
                "test rationale",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1


# =============================================================================
# TestDecisionsCLIOutcome
# =============================================================================


class TestDecisionsCLIOutcome:
    """Tests for ll-issues decisions outcome sub-sub-command."""

    def test_outcome_success(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """outcome WORKFLOW-001 --result worked returns 0."""
        save_decisions([sample_decision], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "outcome",
                "WORKFLOW-001",
                "--result",
                "worked",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_outcome_not_found(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """outcome for a nonexistent entry returns 1."""
        # Ensure the file exists but is empty (no entries)
        save_decisions([], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "outcome",
                "NONEXISTENT",
                "--result",
                "worked",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_outcome_force(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """outcome --force overwrites an existing outcome and returns 0."""
        from little_loops.decisions import DecisionOutcome

        decision_with_outcome = DecisionEntry(
            id="WORKFLOW-001",
            type="decision",
            timestamp="2026-06-03T00:00:00Z",
            category="workflow",
            labels=["storage"],
            rationale="Simpler than SQLite for this use case",
            rule="Use YAML over SQLite for decisions log",
            scope="project",
            outcome=DecisionOutcome(
                result="worked",
                measured_at="2026-06-03T00:00:00Z",
            ),
        )
        save_decisions([decision_with_outcome], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "outcome",
                "WORKFLOW-001",
                "--result",
                "mixed",
                "--force",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0


# =============================================================================
# TestDecisionsCLISync
# =============================================================================


class TestDecisionsCLISync:
    """Tests for ll-issues decisions sync sub-sub-command."""

    def test_sync_creates_ll_local_md(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_rule: RuleEntry,
    ) -> None:
        """sync returns 0 and writes active rules to ll.local.md."""
        save_decisions([sample_rule], decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "sync", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        ll_local = decisions_path.parent / "ll.local.md"
        assert ll_local.exists()
        content = ll_local.read_text(encoding="utf-8")
        assert "## Active Rules" in content
        assert sample_rule.rule in content


# =============================================================================
# TestDecisionsCLICoupling
# =============================================================================


class TestDecisionsCLICoupling:
    """Tests for coupling-type entries in ll-issues decisions CLI."""

    @pytest.fixture
    def sample_coupling(self) -> CouplingEntry:
        return CouplingEntry(
            id="COUPLING-001",
            type="coupling",
            timestamp="2026-06-06T00:00:00Z",
            category="wiring",
            labels=["wire-issue"],
            rationale="New CLI commands must be registered in plugin.json",
            if_changed="commands/*.md",
            then_check=[".claude-plugin/plugin.json", ".claude/CLAUDE.md"],
            tier="hard",
            archetype="add-cli-command",
        )

    def test_add_coupling(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type coupling creates a coupling entry and returns 0."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "coupling",
                "--category",
                "wiring",
                "--rationale",
                "test rationale",
                "--if-changed",
                "commands/*.md",
                "--then-check",
                ".claude-plugin/plugin.json,.claude/CLAUDE.md",
                "--tier",
                "hard",
                "--archetype",
                "add-cli-command",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert decisions_path.exists()
        entries = load_decisions(decisions_path)
        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, CouplingEntry)
        assert entry.if_changed == "commands/*.md"
        assert entry.then_check == [".claude-plugin/plugin.json", ".claude/CLAUDE.md"]
        assert entry.tier == "hard"
        assert entry.archetype == "add-cli-command"

    def test_add_coupling_missing_if_changed(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type coupling without --if-changed returns 1."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "coupling",
                "--category",
                "wiring",
                "--rationale",
                "test rationale",
                "--then-check",
                "docs/reference/API.md",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_add_coupling_missing_then_check(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """add --type coupling without --then-check returns 1."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "coupling",
                "--category",
                "wiring",
                "--rationale",
                "test rationale",
                "--if-changed",
                "commands/*.md",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_add_coupling_id_prefix(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
    ) -> None:
        """auto-generated coupling IDs use COUPLING- prefix."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "add",
                "--type",
                "coupling",
                "--category",
                "wiring",
                "--rationale",
                "test",
                "--if-changed",
                "scripts/**",
                "--then-check",
                "docs/reference/API.md",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            main_issues()

        entries = load_decisions(decisions_path)
        assert entries[0].id.startswith("COUPLING-")

    def test_list_coupling_type_filter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_coupling: CouplingEntry,
        sample_rule: RuleEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --type coupling shows coupling entries but not rule entries."""
        save_decisions([sample_coupling, sample_rule], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "list",
                "--type",
                "coupling",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "COUPLING-001" in captured.out
        assert "NAMING-001" not in captured.out

    def test_list_coupling_archetype_filter(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_coupling: CouplingEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --archetype filters coupling entries by archetype."""
        other = CouplingEntry(
            id="COUPLING-002",
            if_changed="config-schema.json",
            then_check=["docs/reference/API.md"],
            tier="hard",
            archetype="add-config-key",
        )
        save_decisions([sample_coupling, other], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "list",
                "--archetype",
                "add-cli-command",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "COUPLING-001" in captured.out
        assert "COUPLING-002" not in captured.out

    def test_list_coupling_shows_if_changed_and_tier(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_coupling: CouplingEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --type coupling displays if_changed, then_check, and tier fields."""
        save_decisions([sample_coupling], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "list",
                "--type",
                "coupling",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "commands/*.md" in captured.out
        assert "plugin.json" in captured.out
        assert "hard" in captured.out

    def test_list_coupling_json_format(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_coupling: CouplingEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --type coupling --format json returns valid JSON with coupling fields."""
        import json

        save_decisions([sample_coupling], decisions_path)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "list",
                "--type",
                "coupling",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["type"] == "coupling"
        assert data[0]["if_changed"] == "commands/*.md"
        assert data[0]["then_check"] == [".claude-plugin/plugin.json", ".claude/CLAUDE.md"]
        assert data[0]["tier"] == "hard"
        assert data[0]["archetype"] == "add-cli-command"


# =============================================================================
# TestDecisionsCLIGenerate
# =============================================================================


class TestDecisionsCLIGenerate:
    """Tests for ll-issues decisions generate sub-sub-command."""

    def test_generate_from_completed_writes_entries(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """generate runs generate_from_completed and reports entry count."""
        from datetime import datetime
        from unittest.mock import patch as mock_patch

        from little_loops.issue_history.models import CompletedIssue

        completed = [
            CompletedIssue(
                path=temp_project_dir / ".issues/features/P3-FEAT-001-test.md",
                issue_type="FEAT",
                priority="P3",
                issue_id="FEAT-001",
                completed_at=datetime(2026, 6, 3, tzinfo=UTC),
            ),
        ]
        with (
            mock_patch(
                "little_loops.issue_history.parsing.scan_completed_issues", return_value=completed
            ),
            patch.object(
                sys,
                "argv",
                ["ll-issues", "decisions", "generate", "--config", str(temp_project_dir)],
            ),
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "1" in captured.out
        entries = list_entries(decisions_path)
        assert len(entries) == 1


# =============================================================================
# TestDecisionsCLINoSubcommand
# =============================================================================


class TestDecisionsCLINoSubcommand:
    """Tests for ll-issues decisions with no sub-sub-command."""

    def test_no_subcommand(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-issues decisions with no sub-sub-command returns 1."""
        # --config is not registered on the decisions parser itself (only on sub-sub-commands),
        # so we change directory to temp_project_dir and omit --config.
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_project_dir)
            with patch.object(sys, "argv", ["ll-issues", "decisions"]):
                from little_loops.cli import main_issues

                result = main_issues()
        finally:
            os.chdir(original_cwd)

        assert result == 1


# =============================================================================
# TestDecisionsCLIPromote
# =============================================================================


class TestDecisionsCLIPromote:
    """Tests for ll-issues decisions promote subcommand."""

    def test_promote_decision_to_rule(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
    ) -> None:
        """Promote a decision entry to a rule; entry type changes to 'rule'."""
        save_decisions([sample_decision], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "WORKFLOW-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 0
        entries = load_decisions(decisions_path)
        assert len(entries) == 1
        rule = entries[0]
        assert isinstance(rule, RuleEntry)
        assert rule.id == "WORKFLOW-001"
        assert rule.type == "rule"
        assert rule.enforcement == "required"
        assert rule.rule == sample_decision.rule
        assert rule.rationale == sample_decision.rationale
        assert rule.category == sample_decision.category
        assert rule.labels == sample_decision.labels

    def test_promote_drops_decision_only_fields(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
    ) -> None:
        """Promoted rule does not carry decision-only fields (scope, alternatives_rejected, outcome)."""
        decision_with_extras = DecisionEntry(
            id="WORKFLOW-002",
            type="decision",
            timestamp="2026-06-03T00:00:00Z",
            category="workflow",
            labels=[],
            rationale="some rationale",
            rule="Use YAML",
            scope="project",
            alternatives_rejected="SQLite was considered",
        )
        save_decisions([decision_with_extras], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "WORKFLOW-002",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 0
        raw_yaml = decisions_path.read_text(encoding="utf-8")
        assert "alternatives_rejected" not in raw_yaml
        assert "scope:" not in raw_yaml
        assert "outcome:" not in raw_yaml

    def test_promote_advisory_enforcement(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
    ) -> None:
        """--enforcement advisory produces a rule with enforcement=advisory."""
        save_decisions([sample_decision], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "WORKFLOW-001",
                "--enforcement",
                "advisory",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 0
        entries = load_decisions(decisions_path)
        assert entries[0].enforcement == "advisory"  # type: ignore[union-attr]

    def test_promote_required_syncs_to_ll_local(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
    ) -> None:
        """--enforcement required (default) triggers sync: rule appears in ll.local.md."""
        save_decisions([sample_decision], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "WORKFLOW-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 0
        ll_local = decisions_path.parent / "ll.local.md"
        assert ll_local.exists()
        content = ll_local.read_text(encoding="utf-8")
        assert "## Active Rules" in content
        assert sample_decision.rule in content

    def test_promote_advisory_does_not_sync(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
    ) -> None:
        """--enforcement advisory does NOT write the rule into ## Active Rules."""
        save_decisions([sample_decision], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "WORKFLOW-001",
                "--enforcement",
                "advisory",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 0
        ll_local = decisions_path.parent / "ll.local.md"
        # advisory rules are not in Active Rules; file may not exist at all
        if ll_local.exists():
            content = ll_local.read_text(encoding="utf-8")
            assert sample_decision.rule not in content

    def test_promote_not_found_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
    ) -> None:
        """Promoting a nonexistent entry ID exits 1."""
        save_decisions([], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "NONEXISTENT-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 1

    def test_promote_already_rule_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_rule: RuleEntry,
    ) -> None:
        """Promoting an entry that is already a rule exits 1 with descriptive error."""
        save_decisions([sample_rule], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "NAMING-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()
        assert result == 1

    def test_promote_appears_in_list_type_rule(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_decision: DecisionEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """After promotion, ll-issues decisions list --type rule includes the entry."""
        save_decisions([sample_decision], decisions_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "promote",
                "WORKFLOW-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            main_issues()

        capsys.readouterr()  # discard promote output

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "decisions",
                "list",
                "--type",
                "rule",
                "--config",
                str(temp_project_dir),
            ],
        ):
            result = main_issues()
        assert result == 0
        captured = capsys.readouterr()
        assert "WORKFLOW-001" in captured.out


# =============================================================================
# TestDecisionsCLISuggestRules
# =============================================================================


class TestDecisionsCLISuggestRules:
    """Tests for ll-issues decisions suggest-rules sub-sub-command."""

    def _make_decision(
        self, id: str, category: str, rule: str, rationale: str = "some rationale"
    ) -> DecisionEntry:
        return DecisionEntry(
            id=id,
            type="decision",
            timestamp="2026-06-14T00:00:00Z",
            category=category,
            labels=[],
            rationale=rationale,
            rule=rule,
            scope="issue",
        )

    def test_suggest_rules_fewer_than_3_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules exits 1 with graceful message when fewer than 3 decisions exist."""
        decisions = [self._make_decision("ARCH-001", "architecture", "Use module X")]
        save_decisions(decisions, decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "1" in captured.out
        assert "need at least 3" in captured.out

    def test_suggest_rules_empty_file_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules exits 1 when decisions.yaml has no entries."""
        save_decisions([], decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "need at least 3" in captured.out

    def test_suggest_rules_high_signal_category_exits_0(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules exits 0 and emits SUGGEST block when category has 3+ decisions with general constraints."""
        decisions = [
            self._make_decision("ARCH-001", "architecture", "Use sub-loop composition always"),
            self._make_decision("ARCH-002", "architecture", "Register adapters via Protocol"),
            self._make_decision("ARCH-003", "architecture", "Prefer file-poller for callbacks"),
        ]
        save_decisions(decisions, decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "[SUGGEST]" in captured.out
        assert "architecture" in captured.out
        assert "consider promoting" in captured.out

    def test_suggest_rules_all_one_off_choices_exits_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules exits 1 when all decision rules are one-off choices."""
        decisions = [
            self._make_decision("ARCH-001", "architecture", "Option A: use X"),
            self._make_decision("ARCH-002", "architecture", "Option B: use Y"),
            self._make_decision("ARCH-003", "architecture", "NO-GO: not worth implementing"),
            self._make_decision("ARCH-004", "architecture", "Captured: Do something"),
        ]
        save_decisions(decisions, decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "[SUGGEST]" not in captured.out

    def test_suggest_rules_excludes_rule_and_exception_types(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        sample_rule: RuleEntry,
        sample_exception: ExceptionEntry,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules only analyzes type=decision entries; rule/exception types are excluded."""
        decisions = [
            self._make_decision("ARCH-001", "architecture", "Use sub-loop composition"),
            self._make_decision("ARCH-002", "architecture", "Register via Protocol"),
            self._make_decision("ARCH-003", "architecture", "Prefer file-poller"),
        ]
        save_decisions([sample_rule, sample_exception, *decisions], decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "NAMING-001" not in captured.out
        assert "NAMING-EX-001" not in captured.out

    def test_suggest_rules_low_signal_category_token_overlap(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules clusters low-signal category entries that share common tokens."""
        decisions = [
            self._make_decision(
                "WF-001",
                "workflow",
                "Always use resolve_host() for host CLI invocations",
                rationale="resolve_host is the standard abstraction for host_runner calls",
            ),
            self._make_decision(
                "WF-002",
                "workflow",
                "Never hardcode 'claude'; call resolve_host() instead",
                rationale="Using resolve_host prevents hardcoded binary references in host_runner",
            ),
            # Third entry to meet minimum-3 threshold
            self._make_decision("ARCH-001", "architecture", "Use sub-loop composition for FSM loops"),
        ]
        save_decisions(decisions, decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "[SUGGEST]" in captured.out
        assert "WF-001" in captured.out
        assert "WF-002" in captured.out

    def test_suggest_rules_output_format(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        decisions_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """suggest-rules output includes entry IDs, category, and suggested rule text."""
        decisions = [
            self._make_decision("ARCH-001", "architecture", "Use sub-loop composition always"),
            self._make_decision("ARCH-002", "architecture", "Register adapters via Protocol"),
            self._make_decision("ARCH-003", "architecture", "Prefer file-poller for callbacks"),
        ]
        save_decisions(decisions, decisions_path)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "suggest-rules", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "ARCH-001" in captured.out
        assert "ARCH-002" in captured.out
        assert "ARCH-003" in captured.out
        assert "category=architecture" in captured.out
        assert "consider promoting to a rule" in captured.out

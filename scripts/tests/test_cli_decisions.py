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
    DecisionEntry,
    ExceptionEntry,
    RuleEntry,
    list_entries,
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
        with mock_patch(
            "little_loops.issue_history.parsing.scan_completed_issues", return_value=completed
        ), patch.object(
            sys,
            "argv",
            ["ll-issues", "decisions", "generate", "--config", str(temp_project_dir)],
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

"""Tests for sprint CLI command handlers (direct invocation).

Tests handler functions directly via Pattern 2 (argparse.Namespace + capsys),
focusing on gaps not covered by existing tests in test_sprint.py and test_cli.py.

Existing coverage (do not duplicate):
- test_sprint.py::TestSprintEdit — _cmd_sprint_edit (add, remove, prune, revalidate)
- test_sprint.py::TestSprintAnalyze — _cmd_sprint_analyze (text/json, not-found, cycles)
- test_sprint.py::TestSprintErrorHandling — _cmd_sprint_run error paths
- test_sprint.py::TestSprintDependencyAnalysis — _cmd_sprint_run/show with dep analysis
- test_cli.py::TestMainSprintAdditionalCoverage — create/run/delete integration via main_sprint
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from little_loops.cli.sprint.create import _cmd_sprint_create
from little_loops.cli.sprint.manage import _cmd_sprint_delete, _cmd_sprint_list
from little_loops.sprint import Sprint, SprintManager

# ---------------------------------------------------------------------------
# _cmd_sprint_create Tests
# ---------------------------------------------------------------------------


class TestCmdSprintCreate:
    """Tests for _cmd_sprint_create handler — gaps in existing coverage."""

    @staticmethod
    def _setup_manager(tmp_path: Path) -> SprintManager:
        """Create a SprintManager with a temp sprints dir and minimal issues."""
        issues_dir = tmp_path / ".issues"
        (issues_dir / "bugs").mkdir(parents=True)
        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nFix this."
        )
        (issues_dir / "bugs" / "P2-BUG-002-another-bug.md").write_text(
            "# BUG-002: Another Bug\n\n## Summary\nFix this too."
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        return SprintManager(sprints_dir=sprints_dir)

    def test_issue_ids_are_uppercased(self, tmp_path: Path) -> None:
        """Issue IDs from --issues are uppercased before processing."""
        manager = self._setup_manager(tmp_path)

        args = argparse.Namespace(
            name="test-sprint",
            issues="bug-001,feat-010",
            description="Test sprint",
            max_workers=2,
            timeout=3600,
            skip=None,
            type=None,
        )

        result = _cmd_sprint_create(args, manager)
        assert result == 0

        # Verify sprint was created with uppercased IDs
        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "BUG-001" in sprint.issues

    def test_invalid_issue_ids_warned_but_not_blocked(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Invalid issue IDs produce a warning but don't prevent sprint creation."""
        manager = self._setup_manager(tmp_path)

        args = argparse.Namespace(
            name="test-sprint",
            issues="BUG-001,NONEXISTENT-999",
            description="Test sprint",
            max_workers=2,
            timeout=3600,
            skip=None,
            type=None,
        )

        result = _cmd_sprint_create(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "NONEXISTENT-999" in captured.out or "NONEXISTENT-999" in captured.err

        # Sprint was still created with valid issues
        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "NONEXISTENT-999" in sprint.issues  # invalid IDs still included

    def test_with_skip_filter(self, tmp_path: Path) -> None:
        """--skip excludes specified issue IDs from the sprint."""
        manager = self._setup_manager(tmp_path)

        args = argparse.Namespace(
            name="test-sprint",
            issues="BUG-001,BUG-002",
            description="Test sprint",
            max_workers=2,
            timeout=3600,
            skip="BUG-002",
            type=None,
        )

        result = _cmd_sprint_create(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "BUG-001" in sprint.issues
        assert "BUG-002" not in sprint.issues

    def test_with_type_filter(self, tmp_path: Path) -> None:
        """--type filter keeps only matching issue type prefixes."""
        # Need a feature issue for this test
        issues_dir = tmp_path / ".issues"
        (issues_dir / "features").mkdir(parents=True, exist_ok=True)
        (issues_dir / "features" / "P1-FEAT-010-test-feature.md").write_text(
            "# FEAT-010: Test Feature\n\n## Summary\nImplement this."
        )

        manager = self._setup_manager(tmp_path)

        args = argparse.Namespace(
            name="test-sprint",
            issues="BUG-001,FEAT-010",
            description="Test sprint",
            max_workers=2,
            timeout=3600,
            skip=None,
            type="FEAT",
        )

        result = _cmd_sprint_create(args, manager)
        assert result == 0

        sprint = manager.load("test-sprint")
        assert sprint is not None
        assert "BUG-001" not in sprint.issues
        assert "FEAT-010" in sprint.issues


# ---------------------------------------------------------------------------
# _cmd_sprint_delete Tests
# ---------------------------------------------------------------------------


class TestCmdSprintDelete:
    """Tests for _cmd_sprint_delete handler — success path (not-found tested elsewhere)."""

    def test_delete_existing_sprint_returns_0(self, tmp_path: Path) -> None:
        """Deleting an existing sprint returns 0 and removes the file."""
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        Sprint(name="my-sprint", description="", issues=["BUG-001"], created="").save(sprints_dir)

        manager = SprintManager(sprints_dir=sprints_dir)
        args = argparse.Namespace(sprint="my-sprint")

        result = _cmd_sprint_delete(args, manager)
        assert result == 0

        # Verify file was removed
        assert not (sprints_dir / "my-sprint.yaml").exists()

    def test_delete_nonexistent_sprint_returns_1(self, tmp_path: Path) -> None:
        """Deleting a non-existent sprint returns 1."""
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()  # empty dir

        manager = SprintManager(sprints_dir=sprints_dir)
        args = argparse.Namespace(sprint="nonexistent")

        result = _cmd_sprint_delete(args, manager)
        assert result == 1


# ---------------------------------------------------------------------------
# _cmd_sprint_list Tests (gap coverage)
# ---------------------------------------------------------------------------


class TestCmdSprintList:
    """Tests for _cmd_sprint_list — gaps not covered by existing tests."""

    def test_list_empty_sprints_dir(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Listing an empty sprints directory prints a message and returns 0."""
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()

        manager = SprintManager(sprints_dir=sprints_dir)
        args = argparse.Namespace(json=False, verbose=False)

        result = _cmd_sprint_list(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "No sprints defined" in captured.out

    def test_list_non_verbose_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-verbose list shows sprint names with descriptions (if any)."""
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        Sprint(name="alpha", description="First sprint", issues=["BUG-001"], created="").save(
            sprints_dir
        )
        Sprint(name="beta", description="", issues=["FEAT-010"], created="").save(sprints_dir)

        manager = SprintManager(sprints_dir=sprints_dir)
        args = argparse.Namespace(json=False, verbose=False)

        result = _cmd_sprint_list(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "alpha" in captured.out
        assert "First sprint" in captured.out
        assert "beta" in captured.out

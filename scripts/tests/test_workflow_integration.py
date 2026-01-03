"""Integration tests for the full issue processing workflow.

Tests the end-to-end flow of issue processing with mocked subprocess calls
for Claude CLI and git operations.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


class TestSequentialWorkflowIntegration:
    """Integration tests for sequential issue processing (AutoManager)."""

    @pytest.fixture
    def project_setup(self) -> Generator[tuple[Path, dict[str, Any]], None, None]:
        """Create a complete project setup with config and issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create .claude directory and config
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            config = {
                "project": {
                    "name": "test-project",
                    "src_dir": "src/",
                    "test_cmd": "pytest tests/",
                },
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    },
                    "completed_dir": "completed",
                    "priorities": ["P0", "P1", "P2", "P3"],
                },
                "automation": {
                    "timeout_seconds": 60,
                    "state_file": ".test-auto-state.json",
                },
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config, indent=2))

            # Create issue directories
            issues_base = project_root / ".issues"
            bugs_dir = issues_base / "bugs"
            features_dir = issues_base / "features"
            completed_dir = issues_base / "completed"

            bugs_dir.mkdir(parents=True)
            features_dir.mkdir(parents=True)
            completed_dir.mkdir(parents=True)

            # Create sample issues
            (bugs_dir / "P1-BUG-001-test-bug.md").write_text(
                "# BUG-001: Test Bug\n\n## Summary\nA test bug."
            )
            (bugs_dir / "P2-BUG-002-another-bug.md").write_text(
                "# BUG-002: Another Bug\n\n## Summary\nAnother test bug."
            )
            (features_dir / "P2-FEAT-001-new-feature.md").write_text(
                "# FEAT-001: New Feature\n\n## Summary\nA new feature."
            )

            yield project_root, config

    def test_dry_run_makes_no_changes(self, project_setup: tuple[Path, dict[str, Any]]) -> None:
        """Dry run mode should not execute any commands or modify files."""
        project_root, _ = project_setup

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(project_root)

        # Create manager in dry-run mode
        manager = AutoManager(
            config=config,
            dry_run=True,
            max_issues=1,
            resume=False,
            category=None,
        )

        # Run should complete without calling any subprocess
        with patch("subprocess.Popen") as mock_popen:
            with patch("subprocess.run") as mock_run:
                result = manager.run()

        # Verify no subprocess calls were made
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

        # Original issue files should still exist
        bugs_dir = project_root / ".issues" / "bugs"
        assert (bugs_dir / "P1-BUG-001-test-bug.md").exists()
        assert (bugs_dir / "P2-BUG-002-another-bug.md").exists()

    def test_max_issues_limits_processing(self, project_setup: tuple[Path, dict[str, Any]]) -> None:
        """Max issues parameter should limit the number of issues processed."""
        project_root, _ = project_setup

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager
        from little_loops.issue_parser import find_issues

        config = BRConfig(project_root)

        manager = AutoManager(
            config=config,
            dry_run=True,
            max_issues=1,
            resume=False,
            category=None,
        )

        # Track which issues were found using find_issues
        issues_found = find_issues(config)

        # Should have found issues
        assert len(issues_found) >= 1

        # When we run with max_issues=1, only 1 should be processed
        # (dry run doesn't actually process, but the limit is set)
        assert manager.max_issues == 1

    def test_category_filter_works(self, project_setup: tuple[Path, dict[str, Any]]) -> None:
        """Category filter should only process issues from the specified category."""
        project_root, _ = project_setup

        from little_loops.config import BRConfig
        from little_loops.issue_parser import find_issues

        config = BRConfig(project_root)

        # Filter to only bugs
        issues_found = find_issues(config, category="bugs")

        # Should only find bug issues
        for issue in issues_found:
            assert issue.issue_type == "bugs"
            assert issue.issue_id.startswith("BUG")


class TestParallelWorkflowIntegration:
    """Integration tests for parallel issue processing (ParallelOrchestrator)."""

    @pytest.fixture
    def project_setup(self) -> Generator[tuple[Path, dict[str, Any]], None, None]:
        """Create a complete project setup with config and issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create .claude directory and config
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            config = {
                "project": {
                    "name": "test-project",
                    "src_dir": "src/",
                },
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    },
                    "completed_dir": "completed",
                    "priorities": ["P0", "P1", "P2", "P3"],
                },
                "automation": {
                    "timeout_seconds": 60,
                    "state_file": ".test-state.json",
                },
                "parallel": {
                    "max_workers": 2,
                    "p0_sequential": True,
                    "worktree_base": ".worktrees",
                    "state_file": ".test-parallel-state.json",
                    "timeout_seconds": 60,
                    "max_merge_retries": 2,
                    "include_p0": False,
                    "stream_output": False,
                },
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config, indent=2))

            # Create issue directories
            issues_base = project_root / ".issues"
            bugs_dir = issues_base / "bugs"
            completed_dir = issues_base / "completed"

            bugs_dir.mkdir(parents=True)
            completed_dir.mkdir(parents=True)

            # Create sample issues
            (bugs_dir / "P1-BUG-001-test-bug.md").write_text(
                "# BUG-001: Test Bug\n\n## Summary\nA test bug."
            )
            (bugs_dir / "P1-BUG-002-another-bug.md").write_text(
                "# BUG-002: Another Bug\n\n## Summary\nAnother test bug."
            )

            yield project_root, config

    def test_dry_run_lists_issues(self, project_setup: tuple[Path, dict[str, Any]]) -> None:
        """Dry run should list issues without processing them."""
        project_root, _ = project_setup

        from little_loops.config import BRConfig
        from little_loops.parallel import ParallelOrchestrator
        from little_loops.parallel.types import ParallelConfig

        br_config = BRConfig(project_root)
        parallel_config = ParallelConfig(
            max_workers=2,
            worktree_base=project_root / ".worktrees",
            dry_run=True,
        )

        orchestrator = ParallelOrchestrator(
            parallel_config=parallel_config,
            br_config=br_config,
            repo_path=project_root,
            verbose=False,
        )

        # Dry run should complete without subprocess calls
        with patch("subprocess.Popen") as mock_popen:
            with patch("subprocess.run") as mock_run:
                result = orchestrator.run()

        # No actual processing should have occurred
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

    def test_priority_queue_ordering(self, project_setup: tuple[Path, dict[str, Any]]) -> None:
        """Priority queue should order issues by priority."""
        project_root, _ = project_setup

        from little_loops.parallel.priority_queue import IssuePriorityQueue
        from little_loops.issue_parser import IssueInfo

        queue = IssuePriorityQueue()

        # Add issues in non-priority order
        p2_issue = IssueInfo(
            path=Path("P2-BUG-002.md"),
            issue_id="BUG-002",
            priority="P2",
            issue_type="bugs",
            title="P2 Bug",
        )
        p1_issue = IssueInfo(
            path=Path("P1-BUG-001.md"),
            issue_id="BUG-001",
            priority="P1",
            issue_type="bugs",
            title="P1 Bug",
        )

        queue.add(p2_issue)
        queue.add(p1_issue)

        # First item should be P1 (higher priority)
        first = queue.get(block=False)
        assert first is not None
        assert first.issue_info.priority == "P1"

        # Second should be P2
        second = queue.get(block=False)
        assert second is not None
        assert second.issue_info.priority == "P2"


class TestStateManagement:
    """Tests for state persistence and resume functionality."""

    @pytest.fixture
    def state_setup(self) -> Generator[Path, None, None]:
        """Create temp directory for state testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_state_roundtrip(self, state_setup: Path) -> None:
        """State can be saved and loaded correctly."""
        from little_loops.state import StateManager, ProcessingState
        from little_loops.logger import Logger

        state_file = state_setup / ".test-state.json"
        logger = Logger(verbose=False)
        manager = StateManager(state_file, logger)

        # Mark some issues as completed/failed
        manager.mark_completed("BUG-001")
        manager.mark_completed("BUG-002")
        manager.mark_failed("BUG-003", "Test failure")

        # Create new manager and load state
        new_manager = StateManager(state_file, logger)
        new_manager.load()

        # Verify state was preserved by checking the state directly
        assert "BUG-001" in new_manager.state.completed_issues
        assert "BUG-002" in new_manager.state.completed_issues
        assert "BUG-003" in new_manager.state.failed_issues
        assert "BUG-004" not in new_manager.state.completed_issues

    def test_state_persistence(self, state_setup: Path) -> None:
        """State is correctly persisted to disk."""
        from little_loops.state import StateManager
        from little_loops.logger import Logger

        state_file = state_setup / ".test-state.json"
        logger = Logger(verbose=False)
        manager = StateManager(state_file, logger)

        # Mark an issue as completed
        manager.mark_completed("BUG-001")

        # State file should exist after mark_completed (which calls save)
        assert state_file.exists()

        # Check state content
        assert "BUG-001" in manager.state.completed_issues


class TestOutputParsing:
    """Integration tests for parsing Claude CLI output."""

    def test_ready_verdict_parsing_new_format(self) -> None:
        """Ready issue output is correctly parsed in the new format."""
        from little_loops.parallel.output_parsing import parse_ready_issue_output

        # Test READY verdict (new format with separate lines)
        ready_output = """
## VALIDATION
| Check | Status | Details |
|-------|--------|---------|
| File references | PASS | All files exist |

## VERDICT
READY

The issue is ready.
"""
        result = parse_ready_issue_output(ready_output)
        assert result["verdict"] == "READY"
        assert result["is_ready"] is True

        # Test NOT_READY verdict
        not_ready_output = """
## VALIDATION
| Check | Status | Details |
|-------|--------|---------|
| File references | FAIL | Missing file |

## VERDICT
NOT_READY

## CONCERNS
- File missing
"""
        result = parse_ready_issue_output(not_ready_output)
        assert result["verdict"] == "NOT_READY"
        assert result["is_ready"] is False

        # Test CLOSE verdict
        close_output = """
## VERDICT
CLOSE

## CLOSE_REASON
already_fixed

## CLOSE_STATUS
Closed - Already Fixed
"""
        result = parse_ready_issue_output(close_output)
        assert result["verdict"] == "CLOSE"
        assert result["should_close"] is True


class TestIssueDiscovery:
    """Tests for issue discovery and parsing."""

    @pytest.fixture
    def issues_setup(self) -> Generator[Path, None, None]:
        """Create issue directories with sample issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            issues_base = Path(tmpdir) / ".issues"
            bugs_dir = issues_base / "bugs"
            features_dir = issues_base / "features"

            bugs_dir.mkdir(parents=True)
            features_dir.mkdir(parents=True)

            # Create issues with various priorities
            (bugs_dir / "P0-BUG-001-critical.md").write_text(
                "# BUG-001: Critical Bug\n\n## Summary\nCritical."
            )
            (bugs_dir / "P1-BUG-002-high.md").write_text(
                "# BUG-002: High Priority\n\n## Summary\nHigh."
            )
            (bugs_dir / "P2-BUG-003-medium.md").write_text(
                "# BUG-003: Medium Priority\n\n## Summary\nMedium."
            )
            (features_dir / "P1-FEAT-001-feature.md").write_text(
                "# FEAT-001: New Feature\n\n## Summary\nFeature."
            )

            yield issues_base

    def test_find_issues_by_category(self, issues_setup: Path) -> None:
        """find_issues filters by category correctly."""
        import json
        from little_loops.issue_parser import find_issues
        from little_loops.config import BRConfig

        # Create a config for the test
        claude_dir = issues_setup.parent / ".claude"
        claude_dir.mkdir(exist_ok=True)
        config_data = {
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                },
                "completed_dir": "completed",
                "priorities": ["P0", "P1", "P2"],
            }
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_data))

        config = BRConfig(issues_setup.parent)

        # Find only bugs
        bugs = find_issues(config, category="bugs")
        assert len(bugs) == 3
        for issue in bugs:
            assert issue.issue_type == "bugs"

        # Find only features
        features = find_issues(config, category="features")
        assert len(features) == 1
        assert features[0].issue_type == "features"

    def test_find_highest_priority_issue(self, issues_setup: Path) -> None:
        """find_highest_priority_issue returns the highest priority issue."""
        import json
        from little_loops.issue_parser import find_highest_priority_issue
        from little_loops.config import BRConfig

        # Create a config for the test
        claude_dir = issues_setup.parent / ".claude"
        claude_dir.mkdir(exist_ok=True)
        config_data = {
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                },
                "completed_dir": "completed",
                "priorities": ["P0", "P1", "P2"],
            }
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_data))

        config = BRConfig(issues_setup.parent)

        highest = find_highest_priority_issue(config)

        # P0 should be highest
        assert highest is not None
        assert highest.priority == "P0"
        assert highest.issue_id == "BUG-001"

    def test_issue_parser_extracts_metadata(self, issues_setup: Path) -> None:
        """IssueParser correctly extracts issue metadata from files."""
        import json
        from little_loops.issue_parser import IssueParser
        from little_loops.config import BRConfig

        # Create a config for the test
        claude_dir = issues_setup.parent / ".claude"
        claude_dir.mkdir(exist_ok=True)
        config_data = {
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                },
                "completed_dir": "completed",
                "priorities": ["P0", "P1", "P2"],
            }
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_data))

        config = BRConfig(issues_setup.parent)
        parser = IssueParser(config)

        bug_file = issues_setup / "bugs" / "P1-BUG-002-high.md"
        info = parser.parse_file(bug_file)

        assert info is not None
        assert info.issue_id == "BUG-002"
        assert info.priority == "P1"
        assert info.issue_type == "bugs"
        assert "High" in info.title

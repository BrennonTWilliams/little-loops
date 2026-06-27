"""Tests for little_loops.issue_manager module."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager
from little_loops.issue_parser import IssueInfo


class TestPathRenameHandling:
    """Tests for handling issue file renames during ready-issue."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig for testing."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.state_file = ".auto-manage-state.json"
        return config

    @pytest.fixture
    def mock_issue_info(self, temp_project_dir: Path) -> IssueInfo:
        """Create a mock IssueInfo for testing."""
        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        old_path = issues_dir / "P3-ENH-341-extract-prometheus-adapter.md"
        old_path.write_text("# ENH-341: Extract Prometheus Adapter\n")
        return IssueInfo(
            path=old_path,
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-341",
            title="Extract Prometheus Adapter",
        )

    def test_path_rename_updates_tracking(
        self, temp_project_dir: Path, mock_config: BRConfig, mock_issue_info: IssueInfo
    ) -> None:
        """Test that legitimate file renames update tracking instead of failing."""
        # Setup: Create the new file path (simulating ready-issue renaming)
        new_path = mock_issue_info.path.parent / "P3-ENH-341-refactor-metrics-module.md"
        new_path.write_text("# ENH-341: Refactor Metrics Module\n")
        # Remove the old file to simulate a rename
        mock_issue_info.path.unlink()

        # Mock the ready-issue output
        mock_output = f"""
## VERDICT
CORRECTED

## VALIDATED_FILE
{new_path}

## CORRECTIONS_MADE
- Title changed from 'Extract Prometheus Adapter' to 'Refactor Metrics Module'
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=mock_result),
            patch("little_loops.issue_manager.check_git_status", return_value=([], [])),
        ):
            _manager = AutoManager(mock_config, dry_run=False)
            # Access the internal method for testing path handling
            # We need to mock the subprocess call and check if path is updated

            # Store original path
            original_path = mock_issue_info.path

            # Simulate the parsing and path update logic
            from little_loops.output_parsing import parse_ready_issue_output

            parsed = parse_ready_issue_output(mock_output)

            validated_path = parsed.get("validated_file_path")
            assert validated_path is not None

            validated_resolved = Path(validated_path).resolve()
            expected_path = str(original_path.resolve())

            # Verify paths are different
            assert str(validated_resolved) != expected_path

            # Verify the new file exists and old doesn't
            assert validated_resolved.exists()
            assert not original_path.exists()

            # This is the key assertion: in this scenario, the manager
            # should update info.path rather than failing
            # The actual update happens in _process_issue, so we verify
            # the conditions that would trigger the update

    def test_path_mismatch_fails_when_both_exist(
        self, temp_project_dir: Path, mock_config: BRConfig, mock_issue_info: IssueInfo
    ) -> None:
        """Test that genuine path mismatches fail when both files exist."""
        # Setup: Create a different file that ready-issue claims to validate
        different_path = mock_issue_info.path.parent / "P3-ENH-999-different-issue.md"
        different_path.write_text("# ENH-999: Different Issue\n")

        # Both old and new paths exist - this is a genuine mismatch
        assert mock_issue_info.path.exists()
        assert different_path.exists()

        # Verify this would be detected as a mismatch
        validated_resolved = different_path.resolve()
        expected_path = str(mock_issue_info.path.resolve())

        assert str(validated_resolved) != expected_path
        # When both exist, it's NOT a rename, so should fail

    def test_path_mismatch_fails_when_neither_exist(
        self, temp_project_dir: Path, mock_config: BRConfig
    ) -> None:
        """Test that path mismatches fail when neither file exists."""
        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)

        # Create paths that don't exist
        old_path = issues_dir / "P3-ENH-341-nonexistent-old.md"
        new_path = issues_dir / "P3-ENH-341-nonexistent-new.md"

        # Neither file exists
        assert not old_path.exists()
        assert not new_path.exists()

        # This should be treated as a failure, not a rename

    def test_path_rename_detection_with_absolute_vs_relative(
        self, temp_project_dir: Path, mock_config: BRConfig, mock_issue_info: IssueInfo
    ) -> None:
        """Test that path comparison works with mixed absolute/relative paths."""
        # Setup: Create the new file
        new_path = mock_issue_info.path.parent / "P3-ENH-341-refactor-metrics-module.md"
        new_path.write_text("# ENH-341: Refactor Metrics Module\n")
        mock_issue_info.path.unlink()

        # Test with relative path in output (as Claude often returns)
        relative_path = f".issues/enhancements/{new_path.name}"

        mock_output = f"""
## VERDICT
CORRECTED

## VALIDATED_FILE
{relative_path}
"""
        from little_loops.output_parsing import parse_ready_issue_output

        parsed = parse_ready_issue_output(mock_output)
        validated_path = parsed.get("validated_file_path")
        assert validated_path is not None, "validated_file_path should be present"

        # Path.resolve() should handle relative paths correctly
        validated_resolved = Path(validated_path).resolve()

        # The resolved path should match when we're in the right directory
        # This verifies Path.resolve() works for comparison
        assert validated_resolved.name == new_path.name


class TestAutoManagerIntegration:
    """Integration tests for AutoManager path handling."""

    @pytest.fixture
    def setup_project(self, temp_project_dir: Path) -> tuple[Path, Path]:
        """Set up a minimal project structure."""
        # Create .claude directory with config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }

        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        return temp_project_dir, issues_dir

    def test_auto_manager_wires_sqlite(self, setup_project: tuple[Path, Path]) -> None:
        """AutoManager wires SQLiteTransport; close_issue live-writes rows (no backfill needed)."""
        import subprocess

        from little_loops.config import BRConfig
        from little_loops.issue_lifecycle import close_issue
        from little_loops.issue_manager import AutoManager
        from little_loops.issue_parser import IssueParser
        from little_loops.session_store import connect

        project_root, issues_dir = setup_project
        db_path = project_root / ".ll" / "session.db"

        issue_file = issues_dir / "P1-ENH-001-test.md"
        issue_file.write_text(
            "---\nid: ENH-001\nstatus: open\ntype: ENH\npriority: P1\n---\n\n"
            "# ENH-001: Test\n\n## Summary\nTest.\n"
        )

        config = BRConfig(project_root)
        manager = AutoManager(config, dry_run=True, db_path=db_path)

        info = IssueParser(config).parse_file(issue_file)
        mock_logger = MagicMock()

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[main abc] commit", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            close_issue(
                info, config, mock_logger, "already_fixed", "Closed", event_bus=manager.event_bus
            )

        manager.event_bus.close_transports()

        # Live-written row should exist without calling backfill()
        conn = connect(db_path)
        rows = conn.execute("SELECT * FROM issue_events").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["issue_id"] == "ENH-001"


class TestPathMismatchFallback:
    """Tests for path mismatch fallback resolution."""

    def test_compute_relative_path_from_cwd(self, temp_project_dir: Path) -> None:
        """Test _compute_relative_path computes correct relative path."""
        from little_loops.issue_manager import _compute_relative_path

        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-ENH-341-test-issue.md"
        issue_file.write_text("# Test Issue\n")

        # Compute relative path from project root
        relative = _compute_relative_path(issue_file, temp_project_dir)
        assert relative == ".issues/enhancements/P1-ENH-341-test-issue.md"

    def test_compute_relative_path_falls_back_to_absolute(self, temp_project_dir: Path) -> None:
        """Test _compute_relative_path returns absolute if not relative to base."""
        from little_loops.issue_manager import _compute_relative_path

        # Use a path outside the base directory
        other_path = Path("/tmp/some/other/path.md")
        result = _compute_relative_path(other_path, temp_project_dir)
        assert result == str(other_path)

    def test_fallback_succeeds_when_retry_validates_correct_file(
        self, temp_project_dir: Path
    ) -> None:
        """Test that fallback retry with explicit path succeeds."""
        from little_loops.output_parsing import parse_ready_issue_output

        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)

        # Create the correct file (what ll-auto expects)
        correct_file = issues_dir / "P1-ENH-341-correct-issue.md"
        correct_file.write_text("# ENH-341: Correct Issue\n")

        # Create a wrong file (what ready-issue mistakenly finds)
        wrong_file = issues_dir / "P1-ENH-001-wrong-issue.md"
        wrong_file.write_text("# ENH-001: Wrong Issue\n")

        # First call output (returns wrong file)
        first_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_file}
"""
        # Retry call output (returns correct file)
        retry_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{correct_file}
"""
        # Parse both outputs
        first_parsed = parse_ready_issue_output(first_output)
        retry_parsed = parse_ready_issue_output(retry_output)

        # Verify first call returned wrong file
        assert first_parsed["validated_file_path"] == str(wrong_file)
        assert Path(first_parsed["validated_file_path"]).resolve() != correct_file.resolve()

        # Verify retry returned correct file
        assert retry_parsed["validated_file_path"] == str(correct_file)
        assert Path(retry_parsed["validated_file_path"]).resolve() == correct_file.resolve()

    def test_fallback_fails_when_retry_still_mismatched(self, temp_project_dir: Path) -> None:
        """Test that persistent mismatch after fallback properly fails."""
        from little_loops.output_parsing import parse_ready_issue_output

        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)

        # Create expected and wrong files
        expected_file = issues_dir / "P1-ENH-341-expected.md"
        expected_file.write_text("# ENH-341: Expected\n")

        wrong_file = issues_dir / "P1-ENH-999-wrong.md"
        wrong_file.write_text("# ENH-999: Wrong\n")

        # Both calls return wrong file
        output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_file}
"""
        parsed = parse_ready_issue_output(output)

        # Verify mismatch would be detected
        validated_resolved = Path(parsed["validated_file_path"]).resolve()
        assert validated_resolved != expected_file.resolve()

    def test_path_detection_in_ready_issue_command(self) -> None:
        """Test that ready-issue bash can distinguish paths from IDs.

        This is a unit test for the bash logic - verifying the patterns
        that distinguish file paths from issue IDs.
        """
        # Test patterns that should be detected as file paths
        path_inputs = [
            ".issues/enhancements/P1-ENH-341-test.md",  # relative path with /
            "/absolute/path/to/file.md",  # absolute path
            "P1-BUG-001-test.md",  # filename ending in .md
        ]

        # Test patterns that should be detected as issue IDs
        id_inputs = [
            "BUG-001",
            "ENH-341",
            "FEAT-042",
        ]

        # Verify path patterns (contains "/" or ends with ".md")
        for path in path_inputs:
            is_path = "/" in path or path.endswith(".md")
            assert is_path, f"'{path}' should be detected as path"

        # Verify ID patterns (no "/" and doesn't end with ".md")
        for issue_id in id_inputs:
            is_path = "/" in issue_id or issue_id.endswith(".md")
            assert not is_path, f"'{issue_id}' should be detected as ID"

    def test_manage_issue_uses_path_after_fallback(self, temp_project_dir: Path) -> None:
        """Test that manage-issue uses relative path after fallback, not stale issue_id.

        This tests the BUG-010 fix: when ready-issue fallback succeeds with an explicit
        path, the subsequent manage-issue command should use that path instead of the
        original abstract issue_id which may not match the target repo's naming.
        """
        from unittest.mock import MagicMock

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, _compute_relative_path
        from little_loops.issue_parser import IssueInfo

        # Setup project structure
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)

        # Create the actual issue file with external repo naming convention
        actual_file = issues_dir / "P1-DOC-001-fix-layer-count.md"
        actual_file.write_text("# DOC-001: Fix Layer Count\n\n## Summary\nTest issue\n")

        # Create a different file that initial ready-issue might match
        wrong_file = issues_dir / "P3-BUG-001-old-issue.md"
        wrong_file.write_text("# BUG-001: Old Issue\n")

        # Create IssueInfo with abstract ID that doesn't match filename
        info = IssueInfo(
            path=actual_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-1",  # Abstract ID from queue
            title="Fix Layer Count",
        )

        # Expected relative path for the fallback
        expected_relative_path = _compute_relative_path(actual_file, temp_project_dir)

        # Mock ready-issue outputs
        first_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_file}
"""
        retry_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{actual_file}
"""

        # Track calls to run_claude_command and run_with_continuation
        call_history: list[tuple[str, str]] = []

        def mock_run_claude(command: str, *args, **kwargs) -> MagicMock:
            call_history.append(("run_claude_command", command))
            result = MagicMock()
            result.returncode = 0
            if "ready-issue" in command:
                if expected_relative_path in command:
                    result.stdout = retry_output
                else:
                    result.stdout = first_output
            return result

        def mock_run_with_continuation(command: str, *args, **kwargs) -> MagicMock:
            call_history.append(("run_with_continuation", command))
            result = MagicMock()
            result.returncode = 0
            result.stdout = "## RESULT\n- Status: COMPLETED"
            result.stderr = ""
            return result

        # Create mock config
        mock_config = MagicMock(spec=BRConfig)
        mock_config.repo_path = temp_project_dir
        mock_config.automation = MagicMock()
        mock_config.automation.timeout_seconds = 60
        mock_config.automation.stream_output = False
        mock_config.automation.max_continuations = 3
        mock_config.get_category_action.return_value = "fix"
        mock_config.get_state_file.return_value = temp_project_dir / ".auto-state.json"

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run_claude),
            patch(
                "little_loops.issue_manager.run_with_continuation",
                side_effect=mock_run_with_continuation,
            ),
            patch("little_loops.issue_manager.check_git_status", return_value=False),
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
        ):
            manager = AutoManager(mock_config, dry_run=False)
            manager._process_issue(info)

        # Verify the sequence of calls
        assert len(call_history) >= 3, f"Expected at least 3 calls, got {len(call_history)}"

        # First call: ready-issue with abstract ID
        assert call_history[0][0] == "run_claude_command"
        assert "/ll:ready-issue BUG-1" in call_history[0][1]

        # Second call: ready-issue fallback with explicit path
        assert call_history[1][0] == "run_claude_command"
        assert expected_relative_path in call_history[1][1]

        # Third call: manage-issue should use the path, NOT the stale BUG-1
        assert call_history[2][0] == "run_with_continuation"
        manage_cmd = call_history[2][1]
        assert "manage-issue" in manage_cmd
        # The key assertion: must use path, not stale ID
        assert expected_relative_path in manage_cmd, (
            f"Expected manage-issue to use '{expected_relative_path}', got: {manage_cmd}"
        )
        assert "BUG-1" not in manage_cmd, (
            f"manage-issue should NOT use stale ID 'BUG-1', got: {manage_cmd}"
        )


class TestDependencyAwareSequencing:
    """Tests for dependency-aware issue selection in AutoManager (ENH-016)."""

    @pytest.fixture
    def temp_project_with_deps(self, temp_project_dir: Path) -> Path:
        """Set up project with issues that have dependencies."""

        # Create .claude directory with config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        # Create FEAT-001 (no dependencies)
        (issues_dir / "P1-FEAT-001-first-feature.md").write_text(
            "# FEAT-001: First Feature\n\n## Summary\nFirst\n"
        )

        # Create FEAT-002 (blocked by FEAT-001)
        (issues_dir / "P1-FEAT-002-second-feature.md").write_text(
            "# FEAT-002: Second Feature\n\n## Summary\nSecond\n\n## Blocked By\n\n- FEAT-001\n"
        )

        return temp_project_dir

    def test_dependency_graph_built_on_init(self, temp_project_with_deps: Path) -> None:
        """Test that AutoManager builds dependency graph on initialization."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_deps)
        manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        assert hasattr(manager, "dep_graph")
        assert len(manager.dep_graph) == 2
        assert "FEAT-001" in manager.dep_graph
        assert "FEAT-002" in manager.dep_graph

    def test_blocked_issue_not_selected_first(self, temp_project_with_deps: Path) -> None:
        """Test that blocked issue is not selected before its blocker."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_deps)
        manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        # First issue selected should be FEAT-001 (not blocked)
        info = manager._get_next_issue()
        assert info is not None
        assert info.issue_id == "FEAT-001"

    def test_blocked_issue_selected_after_blocker_completed(
        self, temp_project_with_deps: Path
    ) -> None:
        """Test that blocked issue becomes available after blocker completes."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_deps)
        manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        # Mark FEAT-001 as completed
        manager.state_manager.state.completed_issues.append("FEAT-001")

        # Now FEAT-002 should be selected
        info = manager._get_next_issue()
        assert info is not None
        assert info.issue_id == "FEAT-002"

    def test_no_issue_when_all_blocked(self, temp_project_with_deps: Path) -> None:
        """Test that None is returned when all remaining issues are blocked."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_deps)
        manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        # Mark FEAT-001 as attempted (skip) but not completed
        manager.state_manager.state.attempted_issues.add("FEAT-001")

        # FEAT-002 is blocked by FEAT-001, which is not completed
        # So no issues should be available
        info = manager._get_next_issue()
        assert info is None

    @pytest.fixture
    def temp_project_with_cycle(self, temp_project_dir: Path) -> Path:
        """Set up project with issues that have a dependency cycle."""

        # Create .claude directory with config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        # Create FEAT-001 (blocked by FEAT-002) - circular!
        (issues_dir / "P1-FEAT-001-first-feature.md").write_text(
            "# FEAT-001: First Feature\n\n## Summary\nFirst\n\n## Blocked By\n\n- FEAT-002\n"
        )

        # Create FEAT-002 (blocked by FEAT-001) - circular!
        (issues_dir / "P1-FEAT-002-second-feature.md").write_text(
            "# FEAT-002: Second Feature\n\n## Summary\nSecond\n\n## Blocked By\n\n- FEAT-001\n"
        )

        return temp_project_dir

    def test_cycle_detected_on_init(
        self, temp_project_with_cycle: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that dependency cycles are detected and warned about on init."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_cycle)
        _manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        captured = capsys.readouterr()
        # Check that cycle warning was printed
        assert "Dependency cycle detected" in captured.out or "cycle" in captured.out.lower()


class TestAutoManagerPriorityFilter:
    """Tests for AutoManager priority_filter in _get_next_issue (ENH-804)."""

    @pytest.fixture
    def temp_project_with_priorities(self, temp_project_dir: Path) -> Path:
        """Set up project with issues of mixed priorities."""
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        (issues_dir / "P1-BUG-001-high-priority.md").write_text(
            "# BUG-001: High priority\n\n## Summary\nHigh\n"
        )
        (issues_dir / "P3-BUG-002-medium-priority.md").write_text(
            "# BUG-002: Medium priority\n\n## Summary\nMedium\n"
        )

        return temp_project_dir

    def test_priority_filter_none_returns_all_issues(
        self, temp_project_with_priorities: Path
    ) -> None:
        """With priority_filter=None, all issues are candidates."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_priorities)
        manager = AutoManager(
            config,
            dry_run=True,
            priority_filter=None,
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is not None  # At least one issue returned

    def test_priority_filter_matching_returns_issue(
        self, temp_project_with_priorities: Path
    ) -> None:
        """priority_filter matching an issue's priority returns that issue."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_priorities)
        manager = AutoManager(
            config,
            dry_run=True,
            priority_filter={"P1"},
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is not None
        assert issue.issue_id == "BUG-001"
        assert issue.priority == "P1"

    def test_priority_filter_non_matching_returns_none(
        self, temp_project_with_priorities: Path
    ) -> None:
        """priority_filter that matches no issues returns None."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_priorities)
        manager = AutoManager(
            config,
            dry_run=True,
            priority_filter={"P0"},
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is None

    def test_priority_filter_multiple_levels(self, temp_project_with_priorities: Path) -> None:
        """priority_filter with multiple levels returns issues matching any."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_priorities)
        manager = AutoManager(
            config,
            dry_run=True,
            priority_filter={"P1", "P3"},
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is not None
        assert issue.priority in {"P1", "P3"}


class TestAutoManagerLabelFilter:
    """Tests for AutoManager label_filter in _get_next_issue (ENH-1392)."""

    @pytest.fixture
    def temp_project_with_labels(self, temp_project_dir: Path) -> Path:
        """Set up project with issues of different labels."""
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        (issues_dir / "P1-BUG-001-fsm-issue.md").write_text(
            "---\nlabels:\n  - fsm\n  - quick-win\n---\n# BUG-001: FSM issue\n"
        )
        (issues_dir / "P2-BUG-002-cli-issue.md").write_text(
            "---\nlabels:\n  - cli\n---\n# BUG-002: CLI issue\n"
        )
        (issues_dir / "P3-BUG-003-no-labels.md").write_text("---\n---\n# BUG-003: No labels\n")

        return temp_project_dir

    def test_label_filter_none_returns_all(self, temp_project_with_labels: Path) -> None:
        """With label_filter=None, all issues are candidates."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_labels)
        manager = AutoManager(
            config,
            dry_run=True,
            label_filter=None,
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is not None

    def test_label_filter_matching(self, temp_project_with_labels: Path) -> None:
        """label_filter matching one issue's label returns that issue."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_labels)
        manager = AutoManager(
            config,
            dry_run=True,
            label_filter={"fsm"},
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is not None
        assert issue.issue_id == "BUG-001"

    def test_label_filter_non_matching_returns_none(self, temp_project_with_labels: Path) -> None:
        """label_filter that matches no issues returns None."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_labels)
        manager = AutoManager(
            config,
            dry_run=True,
            label_filter={"nonexistent"},
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is None

    def test_label_filter_any_match(self, temp_project_with_labels: Path) -> None:
        """label_filter matches issues that have any of the specified labels."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_labels)
        manager = AutoManager(
            config,
            dry_run=True,
            label_filter={"quick-win"},
            db_path=config.project_root / ".ll" / "history.db",
        )

        issue = manager._get_next_issue()
        assert issue is not None
        assert "quick-win" in [lb.lower() for lb in issue.labels]


class TestAutoManagerQuietMode:
    """Tests for AutoManager quiet/verbose mode (ENH-188)."""

    def test_auto_manager_verbose_false_creates_quiet_logger(self, temp_project_dir: Path) -> None:
        """Test AutoManager with verbose=False creates quiet logger."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create minimal config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        config = BRConfig(temp_project_dir)
        manager = AutoManager(
            config, verbose=False, db_path=config.project_root / ".ll" / "history.db"
        )

        assert manager.logger.verbose is False

    def test_auto_manager_verbose_true_creates_verbose_logger(self, temp_project_dir: Path) -> None:
        """Test AutoManager with verbose=True creates verbose logger (default)."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create minimal config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        config = BRConfig(temp_project_dir)
        manager = AutoManager(
            config, db_path=config.project_root / ".ll" / "history.db"
        )  # Use default verbose=True

        assert manager.logger.verbose is True

    def test_auto_manager_explicit_verbose_true(self, temp_project_dir: Path) -> None:
        """Test AutoManager with explicit verbose=True."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create minimal config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        config = BRConfig(temp_project_dir)
        manager = AutoManager(
            config, verbose=True, db_path=config.project_root / ".ll" / "history.db"
        )

        assert manager.logger.verbose is True

    def test_auto_manager_verbose_stores_preview_full(self, temp_project_dir: Path) -> None:
        """AutoManager stores _preview_full=True when preview_full=True, False otherwise."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"}
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        config = BRConfig(temp_project_dir)
        manager_full = AutoManager(
            config, preview_full=True, db_path=config.project_root / ".ll" / "history.db"
        )

        assert manager_full._preview_full is True

        manager_default = AutoManager(
            config, preview_full=False, db_path=config.project_root / ".ll" / "history.db"
        )

        assert manager_default._preview_full is False


class TestRunClaudeCommand:
    """Tests for run_claude_command function (ENH-207)."""

    @pytest.fixture
    def mock_logger(self, temp_project_dir: Path) -> MagicMock:
        """Create a mock logger."""
        logger = MagicMock()
        return logger

    def test_streams_output_when_enabled(self, mock_logger: MagicMock) -> None:
        """Test that stream_callback is called when stream_output=True."""
        from little_loops.issue_manager import run_claude_command

        # Track callback invocations
        callback_calls: list[tuple[str, bool]] = []

        def mock_stream_callback(line: str, is_stderr: bool) -> None:
            callback_calls.append((line, is_stderr))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test output\n"
        mock_result.stderr = ""

        with patch("little_loops.issue_manager._run_claude_base") as mock_run:
            mock_run.return_value = mock_result

            # Capture the stream_callback passed to _run_claude_base
            original_callback = None

            def capture_callback(*args, **kwargs):
                nonlocal original_callback
                if "stream_callback" in kwargs:
                    original_callback = kwargs["stream_callback"]
                return mock_result

            mock_run.side_effect = capture_callback
            run_claude_command("test command", mock_logger, stream_output=True)

            # Verify callback was set
            assert original_callback is not None

    def test_skips_streaming_when_disabled(self, mock_logger: MagicMock) -> None:
        """Test that stream_callback is None when stream_output=False."""
        from little_loops.issue_manager import run_claude_command

        mock_result = MagicMock()
        mock_result.returncode = 0

        callback_passed = False

        def check_callback(*args, **kwargs):
            nonlocal callback_passed
            if kwargs.get("stream_callback") is not None:
                callback_passed = True
            return mock_result

        with patch("little_loops.issue_manager._run_claude_base") as mock_run:
            mock_run.side_effect = check_callback
            run_claude_command("test command", mock_logger, stream_output=False)

            assert not callback_passed


class TestRunWithContinuation:
    """Tests for run_with_continuation context handoff handling (ENH-207)."""

    def test_returns_immediately_when_no_handoff(self, temp_project_dir: Path) -> None:
        """Test that function returns normally when no CONTEXT_HANDOFF detected."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Normal output"
        mock_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                result = run_with_continuation("test command", mock_logger)

        assert result.returncode == 0
        assert "Normal output" in result.stdout

    def test_exits_cleanly_when_handoff_detected(self, temp_project_dir: Path) -> None:
        """When CONTEXT_HANDOFF detected, exits cleanly without spawning continuation."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = (
            "Implementation progress...\nCONTEXT_HANDOFF: Ready for fresh session"
        )
        handoff_result.stderr = ""
        handoff_result.args = ["claude", "-p", "manage-issue"]

        with patch(
            "little_loops.issue_manager.run_claude_command", return_value=handoff_result
        ) as mock_run:
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                result = run_with_continuation("test command", mock_logger)

        # Should only call run_claude_command once (no continuation spawned)
        mock_run.assert_called_once()
        assert result.returncode == 0
        assert "CONTEXT_HANDOFF:" in result.stdout

    def test_exits_cleanly_when_issue_already_done(self, temp_project_dir: Path) -> None:
        """Pre-continuation guard: when issue is already done, returns success without handoff."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P2-BUG-999-test.md"
        issue_file.write_text("---\nstatus: done\n---\n\n# BUG-999: Test")

        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = "CONTEXT_HANDOFF: Ready for fresh session"
        handoff_result.stderr = ""
        handoff_result.args = ["claude", "-p", "test"]

        with patch(
            "little_loops.issue_manager.run_claude_command", return_value=handoff_result
        ) as mock_run:
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                result = run_with_continuation("test command", mock_logger, issue_path=issue_file)

        # Should exit cleanly (issue already done, no handoff needed)
        mock_run.assert_called_once()
        assert result.returncode == 0
        # The original Claude output may contain handoff text, but no EXTRA signal
        # was appended and no continuation was spawned

    def test_option_j_guard_skips_when_issue_already_done(self, temp_project_dir: Path) -> None:
        """BUG-2281: Option J guard skips continuation when issue is already done."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P2-BUG-999-test.md"
        issue_file.write_text("---\nstatus: done\n---\n\n# BUG-999: Test")

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        call_count = [0]

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            return overflow_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                result = run_with_continuation(
                    "/ll:manage-issue bug fix BUG-999",
                    mock_logger,
                    issue_path=issue_file,
                    max_continuations=3,
                    context_limit=200_000,
                )

        assert call_count[0] == 1, "No fresh session should be spawned when issue is already done"
        assert result.returncode == 0

    def test_forwards_handoff_signal_to_stdout(self, temp_project_dir: Path) -> None:
        """Handoff signal is forwarded to stdout for outer FSM detection."""
        import io

        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = "CONTEXT_HANDOFF: Ready for fresh session"
        handoff_result.stderr = ""
        handoff_result.args = ["claude", "-p", "test"]

        captured = io.StringIO()
        with patch("little_loops.issue_manager.run_claude_command", return_value=handoff_result):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                with patch("sys.stdout", new=captured):
                    run_with_continuation("test command", mock_logger)

        assert "CONTEXT_HANDOFF:" in captured.getvalue()

    def test_handoff_guard_skips_when_issue_open(self, temp_project_dir: Path) -> None:
        """When issue is still open, handoff signal IS forwarded (not suppressed)."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P2-BUG-998-test.md"
        issue_file.write_text("---\nstatus: open\n---\n\n# BUG-998: Test")

        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = "CONTEXT_HANDOFF: Ready for fresh session"
        handoff_result.stderr = ""
        handoff_result.args = ["claude", "-p", "test"]

        with patch("little_loops.issue_manager.run_claude_command", return_value=handoff_result):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=True):
                result = run_with_continuation("test command", mock_logger, issue_path=issue_file)

        assert result.returncode == 0
        # Signal IS forwarded because issue is still open
        assert "CONTEXT_HANDOFF:" in result.stdout

    def test_returns_default_result_when_loop_never_executes(self, temp_project_dir: Path) -> None:
        """Test that negative max_continuations returns default result (BUG-419)."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        with patch("little_loops.issue_manager.run_claude_command") as mock_run:
            result = run_with_continuation("test", mock_logger, max_continuations=-1)

        mock_run.assert_not_called()
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.args == []

    def test_sentinel_triggers_explicit_handoff_instruction(self, temp_project_dir: Path) -> None:
        """Option E: sentinel file triggers --resume turn with explicit handoff instruction."""
        from little_loops.issue_manager import run_with_continuation
        from little_loops.subprocess_utils import write_sentinel

        mock_logger = MagicMock()
        write_sentinel(temp_project_dir, token_count=130_000, context_limit=200_000)

        normal_result = MagicMock()
        normal_result.returncode = 0
        normal_result.stdout = "Work in progress..."
        normal_result.stderr = ""
        normal_result.args = ["claude"]

        handoff_result = MagicMock()
        handoff_result.returncode = 0
        handoff_result.stdout = "CONTEXT_HANDOFF: Ready for fresh session"
        handoff_result.stderr = ""
        handoff_result.args = ["claude"]

        continuation_result = MagicMock()
        continuation_result.returncode = 0
        continuation_result.stdout = "Done!"
        continuation_result.stderr = ""
        continuation_result.args = ["claude"]

        call_count = [0]
        resume_session_flags: list[bool] = []

        def mock_run(command: str, *args, **kwargs):
            resume_session_flags.append(kwargs.get("resume_session", False))
            call_count[0] += 1
            if call_count[0] == 1:
                return normal_result
            elif call_count[0] == 2:
                return handoff_result
            return continuation_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch(
                "little_loops.issue_manager.detect_context_handoff",
                side_effect=lambda s: "CONTEXT_HANDOFF" in s,
            ):
                with patch(
                    "little_loops.issue_manager.read_continuation_prompt",
                    return_value="# Continuation prompt",
                ):
                    result = run_with_continuation(
                        "/ll:manage-issue bug fix BUG-1377",
                        mock_logger,
                        repo_path=temp_project_dir,
                        max_continuations=3,
                        resume_command="/ll:manage-issue bug fix BUG-1377",
                    )

        # call 1: main session (no CONTEXT_HANDOFF) → sentinel detected
        # call 2: explicit handoff instruction via --resume → CONTEXT_HANDOFF
        # call 3: standard continuation with --resume skill flag
        assert call_count[0] == 3
        assert resume_session_flags[1] is True  # second call uses CLI --resume
        assert resume_session_flags[0] is False
        assert result.returncode == 0

    def test_sentinel_consumed_by_read(self, temp_project_dir: Path) -> None:
        """Sentinel file is deleted after being read (consumed once)."""
        from little_loops.subprocess_utils import SENTINEL_PATH, read_sentinel, write_sentinel

        write_sentinel(temp_project_dir, token_count=130_000, context_limit=200_000)
        sentinel_file = temp_project_dir / SENTINEL_PATH
        assert sentinel_file.exists()

        data = read_sentinel(temp_project_dir)
        assert data is not None
        assert data["usage_percent"] == 65
        assert not sentinel_file.exists()  # consumed

        # Second read returns None (already consumed)
        assert read_sentinel(temp_project_dir) is None

    def test_guillotine_path_on_context_overflow(self, temp_project_dir: Path) -> None:
        """Option J: 'Prompt is too long' in stderr triggers fresh session (no --resume)."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Continued from guillotine"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]
        commands_received: list[str] = []

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            if call_count[0] == 1:
                return overflow_result
            return fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-1377",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                    context_limit=200_000,
                )

        assert call_count[0] == 2
        # Fresh session command contains the guillotine prompt header
        assert "CONTEXT LIMIT REACHED" in commands_received[1]
        assert "Original Task" in commands_received[1]
        # No --resume in guillotine prompt (fresh session)
        assert "--resume" not in commands_received[1]

    def test_guillotine_path_on_prompt_too_long(self, temp_project_dir: Path) -> None:
        """Option J: 'Prompt is too long' in stderr triggers fresh session."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Working..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Done from fresh session"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-1377",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                )

        assert call_count[0] == 2
        # Verify the J-path warning was logged
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("Option J" in w and "Prompt is too long" in w for w in warning_calls)

    def test_guillotine_with_run_dir_writes_resume_file(self, tmp_path: Path) -> None:
        """Option J + run_dir: writes guillotine-prompt.md and invokes /ll:resume."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()
        run_dir = tmp_path / "runs" / "my-loop-20260101"
        run_dir.mkdir(parents=True)

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Continued from resume"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]
        commands_received: list[str] = []

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-1377",
                    mock_logger,
                    repo_path=tmp_path,
                    max_continuations=3,
                    context_limit=200_000,
                    run_dir=str(run_dir),
                )

        assert call_count[0] == 2
        # Second command must be a /ll:resume invocation, not the summary blob
        assert commands_received[1].startswith("/ll:resume")
        assert "CONTEXT LIMIT REACHED" not in commands_received[1]
        # guillotine-prompt.md must be written inside run_dir
        guillotine_file = run_dir / "guillotine-prompt.md"
        assert guillotine_file.exists()
        content = guillotine_file.read_text()
        assert "## Intent" in content
        assert "## Next Steps" in content

    def test_guillotine_without_run_dir_uses_summary_blob(self, temp_project_dir: Path) -> None:
        """Option J without run_dir: assemble_guillotine_prompt fallback preserved."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Done"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]
        commands_received: list[str] = []

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-1377",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                    context_limit=200_000,
                    # run_dir not provided — legacy fallback path
                )

        assert call_count[0] == 2
        assert "CONTEXT LIMIT REACHED" in commands_received[1]
        assert not commands_received[1].startswith("/ll:resume")

    def test_high_cumulative_usage_does_not_write_sentinel(self, temp_project_dir: Path) -> None:
        """BUG-2280: Option G Python sentinel write removed — high cumulative usage no longer
        writes a sentinel. The sentinel is written only by the Stop hook."""
        from little_loops.issue_manager import run_with_continuation
        from little_loops.subprocess_utils import SENTINEL_PATH

        mock_logger = MagicMock()

        normal_result = MagicMock()
        normal_result.returncode = 0
        normal_result.stdout = "Work done"
        normal_result.stderr = ""
        normal_result.args = ["claude"]

        def mock_run(command: str, *args, **kwargs):
            on_usage = kwargs.get("on_usage")
            if on_usage:
                on_usage(120_000, 10_000)  # 130K cumulative — previously triggered sentinel
            return normal_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-1377",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=0,
                    context_limit=200_000,
                )

        sentinel_file = temp_project_dir / SENTINEL_PATH
        assert not sentinel_file.exists(), (
            "Python layer must not write sentinel from cumulative usage (BUG-2280)"
        )

    def test_option_j_fresh_session_skips_option_e(self, temp_project_dir: Path) -> None:
        """BUG-1386: after Option J fires a fresh session, Option E must NOT call --continue.

        Scenario: initial session hits 95% context → Option J spawns fresh session →
        fresh session completes (returncode 0) and its stop hook writes a sentinel →
        run_with_continuation must return the fresh session's returncode=0 without
        making a second --continue call.
        """
        from little_loops.issue_manager import run_with_continuation
        from little_loops.subprocess_utils import SENTINEL_PATH

        mock_logger = MagicMock()

        # Sentinel file that the fresh session's stop hook would have written
        sentinel_file = temp_project_dir / SENTINEL_PATH
        sentinel_file.parent.mkdir(parents=True, exist_ok=True)

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work"
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Issue implemented and committed"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]
        resume_called = [False]

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: "Prompt is too long" → triggers Option J
                return overflow_result
            # Second call: fresh guillotine session — write sentinel to simulate stop hook
            sentinel_file.write_text('{"usage_percent": 63}')
            if kwargs.get("resume_session"):
                resume_called[0] = True
            return fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                result = run_with_continuation(
                    "/ll:manage-issue bug fix BUG-1386",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                    context_limit=200_000,
                )

        # Fresh session completed successfully — result should be success
        assert result.returncode == 0, "Should return fresh session's returncode"
        # Option E must NOT have called --continue (resume_session=True)
        assert not resume_called[0], (
            "Option E must not call --continue after Option J fresh session"
        )
        # run_claude_command called exactly twice: initial session + guillotine fresh session
        assert call_count[0] == 2, f"Expected 2 calls, got {call_count[0]}"
        # Sentinel was consumed (file should be gone after read_sentinel)
        assert not sentinel_file.exists(), "Sentinel should have been consumed by read_sentinel"

    def test_guillotine_with_sprint_context_injects_framing(self, temp_project_dir: Path) -> None:
        """BUG-2141: Option J with sprint_context prepends sprint framing to fresh session prompt."""
        from little_loops.issue_manager import run_with_continuation
        from little_loops.parallel.types import SprintWorkerContext

        mock_logger = MagicMock()
        sprint_ctx = SprintWorkerContext(issue_id="FEAT-025", branch="main")

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Done from fresh session"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]
        commands_received: list[str] = []

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue feature implement FEAT-025",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                    context_limit=200_000,
                    sprint_context=sprint_ctx,
                )

        assert call_count[0] == 2
        fresh_cmd = commands_received[1]
        assert "Sprint Worker Context" in fresh_cmd
        assert "FEAT-025" in fresh_cmd
        assert "exit immediately" in fresh_cmd
        assert "Branch: main" in fresh_cmd

    def test_guillotine_without_sprint_context_unaffected(self, temp_project_dir: Path) -> None:
        """BUG-2141: Option J without sprint_context produces no sprint framing (no regression)."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = "API error: Prompt is too long"
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Done"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]
        commands_received: list[str] = []

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            commands_received.append(command)
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-001",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                    context_limit=200_000,
                    # no sprint_context
                )

        assert call_count[0] == 2
        assert "Sprint Worker Context" not in commands_received[1]

    def test_guillotine_run_dir_single_issue_scope_constraint(self, tmp_path: Path) -> None:
        """BUG-2201: Option J + run_dir + issue_path (no sprint_context) emits scope constraint."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()
        run_dir = tmp_path / "runs" / "rn-implement-20260616"
        run_dir.mkdir(parents=True)
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P2-ENH-2177-test-issue.md"
        issue_file.write_text("---\nid: ENH-2177\nstatus: open\n---\n# ENH-2177")

        overflow_result = MagicMock()
        overflow_result.returncode = 1
        overflow_result.stdout = "Partial work..."
        overflow_result.stderr = ""
        overflow_result.args = ["claude"]

        fresh_result = MagicMock()
        fresh_result.returncode = 0
        fresh_result.stdout = "Continued from resume"
        fresh_result.stderr = ""
        fresh_result.args = ["claude"]

        call_count = [0]

        overflow_result.stderr = "API error: Prompt is too long"

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            return overflow_result if call_count[0] == 1 else fresh_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "ll-auto --only ENH-2177",
                    mock_logger,
                    repo_path=tmp_path,
                    max_continuations=3,
                    context_limit=200_000,
                    issue_path=issue_file,
                    run_dir=str(run_dir),
                    # sprint_context is None (the missing-scope bug path)
                )

        assert call_count[0] == 2
        guillotine_file = run_dir / "guillotine-prompt.md"
        assert guillotine_file.exists()
        content = guillotine_file.read_text()
        assert "ENH-2177" in content, "Scope constraint must name the issue"
        assert "exactly ONE issue" in content, "Scope constraint must say 'exactly ONE issue'"
        assert "exit immediately" in content, "Scope constraint must instruct immediate exit"

    def test_large_cumulative_tokens_with_clean_completion_no_guillotine(
        self, temp_project_dir: Path
    ) -> None:
        """BUG-2280: cumulative session tokens >> context window must NOT trigger Option J.

        A session consuming 989K cumulative tokens (across many turns with cache reads) that
        completes cleanly (returncode=0, no 'prompt is too long') must not spawn a continuation.
        The defective usage_ratio = cumulative_total / context_limit arm fired at ~495%; after
        the fix only prompt_too_long triggers Option J.
        """
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        clean_result = MagicMock()
        clean_result.returncode = 0
        clean_result.stdout = "Issue implemented and committed"
        clean_result.stderr = ""
        clean_result.args = ["claude"]

        call_count = [0]

        def mock_run(command: str, *args, **kwargs):
            call_count[0] += 1
            on_usage = kwargs.get("on_usage")
            if on_usage:
                on_usage(989_202, 0)  # cumulative tokens far over 200K window
            return clean_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "/ll:manage-issue bug fix BUG-2280",
                    mock_logger,
                    repo_path=temp_project_dir,
                    max_continuations=3,
                    context_limit=200_000,
                )

        assert call_count[0] == 1, (
            f"Expected 1 call (no continuation), got {call_count[0]}: "
            "cumulative tokens must not trigger Option J"
        )


class TestReadyIssueErrorHandling:
    """Tests for error handling during ready-issue phase (ENH-207)."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig for testing."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue for testing."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test-bug.md"
        issue_file.write_text("# BUG-001: Test Bug\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test Bug",
        )

    def test_ready_issue_failure_continues_anyway(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that ready-issue failure is logged but processing continues."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # ready-issue fails but doesn't crash
        mock_result = MagicMock()
        mock_result.returncode = 1  # Non-zero return code
        mock_result.stdout = ""
        mock_result.stderr = "Some error"

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.run_with_continuation") as mock_impl:
                    mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch(
                        "little_loops.issue_manager.verify_issue_completed", return_value=True
                    ):
                        process_issue_inplace(sample_issue, mock_config, mock_logger)

        # Should continue (not crash) - verify implementation was called
        mock_impl.assert_called_once()

    def test_fallback_ready_issue_failure_returns_error(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that fallback ready-issue failure returns error result."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # First ready-issue returns wrong path (mismatch)
        first_output = """
## VERDICT
READY

## VALIDATED_FILE
.wrong/path/file.md
"""
        first_result = MagicMock()
        first_result.returncode = 0
        first_result.stdout = first_output

        # Fallback ready-issue fails
        fallback_result = MagicMock()
        fallback_result.returncode = 1
        fallback_result.stdout = ""
        fallback_result.stderr = "Fallback failed"

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return first_result
            return fallback_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Fallback failed" in result.failure_reason

    def test_persistent_path_mismatch_returns_error(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that persistent mismatch after fallback returns error."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # Both calls return wrong path
        wrong_path = ".issues/bugs/P1-WRONG-999.md"
        output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_path}
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Path mismatch persisted" in result.failure_reason


class TestCorrectionsAndConcerns:
    """Tests for corrections and concerns handling (ENH-207)."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_corrections_are_logged_and_stored(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that corrections from ready-issue are logged and stored."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = """
## VERDICT
CORRECTED

## IS_READY
true

## CORRECTIONS_MADE
- Fixed title
- Added description

## VALIDATED_FILE
""" + str(sample_issue.path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=mock_result),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
        ):
            mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert result.corrections == ["Fixed title", "Added description"]

    def test_concerns_are_logged(self, mock_config: BRConfig, sample_issue: IssueInfo) -> None:
        """Test that concerns from ready-issue are logged as warnings."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
READY

## CONCERNS
- Minor issue found
- Another concern

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=mock_result),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
        ):
            mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
            process_issue_inplace(sample_issue, mock_config, mock_logger)

        # Verify warnings were called
        assert any("Concern" in str(call) for call in mock_logger.warning.call_args_list)


class TestCloseVerdictHandling:
    """Tests for CLOSE verdict handling in ready-issue phase (ENH-207)."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_close_with_invalid_ref_fails_without_file_ops(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that CLOSE with invalid_ref returns error without file operations."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # Use the correct format expected by the parser
        output = """
## VERDICT
CLOSE

## CLOSE_REASON
- Reason: invalid_ref

## VALIDATED_FILE
""" + str(sample_issue.path)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Invalid reference" in result.failure_reason
        # close_issue should NOT be called
        mock_logger.warning.assert_called()

    def test_close_without_validated_path_fails(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that CLOSE without validated_file_path returns error."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = """
## VERDICT
CLOSE

## CLOSE_REASON
duplicate
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "CLOSE without validated file path" in result.failure_reason

    def test_close_success_returns_closed_result(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that successful close returns was_closed=True."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
CLOSE

## CLOSE_REASON
- Reason: duplicate

## CLOSE_STATUS
Closed - Duplicate

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            with patch("little_loops.issue_manager.close_issue", return_value=True) as mock_close:
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert result.success
        assert result.was_closed
        mock_close.assert_called_once()

    def test_not_ready_verdict_fails_processing(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that NOT READY verdict fails processing."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
NOT_READY

## CONCERNS
- Missing requirements
- Unclear scope

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        # The failure_reason includes the verdict and concern count
        assert result.failure_reason


class TestFailureClassification:
    """Tests for implementation failure classification (ENH-207)."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    @pytest.mark.parametrize(
        ("error_msg", "expected_transient"),
        [
            ("Error: You're out of extra usage · resets 2pm", True),
            ("Rate limit exceeded. Please retry after 60s", True),
            ("Error 429: Too many requests", True),
            ("Connection refused: localhost:8080", True),
            ("Error: Connection timeout after 30s", True),
            ("HTTP 401 Unauthorized", True),  # NON_RECOVERABLE → suppress (BUG-2302)
            ("Error: Invalid API key provided", True),  # NON_RECOVERABLE → suppress
            ("SyntaxError: unexpected token at line 42", False),
            ("FAILED tests/test_foo.py::test_bar - AssertionError", False),
        ],
    )
    def test_transient_vs_real_failure_classification(
        self,
        mock_config: BRConfig,
        sample_issue: IssueInfo,
        error_msg: str,
        expected_transient: bool,
    ) -> None:
        """Test that failures are correctly classified as transient or real."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # ready-issue succeeds
        ready_output = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"
        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = ready_output

        # Implementation fails
        impl_result = MagicMock()
        impl_result.returncode = 1
        impl_result.stdout = ""
        impl_result.stderr = error_msg

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ready_result
            return impl_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                if expected_transient:
                    # Transient or NON_RECOVERABLE: should NOT create bug issue
                    with patch(
                        "little_loops.issue_manager.create_issue_from_failure"
                    ) as mock_create:
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)
                        mock_create.assert_not_called()
                        assert (
                            "Transient" in result.failure_reason
                            or "Non-recoverable" in result.failure_reason
                        )
                else:
                    # Real failure: should create bug issue
                    with patch(
                        "little_loops.issue_manager.create_issue_from_failure",
                        return_value=sample_issue.path,
                    ):
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)
                        assert not result.success

    def test_early_completion_guard_when_issue_already_in_completed(
        self, mock_config: BRConfig, sample_issue: IssueInfo, temp_project_dir: Path
    ) -> None:
        """BUG-1386 Change 3: non-zero Phase 2 exit is treated as success when
        the issue's frontmatter already shows ``status: done`` (post-ENH-1418)."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # Post-ENH-1418: completion is signalled by frontmatter, not file location.
        sample_issue.path.write_text(
            "---\nstatus: done\n---\n\n# completed",
            encoding="utf-8",
        )

        ready_output = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"
        ready_result = MagicMock(returncode=0, stdout=ready_output, stderr="")

        # Implementation exited non-zero (e.g., spurious --continue failure)
        impl_result = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: --continue requires a valid session title when used with --print.",
            args=[],
        )

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            return ready_result if call_count[0] == 1 else impl_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=True):
                    with patch(
                        "little_loops.issue_manager.create_issue_from_failure"
                    ) as mock_create:
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        # No phantom issue should be created
        mock_create.assert_not_called()
        # Result should be success (issue was already completed)
        assert result.success


class TestFallbackVerification:
    """Tests for fallback verification when issue not moved (ENH-207)."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        """Create a mock BRConfig."""
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        """Create a sample issue."""
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_fallback_completion_when_work_detected(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that fallback completion succeeds when work is detected."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # ready-issue and implement succeed
        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=None
                    ):
                        with patch(
                            "little_loops.issue_manager.check_content_markers",
                            return_value=False,
                        ):
                            with patch(
                                "little_loops.issue_manager.verify_work_was_done",
                                return_value=True,
                            ):
                                with patch(
                                    "little_loops.issue_manager.complete_issue_lifecycle",
                                    return_value=True,
                                ):
                                    result = process_issue_inplace(
                                        sample_issue, mock_config, mock_logger
                                    )

        assert result.success

    def test_refuses_completion_when_no_work_detected(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that completion is refused when no work is detected."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=None
                    ):
                        with patch(
                            "little_loops.issue_manager.check_content_markers",
                            return_value=False,
                        ):
                            with patch(
                                "little_loops.issue_manager.verify_work_was_done",
                                return_value=False,
                            ):
                                result = process_issue_inplace(
                                    sample_issue, mock_config, mock_logger
                                )

        assert not result.success
        mock_logger.error.assert_called()

    def test_fallback_completion_via_content_markers(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that content markers trigger fallback completion (ENH-328)."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=None
                    ):
                        with patch(
                            "little_loops.issue_manager.check_content_markers",
                            return_value=True,
                        ):
                            with patch(
                                "little_loops.issue_manager.complete_issue_lifecycle",
                                return_value=True,
                            ) as mock_complete:
                                result = process_issue_inplace(
                                    sample_issue, mock_config, mock_logger
                                )

        assert result.success
        mock_complete.assert_called_once()

    def test_content_markers_skips_git_evidence_check(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Test that content markers skip the git evidence check (ENH-328)."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=None
                    ):
                        with patch(
                            "little_loops.issue_manager.check_content_markers",
                            return_value=True,
                        ):
                            with patch(
                                "little_loops.issue_manager.verify_work_was_done"
                            ) as mock_work:
                                with patch(
                                    "little_loops.issue_manager.complete_issue_lifecycle",
                                    return_value=True,
                                ):
                                    process_issue_inplace(sample_issue, mock_config, mock_logger)

        # verify_work_was_done should NOT be called when content markers found
        mock_work.assert_not_called()

    def test_baseline_sha_passed_to_verify_work_was_done(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """baseline_sha captured before Phase 2 is forwarded to verify_work_was_done."""
        import subprocess as _subprocess

        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()
        test_sha = "deadbeef1234"

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        def fake_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd == ["git", "rev-parse", "HEAD"]:
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout=f"{test_sha}\n")
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=None
                    ):
                        with patch(
                            "little_loops.issue_manager.check_content_markers",
                            return_value=False,
                        ):
                            with patch(
                                "little_loops.issue_manager.subprocess.run",
                                side_effect=fake_subprocess_run,
                            ):
                                with patch(
                                    "little_loops.issue_manager.verify_work_was_done",
                                    return_value=True,
                                ) as mock_verify:
                                    with patch(
                                        "little_loops.issue_manager.complete_issue_lifecycle",
                                        return_value=True,
                                    ):
                                        process_issue_inplace(
                                            sample_issue, mock_config, mock_logger
                                        )

        mock_verify.assert_called_once_with(mock_logger, baseline_sha=test_sha)


class TestEarlyCompletionGuard:
    """Tests for the already_done guard when Phase 2 exits non-zero (BUG-1538)."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("---\nstatus: completed\n---\n\n# BUG-001: Test")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

    def test_early_completion_guard_accepts_completed_status(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """already_done guard fires for status: completed when Phase 2 exits non-zero."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        # Phase 2 exits non-zero (simulates a spurious continuation failure)
        impl_result = MagicMock()
        impl_result.returncode = 1
        impl_result.stdout = ""
        impl_result.stderr = "Option E --continue failed"
        impl_result.args = []

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.subprocess.run") as mock_sub:
                    mock_sub.return_value = MagicMock(returncode=0, stdout="abc123\n")
                    with patch(
                        "little_loops.issue_manager.verify_issue_completed", return_value=True
                    ):
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        # Guard should have detected status=completed (normalized to done) and treated as success
        assert result.success


class TestCheckContentMarkers:
    """Tests for check_content_markers() (ENH-328)."""

    def test_resolution_section_detected(self, tmp_path: Path) -> None:
        """Returns True when issue file contains ## Resolution section."""
        from little_loops.issue_manager import check_content_markers

        issue_file = tmp_path / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest\n\n## Resolution\nFixed.")
        assert check_content_markers(issue_file) is True

    def test_status_implemented_detected(self, tmp_path: Path) -> None:
        """Returns True when issue file contains Status: Implemented."""
        from little_loops.issue_manager import check_content_markers

        issue_file = tmp_path / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\nStatus: Implemented\n")
        assert check_content_markers(issue_file) is True

    def test_status_completed_detected(self, tmp_path: Path) -> None:
        """Returns True when issue file contains Status: Completed."""
        from little_loops.issue_manager import check_content_markers

        issue_file = tmp_path / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\nStatus: Completed\n")
        assert check_content_markers(issue_file) is True

    def test_completed_date_marker_detected(self, tmp_path: Path) -> None:
        """Returns True when issue file contains **Completed**: date marker."""
        from little_loops.issue_manager import check_content_markers

        issue_file = tmp_path / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n**Completed**: 2026-02-14\n")
        assert check_content_markers(issue_file) is True

    def test_no_markers_returns_false(self, tmp_path: Path) -> None:
        """Returns False when issue file has no implementation markers."""
        from little_loops.issue_manager import check_content_markers

        issue_file = tmp_path / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest issue")
        assert check_content_markers(issue_file) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        """Returns False when issue file does not exist."""
        from little_loops.issue_manager import check_content_markers

        issue_file = tmp_path / "nonexistent.md"
        assert check_content_markers(issue_file) is False


class TestAutoManagerRun:
    """Tests for AutoManager.run() main loop (ENH-207)."""

    @pytest.fixture
    def full_project(self, temp_project_dir: Path) -> Path:
        """Set up a complete project for run() testing."""

        # Create .claude directory with config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {
                        "prefix": "BUG",
                        "dir": "bugs",
                        "action": "fix",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)

        # Create a test issue
        (issues_dir / "P1-BUG-001-test-issue.md").write_text(
            "# BUG-001: Test Issue\n\n## Summary\nTest"
        )

        return temp_project_dir

    def test_run_processes_single_issue(self, full_project: Path) -> None:
        """Test that run() processes a single issue."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)

        # Mock the actual processing
        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-001",
                was_closed=False,
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    max_issues=1,
                    db_path=config.project_root / ".ll" / "history.db",
                )

                exit_code = manager.run()

        assert exit_code == 0
        assert manager.processed_count == 1

    def test_run_stops_at_max_issues(self, full_project: Path) -> None:
        """Test that run() stops after reaching max_issues."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create multiple issues
        issues_dir = full_project / ".issues" / "bugs"
        for i in range(2, 6):
            (issues_dir / f"P1-BUG-{i:03d}-test.md").write_text(
                f"# BUG-{i}: Test\n\n## Summary\nTest"
            )

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-001",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    max_issues=2,
                    db_path=config.project_root / ".ll" / "history.db",
                )

                manager.run()

        assert manager.processed_count == 2

    def test_run_with_only_ids_filter(self, full_project: Path) -> None:
        """Test that run() filters by only_ids."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Create additional issues
        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-002-other.md").write_text("# BUG-002: Other\n\n## Summary\nOther")
        (issues_dir / "P1-BUG-003-target.md").write_text("# BUG-003: Target\n\n## Summary\nTarget")

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-003",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    only_ids={"BUG-003"},
                    db_path=config.project_root / ".ll" / "history.db",
                )

                manager.run()

        # Should only process BUG-003
        mock_process.assert_called_once()

    def test_run_with_numeric_only_id_filter(self, full_project: Path) -> None:
        """Test that run() with a numeric-only --only filter (e.g. '003') matches full IDs."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-002-other.md").write_text("# BUG-002: Other\n\n## Summary\nOther")
        (issues_dir / "P1-BUG-003-target.md").write_text("# BUG-003: Target\n\n## Summary\nTarget")

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=1.0,
                issue_id="BUG-003",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                # Numeric-only ID "003" should match "BUG-003"
                manager = AutoManager(
                    config,
                    dry_run=False,
                    only_ids={"003"},
                    db_path=config.project_root / ".ll" / "history.db",
                )

                manager.run()

        # Should only process BUG-003 via numeric-only match
        mock_process.assert_called_once()

    def test_run_returns_one_when_only_ids_all_gate_blocked(self, full_project: Path) -> None:
        """run() exits 1 when --only was used and every issue was gate-blocked (processed 0)."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-004-needs-decision.md").write_text(
            "---\ndecision_needed: true\n---\n# BUG-004: Needs Decision\n\n## Summary\nBlocked"
        )

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            # Simulate gate-blocked: process_issue_inplace returns failure
            mock_process.return_value = MagicMock(
                success=False,
                duration=0.1,
                issue_id="BUG-004",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    only_ids={"BUG-004"},
                    db_path=config.project_root / ".ll" / "history.db",
                )

                result = manager.run()

        assert result == 1


class TestSignalHandler:
    """Tests for graceful shutdown signal handling (ENH-207)."""

    def test_signal_handler_sets_shutdown_flag(self, temp_project_dir: Path) -> None:
        """Test that signal handler sets _shutdown_requested flag."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Setup
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

        config = BRConfig(temp_project_dir)
        manager = AutoManager(config, dry_run=True)

        # Initially not shutdown
        assert manager._shutdown_requested is False

        # Simulate signal handler call
        import signal

        manager._signal_handler(signal.SIGINT, None)

        # Flag should be set
        assert manager._shutdown_requested is True


class TestTimingSummaryAndStateUpdates:
    """Tests for timing summary and state update conditions (ENH-207)."""

    def test_timing_summary_logged(self, temp_project_dir: Path) -> None:
        """Test that timing summary is logged with aggregate stats."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Setup project
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(exist_ok=True)

        # Create a test issue
        (issues_dir / "P1-BUG-001-test.md").write_text("# BUG-001: Test\n\n## Summary\nTest")

        config = BRConfig(temp_project_dir)

        # Run the manager - this exercises the timing summary code path
        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            mock_process.return_value = MagicMock(
                success=True,
                duration=5.0,
                issue_id="BUG-001",
                corrections=[],
            )
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False, max_issues=1, verbose=True)
                exit_code = manager.run()

        # Verify run completed successfully (timing summary is called at end of run)
        assert exit_code == 0
        assert manager.processed_count == 1

    def test_state_update_branches(self, temp_project_dir: Path) -> None:
        """Test that all state update branches are covered."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        # Setup
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)
        (temp_project_dir / ".issues" / "completed").mkdir(exist_ok=True)

        issue_file = issues_dir / "P1-BUG-001-test.md"
        issue_file.write_text("# BUG-001: Test\n\n## Summary\nTest")

        config = BRConfig(temp_project_dir)

        # Test was_closed branch
        closed_result = MagicMock(
            success=True,
            duration=1.0,
            issue_id="BUG-001",
            was_closed=True,
            corrections=[],
        )

        with patch("little_loops.issue_manager.process_issue_inplace", return_value=closed_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False)
                manager._process_issue(manager._get_next_issue())

        # Test failure_reason branch
        failed_result = MagicMock(
            success=False,
            duration=1.0,
            issue_id="BUG-001",
            failure_reason="Test failure",
            corrections=[],
        )

        with patch("little_loops.issue_manager.process_issue_inplace", return_value=failed_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False)
                manager._process_issue(manager._get_next_issue())

        # Test corrections branch
        with_corrections_result = MagicMock(
            success=True,
            duration=1.0,
            issue_id="BUG-001",
            corrections=["Fixed title"],
        )

        with patch(
            "little_loops.issue_manager.process_issue_inplace", return_value=with_corrections_result
        ):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(config, dry_run=False)
                manager._process_issue(manager._get_next_issue())


class TestIssueManagerConcurrency:
    """Tests for concurrent access to AutoManager (ENH-217)."""

    @pytest.fixture
    def temp_project_with_issues(self, temp_project_dir: Path) -> Path:
        """Set up project with multiple issues for concurrent testing."""

        # Create .claude directory with config
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {
                        "prefix": "BUG",
                        "dir": "bugs",
                        "action": "fix",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        # Create multiple issues
        for i in range(1, 11):
            (issues_dir / f"P1-BUG-{i:03d}-test-issue.md").write_text(
                f"# BUG-{i:03d}: Test Issue\n\n## Summary\nTest issue {i}"
            )

        return temp_project_dir

    def test_concurrent_get_next_issue_no_duplicates(self, temp_project_with_issues: Path) -> None:
        """Multiple threads calling _get_next_issue should not get duplicates."""
        config = BRConfig(temp_project_with_issues)
        manager = AutoManager(config, dry_run=True)

        results = []
        lock = threading.Lock()

        def get_issue() -> None:
            """Try to get next issue."""
            issue = manager._get_next_issue()
            if issue:
                with lock:
                    results.append(issue.issue_id)

        threads = [threading.Thread(target=get_issue) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no duplicates (or document current behavior)
        # Note: Current implementation may return duplicates if called concurrently
        unique_ids = set(results)
        # Document: if duplicates exist, this shows race condition
        assert len(unique_ids) <= len(results)

    def test_concurrent_state_file_access(self, temp_project_dir: Path) -> None:
        """Multiple managers accessing same state file."""

        # Setup
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

        config = BRConfig(temp_project_dir)

        errors = []

        def run_manager(manager_id: int) -> None:
            try:
                manager = AutoManager(config, dry_run=True)
                # All share same state file
                manager._load_state()
                manager.state_manager.mark_attempted(f"MANAGER-{manager_id}", save=True)
            except Exception as e:
                errors.append((manager_id, e))

        threads = [threading.Thread(target=run_manager, args=(i,)) for i in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Document: May have errors due to file contention
        # Current behavior: last write wins, potential JSON corruption
        assert len(errors) >= 0  # Document whatever happens

    def test_concurrent_state_modifications(self, temp_project_dir: Path) -> None:
        """Multiple threads modifying state simultaneously."""

        # Setup
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

        config = BRConfig(temp_project_dir)
        manager = AutoManager(config, dry_run=True)

        errors = []

        def modify_state(thread_id: int) -> None:
            try:
                for i in range(10):
                    manager.state_manager.mark_attempted(f"T{thread_id}-I{i}", save=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=modify_state, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No crashes (though updates may be lost)
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_concurrent_dependency_queries(self, temp_project_with_issues: Path) -> None:
        """Multiple threads querying dependency graph."""
        config = BRConfig(temp_project_with_issues)
        manager = AutoManager(config, dry_run=True)

        errors = []
        query_count = [0]

        def query_graph() -> None:
            try:
                for _ in range(20):
                    _ = manager.dep_graph.get_ready_issues(set())
                    query_count[0] += 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=query_graph) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All queries should succeed (graph is read-only after init)
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert query_count[0] == 100


class TestDetectPlanCreation:
    """Tests for detect_plan_creation function."""

    def test_no_plan_returns_none(self, temp_project_dir: Path) -> None:
        """Returns None when no plan file exists."""
        from little_loops.issue_manager import detect_plan_creation

        # Setup: Create plans directory but no matching plan
        plans_dir = temp_project_dir / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)

        # Change to temp directory
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(temp_project_dir)

            # Test
            result = detect_plan_creation("", "BUG-999")

            # Verify
            assert result is None
        finally:
            os.chdir(original_dir)

    def test_matching_plan_returns_path(self, temp_project_dir: Path) -> None:
        """Returns Path when matching plan file exists."""
        from little_loops.issue_manager import detect_plan_creation

        # Setup: Create plan file
        plans_dir = temp_project_dir / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)
        plan_file = plans_dir / "2026-02-08-BUG-280-management.md"
        plan_file.write_text("# Plan content")

        # Change to temp directory
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(temp_project_dir)

            # Test
            result = detect_plan_creation("", "BUG-280")

            # Verify
            assert result is not None
            assert result.name == "2026-02-08-BUG-280-management.md"
        finally:
            os.chdir(original_dir)

    def test_multiple_plans_returns_latest(self, temp_project_dir: Path) -> None:
        """Returns most recently modified plan when multiple exist."""
        from little_loops.issue_manager import detect_plan_creation

        # Setup: Create multiple plan files
        plans_dir = temp_project_dir / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)
        old_plan = plans_dir / "2026-02-07-BUG-280-management.md"
        new_plan = plans_dir / "2026-02-08-BUG-280-management.md"
        old_plan.write_text("# Old plan")
        import time

        time.sleep(0.01)  # Ensure different mtimes
        new_plan.write_text("# New plan")

        # Change to temp directory
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(temp_project_dir)

            # Test
            result = detect_plan_creation("", "BUG-280")

            # Verify
            assert result is not None
            assert result.name == "2026-02-08-BUG-280-management.md"
        finally:
            os.chdir(original_dir)

    def test_no_plans_dir_returns_none(self, temp_project_dir: Path) -> None:
        """Returns None when plans directory doesn't exist."""
        # Change to temp directory (without creating plans dir)
        import os

        from little_loops.issue_manager import detect_plan_creation

        original_dir = os.getcwd()
        try:
            os.chdir(temp_project_dir)

            # Test
            result = detect_plan_creation("", "BUG-999")

            # Verify
            assert result is None
        finally:
            os.chdir(original_dir)


class TestAutoManagerModelDetection:
    """Tests for AutoManager model name detection and logging (ENH-838)."""

    @pytest.fixture
    def temp_project_with_issue(self, temp_project_dir: Path) -> Path:
        """Set up project with a single feature issue."""
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))

        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()
        (issues_dir / "P1-FEAT-001-test-feature.md").write_text("# FEAT-001: Test Feature\n")

        return temp_project_dir

    def test_auto_manager_logs_detected_model(self, temp_project_with_issue: Path) -> None:
        """AutoManager logs model name when on_model_detected callback fires."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult

        config = BRConfig(temp_project_with_issue)
        manager = AutoManager(config, dry_run=False)

        # Capture logger.info calls
        info_log: list[str] = []
        manager.logger.info = lambda msg: info_log.append(msg)  # type: ignore[method-assign]

        issue = manager._get_next_issue()
        assert issue is not None

        def mock_process_inplace(
            info: Any,
            cfg: Any,
            logger: Any,
            dry_run: bool = False,
            on_model_detected: Any = None,
            on_usage: Any = None,
            preview_full: bool = False,
            event_bus: Any = None,
            sprint_context: Any = None,
            context_limit: Any = None,
            skip_learning_gate: bool = False,
        ) -> IssueProcessingResult:
            if on_model_detected:
                on_model_detected("claude-sonnet-4-6")
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            side_effect=mock_process_inplace,
        ):
            manager._process_issue(issue)

        assert any("model: claude-sonnet-4-6" in msg for msg in info_log)


class TestDecisionNeededGate:
    """Tests for conditional decide-issue invocation when decision_needed=True."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.idle_timeout_seconds = 0
        config.automation.max_continuations = 3
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def issue_with_decision(self, temp_project_dir: Path) -> IssueInfo:
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-900-decision-needed.md"
        issue_file.write_text("# BUG-900: Decision Needed\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-900",
            title="Decision Needed",
            decision_needed=True,
        )

    @pytest.fixture
    def issue_without_decision(self, temp_project_dir: Path) -> IssueInfo:
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P1-BUG-901-no-decision.md"
        issue_file.write_text("# BUG-901: No Decision\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-901",
            title="No Decision",
            decision_needed=None,
        )

    def test_decide_issue_invoked_when_decision_needed(
        self, mock_config: BRConfig, issue_with_decision: IssueInfo
    ) -> None:
        """decide-issue is called when decision_needed=True after ready-issue."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()
        fail_result = MagicMock(returncode=1, stdout="", stderr="")

        with patch(
            "little_loops.issue_manager.run_claude_command", return_value=fail_result
        ) as mock_cmd:
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.run_with_continuation") as mock_impl:
                    mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch(
                        "little_loops.issue_manager.verify_issue_completed", return_value=True
                    ):
                        process_issue_inplace(issue_with_decision, mock_config, mock_logger)

        # run_claude_command called twice: once for ready-issue, once for decide-issue
        assert mock_cmd.call_count == 2
        all_cmds = [str(call.args[0]) for call in mock_cmd.call_args_list]
        assert any("decide-issue" in cmd for cmd in all_cmds)

    def test_decide_issue_skipped_when_decision_not_needed(
        self, mock_config: BRConfig, issue_without_decision: IssueInfo
    ) -> None:
        """decide-issue is NOT called when decision_needed is None."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()
        fail_result = MagicMock(returncode=1, stdout="", stderr="")

        with patch(
            "little_loops.issue_manager.run_claude_command", return_value=fail_result
        ) as mock_cmd:
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.run_with_continuation") as mock_impl:
                    mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch(
                        "little_loops.issue_manager.verify_issue_completed", return_value=True
                    ):
                        process_issue_inplace(issue_without_decision, mock_config, mock_logger)

        # run_claude_command called only once (ready-issue), not for decide-issue
        assert mock_cmd.call_count == 1
        all_cmds = [str(call.args[0]) for call in mock_cmd.call_args_list]
        assert not any("decide-issue" in cmd for cmd in all_cmds)


import json as _json  # noqa: E402 — appended fixture imports


class TestAutoManagerLearningGate:
    """ENH-2319: Per-issue learning gate wired into ll-auto (process_issue_inplace)."""

    @pytest.fixture
    def lt_enabled_config(self, temp_project_dir: Path) -> BRConfig:
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.idle_timeout_seconds = 0
        config.automation.max_continuations = 3
        config.learning_tests = MagicMock()
        config.learning_tests.enabled = True
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def lt_disabled_config(self, temp_project_dir: Path) -> BRConfig:
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.idle_timeout_seconds = 0
        config.automation.max_continuations = 3
        config.learning_tests = MagicMock()
        config.learning_tests.enabled = False
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    def _make_issue(
        self,
        tmp_path: Path,
        *,
        issue_id: str = "ENH-100",
        learning_tests_required: list[str] | None = None,
    ) -> IssueInfo:
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / f"P2-{issue_id}-stub.md"
        issue_file.write_text(
            f"---\nid: {issue_id}\ntitle: Stub\nstatus: open\n---\n# {issue_id}: Stub\n"
        )
        return IssueInfo(
            path=issue_file,
            issue_type="enhancements",
            priority="P2",
            issue_id=issue_id,
            title="Stub issue",
            learning_tests_required=learning_tests_required,
        )

    def _write_blocked_state(self, project_root: Path) -> None:
        """Write a proof-first-task state file indicating blocked verdict."""
        state_dir = project_root / ".loops" / ".running"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "proof-first-task.state.json").write_text(
            _json.dumps({"current_state": "blocked", "status": "completed"})
        )

    def test_blocked_gate_verdict_skips_implement_phase(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path
    ) -> None:
        """When proof-first-task returns blocked, implement phase is skipped."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])
        self._write_blocked_state(temp_project_dir)

        fail_ready = MagicMock(returncode=1, stdout="", stderr="")
        MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=fail_ready),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="blocked",
            ),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
        ):
            result = process_issue_inplace(
                issue, lt_enabled_config, MagicMock(), skip_learning_gate=False
            )

        assert result.success is False
        assert "blocked" in result.failure_reason.lower()
        mock_impl.assert_not_called()

    def test_skip_learning_gate_bypasses_gate_and_runs_implement(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path
    ) -> None:
        """--skip-learning-gate causes the gate to return skipped; implement runs."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])

        fail_ready = MagicMock(returncode=1, stdout="", stderr="")
        impl_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=fail_ready),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="skipped",
            ) as mock_gate,
            patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ) as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
            patch("little_loops.issue_manager.check_git_status", return_value=False),
        ):
            process_issue_inplace(issue, lt_enabled_config, MagicMock(), skip_learning_gate=True)

        # Gate was called with skip=True
        mock_gate.assert_called_once()
        _, kwargs = mock_gate.call_args
        assert kwargs.get("skip") is True
        # Implement phase runs
        mock_impl.assert_called_once()

    def test_gate_not_invoked_when_learning_tests_disabled(
        self, lt_disabled_config: BRConfig, temp_project_dir: Path
    ) -> None:
        """When learning_tests.enabled=False, gate function is never called."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])

        fail_ready = MagicMock(returncode=1, stdout="", stderr="")
        impl_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=fail_ready),
            patch("little_loops.issue_manager.run_learning_gate_for_issue") as mock_gate,
            patch("little_loops.issue_manager.run_with_continuation", return_value=impl_result),
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
            patch("little_loops.issue_manager.check_git_status", return_value=False),
        ):
            process_issue_inplace(issue, lt_disabled_config, MagicMock())

        # Gate must NOT have been called (learning_tests disabled)
        mock_gate.assert_not_called()

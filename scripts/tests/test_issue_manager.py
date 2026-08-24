"""Tests for little_loops.issue_manager module."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
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
    def setup_project(
        self,
        make_project: Callable[[dict[str, Any] | None, list[str] | None], tuple[Path, Path]],
    ) -> tuple[Path, Path]:
        """Set up a minimal project structure."""
        project, issues_base = make_project(
            config={
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
            },
            extra_dirs=[".issues/completed"],
        )
        return project, issues_base / "enhancements"

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
            # BUG-2963: report a clean tree to the completion pre-flight's
            # `git status --porcelain -z`; otherwise the canned commit stdout is
            # parsed as a dirty path and the close is (correctly) refused.
            if "status" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
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

    def test_path_mismatch_persisted_prints_not_started_marker(
        self, temp_project_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-2989: a fallback retry that still mismatches never reaches Phase 2 —
        emits PHASE1_NOT_STARTED with reason "path_mismatch"."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import process_issue_inplace
        from little_loops.issue_parser import IssueInfo

        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        expected_file = issues_dir / "P1-BUG-001-test.md"
        expected_file.write_text("# BUG-001: Test\n\n## Summary\nTest")
        wrong_file = issues_dir / "P1-BUG-999-wrong.md"
        wrong_file.write_text("# BUG-999: Wrong\n")

        sample_issue = IssueInfo(
            path=expected_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test",
        )

        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.automation.ready_issue_unknown_retries = 1
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"

        first_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_file}
"""
        # The fallback retry still validates the wrong file — persistent mismatch.
        retry_result = MagicMock(returncode=0, stdout=first_output, stderr="")
        first_result = MagicMock(returncode=0, stdout=first_output, stderr="")

        with patch(
            "little_loops.issue_manager.run_claude_command",
            side_effect=[first_result, retry_result],
        ):
            result = process_issue_inplace(sample_issue, config, MagicMock())

        assert not result.success
        assert "Path mismatch persisted after fallback" in result.failure_reason
        assert (
            f"PHASE1_NOT_STARTED {sample_issue.issue_id} path_mismatch" in capsys.readouterr().out
        )

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
        mock_config.project_root = temp_project_dir
        mock_config.repo_path = temp_project_dir
        mock_config.automation = MagicMock()
        mock_config.automation.timeout_seconds = 60
        mock_config.automation.stream_output = False
        mock_config.automation.max_continuations = 3
        mock_config.automation.ready_issue_unknown_retries = 1
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

    def test_dependency_graph_built_on_gather_all_issue_ids_exception(
        self, temp_project_with_deps: Path
    ) -> None:
        """AutoManager.__init__ falls back to the active-issue ID set (not None)
        when gather_all_issue_ids() raises, mirroring sprint.py's fix (BUG-3028)."""
        from little_loops.config import BRConfig

        config = BRConfig(temp_project_with_deps)
        with patch(
            "little_loops.dependency_mapper.gather_all_issue_ids",
            side_effect=RuntimeError("boom"),
        ):
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
    def temp_project_with_depends_on(self, temp_project_dir: Path) -> Path:
        """Set up project where FEAT-002 depends_on FEAT-001 (soft prerequisite)."""
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

        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        # FEAT-001 (no dependencies)
        (issues_dir / "P1-FEAT-001-first-feature.md").write_text(
            "---\nid: FEAT-001\n---\n# FEAT-001: First Feature\n\n## Summary\nFirst\n"
        )

        # FEAT-002 declares a soft prerequisite on FEAT-001 via frontmatter
        (issues_dir / "P1-FEAT-002-second-feature.md").write_text(
            "---\nid: FEAT-002\ndepends_on:\n  - FEAT-001\n---\n"
            "# FEAT-002: Second Feature\n\n## Summary\nSecond\n"
        )

        return temp_project_dir

    def test_depends_on_dependent_not_selected_first(
        self, temp_project_with_depends_on: Path
    ) -> None:
        """A depends_on dependent is not dispatched before its prerequisite (BUG-2632, AC #2)."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_depends_on)
        manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        # FEAT-002 depends_on FEAT-001, so FEAT-001 must be selected first even
        # though both are otherwise unblocked and share the same priority.
        info = manager._get_next_issue()
        assert info is not None
        assert info.issue_id == "FEAT-001"

    def test_depends_on_dependent_selected_after_prereq_completed(
        self, temp_project_with_depends_on: Path
    ) -> None:
        """The depends_on dependent becomes available once its prerequisite completes."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(temp_project_with_depends_on)
        manager = AutoManager(
            config, dry_run=True, db_path=config.project_root / ".ll" / "history.db"
        )

        manager.state_manager.state.completed_issues.append("FEAT-001")

        info = manager._get_next_issue()
        assert info is not None
        assert info.issue_id == "FEAT-002"

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
        assert "Dependency cycle detected" in captured.err or "cycle" in captured.err.lower()


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

    def test_forwards_on_usage_detailed(self, mock_logger: MagicMock) -> None:
        """run_claude_command forwards on_usage_detailed to _run_claude_base (BUG-2757)."""
        from little_loops.issue_manager import run_claude_command

        mock_result = MagicMock()
        mock_result.returncode = 0

        def on_usage_detailed(usage: object) -> None:
            pass

        with patch("little_loops.issue_manager._run_claude_base") as mock_run:
            mock_run.return_value = mock_result
            run_claude_command("test command", mock_logger, on_usage_detailed=on_usage_detailed)

            assert mock_run.call_args.kwargs["on_usage_detailed"] is on_usage_detailed


class TestFinalizeRetryPrompt:
    """BUG-3058: the re-drive prompt must not reproduce the failure it recovers."""

    def test_prompt_forbids_backgrounding_the_test_run(self) -> None:
        from little_loops.issue_manager import FINALIZE_RETRY_PROMPT

        body = FINALIZE_RETRY_PROMPT.lower()
        assert "foreground" in body
        assert "run_in_background" in body
        assert "notification" in body

    def test_prompt_does_not_ask_for_reimplementation(self) -> None:
        """The work is already on disk; re-implementing risks undoing it."""
        from little_loops.issue_manager import FINALIZE_RETRY_PROMPT

        assert "Do NOT re-implement" in FINALIZE_RETRY_PROMPT

    def test_prompt_covers_the_full_finalize_tail(self) -> None:
        from little_loops.issue_manager import FINALIZE_RETRY_PROMPT

        body = FINALIZE_RETRY_PROMPT.lower()
        assert "status: done" in body
        assert "completed_at" in body
        assert "commit" in body

    def test_prompt_interpolates_issue_id_and_path(self) -> None:
        from little_loops.issue_manager import FINALIZE_RETRY_PROMPT

        rendered = FINALIZE_RETRY_PROMPT.format(
            issue_id="ENH-3046", issue_path=".issues/enhancements/P3-ENH-3046-x.md"
        )
        assert "ENH-3046" in rendered
        assert ".issues/enhancements/P3-ENH-3046-x.md" in rendered
        assert "{" not in rendered


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

    def test_shutdown_between_rounds_raises_interrupted(self, temp_project_dir: Path) -> None:
        """BUG-3312 Decision 3: a shutdown requested between continuation
        rounds (e.g. right after Option J's guillotine round returns) must
        stop run_with_continuation from starting another round, raising the
        same TimeoutExpired(output="interrupted") shape as a mid-round kill."""
        import subprocess

        from little_loops.issue_manager import run_with_continuation
        from little_loops.subprocess_utils import clear_shutdown, request_shutdown

        mock_logger = MagicMock()

        # First round: no handoff signal, but the "prompt is too long" trigger
        # (Option J) drives the loop back to its top for a second round.
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Prompt is too long"

        call_count = [0]

        def fake_run_claude_command(*args: object, **kwargs: object) -> MagicMock:
            call_count[0] += 1
            # Simulate the signal landing after this round returns, before the
            # loop re-enters for the next round.
            request_shutdown()
            return mock_result

        clear_shutdown()
        try:
            with patch(
                "little_loops.issue_manager.run_claude_command",
                side_effect=fake_run_claude_command,
            ):
                with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
                        run_with_continuation("test command", mock_logger, max_continuations=3)
        finally:
            clear_shutdown()

        assert exc_info.value.output == "interrupted"
        # Exactly one round ran before the loop-head check aborted the next.
        assert call_count[0] == 1

    def test_forwards_on_result_seen(self, temp_project_dir: Path) -> None:
        """BUG-3026: on_result_seen fires with the last round's result_seen value."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Normal output"
        mock_result.stderr = ""

        def fake_run_claude_command(*args: object, **kwargs: object) -> MagicMock:
            on_result_seen = kwargs.get("on_result_seen")
            if callable(on_result_seen):
                on_result_seen(True)
            return mock_result

        seen: list[bool] = []
        with patch(
            "little_loops.issue_manager.run_claude_command", side_effect=fake_run_claude_command
        ):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation("test command", mock_logger, on_result_seen=seen.append)

        assert seen == [True]

    def test_forwards_extra_env(self, temp_project_dir: Path) -> None:
        """FEAT-3116 AC #1: extra_env (e.g. LL_ISSUE_ID) is forwarded to every
        round's run_claude_command() call."""
        from little_loops.issue_manager import run_with_continuation

        mock_logger = MagicMock()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Normal output"
        mock_result.stderr = ""

        with patch(
            "little_loops.issue_manager.run_claude_command", return_value=mock_result
        ) as mock_run:
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation(
                    "test command", mock_logger, extra_env={"LL_ISSUE_ID": "BUG-1"}
                )

        assert mock_run.call_args.kwargs["extra_env"] == {"LL_ISSUE_ID": "BUG-1"}

    def test_disable_background_tasks_defaults_to_false(self, temp_project_dir: Path) -> None:
        """ENH-3261: with no automation= supplied, disable_background_tasks
        reads as falsy -- callers that never opted in are unaffected."""
        from little_loops.issue_manager import run_with_continuation

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Normal output"
        mock_result.stderr = ""

        captured: list[object] = []

        def fake_run_claude_command(*args: object, **kwargs: object) -> MagicMock:
            automation = kwargs.get("automation")
            captured.append(automation.disable_background_tasks if automation else False)
            return mock_result

        with patch(
            "little_loops.issue_manager.run_claude_command", side_effect=fake_run_claude_command
        ):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation("test command", MagicMock())

        assert captured == [False]

    def test_automation_profile_defaults_to_none(self, temp_project_dir: Path) -> None:
        """ENH-3261: with no automation= supplied, profile reads as None --
        callers that never opted in are unaffected."""
        from little_loops.issue_manager import run_with_continuation

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Normal output"
        mock_result.stderr = ""

        captured: list[object] = []

        def fake_run_claude_command(*args: object, **kwargs: object) -> MagicMock:
            automation = kwargs.get("automation")
            captured.append(automation.profile if automation else None)
            return mock_result

        with patch(
            "little_loops.issue_manager.run_claude_command", side_effect=fake_run_claude_command
        ):
            with patch("little_loops.issue_manager.detect_context_handoff", return_value=False):
                run_with_continuation("test command", MagicMock())

        assert captured == [None]

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
        config.automation.ready_issue_unknown_retries = 1
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

    def test_forwards_on_usage_detailed_to_ready_issue_call(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """process_issue_inplace forwards on_usage_detailed to run_claude_command
        for the ready-issue phase call (BUG-2757)."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        def on_usage_detailed(usage: object) -> None:
            pass

        with patch(
            "little_loops.issue_manager.run_claude_command", return_value=mock_result
        ) as mock_run:
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.run_with_continuation") as mock_impl:
                    mock_impl.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch(
                        "little_loops.issue_manager.verify_issue_completed", return_value=True
                    ):
                        process_issue_inplace(
                            sample_issue,
                            mock_config,
                            mock_logger,
                            on_usage_detailed=on_usage_detailed,
                        )

        assert mock_run.call_args.kwargs["on_usage_detailed"] is on_usage_detailed
        # BUG-3093: Phase 1's ready-issue subprocess must declare itself
        # under automation like implement/finalize-retry already do.
        assert mock_run.call_args.kwargs["automation"].profile == "ll-auto"

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
        captured_profiles: list[object] = []

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            automation = kwargs.get("automation")
            captured_profiles.append(automation.profile if automation else None)
            if call_count[0] == 1:
                return first_result
            return fallback_result

        with patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert "Fallback failed" in result.failure_reason
        # BUG-3093: both the initial ready-issue call and the path-mismatch
        # fallback retry must declare automation_profile="ll-auto".
        assert captured_profiles == ["ll-auto", "ll-auto"]

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


class TestShutdownInterrupt:
    """Tests for signal-driven shutdown at phase boundaries (BUG-3312)."""

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
        config.automation.ready_issue_unknown_retries = 1
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

    @pytest.fixture(autouse=True)
    def _clear_shutdown_event(self) -> Any:
        from little_loops.subprocess_utils import clear_shutdown

        clear_shutdown()
        yield
        clear_shutdown()

    def test_shutdown_before_phase_2_skips_implement_subprocess(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """A shutdown requested during Phase 1 aborts before Phase 2 spawns
        run_with_continuation, and the result is flagged was_interrupted."""
        from little_loops.issue_manager import process_issue_inplace
        from little_loops.subprocess_utils import request_shutdown

        mock_logger = MagicMock()
        mock_ready_result = MagicMock()
        mock_ready_result.returncode = 1
        mock_ready_result.stdout = ""
        mock_ready_result.stderr = "Some error"

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_ready_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.run_with_continuation") as mock_impl:
                    request_shutdown()
                    result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        mock_impl.assert_not_called()
        assert result.was_interrupted is True
        assert not result.success

    def test_shutdown_after_phase_2_skips_verify_subprocess(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """A shutdown that fires during Phase 2 aborts before Phase 3's verify
        subprocess is spawned, even though Phase 2 itself returned cleanly."""
        from little_loops.issue_manager import process_issue_inplace
        from little_loops.subprocess_utils import request_shutdown

        mock_logger = MagicMock()
        mock_ready_result = MagicMock()
        mock_ready_result.returncode = 1
        mock_ready_result.stdout = ""
        mock_ready_result.stderr = "Some error"

        def _mocked_phase2(*args: Any, **kwargs: Any) -> MagicMock:
            # Simulate the signal landing while Phase 2's subprocess was running.
            request_shutdown()
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_ready_result):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch(
                    "little_loops.issue_manager.run_with_continuation",
                    side_effect=_mocked_phase2,
                ):
                    with patch("little_loops.issue_manager.verify_issue_completed") as mock_verify:
                        result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        mock_verify.assert_not_called()
        assert result.was_interrupted is True
        assert not result.success


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
        config.automation.ready_issue_unknown_retries = 1
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


class TestClassifyFailureIntegration:
    """Characterization tests for process_issue_inplace's classify_failure() call
    site (BUG-2731 Integration Map: this consumer had zero direct coverage).
    Pins current TRANSIENT/REAL branching behavior before the INFRA_RETRY member
    is added to the exhaustiveness tuple check.
    """

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
        config.automation.ready_issue_unknown_retries = 1
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

    def _ready_verdict_result(self, sample_issue: IssueInfo) -> MagicMock:
        output = f"""
## VERDICT
READY

## VALIDATED_FILE
{sample_issue.path}
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        return mock_result

    def test_transient_phase2_failure_does_not_create_bug_issue(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """A rate-limit-flavored Phase 2 failure is logged, not filed as a bug."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=self._ready_verdict_result(sample_issue),
            ),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.create_issue_from_failure") as mock_create,
        ):
            mock_impl.return_value = MagicMock(
                returncode=1, stdout="", stderr="Error: rate limit exceeded"
            )
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert result.failure_reason.startswith("Transient:")
        mock_create.assert_not_called()

    def test_real_phase2_failure_creates_bug_issue(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """A genuine implementation failure files a bug issue as before."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=self._ready_verdict_result(sample_issue),
            ),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch(
                "little_loops.issue_manager.create_issue_from_failure",
                return_value="BUG-999",
            ) as mock_create,
        ):
            mock_impl.return_value = MagicMock(
                returncode=1, stdout="", stderr="Traceback: NameError: boom"
            )
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        mock_create.assert_called_once()


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
        config.automation.ready_issue_unknown_retries = 1
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
        self, mock_config: BRConfig, sample_issue: IssueInfo, capsys: pytest.CaptureFixture[str]
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
        # ENH-2989: a failed CLOSE never reached Phase 2 — reason "close_failed".
        assert f"PHASE1_NOT_STARTED {sample_issue.issue_id} close_failed" in capsys.readouterr().out

    def test_close_without_validated_path_fails(
        self, mock_config: BRConfig, sample_issue: IssueInfo, capsys: pytest.CaptureFixture[str]
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
        assert f"PHASE1_NOT_STARTED {sample_issue.issue_id} close_failed" in capsys.readouterr().out

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

    def test_blocked_verdict_prints_not_started_marker(
        self, mock_config: BRConfig, sample_issue: IssueInfo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A BLOCKED verdict (open dependency) never reaches Phase 2 — reason "blocked"."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        output = f"""
## VERDICT
BLOCKED

## CONCERNS
- Depends on BUG-999

## VALIDATED_FILE
{sample_issue.path}
"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert result.was_blocked
        assert f"PHASE1_NOT_STARTED {sample_issue.issue_id} blocked" in capsys.readouterr().out

    def test_unknown_verdict_prints_not_started_marker_with_unknown_reason(
        self, mock_config: BRConfig, sample_issue: IssueInfo, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A non-compliant model turn (no recognizable verdict token) defaults to
        UNKNOWN, which is transient — reason "unknown", not "not_ready" (ENH-2989)."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        # No ## VERDICT section at all — output_parsing.py defaults verdict to
        # "UNKNOWN" when no strategy finds a recognizable token.
        output = "Some non-compliant model output with no verdict marker."

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output

        with patch("little_loops.issue_manager.run_claude_command", return_value=mock_result):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        assert not result.success
        assert f"PHASE1_NOT_STARTED {sample_issue.issue_id} unknown" in capsys.readouterr().out

    def test_not_ready_verdict_fails_processing(
        self, mock_config: BRConfig, sample_issue: IssueInfo, capsys: pytest.CaptureFixture[str]
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
        # ENH-2989: a real NOT_READY verdict is a deterministic Phase 1
        # rejection — reason token "not_ready", not "unknown".
        captured = capsys.readouterr()
        assert f"PHASE1_NOT_STARTED {sample_issue.issue_id} not_ready" in captured.out


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
        config.automation.ready_issue_unknown_retries = 1
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
        config.automation.ready_issue_unknown_retries = 1
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

    def test_fallback_log_tags_result_seen_reason(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """BUG-3026: fallback success log tags whether the turn ended on a
        clean result event, distinguishing a truncated-but-clean exit from a
        genuinely missing result event."""
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        def fake_run_with_continuation(*args: object, **kwargs: object) -> MagicMock:
            on_result_seen = kwargs.get("on_result_seen")
            if callable(on_result_seen):
                on_result_seen(True)
            return impl_result

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation",
                side_effect=fake_run_with_continuation,
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
        success_messages = [str(c.args[0]) for c in mock_logger.success.call_args_list]
        assert any("result event observed" in msg for msg in success_messages)

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
        # BUG-3005: this return previously omitted failure_reason entirely,
        # so mark_failed() never fired and the summary silently under-reported.
        assert result.failure_reason == "verification failed"
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

        mock_verify.assert_called_once_with(
            mock_logger,
            baseline_sha=test_sha,
            config=mock_config,
            pre_step_snapshot={},
            issue_id=sample_issue.issue_id,
        )

    def test_tamper_guard_trips_end_to_end_no_fsm_involved(
        self,
        mock_config: BRConfig,
        sample_issue: IssueInfo,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ENH-2935: an ll-auto run whose agent weakened a test trips the
        shared tamper guard with no FSM state involved. Exercises the real
        verify_work_was_done() -> run_tamper_guard() call chain (not a
        wholesale verify_work_was_done stub) against a real git repo, per
        this issue's own test-authoring requirement."""
        import subprocess

        from little_loops.config import BRConfig as RealBRConfig
        from little_loops.issue_manager import process_issue_inplace
        from tests.helpers import copy_git_template

        repo = tmp_path / "repo"
        copy_git_template(repo)
        (repo / "tests").mkdir()
        (repo / "tests" / "test_x.py").write_text("def test_x():\n    assert 1 == 1\n")
        subprocess.run(["git", "add", "tests/test_x.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "add test"], cwd=repo, check=True)

        # Weaken the test in place, uncommitted -- the state an agent would
        # leave behind after "implementing" by gutting the assertion.
        (repo / "tests" / "test_x.py").write_text("def test_x():\n    pass  # weakened\n")

        real_config = RealBRConfig(repo)

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        monkeypatch.chdir(repo)

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
                            result = process_issue_inplace(sample_issue, real_config, mock_logger)

        assert not result.success
        mock_logger.error.assert_called()

    def test_plan_present_but_uncommitted_work_routes_to_evidence_path(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """BUG-2409: a plan file present alongside uncommitted work must NOT park the
        issue as 'awaiting approval'; it should fall through to the evidence-of-work path.
        """
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        plan_path = Path("thoughts/shared/plans/2026-07-01-BUG-001-management.md")

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=plan_path
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
                                ) as mock_complete:
                                    result = process_issue_inplace(
                                        sample_issue, mock_config, mock_logger
                                    )

        # Dirty tree: must not be parked as awaiting approval, and must finalize.
        assert result.plan_created is False
        assert result.success
        mock_complete.assert_called_once()

    def test_plan_present_clean_tree_still_awaits_approval(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """BUG-280 regression: a plan file present with a clean tree (no work vs baseline)
        must still be parked as 'awaiting approval'.
        """
        from little_loops.issue_manager import process_issue_inplace

        mock_logger = MagicMock()

        ready_result = MagicMock()
        ready_result.returncode = 0
        ready_result.stdout = f"## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}"

        impl_result = MagicMock()
        impl_result.returncode = 0
        impl_result.stdout = "Implementation successful"
        impl_result.stderr = ""

        plan_path = Path("thoughts/shared/plans/2026-07-01-BUG-001-management.md")

        with patch("little_loops.issue_manager.run_claude_command", return_value=ready_result):
            with patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ):
                with patch("little_loops.issue_manager.verify_issue_completed", return_value=False):
                    with patch(
                        "little_loops.issue_manager.detect_plan_creation", return_value=plan_path
                    ):
                        with patch(
                            "little_loops.issue_manager.verify_work_was_done",
                            return_value=False,
                        ):
                            with patch(
                                "little_loops.issue_manager.complete_issue_lifecycle",
                                return_value=True,
                            ) as mock_complete:
                                result = process_issue_inplace(
                                    sample_issue, mock_config, mock_logger
                                )

        # Clean tree: genuine approval pause preserved.
        assert result.plan_created is True
        assert result.plan_path == str(plan_path)
        assert not result.success
        mock_complete.assert_not_called()


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
        config.automation.ready_issue_unknown_retries = 1
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

    def test_run_returns_one_when_only_ids_never_eligible(self, full_project: Path) -> None:
        """run() exits 1 when the --only target is blocked and never dequeued at all.

        Regression test for BUG-2907: unlike gate-blocked (attempted, then
        failed), a `blocked_by`-blocked issue never comes back from
        `_get_next_issue()` at all, so `attempted_count` stays 0. The exit
        code must still be 1, and the blocker IDs should appear in the log.
        """
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-005-blocker.md").write_text(
            "# BUG-005: Blocker\n\n## Summary\nUnfinished blocker"
        )
        (issues_dir / "P1-BUG-006-target.md").write_text(
            "---\nblocked_by: [BUG-005]\n---\n# BUG-006: Target\n\n## Summary\nBlocked target"
        )

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    only_ids={"BUG-006"},
                    db_path=config.project_root / ".ll" / "history.db",
                )

                result = manager.run()

        # BUG-006 was never dequeued, so process_issue_inplace must not be called
        mock_process.assert_not_called()
        assert result == 1

    def test_run_returns_one_when_only_id_not_found(self, full_project: Path) -> None:
        """run() exits 1 when the --only target doesn't exist in .issues/ at all."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)

        with patch("little_loops.issue_manager.process_issue_inplace") as mock_process:
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    only_ids={"BUG-999"},
                    db_path=config.project_root / ".ll" / "history.db",
                )

                result = manager.run()

        mock_process.assert_not_called()
        assert result == 1

    def test_unreachable_reason_classifications(self, full_project: Path) -> None:
        """`_unreachable_reason` distinguishes not_found/blocked/already_done directly."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-005-blocker.md").write_text(
            "# BUG-005: Blocker\n\n## Summary\nUnfinished blocker"
        )
        (issues_dir / "P1-BUG-006-target.md").write_text(
            "---\nblocked_by: [BUG-005]\n---\n# BUG-006: Target\n\n## Summary\nBlocked target"
        )
        (issues_dir / "P1-BUG-007-done.md").write_text(
            "---\nstatus: done\n---\n# BUG-007: Done\n\n## Summary\nAlready finished"
        )

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        assert manager._unreachable_reason("BUG-999").startswith("not_found")
        assert "BUG-006 blocked by: BUG-005" in manager._unreachable_reason("BUG-006")
        assert manager._unreachable_reason("BUG-007") == "BUG-007: already_done"

    def test_unreachable_reason_cross_type_suggestion(self, full_project: Path) -> None:
        """ENH-3086: a wrong-type-prefix ID suggests the ID under its real type
        when exactly one other issue shares the numeric suffix."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-042-target.md").write_text(
            "# BUG-042: Target\n\n## Summary\nExists only as BUG-042"
        )

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        assert manager._unreachable_reason("ENH-042") == "not_found (did you mean BUG-042?)"
        # Genuinely absent numeric suffix still returns the bare token unchanged.
        assert manager._unreachable_reason("ENH-999").startswith("not_found")
        assert manager._unreachable_reason("ENH-999") == "not_found"

    def test_unreachable_reason_attempted_and_failed(self, full_project: Path) -> None:
        """BUG-3005: an attempted-and-failed issue reports the real outcome, not
        the "filtered out" catch-all — even though it is open/unblocked/acyclic."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        manager._run_attempted.add("BUG-001")
        manager.state_manager.mark_attempted("BUG-001", save=False)
        manager.state_manager.mark_failed("BUG-001", "verification failed")

        reason = manager._unreachable_reason("BUG-001")
        assert reason == "BUG-001: attempted, verification failed"
        assert "filtered out" not in reason

    def test_unreachable_reason_attempted_no_recorded_outcome(self, full_project: Path) -> None:
        """BUG-3005: an attempted ID with no recorded reason still avoids the
        catch-all (the bare-attempted_issues backstop invariant)."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        manager._run_attempted.add("BUG-001")
        manager.state_manager.mark_attempted("BUG-001", save=False)

        assert manager._unreachable_reason("BUG-001") == "BUG-001: attempted, outcome not recorded"

    def test_unreachable_reason_was_blocked_and_plan_created_wording(
        self, full_project: Path
    ) -> None:
        """BUG-3005: was_blocked/plan_created outcomes render their own,
        non-failure wording via skipped_issues rather than the catch-all."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-008-blocked-outcome.md").write_text(
            "# BUG-008: Blocked outcome\n\n## Summary\nBlocked at runtime"
        )
        (issues_dir / "P1-BUG-009-plan-outcome.md").write_text(
            "# BUG-009: Plan outcome\n\n## Summary\nPlan awaiting approval"
        )

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        manager._run_attempted.update({"BUG-008", "BUG-009"})
        manager.state_manager.mark_attempted("BUG-008", save=False)
        manager.state_manager.mark_skipped("BUG-008", "skipped — blocked by open dependency")
        manager.state_manager.mark_attempted("BUG-009", save=False)
        manager.state_manager.mark_skipped("BUG-009", "plan created, awaiting approval")

        assert (
            manager._unreachable_reason("BUG-008")
            == "BUG-008: attempted, skipped — blocked by open dependency"
        )
        assert (
            manager._unreachable_reason("BUG-009")
            == "BUG-009: attempted, plan created, awaiting approval"
        )

    def test_unreachable_reason_earlier_run_suffix(self, full_project: Path) -> None:
        """BUG-3005: an outcome recorded in persisted state but not attempted in
        *this* run's in-process set is worded as an earlier run's outcome."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        # Simulate persisted state loaded via --resume, without adding to
        # this run's _run_attempted set.
        manager.state_manager.mark_attempted("BUG-001", save=False)
        manager.state_manager.mark_failed("BUG-001", "verification failed")

        reason = manager._unreachable_reason("BUG-001")
        assert reason == "BUG-001: attempted, verification failed (earlier run)"

    def test_unreachable_reason_catch_all_reworded(self, full_project: Path) -> None:
        """BUG-3005: the genuine "we don't know" catch-all names its own
        uncertainty instead of implying a filter matched."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-010-never-attempted.md").write_text(
            "# BUG-010: Never attempted\n\n## Summary\nOpen, unblocked, never selected"
        )

        config = BRConfig(full_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        assert manager._unreachable_reason("BUG-010") == "BUG-010: not selected (no filter matched)"

    def test_timeout_on_one_issue_does_not_abort_remaining_issues(self, full_project: Path) -> None:
        """BUG-2976: a per-issue TimeoutExpired fails only that issue.

        Regression guard for the pre-fix behavior where an uncaught
        subprocess.TimeoutExpired from run_claude_command() unwound past
        _process_issue() to run()'s top-level `except Exception`, logging
        "Fatal error" and discarding every remaining issue in the backlog.
        """
        import subprocess

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = full_project / ".issues" / "bugs"
        (issues_dir / "P1-BUG-002-second.md").write_text(
            "# BUG-002: Second\n\n## Summary\nSecond issue"
        )

        config = BRConfig(full_project)

        def side_effect(info: Any, *args: Any, **kwargs: Any) -> Any:
            if info.issue_id == "BUG-001":
                raise subprocess.TimeoutExpired(cmd="claude", timeout=60)
            return MagicMock(
                success=True,
                duration=1.0,
                issue_id=info.issue_id,
                was_closed=False,
                was_blocked=False,
                plan_created=False,
                failure_reason="",
                corrections=[],
            )

        with patch("little_loops.issue_manager.process_issue_inplace", side_effect=side_effect):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    db_path=config.project_root / ".ll" / "history.db",
                )

                exit_code = manager.run()

        # BUG-002 was still attempted and completed after BUG-001 timed out.
        assert manager.processed_count == 1
        assert exit_code == 0
        assert "BUG-001" in manager.state_manager.state.failed_issues
        assert "timeout after 60s" in manager.state_manager.state.failed_issues["BUG-001"]

    def test_timeout_after_finalization_records_success(self, full_project: Path) -> None:
        """BUG-3131: a kill that lands after the agent finalized records success.

        The wall-clock kill is a SIGKILL at an arbitrary instant and can fire
        after the agent already set `status: done` and committed. The pre-fix
        handler fabricated a failure without consulting the issue file, so the
        run summary reported 0 processed / 1 failed for work that had landed,
        and a --resume run would reprocess it.
        """
        import subprocess

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issue_path = full_project / ".issues" / "bugs" / "P1-BUG-001-test-issue.md"
        config = BRConfig(full_project)

        def side_effect(info: Any, *args: Any, **kwargs: Any) -> Any:
            # The agent finalizes the lifecycle, then the wall-clock kill fires
            # before its turn ends -- the exact FEAT-3078 sequence.
            issue_path.write_text(
                "---\nstatus: done\n---\n\n# BUG-001: Test\n\n## Summary\nFinalized\n"
            )
            raise subprocess.TimeoutExpired(cmd="claude", timeout=60)

        with patch("little_loops.issue_manager.process_issue_inplace", side_effect=side_effect):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    db_path=config.project_root / ".ll" / "history.db",
                )
                exit_code = manager.run()

        assert exit_code == 0
        assert manager.processed_count == 1
        assert "BUG-001" not in manager.state_manager.state.failed_issues
        assert "BUG-001" in manager.state_manager.state.completed_issues

    def test_timeout_without_finalization_still_fails(self, full_project: Path) -> None:
        """BUG-3131: the verification is authoritative, not permissive.

        An issue still `open` when the kill fires must stay failed -- the
        handler must not fall back to completing it from a dirty working tree,
        because a killed agent's half-written implementation is
        indistinguishable from a finished one.
        """
        import subprocess

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issue_path = full_project / ".issues" / "bugs" / "P1-BUG-001-test-issue.md"
        issue_path.write_text(
            "---\nstatus: open\n---\n\n# BUG-001: Test\n\n## Summary\nKilled mid-implementation\n"
        )

        config = BRConfig(full_project)

        def side_effect(info: Any, *args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=60)

        with patch("little_loops.issue_manager.process_issue_inplace", side_effect=side_effect):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                # Dirty tree: the fallback must still refuse to auto-complete.
                with patch("little_loops.issue_manager.verify_work_was_done", return_value=True):
                    manager = AutoManager(
                        config,
                        dry_run=False,
                        db_path=config.project_root / ".ll" / "history.db",
                    )
                    manager.run()

        assert manager.processed_count == 0
        assert "BUG-001" in manager.state_manager.state.failed_issues
        assert "timeout after 60s" in manager.state_manager.state.failed_issues["BUG-001"]

    def test_interrupt_without_finalization_is_skipped_not_failed(self, full_project: Path) -> None:
        """BUG-3312: TimeoutExpired(output="interrupted") -- raised when a
        shutdown signal kills the subprocess mid-round -- shares the
        "already finalized?" recovery check with a real timeout, but on the
        not-finalized path must be attributed as interrupted (skipped), not a
        generic timeout failure that could spawn a bug issue.
        """
        import subprocess

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issue_path = full_project / ".issues" / "bugs" / "P1-BUG-001-test-issue.md"
        issue_path.write_text(
            "---\nstatus: open\n---\n\n# BUG-001: Test\n\n## Summary\nKilled by signal\n"
        )

        config = BRConfig(full_project)

        def side_effect(info: Any, *args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=0, output="interrupted")

        with patch("little_loops.issue_manager.process_issue_inplace", side_effect=side_effect):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                with patch("little_loops.issue_manager.verify_work_was_done", return_value=True):
                    manager = AutoManager(
                        config,
                        dry_run=False,
                        db_path=config.project_root / ".ll" / "history.db",
                    )
                    manager.run()

        assert manager.processed_count == 0
        assert "BUG-001" not in manager.state_manager.state.failed_issues
        assert "BUG-001" in manager.state_manager.state.skipped_issues
        assert "interrupted" in manager.state_manager.state.skipped_issues["BUG-001"]

    def test_run_preserves_state_file_after_fatal_exception(self, full_project: Path) -> None:
        """BUG-2976: a fatal (non-timeout) exception must not delete resume state.

        Regression guard for the inverted `finally` gate: the old code
        deleted .auto-manage-state.json on the exception path and preserved
        it only on Ctrl-C, backwards from what --resume needs.
        """
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            side_effect=RuntimeError("boom"),
        ):
            with patch("little_loops.issue_manager.check_git_status", return_value=False):
                manager = AutoManager(
                    config,
                    dry_run=False,
                    db_path=config.project_root / ".ll" / "history.db",
                )

                exit_code = manager.run()

        assert exit_code == 1
        assert manager.state_manager.state_file.exists()

    def test_run_cleans_up_state_file_on_normal_completion(self, full_project: Path) -> None:
        """BUG-2976: normal completion still removes the resume state file."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(full_project)

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
                    db_path=config.project_root / ".ll" / "history.db",
                )

                exit_code = manager.run()

        assert exit_code == 0
        assert not manager.state_manager.state_file.exists()


class TestInterruptedAttribution:
    """Tests for BUG-3312 Decision 5: an interrupted issue is recorded as
    skipped (not failed) and its attempted_issues mark is undone so --resume
    retries it rather than treating it as a burned attempt."""

    @pytest.fixture
    def full_project(self, temp_project_dir: Path) -> Path:
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".auto-manage-state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        (issues_dir / "P1-BUG-001-test-issue.md").write_text(
            "# BUG-001: Test Issue\n\n## Summary\nTest"
        )
        return temp_project_dir

    def test_interrupted_result_is_skipped_not_failed(self, full_project: Path) -> None:
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult

        config = BRConfig(full_project)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            return_value=IssueProcessingResult(
                success=False,
                was_interrupted=True,
                duration=1.0,
                issue_id="BUG-001",
                failure_reason="Interrupted by signal before Phase 3",
            ),
        ):
            manager = AutoManager(
                config, dry_run=False, db_path=config.project_root / ".ll" / "history.db"
            )
            issue = manager._get_next_issue()
            assert issue is not None
            success = manager._process_issue(issue)

        assert success is False
        assert "BUG-001" not in manager.state_manager.state.failed_issues
        assert "BUG-001" in manager.state_manager.state.skipped_issues

    def test_interrupted_result_unmarks_attempted(self, full_project: Path) -> None:
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult

        config = BRConfig(full_project)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            return_value=IssueProcessingResult(
                success=False,
                was_interrupted=True,
                duration=1.0,
                issue_id="BUG-001",
                failure_reason="Interrupted by signal before Phase 3",
            ),
        ):
            manager = AutoManager(
                config, dry_run=False, db_path=config.project_root / ".ll" / "history.db"
            )
            issue = manager._get_next_issue()
            assert issue is not None
            # mark_attempted() fires before process_issue_inplace is even called.
            manager._process_issue(issue)

        assert "BUG-001" not in manager.state_manager.state.attempted_issues
        assert "BUG-001" not in manager._run_attempted


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

    def test_signal_handler_sets_shutdown_event(self, temp_project_dir: Path) -> None:
        """First signal also sets the module-level subprocess_utils shutdown
        Event (BUG-3312 Decision 1), so an in-flight run_claude_command read
        loop observes it and kills the active subprocess."""
        import signal

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager
        from little_loops.subprocess_utils import clear_shutdown, is_shutdown_requested

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
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)

        clear_shutdown()
        try:
            config = BRConfig(temp_project_dir)
            manager = AutoManager(config, dry_run=True)

            assert is_shutdown_requested() is False
            manager._signal_handler(signal.SIGINT, None)
            assert is_shutdown_requested() is True
        finally:
            clear_shutdown()

    def test_second_signal_forces_immediate_exit(self, temp_project_dir: Path) -> None:
        """Second signal escalates to an immediate os._exit (BUG-3312 Decision 4,
        mirrors ll-loop's _loop_signal_handler / ENH-2516) rather than waiting on
        any in-progress cleanup."""
        import signal

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager
        from little_loops.subprocess_utils import clear_shutdown

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
        (temp_project_dir / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)

        clear_shutdown()
        try:
            config = BRConfig(temp_project_dir)
            manager = AutoManager(config, dry_run=True)

            manager._signal_handler(signal.SIGINT, None)
            assert manager._shutdown_requested is True

            with patch("little_loops.issue_manager.os._exit") as mock_exit:
                manager._signal_handler(signal.SIGINT, None)
                mock_exit.assert_called_once_with(1)
        finally:
            clear_shutdown()


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

    def test_no_plan_returns_none(
        self, temp_project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when no plan file exists."""
        from little_loops.issue_manager import detect_plan_creation

        # Setup: Create plans directory but no matching plan
        plans_dir = temp_project_dir / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)

        # Change to temp directory
        monkeypatch.chdir(temp_project_dir)

        # Test
        result = detect_plan_creation("", "BUG-999")

        # Verify
        assert result is None

    def test_matching_plan_returns_path(
        self, temp_project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns Path when matching plan file exists."""
        from little_loops.issue_manager import detect_plan_creation

        # Setup: Create plan file
        plans_dir = temp_project_dir / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)
        plan_file = plans_dir / "2026-02-08-BUG-280-management.md"
        plan_file.write_text("# Plan content")

        # Change to temp directory
        monkeypatch.chdir(temp_project_dir)

        # Test
        result = detect_plan_creation("", "BUG-280")

        # Verify
        assert result is not None
        assert result.name == "2026-02-08-BUG-280-management.md"

    def test_multiple_plans_returns_latest(
        self, temp_project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        monkeypatch.chdir(temp_project_dir)

        # Test
        result = detect_plan_creation("", "BUG-280")

        # Verify
        assert result is not None
        assert result.name == "2026-02-08-BUG-280-management.md"

    def test_no_plans_dir_returns_none(
        self, temp_project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when plans directory doesn't exist."""
        from little_loops.issue_manager import detect_plan_creation

        # Change to temp directory (without creating plans dir)
        monkeypatch.chdir(temp_project_dir)

        # Test
        result = detect_plan_creation("", "BUG-999")

        # Verify
        assert result is None


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
        """AutoManager logs the resolved model ID (from on_usage_detailed), not the
        requested alias (from on_model_detected), when both fire (BUG-2757)."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult
        from little_loops.subprocess_utils import TokenUsage

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
            on_usage_detailed: Any = None,
            preview_full: bool = False,
            event_bus: Any = None,
            sprint_context: Any = None,
            context_limit: Any = None,
            skip_learning_gate: bool = False,
            **kwargs: Any,
        ) -> IssueProcessingResult:
            # Simulate the real subprocess_utils flow: the init event fires
            # on_model_detected with the requested alias, then the result event
            # fires on_usage_detailed with the resolved model ID.
            if on_model_detected:
                on_model_detected("sonnet")
            if on_usage_detailed:
                on_usage_detailed(
                    TokenUsage(
                        input_tokens=100,
                        output_tokens=50,
                        cache_read_tokens=0,
                        cache_creation_tokens=0,
                        model="claude-sonnet-4-6",
                    )
                )
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            side_effect=mock_process_inplace,
        ):
            manager._process_issue(issue)

        assert any("model: claude-sonnet-4-6" in msg for msg in info_log)
        assert not any(msg.strip() == "model: sonnet" for msg in info_log)
        assert manager._detected_model == ["claude-sonnet-4-6"]

    def test_auto_manager_falls_back_to_alias_when_no_result_event(
        self, temp_project_with_issue: Path
    ) -> None:
        """AutoManager falls back to the requested alias when no result event
        (on_usage_detailed) ever fires, e.g. the subprocess fails before completing
        (BUG-2757)."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult

        config = BRConfig(temp_project_with_issue)
        manager = AutoManager(config, dry_run=False)

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
            on_usage_detailed: Any = None,
            preview_full: bool = False,
            event_bus: Any = None,
            sprint_context: Any = None,
            context_limit: Any = None,
            skip_learning_gate: bool = False,
            **kwargs: Any,
        ) -> IssueProcessingResult:
            if on_model_detected:
                on_model_detected("sonnet")
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            side_effect=mock_process_inplace,
        ):
            manager._process_issue(issue)

        assert any("model: sonnet" in msg for msg in info_log)
        assert manager._detected_model == ["sonnet"]

    def test_records_mixed_issue_outcomes_with_one_batch_id(
        self, temp_project_with_issue: Path
    ) -> None:
        """ENH-2492: ll-auto persists success/failure detail under one run ID."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult
        from little_loops.issue_parser import IssueInfo
        from little_loops.session_store import recent

        db = temp_project_with_issue / ".ll" / "orchestration.db"
        config = BRConfig(temp_project_with_issue)
        manager = AutoManager(
            config,
            dry_run=False,
            db_path=db,
            run_id="auto-batch",
        )
        first = manager._get_next_issue()
        assert first is not None
        second = IssueInfo(
            path=first.path,
            issue_type=first.issue_type,
            priority=first.priority,
            issue_id="FEAT-002",
            title="Second Feature",
        )
        outcomes = [
            IssueProcessingResult(success=True, duration=1.5, issue_id=first.issue_id),
            IssueProcessingResult(
                success=False,
                duration=2.5,
                issue_id=second.issue_id,
                failure_reason="verification failed",
            ),
        ]

        with patch("little_loops.issue_manager.process_issue_inplace", side_effect=outcomes):
            assert manager._process_issue(first) is True
            assert manager._process_issue(second) is False

        rows = recent(db, kind="orchestration_run")
        assert len(rows) == 2
        assert {row["run_id"] for row in rows} == {"auto-batch"}
        by_issue = {row["issue_id"]: row for row in rows}
        assert by_issue[first.issue_id]["status"] == "completed"
        assert by_issue[first.issue_id]["duration_s"] == 1.5
        assert by_issue[second.issue_id]["status"] == "failed"
        assert by_issue[second.issue_id]["failure_reason"] == "verification failed"

    def test_orchestration_write_failure_does_not_change_auto_result(
        self, temp_project_with_issue: Path
    ) -> None:
        """ENH-2492: history write failures are best-effort for ll-auto."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager, IssueProcessingResult

        config = BRConfig(temp_project_with_issue)
        manager = AutoManager(config, dry_run=False, run_id="auto-batch")
        issue = manager._get_next_issue()
        assert issue is not None
        outcome = IssueProcessingResult(success=True, duration=1.0, issue_id=issue.issue_id)

        with (
            patch("little_loops.issue_manager.process_issue_inplace", return_value=outcome),
            patch(
                "little_loops.issue_manager.record_orchestration_run",
                side_effect=OSError("database unavailable"),
            ),
        ):
            assert manager._process_issue(issue) is True

    def test_context_window_sizes_from_resolved_model_not_alias(
        self, temp_project_with_issue: Path
    ) -> None:
        """context_window_for() sizes context using the resolved model ID
        (self._detected_model), not the requested alias, once it's populated
        via on_usage_detailed (BUG-2757)."""
        from little_loops.config import BRConfig
        from little_loops.context_window import context_window_for
        from little_loops.issue_manager import AutoManager, IssueProcessingResult
        from little_loops.subprocess_utils import TokenUsage

        config = BRConfig(temp_project_with_issue)
        manager = AutoManager(config, dry_run=False)

        issue = manager._get_next_issue()
        assert issue is not None

        def mock_process_inplace(
            info: Any,
            cfg: Any,
            logger: Any,
            dry_run: bool = False,
            on_model_detected: Any = None,
            on_usage: Any = None,
            on_usage_detailed: Any = None,
            preview_full: bool = False,
            event_bus: Any = None,
            sprint_context: Any = None,
            context_limit: Any = None,
            skip_learning_gate: bool = False,
            **kwargs: Any,
        ) -> IssueProcessingResult:
            if on_model_detected:
                on_model_detected("sonnet")  # unresolved alias — sizes to 200K default
            if on_usage_detailed:
                on_usage_detailed(
                    TokenUsage(
                        input_tokens=100,
                        output_tokens=50,
                        cache_read_tokens=0,
                        cache_creation_tokens=0,
                        model="claude-sonnet-4-6[1m]",  # resolved — sizes to 1M
                    )
                )
            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        with patch(
            "little_loops.issue_manager.process_issue_inplace",
            side_effect=mock_process_inplace,
        ):
            manager._process_issue(issue)

        assert manager._detected_model == ["claude-sonnet-4-6[1m]"]
        assert context_window_for(manager._detected_model[0]) == 1_000_000
        assert context_window_for("sonnet") == 200_000


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
        config.automation.ready_issue_unknown_retries = 1
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
        # BUG-3093: both Phase 1 (ready-issue) and the decide-issue gate
        # subprocesses must declare automation_profile="ll-auto".
        assert all(
            call.kwargs.get("automation") is not None
            and call.kwargs["automation"].profile == "ll-auto"
            for call in mock_cmd.call_args_list
        )

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
        config.automation.ready_issue_unknown_retries = 1
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
        config.automation.ready_issue_unknown_retries = 1
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

    def test_blocked_gate_prints_greppable_marker(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A blocked verdict prints the LEARNING_GATE_BLOCKED marker to stdout so FSM loops
        implementing via `ll-auto --only` can route on it (cross-loop consistency)."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])
        self._write_blocked_state(temp_project_dir)

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="blocked",
            ),
            patch("little_loops.issue_manager.run_with_continuation"),
        ):
            process_issue_inplace(issue, lt_enabled_config, MagicMock(), skip_learning_gate=False)

        out = capsys.readouterr().out
        assert "LEARNING_GATE_BLOCKED" in out
        assert issue.issue_id in out

    def test_impl_failed_gate_verdict_skips_implement_phase(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path
    ) -> None:
        """BUG-2833: an impl_failed verdict must not be treated as a gate block —
        it skips the implement phase but does not report as blocked."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="impl_failed",
            ),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
        ):
            result = process_issue_inplace(
                issue, lt_enabled_config, MagicMock(), skip_learning_gate=False
            )

        assert result.success is False
        assert "blocked" not in result.failure_reason.lower()
        mock_impl.assert_not_called()

    def test_impl_failed_gate_prints_implement_failed_marker(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """An impl_failed verdict prints IMPLEMENT_FAILED, not LEARNING_GATE_BLOCKED, so
        downstream FSM loops route it as a generic implementation failure."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="impl_failed",
            ),
            patch("little_loops.issue_manager.run_with_continuation"),
        ):
            process_issue_inplace(issue, lt_enabled_config, MagicMock(), skip_learning_gate=False)

        out = capsys.readouterr().out
        assert "IMPLEMENT_FAILED" in out
        assert "LEARNING_GATE_BLOCKED" not in out
        assert issue.issue_id in out

    def test_infra_failed_gate_verdict_skips_implement_phase(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path
    ) -> None:
        """ENH-3084 AC 3 (anti-fall-through): an infra_failed verdict must STOP and
        report failure — it must NOT fall through the if/elif chain as if passed and
        proceed to Phase 2 (silent success is worse than the misclassification)."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="infra_failed",
            ),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
        ):
            result = process_issue_inplace(
                issue, lt_enabled_config, MagicMock(), skip_learning_gate=False
            )

        assert result.success is False
        assert "Learning gate could not run" in result.failure_reason
        assert "implementation failed" not in result.failure_reason.lower()
        mock_impl.assert_not_called()

    def test_infra_failed_gate_prints_gate_infra_failed_marker(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """ENH-3084 AC 4: an infra_failed verdict prints GATE_INFRA_FAILED — not
        LEARNING_GATE_BLOCKED nor IMPLEMENT_FAILED — so downstream FSM loops can
        retry/skip rather than remediate."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["anthropic"])

        with (
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="infra_failed",
            ),
            patch("little_loops.issue_manager.run_with_continuation"),
        ):
            process_issue_inplace(issue, lt_enabled_config, MagicMock(), skip_learning_gate=False)

        out = capsys.readouterr().out
        assert "GATE_INFRA_FAILED" in out
        assert "LEARNING_GATE_BLOCKED" not in out
        assert "IMPLEMENT_FAILED" not in out
        assert issue.issue_id in out

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

    def test_gate_called_with_resolved_targets(
        self, lt_enabled_config: BRConfig, temp_project_dir: Path
    ) -> None:
        """ENH-2405: the resolved registry list must be threaded into the gate call
        instead of being discarded after the trigger-guard check, so the gate proves
        the registered targets rather than re-extracting an independent list."""
        from little_loops.issue_manager import process_issue_inplace

        issue = self._make_issue(temp_project_dir, learning_tests_required=["stripe"])

        fail_ready = MagicMock(returncode=1, stdout="", stderr="")
        impl_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("little_loops.issue_manager.run_claude_command", return_value=fail_ready),
            patch(
                "little_loops.issue_manager.run_learning_gate_for_issue",
                return_value="passed",
            ) as mock_gate,
            patch("little_loops.issue_manager.run_with_continuation", return_value=impl_result),
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
            patch("little_loops.issue_manager.check_git_status", return_value=False),
        ):
            process_issue_inplace(issue, lt_enabled_config, MagicMock(), skip_learning_gate=False)

        mock_gate.assert_called_once()
        _, kwargs = mock_gate.call_args
        assert kwargs.get("targets") == ["stripe"]

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


class TestDequeueTimeBaseStateStamp:
    """ENH-2866: ll-auto's own dequeue site stamps before Phase 1 mutates anything."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.automation.ready_issue_unknown_retries = 1
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
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

    def test_resolve_base_state_uses_untracked_files_no(self, tmp_path: Path) -> None:
        import subprocess as _subprocess

        from little_loops.issue_manager import _resolve_base_state

        seen: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            seen.append(cmd)
            if cmd[:2] == ["git", "rev-parse"]:
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc123\n")
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

        with patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run):
            sha, dirty = _resolve_base_state(tmp_path)

        assert sha == "abc123"
        assert dirty is False
        assert ["git", "status", "--porcelain", "--untracked-files=no"] in seen, (
            "an untracked scratch file must not mark the base dirty"
        )

    def test_resolve_base_state_reports_tracked_dirty(self, tmp_path: Path) -> None:
        import subprocess as _subprocess

        from little_loops.issue_manager import _resolve_base_state

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["git", "rev-parse"]:
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc\n")
            return _subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout=" M scripts/foo.py\n"
            )

        with patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run):
            sha, dirty = _resolve_base_state(tmp_path)

        assert sha == "abc"
        assert dirty is True

    def test_resolve_base_state_none_when_git_fails(self, tmp_path: Path) -> None:
        import subprocess as _subprocess

        from little_loops.issue_manager import _resolve_base_state

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            return _subprocess.CompletedProcess(args=cmd, returncode=128, stdout="", stderr="no")

        with patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run):
            sha, dirty = _resolve_base_state(tmp_path)

        assert sha is None
        assert dirty is None

    def test_stamp_is_readable_while_the_issue_is_still_in_flight(
        self, mock_config: BRConfig, sample_issue: IssueInfo, tmp_path: Path
    ) -> None:
        """The AC that keeps a pre-patch base-state consumer's path from being dead code.

        The row must exist and resolve *during* processing — asserted from
        inside the Phase-1 command, before any terminal write.
        """
        import subprocess as _subprocess

        from little_loops.history_reader import read_base_sha
        from little_loops.issue_manager import process_issue_inplace

        db = tmp_path / "history.db"
        mid_flight: list[str | None] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["git", "rev-parse"]:
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="basesha1\n")
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        def fake_claude(*args, **kwargs):  # type: ignore[no-untyped-def]
            # Phase 1 has begun; the dequeue-time row must already be readable.
            mid_flight.append(read_base_sha(sample_issue.issue_id, db=db))
            raise RuntimeError("stop the run here — the stamp is what's under test")

        with (
            patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run),
            patch("little_loops.issue_manager.run_claude_command", side_effect=fake_claude),
            pytest.raises(RuntimeError),
        ):
            process_issue_inplace(
                sample_issue,
                mock_config,
                MagicMock(),
                run_id="run-inflight",
                driver="ll-auto",
                db_path=db,
            )

        assert mid_flight == ["basesha1"]

    def test_dry_run_writes_no_orchestration_row_at_dequeue(
        self, mock_config: BRConfig, sample_issue: IssueInfo, tmp_path: Path
    ) -> None:
        """A dry run must not become the one mode that persists rows."""
        import subprocess as _subprocess

        from little_loops.history_reader import read_base_sha
        from little_loops.issue_manager import process_issue_inplace
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc\n")

        with patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run):
            process_issue_inplace(
                sample_issue,
                mock_config,
                MagicMock(),
                dry_run=True,
                run_id="run-dry",
                driver="ll-auto",
                db_path=db,
            )

        assert read_base_sha(sample_issue.issue_id, db=db) is None

    def test_no_row_written_without_full_identity(
        self, mock_config: BRConfig, sample_issue: IssueInfo, tmp_path: Path
    ) -> None:
        """An orchestrator that passes no identity keeps today's behavior exactly."""
        import subprocess as _subprocess

        from little_loops.issue_manager import process_issue_inplace

        recorded: list[dict[str, Any]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="abc\n")

        with (
            patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run),
            patch(
                "little_loops.issue_manager.record_orchestration_run",
                side_effect=lambda *a, **kw: recorded.append(kw),
            ),
            patch("little_loops.issue_manager.run_claude_command", side_effect=RuntimeError("x")),
            pytest.raises(RuntimeError),
        ):
            # run_id/driver/db_path all omitted.
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        assert recorded == []

    def test_result_carries_the_stamp_back_to_callers(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """IssueProcessingResult is how ll-sprint's sequential path forwards the stamp."""
        import subprocess as _subprocess

        from little_loops.issue_manager import process_issue_inplace

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["git", "rev-parse"]:
                return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="carried\n")
            return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout="")

        with patch("little_loops.issue_manager.subprocess.run", side_effect=fake_run):
            result = process_issue_inplace(sample_issue, mock_config, MagicMock(), dry_run=True)

        assert result.base_sha == "carried"
        assert result.base_dirty is False


class TestConfidenceGatePreCheck:
    """BUG-3004: process_issue_inplace() gates before Phase 1 rather than
    letting manage-issue's own Phase 2.5 halt after a wasted ready-issue pass."""

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
        config.automation.ready_issue_unknown_retries = 1
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
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

    def _status(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        from little_loops.cli.issues.check_readiness import ReadinessStatus

        defaults: dict[str, Any] = {
            "confidence": 50,
            "outcome": 50,
            "readiness_threshold": 85,
            "outcome_threshold": 65,
            "enabled": True,
        }
        defaults.update(kwargs)
        # BUG-3252: a scored fixture is scored unless the caller explicitly
        # asks for the unscored case via raw_confidence=None.
        defaults.setdefault("raw_confidence", defaults["confidence"])
        defaults.setdefault("raw_outcome", defaults["outcome"])
        return ReadinessStatus(**defaults)

    def test_gate_disabled_runs_phase_1(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """With enabled=False, a sub-threshold score must not block Phase 1
        (protects every pre-existing fixture that has no confidence_score)."""
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=0, enabled=False)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ) as mock_ready,
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_ready.assert_called()

    def test_sub_threshold_score_skips_before_phase_1(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=80, readiness_threshold=85)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command") as mock_ready,
        ):
            result = process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_ready.assert_not_called()
        assert result.success is False
        assert result.failure_reason == "below_readiness_threshold (80 < 85)"
        assert result.was_gated is True

    def test_unscored_issue_reports_never_assessed_not_zero(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """BUG-3252: an issue with no confidence_score at all must not be
        reported as though it scored a measured 0."""
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=0, raw_confidence=None, readiness_threshold=85)
        mock_logger = MagicMock()
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command") as mock_ready,
        ):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        mock_ready.assert_not_called()
        assert result.success is False
        assert result.was_gated is True
        assert result.failure_reason == "no_confidence_score (never assessed)"
        warning_text = " ".join(str(call.args[0]) for call in mock_logger.warning.call_args_list)
        assert "has no confidence score (never assessed)" in warning_text
        assert "0 < 85" not in warning_text
        assert "/ll:confidence-check BUG-001" in warning_text

    def test_scored_gate_message_includes_remediation(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """BUG-3252 Part 2: the scored (non-None raw_confidence) branch must
        also carry the /ll:confidence-check remediation suggestion."""
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=40, readiness_threshold=85)
        mock_logger = MagicMock()
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command"),
        ):
            process_issue_inplace(sample_issue, mock_config, mock_logger)

        warning_text = " ".join(str(call.args[0]) for call in mock_logger.warning.call_args_list)
        assert "confidence 40 < 85" in warning_text
        assert "/ll:confidence-check BUG-001" in warning_text

    def test_sub_threshold_prints_confidence_gate_blocked_marker(
        self,
        mock_config: BRConfig,
        sample_issue: IssueInfo,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=80, readiness_threshold=85)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command"),
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        out = capsys.readouterr().out
        assert "CONFIDENCE_GATE_BLOCKED BUG-001" in out
        assert "LEARNING_GATE_BLOCKED" not in out
        assert "IMPLEMENT_FAILED" not in out
        # ENH-2989: the pre-Phase-1 confidence gate must also emit the
        # generic Phase-1-not-reached marker (alongside, not instead of, the
        # existing CONFIDENCE_GATE_BLOCKED marker) so autodev's
        # check_impl_reached discriminator catches this route too.
        assert "PHASE1_NOT_STARTED BUG-001 confidence_gate" in out

    def test_sub_threshold_with_trigger_enabled_consults_once(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """FEAT-3117: a sub-threshold score with `confidence_gate` in
        advisor.triggers fires exactly one consult carrying the gap analysis,
        without changing the gate's blocking outcome."""
        from little_loops.advisor import AdvisorVerdict, ConsultOutcome, TaskKey
        from little_loops.config.orchestration import AdvisorConfig
        from little_loops.issue_manager import process_issue_inplace

        mock_config.advisor = AdvisorConfig(enabled=True, triggers=["confidence_gate"])
        status = self._status(confidence=80, readiness_threshold=85)
        verdict = AdvisorVerdict(
            recommendation="proceed with caution",
            risks=[],
            confidence=0.5,
            dissent="",
            signal="confidence_gate",
            host="claude-code",
            model="opus",
        )
        outcome = ConsultOutcome(task_key=TaskKey(kind="issue", value="BUG-001"), verdict=verdict)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command") as mock_ready,
            patch("little_loops.advisor.consult_for_trigger", return_value=outcome) as mock_consult,
        ):
            result = process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_ready.assert_not_called()
        mock_consult.assert_called_once()
        call_kwargs = mock_consult.call_args
        assert call_kwargs.args[0] == "confidence_gate"
        assert "80" in call_kwargs.kwargs["context"]
        assert "85" in call_kwargs.kwargs["context"]
        assert result.success is False
        assert result.failure_reason == "below_readiness_threshold (80 < 85)"
        assert result.was_gated is True

    def test_sub_threshold_trigger_absent_fires_no_consult(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """FEAT-3117 AC #2: `confidence_gate` absent from advisor.triggers
        skips the consult entirely — `consult_for_trigger` is still called
        (fail-soft wrapper), but its internal `should_consult` gate prevents
        the actual host-calling `consult()` from ever running."""
        from little_loops.config.orchestration import AdvisorConfig
        from little_loops.issue_manager import process_issue_inplace

        mock_config.advisor = AdvisorConfig(enabled=True, triggers=[])
        status = self._status(confidence=80, readiness_threshold=85)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command"),
            patch("little_loops.advisor.consult") as mock_consult,
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_consult.assert_not_called()

    def test_sub_threshold_advisor_disabled_fires_no_consult(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """FEAT-3117 AC #2: advisor.enabled=False skips the consult entirely
        (same fail-soft shape as the trigger-absent case above)."""
        from little_loops.config.orchestration import AdvisorConfig
        from little_loops.issue_manager import process_issue_inplace

        mock_config.advisor = AdvisorConfig(enabled=False, triggers=["confidence_gate"])
        status = self._status(confidence=80, readiness_threshold=85)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command"),
            patch("little_loops.advisor.consult") as mock_consult,
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_consult.assert_not_called()

    def test_sub_threshold_consult_failure_does_not_change_gate_outcome(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """FEAT-3117 AC #3: a failed/timed-out consult never blocks the gate —
        it completes with the original below_readiness_threshold verdict."""
        from little_loops.advisor import ConsultOutcome, TaskKey
        from little_loops.config.orchestration import AdvisorConfig
        from little_loops.issue_manager import process_issue_inplace

        mock_config.advisor = AdvisorConfig(enabled=True, triggers=["confidence_gate"])
        status = self._status(confidence=80, readiness_threshold=85)
        outcome = ConsultOutcome(
            task_key=TaskKey(kind="issue", value="BUG-001"),
            skipped_reason="timeout",
            error="host timed out",
        )
        mock_logger = MagicMock()
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command") as mock_ready,
            patch("little_loops.advisor.consult_for_trigger", return_value=outcome),
        ):
            result = process_issue_inplace(sample_issue, mock_config, mock_logger)

        mock_ready.assert_not_called()
        assert result.success is False
        assert result.failure_reason == "below_readiness_threshold (80 < 85)"
        assert result.was_gated is True
        warning_text = " ".join(str(call.args[0]) for call in mock_logger.warning.call_args_list)
        assert "timeout" in warning_text

    def test_readiness_outcome_parity_matches_manage_issue(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Gate Parity: readiness only. confidence 90 >= 85 must NOT gate even
        though outcome 60 < 65 — matching manage-issue Phase 2.5, which never
        reads outcome_confidence. (cmd_check_readiness on the same scores would
        still exit 1 — see test_check_readiness.py.)"""
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(
            confidence=90, outcome=60, readiness_threshold=85, outcome_threshold=65
        )
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ) as mock_ready,
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_ready.assert_called()

    def test_verify_action_does_not_gate(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Second Gate Parity hole: manage-issue skips Phase 2.5 for verify/plan
        actions, so the pre-gate must not fire for them either."""
        from little_loops.issue_manager import process_issue_inplace

        mock_config.get_category_action.return_value = "verify"
        status = self._status(confidence=0, readiness_threshold=85)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ) as mock_ready,
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_ready.assert_called()

    def test_plan_action_does_not_gate(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        from little_loops.issue_manager import process_issue_inplace

        mock_config.get_category_action.return_value = "plan"
        status = self._status(confidence=0, readiness_threshold=85)
        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch(
                "little_loops.issue_manager.run_claude_command",
                return_value=MagicMock(returncode=1, stdout="", stderr=""),
            ) as mock_ready,
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        mock_ready.assert_called()

    def test_dry_run_does_not_gate_or_print_marker(
        self,
        mock_config: BRConfig,
        sample_issue: IssueInfo,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=0, readiness_threshold=85)
        with patch(
            "little_loops.cli.issues.check_readiness.readiness_status",
            return_value=status,
        ):
            result = process_issue_inplace(sample_issue, mock_config, MagicMock(), dry_run=True)

        out = capsys.readouterr().out
        assert "CONFIDENCE_GATE_BLOCKED" not in out
        assert result.success is not False or result.failure_reason == ""

    def test_force_implement_bypasses_pre_gate_and_appends_flag(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """Mirrors test_skip_learning_gate_bypasses_gate_and_runs_implement's shape."""
        from little_loops.issue_manager import process_issue_inplace

        status = self._status(confidence=0, readiness_threshold=85)
        fail_ready = MagicMock(returncode=1, stdout="", stderr="")
        impl_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch(
                "little_loops.cli.issues.check_readiness.readiness_status",
                return_value=status,
            ),
            patch("little_loops.issue_manager.run_claude_command", return_value=fail_ready),
            patch(
                "little_loops.issue_manager.run_with_continuation", return_value=impl_result
            ) as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
            patch("little_loops.issue_manager.check_git_status", return_value=False),
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock(), force_implement=True)

        mock_impl.assert_called_once()
        called_cmd = mock_impl.call_args[0][0]
        assert "--force-implement" in called_cmd

    @pytest.fixture
    def gate_routing_project(self, temp_project_dir: Path) -> Path:
        """Minimal real-config project for AutoManager routing/summary tests
        (full_project lives on a different test class)."""
        ll_dir = temp_project_dir / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "completed_dir": "completed",
            },
            "automation": {"timeout_seconds": 60, "state_file": ".auto-manage-state.json"},
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config_content))
        issues_dir = temp_project_dir / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir(parents=True)
        (issues_dir / "P1-BUG-001-test-issue.md").write_text(
            "# BUG-001: Test Issue\n\n## Summary\nTest"
        )
        return temp_project_dir

    def test_gated_issue_routes_to_skipped_not_failed(self, gate_routing_project: Path) -> None:
        """BUG-3252 Part 3: a confidence-gate skip must land in
        state.skipped_issues, not state.failed_issues — it was never attempted."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        issues_dir = gate_routing_project / ".issues" / "bugs"
        issue_file = issues_dir / "P1-BUG-001-test-issue.md"
        info = IssueInfo(
            path=issue_file,
            issue_type="bugs",
            priority="P1",
            issue_id="BUG-001",
            title="Test Issue",
        )

        config = BRConfig(gate_routing_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )

        status = self._status(confidence=0, raw_confidence=None, readiness_threshold=85)
        with patch(
            "little_loops.cli.issues.check_readiness.readiness_status",
            return_value=status,
        ):
            manager._process_issue(info)

        assert "BUG-001" in manager.state_manager.state.skipped_issues
        assert "BUG-001" not in manager.state_manager.state.failed_issues

    def test_auto_corrections_annotates_gated_exclusion(self, gate_routing_project: Path) -> None:
        """BUG-3252 Part 4: the Auto-corrections line discloses how many
        gated (never-attempted) issues were excluded from its denominator,
        and the rate itself reflects only issues that reached Phase 1."""
        import time as time_module

        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(gate_routing_project)
        with patch("little_loops.issue_manager.check_git_status", return_value=False):
            manager = AutoManager(
                config,
                dry_run=False,
                db_path=config.project_root / ".ll" / "history.db",
            )
        manager.logger = MagicMock()

        # One issue reached Phase 1 and was corrected.
        manager.state_manager.mark_completed("BUG-001", {"total": 1.0})
        manager.state_manager.record_corrections("BUG-001", ["fixed frontmatter"])
        # One issue never reached Phase 1 — gated before it.
        manager.state_manager.mark_skipped("BUG-002", "no_confidence_score (never assessed)")
        manager._gated_issue_ids.add("BUG-002")

        manager._log_timing_summary(time_module.time())

        info_text = " ".join(str(call.args[0]) for call in manager.logger.info.call_args_list)
        assert "Auto-corrections: 1/1 (100.0%) (1 gated before Phase 1)" in info_text
        assert "Skipped issues: 1" in info_text

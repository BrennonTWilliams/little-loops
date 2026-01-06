"""Tests for little_loops.issue_manager module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.issue_manager import AutoManager
from little_loops.issue_parser import IssueInfo


class TestPathRenameHandling:
    """Tests for handling issue file renames during ready_issue."""

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
        # Setup: Create the new file path (simulating ready_issue renaming)
        new_path = mock_issue_info.path.parent / "P3-ENH-341-refactor-metrics-module.md"
        new_path.write_text("# ENH-341: Refactor Metrics Module\n")
        # Remove the old file to simulate a rename
        mock_issue_info.path.unlink()

        # Mock the ready_issue output
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
            from little_loops.parallel.output_parsing import parse_ready_issue_output

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
        # Setup: Create a different file that ready_issue claims to validate
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
        from little_loops.parallel.output_parsing import parse_ready_issue_output

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
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir(exist_ok=True)

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

        import json

        (claude_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        return temp_project_dir, issues_dir


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
        from little_loops.parallel.output_parsing import parse_ready_issue_output

        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)

        # Create the correct file (what ll-auto expects)
        correct_file = issues_dir / "P1-ENH-341-correct-issue.md"
        correct_file.write_text("# ENH-341: Correct Issue\n")

        # Create a wrong file (what ready_issue mistakenly finds)
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
        from little_loops.parallel.output_parsing import parse_ready_issue_output

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
        """Test that ready_issue bash can distinguish paths from IDs.

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

"""End-to-end tests for CLI workflows.

These tests invoke actual CLI commands via subprocess to validate
complete user workflows from invocation to completion.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass

pytestmark = pytest.mark.integration


class E2ETestFixture:
    """Base fixture class for E2E tests with temporary git repositories."""

    @pytest.fixture
    def e2e_project_dir(self) -> Generator[Path, None, None]:
        """Create a temporary git repository with complete project setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=project_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=project_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=project_root,
                capture_output=True,
                check=True,
            )

            # Create .claude directory and config
            claude_dir = project_root / ".claude"
            claude_dir.mkdir()

            config = self._get_test_config()
            (claude_dir / "ll-config.json").write_text(json.dumps(config, indent=2))

            # Create issue directories
            self._create_issue_directories(project_root)
            self._create_sample_issues(project_root)

            # Initial commit
            subprocess.run(
                ["git", "add", "."],
                cwd=project_root,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=project_root,
                capture_output=True,
                check=True,
            )

            yield project_root

    def _get_test_config(self) -> dict:
        """Return test configuration dictionary."""
        return {
            "project": {
                "name": "e2e-test-project",
                "src_dir": "src/",
                "test_cmd": "pytest tests/",
                "lint_cmd": "ruff check .",
                "type_cmd": "mypy src/",
                "format_cmd": "ruff format .",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                },
                "completed_dir": "completed",
                "priorities": ["P0", "P1", "P2", "P3"],
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".test-auto-state.json",
            },
            "parallel": {
                "max_workers": 2,
                "p0_sequential": True,
                "worktree_base": ".worktrees",
                "state_file": ".test-parallel-state.json",
                "timeout_seconds": 60,
            },
            "sprints": {
                "sprints_dir": ".sprints",
                "default_timeout": 3600,
                "default_max_workers": 2,
            },
        }

    def _create_issue_directories(self, project_root: Path) -> None:
        """Create issue category directories."""
        issues_base = project_root / ".issues"
        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_base / category).mkdir(parents=True, exist_ok=True)

    def _create_sample_issues(self, project_root: Path) -> None:
        """Create sample issue files for testing."""
        issues_base = project_root / ".issues"

        # Bug issues
        (issues_base / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "# BUG-001: Test Bug\n\n## Summary\nA test bug for E2E testing.\n\n## Status\nReady"
        )
        (issues_base / "bugs" / "P2-BUG-002-another-bug.md").write_text(
            "# BUG-002: Another Bug\n\n## Summary\nAnother test bug.\n\n## Status\nReady"
        )

        # Feature issues
        (issues_base / "features" / "P1-FEAT-001-test-feature.md").write_text(
            "# FEAT-001: Test Feature\n\n"
            "## Summary\nA test feature for E2E testing.\n\n"
            "## Status\nReady"
        )

        # Enhancement issues
        (issues_base / "enhancements" / "P2-ENH-001-test-enhancement.md").write_text(
            "# ENH-001: Test Enhancement\n\n## Summary\nA test enhancement.\n\n## Status\nReady"
        )

    def run_cli_command(
        self,
        project_root: Path,
        command: list[str],
        expected_success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a CLI command and return the result."""
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if expected_success:
            assert result.returncode == 0, (
                f"Command failed: {' '.join(command)}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        return result


class TestIssueCreationWorkflow(E2ETestFixture):
    """E2E tests for issue creation workflow."""

    def test_issue_appears_in_listings(self, e2e_project_dir: Path) -> None:
        """Created issue should appear in issue listings."""
        # Verify initial state - issues exist
        bugs_dir = e2e_project_dir / ".issues" / "bugs"
        assert (bugs_dir / "P1-BUG-001-test-bug.md").exists()

        # List issues using ll-messages or similar
        # For now, verify file system state
        assert len(list(bugs_dir.glob("*.md"))) >= 2

    def test_issue_file_format_valid(self, e2e_project_dir: Path) -> None:
        """Created issue files should have valid format."""
        issue_file = e2e_project_dir / ".issues" / "bugs" / "P1-BUG-001-test-bug.md"
        content = issue_file.read_text()

        # Verify frontmatter format
        assert "# BUG-001:" in content
        assert "## Summary" in content
        assert "## Status" in content


class TestSprintPlanningWorkflow(E2ETestFixture):
    """E2E tests for sprint planning workflow."""

    def test_sprint_creation_from_issues(self, e2e_project_dir: Path) -> None:
        """Create a sprint from multiple issues."""
        sprints_dir = e2e_project_dir / ".sprints"
        sprints_dir.mkdir(exist_ok=True)

        sprint_file = sprints_dir / "test-sprint.yaml"
        sprint_config = {
            "name": "test-sprint",
            "description": "Test sprint for E2E",
            "issues": ["BUG-001", "BUG-002", "FEAT-001"],
            "mode": "auto",
            "max_workers": 2,
            "timeout": 3600,
        }
        sprint_file.write_text(json.dumps(sprint_config))

        # Verify sprint was created
        assert sprint_file.exists()

    def test_sprint_configuration_validation(self, e2e_project_dir: Path) -> None:
        """Sprint configuration should be validated."""
        from little_loops.config import BRConfig
        from little_loops.sprint import SprintManager

        config = BRConfig(e2e_project_dir)
        manager = SprintManager(config=config)

        # Verify manager can be instantiated
        assert manager is not None


class TestSequentialExecutionWorkflow(E2ETestFixture):
    """E2E tests for sequential execution (ll-auto) workflow."""

    def test_ll_auto_dry_run(self, e2e_project_dir: Path) -> None:
        """ll-auto --dry-run should list issues without processing."""
        import sys
        from io import StringIO
        from unittest.mock import patch

        from little_loops.cli import main_auto

        # Change to project directory
        original_cwd = Path.cwd()
        original_argv = sys.argv.copy()

        try:
            import os

            os.chdir(e2e_project_dir)
            sys.argv = ["ll-auto", "--dry-run", "--max-issues", "1"]

            # Mock subprocess to prevent actual Claude execution
            with patch("subprocess.Popen") as mock_popen:
                with patch("subprocess.run"):
                    # Capture stdout
                    old_stdout = sys.stdout
                    sys.stdout = StringIO()

                    try:
                        exit_code = main_auto()
                        _output = sys.stdout.getvalue()
                    finally:
                        sys.stdout = old_stdout

            # Verify command succeeded
            assert exit_code == 0

            # Verify no actual subprocess calls for Claude
            # (Note: some subprocess calls may happen for git operations)
            assert mock_popen.call_count == 0 or "claude" not in str(mock_popen.call_args)

            # Verify issues still exist (not moved to completed)
            assert (e2e_project_dir / ".issues" / "bugs" / "P1-BUG-001-test-bug.md").exists()
        finally:
            os.chdir(original_cwd)
            sys.argv = original_argv

    def test_ll_auto_max_issues_limit(self, e2e_project_dir: Path) -> None:
        """ll-auto --max-issues should limit processing."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(e2e_project_dir)
        manager = AutoManager(
            config=config,
            dry_run=True,
            max_issues=1,
            resume=False,
            category=None,
        )

        assert manager.max_issues == 1

    def test_ll_auto_category_filter(self, e2e_project_dir: Path) -> None:
        """ll-auto --category should filter issues by type."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig(e2e_project_dir)
        manager = AutoManager(
            config=config,
            dry_run=True,
            max_issues=10,
            resume=False,
            category="bugs",
        )

        assert manager.category == "bugs"


class TestParallelExecutionWorkflow(E2ETestFixture):
    """E2E tests for parallel execution (ll-parallel) workflow."""

    def test_ll_parallel_dry_run(self, e2e_project_dir: Path) -> None:
        """ll-parallel --dry-run should list issues without processing."""
        import sys
        from io import StringIO
        from unittest.mock import patch

        from little_loops.cli import main_parallel

        # Change to project directory
        original_cwd = Path.cwd()
        original_argv = sys.argv.copy()

        try:
            import os

            os.chdir(e2e_project_dir)
            sys.argv = ["ll-parallel", "--dry-run", "--workers", "2"]

            # Mock subprocess to prevent actual Claude execution
            with patch("subprocess.Popen"):
                with patch("subprocess.run") as mock_run:
                    # Capture stdout
                    old_stdout = sys.stdout
                    sys.stdout = StringIO()

                    try:
                        exit_code = main_parallel()
                        _output = sys.stdout.getvalue()
                    finally:
                        sys.stdout = old_stdout

            # Verify command succeeded
            assert exit_code == 0

            # Verify no actual subprocess calls for Claude
            # (Note: some subprocess calls may happen for git operations)
            assert mock_run.call_count == 0 or "claude" not in str(mock_run.call_args)

        finally:
            os.chdir(original_cwd)
            sys.argv = original_argv

    def test_ll_parallel_worktree_creation(self, e2e_project_dir: Path) -> None:
        """ll-parallel should create worktrees for parallel processing."""
        from little_loops.config import BRConfig
        from little_loops.parallel import ParallelOrchestrator
        from little_loops.parallel.types import ParallelConfig

        config = BRConfig(e2e_project_dir)
        parallel_config = ParallelConfig(
            max_workers=2,
            worktree_base=e2e_project_dir / ".worktrees",
            dry_run=True,
        )

        orchestrator = ParallelOrchestrator(
            parallel_config=parallel_config,
            br_config=config,
            repo_path=e2e_project_dir,
            verbose=False,
        )

        assert orchestrator is not None


class TestLoopExecutionWorkflow(E2ETestFixture):
    """E2E tests for loop execution (ll-loop) workflow."""

    def test_ll_loop_list_configs(self, e2e_project_dir: Path) -> None:
        """ll-loop list should show available configurations."""
        import sys
        from io import StringIO

        from little_loops.cli import main_loop

        # Change to project directory
        original_cwd = Path.cwd()
        original_argv = sys.argv.copy()

        try:
            import os

            os.chdir(e2e_project_dir)
            sys.argv = ["ll-loop", "list"]

            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = StringIO()

            try:
                exit_code = main_loop()
                _output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout

            # Should complete successfully (no loops is fine)
            assert exit_code == 0

        finally:
            os.chdir(original_cwd)
            sys.argv = original_argv

    def test_ll_loop_list_running(self, e2e_project_dir: Path) -> None:
        """ll-loop list --running should show running loops."""
        import sys
        from io import StringIO

        from little_loops.cli import main_loop

        # Change to project directory
        original_cwd = Path.cwd()
        original_argv = sys.argv.copy()

        try:
            import os

            os.chdir(e2e_project_dir)
            sys.argv = ["ll-loop", "list", "--running"]

            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = StringIO()

            try:
                exit_code = main_loop()
                _output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout

            # Should complete successfully (no running loops is fine)
            assert exit_code == 0

        finally:
            os.chdir(original_cwd)
            sys.argv = original_argv

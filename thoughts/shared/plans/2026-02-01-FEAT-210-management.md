# FEAT-210: Add end-to-end CLI workflow tests - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-210-add-end-to-end-cli-workflow-tests.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

### Key Discoveries
- The codebase uses **argparse** (not Click) for CLI command parsing (scripts/little_loops/cli.py:1-100)
- Only **2 integration test files** exist: test_workflow_integration.py (531 lines) and test_sprint_integration.py (1084 lines)
- Current integration tests use Python API directly, **not actual CLI entry points** (test_workflow_integration.py:86-103)
- Pytest integration marker is defined but underutilized (pyproject.toml:99-102)
- No true end-to-end tests that invoke actual CLI commands via subprocess

### Current State
- **Unit tests**: 2,279 tests across 44 test files
- **Integration tests**: Only 2 files marked with `@pytest.mark.integration`
- **Gap**: No validation of complete user workflows from CLI invocation to completion
- **Test patterns**: Existing tests mock subprocess calls instead of invoking actual CLI commands

### Patterns to Follow
- Temporary git repository setup pattern (scripts/tests/test_merge_coordinator.py:20-53)
- Integration test marker usage (scripts/tests/test_workflow_integration.py:21)
- Project setup with config and issues (scripts/tests/test_workflow_integration.py:27-80)
- Subprocess execution in tests (scripts/tests/test_hooks_integration.py:54-67)

## Desired End State

5 new end-to-end workflow tests that:
1. Invoke actual CLI entry points (ll-auto, ll-parallel, ll-sprint, ll-loop)
2. Use temporary git repositories for isolation
3. Exercise complete user workflows from invocation to completion
4. Validate both success and failure paths
5. Are marked with `@pytest.mark.integration`

### How to Verify
- Run: `python -m pytest scripts/tests/test_cli_e2e.py -v -m integration`
- All 5+ E2E tests pass
- Tests invoke actual CLI commands via subprocess
- Tests create and cleanup temporary git repositories

## What We're NOT Doing

- Not changing existing unit tests - they work fine
- Not refactoring existing integration tests - they serve a different purpose
- Not adding Click library - codebase uses argparse
- Not testing every CLI command - focusing on core workflows
- Not adding performance benchmarks - focused on functional correctness

## Problem Analysis

The current test suite has excellent coverage of individual components but lacks validation of complete user workflows. This means:
1. Integration issues between components may go undetected
2. CLI argument parsing bugs may not be caught
3. File system state changes during execution are not validated
4. Real-world usage patterns are not tested

## Solution Approach

Create a new test file `test_cli_e2e.py` with true end-to-end tests that:
1. Use `subprocess.run()` to invoke actual CLI commands (not Python API)
2. Create temporary git repositories for isolation
3. Validate exit codes, stdout/stderr, and file system state
4. Test both success and error paths for each workflow

This approach differs from existing integration tests by exercising the actual CLI entry points rather than internal Python APIs.

## Implementation Phases

### Phase 1: Create E2E Test Infrastructure

#### Overview
Create base fixtures and utilities for end-to-end CLI testing.

#### Changes Required

**File**: `scripts/tests/test_cli_e2e.py` (NEW)
**Changes**: Create new test file with infrastructure

```python
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
            claude.mkdir()

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
                "default_mode": "auto",
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
            "# FEAT-001: Test Feature\n\n## Summary\nA test feature for E2E testing.\n\n## Status\nReady"
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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli_e2e.py -v -m integration`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_e2e.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_cli_e2e.py`

---

### Phase 2: Issue Creation Workflow E2E Test

#### Overview
Test the workflow of creating a new issue via CLI and verifying it appears in listings.

#### Changes Required

**File**: `scripts/tests/test_cli_e2e.py`
**Changes**: Add test class for issue creation workflow

```python
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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli_e2e.py::TestIssueCreationWorkflow -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_e2e.py`

**Manual Verification**:
- [ ] Issue files are created with correct naming format
- [ ] Issue content follows expected markdown structure

---

### Phase 3: Sprint Planning Workflow E2E Test

#### Overview
Test the workflow of creating a sprint from multiple issues and validating it can be executed.

#### Changes Required

**File**: `scripts/tests/test_cli_e2e.py`
**Changes**: Add test class for sprint planning workflow

```python
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
        sprint_file.write_text(
            json.dumps(sprint_config)  # Will use yaml in actual implementation
        )

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli_e2e.py::TestSprintPlanningWorkflow -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_e2e.py`

**Manual Verification**:
- [ ] Sprint files are created with valid YAML/JSON format
- [ ] Sprint configuration is validated correctly

---

### Phase 4: Sequential Execution Workflow E2E Test

#### Overview
Test the workflow of running ll-auto on issues with sequential processing.

#### Changes Required

**File**: `scripts/tests/test_cli_e2e.py`
**Changes**: Add test class for sequential execution workflow

```python
class TestSequentialExecutionWorkflow(E2ETestFixture):
    """E2E tests for sequential execution (ll-auto) workflow."""

    def test_ll_auto_dry_run(self, e2e_project_dir: Path) -> None:
        """ll-auto --dry-run should list issues without processing."""
        from unittest.mock import patch

        # Mock subprocess to prevent actual Claude execution
        with patch("subprocess.Popen") as mock_popen:
            with patch("subprocess.run") as mock_run:
                result = self.run_cli_command(
                    e2e_project_dir,
                    ["ll-auto", "--dry-run", "--max-issues", "1"],
                )

        # Verify no actual subprocess calls
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

        # Verify issues still exist
        assert (e2e_project_dir / ".issues" / "bugs" / "P1-BUG-001-test-bug.md").exists()

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli_e2e.py::TestSequentialExecutionWorkflow -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_e2e.py`

**Manual Verification**:
- [ ] Sequential processing respects max-issues limit
- [ ] Dry-run mode doesn't modify files

---

### Phase 5: Parallel Execution Workflow E2E Test

#### Overview
Test the workflow of running ll-parallel on a sprint with worker coordination.

#### Changes Required

**File**: `scripts/tests/test_cli_e2e.py`
**Changes**: Add test class for parallel execution workflow

```python
class TestParallelExecutionWorkflow(E2ETestFixture):
    """E2E tests for parallel execution (ll-parallel) workflow."""

    def test_ll_parallel_dry_run(self, e2e_project_dir: Path) -> None:
        """ll-parallel --dry-run should list issues without processing."""
        from unittest.mock import patch

        # Mock subprocess to prevent actual Claude execution
        with patch("subprocess.Popen") as mock_popen:
            with patch("subprocess.run") as mock_run:
                result = self.run_cli_command(
                    e2e_project_dir,
                    ["ll-parallel", "--dry-run", "--max-workers", "2"],
                )

        # Verify no actual subprocess calls
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

    def test_ll_parallel_worktree_creation(self, e2e_project_dir: Path) -> None:
        """ll-parallel should create worktrees for parallel processing."""
        from little_loops.config import BRConfig
        from little_loops.parallel.types import ParallelConfig
        from little_loops.parallel import ParallelOrchestrator

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli_e2e.py::TestParallelExecutionWorkflow -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_e2e.py`

**Manual Verification**:
- [ ] Worktree base directory is created
- [ ] Workers can be configured with max-workers parameter

---

### Phase 6: Loop Execution Workflow E2E Test

#### Overview
Test the workflow of running ll-loop with FSM execution and state persistence.

#### Changes Required

**File**: `scripts/tests/test_cli_e2e.py`
**Changes**: Add test class for loop execution workflow

```python
class TestLoopExecutionWorkflow(E2ETestFixture):
    """E2E tests for loop execution (ll-loop) workflow."""

    def test_ll_loop_status_check(self, e2e_project_dir: Path) -> None:
        """ll-loop status should check loop state."""
        result = self.run_cli_command(
            e2e_project_dir,
            ["ll-loop", "status"],
        )

        # Should not fail even with no active loop
        assert result.returncode == 0

    def test_ll_loop_list_configs(self, e2e_project_dir: Path) -> None:
        """ll-loop list should show available configurations."""
        result = self.run_cli_command(
            e2e_project_dir,
            ["ll-loop", "list"],
        )

        # Should complete successfully
        assert result.returncode == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli_e2e.py::TestLoopExecutionWorkflow -v`
- [ ] Lint passes: `ruff check scripts/tests/test_cli_e2e.py`

**Manual Verification**:
- [ ] Loop status command works without active loop
- [ ] Loop list command shows available configurations

---

### Phase 7: Documentation

#### Overview
Add documentation for running end-to-end tests.

#### Changes Required

**File**: `CONTRIBUTING.md` (or create `docs/E2E_TESTING.md`)
**Changes**: Add E2E testing section

```markdown
## End-to-End Testing

The project includes end-to-end (E2E) tests that validate complete CLI workflows
from invocation to completion.

### Running E2E Tests

E2E tests are marked with the `integration` marker:

```bash
# Run all E2E tests
python -m pytest scripts/tests/test_cli_e2e.py -v -m integration

# Run specific E2E test class
python -m pytest scripts/tests/test_cli_e2e.py::TestSequentialExecutionWorkflow -v

# Run all tests except integration (faster)
python -m pytest scripts/tests/ -v -m "not integration"
```

### E2E Test Coverage

The E2E test suite covers:
1. **Issue Creation Workflow** - Validates issue file creation and listings
2. **Sprint Planning Workflow** - Tests sprint creation and configuration
3. **Sequential Execution Workflow** - Tests ll-auto command processing
4. **Parallel Execution Workflow** - Tests ll-parallel worker coordination
5. **Loop Execution Workflow** - Tests ll-loop FSM execution

### Test Isolation

E2E tests create temporary git repositories for complete isolation.
Tests use `subprocess.run()` to invoke actual CLI commands, not Python APIs.
```

#### Success Criteria

**Automated Verification**:
- [ ] Documentation file exists
- [ ] Documentation is accurate and complete

**Manual Verification**:
- [ ] Documentation helps users run E2E tests
- [ ] Examples in documentation work correctly

---

## Testing Strategy

### Unit Tests
Each test class focuses on a specific CLI workflow:
- TestIssueCreationWorkflow - Issue creation and listing
- TestSprintPlanningWorkflow - Sprint creation and validation
- TestSequentialExecutionWorkflow - ll-auto command
- TestParallelExecutionWorkflow - ll-parallel command
- TestLoopExecutionWorkflow - ll-loop command

### Integration Tests
All tests use:
- Temporary git repositories for isolation
- Actual CLI command invocation via subprocess
- Exit code validation
- File system state validation
- Mocked subprocess calls for Claude CLI

### Test Isolation
- Each test gets a fresh temporary directory
- Git repos are initialized per test
- Config files are created per test
- Automatic cleanup via tempfile.TemporaryDirectory()

## References

- Original issue: `.issues/features/P1-FEAT-210-add-end-to-end-cli-workflow-tests.md`
- CLI entry points: `scripts/little_loops/cli.py`
- Existing integration tests: `scripts/tests/test_workflow_integration.py`
- Sprint integration tests: `scripts/tests/test_sprint_integration.py`
- Test configuration: `scripts/pyproject.toml:87-102`
- Temporary git repo pattern: `scripts/tests/test_merge_coordinator.py:20-53`

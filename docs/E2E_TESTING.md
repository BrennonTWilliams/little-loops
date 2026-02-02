# End-to-End Testing Guide

This guide covers the end-to-end (E2E) test suite for little-loops CLI workflows.

## Overview

The E2E test suite validates complete CLI workflows from invocation to completion. Unlike unit tests that test individual components, E2E tests invoke actual CLI commands and validate the entire user journey.

## Running E2E Tests

E2E tests are marked with the `integration` marker for easy selection:

```bash
# Run all E2E tests
python -m pytest scripts/tests/test_cli_e2e.py -v -m integration

# Run specific E2E test class
python -m pytest scripts/tests/test_cli_e2e.py::TestSequentialExecutionWorkflow -v

# Run all tests except integration (faster feedback)
python -m pytest scripts/tests/ -v -m "not integration"

# Run E2E tests with coverage
python -m pytest scripts/tests/test_cli_e2e.py -v -m integration --cov=little_loops
```

## E2E Test Coverage

The E2E test suite covers the following workflows:

### 1. Issue Creation Workflow
- **Tests**: `TestIssueCreationWorkflow`
- **Validates**:
  - Issue files are created with correct naming format
  - Issue content follows expected markdown structure
  - Issues appear in listings

### 2. Sprint Planning Workflow
- **Tests**: `TestSprintPlanningWorkflow`
- **Validates**:
  - Sprint configuration files can be created
  - SprintManager can instantiate with valid configuration
  - Sprint configuration is validated correctly

### 3. Sequential Execution Workflow (ll-auto)
- **Tests**: `TestSequentialExecutionWorkflow`
- **Validates**:
  - `ll-auto --dry-run` lists issues without processing
  - `--max-issues` parameter limits processing
  - `--category` parameter filters issues by type

### 4. Parallel Execution Workflow (ll-parallel)
- **Tests**: `TestParallelExecutionWorkflow`
- **Validates**:
  - `ll-parallel --dry-run` lists issues without processing
  - Worktree base directory is configured correctly
  - ParallelOrchestrator can instantiate with valid configuration

### 5. Loop Execution Workflow (ll-loop)
- **Tests**: `TestLoopExecutionWorkflow`
- **Validates**:
  - `ll-loop status` works without active loop
  - `ll-loop list` shows available configurations

## Test Isolation

E2E tests use several techniques for complete isolation:

1. **Temporary Git Repositories**: Each test creates a fresh git repository with proper configuration
2. **Temporary Directories**: Uses `tempfile.TemporaryDirectory()` for automatic cleanup
3. **Subprocess Mocking**: Mocks Claude CLI subprocess calls to prevent actual execution
4. **Independent Fixtures**: Each test class has its own fixture setup

## Test Architecture

### Base Fixture: `E2ETestFixture`

The `E2ETestFixture` class provides common functionality for all E2E tests:

- `e2e_project_dir`: Creates a temporary git repository with complete project setup
- `run_cli_command()`: Executes CLI commands via subprocess with validation
- `_get_test_config()`: Provides test configuration dictionary
- `_create_issue_directories()`: Creates issue category directories
- `_create_sample_issues()`: Creates sample issue files for testing

### Test Classes

Each test class inherits from `E2ETestFixture` and focuses on a specific CLI workflow:

```python
class TestSequentialExecutionWorkflow(E2ETestFixture):
    """E2E tests for sequential execution (ll-auto) workflow."""

    def test_ll_auto_dry_run(self, e2e_project_dir: Path) -> None:
        """ll-auto --dry-run should list issues without processing."""
        # Test implementation...
```

## Writing New E2E Tests

When adding new E2E tests, follow this pattern:

1. **Inherit from `E2ETestFixture`**
2. **Use the `e2e_project_dir` fixture**
3. **Invoke actual CLI commands** via `self.run_cli_command()`
4. **Validate results** with assertions on exit codes, stdout/stderr, and file system state
5. **Mock subprocess calls** when you don't want actual Claude CLI execution

Example:

```python
class TestNewWorkflow(E2ETestFixture):
    """E2E tests for new CLI workflow."""

    def test_new_command_works(self, e2e_project_dir: Path) -> None:
        """New command should work correctly."""
        from unittest.mock import patch

        # Mock subprocess to prevent actual Claude execution
        with patch("subprocess.Popen") as mock_popen:
            with patch("subprocess.run") as mock_run:
                result = self.run_cli_command(
                    e2e_project_dir,
                    ["python", "-m", "little_loops.cli", "new-command", "--flag"],
                )

        # Validate no actual subprocess calls
        mock_popen.assert_not_called()
        mock_run.assert_not_called()

        # Validate file system state
        assert (e2e_project_dir / "expected-file.txt").exists()
```

## Difference from Integration Tests

The project has two types of integration-level tests:

| Feature | Integration Tests (`test_workflow_integration.py`) | E2E Tests (`test_cli_e2e.py`) |
|---------|---------------------------------------------------|-------------------------------|
| Invocation | Direct Python API calls | Actual CLI commands via subprocess |
| Scope | Component integration | Complete user workflows |
| Subprocess | Mocked subprocess calls | Mocked subprocess calls (for Claude) |
| Purpose | Validate component interactions | Validate CLI entry points and user experience |

Both types are valuable:
- **Integration tests** are faster and easier to debug
- **E2E tests** validate the actual CLI user experience

## Troubleshooting

### Tests Timeout

E2E tests have a 120-second timeout. If tests timeout:
- Check for infinite loops in CLI code
- Verify mock patches are correctly applied
- Ensure temporary directories are being cleaned up

### Git Repository Errors

If git initialization fails:
- Verify git is installed and accessible
- Check file permissions on temporary directory
- Ensure `GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` are set

### Import Errors

If imports fail during tests:
- Ensure you're running from the `scripts/` directory
- Verify the package is installed: `pip install -e scripts/[dev]`
- Check PYTHONPATH includes `scripts/`

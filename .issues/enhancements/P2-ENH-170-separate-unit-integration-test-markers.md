---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-170: Separate unit and integration tests with pytest markers

## Summary

Currently all tests run together, making it difficult to run quick unit tests during development versus slower integration tests. Adding pytest markers would allow selective test execution.

## Current State

**Test suite**: 1,868 tests across 34 test files

**Test execution**:
- All tests run together with `pytest scripts/tests/`
- No way to run only fast unit tests
- No way to skip slow integration tests

## Context

**Direct mode**: User description: "Separate unit/integration tests with markers (@pytest.mark.integration)"

Identified from testing analysis showing:
- Some tests involve file I/O, subprocess calls, git operations (slow)
- Many tests are pure unit tests (fast)
- Development workflow hurt by running everything

## Proposed Solution

### 1. Define markers in pyproject.toml

See ENH-168 for configuration. Add:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "slow: marks tests as slow running (deselect with '-m \"not slow\"')",
]
```

### 2. Mark integration tests

Apply `@pytest.mark.integration` to integration test classes/files:

**Files to mark**:
- `test_workflow_integration.py` - All classes
- `test_sprint_integration.py` - All classes
- `test_orchestrator.py` - Tests with real git operations
- `test_merge_coordinator.py` - Tests with git operations
- `test_worker_pool.py` - Tests with threading/processes
- `test_git_operations.py` - All tests (real subprocess calls)
- `test_git_lock.py` - Tests with threading
- `test_fsm_interpolation.py` - Tests with file I/O

**Example**:
```python
import pytest

@pytest.mark.integration
class TestWorkflowIntegration:
    """Integration tests for workflow processing."""
    ...
```

### 3. Mark slow tests

Apply `@pytest.mark.slow` to tests that take >1 second:

**Likely candidates**:
- Tests with 100+ iterations
- Tests with complex dependency graphs
- Tests with large file operations
- Tests with sleep/delay

### 4. Development workflow

**Run fast unit tests only**:
```bash
pytest -m "not integration" scripts/tests/
```

**Run all tests** (CI/CD):
```bash
pytest scripts/tests/
```

**Run specific category**:
```bash
pytest -m integration scripts/tests/
pytest -m "not slow" scripts/tests/
```

## Impact

- **Priority**: P2 (Medium)
- **Effort**: Medium (requires marking many tests)
- **Risk**: Low (adding markers only)

## Acceptance Criteria

- [ ] Add marker definitions to pyproject.toml
- [ ] Mark all integration test classes/files
- [ ] Mark slow tests
- [ ] Verify `pytest -m "not integration"` runs fast (< 30 seconds)
- [ ] Verify `pytest -m integration` runs integration tests
- [ ] Verify `pytest` still runs all tests
- [ ] Update CONTRIBUTING.md with test selection commands

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Documents test execution commands |

## Labels

`enhancement`, `testing`, `infrastructure`, `development-experience`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P2

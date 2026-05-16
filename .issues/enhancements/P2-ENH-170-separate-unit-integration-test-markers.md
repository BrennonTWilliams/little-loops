---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-170: Separate unit and integration tests with pytest markers

## Summary

Currently all tests run together, making it difficult to run quick unit tests during development versus slower integration tests. Adding pytest markers would allow selective test execution.

## Current State

**Test suite**: 1,873 tests across 36 test files

**Marker configuration**: Already exists in `scripts/pyproject.toml` (added via ENH-168)

**Test execution**:
- All tests run together with `pytest scripts/tests/`
- Markers defined but not applied to any tests
- No way to run only fast unit tests
- No way to skip slow integration tests

## Context

**Direct mode**: User description: "Separate unit/integration tests with markers (@pytest.mark.integration)"

Identified from testing analysis showing:
- Some tests involve file I/O, subprocess calls, git operations (slow)
- Many tests are pure unit tests (fast)
- Development workflow hurt by running everything

## Proposed Solution

### 1. Marker definitions (ALREADY DONE)

Markers are already defined in `scripts/pyproject.toml` (lines 97-100), added via ENH-168:

```toml
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "slow: marks tests as slow running (deselect with '-m \"not slow\"')",
]
```

**No action needed for this step.**

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

- [x] Add marker definitions to pyproject.toml (DONE via ENH-168)
- [x] Mark all integration test classes/files (7 files marked - fsm_interpolation excluded as unit tests)
- [ ] Mark slow tests (deferred to future enhancement)
- [x] Verify `pytest -m "not integration"` runs fast (1.56s for 1,615 tests)
- [x] Verify `pytest -m integration` runs integration tests (7.72s for 258 tests)
- [x] Verify `pytest` still runs all tests (1,873 tests)
- [x] Update CONTRIBUTING.md with test selection commands

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | CONTRIBUTING.md | Documents test execution commands |

## Labels

`enhancement`, `testing`, `infrastructure`, `development-experience`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made
- `scripts/tests/test_workflow_integration.py`: Added `pytestmark = pytest.mark.integration`
- `scripts/tests/test_sprint_integration.py`: Added `pytestmark = pytest.mark.integration`
- `scripts/tests/test_orchestrator.py`: Added `pytestmark = pytest.mark.integration`
- `scripts/tests/test_merge_coordinator.py`: Added `pytestmark = pytest.mark.integration`
- `scripts/tests/test_worker_pool.py`: Added `pytestmark = pytest.mark.integration`
- `scripts/tests/test_git_operations.py`: Added `pytestmark = pytest.mark.integration`
- `scripts/tests/test_git_lock.py`: Added `pytestmark = pytest.mark.integration`
- `CONTRIBUTING.md`: Added test selection commands documentation

### Notes
- `test_fsm_interpolation.py` was excluded as it contains unit tests (pure function tests)
- Marking slow tests deferred to future enhancement
- 258 tests marked as integration, 1,615 remain as unit tests

### Verification Results
- Tests: PASS (all 1,873 tests)
- Lint: PASS
- Integration tests can be selected: `pytest -m integration scripts/tests/`
- Unit tests can be selected: `pytest -m "not integration" scripts/tests/`

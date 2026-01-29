# ENH-170: Separate unit and integration tests with pytest markers - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-170-separate-unit-integration-test-markers.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The test suite has 1,873 tests across 38 test files in `scripts/tests/`. Pytest markers are already defined in `scripts/pyproject.toml:97-100` but are not applied to any tests.

### Key Discoveries
- Marker definitions exist in `scripts/pyproject.toml:97-100` (added via ENH-168)
- `--strict-markers` is enabled, preventing typos in marker names
- No tests currently use `@pytest.mark.integration` or `@pytest.mark.slow`
- Only `@pytest.mark.parametrize` is currently used in the codebase

### Files Requiring Integration Markers
The issue identifies 8 test files that need `@pytest.mark.integration`:

| File | Integration Indicators |
|------|------------------------|
| `test_workflow_integration.py` | Full project setup fixtures, mocked subprocess |
| `test_sprint_integration.py` | Project config setup, file I/O |
| `test_orchestrator.py` | Signal handlers, git operations, threading |
| `test_merge_coordinator.py` | Real git repo fixture, subprocess |
| `test_worker_pool.py` | Threading, subprocess, worktree operations |
| `test_git_operations.py` | Subprocess mocking, git status parsing |
| `test_git_lock.py` | Threading, lock operations |
| `test_fsm_interpolation.py` | File I/O (however, review shows this is mostly unit tests) |

### Patterns to Follow
- Class-level markers: Apply `@pytest.mark.integration` at the class level for entire test classes
- Marker import: Just use `import pytest` which is already present in all test files
- Example pattern from `scripts/pyproject.toml:97-100`:
  ```toml
  markers = [
      "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
      "slow: marks tests as slow running (deselect with '-m \"not slow\"')",
  ]
  ```

## Desired End State

- All integration tests marked with `@pytest.mark.integration`
- `pytest -m "not integration"` runs only fast unit tests
- `pytest -m integration` runs only integration tests
- `pytest` (no flags) runs all tests
- CONTRIBUTING.md documents test selection commands

### How to Verify
- `pytest -m "not integration" scripts/tests/` completes quickly (unit tests only)
- `pytest -m integration scripts/tests/` runs integration tests
- `pytest scripts/tests/` runs all 1,873 tests
- No warnings about unknown markers

## What We're NOT Doing

- **NOT marking slow tests** - Deferred; focus on integration/unit separation first
- **NOT changing test behavior** - Only adding markers, no functional changes
- **NOT reorganizing test files** - Tests stay in their current locations
- **NOT adding markers to non-integration tests** - Only the 8 identified files get markers

## Problem Analysis

Currently, running `pytest scripts/tests/` executes all tests together. Developers cannot quickly run unit tests during development while skipping slower integration tests. The markers are defined but not applied.

## Solution Approach

Apply `@pytest.mark.integration` at the module level (using `pytestmark`) or class level to the 8 identified test files. This is the cleanest approach as entire files contain integration-style tests. Update CONTRIBUTING.md with test selection commands.

## Implementation Phases

### Phase 1: Mark Integration Test Files

#### Overview
Apply `@pytest.mark.integration` to the 8 identified integration test files using `pytestmark` module-level assignment.

#### Changes Required

**File**: `scripts/tests/test_workflow_integration.py`
**Changes**: Add module-level marker after imports

```python
import pytest

if TYPE_CHECKING:
    pass

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add module-level marker after imports

```python
import pytest

from little_loops.config import BRConfig
from little_loops.sprint import SprintManager

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add module-level marker after imports

```python
import pytest

from little_loops.config import BRConfig
# ... other imports

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add module-level marker after imports

```python
import pytest

from little_loops.parallel.merge_coordinator import MergeCoordinator
# ... other imports

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add module-level marker after imports

```python
import pytest

from little_loops.config import BRConfig
# ... other imports

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_git_operations.py`
**Changes**: Add module-level marker after imports

```python
import pytest

from little_loops.git_operations import get_untracked_files

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_git_lock.py`
**Changes**: Add module-level marker after imports

```python
import pytest

from little_loops.parallel.git_lock import GitLock

pytestmark = pytest.mark.integration
```

**File**: `scripts/tests/test_fsm_interpolation.py`
**Changes**: Review needed - this file appears to be mostly unit tests with `InterpolationContext` and pure function testing. Skip marking this file as integration.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Integration tests can be selected: `python -m pytest -m integration scripts/tests/ --collect-only` shows only marked tests
- [ ] Unit tests can be selected: `python -m pytest -m "not integration" scripts/tests/ --collect-only` excludes marked tests

**Manual Verification**:
- [ ] Verify `pytest -m "not integration"` runs faster than full suite

---

### Phase 2: Update Documentation

#### Overview
Update CONTRIBUTING.md to document test selection commands.

#### Changes Required

**File**: `CONTRIBUTING.md`
**Changes**: Update the "Running Tests" section to include marker-based selection

Add after the existing test commands (around line 54):

```markdown
### Running Tests

```bash
# Run all tests
pytest scripts/tests/

# Run with coverage
pytest scripts/tests/ --cov=little_loops --cov-report=html

# Run specific test file
pytest scripts/tests/test_config.py

# Run with verbose output
pytest scripts/tests/ -v

# Run only unit tests (fast, excludes integration tests)
pytest -m "not integration" scripts/tests/

# Run only integration tests
pytest -m integration scripts/tests/
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] Documentation is clear and accurate

---

### Phase 3: Verification and Cleanup

#### Overview
Run full test suite to verify markers work correctly and tests still pass.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Integration marker collection works: `python -m pytest -m integration scripts/tests/ --collect-only`
- [ ] Unit test collection works: `python -m pytest -m "not integration" scripts/tests/ --collect-only`

**Manual Verification**:
- [ ] Confirm unit tests run noticeably faster than full suite

---

## Testing Strategy

### Unit Tests
- No new tests required - this is a metadata-only change
- Existing tests should continue to pass unchanged

### Integration Tests
- Verify marker collection with `--collect-only`
- Verify marker exclusion with `-m "not integration"`

## References

- Original issue: `.issues/enhancements/P2-ENH-170-separate-unit-integration-test-markers.md`
- Marker configuration: `scripts/pyproject.toml:97-100`
- Documentation to update: `CONTRIBUTING.md:40-54`

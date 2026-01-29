---
discovered_date: 2026-01-29
discovered_by: capture_issue
source: docs/CLI-TOOLS-AUDIT.md
---

# ENH-189: Expand ll-sprint integration test coverage

## Summary

ll-sprint has significantly fewer tests than ll-auto and ll-parallel, particularly lacking integration tests for complex scenarios. This gap increases risk of regressions.

## Context

Identified from CLI Tools Audit (docs/CLI-TOOLS-AUDIT.md):
- Test Coverage Summary (from audit snapshot, some tests added since):
  - ll-auto: ~35 unit tests, ~800 lines
  - ll-parallel: ~220 unit + ~30 integration, ~1500 lines
  - ll-sprint: **now ~38 tests, ~675 lines** (was ~23 tests, ~475 lines at audit time)
- Key gap: ll-sprint still lacks integration tests for complex multi-wave scenarios
- Code Quality Score: ⭐⭐⭐ for Test Coverage (integration test gap remains)

## Current Behavior

`scripts/tests/test_sprint.py` contains ~675 lines with:
- 38 test functions across 7 test classes
- Unit tests for dataclasses (SprintOptions, Sprint, SprintState)
- Tests for SprintManager and YAML format
- Signal handling tests (added via ENH-183)
- Error handling tests (added via ENH-185)
- **Still missing**: Integration tests for complex execution scenarios

**Anchor**: `class TestSprintErrorHandling` (last test class in file)

## Expected Behavior

Comprehensive test coverage including:
- Multi-wave execution scenarios
- Error recovery paths
- Dependency cycle detection and handling
- Partial completion scenarios
- Edge cases (empty waves, single issue waves)

## Proposed Solution

Add integration tests for the following scenarios:

### 1. Multi-Wave Execution Tests

```python
def test_sprint_run_multiple_waves():
    """Test sprint with 3+ waves executes in correct order."""

def test_sprint_wave_completion_reporting():
    """Test wave completion messages show X/Y format."""

def test_sprint_parallel_within_wave():
    """Test issues within same wave run in parallel."""
```

### 2. Error Recovery Tests

```python
def test_sprint_continues_after_issue_failure():
    """Test sprint continues to next issue after failure."""

def test_sprint_wave_fails_if_blocking_issue_fails():
    """Test dependent waves don't run if blocker fails."""

def test_sprint_error_summary_at_end():
    """Test final summary shows failed issues."""
```

### 3. Dependency Handling Tests

```python
def test_sprint_detects_dependency_cycle():
    """Test circular dependencies are detected and reported."""

def test_sprint_respects_issue_dependencies():
    """Test issues wait for their dependencies."""

def test_sprint_orphan_dependencies_handled():
    """Test issues depending on non-existent issues."""
```

### 4. Edge Case Tests

```python
def test_sprint_empty_wave():
    """Test sprint handles waves with no issues."""

def test_sprint_single_issue():
    """Test sprint with only one issue."""

def test_sprint_all_issues_skipped():
    """Test sprint where all issues are filtered out."""
```

## Files to Modify

- `scripts/tests/test_sprint.py` - Add integration tests (currently 675 lines, 38 tests)
- `scripts/tests/fixtures/` - Test fixtures directory exists; may add sprint-specific fixtures
- Reference: `scripts/tests/test_parallel_types.py` for comprehensive test patterns

## Impact

- **Priority**: P3 (Medium - quality/reliability)
- **Effort**: Medium (test writing and fixture setup)
- **Risk**: Very Low (tests don't change production code)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| reference | scripts/tests/test_parallel_types.py | Pattern for comprehensive tests |
| audit | docs/CLI-TOOLS-AUDIT.md | Test Coverage Summary |

## Labels

`enhancement`, `ll-sprint`, `testing`, `quality`, `captured`

---

## Status

**Completed** | Created: 2026-01-29 | Completed: 2026-01-29 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-29
- **Status**: Completed

### Changes Made

- `scripts/tests/test_sprint_integration.py`: Expanded from 149 lines (3 tests) to 1073 lines (16 tests)
  - Added `TestMultiWaveExecution` class (3 tests):
    - `test_sprint_wave_composition` - Verifies wave calculation groups parallel issues correctly
    - `test_sprint_run_multiple_waves` - Verifies execution order respects dependencies
    - `test_sprint_parallel_within_wave` - Verifies orchestrator used for multi-issue waves
  - Added `TestErrorRecovery` class (3 tests):
    - `test_sprint_wave_failure_tracks_correctly` - Verifies failed issues tracked in state
    - `test_sprint_state_saved_on_failure` - Verifies state persistence on failure
    - `test_sprint_resume_skips_completed_waves` - Verifies resume skips completed waves
  - Added `TestDependencyHandling` class (4 tests):
    - `test_sprint_detects_dependency_cycle` - Verifies circular dependencies detected
    - `test_sprint_orphan_dependencies_handled` - Verifies missing blockers logged but not fatal
    - `test_sprint_completed_dependencies_satisfied` - Verifies completed blockers are satisfied
  - Added `TestEdgeCases` class (4 tests):
    - `test_sprint_single_issue` - Verifies single issue uses in-place processing
    - `test_sprint_all_issues_skipped` - Verifies error when all issues filtered
    - `test_sprint_dry_run_no_execution` - Verifies dry run makes no changes
    - `test_sprint_not_found` - Verifies error for non-existent sprint

### Test Coverage Summary

| File | Before | After |
|------|--------|-------|
| test_sprint.py | 38 tests, 676 lines | 38 tests, 676 lines (unchanged) |
| test_sprint_integration.py | 3 tests, 149 lines | 16 tests, 1073 lines |
| **Total** | 41 tests, 825 lines | **54 tests, 1749 lines** |

### Verification Results

- Tests: PASS (54/54)
- Lint: PASS
- Types: PASS

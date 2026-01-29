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
- Test Coverage Summary shows disparity:
  - ll-auto: ~35 unit tests, ~800 lines
  - ll-parallel: ~220 unit + ~30 integration, ~1500 lines
  - ll-sprint: ~23 unit + 3 integration, ~475 lines
- Consistency Matrix shows "⚠️ 29 tests" (70% score)
- Code Quality Score: ⭐⭐⭐ for Test Coverage

## Current Behavior

`scripts/tests/test_sprint.py` contains 328 lines with:
- ~23 unit tests
- Only 3 integration tests
- Missing coverage for key scenarios

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

- `scripts/tests/test_sprint.py` - Add integration tests
- May need `scripts/tests/fixtures/` for test sprint definitions

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

**Open** | Created: 2026-01-29 | Priority: P3

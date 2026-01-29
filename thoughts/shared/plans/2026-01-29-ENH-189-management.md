# ENH-189: Expand ll-sprint Integration Test Coverage - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-189-expand-ll-sprint-integration-tests.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The existing test files contain:
- `scripts/tests/test_sprint.py`: 676 lines with 38 unit tests covering:
  - `TestSprintOptions` - dataclass serialization
  - `TestSprint` - dataclass and save/load
  - `TestSprintManager` - CRUD operations
  - `TestSprintYAMLFormat` - YAML serialization
  - `TestSprintState` - state dataclass and persistence
  - `TestSprintSignalHandler` - signal handling (ENH-183)
  - `TestSprintErrorHandling` - error wrapper (ENH-185)

- `scripts/tests/test_sprint_integration.py`: 149 lines with 3 integration tests covering:
  - `test_sprint_lifecycle` - create/list/show/delete
  - `test_sprint_validation_invalid_issues` - validation with invalid IDs
  - `test_sprint_yaml_format` - YAML format verification

### Key Discoveries
- `DependencyGraph.from_issues()` at `dependency_graph.py:41` builds the graph with cycle detection
- `DependencyGraph.get_execution_waves()` at `dependency_graph.py:119` groups issues into parallel waves
- Wave execution in `_cmd_sprint_run()` at `cli.py:1858-1941`:
  - Single-issue waves: `process_issue_inplace()` at `issue_manager.py`
  - Multi-issue waves: `ParallelOrchestrator.run()` at `orchestrator.py`
- State persistence via `SprintState` with JSON serialization

### Patterns to Follow
- `TestSprintErrorHandling._setup_test_project()` at `test_sprint.py:504-562` for project setup
- `sprint_project` fixture at `test_sprint_integration.py:14-58` for simpler integration setup
- Monkeypatch pattern for mocking `process_issue_inplace` at `test_sprint.py:580-587`
- `subprocess.run` mocking pattern at `test_subprocess_mocks.py:154-222`

## Desired End State

Comprehensive integration test coverage including:
- Multi-wave execution scenarios with dependency ordering verification
- Error recovery paths (issue failure continuation, state persistence)
- Dependency cycle detection and handling
- Edge cases (empty waves, single issue, all filtered)

### How to Verify
- All new tests pass: `pytest scripts/tests/test_sprint_integration.py -v`
- Test count increases from 3 to ~15+ integration tests
- Coverage of wave execution paths validated

## What We're NOT Doing

- **Not testing actual subprocess execution** - we mock `process_issue_inplace` and `ParallelOrchestrator`
- **Not creating real git worktrees** - mocked via patching
- **Not modifying production code** - only adding tests
- **Not testing UI/CLI output formatting** - focus on execution logic

## Problem Analysis

The current test suite lacks integration tests for:
1. **Multi-wave scenarios**: No tests verify issues are grouped and executed in correct wave order
2. **Error recovery**: Only unit tests for exception handling, no integration tests for actual flow
3. **Dependency handling**: `DependencyGraph` has tests, but no integration with sprint execution
4. **Edge cases**: No tests for empty waves, single-issue sprints, or fully-filtered sprints

## Solution Approach

Expand `test_sprint_integration.py` with new test classes that:
1. Use `_setup_test_project()` pattern for consistent project setup
2. Mock subprocess calls to isolate from external commands
3. Create test fixtures with explicit dependencies (blocked_by fields)
4. Verify wave ordering and parallel execution grouping
5. Test state persistence through simulated failures

## Implementation Phases

### Phase 1: Multi-Wave Execution Tests

#### Overview
Add `TestMultiWaveExecution` class with tests for wave ordering and parallel grouping.

#### Changes Required

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add new test class after existing tests

```python
class TestMultiWaveExecution:
    """Integration tests for multi-wave sprint execution."""

    @staticmethod
    def _setup_multi_wave_project(tmp_path: Path) -> tuple[Path, Any, Any]:
        """Set up project with issues having dependencies."""
        # Creates:
        # - BUG-001: no blockers (Wave 1)
        # - BUG-002: blocked by BUG-001 (Wave 2)
        # - FEAT-001: blocked by BUG-001 (Wave 2)
        # - FEAT-002: blocked by BUG-002 and FEAT-001 (Wave 3)

    def test_sprint_run_multiple_waves(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint with 3 waves executes in correct order."""

    def test_sprint_wave_composition(self, tmp_path: Path) -> None:
        """Test wave calculation groups parallel issues correctly."""

    def test_sprint_parallel_within_wave(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test issues within same wave are processed together."""
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_sprint_integration.py::TestMultiWaveExecution -v`
- [ ] No regressions: `pytest scripts/tests/test_sprint.py -v`

---

### Phase 2: Error Recovery Tests

#### Overview
Add `TestErrorRecovery` class with tests for issue failure handling and state persistence.

#### Changes Required

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add test class for error recovery scenarios

```python
class TestErrorRecovery:
    """Integration tests for error recovery during sprint execution."""

    def test_sprint_continues_after_issue_failure(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint continues to next issue after single failure."""

    def test_sprint_wave_failure_tracks_correctly(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test failed issues are tracked in state correctly."""

    def test_sprint_state_saved_on_failure(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test state is saved when issue fails."""

    def test_sprint_resume_skips_completed(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test resume skips already-completed issues."""
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_sprint_integration.py::TestErrorRecovery -v`

---

### Phase 3: Dependency Handling Tests

#### Overview
Add `TestDependencyHandling` class with tests for cycle detection and orphan dependencies.

#### Changes Required

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add test class for dependency edge cases

```python
class TestDependencyHandling:
    """Integration tests for dependency handling in sprint execution."""

    def test_sprint_detects_dependency_cycle(self, tmp_path: Path) -> None:
        """Test circular dependencies are detected and reported."""

    def test_sprint_respects_issue_dependencies(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test issues wait for their dependencies."""

    def test_sprint_orphan_dependencies_handled(self, tmp_path: Path) -> None:
        """Test issues depending on non-existent issues are warned."""

    def test_sprint_completed_dependencies_satisfied(self, tmp_path: Path) -> None:
        """Test blockers in completed dir are treated as satisfied."""
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_sprint_integration.py::TestDependencyHandling -v`

---

### Phase 4: Edge Case Tests

#### Overview
Add `TestEdgeCases` class with tests for boundary conditions.

#### Changes Required

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add test class for edge cases

```python
class TestEdgeCases:
    """Integration tests for edge cases in sprint execution."""

    def test_sprint_single_issue(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint with only one issue."""

    def test_sprint_all_issues_skipped(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint where all issues are filtered via --skip."""

    def test_sprint_dry_run_no_execution(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test dry run mode makes no actual changes."""

    def test_sprint_empty_sprint(self, tmp_path: Path) -> None:
        """Test sprint with no issues."""
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_sprint_integration.py::TestEdgeCases -v`
- [ ] Full test suite passes: `pytest scripts/tests/test_sprint_integration.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_sprint_integration.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_sprint_integration.py`

---

## Testing Strategy

### Unit Tests
- Already covered in `test_sprint.py` for dataclasses and manager methods
- New integration tests complement existing unit tests

### Integration Tests
- Test `_cmd_sprint_run()` with mocked subprocess execution
- Verify wave calculation via `DependencyGraph.get_execution_waves()`
- Test state persistence and resume capability

## References

- Original issue: `.issues/enhancements/P3-ENH-189-expand-ll-sprint-integration-tests.md`
- Implementation: `scripts/little_loops/cli.py:1729-1969` (`_cmd_sprint_run`)
- Dependency graph: `scripts/little_loops/dependency_graph.py:119-166` (`get_execution_waves`)
- Test patterns: `scripts/tests/test_sprint.py:501-676` (`TestSprintErrorHandling`)
- Subprocess mocks: `scripts/tests/test_subprocess_mocks.py:30-222`

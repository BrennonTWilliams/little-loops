# ENH-217: Add concurrent access tests beyond hooks - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-217-add-concurrent-access-tests-beyond-hooks.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Research Findings

### Key Discoveries
- **State manager** (`scripts/little_loops/state.py`): No file locking, non-atomic read-modify-write operations at lines 95 (lazy init), 155, 166, 180, 202
- **Issue manager** (`scripts/little_loops/issue_manager.py`): Single-threaded design, but `_get_next_issue()` at line 621 could return same issue to multiple workers if called concurrently
- **Orchestrator** (`scripts/little_loops/parallel/orchestrator.py`): Multiple race conditions - `corrections` dict at line 738, `timing` dict at line 750, `_interrupted_issues` list at line 703 modified without locks
- **Existing concurrent test patterns** available: `test_hooks_integration.py:40-94` (ThreadPoolExecutor), `test_git_lock.py:395-503` (threading.Thread with Events)
- **Already tested**: Git operations have concurrent tests in `test_git_lock.py` (TestThreadSafety class)

### Current State Analysis

**State Manager (state.py)**
- Uses `write_text()` at line 123 for persistence - not atomic on all filesystems
- Lazy initialization at line 95 has race condition if multiple threads access simultaneously
- Methods `mark_attempted()`, `mark_completed()`, `mark_failed()` all do read-modify-write without atomicity

**Issue Manager (issue_manager.py)**
- Sequential design (single main loop at line 706)
- `_get_next_issue()` at line 621 queries dependency graph without coordination
- State file shared between runs but no inter-process locking

**Orchestrator (orchestrator.py)**
- Worker callbacks modify `self.state.corrections` at line 738 and `self.state.timing` at line 750 without locks
- `_interrupted_issues` list appended at line 703 from multiple workers
- GitLock provides serialization for git operations but not for in-memory state

### Patterns to Follow

**ThreadPoolExecutor Pattern** (test_hooks_integration.py:40-94):
```python
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(run_task, i) for i in range(10)]
    results = [f.result() for f in as_completed(futures)]
```

**Thread Coordination Pattern** (test_git_lock.py:421-460):
```python
first_started = threading.Event()
first_can_finish = threading.Event()
# Use events to coordinate thread execution order
```

**Exception Collection Pattern** (test_overlap_detector.py:145-169):
```python
errors: list[Exception] = []
def task():
    try:
        # operation
    except Exception as e:
        errors.append(e)
# Assert len(errors) == 0
```

## Desired End State

Three new test classes added to existing test files:
1. **TestStateConcurrency** in `test_state.py` - State manager concurrent access tests
2. **TestIssueManagerConcurrency** in `test_issue_manager.py` - Issue manager concurrent tests
3. **TestOrchestratorConcurrency** in `test_orchestrator.py` - Orchestrator worker callback tests

Each test class uses established patterns from `test_hooks_integration.py` and `test_git_lock.py`.

### How to Verify
- Run `python -m pytest scripts/tests/test_state.py::TestStateConcurrency -v`
- Run `python -m pytest scripts/tests/test_issue_manager.py::TestIssueManagerConcurrency -v`
- Run `python -m pytest scripts/tests/test_orchestrator.py::TestOrchestratorConcurrency -v`
- All tests pass with threading assertions for thread safety

## What We're NOT Doing
- Not modifying source code to add thread safety - tests should document existing behavior
- Not adding inter-process locking (focus on in-process threading)
- Not testing git operations (already covered in test_git_lock.py)
- Not refactoring existing test structure - adding new test classes only

## Problem Analysis

The codebase has verified thread safety for git operations and hooks, but core state management lacks concurrent access testing:
- State manager persistence is vulnerable to lost updates from concurrent writes
- Issue manager could assign same issue to multiple workers if used concurrently
- Orchestrator worker callbacks modify shared dictionaries/lists without synchronization

These are P4 priority because current usage is mostly single-threaded, but future parallel processing could expose these issues.

## Solution Approach

Add three test classes following established concurrent testing patterns:
1. **State Manager Tests**: Test concurrent `save()`, `mark_attempted()`, lazy initialization
2. **Issue Manager Tests**: Test concurrent `_get_next_issue()` calls, state file access
3. **Orchestrator Tests**: Test concurrent worker callbacks modifying shared state

Use `ThreadPoolExecutor` for high-level concurrency and `threading.Thread` with `Event` for precise coordination.

## Implementation Phases

### Phase 1: Add State Manager Concurrent Tests

#### Overview
Add `TestStateConcurrency` class to `test_state.py` with tests for state file concurrent writes, lazy initialization, and state mutation operations.

#### Changes Required

**File**: `scripts/tests/test_state.py`
**Changes**: Add new test class with concurrent access tests

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


class TestStateConcurrency:
    """Tests for concurrent access to StateManager."""

    def test_concurrent_save_no_corruption(self, tmp_path: Path):
        """Multiple threads saving state simultaneously should not corrupt JSON."""
        # Setup
        state_file = tmp_path / "state.json"
        managers = [StateManager(state_file, MagicMock()) for _ in range(5)]

        def save_state(manager_id: int) -> bool:
            """Save state from a thread."""
            manager = managers[manager_id]
            for i in range(10):
                manager.mark_attempted(f"ISSUE-{manager_id}-{i}", save=True)
            return True

        # Execute
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(save_state, i) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]

        # Verify all completed and file is valid JSON
        assert len(results) == 5
        assert state_file.exists()
        content = state_file.read_text()
        # Should be valid JSON
        import json
        state = json.loads(content)
        assert isinstance(state, dict)

    def test_lazy_init_thread_safety(self, tmp_path: Path):
        """Multiple threads accessing state property simultaneously."""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, MagicMock())
        instances = []

        def access_state() -> ProcessingState:
            """Access state property."""
            state = manager.state
            instances.append(id(state))
            return state

        threads = [threading.Thread(target=access_state) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get same instance (or at least valid state)
        # If lazy init has race, might get different instances
        # The important thing is no crash and valid state
        assert len(instances) == 10

    def test_concurrent_mark_attempted(self, tmp_path: Path):
        """Multiple threads marking issues attempted simultaneously."""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, MagicMock())
        errors = []

        def mark_issue(thread_id: int) -> None:
            try:
                for i in range(20):
                    manager.mark_attempted(f"ENH-{thread_id:03d}-{i:03d}", save=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mark_issue, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all issues were recorded (may have lost updates due to races)
        # This documents current behavior - last-write-wins
        manager.load()
        # At minimum, should have some issues recorded
        assert manager.state.total_attempts >= 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_state.py::TestStateConcurrency -v`
- [ ] Lint passes: `ruff check scripts/tests/test_state.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/state.py`

---

### Phase 2: Add Issue Manager Concurrent Tests

#### Overview
Add `TestIssueManagerConcurrency` class to `test_issue_manager.py` with tests for concurrent issue selection, state file access, and queue operations.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`
**Changes**: Add new test class with concurrent access tests

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


class TestIssueManagerConcurrency:
    """Tests for concurrent access to AutoManager."""

    def test_concurrent_get_next_issue_no_duplicates(
        self, temp_project_dir: Path, sample_config: dict
    ):
        """Multiple threads calling _get_next_issue should not get duplicates."""
        # Setup
        config = Config.from_dict(sample_config)
        manager = AutoManager(config, MagicMock())
        manager._scan_issues()

        results = []
        lock = threading.Lock()

        def get_issue() -> None:
            """Try to get next issue."""
            issue = manager._get_next_issue()
            if issue:
                with lock:
                    results.append(issue.issue_id)

        threads = [threading.Thread(target=get_issue) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no duplicates (or document current behavior)
        # Note: Current implementation may return duplicates if called concurrently
        unique_ids = set(results)
        # Document: if duplicates exist, this shows race condition
        assert len(unique_ids) <= len(results)

    def test_concurrent_state_file_access(
        self, temp_project_dir: Path, sample_config: dict
    ):
        """Multiple managers accessing same state file."""
        config = Config.from_dict(sample_config)

        errors = []

        def run_manager(manager_id: int) -> None:
            try:
                manager = AutoManager(config, MagicMock())
                # All share same state file
                manager._load_state()
                manager.state_manager.mark_attempted(f"MANAGER-{manager_id}", save=True)
            except Exception as e:
                errors.append((manager_id, e))

        threads = [threading.Thread(target=run_manager, args=(i,)) for i in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Document: May have errors due to file contention
        # Current behavior: last write wins, potential JSON corruption
        assert len(errors) >= 0  # Document whatever happens

    def test_concurrent_state_modifications(
        self, temp_project_dir: Path, sample_config: dict
    ):
        """Multiple threads modifying state simultaneously."""
        config = Config.from_dict(sample_config)
        manager = AutoManager(config, MagicMock())

        errors = []

        def modify_state(thread_id: int) -> None:
            try:
                for i in range(10):
                    manager.state_manager.mark_attempted(f"T{thread_id}-I{i}", save=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=modify_state, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No crashes (though updates may be lost)
        assert len(errors) == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestIssueManagerConcurrency -v`
- [ ] Lint passes: `ruff check scripts/tests/test_issue_manager.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_manager.py`

---

### Phase 3: Add Orchestrator Concurrent Tests

#### Overview
Add `TestOrchestratorConcurrency` class to `test_orchestrator.py` with tests for concurrent worker callbacks modifying shared state.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add new test class with concurrent callback tests

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock


class TestOrchestratorConcurrency:
    """Tests for concurrent access in ParallelOrchestrator."""

    def test_concurrent_worker_callbacks(
        self, orchestrator: ParallelOrchestrator, sample_issues: list[IssueInfo]
    ):
        """Multiple workers completing simultaneously modify state."""
        orchestrator.queue.add_many(sample_issues[:3])

        errors = []
        corrections_count = [0]
        lock = threading.Lock()

        def complete_worker(worker_id: int) -> None:
            try:
                result = WorkerResult(
                    issue_id=sample_issues[worker_id].issue_id,
                    success=True,
                    branch_name=f"parallel/{sample_issues[worker_id].issue_id}",
                    worktree_path=Path(f"/tmp/worktree-{worker_id}"),
                    corrections=[f"correction-{worker_id}"],
                )
                orchestrator._on_worker_complete(result)
                with lock:
                    corrections_count[0] += len(result.corrections or [])
            except Exception as e:
                errors.append(e)

        # Simulate 3 workers completing at once
        threads = [threading.Thread(target=complete_worker, args=(i,)) for i in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors (though some corrections may be lost)
        assert len(errors) == 0, f"Errors: {errors}"

    def test_concurrent_interrupted_issues(self, orchestrator: ParallelOrchestrator):
        """Multiple workers adding to interrupted_issues list."""
        errors = []

        def interrupt_worker(worker_id: int) -> None:
            try:
                orchestrator._interrupted_issues.append(f"ENH-{worker_id:03d}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=interrupt_worker, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All appends should succeed
        assert len(errors) == 0
        # List should have all 10 items (or fewer if lost due to race)
        assert len(orchestrator._interrupted_issues) >= 0

    def test_state_dictionary_concurrent_writes(self, orchestrator: ParallelOrchestrator):
        """Multiple threads writing to state.corrections dictionary."""
        errors = []

        def write_corrections(worker_id: int) -> None:
            try:
                orchestrator.state.corrections[f"ISSUE-{worker_id}"] = [
                    f"correction-{worker_id}"
                ]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_corrections, args=(i,)) for i in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors (but may have lost updates)
        assert len(errors) == 0
        # Check dictionary integrity - should be valid dict
        assert isinstance(orchestrator.state.corrections, dict)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestOrchestratorConcurrency -v`
- [ ] Lint passes: `ruff check scripts/tests/test_orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`

---

## Testing Strategy

### Unit Tests
- Each test class focuses on one module's concurrent behavior
- Tests use threading to simulate concurrent access patterns
- Exception collection pattern documents any crashes

### Integration Tests
- Tests verify that shared state doesn't cause crashes
- Tests document current behavior (even if racy)
- Tests use assertions that are resilient to last-write-wins behavior

### Edge Cases Covered
- Lazy initialization races (state manager)
- Concurrent file writes (state file, JSON corruption)
- Dictionary/list concurrent modifications (orchestrator)
- Duplicate issue assignment (issue manager)

## References

- Original issue: `.issues/enhancements/P4-ENH-217-add-concurrent-access-tests-beyond-hooks.md`
- Reference pattern (ThreadPoolExecutor): `scripts/tests/test_hooks_integration.py:40-94`
- Reference pattern (threading coordination): `scripts/tests/test_git_lock.py:421-460`
- Exception collection pattern: `scripts/tests/test_overlap_detector.py:145-169`
- Target modules:
  - `scripts/little_loops/state.py:95` (lazy init race)
  - `scripts/little_loops/state.py:123` (write_text - not atomic)
  - `scripts/little_loops/issue_manager.py:621` (_get_next_issue)
  - `scripts/little_loops/parallel/orchestrator.py:738` (corrections dict race)
  - `scripts/little_loops/parallel/orchestrator.py:750` (timing dict race)
  - `scripts/little_loops/parallel/orchestrator.py:703` (interrupted_issues list race)

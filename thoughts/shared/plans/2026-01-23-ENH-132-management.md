# ENH-132: Add tests for parallel types module - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-132-parallel-types-test-coverage.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `scripts/little_loops/parallel/types.py` module (403 lines) has no test coverage. It defines:

### Key Discoveries
- `QueuedIssue` at types.py:19-48 - Priority queue wrapper with `__lt__` for ordering, `to_dict()` but no `from_dict()`
- `WorkerResult` at types.py:51-132 - Full serialization with both `to_dict()` and `from_dict()`
- `MergeStatus` at types.py:135-143 - Enum with 6 status values
- `MergeRequest` at types.py:146-172 - Merge tracking, `to_dict()` but no `from_dict()`
- `OrchestratorState` at types.py:175-226 - State persistence with full serialization
- `PendingWorktreeInfo` at types.py:229-252 - Worktree tracking with `has_pending_work` property
- `ParallelConfig` at types.py:255-403 - Full serialization plus command template methods

### Patterns to Follow
- Test structure in `test_issue_parser.py:55-202` - individual methods per behavior
- Fixtures for IssueInfo in `test_priority_queue.py:37-94`
- WorkerResult tests in `test_worker_pool.py:114-157` - tests defaults and serialization

## Desired End State

- `scripts/tests/test_parallel_types.py` exists with comprehensive tests
- >85% line coverage for `parallel/types.py`
- All serialization roundtrips verified
- Priority ordering tested

### How to Verify
- `pytest scripts/tests/test_parallel_types.py -v` passes
- `pytest scripts/tests/test_parallel_types.py --cov=little_loops.parallel.types` shows >85%

## What We're NOT Doing

- Not testing priority queue behavior (covered in `test_priority_queue.py`)
- Not testing integration with orchestrator (separate module)
- Not adding `from_dict()` methods to classes that lack them

## Solution Approach

Create a comprehensive test file following existing patterns:
1. Use pytest fixtures for reusable IssueInfo objects
2. Test each dataclass independently
3. Focus on serialization roundtrips, default values, and computed properties

## Implementation Phases

### Phase 1: Create Test File with Fixtures and QueuedIssue Tests

#### Overview
Create the test file with fixtures and tests for QueuedIssue

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Create new file with:
- Imports and fixtures
- `TestQueuedIssue` class with tests for:
  - Creation with all fields
  - Priority ordering (`__lt__`)
  - Timestamp FIFO ordering
  - `to_dict()` serialization
  - Default timestamp handling

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestQueuedIssue -v`

---

### Phase 2: WorkerResult Tests

#### Overview
Add comprehensive tests for WorkerResult dataclass

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Add `TestWorkerResult` class with tests for:
- Creation with required fields
- Default values for optional fields
- `to_dict()` serialization
- `from_dict()` deserialization
- Roundtrip serialization
- Backward compatibility (missing optional fields in dict)
- Path conversion (str <-> Path)

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestWorkerResult -v`

---

### Phase 3: MergeStatus and MergeRequest Tests

#### Overview
Add tests for MergeStatus enum and MergeRequest dataclass

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Add tests for:
- `TestMergeStatus`: enum values, value access
- `TestMergeRequest`: creation, defaults, `to_dict()`

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestMergeStatus -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestMergeRequest -v`

---

### Phase 4: OrchestratorState Tests

#### Overview
Add tests for OrchestratorState with full serialization coverage

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Add `TestOrchestratorState` class with tests for:
- Default values (empty lists/dicts)
- `to_dict()` serialization
- `from_dict()` deserialization
- Roundtrip serialization
- Partial state recovery (missing fields)

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestOrchestratorState -v`

---

### Phase 5: PendingWorktreeInfo Tests

#### Overview
Add tests for PendingWorktreeInfo including `has_pending_work` property

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Add `TestPendingWorktreeInfo` class with tests for:
- Creation with all fields
- Default values
- `has_pending_work` property logic (commits_ahead > 0 OR has_uncommitted_changes)

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestPendingWorktreeInfo -v`

---

### Phase 6: ParallelConfig Tests

#### Overview
Add comprehensive tests for ParallelConfig including command template methods

#### Changes Required

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Add `TestParallelConfig` class with tests for:
- Default values
- `get_ready_command()` template building
- `get_manage_command()` template building
- `to_dict()` serialization
- `from_dict()` deserialization
- Roundtrip serialization
- Path conversion
- Set conversion (only_ids, skip_ids)

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py::TestParallelConfig -v`
- [ ] Full test pass: `python -m pytest scripts/tests/test_parallel_types.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_parallel_types.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_parallel_types.py`

---

## Testing Strategy

### Unit Tests
- Each dataclass tested independently
- Serialization roundtrips for all types with `to_dict()`/`from_dict()`
- Default value verification
- Computed property logic (`priority_int`, `has_pending_work`)

### Edge Cases
- Empty/None values in optional fields
- Missing fields during deserialization (backward compatibility)
- Path <-> string conversions
- Set <-> list conversions for ID filters

## References

- Original issue: `.issues/enhancements/P3-ENH-132-parallel-types-test-coverage.md`
- Target module: `scripts/little_loops/parallel/types.py`
- Pattern: `scripts/tests/test_issue_parser.py:55-202`
- Pattern: `scripts/tests/test_worker_pool.py:114-157`

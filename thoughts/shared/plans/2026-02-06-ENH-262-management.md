# ENH-262: Add real-time worktree progress visibility during parallel execution - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-262-worktree-progress-visibility-during-parallel-execution.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The parallel execution system processes multiple issues concurrently using isolated git worktrees managed by a thread pool. The orchestrator dispatches issues to workers, which process them through multiple stages (worktree setup → ready_issue validation → manage_issue implementation → verification → merge). Currently, progress visibility is limited to logging at key lifecycle transitions, with no real-time status updates showing which workers are active and what stage each worker is in.

### Key Discoveries

From research analysis, the following patterns and integration points were identified:

**File**: `scripts/little_loops/parallel/types.py`
- `WorkerStage` enum needs to be added to track processing stages (lines 52-133: WorkerResult dataclass)
- No explicit stage tracking exists currently

**File**: `scripts/little_loops/parallel/worker_pool.py`
- `_process_issue()` method (lines 222-455) contains all worker stages but no explicit state emission
- `stream_subprocess_output` config flag (line 631) controls subprocess output visibility
- Workers are tracked via `self._active_workers: dict[str, Future[WorkerResult]]` (line 81)
- Active worktrees tracked via `self._active_worktrees: set[Path]` (line 85)

**File**: `scripts/little_loops/parallel/orchestrator.py`
- Main dispatch loop at `_execute()` (lines 565-595) with 0.1s sleep interval
- Ideal location for periodic status reporting
- `_on_worker_complete()` callback (lines 688-752) already logs completion
- `self._issue_info_by_id: dict[str, IssueInfo]` (line 99) provides metadata

**File**: `scripts/little_loops/logger.py`
- Simple Logger class with color-coded output (lines 12-90)
- ANSI color codes: CYAN (info), GREEN (success), YELLOW (warning), RED (error), MAGENTA (timing), GRAY (debug)
- No overwriting or live-update capability

### Pattern Discovered in Codebase

**FSM Executor Event Callback** (`scripts/little_loops/fsm/executor.py:675-682`):
```python
def _emit(self, event: str, data: dict[str, Any]) -> None:
    """Emit an event via the callback."""
    self.event_callback(
        {
            "event": event,
            "ts": _iso_now(),
            **data,
        }
    )
```
This event-driven pattern is used for FSM loop progress tracking and can be adapted for worker stage tracking.

### Current Behavior
- Workers run in parallel with minimal real-time status output
- Main loop runs every 0.1 seconds but only saves state (line 592)
- Progress information is only available after completion or by manually inspecting log files
- No visibility into which stage each worker is in

## Desired End State

Users will see real-time CLI output showing:
1. Each worktree's current status (setup, validating, implementing, verifying, merging, completed, failed)
2. Periodic progress updates indicating which issue each worker is processing and what phase it's in
3. Summary line showing overall progress (e.g., "3/8 issues complete, 4 in progress, 1 queued, 2 pending merge")
4. Works for both `ll-parallel` and `ll-sprint` execution modes

### How to Verify
- Run `ll-parallel` or `ll-sprint` with multiple issues
- Observe periodic status updates during execution showing active workers and their stages
- Confirm completion/failure counts update in real-time
- Test with `--verbose` and without to confirm optional behavior

## What We're NOT Doing

- **Not adding a rich library dependency** - keeping it simple with existing Logger patterns
- **Not changing core processing logic** - this is purely additive for visibility
- **Not implementing a live-updating progress bar** - that would require complex terminal handling and rich library
- **Not tracking detailed sub-stages** - only high-level worker stages (setup, validate, implement, verify, merge)
- **Deferring per-worker subprocess output** - subprocess streaming already exists via `stream_subprocess_output` flag

## Problem Analysis

The root issue is that while the orchestrator has access to all state information (active workers, queue status, merge status), it never emits this information to the user during execution. The main loop runs every 0.1 seconds but only performs two actions:
1. Check if workers are available and dispatch next issue
2. Save state to file

There is no explicit tracking of which processing stage each worker is in - the stages are implicit in the code flow of `_process_issue()`.

## Solution Approach

Based on existing patterns in the codebase, the solution will:

1. **Add worker stage enum and tracking** - Create a `WorkerStage` enum and thread-safe tracking in WorkerPool
2. **Emit stage events during processing** - Update stage at key points in `_process_issue()`
3. **Add periodic status reporting** - Add a status reporter in the orchestrator's main loop
4. **Use existing Logger patterns** - Color-coded, timestamped status output

The approach follows the FSM executor event callback pattern but adapted for worker lifecycle events. Status updates will be simple line-based output (not overwriting) to avoid terminal complexity.

## Implementation Phases

### Phase 1: Add Worker Stage Enum and Type Definitions

#### Overview
Add a `WorkerStage` enum to track processing stages and extend data structures to support stage tracking.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Add WorkerStage enum after MergeStatus enum (around line 144)

```python
class WorkerStage(Enum):
    """Processing stage of a worker.

    Stages progress in order:
    - SETUP: Creating git worktree and copying .claude/ directory
    - VALIDATING: Running ready_issue command
    - IMPLEMENTING: Running manage_issue command
    - VERIFYING: Checking work was done and updating branch base
    - MERGING: Awaiting merge coordination
    - COMPLETED: Successfully finished
    - FAILED: Failed at some stage
    - INTERRUPTED: Interrupted during shutdown
    """

    SETUP = "setup"
    VALIDATING = "validating"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_parallel_types.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/types.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/types.py`

---

### Phase 2: Add Stage Tracking to WorkerPool

#### Overview
Add thread-safe stage tracking to WorkerPool with methods to update and query worker stages.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**: Add stage tracking dictionary and update method

1. Add instance variable in `__init__` (around line 92):
```python
self._worker_stages: dict[str, WorkerStage] = {}  # issue_id -> current stage
```

2. Add properties/methods after `active_count` property (around line 1070):
```python
def set_worker_stage(self, issue_id: str, stage: WorkerStage) -> None:
    """Update the stage of a worker.

    Args:
        issue_id: Issue ID being processed
        stage: New stage value
    """
    with self._process_lock:
        self._worker_stages[issue_id] = stage

def get_worker_stage(self, issue_id: str) -> WorkerStage | None:
    """Get the current stage of a worker.

    Args:
        issue_id: Issue ID being processed

    Returns:
        Current stage, or None if issue not being tracked
    """
    with self._process_lock:
        return self._worker_stages.get(issue_id)

def get_active_stages(self) -> dict[str, WorkerStage]:
    """Get all active worker stages.

    Returns:
        Dictionary mapping issue_id to current stage for active workers
    """
    with self._process_lock:
        # Only return workers that are actually active
        active_ids = set(self._active_workers.keys())
        return {
            issue_id: stage
            for issue_id, stage in self._worker_stages.items()
            if issue_id in active_ids
        }

def remove_worker_stage(self, issue_id: str) -> None:
    """Remove a worker from stage tracking.

    Args:
        issue_id: Issue ID to remove
    """
    with self._process_lock:
        self._worker_stages.pop(issue_id, None)
```

3. Import WorkerStage at top of file:
```python
from little_loops.parallel.types import (
    ParallelConfig,
    QueuedIssue,
    WorkerResult,
    WorkerStage,  # Add this
)
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/worker_pool.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/worker_pool.py`

---

### Phase 3: Emit Stage Events During Worker Processing

#### Overview
Update `_process_issue()` method to emit stage events at key processing points.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**: Add `set_worker_stage()` calls throughout `_process_issue()` method

1. At start of `_process_issue()` (after line 231, after `start_time = time.time()`):
```python
self.set_worker_stage(issue.issue_id, WorkerStage.SETUP)
```

2. After worktree setup (after line 250, after `self._active_worktrees.add(worktree_path)`):
```python
self.set_worker_stage(issue.issue_id, WorkerStage.VALIDATING)
```

3. After ready_issue validation passes (after line 328, before getting action):
```python
self.set_worker_stage(issue.issue_id, WorkerStage.IMPLEMENTING)
```

4. After manage_issue completes (after line 345, before shutdown check):
```python
self.set_worker_stage(issue.issue_id, WorkerStage.VERIFYING)
```

5. Before returning success result (after line 425, in the success return branch):
```python
self.set_worker_stage(issue.issue_id, WorkerStage.MERGING)
```

6. Update `finally` block (line 452-454) to clean up stage:
```python
finally:
    with self._process_lock:
        self._active_worktrees.discard(worktree_path)
    # Don't remove stage here - orchestrator needs it for status reporting
```

7. Add stage cleanup in `_handle_completion` before callback (around line 212):
```python
# Clean up stage tracking after result is available
if result.success:
    self.set_worker_stage(issue_id, WorkerStage.COMPLETED)
elif result.interrupted:
    self.set_worker_stage(issue_id, WorkerStage.INTERRUPTED)
else:
    self.set_worker_stage(issue_id, WorkerStage.FAILED)
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/worker_pool.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/worker_pool.py`

---

### Phase 4: Add Status Reporter to Orchestrator

#### Overview
Add a method to generate and display periodic status updates in the orchestrator's main loop.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Add status reporting method and periodic updates

1. Add tracking variable in `__init__` (around line 108):
```python
self._last_status_time: float = 0.0
```

2. Add status reporting method (around line 540, before `_execute`):
```python
def _maybe_report_status(self) -> None:
    """Report status if enough time has elapsed since last report.

    Reports every 5 seconds during active processing.
    """
    now = time.time()
    # Report every 5 seconds
    if now - self._last_status_time < 5.0:
        return

    self._last_status_time = now

    # Build status line
    parts = []

    # Queued count (estimate from queue size - private but we can infer)
    # We'll use what's available: completed, failed, in_progress
    in_progress = len(self.queue.in_progress_ids)
    completed = self.queue.completed_count
    failed = self.queue.failed_count
    pending_merge = self.merge_coordinator.pending_count

    # Get active worker stages
    active_stages = self.worker_pool.get_active_stages()

    parts.append(f"Active: {in_progress}")
    parts.append(f"Done: {completed}")
    if failed > 0:
        parts.append(f"Failed: {failed}")
    if pending_merge > 0:
        parts.append(f"Merging: {pending_merge}")

    # Build status line
    status = " | ".join(parts)

    # Add worker details if any are active
    if active_stages:
        # Group by stage
        by_stage: dict[WorkerStage, list[str]] = {}
        for issue_id, stage in active_stages.items():
            by_stage.setdefault(stage, []).append(issue_id)

        stage_parts = []
        for stage in [WorkerStage.VALIDATING, WorkerStage.IMPLEMENTING, WorkerStage.VERIFYING]:
            if stage in by_stage:
                issue_ids = ", ".join(by_stage[stage])
                stage_name = stage.value.title()
                stage_parts.append(f"{stage_name}: [{issue_ids}]")

        if stage_parts:
            status += " | " + " | ".join(stage_parts)

    # Log with gray color to distinguish from normal logs
    if self.logger.use_color:
        color = self.logger.GRAY
        ts = self.logger._timestamp()
        print(f"{color}[{ts}]{self.logger.RESET} {status}")
    else:
        self.logger.info(status)
```

3. Call status reporter in main loop (replace line 592-595):
```python
# Save state periodically
self._save_state()

# Report status periodically
self._maybe_report_status()

# Small sleep to prevent busy loop
time.sleep(0.1)
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`
- [ ] Manual: Run `ll-parallel` and observe status updates every 5 seconds

---

### Phase 5: Add Issue Title to Status Display

#### Overview
Enhance status display to show issue titles for better context.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Update `_maybe_report_status()` to include issue titles

Modify the stage_parts building section to include titles:
```python
if active_stages:
    # Group by stage
    by_stage: dict[WorkerStage, list[str]] = {}
    for issue_id, stage in active_stages.items():
        by_stage.setdefault(stage, []).append(issue_id)

    stage_parts = []
    for stage in [WorkerStage.VALIDATING, WorkerStage.IMPLEMENTING, WorkerStage.VERIFYING]:
        if stage in by_stage:
            issue_ids = ", ".join(by_stage[stage])
            stage_name = stage.value.title()
            # Format: "Implementing: [BUG-123, FEAT-456]"
            stage_parts.append(f"{stage_name}: [{issue_ids}]")

    if stage_parts:
        status += " | " + " | ".join(stage_parts)
```

Note: Issue titles are available via `self._issue_info_by_id` but including full titles would make the status line too long. We'll stick to issue IDs for brevity.

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`
- [ ] Manual: Run `ll-parallel` and verify status shows issue IDs by stage

---

### Phase 6: Cleanup Stages on Completion

#### Overview
Ensure worker stages are cleaned up when workers complete to prevent memory buildup.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Clean up stage tracking in `_on_worker_complete()` callback

Add at the end of `_on_worker_complete()` (after line 752):
```python
# Clean up stage tracking after a delay
# We keep the stage for a bit so status reporter can show completion
import threading
def cleanup_stage(issue_id: str) -> None:
    time.sleep(2.0)  # Keep stage visible for 2 seconds
    self.worker_pool.remove_worker_stage(issue_id)

cleanup_thread = threading.Thread(target=cleanup_stage, args=(result.issue_id,))
cleanup_thread.daemon = True
cleanup_thread.start()
```

Actually, let's simplify - just remove immediately but the status has already been logged:
```python
# Clean up stage tracking
self.worker_pool.remove_worker_stage(result.issue_id)
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`

---

### Phase 7: Support for Sprint Wave Context

#### Overview
Include wave label in status output when running under ll-sprint.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Update `_maybe_report_status()` to include wave context

Modify the status building to include wave label if present:
```python
def _maybe_report_status(self) -> None:
    """Report status if enough time has elapsed since last report.

    Reports every 5 seconds during active processing.
    """
    now = time.time()
    # Report every 5 seconds
    if now - self._last_status_time < 5.0:
        return

    self._last_status_time = now

    # Build status line
    parts = []

    # Add wave label if present
    if self.wave_label:
        parts.append(f"{self.wave_label}")

    # Rest of status building...
    in_progress = len(self.queue.in_progress_ids)
    completed = self.queue.completed_count
    failed = self.queue.failed_count
    pending_merge = self.merge_coordinator.pending_count

    parts.append(f"Active: {in_progress}")
    parts.append(f"Done: {completed}")
    # ... rest of the code
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`
- [ ] Manual: Run `ll-sprint` and verify wave label appears in status

---

### Phase 8: Add Tests

#### Overview
Add unit tests for new stage tracking functionality.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add tests for stage tracking

```python
def test_worker_stage_tracking(worker_pool: WorkerPool) -> None:
    """Test that worker stages are tracked correctly."""
    from little_loops.parallel.types import WorkerStage

    # Initially no stages
    assert worker_pool.get_active_stages() == {}

    # Set a stage
    worker_pool.set_worker_stage("BUG-123", WorkerStage.IMPLEMENTING)
    assert worker_pool.get_worker_stage("BUG-123") == WorkerStage.IMPLEMENTING

    # Get active stages (empty since no actual worker)
    # We need to test the methods work
    assert worker_pool.get_worker_stage("NONEXISTENT") is None

    # Remove stage
    worker_pool.remove_worker_stage("BUG-123")
    assert worker_pool.get_worker_stage("BUG-123") is None
```

**File**: `scripts/tests/test_parallel_types.py`
**Changes**: Add test for WorkerStage enum

```python
def test_worker_stage_enum() -> None:
    """Test WorkerStage enum values."""
    from little_loops.parallel.types import WorkerStage

    assert WorkerStage.SETUP.value == "setup"
    assert WorkerStage.VALIDATING.value == "validating"
    assert WorkerStage.IMPLEMENTING.value == "implementing"
    assert WorkerStage.VERIFYING.value == "verifying"
    assert WorkerStage.MERGING.value == "merging"
    assert WorkerStage.COMPLETED.value == "completed"
    assert WorkerStage.FAILED.value == "failed"
    assert WorkerStage.INTERRUPTED.value == "interrupted"
```

**Success Criteria**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_worker_pool.py scripts/tests/test_parallel_types.py -v`
- [ ] Lint passes: `ruff check scripts/tests/`
- [ ] Types pass: `python -m mypy scripts/tests/`

---

## Testing Strategy

### Unit Tests
- WorkerStage enum values
- WorkerPool stage tracking methods (set, get, remove, get_active)
- Thread safety of stage updates

### Integration Tests
- Run ll-parallel with multiple issues and verify status output
- Run ll-sprint and verify wave context in status
- Verify stage transitions during actual worker execution

### Manual Verification
- Run `ll-parallel --max-workers 2` with 4+ issues
- Observe status updates every 5 seconds
- Verify stages progress: SETUP → VALIDATING → IMPLEMENTING → VERIFYING → MERGING → COMPLETED
- Verify failed/interrupted stages are shown
- Run `ll-sprint` and verify wave label appears

## References

- Original issue: `.issues/enhancements/P3-ENH-262-worktree-progress-visibility-during-parallel-execution.md`
- FSM event callback pattern: `scripts/little_loops/fsm/executor.py:675-682`
- CLI progress display: `scripts/little_loops/cli.py:698-738`
- Logger class: `scripts/little_loops/logger.py:12-90`
- Orchestrator main loop: `scripts/little_loops/parallel/orchestrator.py:565-595`
- Worker processing stages: `scripts/little_loops/parallel/worker_pool.py:222-455`

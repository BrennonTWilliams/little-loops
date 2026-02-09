# BUG-307: Sprint state marks all wave issues as completed even when some fail - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-307-sprint-state-marks-all-wave-issues-completed-on-failure.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

In `_cmd_sprint_run()` at `cli.py:1967-1988`, after `orchestrator.run()` returns, the sprint runner only uses the scalar return code (0 or 1) to decide how to update sprint state. It does not query the orchestrator's per-issue results.

### Key Discoveries
- `cli.py:1971-1988` — Both success and failure paths add ALL `wave_ids` to `state.completed_issues`
- `cli.py:1986-1987` — Failure path also adds ALL `wave_ids` to `state.failed_issues` with generic message
- `priority_queue.py:184-194` — `completed_ids` and `failed_ids` properties expose accurate per-issue results
- `orchestrator.py:474-478` — `_save_state()` demonstrates the correct pattern: reading `self.queue.completed_ids` and `self.queue.failed_ids`
- `cli.py:1860-1866` — Resume logic uses `state.completed_issues` as a set; false entries prevent retrying stranded issues

## Desired End State

After a multi-issue wave completes, `state.completed_issues` contains only issues that actually completed (merged), `state.failed_issues` contains only issues that actually failed, and issues that were neither (interrupted/stranded) remain untracked for retry on resume.

### How to Verify
- Unit test: MockOrchestrator with partial success (some completed, some failed) verifies state has correct per-issue breakdown
- Existing tests updated to assert per-issue accuracy

## What We're NOT Doing

- Not changing single-issue wave path (lines 1923-1944) — it already tracks the single issue correctly
- Not changing `SprintState` dataclass — its fields are fine, just populated incorrectly
- Not adding per-issue timing from orchestrator — timing improvement is out of scope

## Problem Analysis

The root cause is that `_cmd_sprint_run()` treats wave-level exit codes as the only signal, ignoring the per-issue `orchestrator.queue.completed_ids` and `orchestrator.queue.failed_ids` that are available after `run()` returns.

## Solution Approach

Replace the all-or-nothing wave tracking (lines 1970-1988) with per-issue tracking that reads `orchestrator.queue.completed_ids` and `orchestrator.queue.failed_ids` after each wave completes.

## Code Reuse & Integration

- **Reusable existing code**: `orchestrator.queue.completed_ids` and `orchestrator.queue.failed_ids` at `priority_queue.py:184-194` — use as-is
- **Pattern to follow**: `orchestrator.py:474-478` (`_save_state()`) — demonstrates reading queue for per-issue state
- **New code justification**: Only new logic is the replacement block in `_cmd_sprint_run` — no new modules needed

## Implementation Phases

### Phase 1: Fix Multi-Issue Wave Tracking in `_cmd_sprint_run()`

#### Overview
Replace lines 1970-1988 in `cli.py` with per-issue tracking that reads from the orchestrator's queue.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Replace the `if result == 0` / `else` block (lines 1970-1988) with per-issue tracking

Current code (lines 1970-1988):
```python
                # Track completed/failed from this wave
                if result == 0:
                    completed.update(wave_ids)
                    state.completed_issues.extend(wave_ids)
                    for issue_id in wave_ids:
                        state.timing[issue_id] = {
                            "total": orchestrator.execution_duration / len(wave)
                        }
                    logger.success(
                        f"Wave {wave_num}/{total_waves} completed: {', '.join(wave_ids)}"
                    )
                else:
                    # Some issues failed - continue but track failures
                    failed_waves += 1
                    completed.update(wave_ids)
                    state.completed_issues.extend(wave_ids)
                    for issue_id in wave_ids:
                        state.failed_issues[issue_id] = "Wave execution had failures"
                    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
```

New code:
```python
                # Track completed/failed from this wave using per-issue results
                actually_completed = set(orchestrator.queue.completed_ids)
                actually_failed = set(orchestrator.queue.failed_ids)

                # Add only actually-completed issues to state
                for issue_id in wave_ids:
                    if issue_id in actually_completed:
                        completed.add(issue_id)
                        state.completed_issues.append(issue_id)
                        state.timing[issue_id] = {
                            "total": orchestrator.execution_duration / len(wave)
                        }
                    elif issue_id in actually_failed:
                        completed.add(issue_id)
                        state.completed_issues.append(issue_id)
                        state.failed_issues[issue_id] = "Issue failed during wave execution"
                    # else: issue was neither completed nor failed (interrupted/stranded)
                    # — leave untracked so it can be retried on resume

                if result == 0:
                    logger.success(
                        f"Wave {wave_num}/{total_waves} completed: {', '.join(wave_ids)}"
                    )
                else:
                    failed_waves += 1
                    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
```

Key design decisions:
- Failed issues are still added to `completed` set and `state.completed_issues` — this is intentional because `completed` tracks "processed" issues (both succeeded and failed) to prevent re-processing in the same run. The `state.failed_issues` dict distinguishes failures from successes.
- Interrupted/stranded issues (not in either queue list) are NOT added to `completed` or `state.completed_issues`, allowing resume to retry them.
- Timing uses the same averaged approach as before (out of scope to improve).

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint_integration.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

---

### Phase 2: Add Test for Per-Issue Tracking

#### Overview
Add a new test that verifies partial wave success is tracked correctly per-issue.

#### Changes Required

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add test method to `TestErrorRecovery` class

```python
def test_sprint_partial_wave_tracks_per_issue(self, tmp_path: Path, monkeypatch: Any) -> None:
    """Test that partial wave success tracks completed and failed issues separately."""
    import argparse
    from little_loops import cli

    _, config, manager = self._setup_error_recovery_project(tmp_path)

    class MockQueue:
        @property
        def completed_ids(self) -> list[str]:
            return ["BUG-001", "BUG-003"]

        @property
        def failed_ids(self) -> list[str]:
            return ["BUG-002"]

    class MockOrchestrator:
        execution_duration = 3.0

        def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
            self.queue = MockQueue()

        def run(self) -> int:
            return 1  # Some failures

    monkeypatch.setattr("little_loops.cli.ParallelOrchestrator", MockOrchestrator)
    monkeypatch.chdir(tmp_path)
    cli._sprint_shutdown_requested = False

    args = argparse.Namespace(
        sprint="recovery-test",
        dry_run=False,
        resume=False,
        skip=None,
        max_workers=3,
        quiet=False,
    )

    result = cli._cmd_sprint_run(args, manager, config)
    assert result == 1

    state_data = json.loads((tmp_path / ".sprint-state.json").read_text())

    # Only actually-completed issues should be in completed_issues
    assert "BUG-001" in state_data["completed_issues"]
    assert "BUG-003" in state_data["completed_issues"]

    # Failed issue should be in both completed_issues (processed) and failed_issues
    assert "BUG-002" in state_data["completed_issues"]
    assert "BUG-002" in state_data["failed_issues"]

    # Only the actually-failed issue should be in failed_issues
    assert "BUG-001" not in state_data["failed_issues"]
    assert "BUG-003" not in state_data["failed_issues"]
```

Also add a test for stranded/interrupted issues:

```python
def test_sprint_stranded_issues_not_marked_completed(self, tmp_path: Path, monkeypatch: Any) -> None:
    """Test that issues neither completed nor failed are left untracked for retry."""
    import argparse
    from little_loops import cli

    _, config, manager = self._setup_error_recovery_project(tmp_path)

    class MockQueue:
        @property
        def completed_ids(self) -> list[str]:
            return ["BUG-001"]  # Only 1 of 3 completed

        @property
        def failed_ids(self) -> list[str]:
            return ["BUG-002"]  # Only 1 of 3 failed
            # BUG-003 is stranded (not in either list)

    class MockOrchestrator:
        execution_duration = 3.0

        def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
            self.queue = MockQueue()

        def run(self) -> int:
            return 1

    monkeypatch.setattr("little_loops.cli.ParallelOrchestrator", MockOrchestrator)
    monkeypatch.chdir(tmp_path)
    cli._sprint_shutdown_requested = False

    args = argparse.Namespace(
        sprint="recovery-test",
        dry_run=False,
        resume=False,
        skip=None,
        max_workers=3,
        quiet=False,
    )

    result = cli._cmd_sprint_run(args, manager, config)

    state_data = json.loads((tmp_path / ".sprint-state.json").read_text())

    # Stranded issue (BUG-003) should NOT be in completed_issues
    assert "BUG-003" not in state_data["completed_issues"]
    assert "BUG-003" not in state_data["failed_issues"]

    # BUG-001 completed, BUG-002 failed — both tracked
    assert "BUG-001" in state_data["completed_issues"]
    assert "BUG-002" in state_data["completed_issues"]
    assert "BUG-002" in state_data["failed_issues"]
```

Also update the existing `test_sprint_wave_failure_tracks_correctly` test to provide a `queue` attribute on its MockOrchestrator:

```python
class MockQueue:
    @property
    def completed_ids(self) -> list[str]:
        return []

    @property
    def failed_ids(self) -> list[str]:
        return ["BUG-001", "BUG-002", "BUG-003"]

class MockOrchestrator:
    execution_duration = 2.0

    def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
        self.queue = MockQueue()

    def run(self) -> int:
        return 1
```

And update the `test_sprint_state_saved_on_failure` test similarly.

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_sprint_integration.py -v -k "per_issue or stranded"`
- [ ] All existing sprint tests still pass: `python -m pytest scripts/tests/test_sprint_integration.py -v`
- [ ] Full test suite: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Partial wave success: 2 of 3 issues complete, 1 fails — verify per-issue tracking
- Stranded issues: 1 complete, 1 fail, 1 stranded — verify stranded not in completed_issues
- All fail: 0 complete, 3 fail — verify all in failed_issues, all in completed_issues
- All succeed: 3 complete, 0 fail — verify all in completed_issues, none in failed_issues

### Integration Concerns
- Existing `MockOrchestrator` tests need `queue` attribute added
- Resume logic (`cli.py:1860-1866`) now correctly handles stranded issues since they won't be in `completed_issues`

## References

- Original issue: `.issues/bugs/P2-BUG-307-sprint-state-marks-all-wave-issues-completed-on-failure.md`
- Correct pattern: `orchestrator.py:474-478` (`_save_state()`)
- Queue properties: `priority_queue.py:184-194`
- Existing failure test: `test_sprint_integration.py:507-551`

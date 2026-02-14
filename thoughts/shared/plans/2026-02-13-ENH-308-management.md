# ENH-308: Sprint Sequential Retry for Merge-Failed Issues

## Summary

Add automatic sequential retry of merge-failed issues after parallel wave execution. When issues fail during a multi-issue parallel wave, retry them one at a time using `process_issue_inplace()` before proceeding to the next wave.

## Research Findings

### Key Code Locations
- **Multi-issue wave processing**: `cli/sprint.py:1062-1111`
- **Single-issue wave processing**: `cli/sprint.py:1032-1061`
- **`process_issue_inplace()`**: `issue_manager.py:249` (signature at line 249, returns `IssueProcessingResult`)
- **Sprint state**: `sprint.py:60-111` (`SprintState` dataclass with `completed_issues`, `failed_issues`, `timing`)
- **Orchestrator queue**: `parallel/priority_queue.py:184-194` (`completed_ids`, `failed_ids` properties)

### Existing Patterns
- Single-issue waves already use `process_issue_inplace()` at `cli/sprint.py:1034-1054`
- State tracking uses dual pattern: `completed_issues` (all attempted) + `failed_issues` (dict with reasons)
- `import` of `process_issue_inplace` is done lazily inside the `if len(wave) == 1:` block

### Design Decisions
- Retry logic goes **after** result tracking (lines 1079-1095) and **before** result code handling (lines 1097-1103)
- Only retry issues in `actually_failed` set — not stranded/interrupted issues
- Use same state tracking pattern as single-issue waves
- Import `process_issue_inplace` at function scope (already lazy-imported in single-issue branch)

## Implementation Plan

### Phase 1: Add retry logic to `_cmd_sprint_run()` (`cli/sprint.py`)

Insert retry block after the per-issue result tracking loop (after line 1095), before the result code check (line 1097):

```python
# Sequential retry for failed issues (ENH-308)
if actually_failed:
    logger.info(
        f"Retrying {len(actually_failed)} failed issue(s) sequentially..."
    )
    from little_loops.issue_manager import process_issue_inplace

    retried_ok = 0
    for issue in wave:
        if issue.issue_id not in actually_failed:
            continue
        logger.info(f"  Retrying {issue.issue_id} in-place...")
        retry_result = process_issue_inplace(
            info=issue,
            config=config,
            logger=logger,
            dry_run=args.dry_run,
        )
        total_duration += retry_result.duration
        if retry_result.success:
            retried_ok += 1
            # Update state: remove from failed, update timing
            state.failed_issues.pop(issue.issue_id, None)
            state.timing[issue.issue_id] = {"total": retry_result.duration}
            logger.success(f"  Retry succeeded: {issue.issue_id}")
        else:
            logger.warning(f"  Retry failed: {issue.issue_id}")
    if retried_ok > 0:
        logger.info(
            f"Sequential retry recovered {retried_ok}/{len(actually_failed)} issue(s)"
        )
```

Key details:
- Only retry issues in `actually_failed` (already tracked in state as failed)
- On retry success: remove from `state.failed_issues`, update timing — but leave in `state.completed_issues` (already there)
- On retry failure: leave as-is (already tracked as failed)
- The `failed_waves` counter and result code check happens after retries, so if all retries succeed, the wave won't be counted as failed

### Phase 2: Adjust `failed_waves` logic

The existing check `if result == 0:` at line 1097 uses orchestrator return code. After retries, we should check whether any issues remain failed:

```python
# Check whether failures remain after retry
remaining_failures = {
    iid for iid in actually_failed if iid in state.failed_issues
}
if result == 0 or (result != 0 and not remaining_failures):
    logger.success(...)
else:
    failed_waves += 1
    logger.warning(...)
```

### Phase 3: Add test for retry behavior

Add test to `test_sprint_integration.py` in the `TestErrorRecovery` class:
- `test_sprint_sequential_retry_after_parallel_failure` — Mock orchestrator to report failures, mock `process_issue_inplace` to succeed on retry, verify state is updated correctly

### Phase 4: Add test for retry that also fails

Add test:
- `test_sprint_sequential_retry_still_fails` — Mock both orchestrator and retry to fail, verify issue stays in `failed_issues`

## Success Criteria

- [ ] Multi-issue wave failures trigger sequential retry via `process_issue_inplace()`
- [ ] Successful retries remove issues from `state.failed_issues`
- [ ] Failed retries leave issues in `state.failed_issues`
- [ ] Wave is not counted as failed if all retries succeed
- [ ] Logging shows retry attempts and outcomes
- [ ] Tests pass for both successful and unsuccessful retry scenarios
- [ ] Existing tests continue to pass
- [ ] Lint, type check pass

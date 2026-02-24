---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-473: Failed single-issue sprint wave corrupts resume state

## Summary

When a single-issue sprint wave fails, the issue ID is added to both `state.completed_issues` and `state.failed_issues`. On `--resume`, the failed issue is treated as "done" and skipped, making the failure invisible to retry.

## Location

- **File**: `scripts/little_loops/cli/sprint.py`
- **Line(s)**: 1239-1243 (at scan commit: 95d4139)
- **Anchor**: `in function cmd_run`, single-issue wave failure handling block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/cli/sprint.py#L1239-L1243)
- **Code**:
```python
else:
    failed_waves += 1
    completed.update(wave_ids)
    state.completed_issues.extend(wave_ids)          # line 1242
    state.failed_issues[wave_ids[0]] = "Issue processing failed"  # line 1243
    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
```

## Current Behavior

When a single-issue wave fails (`issue_result.success` is `False`), the code adds the issue ID to `state.completed_issues` (line 1242) simultaneously with `state.failed_issues` (line 1243). The multi-issue parallel path (lines 1283-1295) explicitly avoids this by only appending to `state.completed_issues` when actually completed.

## Expected Behavior

Failed single-issue waves should NOT be added to `state.completed_issues`. The issue ID should only appear in `state.failed_issues`, allowing `--resume` to retry the failed wave.

## Steps to Reproduce

1. Create a sprint with a single-issue wave that will fail (e.g., an issue with a broken implementation path)
2. Run `ll-sprint run <sprint>`
3. Observe the wave fails
4. Re-run with `ll-sprint run <sprint> --resume`
5. Observe the failed issue wave is skipped (treated as completed)

## Root Cause

- **File**: `scripts/little_loops/cli/sprint.py`
- **Anchor**: `in function cmd_run()`, single-issue wave failure branch
- **Cause**: `state.completed_issues.extend(wave_ids)` at line 1242 unconditionally adds the issue to the completed set regardless of success/failure. The resume logic at line 1161 checks `completed_set = set(state.completed_issues)` to determine which waves to skip.

## Proposed Solution

Remove the `state.completed_issues.extend(wave_ids)` call from the failure branch. Only add to `completed_issues` when the wave actually succeeds:

```python
else:
    failed_waves += 1
    completed.update(wave_ids)  # local tracking for wave progress
    state.failed_issues[wave_ids[0]] = "Issue processing failed"
    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — remove `state.completed_issues.extend(wave_ids)` from single-issue failure branch

### Dependent Files (Callers/Importers)
- N/A — internal state management

### Similar Patterns
- Multi-issue parallel path (lines 1283-1295) already handles this correctly

### Tests
- `scripts/tests/` — add test for single-issue wave failure + resume behavior

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Failed issues silently skipped on resume, data loss risk
- **Effort**: Small — Single line removal
- **Risk**: Low — Aligns single-issue path with existing multi-issue pattern
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `resume`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P2

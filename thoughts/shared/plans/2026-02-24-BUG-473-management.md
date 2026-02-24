# BUG-473: Failed single-issue sprint wave corrupts resume state

## Plan

### Problem
When a sprint wave fails (single-issue or multi-issue), the issue ID is added to both `state.completed_issues` and `state.failed_issues`. On `--resume`, the resume logic at line 1161 builds `completed_set = set(state.completed_issues)` and skips any wave whose issues are a subset — so failed issues are silently skipped.

### Fix

**File**: `scripts/little_loops/cli/sprint.py`

#### Change 1: Single-issue failure branch (line 1242)
Remove `state.completed_issues.extend(wave_ids)` from the `else` (failure) branch at line 1242. Keep:
- `completed.update(wave_ids)` — local tracking for current-run progress display
- `state.failed_issues[wave_ids[0]] = ...` — persistent failure tracking

#### Change 2: Multi-issue failure branch (line 1292)
Remove `state.completed_issues.append(issue_id)` from the `elif issue_id in actually_failed` branch at line 1292. Keep:
- `completed.add(issue_id)` — local tracking
- `state.failed_issues[issue_id] = ...` — persistent failure tracking

#### Change 3: Add regression test
Add test `test_sprint_failed_wave_not_in_completed_issues` to `scripts/tests/test_sprint_integration.py` covering:
1. Single-issue wave fails → issue NOT in `state.completed_issues`, IS in `state.failed_issues`
2. On `--resume`, the failed wave is retried (not skipped)

### Success Criteria
- [ ] Line 1242 removed from single-issue failure branch
- [ ] Line 1292 removed from multi-issue failure branch
- [ ] Regression test passes
- [ ] All existing sprint tests pass

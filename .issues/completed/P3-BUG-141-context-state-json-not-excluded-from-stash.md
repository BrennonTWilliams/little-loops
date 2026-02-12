---
discovered_commit: 841d8e8
discovered_date: 2026-01-24
discovered_source: argobots-ll-parallel-debug.log
discovered_external_repo: <external-repo>
---

# BUG-141: .claude/ll-context-state.json deletions not excluded from stash

## Summary

The merge coordinator's `_stash_local_changes()` method excludes the orchestrator's state file (`ll-config.json` or configured `state_file`) from stashing, but does not exclude `.claude/ll-context-state.json`. This file is managed by Claude Code and frequently appears as deleted in git status, causing unnecessary stash/restore cycling during merges.

## Evidence from Log

**Log File**: `argobots-ll-parallel-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`

### Sample Log Output

```
[18:14:42] Git status output:  D .claude/ll-context-state.json
 M .gitignore

[18:14:42] Tracked files to stash: [' D .claude/ll-context-state.json', ' M .gitignore']
[18:14:42] Stashed local changes before merge
...
[18:14:43] Stashing worktree changes before rebase:  D .claude/ll-context-state.json
...
[18:14:43] Git status output:  D .claude/ll-context-state.json
 M .gitignore

[18:14:43] Tracked files to stash: [' D .claude/ll-context-state.json', ' M .gitignore']
```

The file appears as deleted (`D`) repeatedly across multiple merge operations, causing redundant stash operations.

## Current Behavior

In `merge_coordinator.py:173-174`:

```python
if file_path == state_file_str or file_path.endswith(state_file_name):
    continue  # Skip state file - orchestrator manages it independently
```

This excludes the orchestrator's configured `state_file` (typically `ll-config.json`), but `.claude/ll-context-state.json` is a different file managed by Claude Code itself, not the orchestrator.

## Expected Behavior

The `_stash_local_changes()` method should also exclude `.claude/ll-context-state.json` since:
1. It's Claude Code internal state, not project code
2. It's frequently modified/deleted during Claude operations
3. Including it causes unnecessary stash cycling
4. It has no bearing on the merge outcome

## Affected Components

- **Tool**: ll-parallel
- **Module**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Function**: `_stash_local_changes()` (line ~125-217)

## Proposed Fix

Add exclusion for Claude Code's context state file:

```python
# In _stash_local_changes(), after the state_file check:
if file_path == state_file_str or file_path.endswith(state_file_name):
    continue  # Skip state file - orchestrator manages it independently

# Add this:
if file_path.endswith("ll-context-state.json"):
    continue  # Skip Claude Code context state - managed externally
```

Alternatively, exclude the entire `.claude/` directory from stashing since it contains only configuration and state files, not project code:

```python
if file_path.startswith(".claude/"):
    continue  # Skip Claude Code directory - managed externally
```

## Impact

- **Severity**: Low (P3)
- **Frequency**: High (occurs on every merge when file is deleted)
- **Data Risk**: None - only affects performance/log noise

---

## Labels
- component:parallel
- type:bug

## Status
**Completed** | Created: 2026-01-24 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/merge_coordinator.py`: Added exclusion for `ll-context-state.json` in `_stash_local_changes()` method (lines 186-189). Updated docstring to document the new exclusion.
- `scripts/tests/test_merge_coordinator.py`: Added `test_excludes_claude_context_state_file_from_stash` test to verify the exclusion works correctly.

### Verification Results
- Tests: PASS (53/53)
- Lint: PASS
- Types: PASS

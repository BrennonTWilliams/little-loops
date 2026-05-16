---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# BUG-347: Mutable default aliasing in ProcessingState.from_dict

## Summary

`ProcessingState.from_dict()` passes list/dict values directly from the input `data` dict into the dataclass fields. Mutating the resulting state object's `completed_issues` or `failed_issues` also mutates the original `data` dictionary's values.

## Location

- **File**: `scripts/little_loops/state.py`
- **Line(s)**: 62-73 (at scan commit: be30013)
- **Anchor**: `in ProcessingState.from_dict()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/be30013d0e2446b479c121af1d58a2309b3cfeb5/scripts/little_loops/state.py#L64-L73)
- **Code**:
```python
return cls(
    current_issue=data.get("current_issue", ""),
    phase=data.get("phase", "idle"),
    timestamp=data.get("timestamp", ""),
    completed_issues=data.get("completed_issues", []),
    failed_issues=data.get("failed_issues", {}),
    attempted_issues=set(data.get("attempted_issues", [])),
    timing=data.get("timing", {}),
    corrections=data.get("corrections", {}),
)
```

## Current Behavior

When `data` contains `completed_issues` or `failed_issues` keys, the exact same list/dict object is shared between `data` and the new `ProcessingState` instance.

## Expected Behavior

The `from_dict()` method should create copies of mutable values to prevent aliasing.

## Steps to Reproduce

1. Create a `data` dict with `completed_issues: ["A"]`
2. Call `state = ProcessingState.from_dict(data)`
3. Call `state.completed_issues.append("B")`
4. Observe `data["completed_issues"]` is now `["A", "B"]`

## Actual Behavior

Mutations to the state object propagate to the original data dictionary.

## Root Cause

- **File**: `scripts/little_loops/state.py`
- **Anchor**: `in ProcessingState.from_dict()`
- **Cause**: `dict.get()` returns the original object when the key exists, creating a shared reference

## Proposed Solution

Copy mutable values:
```python
completed_issues=list(data.get("completed_issues", [])),
failed_issues=dict(data.get("failed_issues", {})),
attempted_issues=set(data.get("attempted_issues", [])),
timing={k: dict(v) for k, v in data.get("timing", {}).items()},
corrections={k: list(v) for k, v in data.get("corrections", {}).items()},
```

## Motivation

This bug would:
- Prevent mutation bugs in state management where modifying a `ProcessingState` inadvertently corrupts the source data dictionary
- Business value: Ensures reliable state handling in automated issue processing pipelines
- Technical debt: Eliminates a latent shared-reference hazard that could surface as hard-to-diagnose bugs if callers begin mutating state objects

## Implementation Steps

1. Wrap list/dict values in copy constructors in `ProcessingState.from_dict()` (e.g., `list(data.get(...))`, `dict(data.get(...))`)
2. Add a unit test that verifies mutating the returned state does not alias back to the original `data` dict
3. Verify all existing state tests still pass

## Integration Map

### Files to Modify
- `scripts/little_loops/state.py` — `ProcessingState.from_dict()` method

### Dependent Files (Callers/Importers)
- `scripts/little_loops/state.py` — `StateManager.load()` calls `ProcessingState.from_dict()`
- `scripts/little_loops/issue_manager.py` — uses `StateManager` which wraps `ProcessingState.from_dict()`

### Similar Patterns
- Any other `from_dict()` class methods that pass mutable defaults without copying

### Tests
- `scripts/tests/test_state.py` — add aliasing prevention test verifying mutating returned state does not alias back to the original data dict

### Documentation
- N/A — internal bug fix, no user-facing doc changes

### Configuration
- N/A

## Impact

- **Priority**: P4 - Requires specific usage pattern to trigger; current callers may not mutate
- **Effort**: Small - Two-line change
- **Risk**: Low - Defensive copy is strictly safer
- **Breaking Change**: No

## Labels

`bug`, `state`, `captured`

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/state.py`: Wrapped mutable `data.get()` calls in `list()` and `dict()` copy constructors in `ProcessingState.from_dict()`
- `scripts/tests/test_state.py`: Added `test_from_dict_no_aliasing` test verifying mutations don't propagate back to original data

### Verification Results
- Tests: PASS (33/33)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:scan-codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`
- `/ll:format-issue --all --auto` - 2026-02-13
- `/ll:manage-issue` - 2026-02-13T01:33:28Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-worker-bug-347-20260213-013328/ffc37e42-1502-48e2-bbfa-ca344b0fcf60.jsonl`


---

**Completed** | Created: 2026-02-12 | Priority: P4

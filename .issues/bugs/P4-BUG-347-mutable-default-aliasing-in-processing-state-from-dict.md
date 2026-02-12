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
- **Line(s)**: 64-73 (at scan commit: be30013)
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
```

## Impact

- **Priority**: P4 - Requires specific usage pattern to trigger; current callers may not mutate
- **Effort**: Small - Two-line change
- **Risk**: Low - Defensive copy is strictly safer
- **Breaking Change**: No

## Labels

`bug`, `state`, `captured`

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P4

---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# BUG-603: Corrupted state file silently returns `None` — indistinguishable from missing state

## Summary

`StatePersistence.load_state` catches `KeyError` alongside `json.JSONDecodeError` and returns `None` for both. When a state file exists but has missing required keys (due to partial writes, external modification, or disk errors), callers like `cmd_status` and `cmd_resume` receive `None` and report "no state found" — giving the user no indication that a corrupted state file exists on disk.

## Location

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Line(s)**: 168-173 (at scan commit: c010880)
- **Anchor**: `in method StatePersistence.load_state()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/fsm/persistence.py#L168-L173)
- **Code**:
```python
try:
    data = json.loads(self.state_file.read_text())
    return LoopState.from_dict(data)
except (json.JSONDecodeError, KeyError):
    return None
```

## Current Behavior

A corrupted state file (valid JSON but missing required keys like `loop_name`, `current_state`, etc.) causes `LoopState.from_dict` to raise `KeyError`, which is caught silently. The caller sees `None` — identical to "no state file exists".

## Expected Behavior

`load_state` should distinguish between "no state file" and "corrupted state file". At minimum, log a warning when a `KeyError` occurs so the user knows the file exists but is unreadable.

## Steps to Reproduce

1. Start a loop to generate a state file
2. Manually remove the `"loop_name"` key from the `.state.json` file
3. Run `ll-loop status <loop>`
4. Output: `No state found for: <loop>` — no indication of corruption

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `in method StatePersistence.load_state()`
- **Cause**: `KeyError` is caught alongside `JSONDecodeError` in a single except clause, returning `None` for both. `LoopState.from_dict` uses direct dict indexing (`data["loop_name"]`) without `.get()` fallbacks.

## Proposed Solution

Separate the exception handling:

```python
try:
    data = json.loads(self.state_file.read_text())
except json.JSONDecodeError:
    return None
try:
    return LoopState.from_dict(data)
except KeyError as e:
    logger.warning(f"Corrupted state file {self.state_file}: missing key {e}")
    return None
```

## Implementation Steps

1. Split the exception handling in `load_state` to log on `KeyError`
2. Add a test for loading a corrupted state file and verifying the warning

## Impact

- **Priority**: P3 - Misleading output when state files are corrupted
- **Effort**: Small - Splitting one except clause and adding a log line
- **Risk**: Low - Only adds a warning, return value unchanged
- **Breaking Change**: No

## Labels

`bug`, `ll-loop`, `persistence`

---

**Open** | Created: 2026-03-06 | Priority: P3

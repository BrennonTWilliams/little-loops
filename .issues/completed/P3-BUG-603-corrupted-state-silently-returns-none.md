---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# BUG-603: Corrupted state file silently returns `None` — indistinguishable from missing state

## Summary

`StatePersistence.load_state` catches `KeyError` alongside `json.JSONDecodeError` and returns `None` for both. When a state file exists but has missing required keys (due to partial writes, external modification, or disk errors), callers like `cmd_status` and `cmd_resume` receive `None` and report "no state found" — giving the user no indication that a corrupted state file exists on disk.

## Location

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Line(s)**: 169-173 (at scan commit: c010880)
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

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `except (json.JSONDecodeError, KeyError): return None` confirmed at `persistence.py:172`
- `/ll:format-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — added ## Status heading
- `/ll:confidence-check` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — readiness: 100/100 PROCEED, outcome: 86/100 HIGH CONFIDENCE
- `/ll:ready-issue` - 2026-03-06T15:48:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68b0ec44-3243-4aca-9797-af2c985bb340.jsonl` — CORRECTED: line drift 168->169; code confirmed at persistence.py:169-173

- `/ll:manage-issue` - 2026-03-06T16:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl` — FIXED: split except clause in `load_state`, added `logging` import and module logger, updated `test_missing_required_field_in_state` to assert warning emitted; 59 tests pass

---

## Resolution

**Fixed** in `scripts/little_loops/fsm/persistence.py`:
- Added `import logging` and `logger = logging.getLogger(__name__)`
- Split `except (json.JSONDecodeError, KeyError): return None` into two separate try/except blocks
- `KeyError` path now calls `logger.warning("Corrupted state file %s: missing key %s", ...)` before returning `None`
- Updated `test_missing_required_field_in_state` to assert the warning is logged

## Status

**Completed** | Created: 2026-03-06 | Resolved: 2026-03-06 | Priority: P3

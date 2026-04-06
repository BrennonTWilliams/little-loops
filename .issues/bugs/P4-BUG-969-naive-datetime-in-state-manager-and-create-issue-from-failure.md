---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# BUG-969: Naive (non-UTC) datetime in `StateManager` and `create_issue_from_failure`

## Summary

Two locations in the codebase call `datetime.now().isoformat()` without a timezone argument, producing local-time timestamps that lack UTC offset information. Both files already import `UTC` from `datetime` and use `datetime.now(UTC)` elsewhere. The inconsistency means timestamps in state JSON files and auto-generated issue files vary by the machine's locale, breaking consistent cross-machine comparison.

## Location

- **File**: `scripts/little_loops/state.py`
- **Line(s)**: 113, 143 (at scan commit: 96d74cda)
- **Anchor**: `in StateManager.state property` and `in StateManager.save`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/state.py#L113)
- **Code**:
```python
# state.py line 113
self._state = ProcessingState(timestamp=datetime.now().isoformat())  # naive

# state.py line 143
self.state.timestamp = datetime.now().isoformat()  # naive
```

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Line(s)**: 518 (at scan commit: 96d74cda)
- **Anchor**: `in function create_issue_from_failure`, Status section f-string
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_lifecycle.py#L518)
- **Code**:
```python
## Status
**Open** | Created: {datetime.now().isoformat()} | Priority: P1  # naive
```

## Current Behavior

On machines not running in UTC, the `timestamp` field in `.json` state files and the `Created:` timestamp in auto-generated issue files reflect local time without a timezone offset (e.g., `2026-04-06T08:57:51` instead of `2026-04-06T15:57:51+00:00`). All other system-generated timestamps in the same codebase include `+00:00`.

## Expected Behavior

All timestamps should be UTC-aware: `datetime.now(UTC).isoformat()`. The `_iso_now()` helper in `issue_lifecycle.py` (line 27) already does this correctly and should be used in place of raw `datetime.now()` calls.

## Motivation

Inconsistent timestamp formats cause issues in log analysis, sorting, and cross-machine reproducibility. The `ll-history` and `ll-auto` tools parse these timestamps for ordering and reporting; naive timestamps sort incorrectly relative to UTC-aware timestamps in Python's `datetime` comparisons.

## Steps to Reproduce

1. Run `ll-auto` or `ll-parallel` on a machine in a non-UTC timezone.
2. Inspect the resulting `.json` state file's `timestamp` field.
3. Observe: the timestamp lacks timezone info while other fields in the same system have `+00:00`.

## Root Cause

- **File**: `scripts/little_loops/state.py`; `scripts/little_loops/issue_lifecycle.py`
- **Anchor**: `StateManager.state`, `StateManager.save`, `create_issue_from_failure`
- **Cause**: `datetime.now()` called without the `UTC` argument at lines 113, 143 (state.py) and line 518 (issue_lifecycle.py). Both files import `UTC` but these specific call sites omit it.

## Proposed Solution

Replace all three occurrences:

```python
# state.py lines 113 and 143:
datetime.now(UTC).isoformat()

# issue_lifecycle.py line 518 — use existing _iso_now() helper:
**Open** | Created: {_iso_now()} | Priority: P1
```

The `_iso_now()` helper at `issue_lifecycle.py:27` is already the canonical UTC-timestamp function in that module.

## Integration Map

### Files to Modify
- `scripts/little_loops/state.py` — lines 113, 143
- `scripts/little_loops/issue_lifecycle.py` — line 518

### Dependent Files (Callers/Importers)
- Any code that reads `ProcessingState.timestamp` and parses it as a datetime

### Similar Patterns
- `issue_lifecycle.py:27` `_iso_now()` — reference implementation to reuse

### Tests
- `scripts/tests/test_state.py` — add assertion that saved timestamp ends with `+00:00`
- `scripts/tests/test_issue_lifecycle.py` — add assertion that `create_issue_from_failure` produces a UTC timestamp in the Status section

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace `datetime.now().isoformat()` with `datetime.now(UTC).isoformat()` in `state.py` (lines 113 and 143)
2. Replace `datetime.now().isoformat()` with `_iso_now()` in `issue_lifecycle.py` line 518
3. Add/update tests to assert timestamps are UTC-aware

## Impact

- **Priority**: P4 — Correctness issue; subtle timezone bug that only manifests on non-UTC machines
- **Effort**: Small — Three one-line substitutions
- **Risk**: Low — No behavior change on UTC machines; fixes incorrect behavior on others
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `datetime`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4

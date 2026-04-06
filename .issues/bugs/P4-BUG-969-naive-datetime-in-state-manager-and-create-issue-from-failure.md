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
- `scripts/little_loops/state.py` — lines 113, 143 (`StateManager.state` property and `save()`)
- `scripts/little_loops/issue_lifecycle.py` — line 518 (`create_issue_from_failure` status f-string)
- `scripts/little_loops/issue_manager.py` — line 919 (`ProcessingState(timestamp=datetime.now().isoformat())` — fourth naive site, not in original scan)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — imports `StateManager`/`ProcessingState`; reads `.timestamp` field (also a write site, see above)
- `scripts/little_loops/parallel/orchestrator.py` — imports from `issue_lifecycle`; uses `create_issue_from_failure`
- `scripts/little_loops/cli/issues/skip.py` — imports from `issue_lifecycle`
- `scripts/little_loops/__init__.py` — imports from `issue_lifecycle`

### Similar Patterns
- `state.py:20-22` — `_iso_now()` helper defined in `state.py` itself; use this for lines 113 and 143 (not the one in `issue_lifecycle.py`)
- `issue_lifecycle.py:25-27` — `_iso_now()` helper in `issue_lifecycle.py`; use for line 518 and line 919 fix in `issue_manager.py`
- `scripts/tests/test_fsm_persistence.py:332,496` — model UTC assertion pattern: `assert result == "2024-01-15T11:00:00+00:00"`

### Tests
- `scripts/tests/test_state.py:205,261` — currently only asserts `timestamp != ""`; update to assert `"+00:00" in timestamp`
- `scripts/tests/test_state.py:36,76,114` — hardcoded naive fixture strings (`"2025-01-01T12:00:00"`) will need updating to `"2025-01-01T12:00:00+00:00"` format (or use `datetime.now(UTC).isoformat()` in fixtures)
- `scripts/tests/test_issue_lifecycle.py:633-736` (`TestCreateIssueFromFailure`) — no existing assertion on the `Created:` timestamp line; add one asserting `"+00:00"` is present in the Status section

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_state.py:51` — asserts `result["timestamp"] == "2025-01-01T12:00:00"` (paired assertion for fixture at :39); must update alongside the fixture to `"2025-01-01T12:00:00+00:00"`
- `scripts/tests/test_state.py:87` — asserts `state.timestamp == "2025-01-01T14:00:00"` (paired assertion for fixture at :75); must update alongside the fixture to `"2025-01-01T14:00:00+00:00"`
- `scripts/tests/test_state.py:220` — fourth naive timestamp fixture `"2025-01-01T00:00:00"` in `test_load_existing_file`; not mentioned in existing issue — update to `"2025-01-01T00:00:00+00:00"`

### Documentation
- N/A

### Configuration
- N/A

### Out-of-Scope Naive Calls (do NOT fix in this issue)
- `issue_lifecycle.py:170,216` — `datetime.now().strftime("%Y-%m-%d")` (date-only, timezone irrelevant)
- `issue_lifecycle.py:717,729,817` — `datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")` with misleading literal `Z` suffix on local time; separate bug worth a dedicated issue

## Implementation Steps

1. In `state.py` lines 113 and 143, replace `datetime.now().isoformat()` with `_iso_now()` (the helper is already defined at `state.py:20-22` — no new import needed)
2. In `issue_lifecycle.py` line 518, replace `datetime.now().isoformat()` with `_iso_now()` (already defined at `issue_lifecycle.py:25-27`)
3. In `issue_manager.py` line 919, replace `datetime.now().isoformat()` with `_iso_now()` — add `from little_loops.issue_lifecycle import _iso_now` if not already imported, or `from little_loops.state import _iso_now`
4. Update `test_state.py` hardcoded naive timestamp fixtures at lines 36, 76, 114 to use `+00:00`-suffixed strings (e.g., `"2025-01-01T12:00:00+00:00"`)
5. Strengthen `test_state.py:205,261` assertions from `!= ""` to `assert "+00:00" in state.timestamp`
6. Add a test in `TestCreateIssueFromFailure` (`test_issue_lifecycle.py:633`) asserting the Status section contains a UTC-aware `Created:` timestamp: `assert "Created:" in content` and `assert "+00:00" in content`
7. Run `python -m pytest scripts/tests/test_state.py scripts/tests/test_issue_lifecycle.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `test_state.py:51` — change `assert result["timestamp"] == "2025-01-01T12:00:00"` to `"2025-01-01T12:00:00+00:00"` (paired with fixture update at :39 from Step 4)
9. Update `test_state.py:87` — change `assert state.timestamp == "2025-01-01T14:00:00"` to `"2025-01-01T14:00:00+00:00"` (paired with fixture update at :75 from Step 4)
10. Update `test_state.py:220` — change `"timestamp": "2025-01-01T00:00:00"` fixture in `test_load_existing_file` to `"2025-01-01T00:00:00+00:00"`

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
- `/ll:wire-issue` - 2026-04-06T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c54bab8-6d66-4299-8536-f9754fcca2a4.jsonl`
- `/ll:refine-issue` - 2026-04-06T19:15:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71d7d560-3e7b-4d8f-a782-7e0c62fdfa6c.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4

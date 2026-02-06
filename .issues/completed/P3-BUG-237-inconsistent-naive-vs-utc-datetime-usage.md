---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "No actual bug found. Naive and aware datetimes are never compared in practice — naive datetimes are used in display-only contexts (logger timestamps, filenames) or serialized to ISO strings that are never compared with UTC strings. Fixing this is pure hygiene with no practical impact."
---

# BUG-237: Inconsistent naive vs UTC-aware datetime usage

## Summary

The codebase inconsistently mixes naive `datetime.now()` (no timezone) with timezone-aware `datetime.now(UTC)`. Naive and aware datetimes cannot be compared in Python (raises `TypeError`), and timestamps from different modules may produce incompatible formats.

## Location

- **File**: Multiple files (at scan commit: a8f4144)
- **Anchor**: `datetime.now()` vs `datetime.now(UTC)` calls

**Naive datetime.now() usage:**
- `scripts/little_loops/state.py` line 98
- `scripts/little_loops/issue_lifecycle.py` lines 162, 208, 487
- `scripts/little_loops/parallel/orchestrator.py` lines 452, 470, 474
- `scripts/little_loops/issue_discovery.py` lines 553, 767, 945
- `scripts/little_loops/parallel/worker_pool.py` line 219
- `scripts/little_loops/issue_manager.py` line 703

**UTC-aware datetime.now(UTC) usage:**
- `scripts/little_loops/fsm/concurrency.py`, `fsm/persistence.py`, `fsm/executor.py`
- `scripts/little_loops/sync.py`, `sprint.py`

## Current Behavior

Naive datetimes produce strings like `2026-02-05T10:30:00` while UTC-aware ones produce `2026-02-05T10:30:00+00:00`. The `issue_discovery.py` line 553 computes `(datetime.now() - completion_date).days` mixing naive timestamps which could produce incorrect results across timezone changes.

## Expected Behavior

All datetime usage should consistently use `datetime.now(UTC)` for timezone-aware timestamps throughout the codebase.

## Proposed Solution

Replace all `datetime.now()` calls with `datetime.now(UTC)` and ensure `from datetime import UTC` is imported in each affected module.

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p3`

---

## Status
**Closed (won't-fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P3

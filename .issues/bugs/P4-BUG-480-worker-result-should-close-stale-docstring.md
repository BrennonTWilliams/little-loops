---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-480: `WorkerResult.should_close` docstring says "not implemented" but it is

## Summary

The `WorkerResult` dataclass docstring at `types.py:68` says `should_close: Whether the issue should be closed (not implemented)`. However, this field IS populated in `worker_pool.py:304-316` and IS handled in `orchestrator.py:784-803` by calling `close_issue()`. The stale docstring implies a missing feature that is actually present.

## Location

- **File**: `scripts/little_loops/parallel/types.py`
- **Line(s)**: 68 (at scan commit: 95d4139)
- **Anchor**: `in class WorkerResult docstring`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/parallel/types.py#L68)
- **Code**:
```python
should_close: Whether the issue should be closed (not implemented)
```

## Current Behavior

The docstring annotation reads "(not implemented)" but the close path for `ll-parallel` workers is fully wired: the field is set in `worker_pool.py`, checked in `orchestrator.py`, and triggers `close_issue()` from `issue_lifecycle.py`.

## Expected Behavior

The docstring should accurately reflect that `should_close` IS implemented and describe its behavior.

## Proposed Solution

Update the docstring:

```python
should_close: Whether the issue should be closed (e.g., already fixed, invalid)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/types.py` — update docstring for `should_close`

### Dependent Files (Callers/Importers)
- N/A — documentation-only change

### Similar Patterns
- N/A

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Misleading documentation, no functional impact
- **Effort**: Small — Single line docstring update
- **Risk**: Low — Documentation change only
- **Breaking Change**: No

## Labels

`bug`, `documentation`, `parallel`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

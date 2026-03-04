---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-537: Extract Shared `_process_alive` to Eliminate Duplication Between `concurrency.py` and `lifecycle.py`

## Summary

An identical 6-line `os.kill(pid, 0)` / `except OSError` function exists in two locations: as `LockManager._process_alive()` in `concurrency.py` and as a module-level `_process_alive()` in `lifecycle.py`. Both contain the same EPERM/ESRCH bug (see BUG-526). Any behavioral fix must be applied in both places. Extracting to a shared utility eliminates this maintenance hazard.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 252–258 (at scan commit: 47c81c8)
- **Anchor**: `in method LockManager._process_alive()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/concurrency.py#L252-L258)

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 28–34 (at scan commit: 47c81c8)
- **Anchor**: `module-level function _process_alive()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/lifecycle.py#L28-L34)

## Current Behavior

Two byte-for-byte identical implementations of the process-liveness check exist. Any change (e.g., the EPERM fix from BUG-526) must be applied in both locations manually.

## Expected Behavior

A single `process_alive(pid: int) -> bool` utility function exists in one location (e.g., `scripts/little_loops/fsm/concurrency.py` as a module-level function, or a new `scripts/little_loops/process_utils.py`). Both `LockManager` and `lifecycle.py` import and call it.

## Motivation

Code duplication is a maintenance burden. The EPERM/ESRCH bug (BUG-526) exists in both copies and was introduced at the same time — the duplication is the reason the bug will persist if only one copy is fixed. Any future improvements (e.g., Windows compatibility, logging, timeout) must also be applied in both places.

## Proposed Solution

Extract to a module-level function in `concurrency.py` (already imported by both) or a small utility module:

```python
# In concurrency.py (module level):
import errno

def _process_alive(pid: int) -> bool:
    """Check if process is running. Distinguishes ESRCH (dead) from EPERM (alive, no permission)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        return e.errno != errno.ESRCH

# In LockManager:
def _process_alive(self, pid: int) -> bool:
    return _process_alive(pid)   # delegate to module-level

# In lifecycle.py:
from little_loops.fsm.concurrency import _process_alive as _process_alive
```

Alternatively, make `LockManager._process_alive` a static method and import it in `lifecycle.py`.

## Scope Boundaries

- Only affects code sharing; no behavioral changes beyond BUG-526 fix (which should be applied simultaneously)
- Does not add new public API
- Does not change how `LockManager` or `lifecycle.py` call the function

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — extract module-level `_process_alive`, update `LockManager._process_alive` to delegate
- `scripts/little_loops/cli/loop/lifecycle.py` — import and use shared function

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/concurrency.py` — `cleanup_stale()` → `LockManager._process_alive()`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()` → module-level `_process_alive()`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_ll_loop_execution.py` — existing tests cover both callers; no new tests required, but verify both still pass

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract `_process_alive` as a module-level function in `concurrency.py` (with BUG-526 EPERM fix applied)
2. Update `LockManager._process_alive` to delegate to the module-level function
3. Update `lifecycle.py` to import and use the shared function
4. Confirm existing tests pass

## Impact

- **Priority**: P3 — Code quality / maintainability; pairs with BUG-526 fix
- **Effort**: Small — Extraction and import wiring; no logic changes
- **Risk**: Low — Pure refactor; behavior identical to current (plus BUG-526 fix if applied)
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Concurrency and locking model (line 1288) — stale-lock cleanup behavior |

## Labels

`enhancement`, `ll-loop`, `refactor`, `concurrency`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted duplication in `concurrency.py:252` and `lifecycle.py:28`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P3

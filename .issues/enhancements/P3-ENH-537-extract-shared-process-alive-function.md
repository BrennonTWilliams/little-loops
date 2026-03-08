---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 96
outcome_confidence: 86
---

# ENH-537: Extract Shared `_process_alive` to Eliminate Duplication Between `concurrency.py` and `lifecycle.py`

## Summary

An identical 6-line `os.kill(pid, 0)` / `except OSError` function exists in two locations: as `LockManager._process_alive()` in `concurrency.py` and as a module-level `_process_alive()` in `lifecycle.py`. Both contain the same EPERM/ESRCH bug (see BUG-526). Any behavioral fix must be applied in both places. Extracting to a shared utility eliminates this maintenance hazard.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 256–264 (at scan commit: 47c81c8; current HEAD)
- **Anchor**: `in method LockManager._process_alive()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/concurrency.py#L252-L258)

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 30–38 (at scan commit: 47c81c8; current HEAD)
- **Anchor**: `module-level function _process_alive()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/lifecycle.py#L28-L34)

## Current Behavior

Two byte-for-byte identical implementations of the process-liveness check exist. Any change (e.g., the EPERM fix from BUG-526) must be applied in both locations manually.

## Expected Behavior

A single `process_alive(pid: int) -> bool` utility function exists in one location (e.g., `scripts/little_loops/fsm/concurrency.py` as a module-level function, or a new `scripts/little_loops/process_utils.py`). Both `LockManager` and `lifecycle.py` import and call it.

## Motivation

~6 lines of byte-for-byte duplicate code across 2 files:

- **Maintenance burden**: The EPERM/ESRCH bug (BUG-526) was introduced identically in both copies — any fix must be applied manually in both places; missing one means the bug persists
- **Future-proofing**: Any improvement (Windows compatibility, logging, timeout handling) must be duplicated across both files
- **Technical debt**: Two files share identical logic with no enforced contract; behavioral drift is inevitable over time

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

## API/Interface

```python
def _process_alive(pid: int) -> bool:
    """Check if process is running.
    Returns True if alive (or alive but unreadable),
    False only if process does not exist (ESRCH).
    """
```

Shared via import in `lifecycle.py`:
```python
from little_loops.fsm.concurrency import _process_alive
```

## Scope Boundaries

**In scope:**
- Extract `_process_alive` to a module-level function in `concurrency.py`
- Apply BUG-526 EPERM/ESRCH fix in the single canonical implementation
- Update `lifecycle.py` to import from `concurrency.py`

**Out of scope:**
- No behavioral changes beyond the BUG-526 fix
- Does not add new public API
- Does not change call sites in `cleanup_stale()` or `cmd_stop()`

## Success Metrics

- [ ] Existing tests in `scripts/tests/test_ll_loop_execution.py` pass unchanged
- [ ] `grep -r "_process_alive" scripts/` returns exactly one function body (in `concurrency.py`); `lifecycle.py` contains only an import
- [ ] BUG-526 EPERM/ESRCH fix applied in single location — no manual sync needed between files
- [ ] `from little_loops.fsm.concurrency import _process_alive` resolves without error and without creating a circular import

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
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: duplication confirmed in concurrency.py:256 and lifecycle.py:31
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `_process_alive` duplication confirmed at `concurrency.py:256` and `lifecycle.py:36`

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted duplication in `concurrency.py:252` and `lifecycle.py:28`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — Added Blocks FEAT-543 (docs overlap, auto)
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: both `_process_alive` functions confirmed present (`concurrency.py:256`, `lifecycle.py:30`); line numbers updated from scan-commit values
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/780b1de5-df56-457c-b885-0bae03760fd7.jsonl` — Added API/Interface (shared signature), Success Metrics (4 criteria), restructured Scope Boundaries (in/out framing), quantified Motivation
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — Readiness: 96/100 PROCEED; Outcome: 86/100 HIGH CONFIDENCE

## Blocks

- FEAT-543 — `docs/generalized-fsm-loop.md` overlap (higher priority; complete first)

---

## Status

**Open** | Created: 2026-03-03 | Priority: P3

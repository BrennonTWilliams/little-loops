---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 100
---

# ENH-629: `_scopes_overlap` re-resolves `Path.resolve()` (filesystem stat) on every path pair

## Summary

`_scopes_overlap()` in `concurrency.py` checks whether two scope path lists have overlapping paths. For each pair, it calls `_paths_overlap()`, which calls `Path.resolve()` on both paths. `Path.resolve()` makes a filesystem stat call. For an FSM with many concurrent states and large scope lists, this produces O(n²) stat calls on every lock acquisition.

## Location

- **File**: `scripts/little_loops/fsm/concurrency.py`
- **Line(s)**: 220–230 (at scan commit: 12a6af0)
- **Anchor**: `in class ScopeLockManager, methods _scopes_overlap() and _paths_overlap()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/concurrency.py#L220-L230)
- **Code**:
```python
def _scopes_overlap(self, scope1: list[str], scope2: list[str]) -> bool:
    for p1 in scope1:
        for p2 in scope2:
            if self._paths_overlap(p1, p2):
                return True
    return False

def _paths_overlap(self, path1: str, path2: str) -> bool:
    p1 = Path(path1).resolve()   # filesystem stat on every call
    p2 = Path(path2).resolve()
    ...
```

## Current Behavior

Every call to `_scopes_overlap` resolves all scope paths from strings to absolute paths via filesystem stat. The `_normalize_path` method (line 252) also calls `Path(path).resolve()` at scope-acquire time; the resolved values are available at acquire time but are not reused in `_paths_overlap`.

## Expected Behavior

Scope paths should be normalized (resolved) once at scope acquire/register time and stored as pre-resolved `Path` objects, so `_scopes_overlap` can compare them without repeated filesystem calls.

## Motivation

Reduces syscall overhead for FSM loops with many concurrent states. Even for small loops, this is an easy optimization that makes the code cleaner.

## Proposed Solution

Pre-resolve scope paths when stored:

```python
# In acquire() or wherever scopes are stored:
resolved_scopes = [str(Path(p).resolve()) for p in scope]

# _scopes_overlap and _paths_overlap work on pre-resolved strings
# Path.resolve() is not called inside the comparison loop
```

## Scope Boundaries

- Only `concurrency.py` needs to change
- No interface changes

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/concurrency.py` — `ScopeLockManager.acquire()`, `_scopes_overlap()`, `_paths_overlap()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/__init__.py` — re-exports `ScopeLockManager` from concurrency module
- `scripts/little_loops/cli/loop/run.py` — imports `LockManager` for scope-based locking during loop execution

### Similar Patterns
- `ScopeLockManager._normalize_path()` in `concurrency.py` — already calls `Path(path).resolve()`; pre-resolution in `acquire()` can reuse this existing method directly rather than adding a new one

### Tests
- `scripts/tests/test_concurrency.py` — existing tests cover `_paths_overlap` and `_scopes_overlap`; no new tests needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Pre-resolve scope paths in `acquire()` (or wherever scope lists are stored as instance data)
2. Update `_paths_overlap()` to skip `Path.resolve()` since paths are pre-resolved

## Impact

- **Priority**: P4 — Performance improvement for concurrent FSM loops; not critical for typical use
- **Effort**: Small — Minor refactor in `concurrency.py`
- **Risk**: Low — Behavior-preserving; only changes when resolution happens
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `concurrency`, `performance`, `captured`

## Verification Notes

Verified 2026-03-07 — **VALID**. Code at `concurrency.py` lines 220–250 matches the quoted snippets exactly. `_normalize_path()` is confirmed at line 252; `acquire()` at line 96 already calls it to produce resolved strings, but `_paths_overlap()` re-calls `Path.resolve()` anyway. No files have moved since the scan commit (12a6af0). Issue accurately describes the current state.

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `_paths_overlap()` re-calls `Path.resolve()` at `concurrency.py:220-230`; `_normalize_path()` at line 252 not reused in comparison

## Status

**Open** | Created: 2026-03-07 | Priority: P4

---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-540: `_find_reachable_states` BFS Uses `list.pop(0)` — O(n²) vs O(n) with `deque`

## Summary

`_find_reachable_states` in `validation.py` implements BFS using a plain `list` with `pop(0)`. `list.pop(0)` is O(n) because it shifts all remaining elements left. For FSMs with many states, the function performs O(n²) memory moves across all iterations. Replacing with `collections.deque` and `popleft()` gives O(1) dequeue with identical semantics.

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 275–290 (at scan commit: 47c81c8)
- **Anchor**: `in function _find_reachable_states()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/validation.py#L275-L290)
- **Code**:
```python
def _find_reachable_states(fsm: FSMLoop) -> set[str]:
    to_visit: list[str] = [fsm.initial]
    while to_visit:
        current = to_visit.pop(0)    # O(n) list shift
        ...
        to_visit.append(ref)
```

## Current Behavior

BFS uses `list.pop(0)`, which shifts O(n) elements on each dequeue. For a loop with N states, the total dequeue cost is O(N + (N-1) + ... + 1) = O(N²/2). `_find_reachable_states` is called on every `validate_fsm` call, which runs on every `load_and_validate`, which runs on every CLI subcommand invocation.

## Expected Behavior

BFS uses `collections.deque.popleft()`, giving O(1) dequeue and O(N) total traversal cost.

## Motivation

Minor performance improvement that also removes a code smell. The `collections.deque` type is already imported in `info.py` for the diagram BFS, so the pattern is established in the codebase. For typical FSMs (5–20 states) the difference is imperceptible, but it's a one-line fix that also makes the intent clearer.

## Proposed Solution

```python
from collections import deque

def _find_reachable_states(fsm: FSMLoop) -> set[str]:
    reachable: set[str] = set()
    to_visit: deque[str] = deque([fsm.initial])   # was: list[str] = [fsm.initial]
    while to_visit:
        current = to_visit.popleft()               # was: to_visit.pop(0)
        ...
```

## Scope Boundaries

- Only `_find_reachable_states` in `validation.py`
- Does not change validation logic or returned set
- Does not affect the BFS in `info.py` (already uses deque)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — `_find_reachable_states()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py` — `validate_fsm()` calls `_find_reachable_states()`; no interface change

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py` — `_render_fsm_diagram()` uses `deque` for BFS; same pattern

### Tests
- Existing validation tests cover `_find_reachable_states` indirectly via `validate_fsm`; no new tests needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `from collections import deque` import to `validation.py` (if not already present)
2. Change `to_visit: list[str] = [fsm.initial]` → `to_visit: deque[str] = deque([fsm.initial])`
3. Change `to_visit.pop(0)` → `to_visit.popleft()`
4. Run validation tests to confirm pass

## Impact

- **Priority**: P4 — Minor performance; primarily a code clarity improvement
- **Effort**: Small — 3-line change
- **Risk**: Low — Pure algorithmic optimization; no semantic change
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | FSM schema validation (line 357) — reachable state detection context |

## Labels

`enhancement`, `ll-loop`, `performance`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `schema.py` BFS traversal as fix location

---

**Open** | Created: 2026-03-03 | Priority: P4

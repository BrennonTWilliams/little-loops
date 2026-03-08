---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 92
outcome_confidence: 88
---

# ENH-540: `_find_reachable_states` BFS Uses `list.pop(0)` — O(n²) vs O(n) with `deque`

## Summary

`_find_reachable_states` in `scripts/little_loops/fsm/validation.py` (line 264–279) implements BFS using a plain `list` with `pop(0)`. The operation is O(n) because it shifts all remaining elements left. For FSMs with N states, total dequeue cost is O(N²/2). Replacing with `collections.deque` and `popleft()` gives O(1) dequeue with identical semantics and O(N) total traversal cost.

## Current Behavior

BFS uses `list.pop(0)`, which is O(n) per dequeue operation because the list shifts all remaining elements. For a loop with N states, total dequeue cost is O(N²/2). The function is called on every `validate_fsm()` call, which executes on every CLI subcommand invocation (during loop load and validation).

## Expected Behavior

BFS uses `collections.deque.popleft()`, giving O(1) dequeue and O(N) total traversal cost.

## Motivation

Minor but measurable performance improvement for a common operation:
- **Algorithmic fix**: O(n²) → O(n) complexity in a utility function called on every CLI invocation
- **Code clarity**: The `collections.deque` pattern is already established in `info.py` for the diagram BFS; using it consistently removes a code smell
- **Technical debt**: Using the wrong data structure (list for queue ops) is a recognized anti-pattern that newer contributors may cargo-cult
- **Magnitude**: For typical FSMs (5–20 states), imperceptible. For larger loops (50+ states), reduces validation overhead by ~10–20x for this specific operation

**Practical impact**: Every `ll` CLI call runs validation; this saves microseconds per invocation across all commands. Not user-facing, but meaningful in aggregate.

## Proposed Solution

```python
from collections import deque

def _find_reachable_states(fsm: FSMLoop) -> set[str]:
    reachable: set[str] = set()
    to_visit: deque[str] = deque([fsm.initial])   # was: list[str] = [fsm.initial]
    while to_visit:
        current = to_visit.popleft()               # was: to_visit.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        for target in fsm.states[current].edges.keys():
            to_visit.append(target)
    return reachable
```

## API/Interface

No public API change. The function signature remains identical:
```python
def _find_reachable_states(fsm: FSMLoop) -> set[str]:
```

Internal implementation detail only — no external impact.

## Success Metrics

- [ ] All existing validation tests in `scripts/tests/test_ll_loop_*.py` pass unchanged
- [ ] `_find_reachable_states` still returns the same result set for all test FSMs
- [ ] No import errors or circular dependencies introduced by adding `from collections import deque`
- [ ] BFS traversal produces identical output (reachable state set) before and after change

## Scope Boundaries

**In scope:**
- Replace `list` with `deque` in `_find_reachable_states` function
- Add `from collections import deque` import (if not present)
- Change `pop(0)` to `popleft()` — one line change

**Out of scope:**
- Does not change the BFS in `info.py` (already uses deque)
- No changes to validation logic or return value
- No changes to callers or call sites
- No changes to function signature or documentation

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
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: pop(0) at validation.py:279
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `to_visit.pop(0)` confirmed at `validation.py:321` (line shifted from 279)

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `schema.py` BFS traversal as fix location
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: `_find_reachable_states` at `validation.py:264`; `to_visit.pop(0)` confirmed at line 279; no `deque` import in `validation.py`
- `/ll:format-issue` (v2.0) - 2026-03-06 - Converted to v2.0 ENH template: added Motivation with quantified impact (10-20x improvement for 50+ state FSMs), Success Metrics (4 criteria), API/Interface section (no public API change), restructured Scope Boundaries (in/out framing), expanded Proposed Solution with complete function body
- `/ll:confidence-check` - 2026-03-06 - Readiness: 92/100 PROCEED; Outcome: 88/100 HIGH CONFIDENCE. Single 3-line change, well-understood algorithm, identical pattern in codebase (info.py), zero breaking changes

---

## Blocks

- ENH-542

---

## Status

**Open** | Created: 2026-03-03 | Priority: P4

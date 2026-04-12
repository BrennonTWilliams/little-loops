---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
---

# FEAT-1078: Parallel State Wiring, Display, and Docs

## Summary

Wire `ParallelStateConfig` and `ParallelResult` into `fsm/__init__.py`, add display handling in `cli/loop/layout.py` and `cli/loop/info.py`, and update all documentation touchpoints identified in the wiring pass.

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### __init__.py exports

`scripts/little_loops/fsm/__init__.py` — add `ParallelStateConfig` and `ParallelResult` to:
- `from little_loops.fsm.schema import (...)` block at lines 113–120
- `__all__` list at lines 136–184
- Module docstring at lines 1–68 (add brief description of parallel state type)

### CLI display

**`scripts/little_loops/cli/loop/layout.py`** — `_get_state_badge()` at line 118 has no branch for `state.parallel is not None`:
- Add `_PARALLEL_BADGE` constant
- Add `if state.parallel is not None: return _PARALLEL_BADGE` branch before action_type checks

**`scripts/little_loops/cli/loop/info.py`**:
- `_print_state_overview_table` type column at line 548 — add `state.parallel` branch (display `"parallel"` type)
- Verbose state output at lines 755–834 — add `state.parallel` branch to show items source, loop name, max_workers, isolation, fail_mode

### Documentation

**`docs/ARCHITECTURE.md`** — Document the `parallel:` state type in the FSM section.

**`docs/reference/API.md`** — Add `ParallelStateConfig` and `ParallelResult` to schema reference.

**`docs/guides/LOOPS_GUIDE.md:1653`** — "Composable Sub-Loops" section and comparison table (lines 1695–1700) describe only `loop:` and inline states; add `parallel:` row and YAML example.

**`scripts/little_loops/loops/README.md:148`** — "Composing Loops" section references `loop:` field only; add `parallel:` fan-out pattern.

**`CONTRIBUTING.md:231`** — `fsm/` directory tree listing; add `parallel_runner.py` entry.

### Skill/create-loop docs

**`skills/create-loop/reference.md:686`** — `loop:` field section documents sub-loop invocation; add `parallel:` field documentation alongside it.

**`skills/create-loop/loop-types.md:978`** — Sub-loop composition section describes `loop:` as the primary child mechanism; add `parallel:` as peer concurrent fan-out mechanism.

## Files to Modify

- `scripts/little_loops/fsm/__init__.py` — Add `ParallelStateConfig`, `ParallelResult` exports
- `scripts/little_loops/cli/loop/layout.py` — Add `_PARALLEL_BADGE` and dispatch branch
- `scripts/little_loops/cli/loop/info.py` — Add `state.parallel` display branches
- `docs/ARCHITECTURE.md` — Document `parallel:` state type
- `docs/reference/API.md` — Add `ParallelStateConfig`, `ParallelResult` reference
- `docs/guides/LOOPS_GUIDE.md` — Add `parallel:` to composable sub-loops section + table
- `scripts/little_loops/loops/README.md` — Add `parallel:` to Composing Loops section
- `CONTRIBUTING.md` — Add `parallel_runner.py` to fsm/ tree listing
- `skills/create-loop/reference.md` — Add `parallel:` field docs
- `skills/create-loop/loop-types.md` — Add `parallel:` mechanism docs

## Dependencies

- FEAT-1074 must be complete (needs `ParallelStateConfig`, `ParallelResult` to export)
- FEAT-1075 and FEAT-1076 should be complete for accurate display and docs

## Acceptance Criteria

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` works without error
- `ll-loop info <loop-with-parallel>` displays parallel states with badge and type column entry
- `ll-loop info --verbose <loop-with-parallel>` shows parallel state details (items, loop, workers, isolation)
- `docs/ARCHITECTURE.md` and `docs/reference/API.md` document `parallel:` state type
- `LOOPS_GUIDE.md` comparison table includes `parallel:` row
- `create-loop` skill docs describe `parallel:` alongside `loop:`

## Labels

`fsm`, `parallel`, `wiring`, `docs`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2

> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1201
size: Small
---

# FEAT-1225: Parallel Display Badge Test and Constant

## Summary

Add `_PARALLEL_BADGE` constant to `scripts/little_loops/cli/loop/layout.py`, wire it into `_get_state_badge()`, and add the badge assertion to `TestStateBadges` in `scripts/tests/test_ll_loop_display.py`.

## Parent Issue

Decomposed from FEAT-1201: Parallel State Executor, Integration, and Display Tests

## Use Case

**Who**: Developer closing out the parallel state feature

**Context**: `_PARALLEL_BADGE` is absent from `layout.py` (only `_SUB_LOOP_BADGE = "↳⟳"` exists at line 109). FEAT-1078's completed marker is stale — the constant was never added. This issue adds both the constant and its test.

**Goal**: Add `_PARALLEL_BADGE` constant, wire it into `_get_state_badge()`, and test it in `test_ll_loop_display.py`.

**Outcome**: `python -m pytest scripts/tests/test_ll_loop_display.py -x -k parallel_badge` passes green with no regressions in existing badge precedence tests.

## Proposed Solution

### layout.py changes

Add `_PARALLEL_BADGE` constant to `scripts/little_loops/cli/loop/layout.py:109` alongside `_SUB_LOOP_BADGE`:

```python
_PARALLEL_BADGE = "⇉"  # or chosen glyph
```

Wire into `_get_state_badge()` — the position where the `parallel:` check is inserted must not break existing sub-loop badge precedence. Verify priority order (parallel should rank above or equal to sub-loop, but below nothing that currently takes precedence).

### test_ll_loop_display.py changes

Add to `TestStateBadges:2353`, modeled after `test_get_state_badge_sub_loop:2383–2386`:

```python
def test_get_state_badge_parallel(self) -> None:
    state = StateConfig(parallel=...)  # shape per FEAT-1074 ParallelStateConfig
    assert _get_state_badge(state) == _PARALLEL_BADGE
```

Add `_PARALLEL_BADGE` to the same import block (lines 15–21) that already imports `_SUB_LOOP_BADGE`.

Update `test_badge_constants_match_spec:2356` — add `_PARALLEL_BADGE` assertion alongside existing `_SUB_LOOP_BADGE`/`_ROUTE_BADGE` checks.

### No Skip Guards

No `pytest.mark.skipif` / `pytest.importorskip` — these are not precedented in `scripts/tests/`. The only conditional-skip idiom is inline `pytest.skip(...)`. Since this issue adds `_PARALLEL_BADGE` itself, no skip is needed.

### Regression Checks

- `test_ll_loop_display.py:2388–2391` (`test_sub_loop_badge_takes_precedence_over_action_type`) — must not break
- `test_ll_loop_display.py:2455–2461` (`test_route_badge_lower_priority_than_sub_loop`) — must not break

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — Add `_PARALLEL_BADGE` constant and wire into `_get_state_badge()`
- `scripts/tests/test_ll_loop_display.py` — Add badge test to `TestStateBadges:2353`, update `test_badge_constants_match_spec:2356`, update import block

### Dependent Files
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` shape for constructing `StateConfig(parallel=...)` — FEAT-1074

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` shape needed for test fixture)

## Acceptance Criteria

- `python -m pytest scripts/tests/test_ll_loop_display.py -x -k parallel_badge` passes green
- `_PARALLEL_BADGE` constant added to `layout.py` and exported
- `_get_state_badge()` returns `_PARALLEL_BADGE` for parallel states
- No regressions in `test_sub_loop_badge_takes_precedence_over_action_type` (line 2388) and `test_route_badge_lower_priority_than_sub_loop` (line 2455)
- `test_badge_constants_match_spec` updated to include `_PARALLEL_BADGE` assertion

## Labels

`fsm`, `parallel`, `tests`, `display`

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/258256f7-974b-4688-b813-9928466b24ec.jsonl`

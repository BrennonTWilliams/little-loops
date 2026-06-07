---
id: BUG-1997
type: BUG
priority: P3
status: done
captured_at: '2026-06-07T03:19:54Z'
completed_at: '2026-06-07T03:19:54Z'
discovered_date: '2026-06-07'
discovered_by: ll-loop run rn-implement
labels:
- fsm
- validation
- false-positive
confidence_score: 100
outcome_confidence: 90
decision_needed: false
relates_to:
- ENH-1961
- FEAT-1991
---

# BUG-1997: capture-reachability validator emits false positives for multi-source captures

## Summary

`ll-loop run rn-implement FEAT-1991` (and `ll-loop validate rn-implement`)
surfaced 7 spurious `[WARNING]` lines of the form:

> References `${captured.input.*}` but `input` is captured by state
> `select_next` which may not execute on all paths to `<state>`.
> Path(s) bypassing capture: `… → fifo_pop → …`

These were **false positives**. In `rn-implement.yaml`, `input` is captured by
**two** states — `fifo_pop` (line 141) and `select_next` (line 306) — which are
the two mutually-exclusive branches of `dequeue_next` (lines 103-114, dispatched
on `schedule_mode`). On every tick exactly one of them runs, so `input` is
always captured before any downstream state (`mark_depth_capped`,
`classify_remediation`, `record_failure`, etc.) reads it. The loop was correct;
the validator was wrong.

## Current Behavior (before fix)

`_validate_capture_reachability()` in `scripts/little_loops/fsm/validation.py`
(ENH-1961) built its capture map as `dict[str, str]` with last-writer-wins:

```python
capture_map: dict[str, str] = {}
for state_name, state in fsm.states.items():
    if state.capture:
        capture_map[state.capture] = state_name   # only the last one survives
```

When two states capture the same variable, only the last one (here
`select_next`) was retained. The single-state dominance check
`_dominates(fsm, "select_next", ref_state)` then returned `False` for every path
flowing through `fifo_pop`, emitting a bypass WARNING — even though `fifo_pop`
also captures `input`.

## Expected Behavior

A `${captured.X}` reference is safe when the **set** of all states capturing `X`
*collectively* dominates the referencing state (every path from `initial` passes
through at least one capturing state). The validator must treat alternative
capture sources as group dominators rather than picking a single canonical one.

## Motivation

- **Signal quality**: spurious warnings on a correct, shipped loop erode trust in
  `ll-loop validate` and bury genuine capture-bypass bugs in noise.
- **Correctness**: the multi-source capture pattern (mode-dispatched branches,
  e.g. FEAT-1991's `fifo` vs `value_ranked` dequeue) is a legitimate and growing
  design idiom; the validator should support it.

## Resolution

Fixed entirely in the validator — no change to `rn-implement.yaml` (the loop was
already correct).

`scripts/little_loops/fsm/validation.py`:
- `capture_map` is now `dict[str, set[str]]` — all states capturing a variable.
- Added `_dominated_by_any(fsm, dominators: set[str], dominated)` — group
  domination: blocks the whole set of capturing states and checks reachability.
- Added `_find_bypass_path_any(fsm, dominators: set[str], dominated)` — bypass
  example path avoiding all capturing states.
- `_dominates()` / `_find_bypass_path()` retained as thin single-element
  wrappers, so single-capture behavior is provably unchanged.
- `_validate_capture_reachability()` uses the set-based check; the WARNING
  message renders one (`state 'X'`) vs. many (`states 'A', 'B', none of which`)
  gracefully.

`scripts/tests/test_fsm_validation.py` (`TestCaptureReachabilityValidation`):
- `test_alternative_capture_branches_no_warning` — the rn-implement fork shape;
  regression guard (fails before the fix).
- `test_partial_capture_branches_still_warn` — one branch lacks the capture;
  ensures genuine bypasses still warn (guards against over-suppression).

## Verification

- `python -m pytest scripts/tests/test_fsm_validation.py` → 160 passed.
- `ll-loop validate rn-implement` → valid, zero `captured.input` warnings.
- `python -m mypy scripts/little_loops/fsm/validation.py` → clean.
- `ruff check` on both changed files → clean.

## Notes

Generalizes the ENH-1961 capture-reachability analysis from one capture source
to N. The single-source dominance semantics are preserved exactly (a one-element
set reduces to the original behavior).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-07T03:20:19 - `b3dbca02-a495-4280-930e-bf7683512675.jsonl`

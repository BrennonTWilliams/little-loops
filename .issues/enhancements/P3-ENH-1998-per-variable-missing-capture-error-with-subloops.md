---
id: ENH-1998
type: ENH
priority: P3
status: open
captured_at: '2026-06-07T03:21:51Z'
discovered_date: '2026-06-07'
discovered_by: capture-issue
labels:
- fsm
- validation
relates_to:
- ENH-1961
- BUG-1997
- EPIC-1962
---

# ENH-1998: Tighten missing-capture ERROR suppression to per-variable when a loop has sub-loops

## Summary

`_validate_capture_reachability()` in `scripts/little_loops/fsm/validation.py`
suppresses the *missing-capture* ERROR for **every** `${captured.X}` reference
whenever the loop contains **any** sub-loop state (`_has_sub_loop_state(fsm)` →
`continue`). This is a coarse, whole-loop escape hatch: a genuinely undefined
capture variable in a loop that *also* delegates to a sub-loop is silently never
flagged.

## Motivation

ENH-1961 added the missing-capture ERROR but deliberately scoped it to skip
loops with sub-loops, because a captured var may legitimately live in a child
loop's namespace. The trade-off is that the check goes completely dark for those
loops — a typo'd `${captured.iput.output}` in a multi-loop orchestrator (e.g.
`rn-implement`, `loop-router`, `sprint-build-and-validate`) produces no error.
As more orchestrator-style loops with sub-loops land, this blind spot widens.

This was noted as a pre-existing gap while fixing BUG-1997 (multi-source capture
false positives) — orthogonal to that bug, but in the same code path.

## Current Behavior

```python
if var_name not in capture_map:
    if _has_sub_loop_state(fsm):
        continue          # whole-loop suppression — any sub-loop disables the check
    errors.append(ValidationError(... severity=ERROR ...))
```

## Expected Behavior

Suppress the ERROR only for variables that a sub-loop *plausibly* produces,
rather than disabling the check for the entire loop. Options to evaluate during
implementation:

- Cross-reference the variable name against the `with:`/output contract of the
  delegated child loops (if discoverable) and only skip vars that match.
- Downgrade to WARNING (instead of full suppression) for unmatched vars in
  sub-loop loops, so genuine typos surface without false ERRORs.
- At minimum, skip only when the reference is reachable from a sub-loop state's
  successors, not globally.

## Implementation Steps

1. Locate the suppression branch in `_validate_capture_reachability()`
   (`scripts/little_loops/fsm/validation.py`).
2. Replace the global `_has_sub_loop_state(fsm)` guard with per-variable logic
   (see options above).
3. Add tests to `TestCaptureReachabilityValidation` in
   `scripts/tests/test_fsm_validation.py`: (a) genuine missing capture in a
   sub-loop loop is now flagged, (b) a legitimate child-loop-provided capture is
   still not flagged.
4. Validate all existing loops (`ll-loop validate <each>`) to confirm no new
   false ERRORs against real orchestrator loops.

## Success Metrics

- Zero new false ERRORs introduced on real orchestrator loops (`rn-implement`, `loop-router`, `sprint-build-and-validate`) — verified by `ll-loop validate <loop>` exit 0
- Typo'd `${captured.X}` in a sub-loop orchestrator now surfaces as ERROR or WARNING (not silently suppressed)
- All existing tests in `TestCaptureReachabilityValidation` continue to pass

## Scope Boundaries

- **In scope**: Per-variable suppression logic inside `_validate_capture_reachability()` in `validation.py`; new test cases in `TestCaptureReachabilityValidation`
- **Out of scope**: Changes to `_has_sub_loop_state()` implementation; other validation checks in `validation.py`; multi-level (grandchild) sub-loop nesting — treat as a follow-on if needed

## API/Interface

N/A — No public API changes; `_validate_capture_reachability()` is internal to the FSM validation module.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — replace whole-loop suppression guard with per-variable logic
- `scripts/tests/test_fsm_validation.py` — add tests for (a) genuine missing capture in sub-loop loop flagged, (b) legitimate child-provided capture still suppressed

### Dependent Files (Callers/Importers)
- `validate_fsm()` in `scripts/little_loops/fsm/validation.py` (line 1013) — direct caller; exported via `scripts/little_loops/fsm/__init__.py`
- `load_and_validate()` in `scripts/little_loops/fsm/validation.py` (line 1924) — calls `validate_fsm()`; used by `cli/loop/run.py`, `cli/loop/_helpers.py`, `cli/loop/config_cmds.py`, `cli/loop/info.py`, `fsm/executor.py`

### Similar Patterns
- `_has_sub_loop_state()` in `validation.py` — existing helper; may be extended or replaced

### Tests
- `scripts/tests/test_fsm_validation.py` — `TestCaptureReachabilityValidation` class

### Documentation
- N/A

### Configuration
- N/A

## Notes

Lower priority — the false-negative only bites on typos in orchestrator loops.
Whatever approach is chosen must not reintroduce false positives against the
legitimate "capture lives in a child namespace" pattern that ENH-1961 protected.


## Session Log
- `/ll:format-issue` - 2026-06-07T03:47:36 - `32cf3ee0-7e8b-4b29-bb4f-4a7fbbff706f.jsonl`
- `/ll:format-issue` - 2026-06-07T03:33:19 - `aecc5331-8f02-406f-ab88-92ece2b456b7.jsonl`

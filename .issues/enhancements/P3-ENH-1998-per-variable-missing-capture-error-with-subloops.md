---
id: ENH-1998
type: ENH
priority: P3
status: done
captured_at: '2026-06-07T03:21:51Z'
completed_at: '2026-06-07T04:04:17Z'
discovered_date: '2026-06-07'
discovered_by: capture-issue
labels:
- fsm
- validation
relates_to:
- ENH-1961
- BUG-1997
- EPIC-1962
confidence_score: 92
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 18
decision_needed: false
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

> **Selected:** Option B — Downgrade to WARNING — replace the `continue` with a WARNING-severity `ValidationError`; all required infrastructure already exists and eight existing validation checks follow this exact pattern.

- At minimum, skip only when the reference is reachable from a sub-loop state's
  successors, not globally.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-06.

**Selected**: Option B — Downgrade to WARNING for unmatched vars in sub-loop contexts

**Reasoning**: Option B maps directly onto an established codebase pattern — eight existing validation checks in `validation.py` use `ValidationSeverity.WARNING` for "likely wrong but possibly legitimate" conditions, and `load_and_validate()` already separates WARNINGs from ERRORs without any additional changes. The implementation is a single-line substitution in `_validate_capture_reachability()` at `validation.py:1751` with no new infrastructure. Option A is ruled out because `parameters:` declares child *inputs*, not child-produced captures, making the cross-reference unable to identify which `${captured.X}` names a child produces. Option C is more precise but adds ~15 lines of BFS graph traversal for a problem WARNING already solves.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (child contract cross-ref) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option B (downgrade to WARNING) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option C (successor reachability) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option B: `_validate_failure_terminal_action()` and `_validate_artifact_isolation()` use WARNING for the same "suspicious but possibly intentional" pattern; `load_and_validate()` already routes WARNINGs to `logger.warning()` without raising; reuse score 3/3.
- Option A: `_validate_with_bindings()` at `validation.py:333–407` is a structural analog, but `parameters:` declares child *inputs* not outputs — the cross-reference cannot determine which `${captured.X}` names a child produces; reuse score 2/3.
- Option C: `_validate_artifact_overwrite()` at `validation.py:1412–1446` and `_find_reachable_states()` at `validation.py:1799` provide all needed graph primitives; requires ~15 lines of new BFS seeded from sub-loop successors; reuse score 2/3.

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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-06_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 73/100 → MODERATE

### Outcome Risk Factors
- **Open decision on implementation approach** — three distinct options listed in "Expected Behavior" without resolution; this is an unresolved decision that must be resolved before starting. Options differ in whether `_validate_capture_reachability()` requires file-system access (Option 1: child contract cross-reference), changes ERROR to WARNING (Option 2: downgrade unmatched vars), or adds dominator analysis from sub-loop successors (Option 3). Recommend Option 2 (WARNING downgrade) as lowest-complexity path meeting the success metrics.

## Session Log
- `/ll:ready-issue` - 2026-06-07T04:02:14 - `1662160e-cd50-481c-b286-8eb001d705c8.jsonl`
- `/ll:confidence-check` - 2026-06-07T04:00:00Z - `d89ae4c5-b5b2-495b-85d5-a34bcd6a7240.jsonl`
- `/ll:decide-issue` - 2026-06-07T03:58:07 - `6f4fb7ea-c3f7-43fb-8717-384286acf4e0.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:00:00Z - `88eeef44-5e55-4c31-8929-85c991dd6d61.jsonl`
- `/ll:format-issue` - 2026-06-07T03:47:36 - `32cf3ee0-7e8b-4b29-bb4f-4a7fbbff706f.jsonl`
- `/ll:format-issue` - 2026-06-07T03:33:19 - `aecc5331-8f02-406f-ab88-92ece2b456b7.jsonl`

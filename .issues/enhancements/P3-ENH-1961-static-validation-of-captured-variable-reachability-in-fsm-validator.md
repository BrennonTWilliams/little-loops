---
id: ENH-1961
type: ENH
priority: P3
status: done
captured_at: "2026-06-05T18:05:10Z"
completed_at: "2026-06-05T20:30:00Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1962
confidence_score: 75
---

# ENH-1961: Add Static Validation of Captured Variable Reachability in FSM Validator

## Summary

`validate_fsm()` in `scripts/little_loops/fsm/validation.py` checks that all referenced *states* exist, but does not check that `${captured.*}` variables referenced in a state's action are capturable on all code paths leading to that state. This means a loop can pass validation but crash at runtime when a bypassed capture state leaves a variable unpopulated.

Add a static reachability analysis that warns when a state references `${captured.<var>.*}` and there exists at least one code path to that state that does NOT pass through the state that captures `<var>`.

## Current Behavior

Consider this routing pattern from `general-task.yaml`:

```
resume_check → on_yes: mark_done → check_done
resume_check → on_no: select_step → do_work → ... → check_done
```

`check_done` references `${captured.selected_step.output}`, but `selected_step` is only captured by `select_step`. On the `resume_check → mark_done → check_done` path, `select_step` is never executed, so the reference crashes at runtime.

The validator currently checks:
- All `next:`, `on_yes:`, `on_no:`, etc. targets reference existing states
- At least one terminal state exists
- Evaluator configs have required fields
- etc.

But it does NOT check whether captured variables referenced in a state's action are guaranteed to exist on all paths.

## Expected Behavior

`ll-loop validate general-task` should emit a WARNING like:

```
[WARNING] states.check_done.action: References ${captured.selected_step.output} but 'selected_step'
is captured by state 'select_step' which may not execute on all paths to 'check_done'.
Paths bypassing capture: resume_check → mark_done → check_done
```

This is a WARNING (not ERROR) because:
1. It's a static approximation — the validator can't know which branch `resume_check` will take at runtime
2. Some paths may be impossible in practice (dead code paths)
3. Loop authors may intentionally handle the missing case via `on_error` routing

## Motivation

- **Shift-left**: Catch missing-capture bugs at validation time instead of runtime
- **Loop authoring safety**: Especially valuable for complex loops with resume/checkpoint logic where capture states are conditional
- **Template guidance**: When users copy `general-task.yaml` and modify the routing, the validator can flag newly-introduced capture gaps
- **Defense in depth**: Complements ENH-1958 (safe interpolation syntax) — validation warns at authoring time, safe syntax prevents crashes at runtime

## Proposed Solution

### Algorithm

In `validate_fsm()`, after existing structural checks, add a new validation pass:

1. **Build capture map**: For each state `S`, if `S.capture` is set to `<var>`, record that `<var>` is captured by `S`
2. **Build reference map**: For each state `S`, extract all `${captured.<var>.*}` references from `S.action` (and `S.evaluate.source` if present)
3. **For each referenced `<var>` in state `S_ref`**:
   a. Find the capturing state `S_cap`
   b. Compute all simple paths (or use dominance analysis) from `initial` to `S_ref`
   c. If any path exists that reaches `S_ref` without passing through `S_cap`, emit WARNING

### Pragmatic Simplification

Full path enumeration is expensive for complex loops. A simpler and still-useful approximation:

- **Dominance check**: A state `D` **dominates** state `S` if every path from `initial` to `S` must pass through `D`. If `S_cap` does NOT dominate `S_ref`, warn.
- Dominance can be approximated with a reverse BFS from `S_ref` that checks if all predecessors eventually trace back through `S_cap`.

### Scope

- Only analyze `${captured.*}` references (not `${context.*}`, `${env.*}`, etc. — those come from outside the loop)
- Only flag when the capturing state is in the same loop (not for sub-loop captures, which are harder to trace statically)
- Skip states with `next:` unconditional transitions that go through the capture state (these are safe)

## API/Interface

N/A — No public API changes. The new validation is an internal function `_validate_capture_reachability(fsm)` called from `validate_fsm()`; it augments existing validation output but does not change any public signatures or CLI contracts.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_validate_capture_reachability(fsm)` function, call it from `validate_fsm()`
- `scripts/tests/test_fsm_validation.py` — add tests for: missing capture warning, safe capture (all paths pass through), sub-loop capture (skipped), unconditional-next safety

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` calls `load_and_validate()` which calls `validate_fsm()`; new warnings appear in output automatically
- `scripts/tests/test_builtin_loops.py` — may need to update expected warning count for `general-task.yaml` until BUG-1960 is fixed

### Similar Patterns
- Existing `_validate_partial_route_dead_end()` (MR-4) — same pattern: static analysis that warns about potential runtime issues
- Existing reachability BFS in `validate_fsm()` — computes which states are reachable; can be extended for dominance analysis

### Tests
- `test_fsm_validation.py`:
  - `test_capture_reachable_on_all_paths_no_warning` — a loop where capture state dominates reference state
  - `test_capture_bypassed_on_one_path_emits_warning` — the `general-task` pattern: two paths to reference state, one bypasses capture
  - `test_capture_from_sub_loop_skipped` — `${captured.*}` from a sub-loop state is skipped (out of scope)
  - `test_capture_with_unconditional_next_safe` — state has `next:` through capture state, no warning
  - `test_missing_capture_state_emits_error` — referenced capture var has no capturing state at all

### Documentation
- `docs/generalized-fsm-loop.md` — document the new validation rule
- `docs/guides/LOOPS_GUIDE.md` — mention the warning in the loop authoring section

## Implementation Steps

1. **Implement capture/reference extraction** — parse `state.capture` and `${captured.*}` patterns from `state.action` strings across all states
2. **Implement dominance check** — reverse BFS from reference state, verifying all predecessor paths include the capturing state
3. **Wire into `validate_fsm()`** — add call to `_validate_capture_reachability(fsm)` after existing structural validations
4. **Add tests** — all scenarios listed above
5. **Verify on existing loops** — run `ll-loop validate` on all built-in loops; review warnings for false positives
6. **Tune severity** — start as WARNING; consider ERROR after field-testing on real loops

## Scope Boundaries

- **In scope**:
  - Static reachability analysis for `${captured.*}` variable references only
  - Dominance-based approximation (reverse BFS) to avoid full path enumeration
  - Warning emission when a capturing state does not dominate a referencing state
  - Analysis within a single loop (same FSM definition)

- **Out of scope**:
  - `${context.*}`, `${env.*}`, and other non-captured variable references (these come from outside the loop)
  - Sub-loop captures (harder to trace statically across loop boundaries)
  - Runtime validation or dynamic checking (this is purely static analysis)
  - ERROR severity (starts as WARNING; may escalate after field-testing)

## Success Metrics

- **False positive rate**: All existing built-in loops pass `ll-loop validate` without new false-positive warnings (any new warnings should be confirmed bugs like BUG-1960)
- **Detection rate**: The validator correctly flags the known capture gap in `general-task.yaml` (the `resume_check → mark_done → check_done` bypassing path)
- **User experience**: Loop authors receive actionable warnings that include the bypassing path, not just the variable name

## Impact

- **Priority**: P3 — Prevents bugs at authoring time but doesn't fix existing runtime failures; lower urgency than ENH-1958/1959
- **Effort**: Large — ~100-200 lines for BFS-based dominance analysis + tests
- **Risk**: Medium — static analysis is approximate; false positives could annoy loop authors; start as WARNING severity
- **Breaking Change**: No — additive validation only

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm`, `validation`, `static-analysis`, `captured`, `safety`

## Session Log
- `/ll:format-issue` - 2026-06-05T18:13:49 - `85b7b0bc-2759-4162-9d85-db608997f759.jsonl`
- `/ll:capture-issue` - 2026-06-05T18:05:10Z - `6111e846-8894-477b-81b3-17824f89e659.jsonl`

**Open** | Created: 2026-06-05 | Priority: P3

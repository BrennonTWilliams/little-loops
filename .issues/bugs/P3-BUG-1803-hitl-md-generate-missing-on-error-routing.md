---
id: BUG-1803
type: BUG
priority: P3
status: done
captured_at: '2026-05-29T21:57:08Z'
completed_at: '2026-05-29T22:25:47Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1803: hitl-md generate state missing on_error routing causes fatal loop termination

## Summary

The `generate` state in `scripts/little_loops/loops/hitl-md.yaml` has `next: "evaluate"` but no `on_error` routing. When the 16KB prompt action fails to start, the FSM engine terminates with `terminated_by: "error"` instead of routing to the `failed` terminal for diagnostics. This makes the `failed` terminal unreachable from the generate phase of the loop.

## Current Behavior

The `generate` state is defined as:
```yaml
generate:
  action: "Read ${captured.run_dir.output}/segments.json..."
  action_type: prompt
  next: evaluate
```

When the prompt action encounters an error (e.g., template interpolation failure, token limit exceeded), the FSM engine has no recovery path — it terminates immediately with `loop_complete` / `terminated_by: "error"`. The `failed` terminal state (which produces a diagnostic summary) is never reached because only `score.on_error` routes to it, and `score` is downstream of `generate`.

## Expected Behavior

The `generate` state should route errors to a state that produces diagnostics and terminates gracefully:

```yaml
generate:
  action: "..."
  action_type: prompt
  next: evaluate
  on_error: failed
```

This matches the pattern used by `score.on_error: failed` and ensures the `failed` terminal's diagnostic action runs (checking for critique.md, segments.json, and summarizing failure cause).

## Motivation

The `hitl-md` loop failed on its most recent run (`2026-05-29T213409`) at the generate state with `terminated_by: "error"` before the action even started (no `action_start` event emitted). The segments.json was successfully produced (160 segments, 112KB), but index.html was never generated. Without `on_error` routing, there is no recovery path and no diagnostic output — the operator gets a silent failure.

## Steps to Reproduce

1. Run `ll-loop run hitl-md --input "PRD-Hermes-Integration-v3.md"`
2. Observe the segment state completes and writes segments.json
3. Observe the loop transitions to generate state
4. Observe the loop terminates with `terminated_by: "error"` before `action_start` is emitted for generate

## Root Cause

The `generate` state at `scripts/little_loops/loops/hitl-md.yaml:151` has `action_type: prompt` and `next: evaluate` but no `on_error` field. When the prompt action raises an exception (interpolation error, token limit exceeded, CLI crash), the FSM executor's `_run_action_or_route()` at `scripts/little_loops/fsm/executor.py:1309` checks `state.on_error` — finding `None`, it re-raises the exception (line 1319). The exception propagates to `run()` at line 491, which calls `_finish("error")`, producing `terminated_by: "error"` without ever entering the `failed` terminal state that would produce diagnostic output.

For non-exception failures (non-zero exit codes from the prompt action), `_execute_state()` at `executor.py:825` only routes to `on_error` when the field is set — without it, the failure silently falls through to `next: evaluate`, bypassing error handling entirely.

The `score` state (line 591, `on_error: failed`) and `evaluate` state (line 453, `on_error: generate`) in the same loop already define `on_error`, making `generate` the lone unguarded state in the core `generate → evaluate → score` pipeline.

## Proposed Solution

Add `on_error: failed` to the `generate` state in `scripts/little_loops/loops/hitl-md.yaml`:

```yaml
states:
  generate:
    action: "Read ${captured.run_dir.output}/segments.json for the ordered segment list..."
    action_type: prompt
    next: evaluate
    on_error: failed
```

This is a one-line change that wires the existing `failed` terminal into the generate phase's error path.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/hitl-md.yaml` — add `on_error: failed` to `generate` state

### Dependent Files (Callers/Importers)
- N/A — no callers import the loop YAML directly

### Similar Patterns
- `scripts/little_loops/loops/hitl-md.yaml` `score` state already has `on_error: failed` — this fix mirrors that pattern
- `scripts/little_loops/loops/svg-image-generator.yaml` `evaluate` state has `on_error: generate` — deliberate divergence documented in hitl-md description
- Other harness loops (`apo-textgrad`, `hitl-compare`) should be checked for the same missing on_error pattern

### Tests
- **Existing coverage**: `scripts/tests/test_builtin_loops.py` — `TestHitlMdLoop` class (line 3467) has `test_score_on_error_routes_to_failed` (line 3582) and `test_evaluate_on_error_routes_to_generate` (line 3547), but no test verifies that `generate` has `on_error` defined
- **Related executor tests**: `scripts/tests/test_fsm_executor.py` — `test_exception_in_branch_c_without_on_error_reraises` (line 2656) and `test_interpolation_error_routes_to_on_error_when_set` (line 2730) verify the executor behavior this bug triggers
- **Related issue**: `P2-BUG-1602` — same class of bug fixed in `scripts/little_loops/loops/hitl-compare.yaml` `evaluate` state
- **Suggested new test**: Add `test_generate_on_error_routes_to_failed` to `TestHitlMdLoop`, following the pattern of `test_score_on_error_routes_to_failed`
- **Manual verification**: re-run the failing invocation and confirm the `failed` terminal produces diagnostic output

### Documentation
- N/A

### Configuration
- N/A

### Behavioral Couplings

_Wiring pass added by `/ll:wire-issue`:_

Adding `on_error: failed` to `generate` changes the termination path for generate-state errors. These side effects don't require code changes but are worth noting during implementation and testing:

- **Exit code change** (`scripts/little_loops/cli/loop/_helpers.py` `EXIT_CODES` dict, line ~33): Without `on_error`, generate errors produce `terminated_by: "error"` which falls through to the default exit code **1**. With `on_error`, the loop routes to the `failed` terminal, producing `terminated_by: "terminal"` which maps to exit code **0**. Automation that checks exit codes of `ll-loop run hitl-md` for generate-state failures will see 0 instead of 1 after the fix.
- **Persistence status flip** (`scripts/little_loops/fsm/persistence.py` lines 725-733): `final_status` changes from `"failed"` to `"completed"` for generate errors. This affects `ll-loop history` queries and any downstream consumers of the persistent store.
- **New `action_error` event**: The `action_error` event (schema in `docs/reference/EVENT-SCHEMA.md`) will now be emitted for generate-state errors. Previously, generate exceptions propagated without emitting this event. Event-stream consumers that aggregate on `action_error` events will see a new emission point.
- **`failed` terminal diagnostic action does not execute on routing**: The `failed` state has both `terminal: true` and a diagnostic prompt action. Because the executor checks `terminal` before calling `_execute_state()` (`executor.py` line 339 vs. 402), the diagnostic prompt never runs when `failed` is reached via routing. This is pre-existing behavior — the same applies to `score.on_error: failed`. The fix improves error routing (clean termination instead of a crash) but the diagnostic action still only fires when `failed` is the `initial` state.
- **Coordination with P3-ENH-1804**: That enhancement plans to extract `generate`'s 16KB prompt to a shared fragment file — it touches the same `generate` state definition. Whichever issue is implemented second should merge the changes (the `on_error` line from this fix + the fragment ref from ENH-1804).

## Implementation Steps

1. Edit `scripts/little_loops/loops/hitl-md.yaml` — add `on_error: failed` to `generate` state
2. Validate: `ll-loop validate hitl-md`
3. Re-run the failing invocation to confirm error routing works
4. Audit other harness loops for the same missing `on_error` pattern
5. Add `test_generate_on_error_routes_to_failed` to `TestHitlMdLoop` in `scripts/tests/test_builtin_loops.py` — follow the pattern of `test_score_on_error_routes_to_failed`:
   ```python
   def test_generate_on_error_routes_to_failed(self, data: dict) -> None:
       state = data["states"].get("generate", {})
       assert state.get("on_error") == "failed"
   ```

### Wiring Phase (added by `/ll:wire-issue`)

_Not new files to change, but behavioral side effects to verify during implementation and testing:_

N+1. After the fix, verify exit code behavior: a generate-state error should now produce exit code 0 (via `failed` terminal) instead of exit code 1 (via exception re-raise). See `EXIT_CODES` dict in `scripts/little_loops/cli/loop/_helpers.py`.
N+2. Verify `ll-loop history` reports `final_status: "completed"` (not `"failed"`) for generate-error runs post-fix. See persistence mapping in `scripts/little_loops/fsm/persistence.py:725-733`.
N+3. Confirm an `action_error` event is now emitted for generate errors (previously it was not). The event schema is in `docs/reference/EVENT-SCHEMA.md` (generated by `scripts/little_loops/generate_schemas.py`).
N+4. Coordinate with P3-ENH-1804 — that enhancement touches the same `generate` state for prompt extraction. Whichever lands second must merge both changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **FSM executor error path**: `_run_action_or_route()` at `scripts/little_loops/fsm/executor.py:1295-1319` is the primary mechanism — adding `on_error` causes the exception handler (line 1309) to route instead of re-raise (line 1319)
- **Non-exit-code failures also affected**: `_execute_state()` at `executor.py:825-826` only routes non-zero exit codes to `on_error` when the field is set — without the fix, `generate` silently advances to `evaluate` on non-zero CLI exit
- **Loop audit candidates**: `segment` state (line 53) in `scripts/little_loops/loops/hitl-md.yaml` also lacks `on_error`; `scripts/little_loops/loops/apo-textgrad.yaml` `generate` state should be checked for the same gap
- **Validation gap**: `_validate_state_routing()` at `scripts/little_loops/fsm/validation.py:467` checks that at least one transition mechanism exists but does not require `on_error` on `action_type: prompt` states — a follow-up enhancement could add a QC warning for this pattern
- **Original `on_error` routing feature**: `P3-ENH-1168` added the `on_error` routing capability to `_run_action_or_route()`

## Impact

- **Priority**: P3 — The loop works on smaller/simpler inputs; the 16KB prompt size triggers the edge case. Affects usability but not data integrity.
- **Effort**: Small — One-line YAML change
- **Risk**: Low — Adds error routing only; normal (non-error) path unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm-routing`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-05-29T22:23:03 - `13d03593-4544-4171-b680-300ae620d860.jsonl`
- `/ll:confidence-check` - 2026-05-29T22:17:00 - `fd469e18-dee2-4c15-834f-59aaa5311c6d.jsonl`
- `/ll:wire-issue` - 2026-05-29T22:15:22 - `a35403e4-d8a3-42c9-94dc-7772464196bf.jsonl`
- `/ll:refine-issue` - 2026-05-29T22:08:48 - `dc21010e-a01f-4d69-8946-c34633cb7571.jsonl`
- `/ll:format-issue` - 2026-05-29T22:00:02 - `e594fda4-804f-47e5-8431-2051fd565d1e.jsonl`

- `/ll:capture-issue` — 2026-05-29T21:57:08Z — `64ba091c-1c65-464a-81b6-237b5a702007.jsonl`
- `/ll:manage-issue` — 2026-05-29T22:25:47Z — `8e6b8291-2150-4ebb-a43c-cc19c32c002b.jsonl`

---

**Done** | Created: 2026-05-29 | Priority: P3

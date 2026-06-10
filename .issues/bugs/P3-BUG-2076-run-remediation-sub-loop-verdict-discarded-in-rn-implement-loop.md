---
discovered_date: 2026-06-10
discovered_by: debug-loop-run
source_loop: rn-implement
source_state: run_remediation
status: cancelled
decision_needed: false
labels:
- rn-implement
- loop-defect
- sub-loop
---

# BUG-2076: run_remediation sub-loop verdict discarded in rn-implement loop — rn-remediate result ignored (classify_remediation)

## Summary

The `run_remediation` state in `rn-implement` invokes the `rn-remediate` sub-loop with `on_yes: classify_remediation` and `on_no: classify_remediation` — both outcomes route to the same state. The sub-loop's success/failure verdict is structurally discarded: `classify_remediation` always runs regardless of whether remediation succeeded or failed, relying entirely on downstream output-pattern chains (`route_rem_implemented → route_rem_decompose → ...`) to infer the outcome from captured output.

This is a config-based design smell independent of execution frequency. In the observed run, the sub-loop crashed before reaching `classify_remediation`, so the impact was masked — but any successful remediation run would also route `on_yes` and `on_no` identically, making the sub-loop verdict a no-op in the FSM.

## Loop Context

- **Loop**: `rn-implement`
- **State**: `run_remediation`
- **Signal type**: sub_loop_verdict_discarded (config-based)
- **Child loop**: `rn-remediate`
- **Shared next state**: `classify_remediation`
- **Occurrences**: config-level — fires every run

## History Excerpt

Events leading to this signal (config evidence):

```json
[
  {"event": "state_enter", "ts": "2026-06-10T17:02:26.053804+00:00", "state": "run_remediation", "iteration": 7},
  {"event": "loop_start", "ts": "2026-06-10T17:02:26.078651+00:00", "loop": "rn-remediate", "depth": 1},
  {"event": "loop_complete", "ts": "2026-06-10T17:05:51.501086+00:00", "final_state": "assess", "iterations": 1, "terminated_by": "error", "depth": 1},
  {"event": "route", "ts": "2026-06-10T17:05:51.501647+00:00", "from": "run_remediation", "to": "record_sub_loop_crash"}
]
```

Config state (from `ll-loop show rn-implement --resolved`):
```yaml
run_remediation:
  loop: rn-remediate
  on_yes: classify_remediation
  on_no: classify_remediation   # same as on_yes — verdict discarded
```

## Root Cause

- **File**: `scripts/little_loops/loops/rn-implement.yaml`
- **Anchor**: state `run_remediation`
- **Cause**: Both `on_yes` and `on_no` are set to `classify_remediation`, so the FSM discards the sub-loop verdict. `classify_remediation` always executes regardless of whether `rn-remediate` succeeded or failed, forcing it to re-infer success/failure from output-pattern chains rather than reading the signal already present in the FSM.

## Expected Behavior

The `run_remediation` state should route differently based on whether rn-remediate succeeded or failed:

- `on_yes: classify_remediation` — remediation completed; proceed to outcome classification
- `on_no: record_failure` or `on_no: mark_deferred` — remediation explicitly failed; skip classify_remediation and record outcome directly

This preserves the sub-loop verdict in the FSM topology and avoids forcing `classify_remediation` to infer failure from output patterns when the FSM already has that information.

## Proposed Solution

In `scripts/little_loops/loops/rn-implement.yaml`, differentiate `run_remediation`'s routing:

```yaml
run_remediation:
  loop: rn-remediate
  on_yes: classify_remediation
  on_no: record_failure          # or mark_deferred — route failures explicitly
```

If `classify_remediation` must handle both success and failed-but-partial cases (e.g. partial remediation output), consider adding an `on_partial` route that fast-paths to the appropriate classification branch rather than running the full output-pattern chain.

Note: the `record_sub_loop_crash` path (used for infrastructure crashes / error termination) is separate from the FSM `on_yes`/`on_no` routing and can remain unchanged.

## Implementation Steps

1. Open `scripts/little_loops/loops/rn-implement.yaml` and locate the `run_remediation` state
2. Change `on_no` from `classify_remediation` to a distinct failure state (e.g., `record_failure` or `mark_deferred`); add that state if it doesn't exist
3. Optionally add `on_partial: classify_remediation` if partial-remediation output still needs classification
4. Run `ll-loop validate rn-implement` to confirm no sub-loop-verdict-discarded warning
5. Add assertion in `scripts/tests/test_builtin_loops.py` that `run_remediation.on_yes != run_remediation.on_no`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — update `run_remediation` routing (`on_no` → distinct failure state)
- `scripts/tests/test_builtin_loops.py` — add regression test asserting distinct `on_yes` / `on_no` routes

### Dependent Files (Callers/Importers)
- No external callers. `grep -r "loop: rn-remediate" scripts/little_loops/loops/` returns only two hits: `rn-implement.yaml` (the parent) and `rn-remediate.yaml` itself (recursive self-invocation). No other loop delegates to `rn-remediate`.

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml` state `run_decomposition` (lines ~553–568) — identical sidecar pattern: `on_success: classify_decomposition`, `on_failure: classify_decomposition`, `on_error: record_sub_loop_crash`. Both states use the same ENH-2005 intentional design.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CRITICAL: This issue's premise conflicts with completed ENH-2005.**

- **ENH-2005** (Completed 2026-06-07) — explicitly annotated `run_remediation` and `run_decomposition` as intentional sidecar routing. The explanatory comment at `rn-implement.yaml:491–497` reads:
  > `on_success == on_failure is INTENTIONAL sidecar routing, not verdict laundering. The child's real outcome is read from subloop_outcome_<ID>.txt by classify_remediation, so collapsing the done/failed verdict here is by design. on_error is NOT collapsed…`

- **Sidecar mechanism**: `rn-remediate` writes its real outcome token to `${run_dir}/subloop_outcome_${issue_id}.txt`. `classify_remediation` (line 512) reads that file with `cat … || echo "IMPLEMENT_FAILED"`. The outcome chain (`route_rem_implemented → route_rem_decompose → route_rem_manual_review → route_rem_rate_limited`) maps tokens `IMPLEMENTED`, `NEEDS_DECOMPOSE`, `MANUAL_REVIEW_NEEDED`, `RATE_LIMITED` to distinct states — a richness the bare `on_success`/`on_failure` FSM signal cannot express.

- **Terminology error in issue**: The issue uses `on_yes`/`on_no` throughout (including the History Excerpt), but `run_remediation` is a `loop:` delegation state and uses `on_success`/`on_failure`/`on_error` — not `on_yes`/`on_no`. The actual current config keys are `on_success`/`on_failure`.

- **Proposed fix would regress behavior**: Routing `on_failure: record_failure` directly would skip `classify_remediation`, losing the `NEEDS_DECOMPOSE`, `RATE_LIMITED`, and `MANUAL_REVIEW_NEEDED` outcome paths. A failed rn-remediate sub-loop can still produce an actionable sidecar token.

- **Source of false positive**: `debug-loop-run` detected the collapsed-route shape (both routes to same state) and emitted `sub_loop_verdict_discarded`. The signal predates ENH-2005's explanatory comments (completed 2026-06-07); the auditor reads the shape structurally, not the inline design comment.

**Assessment**: This issue is a false positive. The behavior is intentional and documented. Recommend closing as `cancelled` with a note referencing ENH-2005.

### Tests
- `scripts/tests/test_rn_implement.py` — dedicated rn-implement tests; lines ~255–265 already assert `run_remediation` routes to `classify_remediation` on both success and failure (matching current intentional behavior); `TestParentClassifier` class (lines ~593–603) covers ENH-1977 orchestration fixes
- `scripts/tests/test_builtin_loops.py` — integration tests for all built-in loops

### Documentation
- N/A

### Configuration
- `scripts/little_loops/loops/rn-implement.yaml` — FSM state config only

## Acceptance Criteria

- [ ] `run_remediation.on_yes` and `run_remediation.on_no` route to distinct states in `rn-implement.yaml`
- [ ] `ll-loop validate rn-implement` no longer flags `run_remediation` for the sub-loop verdict discarded rule
- [ ] A test in `test_builtin_loops.py` asserts `run_remediation.on_yes != run_remediation.on_no`

## Labels

`bug`, `loops`, `rn-implement`, `sub-loop`, `captured`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-06-10T17:22:29 - `70d57987-45fa-4847-b696-68ca2b6d045c.jsonl`
- `/ll:format-issue` - 2026-06-10T17:17:46 - `e0c105a5-0129-4c08-8b37-7d18c3637196.jsonl`

---
id: FEAT-2000
title: Author loops/ll-auto.yaml FSM definition and validate
type: FEAT
priority: P2
status: blocked
parent: EPIC-1867
blocked_by:
- FEAT-1901
relates_to:
- FEAT-2001
- FEAT-1902
blocks:
- FEAT-2001
- FEAT-1899
size: Medium
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2000: Author loops/ll-auto.yaml FSM definition and validate

## Summary

Write `loops/ll-auto.yaml` as the FSM that defines `ll-auto` control flow, using
queue-orchestration shape from `scripts/little_loops/loops/autodev.yaml` as a template. Validate the
loop with `ll-loop validate`, `diagnose-evaluators`, and `--baseline` checks.

## Current Behavior

`ll-auto` control flow lives entirely in Python (`AutoManager.run()`), with no FSM YAML
definition. This makes FSM-level validation (`ll-loop validate`, `diagnose-evaluators`,
`--baseline`) impossible against the current implementation.

## Expected Behavior

`loops/ll-auto.yaml` exists as a validated FSM defining `ll-auto` control flow in the
queue-orchestration shape. `ll-loop validate ll-auto` passes with no MR-1 or MR-3
violations, `diagnose-evaluators` confirms `verify_work` verdict variance `p(1-p) ≥ 0.05`,
and `--baseline` checks confirm harness quality meets or exceeds unguided baseline.

## Motivation

This feature:
- Enables FSM-level quality gates (`ll-loop validate`, `--baseline`) currently impossible
  against the Python implementation
- Provides a machine-readable control-flow definition that improves debuggability and
  auditability of `ll-auto` orchestration
- Completes the EPIC-1867 FSM decomposition, giving `ll-auto` the same validation
  infrastructure as other loop-based orchestrators

## Parent Issue

Decomposed from FEAT-1902: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness

## Use Case

Developer authors the FSM YAML that will replace `AutoManager.run()` control flow,
enabling `ll-loop validate` and `--baseline` quality checks that are impossible against
the Python implementation.

## Implementation Steps

1. Confirm FEAT-1901 Layer-0 CLI subcommands are available (`ll-issues next`,
   `ll-issues verify-work`, `ll-issues classify-failure`); if not yet merged, stub the
   `verify_work` state with a placeholder shell command (`echo "stub: verify-work"`)
   that exits 0/1 based on a deterministic condition for testing.

2. Author `loops/ll-auto.yaml` FSM:
   - Model on `scripts/little_loops/loops/autodev.yaml` queue-orchestration shape
   - Top-level fields: `initial: init`, `max_iterations: 500`, `timeout: 28800`,
     `on_handoff: spawn`, `import: - lib/common.yaml`
   - States: `init` (count backlog), `dequeue_next` (`fragment: queue_pop` +
     `capture: input`), `implement`, `verify_work` (exit_code evaluator calling
     `ll-issues verify-work ${captured.input.output} --baseline ${context.baseline_sha}`),
     `classify_failure`, `done`
   - Use `fragment: shell_exit` for `init`, `implement`, `verify_work`, `classify_failure`
   - Write all intermediate files to `${context.run_dir}/`

   > **Decision (ARCHITECTURE-030, ENH-2106):** The `implement` state MUST delegate to
   > `loop: per-issue-processor` via sub-loop composition — do NOT inline per-issue
   > processing states. Use the `rn-implement.yaml:491` sidecar-token pattern:
   > ```yaml
   > implement:
   >   loop: per-issue-processor
   >   with:
   >     issue_id: "${captured.input.output}"
   >     baseline_sha: "${context.baseline_sha}"
   >   on_success: dequeue_next
   >   on_failure: classify_failure
   > ```
   > Read outcome from `${context.run_dir}/subloop_outcome_${captured.input.output}.txt`.
   > The shared loop file will live at `loops/per-issue-processor.yaml` (NOT under `loops/lib/`).

3. Run `ll-loop validate ll-auto` — fix all MR-1 and MR-3 violations until clean.

4. Run `ll-loop diagnose-evaluators ll-auto` over ≥10 runs — confirm `verify_work`
   verdict variance `p(1-p) ≥ 0.05`.

5. Run `ll-loop run ll-auto --baseline` — confirm harness performance ≥ unguided baseline.

6. Add `"ll-auto"` to the `expected` set in
   `scripts/tests/test_builtin_loops.py:test_expected_loops_exist()` (line ~73).
   Without this update, adding `ll-auto.yaml` causes `actual != expected` failure.

7. Create `scripts/tests/test_ll_auto_loop.py` — per-loop YAML test following pattern
   from `scripts/tests/test_rn_plan.py`:
   - `LOOP_FILE = BUILTIN_LOOPS_DIR / "ll-auto.yaml"`
   - Assert file exists, YAML parses, `load_and_validate` passes `validate_fsm` with no
     ERROR-severity results
   - Required states: `init`, `dequeue_next`, `implement`, `verify_work`, `classify_failure`, `done`
   - `verify_work` action contains `"ll-issues verify-work"`

## Acceptance Criteria

- [ ] `loops/ll-auto.yaml` exists and passes `ll-loop validate ll-auto` (MR-1 and MR-3 clean)
- [ ] `verify_work` state uses an `exit_code` evaluator (or placeholder stub if FEAT-1901 not merged)
- [ ] `max_iterations` is set to a static ceiling (500+) with queue depletion as termination signal
- [ ] `ll-loop diagnose-evaluators ll-auto` reports `verify_work` verdict variance `p(1-p) ≥ 0.05` (or skip if running stubs)
- [ ] `ll-loop run ll-auto --baseline` shows harness ≥ unguided baseline
- [ ] `"ll-auto"` is in the `expected` set in `test_builtin_loops.py`
- [ ] `scripts/tests/test_ll_auto_loop.py` exists and passes

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/ll-auto.yaml` — create new FSM loop definition
- `scripts/tests/test_builtin_loops.py` — add `"ll-auto"` to `expected` set (~line 73)
- `scripts/tests/test_ll_auto_loop.py` — new file; per-loop YAML test

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "ll-auto" scripts/`

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml` — closest structural template: queue-based orchestration loop
- `loops/rn-refine.yaml` — canonical MR-1 pattern with non-LLM evaluator
- `scripts/tests/test_rn_plan.py` — template for per-loop YAML tests

### Tests
- `scripts/tests/test_ll_auto_loop.py` — new per-loop YAML test (assert exists, YAML parses, `validate_fsm` clean)
- `scripts/tests/test_builtin_loops.py` — add `"ll-auto"` to `expected` set

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2
- **Effort**: Medium — new YAML file with validation and tests; no Python changes
- **Risk**: Low — additive only; no existing code modified in this child

## Labels

`automation`, `loops`, `fsm`, `feat`

## Status

**Open** | Created: 2026-06-07 | Priority: P2

## Verification Notes (2026-06-17)

- `loops/ll-auto.yaml` does not exist (correctly unimplemented). `test_ll_auto_loop.py` does not exist.
- `ENH-2106` was listed in `blocked_by` but its status is `done` — removed from the blockers list.
- Remaining blocker: FEAT-1901 (`ll-issues next`/`verify-work` subcommands still unimplemented).

## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - Status corrected open -> blocked: FEAT-1901 (blocked_by) is unstarted; frontmatter now reflects the true chain state.
- `/ll:verify-issues` - 2026-06-27T19:13:21 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:verify-issues` - 2026-06-25T00:51:21 - `3417b033-6605-44ca-9411-53f9fd585b45.jsonl`
- `/ll:verify-issues` - 2026-06-18T02:52:53 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:format-issue` - 2026-06-07T20:58:15 - `cd20bf16-b103-4e35-9958-d8e7c9147ee9.jsonl`
- `/ll:issue-size-review` - 2026-06-07T00:00:00Z - `5db94c28-db76-4bed-885c-95a49da744cb.jsonl`

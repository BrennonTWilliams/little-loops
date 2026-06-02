---
captured_at: '2026-05-23T16:40:11Z'
completed_at: '2026-05-24T22:12:06Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
status: done
depends_on:
- BUG-1628
- ENH-1658
decision_needed: false
confidence_score: 100
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1631: Add `on_max_iterations` summary hook to FSM runtime + general-task loop

## Summary

When an FSM loop hits `max_iterations`, the runtime silently terminates in whatever state was last executing — leaving the operator with no structured account of what was accomplished vs. what remains. Add an `on_max_iterations: <state>` field at the loop top level (parallel to `on_retry_exhausted` on individual states) and wire `general-task.yaml` to use it for writing a partial-run summary to disk.

## Current Behavior

When `FSMExecutor.run()` exhausts its `max_iterations` budget, it terminates in whatever state was last executing and emits a generic `failed`/cap-reached outcome. No structured summary artifact is written, no distinct event signals partial completion to audit tooling, and the operator must reconstruct progress by hand from the JSONL transcript. Individual states already support `on_retry_exhausted` (`scripts/little_loops/fsm/schema.py:785`), but there is no loop-level equivalent for the iteration-cap case.

## Expected Behavior

The loop YAML schema accepts a top-level `on_max_iterations: <state>` field. When the iteration cap fires and this field is set, the runtime transitions to the named state for exactly one additional action+evaluate cycle, then terminates. The runtime emits an event (e.g., `max_iterations_summary` or an extended `_finish` payload) that audit tooling can use to distinguish "terminated with summary" from "terminated cold." `general-task.yaml` ships with a `summarize_partial` state that writes `${env.PWD}/.loops/tmp/general-task-summary.md` describing what was accomplished, remaining DoD gaps, and recommended next actions.

## Motivation

A recent `general-task` run (`2026-05-23T113819`) terminated at iteration 100 with 10/18 DoD criteria passing and a fully-checked plan. The only artifact left behind was the DoD file with mixed `[x]`/`[ ]` markers — no narrative summary of what was attempted, what failed, or what an operator should do next. For the harness's most generic loop, this is the difference between "the run produced something I can pick up" and "I have to reread 100 iterations of JSONL to understand the state."

This is structurally similar to `on_retry_exhausted` on `StateConfig` (already supported in `scripts/little_loops/fsm/schema.py:785`), just lifted to the loop level for the iteration-cap case.

## Proposed Solution

### Runtime change (`scripts/little_loops/fsm/`)

1. Add `on_max_iterations: str | None = None` to the loop-level schema (alongside `max_iterations: int = 50`) in `scripts/little_loops/fsm/schema.py`.
2. In `FSMExecutor.run()`, when the iteration cap fires, if `on_max_iterations` is set, transition to that state for one final action+evaluate cycle before terminating. Cap the post-budget execution at 1 extra iteration to prevent runaway.
3. Emit a new event (`max_iterations_summary` or extend `_finish` payload) so audit tooling can detect partial-completion termination distinctly from `failed` or `done`.

### Loop change (`scripts/little_loops/loops/general-task.yaml`)

```yaml
max_iterations: 100
on_max_iterations: summarize_partial

states:
  summarize_partial:
    action: |
      Read ${env.PWD}/.loops/tmp/general-task-dod.md and
      ${env.PWD}/.loops/tmp/general-task-plan.md. Write a one-paragraph
      summary to ${env.PWD}/.loops/tmp/general-task-summary.md covering:
      (1) what was accomplished, (2) which DoD criteria remain unmet,
      (3) recommended next actions for a human operator.
    action_type: prompt
    next: done
```

### Tests / docs

- `scripts/tests/test_fsm_executor.py` — add a regression test for a loop that hits `max_iterations` and verify the summary state runs exactly once.
- `docs/guides/LOOPS_GUIDE.md` — document the new top-level field.
- `docs/reference/API.md` — update FSM schema reference.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/schema.py` — `FSMLoop` dataclass (add `on_max_iterations: str | None = None` field alongside `max_iterations: int = 50` at line 875); update `from_dict()` (line 987 block), `to_dict()` (after `on_handoff` serialization at line 922), and `get_all_referenced_states()` (line 1031) to include the new field's target state in the reference set
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` at the cap-check branch (line 279); see Implementation Notes below for the flag approach
- `scripts/little_loops/fsm/validation.py` — `KNOWN_TOP_LEVEL_KEYS` frozenset (line 100); add `"on_max_iterations"` to avoid the unknown-key WARNING; optionally add a validation check that the named state exists (parallel to the `circuit.repeated_failure` state-ref check)
- `scripts/little_loops/loops/general-task.yaml` — add `on_max_iterations: summarize_partial` at top level (after `on_handoff: spawn`) and add the `summarize_partial` state to `states:` (before `done:`)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/executor.py:_` — imports `FSMLoop` from `schema.py`; the cap-check branch at line 279 is the sole modification site
- `scripts/little_loops/fsm/validation.py:_` — imports `FSMLoop`; reads `KNOWN_TOP_LEVEL_KEYS` at line 100

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.run()` wraps `FSMExecutor`; reads `result.terminated_by` at `final_status` assignment; safe since `terminated_by` stays `"max_iterations"` after the summary state — but must verify the `_summary_state_executed` flag path does not affect `ExecutionResult.terminated_by` before `PersistentExecutor` reads it [Agent 1 + 2 finding]
- `scripts/little_loops/cli/loop/run.py` — imports `FSMExecutor`, calls `FSMExecutor.run()` in `cmd_run()`; also applies `--max-iterations` CLI override to `fsm.max_iterations` (no parallel `--on-max-iterations` override, which is by design per scope boundaries) [Agent 1 finding]
- `scripts/little_loops/cli/loop/testing.py` — imports `FSMExecutor`; `ll-loop simulate` exercises the executor code path; verify simulate behavior is correct when `on_max_iterations` is set (does it run the summary state or skip it?) [Agent 1 + 2 finding]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store.py` — `_LOOP_EVENT_TYPES` frozenset (lines 55–65): `"max_iterations_summary"` is absent; after ENH-1631 the event is emitted but not recorded in the SQLite `loop_events` table — `ll-session search --fts` and `ll-history` will not surface partial-run summary events; add `"max_iterations_summary"` to the frozenset [Agent 2 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — `display_progress()` inner function in `run_foreground()`: no handler branch for `"max_iterations_summary"` event type; during a live run the event fires and is silently ignored in the terminal display; add a display branch so operators see the hook fire (e.g., print summary-state name and iteration count) [Agent 2 finding]
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()` config display at lines 767–768 prints `max: {fsm.max_iterations} iter` and `handoff: {fsm.on_handoff}` but not `on_max_iterations`; add `on_max_iterations` to the display block when the field is set [Agent 2 finding]

### Similar Patterns

- `scripts/little_loops/fsm/schema.py:882` — `on_handoff: Literal["pause", "spawn", "terminate"]` on `FSMLoop` — the existing top-level hook field; model `from_dict`, `to_dict`, and default handling after this
- `scripts/little_loops/fsm/schema.py:378` — `on_retry_exhausted: str | None = None` on `StateConfig` — the state-level equivalent; model the executor branch and event emission after this (`executor.py:354`)

### Tests

- `scripts/tests/test_fsm_executor.py` — `TestFSMExecutor.test_max_iterations_respected` (~line 154): baseline max_iterations test to extend; model new tests on `TestPerStateRetryLimits` for event emission and state-routing assertions
- `scripts/tests/test_fsm_schema.py` — `TestFSMLoop.test_roundtrip_serialization` (~line 756): add a roundtrip case for `on_max_iterations`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation.py` — **new test class needed**: `TestOnMaxIterationsValidation` (model on `TestCircuitValidation.test_circuit_recognized_as_top_level_key` and `test_on_repeated_failure_unknown_state_rejected`): (1) `on_max_iterations` key produces no "Unknown top-level" warning via `load_and_validate`; (2) `on_max_iterations` pointing to a non-existent state raises `ValueError`; (3) `on_max_iterations` pointing to a declared state passes — also model the **paired-field pattern** from `TestRateLimitFieldValidation` [Agent 1 + 3 finding]
- `scripts/tests/test_general_task_loop.py` — **WILL BREAK**: `TestGeneralTaskLoopFile.test_expected_states_present` (~line 52) hard-codes the states set; must add `"summarize_partial"` when the new state is added to `general-task.yaml`; add a `TestENH1631SummarizePartial` class to verify `on_max_iterations: summarize_partial` is set at the top level and the state's `action` references the DoD and plan artifact paths [Agent 3 finding]
- `scripts/tests/test_generate_schemas.py` — **WILL FAIL** if `max_iterations_summary` is added as a named event to `generate_schemas.py`: four methods hardcode `34`: `test_all_34_event_types_defined` (count + expected set), `test_creates_34_files` (file count assertion), `test_creates_output_dir_if_missing` (file count), `test_cli_creates_files` (file count) — update all four 34→35; also add `"max_iterations_summary"` to `expected` in `test_all_34_event_types_defined` [Agent 2 + 3 finding]

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — add `on_max_iterations` to the loop-level field reference (currently describes `general-task` at lines 271–279)
- `docs/reference/API.md` — update `LoopConfig`/`FSMLoop` schema reference
- `docs/reference/EVENT-SCHEMA.md` — document new `max_iterations_summary` event (or extended `loop_complete` payload; line 530 describes current `loop_complete`)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/audit-loop-run/SKILL.md` — **required by Acceptance Criteria**: Step 6 verdict table must add a row for `terminated_by == "max_iterations"` AND `max_iterations_summary` event present → verdict `partial` (summary written); without this, the skill cannot distinguish "terminated with summary" from "terminated cold" as required by AC item 4 [Agent 2 finding]
- `skills/debug-loop-run/SKILL.md` — Step 2 event-payload table: add `max_iterations_summary` row with key fields (`summary_state`, `iterations`); without this the event falls through to the generic `k=v` fallback in `_format_history_event()` [Agent 2 finding]
- `skills/create-loop/loop-types.md` — `general-task` section: document the new `on_max_iterations: summarize_partial` pattern after the "Partial DoD Satisfaction Threshold" section so operators using `create-loop` know this field is available [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — documents the top-level field set alongside `on_handoff: spawn` and `max_iterations`; add `on_max_iterations` to the field table so the overview stays consistent with the schema [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — field reference table (line 340) lists `max_iterations: integer` without `on_max_iterations`; troubleshooting table (line 721) lists `on_retry_exhausted` as the only mitigation for an exhausted iteration budget — add `on_max_iterations` as a second option in both places [Agent 2 finding]

### Configuration

- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `on_max_iterations` property if JSON schema is used for IDE validation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/generate_schemas.py` — add `max_iterations_summary` event schema entry to `SCHEMA_DEFINITIONS`; if omitted, `ll-generate-schemas` does not produce the corresponding schema file and `test_generate_schemas.py::test_all_34_event_types_defined` will fail on the count assertion [Agent 2 finding]
- `scripts/little_loops/transport.py` — `_OTEL_EVENT_TYPES` frozenset (lines 323–334): `"max_iterations_summary"` is not forwarded as an OTel span event; add to the frozenset if observability coverage is desired (verify-only for this issue — may be a separate concern) [Agent 2 finding]

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Implementation challenge — cap-check re-triggering**: The `on_retry_exhausted` pattern (mutate `self.current_state`, then `continue`) cannot be used verbatim here. At `executor.py:279`, `self.iteration` is already at or past `max_iterations`; a bare `continue` would re-trigger the cap immediately on the next loop iteration (before `_execute_state()` runs). Three approaches:

- **(a) Boolean flag (recommended)**: Add `self._summary_state_executed: bool = False` in `__init__`. Change the cap guard to: `if self.iteration >= self.fsm.max_iterations and not self._summary_state_executed`. On first cap-hit with `on_max_iterations` set, emit the event, set `self._summary_state_executed = True`, mutate `self.current_state`, and `continue` — the flag prevents re-triggering on the next pass. Follows the same "executor instance flag" pattern as `_just_routed`.
- **(b) Inline `_execute_state()` call**: Call the summary state action directly without re-entering the `while` loop. Bypasses the iteration counter but avoids the re-trigger problem. Less clean because it duplicates the normal execution path.
- **(c) Temporary cap bump**: Set `self.fsm.max_iterations += 1` before the `continue`. Simplest but mutates the shared FSM config.

Option (a) is cleanest; it's consistent with how `_just_routed` and `_retry_counts` track per-run executor state without modifying the `FSMLoop` config.

**Termination event**: The audit skill (`skills/audit-loop-run/SKILL.md`) reads `loop_complete.terminated_by` from `events.jsonl`. Adding a `max_iterations_summary` event emitted *before* calling `_finish("max_iterations")` is sufficient for audit tooling to distinguish "terminated with summary" from "terminated cold" — the skill already key-matches on `terminated_by`. The `_finish("max_iterations")` call should still fire after the summary state completes, preserving `terminated_by="max_iterations"` in `loop_complete` and `status="interrupted"` in `state.json`.

**CLI exit code**: `scripts/little_loops/cli/loop/_helpers.py` maps `"max_iterations"` → exit code 1. No change needed; the overall termination is still `"max_iterations"`.

**`terminated_by` contract — implementation note for Option (a)**: Codebase analysis confirms the modified cap guard works correctly on the second pass (flag prevents re-triggering). However, once `current_state = "summarize_partial"` and the flag is set, the summary state runs normally and routes to its `next: done`. Since `done` is a terminal state, the **terminal-state check fires `_finish("terminal")`** — not `_finish("max_iterations")`. This makes `ExecutionResult.terminated_by = "terminal"`, and `PersistentExecutor` (`persistence.py:571`) maps `"terminal"` → `status = "completed"` (not `"interrupted"`). To preserve the stated `terminated_by = "max_iterations"` intent, add an intercept to the terminal-state check in `FSMExecutor.run()`:

```python
if state_config.terminal:
    if self._summary_state_executed:
        return self._finish("max_iterations")  # preserve cap-termination signal
    return self._finish("terminal")
```

Without this intercept, the `audit-loop-run` verdict condition in Step 12 must key on `max_iterations_summary` event presence alone (not `AND terminated_by == "max_iterations"`), since summary-completed runs would show `terminated_by: "terminal"`. `ExecutionResult` dataclass: `scripts/little_loops/fsm/types.py:16–37` (this file needs no modification).

**`ll-loop simulate` behavior (Step 15 resolved — no changes needed)**: `cmd_simulate` (`testing.py:175`) calls the real `FSMExecutor.run()` with only the action runner substituted (`SimulationActionRunner`). After ENH-1631 is implemented, simulate automatically inherits the `on_max_iterations` behavior: the summary state fires, its prompt is simulated (printed, not LLM-executed), and routing to `done` terminates normally. The default 20-iteration cap in simulate (`testing.py:206–211`) means the hook fires at iteration 20 for `max_iterations: 100` loops — intended behavior, not a defect. No code changes needed to `testing.py`.

**Exact line references confirmed by analysis**:
- `_finish()`: `executor.py:1530–1548` — emits `loop_complete`, returns `ExecutionResult`; no `terminated_by` instance variable on the executor itself
- `on_retry_exhausted` handler: `executor.py:342–365` — confirmed model: emit event → mutate `self.current_state` → `continue`
- `_just_routed` init: `executor.py:198–201`; `_retry_counts` init: `executor.py:193–196` — confirmed pattern for `self._summary_state_executed: bool = False` in `__init__`
- `ExecutionResult.terminated_by` valid values: `"terminal"`, `"max_iterations"`, `"timeout"`, `"signal"`, `"error"`, `"handoff"`, `"cycle_detected"`, `"stall_detected"`

## Acceptance Criteria

- [ ] `on_max_iterations` accepted by the loop YAML schema and validated by `LoopConfig.from_dict`.
- [ ] Runtime executes the target state exactly once when the iteration cap fires, then terminates.
- [ ] `general-task.yaml` defines `summarize_partial` and writes a summary file on partial runs.
- [ ] Audit tooling (`/ll:audit-loop-run`) can distinguish "terminated with summary" from "terminated cold."
- [ ] Regression test covers the cap-firing + summary-state path.

## Implementation Steps

1. **Schema field** — Add `on_max_iterations: str | None = None` to `FSMLoop` dataclass (`schema.py:875`, after `max_iterations`); update `from_dict()` (`schema.py:987`), `to_dict()` (`schema.py:922`, pattern: `if self.on_max_iterations is not None: result["on_max_iterations"] = self.on_max_iterations`), and `get_all_referenced_states()` (`schema.py:1031`) to include the target state in the ref set.
2. **Validation** — Add `"on_max_iterations"` to `KNOWN_TOP_LEVEL_KEYS` (`validation.py:100`); add unknown-state reference check in `validate_fsm()` (parallel to `circuit.repeated_failure` check) so an invalid state name is caught at load time.
3. **Executor branch** — In `FSMExecutor.__init__`, add `self._summary_state_executed: bool = False`. Change the cap guard (`executor.py:279`) to: when `self.iteration >= self.fsm.max_iterations` and `self.fsm.on_max_iterations` is set and `not self._summary_state_executed`, emit `max_iterations_summary` event (`{"summary_state": on_max_iterations, "iterations": self.iteration}`), set `self._summary_state_executed = True`, set `self.current_state = self.fsm.on_max_iterations`, then `continue`. Otherwise fall through to `_finish("max_iterations")` as before.
4. **General-task loop** — Add `on_max_iterations: summarize_partial` at the top level of `general-task.yaml` (after `on_handoff: spawn`); add `summarize_partial` state with the prompt action and `next: done` as shown in the Proposed Solution.
5. **Tests** — In `test_fsm_executor.py`, add a test class (model on `TestPerStateRetryLimits`) that: (a) verifies the summary state executes exactly once when the cap fires with `on_max_iterations` set, (b) verifies `max_iterations_summary` event is emitted with correct payload, (c) verifies `loop_complete.terminated_by == "max_iterations"` still fires after. Also add a roundtrip test in `test_fsm_schema.py` following `TestFSMLoop.test_roundtrip_serialization`.
6. **Docs** — Update `docs/guides/LOOPS_GUIDE.md` top-level field table; update `docs/reference/API.md` `LoopConfig` section; add `max_iterations_summary` event to `docs/reference/EVENT-SCHEMA.md`.
7. **Verify** — Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py -v`; run `ll-loop validate general-task` to confirm schema accepts `on_max_iterations`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/generate_schemas.py` — add `max_iterations_summary` event schema entry to `SCHEMA_DEFINITIONS` (fields: `summary_state: str`, `iterations: int`) so `ll-generate-schemas` produces the schema file and the test count assertion stays correct
9. Fix `scripts/tests/test_general_task_loop.py::TestGeneralTaskLoopFile.test_expected_states_present` — add `"summarize_partial"` to the hard-coded expected states set; add `TestENH1631SummarizePartial` class verifying `on_max_iterations` top-level key and `summarize_partial` state structure
10. Add `scripts/tests/test_fsm_validation.py::TestOnMaxIterationsValidation` — three tests: (1) no "Unknown top-level" warning for `on_max_iterations`; (2) unknown state ref rejected; (3) valid state ref passes — model on `TestCircuitValidation` and `TestRateLimitFieldValidation`
11. Update `scripts/tests/test_generate_schemas.py` — update count assertions 34→35 in all four hardcoded methods: `test_all_34_event_types_defined` (also add `"max_iterations_summary"` to `expected` set), `test_creates_34_files`, `test_creates_output_dir_if_missing`, `test_cli_creates_files`
12. Update `skills/audit-loop-run/SKILL.md` Step 6 verdict table — add row: `terminated_by == "max_iterations"` AND `max_iterations_summary` event present in JSONL → verdict `partial`; satisfies Acceptance Criterion 4
13. Update `skills/debug-loop-run/SKILL.md` Step 2 event-payload table — add `max_iterations_summary` row with fields `summary_state`, `iterations`
14. Update `skills/create-loop/loop-types.md` — document `on_max_iterations: summarize_partial` in the `general-task` section after "Partial DoD Satisfaction Threshold"
15. ~~Verify `scripts/little_loops/cli/loop/testing.py`~~ — **Resolved: no changes needed.** `cmd_simulate` calls real `FSMExecutor.run()` with only `action_runner` substituted; `on_max_iterations` behavior is inherited automatically. Summary state action is simulated (not LLM-executed). 20-iteration default cap (`testing.py:206–211`) means hook fires at iteration 20 for `max_iterations: 100` loops — intended behavior. See Codebase Research Findings for detail.
16. **Final verify** — Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py scripts/tests/test_general_task_loop.py scripts/tests/test_generate_schemas.py -v`
17. Update `scripts/little_loops/session_store.py` — add `"max_iterations_summary"` to `_LOOP_EVENT_TYPES` frozenset so the event is recorded in the SQLite `loop_events` table and visible via `ll-session search --fts` and `ll-history`
18. Update `scripts/little_loops/cli/loop/_helpers.py` `display_progress()` — add a handler branch for `"max_iterations_summary"` event (print summary-state name and iteration count so operators see the hook fire during a live run)
19. Update `scripts/little_loops/cli/loop/info.py` `cmd_show()` — add `on_max_iterations` to the config summary display block (after the `max_iterations` line) when the field is non-None

## Scope Boundaries

Out of scope:

- Continuing iteration past the cap (the summary state runs exactly once; no loop resumption or budget extension).
- Chaining multiple summary states or arbitrary post-budget FSM flows.
- Automatic re-invocation of the loop with the partial summary as new context.
- Backporting `on_max_iterations` semantics to per-state `on_retry_exhausted` (they remain independent mechanisms).
- Changes to the JSONL transcript format beyond the new termination event.

## Impact

- **Priority**: P3 — operator ergonomics for the most generic loop; not blocking but high leverage once `general-task` is used regularly.
- **Effort**: Small — schema field + one branch in `FSMExecutor.run()` + one YAML state + regression test. Reuses the existing `on_retry_exhausted` pattern as a model.
- **Risk**: Low — additive field with `None` default preserves current behavior for all existing loops; post-budget execution is capped at 1 iteration to prevent runaway.
- **Breaking Change**: No.

## Related

- [[BUG-1628]] — partial fix overlaps: with replan + oscillation guard in place, `max_iterations` will fire less often, but the summary hook is still useful for genuinely large tasks.
- [[ENH-1658]] (refiled from ENH-1629) — pairs naturally with the deterministic shell gate; the summary can report the captured `{unchecked_dod, unchecked_plan, failed_samples}` JSON directly rather than re-parsing artifacts.

## Source

`general-task-audit-proposals.md` (Proposal 3) — derived from a partial run audit on 2026-05-23. Proposals file is transient; this issue is the durable record.

## Labels

`enhancement`, `fsm-runtime`, `general-task`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-24_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- **Wide file surface (~20 change sites)**: Per-site depth is mechanical to local, but the PR spans 4 implementation files, 5 wiring files, 5 test files, 3 skills, 3 docs, and 1 config. Execute wiring-phase steps 8–19 as a structured checklist — the breadth is manageable but requires discipline.
- **Skill and doc changes have no automated validation**: The verdict-table row in `skills/audit-loop-run/SKILL.md`, the event-payload row in `skills/debug-loop-run/SKILL.md`, and the three doc edits are prose changes with no automated test coverage. Plan a manual smoke-check against a real partial run to confirm the audit skill verdict logic is correct.

## Session Log
- `/ll:ready-issue` - 2026-05-24T21:54:05 - `6610c4b9-00d0-4e04-aeda-b66222aa4c9b.jsonl`
- `/ll:wire-issue` - 2026-05-24T21:37:49 - `ba5b7ded-8a4a-4c0f-95e1-c82128f42267.jsonl`
- `/ll:refine-issue` - 2026-05-24T21:24:29 - `a2d89ce4-36c3-4dc3-a3b0-5dfc218f3013.jsonl`
- `/ll:confidence-check` - 2026-05-24T22:00:00Z - `3a45116c-f236-4734-b55a-0639c7ec21af.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `0bd96a50-4995-4205-8ae4-3dc620bd44ac.jsonl`
- `/ll:wire-issue` - 2026-05-24T21:14:24 - `dbcaf171-9096-4859-8fb1-49a4841f3b48.jsonl`
- `/ll:refine-issue` - 2026-05-24T21:07:02 - `791044ce-19d8-46a1-8d91-36e6cb0a39c9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `53f5ce8a-8802-4e4f-a82f-cb8f836c6b67.jsonl`
- `/ll:format-issue` - 2026-05-23T16:43:14 - `3b5c3569-1967-4199-ba4f-ccf461e65ff0.jsonl`
- `/ll:capture-issue` - 2026-05-23T16:40:11Z - `001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue modifies general-task.yaml FSM structure (adding `on_max_iterations: summarize_partial` + `summarize_partial` state) and schema.py (adding the top-level `on_max_iterations` field). BUG-1628 makes overlapping structural changes to the same files (replan state, execute/continue_work differentiation). This issue `depends_on: BUG-1628` — let the P2 bug fix land and settle the general-task.yaml structure before adding the on_max_iterations hook to avoid merge conflicts.

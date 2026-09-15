---
id: ENH-3471
title: 'Named abort reason distinguishes attempt-batch vs decision-step failures instead of collapsing both to "error"'
type: ENH
priority: P2
status: open
discovered_date: '2026-09-13'
labels: []
parent: ENH-3468
---

## Summary

An exception raised during an FSM run's action execution (attempt batch) or its `evaluate:`/routing step (decision step) still terminates through `FSMExecutor._finish()`, but today both collapse to the single generic `terminated_by="error"` value (`fsm/executor.py:~1027-1041`), with the attempt-batch/decision-step distinction existing only as "which function's frame raised" — no stored attribute. This issue gives that distinction a named, stored abort reason on the run, so downstream consumers (waste attribution, fleet-review, sub-loop routing) can tell the two failure classes apart instead of treating every exception identically.

## Current Behavior

An exception raised during an FSM run's action execution (attempt batch) or its `evaluate:`/routing step (decision step) both fall through the same `except Exception as exc: return self._finish("error", error=str(exc))` funnel (`fsm/executor.py:1040-1041`). Both cases land on the identical `terminated_by="error"` value — the attempt-batch/decision-step distinction exists only implicitly, as "which function's frame raised," with no stored attribute a downstream consumer can read.

## Expected Behavior

`FSMExecutor._finish()` threads a named, stored abort reason through the funnel so an attempt-batch failure and a decision-step failure produce distinct `terminated_by` values on the run's `ExecutionResult`. Downstream consumers (waste attribution in `history_reader/usage.py`, fleet-review, sub-loop routing in `refine-to-ready-issue.yaml`) read that value to tell the two failure classes apart instead of treating every exception identically.

## Motivation

Collapsing both failure classes to `"error"` erases information the executor already has (which stage raised) at the exact point it would be cheapest to capture it. Waste-attribution and sub-loop routing consumers currently can't distinguish "the action crashed" from "the router couldn't resolve a route" without re-deriving it from logs, which blocks more precise failure-class reporting in fleet-review and `confidence_check` routing (`refine-to-ready-issue.yaml:1043-1046`).

## Scope Boundaries

- **In scope**: naming and threading the new abort reason value(s) through `FSMExecutor._finish()`; re-sorting the 18 existing `test_fsm_executor.py` assertions per raise-site class; updating the waste-attribution predicate, the `refine-to-ready-issue.yaml` sub-loop routing arm, the `loop_complete` event schema/docs, and the `debug-loop-run`/`create-loop` skill references that key off literal `terminated_by == "error"` (all enumerated in Implementation Steps).
- **Out of scope**: the checkpoint-artifact wiring for salvaging best-effort work, which belongs to the sibling child issue in the ENH-3468 decomposition that introduces that artifact; any other existing `terminated_by` vocabulary value (`timeout`, `interrupted`, `handoff`, etc.) is untouched.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 1** and its directly-dependent wiring (vocabulary consumers only — the checkpoint-artifact wiring belongs to the sibling child that introduces that artifact).

## Design

Today's asymmetry, per parent's codebase research: `_run_action_or_route()` (`fsm/executor.py:3773-3801`) wraps action execution and either routes to `state.on_error` or re-raises; `_evaluate()`/`_route()`/`_resolve_route()` (`fsm/executor.py:3076-3169`, `:3233`, `:3307`) have no exception wrapping of their own. Both land in the same `except Exception as exc: return self._finish("error", error=str(exc))` (`fsm/executor.py:1040-1041`). This issue threads a named reason through that funnel instead of collapsing both to `"error"`.

**Open design choice (not settled by precedent)**: this codebase has two competing conventions for a typed "unit didn't produce its normal result" reason — `ConsultOutcome.skipped_reason: Literal[...] | None` (`advisor.py:316`) vs. `ExecutionResult.terminated_by: str` (free-form). Pick one explicitly for the new value(s) and note the choice in the PR; do not assume `Literal` is canonical just because it looks more typed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- The codebase's established mechanism for distinguishing "which stage raised" at a shared exception funnel is a dedicated exception subclass caught by an earlier, more specific `except` clause ahead of the generic `except Exception` — e.g. `HeredocCollisionError(InterpolationError)` is checked before `InterpolationError`, which is checked before `Exception`, at the very funnel this issue targets (`fsm/executor.py:1027-1041`). No frame-inspection or stored-attribute mechanism exists in this codebase for this purpose.
- Neither `_run_action_or_route()` (attempt-batch, `fsm/executor.py:3773-3801`) nor `_evaluate()`/`_route()`/`_resolve_route()` (decision-step, `fsm/executor.py:3076-3169`, `:3233`, `:3307`) wrap exceptions of their own beyond `_run_action_or_route()`'s local `on_error` reroute — an exception from either path reaches the same three `except` clauses in `run()` today.
- On the open Literal-vs-str design choice: even where this codebase does use a `Literal[...]`-typed "why didn't this succeed" field (`ConsultOutcome.skipped_reason`, `advisor.py:306-337`), the value flattens back to plain `str` at its own persistence boundary — `AdvisorConsultRow.outcome` (`history_reader/events.py:212`) is untyped `str`, matching `ExecutionResult.terminated_by`'s existing convention. A third convention also exists: `FailureType(Enum)` (`issue_lifecycle.py:141-176`), consumed via `.value` and exposed to loop YAML as `${captured.<state>.failure_type}` (`fsm/executor.py:2691-2699`) — a separate, already-shipped classifier for "why did this action fail" (BUG-2826), orthogonal to `terminated_by`. All three conventions collapse to a bare string at the interpolation/YAML/persistence boundary; that boundary has no typed-vocabulary convention, only string equality/membership checks.

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- Additional precedent for "which stage raised" distinction beyond the already-cited exception-subclass chain: `advisor.py::consult_for_trigger()` (~540-590) maps four distinct exception types to four distinct `Literal[...]`-typed reason values, one per `except` clause (not a subclass hierarchy) — `AdvisorNotConfigured` → `"not_configured"`, `CapabilityFloorViolation` → `"floor_violation"`, `HostNotConfigured` → `"failed"`, `BlockingJsonError` → inspects `exc.details.get("timeout")` to choose between `"timeout"`/`"failed"` within a single except clause. This is a closer analog to threading a named reason through a shared funnel than the `HeredocCollisionError`/`InterpolationError` chain alone, which today customizes only the `error=` message, not `terminated_by`.
- Confirmed: `StrEnum` has zero usage anywhere in `scripts/little_loops` (only a comment in `issue_lifecycle.py:124-125` mentions the term). `abort_reason` as a field/attribute name is absent from source entirely — it only appears as prose in sibling issue files (`.issues/enhancements/P2-ENH-3473-*.md`, `P2-ENH-3468-*.md`), not as a shipped identifier.
- Repo-wide search for a fourth exception-classification mechanism (beyond subclass-chain, per-except-clause literal assignment, and string/content classification) found none — no `isinstance(exc, ...)`/`isinstance(e, ...)` dispatch pattern exists in any `except` block.

## Program Design

### Types
- `ExecutionResult.terminated_by: str` (`scripts/little_loops/fsm/types.py:59`) — free-form field; docstring (`:35-49`) enumerates the current fixed vocabulary (`"terminal", "max_steps", "max_iterations_reached", "timeout", "interrupted", "user_stopped", "system_signal", "error", "handoff", "cycle_detected", "stall_detected", "host_pressure_abort", "host_budget_exceeded", "workdir_vanished"`). The new attempt-batch/decision-step values are additions to this same field, not a new field.

### Signatures
- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` (`fsm/executor.py:4264`) — the single funnel to thread the new named reason through.

### Call Path
`FSMExecutor.run()` (attempt-batch exception via `_run_action_or_route()` re-raise, or decision-step exception via `_evaluate()`/`_route()`/`_resolve_route()`) → outer `except Exception as exc: return self._finish("error", ...)` (`:1027-1041`) → `_finish()` → `record_loop_run_summary()` (writes `loop_runs` row).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- Citation correction: the `ExecutionResult.terminated_by` docstring's vocabulary enumeration (`fsm/types.py`) actually spans lines 35-43, not 35-49 — lines 44-49 are the docstring entries for `duration_ms` and the start of `captured`/`failure_terminal`, not further `terminated_by` values.
- Pre-existing inconsistency adjacent to this field: the inline vocabulary comment at `fsm/types.py:59` (10 values) already omits several values present in both the class docstring and actual `executor.py` string literals — `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `workdir_vanished` (all in the docstring, :35-43) and `cost_ceiling_exceeded` (used at `executor.py:958`, not in the docstring either). This is a pre-existing three-way drift between the inline comment, the docstring prose, and the actual literals already in use — worth keeping in mind since this issue adds yet more values to the same field.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Documentation

- `docs/reference/API.md` (~lines 8818-8822) — `waste_attribution()` prose enumerates the `terminated_by` infra/step-cap vocabulary including `error`; update alongside the Step 3 `_WASTED_RUN_PREDICATE` code change so the doc doesn't go stale [Agent 2 finding]
- `docs/reference/API.md` (~line 6367) — `ExecutionResult` usage example prints `result.terminated_by` and lists `"error"` among the sample values [Agent 2 finding]
- `docs/reference/API.md` (~line 6377) — `ExecutionResult` dataclass field comment enumerates the same vocabulary [Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~lines 365-366, ~613) — two `# ll-lint: mr11-ok(...)` suppression comments narrate `terminated_by` as "terminal/error/timeout/max_steps/..."; update the prose so it doesn't misdescribe the funnel once decision-step exceptions get their own value [Agent 2 finding]
- `scripts/little_loops/loops/autodev.yaml` (~line 699) — comment describing "a child that dies with terminated_by == 'error' after a 429" as the generic exception-funnel outcome; update to reflect the new named value(s) [Agent 2 finding]

### Skill Mirror Sync

- `.qwen/skills/create-loop/reference.md`, `.kimi-code/skills/create-loop/reference.md`, `.gemini/skills/create-loop/reference.md` (each ~lines 784-785) — verbatim mirrors of `skills/create-loop/reference.md`'s sub-loop routing prose (Implementation Step 8's target). Editing only the canonical file desyncs these three and trips the mirror-drift gate (`test_verify_host_map.py`); resync with `ll-adapt --host <gemini|kimi-code|qwen> --apply` after the canonical edit [Agent 1 finding]

### Tests

- `scripts/tests/test_builtin_loops.py` — no existing test exercises `refine-to-ready-issue.yaml:1043-1046`'s `*:error|*:timeout|*:max_steps` alternation (the actual arm Implementation Step 4 modifies); the only related test, `test_write_failure_evidence_attributes_sub_loop_failure` (:2200-2220), exercises the sibling `True:*` alternation instead. Add a case setting `failure_terminal` to something other than `"True"` alongside the new named `terminated_by` value to cover the arm this issue's Step 4 actually changes [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::test_exception_during_execution_emits_error_in_loop_complete_event` (:3579-3630) — a 19th `terminated_by == "error"` assertion not in Implementation Step 2's enumerated 18; asserts on the emitted `loop_complete` **event dict** (`complete_event["terminated_by"]`) rather than `result.terminated_by`, but is the same `FailingRunner` raise-site as the already-listed `test_exception_during_execution_returns_error_result` — needs the same attempt-batch re-sort [wire-issue pass 2 finding]
- `scripts/tests/test_debug_loop_run_synthesis.py::test_eval_error_termination_inline_no_eval_no_new_signal` (:591-604) — inline-encodes the same `terminated_by == "error"` → FATAL_ERROR-path precedence rule that Implementation Step 7's `skills/debug-loop-run/SKILL.md` edit documents (SKILL.md:181, :204); update alongside that step or the fixture's docstring/assertion will misdescribe the funnel once decision-step exceptions get their own value [wire-issue pass 2 finding]
- `scripts/tests/test_fsm_persistence.py::test_archive_run_only_maps_terminated_by_to_status` (:1071-1102) — parametrized `terminated_by → status` case list has no `"error"` case today (falls through `map_final_status()`'s generic `"failed"` default); add a case pinning the new named value(s) to their mapped status [wire-issue pass 2 finding]
- `scripts/tests/test_generate_schemas.py` — no existing test reads `SCHEMA_DEFINITIONS["loop_complete"]["properties"]["terminated_by"]`'s description text, so Implementation Step 5's prose edit has no regression coverage either direction; optional, not blocking [wire-issue pass 2 finding]

### Confirmed Not Affected (no action needed)

- `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` — checks `if "error" in event: return "error"` *before* inspecting `terminated_by`; since `_finish()` still sets `error=str(exc)` for the new named values, this bucket (and its `test_ll_logs.py` assertions, and `docs/runbooks/FLEET_LOOP_REVIEW.md`'s vocabulary listing) fires unchanged. No edit required [Agent 2 finding, confirmed]
- No `Literal`/JSON-Schema `enum` anywhere constrains `terminated_by`'s values (`loop_complete.json` is untyped `"type": "string"`, `session_store/schema.py`'s column is plain `TEXT`) — purely additive vocabulary change, no validator to update [Agent 2 finding]
- `scripts/little_loops/transport.py:1749-1753` (OTel span attribute), `scripts/little_loops/cli/loop/{feed.py:1044-1045,testing.py:278,audit.py:60,79,201,227,238,256,307}`, `scripts/little_loops/cli/loop/signals.py:60` (`archive_run_only(terminated_by="interrupted_force")`), `scripts/little_loops/history_reader/runs.py:331,391,396,401` (`group_by: Literal["loop_name", "terminated_by"]` rollup — a new bucket appears automatically, which is correct), `scripts/little_loops/mcp_server/tasks.py:148,170-176`, `scripts/little_loops/cli/loop/evidence.py:47-58,396,573` (`_LOOP_RUN_ALLOWLIST`) — all generic string pass-through/display/persistence of whatever `terminated_by` value is set; none pattern-match on the literal `"error"`, so all continue to work unchanged with the new named values [wire-issue pass 2 findings]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/API.md` — waste_attribution prose (~8818-8822), ExecutionResult usage example (~6367), and field comment (~6377) to enumerate the new abort-reason value(s)
- Update `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~365-366, ~613) and `scripts/little_loops/loops/autodev.yaml` (~699) — stale comment prose describing the old "error"-only funnel
- After editing `skills/create-loop/reference.md` (Step 8), run `ll-adapt --host qwen --apply`, `ll-adapt --host kimi-code --apply`, `ll-adapt --host gemini --apply` to resync the three mirror copies
- Add a `test_builtin_loops.py` case exercising `refine-to-ready-issue.yaml:1043-1046`'s `*:error|*:timeout|*:max_steps` alternation directly (not just the sibling `True:*` arm already covered)
- **`scripts/little_loops/fsm/executor.py::FSMExecutor._execute_sub_loop()` (:1304, :1320, :1338)** — two literal `in ("error", "workdir_vanished")` membership checks (verdict derivation at :1304 and routing at :1320) are the engine's *generic* sub-loop dispatch, used by every `type: loop` call state in every loop YAML — a strictly larger surface than the already-known `refine-to-ready-issue.yaml:1043-1046` case arm. Widen both tuples to include the new named value(s), or a child that fails via the new funnel routes to `on_no`/`"no"` verdict instead of `on_error`/`"error"` verdict for every parent loop, not just `refine-to-ready-issue.yaml` [wire-issue pass 2 finding]
- `scripts/little_loops/fsm/types.py:59` inline vocabulary comment and class docstring (:35-43) — add the new value(s) to the enumerated list (already noted as having pre-existing drift from actual literals; this issue adds to the same field) [wire-issue pass 2 finding]
- `docs/reference/CLI.md` (~line 574, `ll-ctx-stats` section) — a third, independent prose copy of the waste-attribution vocabulary ("'Wasted' is terminal-status only: any infra/step-cap exit (`error`/`max_steps`/...)"), alongside the two already-known `API.md` citations; update alongside Step 3 [wire-issue pass 2 finding]
- `scripts/tests/test_builtin_loops.py::test_resolve_decision_call_states_declare_on_error_matching_on_failure` (~8807-8814) — docstring repeats the same "child dies with `terminated_by == 'error'` after a 429" framing as the `autodev.yaml:699` comment; update the prose (assertions themselves are value-agnostic) [wire-issue pass 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- `docs/reference/API.md` citations re-verified against current content (2026-09-15): all three cited passages still match verbatim, only line numbers drifted by 2-3 lines each (unrelated edits elsewhere in the file) — usage example now at :6369 (was :6367), field comment now at :6379 (was :6377), waste_attribution prose now at :8820-8823 (was :8818-8822). No other Integration Map citation (loop YAMLs, three skill mirrors, canonical `skills/create-loop/reference.md`, `test_builtin_loops.py`) has drifted — all confirmed exact.

## Implementation Steps

1. Thread a named abort reason through `FSMExecutor._finish()` distinguishing an attempt-batch failure from a decision-step failure, replacing (or supplementing — see Open design choice above) the generic `"error"` value for these two paths. Verified by a new test in `test_fsm_executor.py` asserting the new value(s) surface in `result.terminated_by`.
2. Re-sort the following existing `test_fsm_executor.py` assertions of the form `result.terminated_by == "error"` per their actual raise-site class (grep-confirmed, 18 total):
   - **Decision-step / route-resolution class** (assert the new decision-step value): `test_no_valid_route_terminates_with_error` (:2027/2047), `test_on_partial_missing_falls_through_to_error` (:2140), `test_on_blocked_missing_falls_through_to_error` (:2207), `test_extra_routes_missing_falls_through_to_error` (:2270), `test_undeclared_cannot_judge_shorthand_no_on_error_terminates_loud` (:2405), `test_no_valid_transition_returns_error` (:5573), `test_before_route_veto_terminates_with_error` (:7545).
   - **Attempt-batch / action-execution class** (assert the new attempt-batch value): `test_exception_during_execution_returns_error_result` (:3532/3576), `test_exception_in_branch_c_without_on_error_reraises` (:4847), `test_heredoc_collision_halts_run_even_with_on_error_set` (:4963), `test_missing_context_variable_produces_friendly_message` (:6383), `test_missing_capture_returns_error` (:1719), `test_missing_required_fragment_param_terminates_with_error` (:11108).
   - **Ambiguous / infra-driven** (explicit `_finish("error", ...)` from another subsystem, not a raised exception — leave as `"error"` unless a case-by-case classification is clearly correct): `test_fatal_error_signal_terminates_with_error` (:5419), `test_fatal_error_signal_does_not_continue_to_next_state` (:5459), `test_sub_loop_missing_loop_without_on_error` (:7163), `test_stop_event_emitted_beyond_hard_max` (:10201).
   - The 4 `result.terminated_by != "error"` inequality assertions (:11903, :11938, :11982, :12153) need no change.
3. Update `scripts/little_loops/history_reader/usage.py::_WASTED_RUN_PREDICATE` (:310-316) — add the new attempt-batch/decision-step value(s) to the `IN (...)` membership list so those runs are still counted as "wasted."
4. Update `scripts/little_loops/loops/refine-to-ready-issue.yaml:1043-1046` — the `case "${captured.confidence_check.failure_terminal?}:${captured.confidence_check.terminated_by?}" in ... *:error|...)` arm is an exact-string glob match, not a prefix wildcard; extend it to also match the new named value(s) so `confidence_check` failures stay attributed to `FAILING_STATE=confidence_check`.
5. Update `scripts/little_loops/generate_schemas.py` (:615-634) `EVENT_SCHEMAS["loop_complete"]`'s `terminated_by`/`error` field-description prose to reflect the split, then regenerate `docs/reference/schemas/loop_complete.json` via `ll-generate-schemas`.
6. Update `docs/reference/EVENT-SCHEMA.md` `### loop_complete` section (`terminated_by`/`error` rows, and the `action_error` claim that terminates with `terminated_by="error"`) and `docs/guides/LOOPS_GUIDE.md` `### terminated_by exit reasons` table (~line 916, split the `error` row) plus the `## Troubleshooting` entry (~line 1326) referencing collapsed `terminated_by="error"` behavior.
7. Update `docs/reference/COMMANDS.md` `/ll:debug-loop-run` "Signal detection rules" (~lines 857-858) and `skills/debug-loop-run/reference.md` (field table :26; `### BUG — FATAL_ERROR termination` :64-68; `### BUG — Evaluate error terminated the loop` :70-76) and `skills/debug-loop-run/SKILL.md` (:181, :196, :204) — all key off literal `terminated_by == "error"` and are not covered by the MR-8 evidence-contract lint (FSM-YAML-only), so they need hand-updating.
8. Update `skills/create-loop/reference.md` (~lines 783-785) sub-loop `Routing` section's closed `on_success`/`on_failure`/`on_error` classification to name the new value(s) so wizard-generated loops know what to expect.
9. Widen the two `in ("error", "workdir_vanished")` membership checks in `FSMExecutor._execute_sub_loop()` (`fsm/executor.py:1304`, `:1320`) to include the new named value(s) — this is the engine's generic `type: loop` sub-loop dispatch (verdict derivation and `on_error` routing), a broader surface than the `refine-to-ready-issue.yaml` case arm Step 4 already covers (added by `/ll:wire-issue` pass 2).
10. `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_persistence.py scripts/tests/test_debug_loop_run_synthesis.py -v` passes.

## Impact

- **Priority**: P2 - inherited from parent decomposition (ENH-3468); improves failure-class observability but blocks nothing critical on its own.
- **Effort**: Medium - one funnel change in `_finish()`, but ripples through 18 test assertions, a waste-attribution predicate, a sub-loop routing arm, generated schemas, and five documentation files (Implementation Steps 1-8).
- **Risk**: Low - `ExecutionResult.terminated_by` stays a free-form `str` field; this only adds new values to its existing vocabulary rather than changing the field's type or the executor's control flow.
- **Breaking Change**: No - existing `terminated_by` values are unchanged; all known consumers that match on the literal `"error"` string are updated as part of this issue's own Implementation Steps.

## Tests

- `scripts/tests/test_fsm_executor.py` — existing exception-to-`terminated_by` conversion tests (e.g. `test_no_valid_route_terminates_with_error`) construct `FSMLoop`/`StateConfig` directly and assert on `result.terminated_by`/`result.error`/`result.final_state`; new tests follow this same construction-and-assert shape.
- `scripts/tests/test_history_reader_usage.py::TestWasteAttribution` — extend with a fixture for the new attempt-batch/decision-step values against `_WASTED_RUN_PREDICATE`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Two established testing conventions exist for exception-to-reason mapping and neither supersedes the other: (a) one dedicated test method per raise-site scenario with full `FSMLoop`/`StateConfig` construction (the shape `test_fsm_executor.py`'s existing `terminated_by=="error"` assertions already use, e.g. `test_no_valid_route_terminates_with_error` at :2027, `test_exception_during_execution_returns_error_result` at :3532); (b) a single `@pytest.mark.parametrize("exc,expected_reason", [...])` method mapping exception instances to expected reason strings (`test_advisor.py::test_maps_each_exception_to_skipped_reason`, :475-503; `test_issue_lifecycle.py`'s `classify_failure()` parametrization, :963-1050). The new tests for this issue's abort-reason split should follow convention (a), matching the file's own existing `terminated_by` assertion shape.

## Session Log
- `/ll:wire-issue` - 2026-09-15T22:31:53 - `74d0e714-5fa8-4d36-8d26-f70b1e11f439.jsonl`
- `/ll:refine-issue` - 2026-09-15T22:16:07 - `a0a3cae8-46b6-4741-b032-8859dea7a727.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:29:41 - `8cf1df9b-8fca-46d9-b751-f28d170c6572.jsonl`
- `/ll:refine-issue` - 2026-09-14T19:32:05 - `93b68600-9c57-4c65-a431-1e887e42f117.jsonl`
- `/ll:format-issue` - 2026-09-14T19:18:19 - `e03a4d3e-6e32-492e-b751-6c3a912f41aa.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:24 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`

## Status

**Open** | Created: 2026-09-13 | Priority: P2

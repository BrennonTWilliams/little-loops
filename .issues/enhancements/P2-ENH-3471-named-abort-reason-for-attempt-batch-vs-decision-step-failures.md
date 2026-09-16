---
id: ENH-3471
title: Named abort reason distinguishes attempt-batch vs decision-step failures instead
  of collapsing both to "error"
type: ENH
priority: P2
status: done
discovered_date: '2026-09-13'
completed_at: '2026-09-16T00:39:46Z'
labels: []
parent: ENH-3468
confidence_score: 100
outcome_confidence: 81
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

## Summary

An FSM run that dies because its **action crashed** (attempt-batch failure) and one that dies because the **executor could not decide where to go next** (decision-step failure: no valid transition, `before_route` veto, evaluator crash) both terminate with the identical `terminated_by="error"`. The distinction exists only as "which line called `_finish()`" — no stored attribute a downstream consumer can read. This issue introduces one new `terminated_by` value, `"no_route"`, for the decision-step class, and leaves `"error"` meaning what it means today (the action crashed). Downstream consumers (waste attribution, fleet-review, sub-loop routing) can then tell the two apart.

## Current Behavior

Two distinct failure classes reach `FSMExecutor._finish("error", ...)` through **different mechanisms**, both producing `terminated_by="error"`:

- **Attempt-batch (action crashed)** — an exception raised inside `_run_action_or_route()` (`fsm/executor.py:3773-3801`) with no `on_error` declared is re-raised and lands in one of the three `except` clauses in `run()` (`fsm/executor.py:1027-1041`: `HeredocCollisionError`, `InterpolationError`, generic `Exception`).
- **Decision-step (could not route)** — these are **not exceptions**. They are direct `_finish("error", ...)` calls:
  - `fsm/executor.py:981` — `_finish("error", error="No valid transition")` when `_execute_state()` returns `None` outside of maintain mode / shutdown / cap-summary handling. This is the path for a missing route, a missing `on_partial`/`on_blocked`/extra route, an undeclared `cannot_judge` shorthand, and a `before_route` veto (`RouteDecision(None)`, documented at `:202`).
  - The evaluator itself (`_evaluate()`, called unwrapped at `fsm/executor.py:2157`) can raise, in which case the exception reaches the generic `except Exception` clause at `:1040` — the one place where the two classes genuinely share a funnel.

A third class is **infra/signal-driven** and also uses `"error"`: the FATAL_ERROR host signal (`fsm/executor.py:897`, `_finish("error", error=self._pending_error)`), a missing sub-loop YAML, and the stop-event-beyond-hard-max path. These stay `"error"`.

## Expected Behavior

- Attempt-batch failures continue to produce `terminated_by="error"` (unchanged — every existing consumer keeps working).
- Decision-step failures produce `terminated_by="no_route"` with the same `error=` message they carry today.
- An exception raised from `_evaluate()`/`_route()` into any of `run()`'s three `except` clauses (`HeredocCollisionError`, `InterpolationError`, generic `Exception`) is classified as `"no_route"`; an exception raised from action execution or from a pre-action dispatch (sub-loop, `human_approval`, `learning`, context build, tamper snapshot, baseline) into those same clauses stays `"error"`.
- Consumers that must treat both classes as "the child died" (sub-loop `on_error` routing, waste attribution) are widened to include `"no_route"`.

## Motivation

Waste-attribution and sub-loop routing consumers currently can't distinguish "the action crashed" from "the router couldn't resolve a route" without re-deriving it from logs, which blocks more precise failure-class reporting in fleet-review and `confidence_check` routing (`refine-to-ready-issue.yaml:1043-1046`). A `no_route` outcome almost always means a loop-authoring bug (missing route declaration), whereas `error` usually means a runtime/environment failure — different owners, different fixes.

## Scope Boundaries

- **In scope**: introducing the single value `"no_route"`; classifying the direct `_finish("error")` call at `:981` and the generic `except Exception` clause; widening the consumers enumerated in Implementation Steps; updating the affected tests and docs.
- **Out of scope**: renaming or re-sorting the attempt-batch class (stays `"error"`); the infra/signal-driven `"error"` sites (`:897`, sub-loop-missing, stop-event) stay `"error"`; every other `terminated_by` value is untouched; checkpoint-artifact wiring (ENH-3473).
- **Deliberately deferred — fleet-review outcome bucketing**: `cli/logs.py::_derive_loop_outcome()` (`:2058-2083`) buckets any `loop_complete` event carrying an `error` key as `"error"` *before* it reads `terminated_by`. Because `_finish()` still passes `error=` for `no_route`, `ll-logs fleet-review` will continue to lump `no_route` runs into its `"error"` bucket after this issue. The Motivation's fleet-review payoff therefore lands only once the follow-up **ENH-3482** (blocked by this issue) splits that bucket; this issue only makes the value *available* (`loop_runs.terminated_by`, `group_by="terminated_by"` rollups, sub-loop routing). Do not change `_derive_loop_outcome()` here — its `"error"` bucket is load-bearing for `docs/runbooks/FLEET_LOOP_REVIEW.md` and `test_ll_logs.py`.

## Parent Issue

Decomposed from ENH-3468: Every loop iteration writes a checkpoint, never zero: salvage paid work and tag the best-effort attempt.

This child covers **Implementation Step 1** and its directly-dependent vocabulary-consumer wiring.

## Design

### Decision: supplement, don't replace

Keep `"error"` for the attempt-batch class and add exactly one new value, `"no_route"`, for the decision-step class. Rationale: the attempt-batch class is the common, already-documented meaning of `"error"` ("the action crashed"), and every consumer matching the literal `"error"` today is matching *that* meaning. Adding one value for the rarer class shrinks every consumer edit to "add one string to a tuple" and leaves the six attempt-batch test assertions untouched. `"no_route"` is chosen over `"action_error"`/`"route_error"` because `action_error` is already an **event** name (`_run_action_or_route()` emits it) and would be confusing as a `terminated_by` value.

`ExecutionResult.terminated_by` stays a free-form `str` (`fsm/types.py:59`); this matches every other vocabulary value and the persistence/interpolation boundary, which is string-equality only. No `Literal`/`Enum` is introduced.

### Mechanism: classify at the call site, plus one phase marker

The earlier draft of this issue assumed both classes flow through the `except` funnel at `:1027-1041` and proposed an exception-subclass chain. That is wrong for the decision-step class, which is a direct `_finish()` call at `:981`, not a raised exception. The correct mechanism:

1. **Call-site literal change** — `fsm/executor.py:981` becomes `self._finish("no_route", error="No valid transition")`. This alone covers every decision-step test in the Tests section (missing route, missing `on_partial`/`on_blocked`/extra route, `cannot_judge` shorthand, `before_route` veto).
2. **Phase marker for the shared `except` clauses** — add an instance attribute `self._phase: str`. It is **reset to `"action"` as the first statement of `_execute_state()`** (`:2011`) and flipped to `"decide"` at exactly four places, all of which are route-target resolution or verdict evaluation:
   - the `next:` branch's route-target interpolations — set `"decide"` immediately before `error_target = interpolate(state.on_error, ctx)` (`:2122`) and immediately before `return interpolate(state.next, ctx)` (`:2135`). Without these, `next: "${context.missing}"` terminates as `"error"` while `on_yes: "${context.missing}"` terminates as `"no_route"` — same failure class, different reason;
   - **bracketing `_evaluate()`** (`:2157`) — set `"decide"` immediately before the call and back to `"action"` immediately after it returns, because `_check_prepatch_check()` and `_check_tamper_guard()` (`:2161-2172`) run *after* `_evaluate()` in this branch but *before* any routing in the `next:` branch (`:2100-2110`). A raise from either check is about the action's filesystem effects and must classify as `"error"` in both branches, which only the bracket guarantees;
   - the routing block — set `"decide"` immediately before `# Route based on verdict` (`:2196`) and leave it there through stall detection, `RouteContext`/`before_route`, and `_route()`.

   All three `except` clauses at `:1027-1041` compute the reason from the marker: `reason = "no_route" if self._phase == "decide" else "error"` and pass `reason` to `_finish()` (keeping each clause's existing `error=` message).

   **Why the reset must be at the top of `_execute_state()`, not at the action call sites:** the marker is an instance attribute that survives across states. After state N finishes routing it is left at `"decide"`; if state N+1 raises *before* any action site is reached — sub-loop dispatch (`:2024`, missing-YAML `FileNotFoundError` re-raised at `:2029`), `human_approval` (`:2036`) or `learning` (`:2043`) dispatch, `_build_context()` (`:2021`), the tamper-guard snapshot (`:2060-2066`), or `_execute_with_baseline()` (`:2141`) — a marker set only at `:2078`/`:2147` would misclassify that raise as `no_route`. Resetting at entry covers every pre-action raise site in one line and keeps the missing-sub-loop-YAML case at `"error"` per Scope Boundaries.

   **Why all three clauses consult the marker, not just the generic one:** `InterpolationError` is *not* attempt-batch by construction. `_route()` interpolates route targets at `:3319`, so a target like `on_yes: "${context.target}"` with the variable missing raises `InterpolationError` from the decide phase into the `:1032` clause. (`_evaluate()` itself is safe — it swallows its own `InterpolationError` at `:3134`.) `HeredocCollisionError` can only originate in action heredoc handling, so consulting the marker there is a no-op but keeps the three clauses uniform.

   Precedent for a stored-attribute classifier consulted at a shared exit: `self._pending_error` (`:897`), `self._summary_state_executed`/`self._iteration_summary_executed` (`:976-980`) — all instance flags set earlier and read at the `_finish()` decision point. This is the same shape.

3. **Throttle `__STOP__` needs no handling** — `_check_throttle()` sets `self._pending_error` before returning `"__STOP__"` (`:1593-1597`), and `run()` checks `_pending_error` at `:897` *before* the `None` check at `:981`, so it stays `"error"` (infra class) without touching the marker. Likewise the stall-abort `return None` sites (`:2239`, `:2270`, set `_pending_stall_abort`) and the signal-killed-action `return None` (`:2119`, calls `request_shutdown()`) are intercepted by `run()` before `:981`.

4. **Sub-loop child died, parent declares neither `on_error` nor `on_no`** — `_execute_sub_loop()` returns `None` at `:1329` after stashing the child's message in `captured[<state>]["error"]`, which reaches the `:981` site. After this issue the *parent* terminates `no_route` with `error="No valid transition"` (today: `"error"` with the same message). This is the intended classification — the parent has no route declared for a child death, which is a loop-authoring bug — and a grandparent's widened `_execute_sub_loop()` tuple still treats it as "child died". The child's own message stays in `captured` only; surfacing it in the parent's `result.error` is out of scope. Pinned by test 4(f).

### Codebase Research Findings (retained, condensed)

- `advisor.py::consult_for_trigger()` (~540-590) maps distinct exception types to distinct reason strings one per `except` clause — the closest analog for *exception*-driven classification, but only relevant to the generic clause here since the decision-step class is not exception-driven.
- No `Literal`/JSON-Schema `enum` constrains `terminated_by` anywhere (`loop_complete.json` is `"type": "string"`, `session_store/schema.py` column is `TEXT`); the addition is purely additive.
- Pre-existing drift: the inline comment at `fsm/types.py:59` (10 values) omits `stall_detected`, `host_pressure_abort`, `host_budget_exceeded`, `workdir_vanished` (all in the docstring `:35-43`) and `cost_ceiling_exceeded` (used at `executor.py:958`, in neither). Fix the inline comment while adding `no_route`.

## Program Design

### Types
- `ExecutionResult.terminated_by: str` (`scripts/little_loops/fsm/types.py:59`) — add `"no_route"` to the docstring vocabulary (`:35-43`) and the inline comment (`:59`).
- `FSMExecutor._phase: str` (new instance attribute, `"action"` | `"decide"`, default `"action"`) — reset to `"action"` at the top of `_execute_state()`; `"decide"` around the `next:`-branch route interpolations (`:2122`, `:2135`), bracketing `_evaluate()` (`:2157`, back to `"action"` after), and from the routing block (`:2196`) onward.

### Signatures
- `FSMExecutor._finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult` (`fsm/executor.py:4264`) — unchanged signature; receives `"no_route"` from the two new sites.

### Call Path
`FSMExecutor.run()` → `FSMExecutor._execute_state()` (resets `_phase = "action"`) → either `FSMExecutor._run_action_or_route()` / a pre-action dispatch (attempt-batch; re-raises into `run()`'s `except` clauses at `fsm/executor.py:1027-1041` with `_phase == "action"` → `_finish("error")`) or `FSMExecutor._evaluate()` / `FSMExecutor._route()` (decision-step; a `None` return reaches the direct call at `:981` → `_finish("no_route")`, a raise reaches any of the three clauses with `_phase == "decide"` → `_finish("no_route")`) → `FSMExecutor._finish()` → `record_loop_run_summary()` (writes the `loop_runs` row).

## Integration Map

### Engine

- **`FSMExecutor._execute_sub_loop()` (`fsm/executor.py:1304`, `:1320`)** — two literal `in ("error", "workdir_vanished")` membership checks (verdict derivation and `on_error` routing) are the engine's generic `type: loop` dispatch. Widen both to `("error", "no_route", "workdir_vanished")`, or a child that dies with `no_route` routes to `on_no` instead of `on_error` for every parent loop.
- `scripts/little_loops/cli/loop/runner.py::EXIT_CODES` (`:39-55`) — `"error"` has no entry (falls to the `.get(..., 1)` default). Add an explicit `"no_route": 1` entry per the `workdir_vanished` precedent so the exit code is declared, not defaulted.
- `scripts/little_loops/history_reader/usage.py::_WASTED_RUN_PREDICATE` (`:310-316`) — add `'no_route'` to the `IN (...)` list.
- `scripts/little_loops/fsm/persistence.py::map_final_status()` (`:132-168`) — no change; `no_route` correctly falls to the `"failed"` default. Add it to the trailing comment listing the values that land there.

### Loop YAML

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:1043-1046` — the `case "...:${captured.confidence_check.terminated_by?}" in True:*|*:error|*:timeout|*:max_steps)` arm is an exact-string glob; add `*:no_route`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~365-366, ~613) and `scripts/little_loops/loops/autodev.yaml` (~699) — comment prose narrating the `"error"`-only funnel; update wording. `auto-refine-and-implement.yaml:367`'s `case ... in terminal) ... *) exit 1` switch needs no change (`no_route` falls into `*)` with every other non-terminal outcome, which is correct).

### Documentation

- `docs/reference/API.md` — `ExecutionResult` usage example (~6369), field comment (~6379), `waste_attribution()` prose (~8820-8823).
- `docs/reference/CLI.md` (~574, `ll-ctx-stats` section) — waste-attribution vocabulary prose.
- `scripts/little_loops/generate_schemas.py` (`:607-636`) `EVENT_SCHEMAS["loop_complete"]` `terminated_by`/`error` descriptions, then regenerate `docs/reference/schemas/loop_complete.json` via `ll-generate-schemas`.
- `docs/reference/EVENT-SCHEMA.md` `### loop_complete` rows; `docs/guides/LOOPS_GUIDE.md` `### terminated_by exit reasons` table (~916, add a `no_route` row) and `## Troubleshooting` (~1326).
- `docs/reference/COMMANDS.md` `/ll:debug-loop-run` "Signal detection rules" (~857-858); `skills/debug-loop-run/reference.md` (`:26`, `:64-68`, `:70-76`); `skills/debug-loop-run/SKILL.md` (`:181`, `:196`, `:204`) — the "Evaluate error terminated the loop" rule keys off `terminated_by == "error"` and should now key off `no_route` (that is precisely the case this value names). Not covered by the MR-8 lint (FSM-YAML-only); hand-update.
- `skills/create-loop/reference.md` (~783-785) sub-loop `Routing` classification — name `no_route` alongside `error` under `on_error`. Then resync mirrors: `ll-adapt --host qwen --apply`, `ll-adapt --host kimi-code --apply`, `ll-adapt --host gemini --apply` (the `.qwen/skills/create-loop/reference.md`, `.kimi-code/skills/create-loop/reference.md`, and `.gemini/skills/create-loop/reference.md` copies are verbatim mirrors gated by `test_verify_host_map.py`).

### Confirmed Not Affected

- `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` (`:2058-2083`) — checks `if "error" in event` before `terminated_by`; `_finish()` still sets `error=` for `no_route`, so the `"error"` bucket fires unchanged. `docs/runbooks/FLEET_LOOP_REVIEW.md`'s vocabulary and `test_ll_logs.py` assertions are unaffected. See the deferred-bucketing note under Scope Boundaries — this is a known limitation, not an oversight.
- `FSMExecutor._check_throttle()` `"__STOP__"` return (`fsm/executor.py:1593-1597`, consumed at `:2082`/`:2151`) — sets `_pending_error`, which `run()` checks at `:897` before the `None` check at `:981`; stays `"error"` with no marker interaction.
- `transport.py:1749-1753`, `cli/loop/{feed.py,testing.py,audit.py,signals.py}`, `history_reader/runs.py:331-401` (`group_by="terminated_by"` rollup gains a bucket automatically), `mcp_server/tasks.py`, `cli/loop/evidence.py` — generic string pass-through.

## Implementation Steps

1. Add `self._phase = "action"` in `FSMExecutor.__init__`; **reset it to `"action"` as the first statement of `_execute_state()`** (`fsm/executor.py:2011`, before `_build_context()`). Set `"decide"` at the four sites in Design § Mechanism: before `interpolate(state.on_error, ctx)` (`:2122`) and `interpolate(state.next, ctx)` (`:2135`) in the `next:` branch; bracketing `_evaluate()` (`:2157` — `"decide"` before, `"action"` after it returns); and before the routing block (`:2196`), left there through `_route()`. Change all three `except` clauses at `:1027-1041` to compute `reason = "no_route" if self._phase == "decide" else "error"` and pass `reason` to `_finish()`, keeping each clause's existing `error=` message. Do **not** set the marker at the `_run_action_or_route()` call sites — the entry reset already covers them and every pre-action dispatch (see Design § Mechanism).
2. Change `fsm/executor.py:981` to `_finish("no_route", error="No valid transition")`. Leave `:897` (FATAL_ERROR) as `"error"`.
3. Re-point the existing decision-step assertions in `scripts/tests/test_fsm_executor.py` from `"error"` to `"no_route"`: `test_no_valid_route_terminates_with_error` (:2027), `test_on_partial_missing_falls_through_to_error` (:2110), `test_on_blocked_missing_falls_through_to_error` (:2177), `test_extra_routes_missing_falls_through_to_error` (:2241), `test_undeclared_cannot_judge_shorthand_no_on_error_terminates_loud` (:2382), `test_no_valid_transition_returns_error` (:5552), `test_before_route_veto_terminates_with_error` (:7534). Rename the tests to say `no_route`. **Leave every attempt-batch assertion (`test_exception_during_execution_returns_error_result`, `..._emits_error_in_loop_complete_event`, `test_exception_in_branch_c_without_on_error_reraises`, `test_heredoc_collision_halts_run_even_with_on_error_set`, `test_missing_context_variable_produces_friendly_message`, `test_missing_capture_returns_error`, `test_missing_required_fragment_param_terminates_with_error`) and every infra-driven assertion (`test_fatal_error_signal_*`, `test_sub_loop_missing_loop_without_on_error`, `test_stop_event_emitted_beyond_hard_max`) unchanged at `"error"`.**
4. Add seven new tests in `test_fsm_executor.py` (one method per raise-site, the file's convention): (a) an evaluator that raises inside `_evaluate()` produces `terminated_by == "no_route"` with the exception text in `result.error` — inject the raise by registering a callable that raises in `executor._contributed_evaluators[<type>]` with a matching `evaluate.type` (dispatched at `:3140`; no existing test does this, so this is the precedent), or by `monkeypatch.setattr(executor, "_evaluate", ...)`; (b) an action that raises with no `on_error` still produces `"error"` (pins the phase marker so a later refactor can't flip it); (c) **marker-leak regression**: a two-state loop where state 1 is a normal action+evaluate state that routes to state 2, and state 2 is a `type: loop` sub-loop whose YAML is missing and has no `on_error` — asserts `terminated_by == "error"` (fails if the reset is placed at the action call sites instead of `_execute_state()` entry); (d) **route-target interpolation**: a state whose `on_yes` is `"${context.missing_target}"` with the variable unset — asserts `terminated_by == "no_route"` and that `result.error` still carries the existing "Missing context variable … Run with: ll-loop run" message from the `InterpolationError` clause; (e) **`next:` route-target interpolation**: same as (d) but with `next: "${context.missing_target}"` on a shell-action state — asserts `"no_route"` (fails if the `:2135` marker site is omitted); (f) **sub-loop child death, no parent route**: a parent `type: loop` state with neither `on_error` nor `on_no` whose child terminates `"error"` — asserts the parent's `terminated_by == "no_route"`, `result.error == "No valid transition"`, and the child's message is in `executor.captured[<state>]["error"]` (pins Design § Mechanism item 4); (g) **tamper-guard raise stays `"error"`**: `monkeypatch` `_check_tamper_guard` to raise on an evaluate-branch state — asserts `"error"` (fails if `_evaluate()` is not bracketed back to `"action"`).
5. Widen `_execute_sub_loop()`'s two tuples (`fsm/executor.py:1304`, `:1320`) to include `"no_route"`; add a `test_fsm_executor.py` sub-loop test asserting a child ending in `no_route` routes to the parent's `on_error` and yields `verdict == "error"`.
6. Add `"no_route": 1` to `EXIT_CODES` (`cli/loop/runner.py:39-55`); add a `test_cli_loop_lifecycle.py::TestCmdResumeExitCodes` case on the `test_workdir_vanished_returns_exit_code_1` shape.
7. Add `'no_route'` to `_WASTED_RUN_PREDICATE` (`history_reader/usage.py:310-316`); extend `test_history_reader_usage.py::TestWasteAttribution` with a `no_route` run (the file's `_seed_run`-helper convention).
8. Add `*:no_route` to the `refine-to-ready-issue.yaml:1043-1046` case arm; add a `test_builtin_loops.py` case exercising that alternation with `failure_terminal != "True"` (none exists today — `test_write_failure_evidence_attributes_sub_loop_failure` :2200-2220 only covers the `True:*` arm).
9. Add a `"no_route" → "failed"` case to `test_fsm_persistence.py::test_archive_run_only_maps_terminated_by_to_status` (:1071-1102).
10. Update `fsm/types.py` docstring (`:35-43`), the `error:` field docstring line (`:52`, currently `Error message if terminated_by is "error"` — now `"error"` or `"no_route"`), and the inline comment (`:59`), fixing the pre-existing drift while there. Also update the `RouteDecision(None)` docstring line at `fsm/executor.py:202` from `→ _finish("error")` to `→ _finish("no_route")`.
11. Update the documentation and skill files enumerated in the Integration Map, regenerate `loop_complete.json`, and resync the three `create-loop` mirrors with `ll-adapt`. Update `test_debug_loop_run_synthesis.py::test_eval_error_termination_inline_no_eval_no_new_signal` (:591-604) and the docstring of `test_builtin_loops.py::test_resolve_decision_call_states_declare_on_error_matching_on_failure` (~8807-8814) to match the new prose.
12. `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_persistence.py scripts/tests/test_debug_loop_run_synthesis.py scripts/tests/test_history_reader_usage.py scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_verify_host_map.py -v` passes.

## Impact

- **Priority**: P2 - inherited from ENH-3468; improves failure-class observability, blocks nothing critical.
- **Effort**: Medium - two small executor edits plus a phase marker, then ripple through 7 test assertions, 3 consumer tuples/predicates, generated schema, and ~8 doc/skill files.
- **Risk**: Low - `"error"` keeps its current meaning; only the rarer decision-step class gets a new string, and every consumer that must treat it as "child died" is widened in this issue.
- **Breaking Change**: No for `"error"` consumers. A consumer outside this repo that matched `terminated_by == "error"` to detect a missing-route loop-authoring bug would now need `no_route`; called out in the LOOPS_GUIDE row.

## Tests

- `scripts/tests/test_fsm_executor.py` — existing tests construct `FSMLoop`/`StateConfig` directly and assert on `result.terminated_by`/`result.error`/`result.final_state`; new tests follow that shape (one method per raise-site, not `parametrize`).
- `scripts/tests/test_history_reader_usage.py::TestWasteAttribution` — `_seed_run` helper plus a single assertion block.
- `scripts/tests/test_cli_loop_lifecycle.py::TestCmdResumeExitCodes` — `test_workdir_vanished_returns_exit_code_1` (:1466) shape.

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

All core claims confirmed against current code: `fsm/executor.py:981` is
confirmed a direct `_finish("error", error="No valid transition")` call (not an
exception path); the `try`/`except` funnel at `:1027` (`HeredocCollisionError`),
`:1032` (`InterpolationError`), `:1040` (generic `except Exception`) all match
exactly; `:897` (FATAL_ERROR), `:2078`/`:2147` (`_run_action_or_route()` call
sites), `:2157` (`_evaluate()` call site), and `:1304`/`:1320`
(`_execute_sub_loop()` tuples) all match exactly. `fsm/types.py:59`'s
10-value inline comment and its omission of `stall_detected`,
`host_pressure_abort`, `host_budget_exceeded`, `workdir_vanished`, and
`cost_ceiling_exceeded` (present in the `:35-43` docstring) is confirmed
accurate. `cli/loop/runner.py::EXIT_CODES` (`:39-55`) confirmed to have no
`"error"` entry. `history_reader/usage.py::_WASTED_RUN_PREDICATE` (`:310-316`)
confirmed. Parent `ENH-3468` confirmed to exist.

Drift found: the seven decision-step test line citations in Implementation
Step 3 (`test_no_valid_route_terminates_with_error` and six others) had drifted
11-30 lines from intervening test-file edits; corrected in place in this pass
(now :2027, :2110, :2177, :2241, :2382, :5552, :7534). All seven test functions
still exist under their cited names and still assert `terminated_by == "error"`
at the affected sites, consistent with the issue's premise.

Proposal-vs-code check (B6): the phase-marker mechanism is sound —
`_execute_state()` (which would set `self._phase`) is called from inside
`run()`'s `try` block (opens `:627`, call at `:893`), so an exception raised
inside `_evaluate()`/`_run_action_or_route()` propagates up through
`_execute_state()` into `run()`'s own `except Exception` clause where
`self._phase` (an instance attribute, not a stack-local) is still readable —
same shape as the existing `self._pending_error`/`self._summary_state_executed`
precedent the issue cites.

Graph: provider=`codegraph` freshness=`fresh` (not used for this check; grep/Read
sufficed and gave exact confirmation).

---

## Resolution

- **Action**: improve
- **Completed**: 2026-09-16
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/executor.py`: added `self._phase` instance attribute (reset to `"action"` at `_execute_state()` entry, flipped to `"decide"` around route-target interpolation and the `_evaluate()`/routing block); `run()`'s three `except` clauses now compute `reason = "no_route" if self._phase == "decide" else "error"`; the direct `_finish("error", error="No valid transition")` call is now `_finish("no_route", ...)`; widened both `_execute_sub_loop()` on_error/verdict tuples to include `"no_route"`; updated the `RouteDecision(None)` docstring line.
- `scripts/little_loops/fsm/types.py`: added `"no_route"` (and the pre-existing `cost_ceiling_exceeded` drift) to the `terminated_by` docstring and inline comment.
- `scripts/little_loops/fsm/persistence.py`: `map_final_status()` trailing comment now lists `no_route` alongside `error`.
- `scripts/little_loops/cli/loop/runner.py`: added explicit `EXIT_CODES["no_route"] = 1`.
- `scripts/little_loops/history_reader/usage.py`: added `'no_route'` to `_WASTED_RUN_PREDICATE`.
- `scripts/little_loops/generate_schemas.py` + regenerated `docs/reference/schemas/loop_complete.json`: `terminated_by`/`error` field descriptions cover `no_route`.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: added `*:no_route` to the failure-attribution case arm.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`, `autodev.yaml`: updated comment prose narrating the `"error"`-only funnel to include `no_route`.
- Docs: `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/reference/COMMANDS.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/guides/LOOPS_GUIDE.md` (`terminated_by` table + Troubleshooting), `skills/debug-loop-run/{SKILL.md,reference.md}`, `skills/create-loop/reference.md` (+ `.qwen`/`.kimi-code`/`.gemini` mirrors via `ll-adapt --apply`).
- Tests: re-pointed 7 existing `test_fsm_executor.py` decision-step assertions from `"error"` to `"no_route"`; added a `TestNoRouteVsErrorClassification` class (7 tests, one per raise-site); added sub-loop-tuple-widening, `EXIT_CODES`, waste-attribution, loop-YAML case-arm, and persistence-mapping tests across `test_fsm_executor.py`, `test_cli_loop_lifecycle.py`, `test_fsm_persistence.py`, `test_history_reader_usage.py`, `test_builtin_loops.py`; updated docstrings in `test_debug_loop_run_synthesis.py` and `test_builtin_loops.py` to match the new classification.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 24504 passed, 51 skipped; one unrelated xdist worker-crash flake on `test_feat3323_sse_bridge.py` reproduced clean in isolation and on re-run)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`python -m mypy scripts/little_loops/` — 397 source files)
- Run: N/A (library/FSM-engine change, no standalone entry point)
- Integration: PASS (spot-checked every cited line number in the issue's Program Design against current `executor.py` before implementing; no design changes needed)

## Session Log
- `/ll:manage-issue` - 2026-09-16T00:38:10 - `cc8685da-dafe-499c-ae00-e60e56afe19e.jsonl`
- `/ll:ready-issue` - 2026-09-15T23:54:57 - `d2c237a9-94bb-4fb3-9b36-410309bd7d7c.jsonl`
- `/ll:confidence-check` - 2026-09-15T23:39:30 - `f9b14b88-6ca5-46b6-b4a0-bf805586b764.jsonl`
- Manual review - 2026-09-15 - pre-implementation pass: (1) `next:`-branch route interpolations (`:2122`, `:2135`) were outside the "decide" window, so `next: "${missing}"` would classify `error` while `on_yes: "${missing}"` classified `no_route` — added marker sites; (2) `_check_prepatch_check`/`_check_tamper_guard` sat inside the "decide" window in the evaluate branch but outside it in the `next:` branch — `_evaluate()` is now bracketed and "decide" re-set before the routing block; (3) sub-loop child death with no parent `on_error`/`on_no` reaches `:981` and now reports the parent as `no_route` — stated as intended and pinned; (4) specified how test 4(a) injects an evaluator raise (`_contributed_evaluators`); (5) filed the deferred fleet-review bucketing as ENH-3482 (blocked by this issue). Tests 4(e)/4(f)/4(g) added.
- Manual review - 2026-09-15 - four corrections: (1) `_phase` must reset at `_execute_state()` entry, not at the action call sites, or a stale `"decide"` misclassifies pre-action raises (missing sub-loop YAML, HITL/learning dispatch, baseline at `:2141`); (2) `InterpolationError` clause is not attempt-batch-only — `_route()` interpolates targets at `:3319` — so all three `except` clauses consult the marker; (3) fleet-review bucketing via `_derive_loop_outcome()` explicitly deferred; (4) added `types.py:52` and `executor.py:202` docstring sites. Added tests 4(c)/4(d) and a throttle `__STOP__` non-interaction note.
- `/ll:confidence-check` - 2026-09-15T23:19:58 - `4aed0df2-a263-4d28-ae34-d555931852b6.jsonl`
- `/ll:verify-issues` - 2026-09-15T23:13:49 - `0f995d07-641d-467b-93d8-b6a178acbacb.jsonl`
- Manual review rewrite - 2026-09-15 - corrected the mechanism (decision-step failures are direct `_finish()` calls at `executor.py:981`, not exceptions); pinned the value name `no_route`; decided supplement-not-replace so attempt-batch stays `error`.
- `/ll:wire-issue` - 2026-09-15T22:31:53 - `74d0e714-5fa8-4d36-8d26-f70b1e11f439.jsonl`
- `/ll:refine-issue` - 2026-09-15T22:16:07 - `a0a3cae8-46b6-4741-b032-8859dea7a727.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:29:41 - `8cf1df9b-8fca-46d9-b751-f28d170c6572.jsonl`
- `/ll:refine-issue` - 2026-09-14T19:32:05 - `93b68600-9c57-4c65-a431-1e887e42f117.jsonl`
- `/ll:format-issue` - 2026-09-14T19:18:19 - `e03a4d3e-6e32-492e-b751-6c3a912f41aa.jsonl`
- `/ll:issue-size-review` - 2026-09-13T19:16:24 - `bd6d1308-41a1-42e0-b1ba-67bcf198d91f.jsonl`

## Status

**Open** | Created: 2026-09-13 | Priority: P2

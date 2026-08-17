---
id: ENH-3224
type: ENH
title: ll-harness ABSTAIN exit code 3 is indistinguishable from an error to a parent
  FSM
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:29:27Z'
parent: EPIC-3217
decision_needed: false
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
testable: true
---

# ENH-3224: ll-harness ABSTAIN exit code 3 is indistinguishable from an error to a parent FSM

## Summary

ENH-3185 gave `ll-harness` a distinct ABSTAIN exit code 3, so an inconclusive run is separable from a pass (0) and a failure (1). A parent FSM cannot see that distinction: the `exit_code` evaluator maps `0 → yes`, `1 → no`, and `2+ → error` (`scripts/little_loops/fsm/evaluators.py:250-255`), so exit 3 collapses into `error` — the same verdict a crash, a missing binary, or a timeout produces.

## Current Behavior

A loop shelling out to `ll-harness` (via the `shell_exit` fragment in `loops/lib/common.yaml`, or any `evaluate.type: exit_code` state) routes an all-abstained harness run to `on_error`. The loop cannot tell "the harness ran fine and could not judge" from "the harness died".

No built-in loop currently invokes `ll-harness`, so this is latent rather than actively breaking a shipped loop. It becomes real as soon as a harness run is composed into a loop — which is the composition ENH-3185's exit code was added to enable.

## Expected Behavior

A parent FSM can route an abstained sub-invocation distinctly from an errored one, so that the abstention semantics established inside the FSM (hold, or a declared `on_cannot_judge` route) survive a process boundary.

**The flag is only useful paired with a declared `on_cannot_judge` route.** `_abstention_fallback()` (`executor.py:2688-2700`) resolves `on_error` *only* — it deliberately never falls back to `route.default` or an implicit `on_no`. So a state that sets the new flag but declares no `cannot_judge` route will hold up to `_ABSTENTION_HOLD_CAP = 2` times (`executor.py:2658`), **re-running the full `ll-harness` evaluation twice**, and then land on `on_error` anyway — i.e. exactly the ABSTAIN→error collapse this issue exists to remove, plus two expensive re-executions. The flag without the route is strictly worse than the status quo.

This is the natural enforcement hook for ENH-3222: that rule's predicate must treat a flag-carrying `exit_code` state as abstention-capable, so `ll-loop validate` catches the flag-without-route shape statically. The two issues should be sequenced together.

## Motivation

Abstention is only useful if it propagates. Inside one FSM the grammar is now precise; the moment it crosses into a subprocess it is flattened back into the binary-plus-error shape the enhancement set out to replace. The same flattening will apply to any future tool that adopts the ABSTAIN exit code.

## Proposed Solution

**Direction set by EPIC-3217 decision (b), 2026-08-16: option 1 — map exit 3 to `cannot_judge` in the `exit_code` evaluator.**

The EPIC weighed this issue against adding an abstain-shaped FSM terminal (a third outcome alongside `done` and `failure: true`, mirroring `ll-harness`'s own three-way split) and rejected the terminal. The reasoning: the distinction with a real consumer is at the **evaluator boundary** — a parent FSM reading a child process's exit code — not at the terminal boundary, which would serve only the inverse case (a child *loop* reporting inconclusive to its caller) and has zero consumers today. A new terminal kind would cost a `StateConfig` flag, an `ExecutionResult` field, `_finish`, persistence, `EXIT_CODES`, the `worker_pool`/`queue` consumers of `FAILURE_TERMINAL_EXIT_CODE`, the validation walker, docs, and a policy call on what `ll-parallel` does with an abstaining gate. FSM terminals therefore stay binary, and this issue carries the whole abstention-across-a-process-boundary story.

The original option-1 caveat stands and is the main design work here: **exit 3 is not a reserved code**, so a global remap would make any command returning 3 emit an abstention verdict. The mapping must be opt-in per state (or scoped to invocations known to follow the ABSTAIN contract) rather than a blanket change to `evaluate_exit_code`.

Options 2 and 3, retained for context but not chosen:

2. **A dedicated `harness_exit` fragment / evaluator** that knows the `ll-harness` exit-code contract specifically. Narrower and safer; costs a new evaluator type. Reconsider only if the opt-in mechanism for option 1 turns out to be clumsier than a separate type.
3. **Allow numeric verdict keys in `route:`** so a state can write `route: {3: <state>}`. Most general, largest schema surface.

Document the mapping next to the ABSTAIN exit code so the two stay in sync. Note the two CLIs already disagree on exit `2` (`ll-loop run` = failure terminal, `fsm/types.py:25`; `ll-harness` = infra error, `cli/harness.py:698-700`), so the doc should state the contract per-tool rather than implying one global exit-code vocabulary.

**Ship it with a consumer.** This issue's own Current Behavior notes that no built-in loop invokes `ll-harness`, so as scoped the flag ships with zero users — reproducing the exact "mechanism exists, nothing reads it" defect that ENH-3185 left behind and that ENH-3223 (and this EPIC) exist to clean up. Landing the flag alone means the abstention-across-a-process-boundary story is still untested against a real composition. Minimum bar: a worked example that a loop author can copy — either a `harness_exit`-shaped fragment in `loops/lib/common.yaml` (wrapping `evaluate: {type: exit_code, <flag>: true}` with an `on_cannot_judge` route) or a documented example in the exit-code contract doc. See the added acceptance criterion below.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Option A**: Map exit 3 to `cannot_judge` in the `exit_code` evaluator, opt-in per state (or scoped to invocations known to follow the ABSTAIN contract) rather than a blanket change to `evaluate_exit_code`.

> **Selected:** Option A — reuses the existing `uncertain_suffix` opt-in-flag triad on `EvaluateConfig` with no new abstraction; abstention routing is already verdict-string-driven and evaluator-agnostic.

**Option B**: A dedicated `harness_exit` fragment / evaluator that knows the `ll-harness` exit-code contract specifically. Narrower and safer; costs a new evaluator type. Reconsider only if the opt-in mechanism for option 1 turns out to be clumsier than a separate type.

**Option C**: Allow numeric verdict keys in `route:` so a state can write `route: {3: <state>}`. Most general, largest schema surface.

**Recommended**: Option A — direction set by EPIC-3217 decision (b), 2026-08-16.

### Decision Rationale

**Selected: Option A** — map exit 3 to `cannot_judge` in `evaluate_exit_code()`, gated by a new per-state opt-in flag on `EvaluateConfig`.

**Reasoning**: Option A reuses the exact `EvaluateConfig.uncertain_suffix: bool = False` (`scripts/little_loops/fsm/schema.py:103`) opt-in-flag shape already established for `evaluate_llm_structured` — dataclass field → `to_dict()`/`from_dict()` round-trip → explicit keyword parameter → dispatch-site wiring — and needs no new routing machinery, since `cannot_judge` abstention handling (`executor.py:2075-2097`, `is_abstention_verdict()` in `verdicts.py:25-27`) is already generic across evaluator types. Its footprint is contained to three files (`evaluators.py`, `schema.py`, `fsm-loop-schema.json`) plus directly-extensible existing tests (`TestExitCodeEvaluator` in `test_fsm_evaluators.py:54-76`). Option B (a dedicated `harness_exit` evaluator type) has codebase precedent (`evaluate_mcp_result`, `evaluate_harbor_scorer`) but requires registering a brand-new evaluator type across 6+ touch points (dispatcher branch, `EvaluateConfig.type` Literal, JSON-schema enum, `EVALUATOR_REQUIRED_FIELDS`, multiple test files, multiple docs) and duplicates the `0/1` mapping `evaluate_exit_code` already owns. Option C (numeric verdict keys in `route:`) has no precedent anywhere in the FSM schema — `RouteConfig.routes`, `_route()`, and all 8 downstream consumers (executor, schema, topology, route_table, four CLI modules) are string-typed throughout, an unquoted YAML numeric key parses as `int` rather than `str` and would silently fail the existing string-keyed lookup, and `route_table.py`'s `sorted()` call over mixed `str`/`int` keys would raise `TypeError` — the change would touch every evaluator type's routing, not just `exit_code`.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — opt-in flag on `exit_code` evaluator | 3 | 3 | 3 | 3 | 12/12 |
| B — dedicated `harness_exit` evaluator type | 2 | 1 | 1 | 1 | 5/12 |
| C — numeric verdict keys in `route:` | 0 | 0 | 0 | 0 | 0/12 |

**Key evidence**:
- `uncertain_suffix` triad precedent: `schema.py:103, 146-147, 197`; `evaluators.py:1107, 1295-1296, 2041`
- Abstention routing already evaluator-agnostic: `executor.py:2075-2097`; `verdicts.py:11, 25-27`
- Option B's new-evaluator-type footprint: `evaluators.py` dispatcher + `_EXIT_CODE_AWARE_EVALUATORS` (1876-1888), `schema.py:77-93` (`type: Literal[...]`), `fsm-loop-schema.json` enum, `fsm/validation/_base.py:45-61` (`EVALUATOR_REQUIRED_FIELDS`)
- Option C's string-typed `route:` contract: `schema.py:229-261` (`RouteConfig`), `executor.py:2699-2752` (`_route()`), `route_table.py:79-86` (`sorted()` over mixed-type keys would raise `TypeError`)

## Program Design

### Types
N/A — no new data type. The existing `EvaluationResult(verdict: str, details: dict)` return shape is reused; abstention is expressed purely by the string value `"cannot_judge"` (`scripts/little_loops/fsm/verdicts.py:11,25-27`, `is_abstention_verdict()`), not a separate type.

### Signatures
- `evaluate_exit_code(exit_code: int) -> EvaluationResult` — current mapping, `scripts/little_loops/fsm/evaluators.py:238-257`: maps `0 -> yes`, `1 -> no`, everything else `-> error`.
- `EvaluateConfig.uncertain_suffix: bool = False` — the codebase's existing precedent for a per-state opt-in flag that changes an evaluator's verdict mapping; `scripts/little_loops/fsm/schema.py:103`, consumed by `evaluate_llm_structured(..., uncertain_suffix: bool = False, ...)` at `evaluators.py:1107` (branch at `1295-1296`) and wired at the dispatch call site as `uncertain_suffix=config.uncertain_suffix` at `evaluators.py:2041`. A new opt-in flag for `exit_code` follows the identical triad: `EvaluateConfig` field -> `to_dict()`/`from_dict()` round-trip (`schema.py:123-181`, `183-213`) -> explicit keyword parameter on `evaluate_exit_code()` -> dispatch-site wiring in `evaluate()` (`evaluators.py:1898-1899`).
- `evaluate_config_known_fields() -> set[str]` — derives its field set from the `EvaluateConfig` dataclass itself, `schema.py:217-225`; a new field is automatically visible to the MR-14 unknown-evaluate-key validator with no separate registration.

### Call Path
_Line anchors re-verified 2026-08-17; the previous revision's `executor.py` numbers were ~4 lines stale._

FSM state `evaluate: {type: exit_code, <new_opt_in_flag>: true}` -> `evaluate()` dispatcher (`evaluators.py:1836-1899`, `exit_code` branch dispatching `evaluate_exit_code(exit_code)` at `evaluators.py:1899`) -> `evaluate_exit_code(exit_code, <new_opt_in_flag>)` (`evaluators.py:238`) -> `EvaluationResult(verdict="cannot_judge", ...)` when `exit_code == 3` and the flag is set -> `is_abstention_verdict()` gate -> undeclared abstention: `_abstention_declared()` (`executor.py:2660-2679`) is false -> `_route_abstention_hold()` (`executor.py:2702-2712`, holds up to `_ABSTENTION_HOLD_CAP = 2` at `executor.py:2658`) -> `_abstention_fallback()` (`executor.py:2688-2700`, resolves `on_error` only, never `route.default`); declared abstention (`on_cannot_judge: <state>` present) instead routes immediately through the normal `_route()` path via `state.extra_routes` (`schema.py:849-870`, generic `on_<verdict>` capture — `on_cannot_judge` has no dedicated `StateConfig` field, confirmed by BUG-3221's NO-GO on adding one).

Confirmed reachable: `exit_code` is a member of `_EXIT_CODE_AWARE_EVALUATORS` (`evaluators.py:1876-1888`), so BUG-1815's non-zero-exit short-circuit does **not** intercept exit 3 before it reaches `evaluate_exit_code()`.

### Decision Rules
- New gap kind: `evaluate_exit_code()`'s verdict mapping gains a third branch for exit code 3, gated by a per-state opt-in flag on `EvaluateConfig` (default `false`/absent).
- Exact inputs: `exit_code == 3` AND the opt-in flag is `true` -> verdict `"cannot_judge"`. `exit_code == 3` AND the flag is `false`/absent -> verdict stays `"error"` (today's behavior, unchanged for every state that doesn't opt in).
- Scoping requirement (from Proposed Solution): the mapping must not be a blanket remap of `evaluate_exit_code`, since exit code 3 is not OS-reserved and other commands may legitimately return 3 for unrelated reasons — hence the per-state flag rather than a global change.
- Escape hatch: a state that never sets the flag is unaffected by this change; a third-party command returning exit 3 continues to map to `error`.
- Open implementation choice, not pinned by research: the flag's exact name and whether it lives on `EvaluateConfig` (mirroring `uncertain_suffix`) versus elsewhere is an implementer decision — the `uncertain_suffix` triad is the closest codebase precedent either way.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_exit_code()` (238-257) needs the new opt-in parameter and its exit-3 branch; `evaluate()` dispatcher (1836-1899, exit-code-aware handling 1862-1899) needs to thread the new `EvaluateConfig` field through, mirroring `uncertain_suffix=config.uncertain_suffix` at 2041
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` (38-121) needs the new opt-in bool field plus its `to_dict()`/`from_dict()` entries (123-181, 183-213), following the `uncertain_suffix` shape at 103, 146-147, 197
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `evaluateConfig` JSON schema properties block (694-820) needs the matching schema entry, alongside `uncertain_suffix` at 765-769
- `docs/reference/API.md` — `exit_code` evaluator's verdict-mapping documentation (module reference around `evaluate_exit_code`, currently listing only `0/1/2+`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — the default-evaluator call site of `evaluate_exit_code` at `executor.py:2601` (the shell-mode `else` branch of `_evaluate()`, reached when a state has no `evaluate:` block — it has no `EvaluateConfig` in scope and so can never carry the flag); abstention hold/route dispatch this change must reach: the `is_abstention_verdict` gate, `_abstention_declared` (2660-2679), `_abstention_fallback` (2688-2700), `_route_abstention_hold` (2702-2712), `_route` (2716+). _Anchors re-verified 2026-08-17._
- `scripts/little_loops/loops/lib/common.yaml` — `shell_exit` fragment (15-21), the composition point for `evaluate.type: exit_code` shell states and the likely site for any `ll-harness`-aware wrapping (issue's own "Current Behavior" notes no built-in loop invokes `ll-harness` yet)
- `scripts/little_loops/cli/harness.py` — the ABSTAIN exit-code contract this evaluator must interoperate with: CLI epilog doc (372-376), single-task mapping (600-706, final mapping at 698-706: `not passed -> 1`, `abstained -> 3`, else `0`), multi-task `dsl` mapping (1035-1080, its own fail/error/abstain precedence documented at 1035-1037)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py` — a **third** direct call site of `evaluate_exit_code()` (line 128, `else: # Default to exit_code evaluation` branch in `ll-loop test`'s simulate path), invoked with no `EvaluateConfig` in scope. A state without an explicit `evaluate:` block hits this path and can never carry the new opt-in flag — same scope boundary as `executor.py`'s default-evaluator path, but a separate call site that must keep working with the new (presumably optional, default-`False`) parameter.
- `scripts/little_loops/history_reader.py` — `harness_eval_abstention_rate()` (line 3066, docstring anchor line 70: "ENH-3185 AC4") queries `cannot_judge` verdicts (line 3092) to compute an abstention rate; a real downstream consumer of the abstention signal this issue makes reachable from a parent FSM, worth being aware of even though no direct code change is anticipated here.

### Conventions in Force
- Per-state opt-in flags on `EvaluateConfig` follow a fixed triad: dataclass field with a default -> `to_dict()` conditional emission -> `from_dict()` `.get()` extraction — evidence: `uncertain_suffix` (`schema.py:103, 146-147, 197`)
- Opt-in flags are threaded into evaluator functions as explicit keyword parameters, then wired at the `evaluate()` dispatch call site — evidence: `evaluate_llm_structured(..., uncertain_suffix: bool = False, ...)` (`evaluators.py:1107, 1295-1296`, dispatch wiring at `2041`)
- Abstention routing is verdict-string-driven, not evaluator-type-driven: any evaluator returning `EvaluationResult(verdict="cannot_judge", ...)` is picked up uniformly by the `is_abstention_verdict()`-gated hold/route logic — evidence: `verdicts.py:11,25-27`; `executor.py:2075-2090`
- `on_cannot_judge` has no dedicated `StateConfig` field; it flows through the generic `on_<verdict>` -> `extra_routes` capture — evidence: `schema.py:849-870` (`from_dict`), `fsm-loop-schema.json:686-692` (`patternProperties`), confirmed by `.issues/bugs/P4-BUG-3221-fsm-loop-schemajson-stateconfig-omits-on_cannot_judge-under-additionalproperties-false.md`'s NO-GO on adding an explicit property
- Tests for evaluator changes follow one `Test<EvaluatorName>Evaluator` class with `@pytest.mark.parametrize` exit-code/verdict tables — evidence: `TestExitCodeEvaluator` (`scripts/tests/test_fsm_evaluators.py:54-76`), already covering `0/1/2/127/255/-1`

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestExitCodeEvaluator` class (54-76) is the model to extend with exit-3 cases under both opt-in-true and opt-in-false/absent configurations; no case currently exercises `exit_code=3` at all (parametrize list covers `0,1,2,127,255,-1`), so this is a clean gap, not a collision. Also add a dispatcher-level case modeled on `test_dispatch_llm_with_config_options` (`TestEvaluateDispatcher`, lines 1565-1580) — build `EvaluateConfig(type="exit_code", <new_flag>=True)`, call `evaluate(config, "", 3, ctx)`, assert `verdict == "cannot_judge"`.
- `scripts/tests/test_fsm_executor.py` — FSM executor abstention-routing tests (hold/escalate/declared-route behavior) that a newly-abstaining `exit_code` evaluator must exercise; `TestAbstentionRouting` (lines 1882-2070+) is the pattern to cross with an `exit_code`-flavored case (mirror `TestEvaluators.test_exit_code_evaluator` at ~2279, using `EvaluateConfig(type="exit_code")` + `MockActionRunner.always_return(exit_code=3)`, no LLM patching needed)
- `scripts/tests/test_fsm_schema.py` — `test_known_fields_helper_matches_dataclass_fields` (256-259) and `test_schema_json_evaluate_config_properties_match_dataclass_fields` (261-277) are generic dataclass-introspection lockstep tests; the latter **will fail** the moment the new field is added to `EvaluateConfig` without a matching `fsm-loop-schema.json` property (or vice versa) — this is the concrete gate enforcing the schema-JSON edit, not merely a suggestion
- `scripts/tests/test_fsm_validation_evaluator_rules.py`, `test_fsm_validation_structural.py` — validation-rule tests to extend if the new flag needs its own validation rule (e.g. warn when set on a state whose command isn't known to follow the ABSTAIN contract)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/integration/test_loop_run_e2e.py` — real-subprocess, no-mocks E2E pattern (`pytestmark = pytest.mark.integration`); closest existing case is `test_failure_path_reaches_failure_terminal` (lines 80-94, `action="exit 1", action_type="shell"`). Add an analogous `action="exit 3"` case exercising the new opt-in flag end-to-end through the real `FSMExecutor`, using the file's inline `_run()`/`_state()`/`_loop()` builders (25-48) — no separate fixture YAML needed, matching this file's convention.
- `scripts/tests/test_history_reader.py` — add/extend coverage for `harness_eval_abstention_rate()` now that a parent FSM can produce `cannot_judge` verdicts from an `exit_code` evaluator (not just `llm_structured`), since that function queries `cannot_judge` verdicts irrespective of which evaluator produced them.

### Documentation
- `docs/reference/API.md` — `exit_code` evaluator's verdict-mapping entry (source-of-truth prose mirrors the `evaluate_exit_code()` docstring per the `EvaluateConfig` `Attributes:` convention at `schema.py:45-75`); the same "0/1/2+" one-liner also appears at the `evaluate()` dispatcher section (~5907-5934) and needs the same update
- `docs/generalized-fsm-loop.md` (~line 1817) — narrative example invoking `evaluate_exit_code`; should reflect the new opt-in behavior if it demonstrates exit-code states
- The issue's own note that "the two CLIs already disagree on exit `2`" should be captured in whichever doc ends up hosting the per-tool exit-code contract (`ll-loop run` = failure terminal at `fsm/types.py:25`; `ll-harness` = infra error at `cli/harness.py:698-700`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md:613-619` — the canonical `#### \`exit_code\` (Default for Shell Commands)` verdict table (`0 → yes`, `1 → no`, `2+ → error`) is the exact prose the exit-3 carve-out invalidates; needs a new row or a footnote for the flag-gated `cannot_judge` case. The embedded pytest example at lines 1810-1819 (parametrized `0/1/2/127`) is illustrative only, not load-bearing, but could gain a `(3, "cannot_judge")` example row for completeness.

### Configuration
- N/A — no `.ll/ll-config.json` changes; the new opt-in surface is FSM YAML (`evaluate:` block), covered under Files to Modify above

## Implementation Steps

1. `evaluate_exit_code()` (`scripts/little_loops/fsm/evaluators.py:238-257`) accepts a per-state opt-in flag and maps `exit_code == 3` to verdict `"cannot_judge"` only when that flag is set; exit 3 without the flag still maps to `"error"`, matching every existing `TestExitCodeEvaluator` case in `scripts/tests/test_fsm_evaluators.py:54-76`
2. The opt-in flag is a real `EvaluateConfig` field (`scripts/little_loops/fsm/schema.py:38-121`) with `to_dict()`/`from_dict()` round-tripping and a matching `fsm-loop-schema.json` schema entry, following the `uncertain_suffix` triad (`schema.py:103, 146-147, 197`; `evaluators.py:1107, 1295-1296, 2041`)
3. A state declaring `evaluate: {type: exit_code, <flag>: true}` and exiting 3 reaches the existing abstention hold/route machinery (`executor.py:2075-2097`) exactly as any other `cannot_judge`-yielding evaluator does today — verified by extending `test_fsm_executor.py`'s abstention-routing coverage, not by adding new executor logic
4. The flag ships with at least one consumer: a `harness_exit`-shaped fragment in `scripts/little_loops/loops/lib/common.yaml` pairing `evaluate: {type: exit_code, <flag>: true}` with an `on_cannot_judge` route, **or** an equivalent worked example in the exit-code contract documentation. Landing the flag with zero consumers repeats the ENH-3185 pattern this EPIC is retiring.
5. The docs state plainly that the flag without an `on_cannot_judge` route is a regression, not a partial win — 2 holds (`_ABSTENTION_HOLD_CAP`, `executor.py:2658`) re-run the harness twice before `_abstention_fallback()` lands on `on_error` anyway
6. `python -m pytest scripts/tests/test_fsm_evaluators.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_executor.py -v` passes, and `docs/reference/API.md`'s `exit_code` evaluator entry documents the new opt-in mapping alongside the existing `0/1/2+` table

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Verify `scripts/little_loops/cli/loop/testing.py:128`'s direct `evaluate_exit_code()` call (the `ll-loop test` simulate path, no `EvaluateConfig` in scope) still compiles and behaves correctly with the new parameter — a third call site beyond the dispatcher and executor's default-evaluator path
- Update `docs/generalized-fsm-loop.md:613-619` — the `exit_code` evaluator's verdict-mapping table needs the exit-3 carve-out documented alongside `docs/reference/API.md`
- Add `scripts/tests/test_fsm_evaluators.py::TestExitCodeEvaluator` cases for `exit_code=3` under both flag-true and flag-false/absent, plus a dispatcher-level case modeled on `test_dispatch_llm_with_config_options`
- Add an `scripts/tests/integration/test_loop_run_e2e.py` case (`action="exit 3", action_type="shell"`) modeled on `test_failure_path_reaches_failure_terminal`, exercising the flag through a real, unmocked `FSMExecutor`
- Confirm `scripts/tests/test_fsm_schema.py::test_schema_json_evaluate_config_properties_match_dataclass_fields` passes after the schema-JSON edit — it fails loudly on drift, so treat it as the acceptance gate for that file

## Scope Boundaries

**In scope**
- The opt-in flag on `EvaluateConfig`, its `to_dict()`/`from_dict()` round-trip, its `fsm-loop-schema.json` entry, and the exit-3 branch in `evaluate_exit_code()`
- One worked consumer (fragment or documented example) per the added acceptance criterion
- Documenting the per-tool exit-code contract, including the existing exit-`2` disagreement between `ll-loop run` and `ll-harness`

**Out of scope**
- **An abstain-shaped FSM terminal** — explicitly rejected by EPIC-3217 decision (b); FSM terminals stay binary
- Options B (`harness_exit` evaluator type) and C (numeric verdict keys in `route:`) — scored 5/12 and 0/12 respectively
- Changing `ll-harness`'s own exit codes or the ABSTAIN contract; this issue only teaches a parent FSM to read them
- Any global remap of exit 3 — the mapping is per-state opt-in precisely because exit 3 is not OS-reserved
- The default-evaluator path (`executor.py:2601`) and `ll-loop test`'s simulate path (`cli/loop/testing.py:128`), which have no `EvaluateConfig` in scope and therefore can never carry the flag; they must keep compiling and behaving as they do today, but gain no new capability

## Impact

Enables abstention-aware loop composition over `ll-harness`. No current built-in loop changes behavior — which is also the risk: without the consumer required by step 4, the flag is unexercised outside its own tests.

## Dependencies

- **ENH-3222 must extend its predicate to cover this flag.** Once `exit_code` can emit `cannot_judge`, "LLM-judged" no longer means "abstention-capable", and ENH-3222's validator would miss a flag-carrying `exit_code` state with no `on_cannot_judge` route — the precise shape that makes this flag harmful. Land this issue first or concurrently.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` section — the
  `exit_code` evaluator's verdict mapping this issue targets

## Status

**Open** | Created: 2026-08-16 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-17T03:01:36 - `950fed1e-dcee-4e9e-a142-297b86aebff5.jsonl`
- `/ll:wire-issue` - 2026-08-17T01:55:28 - `bd5e977d-8602-4117-8dad-6c8c2098b8c6.jsonl`
- `/ll:decide-issue` - 2026-08-17T01:37:33 - `998c4c4b-eb46-4ebd-9513-1c70f20dff43.jsonl`
- `/ll:refine-issue` - 2026-08-17T01:32:26 - `998c4c4b-eb46-4ebd-9513-1c70f20dff43.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`

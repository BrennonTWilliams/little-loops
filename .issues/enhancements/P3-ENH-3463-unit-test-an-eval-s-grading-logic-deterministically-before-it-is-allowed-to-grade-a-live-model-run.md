---
id: ENH-3463
title: Unit-test an eval's grading logic deterministically before it is allowed to
  grade a live-model run
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels: []
blocked_by:
- 'ENH-3462'
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

`ll-harness` grading code decides pass/fail for every stochastic subject it evaluates, but nothing currently requires that the grading logic itself be tested. A scorer with an inverted comparison, an off-by-one threshold, or a regex that never matches will report confident verdicts on real runs, and because the subject is stochastic the wrong verdicts look like ordinary model variance rather than a bug in the harness.

Require that any grading or scoring function used by a live-model probe have deterministic unit tests over fixed synthetic inputs — zero API calls — covering at minimum a clear pass, a clear fail, and the boundary the threshold sits on. The tests exercise the grader as a pure function of (output, criteria) so they run in CI at no cost and fail loudly when scoring logic changes.

## Current Behavior

`ll-harness` grading logic decides pass/fail for every stochastic subject it evaluates, but nothing requires the grading logic itself to be tested. A scorer with an inverted comparison, an off-by-one threshold, or a regex that never matches reports confident verdicts on real runs; because the subject is stochastic, a wrong verdict is indistinguishable from ordinary model variance rather than a bug in the harness.

## Expected Behavior

Any grading or scoring function used by a live-model probe has deterministic unit tests over fixed synthetic inputs — zero API calls — covering at minimum a clear pass, a clear fail, and the boundary the threshold sits on. Grading logic is exercised as a pure function of (output, criteria), and a grader with a deliberately inverted comparison is caught by its own unit tests before any live run is dispatched.

## Design

The pattern is proven in a cross-host ruleset project whose eval strategy separates three tiers — deterministic unit tests, a live-model behavior gate, and an agentic benchmark — and whose load-bearing property is that **the graders of the live-model tier are themselves unit-tested** ("RED/GREEN, no API key"): the deterministic tier verifies the live-eval tier's grading logic before that logic is trusted to grade a real model. That is the exact discipline to import: a grader is not allowed to grade until its own logic passes its own deterministic tests.

Distinct from the adjacent verdict work: n-run redundancy (ENH-3415, shipped) governs how many runs a verdict needs before it counts; score-splitting work governs what gets scored; information-isolation work governs flow between builder and validator roles. None of the three tests the grader's own code.

## Acceptance

A grader with a deliberately inverted comparison is caught by its unit tests before any live run is dispatched.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for the two remaining test-coverage gaps and the missing dispatch gate.

### Files to Modify
- `scripts/tests/test_fsm_evaluators.py` — add the two missing cases: an `evaluate_output_json` fail-case and boundary-case (`TestOutputJsonEvaluator`, currently `test_fsm_evaluators.py:284-354`, only asserts `"yes"`/`"error"`), and an `evaluate_llm_structured` `confidence == min_confidence` exact-boundary case (`TestLLMStructuredEvaluator`, currently `test_fsm_evaluators.py:976-1798`, boundary tests only use a clearly-low confidence)
- `scripts/little_loops/cli/harness.py` — `_grade()` (`:1224`) is the sole call site through which a live-model probe reaches `evaluate_llm_structured()`; any presence/pass gate on grader tests has to sit here or at the `evaluate()` dispatcher both it and FSM execution route through
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` dispatcher (`:1839`), a linear `if/elif` chain on `config.type` with no registry — a gate that must apply to every grader type touches this chain once per branch unless wrapped at the call boundary instead

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:1913` (`_run_sample_loop`), `:1965` (`_evaluate_and_report`) — the two call sites that reach `_grade()` for a live sample
- `scripts/little_loops/fsm/evaluators.py:2058` — `evaluate()`'s own `evaluate_llm_structured` branch, a second call path into the same grader outside `_grade()`
- `scripts/little_loops/fsm/executor.py:41`, `scripts/little_loops/fsm/__init__.py:87`, `scripts/little_loops/fsm/types.py:12`, `scripts/little_loops/fsm/validation/structural_rules.py:19` — importers of `fsm/evaluators.py`; a gate added inside `evaluate()` is reachable from every FSM loop run, not only `ll-harness`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py:24,119` — imports `evaluate`/`evaluate_exit_code` and calls the `evaluate()` dispatcher directly from `ll-loop test`, a second CLI entry point into the same dispatcher outside `ll-harness`
- `scripts/little_loops/history_reader/harness.py:299-312` (`_rc_from_event`) — a parallel, non-importing reimplementation of `_grade()`'s exit-code banding contract (its own docstring: "Mirrors the run-time banding"); a gate added inside `_grade()` has no effect here and this function would silently diverge unless reconciled
- `scripts/tests/test_fsm_executor.py`, `test_ll_loop_execution.py`, `test_ll_loop_scaffold_verify.py`, `test_builtin_loops.py`, `test_fsm_open_question_stall.py`, `test_feat3033_idle_timeout.py`, `test_autodev_loop.py`, `test_rn_plan.py`, `test_host_runner.py` — import evaluator symbols or call `evaluate()`/`evaluate_*` directly, outside the three already-known grading test files
- ~29 loop YAML files under `scripts/little_loops/loops/` have `evaluate:` states of type `llm_structured`/`output_json`/`check_semantic` (e.g. `general-task.yaml`, `harness-plan-research-implement-report.yaml`, `eval-driven-development.yaml`, `lib/common.yaml`) — every FSM loop run reaching one of these states hits a gate wired inside the `evaluate()` dispatcher, not only `ll-harness`; confirmed `harness-optimize.yaml` is excluded (its `evaluate:` states are all `exit_code`)

### Conventions in Force
- Graders that would otherwise dispatch a live model call are tested by patching `subprocess.run` at the module level (`little_loops.fsm.evaluators.subprocess.run`) via a `mock_cli`/`_make_cli_response` fixture returning a canned CLI JSON envelope — evidence: `TestLLMStructuredEvaluator.mock_cli` (`test_fsm_evaluators.py:997-1005`), `TestBlindComparator` (`:2314`), `TestContractEvaluator` (`:2622`)
- Pure (non-LLM) graders get one `Test<EvaluatorName>Evaluator` class per function, methods named for the case (`_passes`/`_fails`, operator names), asserting both `result.verdict` and specific `result.details` keys — evidence: `TestExitCodeEvaluator` (`test_fsm_evaluators.py:55-98`, parametrized over exit-code→verdict tuples), `TestOutputNumericEvaluator` (`:98-227`, one `test_<op>_passes`/`test_<op>_fails` pair per operator)
- A state-scoped policy resolved as state-override-then-loop-default, validated by a schema/lint rule so an unrecognized value is caught before a run, is the shape any new grader-test gate would most closely follow — evidence: `_effective_tamper_guard_policy`/`_check_tamper_guard` (`fsm/executor.py:1601-1693`), `_effective_prepatch_check_policy`/`_check_prepatch_check` (`fsm/executor.py:1716-2107`)
- A `block`/`warn` policy gate distinct from grading, applied to require fresh proof before a dependency is trusted, is a second existing precedent for a presence-of-proof gate — evidence: `learning_tests/gate.py` (`is_record_stale`, `run_learning_gate_for_issue`), `release_gate.py` (`run_release_gate`)

### Tests
- `scripts/tests/test_fsm_evaluators.py` — direct tests for 9 of the 10 named graders (all but `evaluate_harbor_scorer`)
- `scripts/tests/test_benchmark_fragment.py` — `TestEvaluateHarborScorerVerdicts` (`:28-74`), the tenth grader's direct tests, in a separate file from the rest
- `scripts/tests/test_cli_harness.py` — `TestGradeEvidenceChannels` (`:3682`) calls `_grade()` directly against synthetic `RunnerResult` fixtures with the LLM grader mocked at `little_loops.cli.harness.evaluate_llm_structured`; no existing test in this class exercises a deliberately-inverted grader or a test-presence/pass gate

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation_evaluator_rules.py` `TestTamperGuardValidation`/`TestPrePatchCheckValidation` — closest lint-layer precedent: unrecognized-value WARNING, a `<key>_ok` suppression flag, six-method shape (unrecognized-on-state, unrecognized-on-loop-default, recognized-values-clean, unset-clean, suppression, wired-into-`validate_fsm`)
- `scripts/tests/test_fsm_schema.py:4842-4953` — dataclass round-trip + `fsm-loop-schema.json` declaration layer for the same two policies (`tamper_guard`/`prepatch_check`)
- `scripts/tests/test_fsm_executor.py` `TestTamperGuardExecutorHook`/`TestPrePatchCheckExecutorHook` — executor behavioral layer against a real `FSMExecutor.run()` (block/warn/allow routing, evidence accumulation)
- `scripts/tests/test_release_gate.py` — second existing "presence-of-proof" gate pattern: config-driven warn/block mode, one test class per mode
- `scripts/tests/test_learning_tests_version_staleness.py` — pure boundary-predicate pattern (`is_record_stale`), the same synthetic-fixed-input/boundary-covering shape this issue's own directive requires for graders
- Tests likely to break if a gate is added unconditionally inside `evaluate()`: `test_builtin_loops.py::test_route_results_key_dispatches_correctly`, `::test_run_test_key_dispatches_correctly`, `::test_run_test_skip_branch_emits_pass_rate`; `test_fsm_open_question_stall.py::test_dispatch_open_question_stall`, `::test_dispatch_defaults_to_run_dir_history`, `::test_dispatch_nonzero_exit_does_not_short_circuit`; `test_feat3033_idle_timeout.py::test_exit_124_still_routes_error_regardless_of_timeout_kind` — all call `evaluate()` directly for non-live-model or short-circuit evaluator types with no grader-test fixture set up; the gate must be scoped to skip these or they need new fixtures
- `scripts/tests/test_cli_harness.py::TestSampleLoopIntegration` — drives `cmd_skill()` → `_run_sample_loop` → `_grade()` end-to-end with the default exit-code grader and no grader-test fixture configured; a break-risk group if the gate applies to every `_grade()` call regardless of grader kind

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — auto-generated module reference for `evaluate()`/`evaluate_llm_structured()`; the `evaluate_llm_structured` doc block already carries an inline ENH-3462 precedent note, the pattern to follow for documenting a new gate
- `docs/reference/CLI.md` — "Shared evaluator flags" table (landing spot for a new gate flag), "Widened evidence surface (ENH-3462)" prose block (precedent for documenting `_grade()`-level behavior), and the Exit codes line (if the gate introduces a refusal code distinct from 1/2)
- `docs/guides/EVALUATION_GUIDE.md:96,547` and `docs/generalized-fsm-loop.md:546-549` — a verbatim-duplicated claim, "`passed` initializes to `True` and no check ever flips it (`_grade()`)," that a mandatory grader-test gate would falsify and must be corrected in both places
- `docs/generalized-fsm-loop.md` `## Testing Strategy` section — narrates an aspirational (non-matching) test-directory layout and a "Mock Strategy for LLM Evaluation" pointing at `TestLLMStructuredEvaluator`; has no existing mention of a grader-test presence/pass gate
- `skills/create-eval-from-issues/SKILL.md` (and its `.qwen/`/`.kimi-code/`/`.gemini/` host mirrors) — references `ll-harness` as a consumer of generated eval fixtures; a skill-body edit needs `ll-adapt --apply` mirror sync per project convention

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py` — `StateConfig.tamper_guard`/`.prepatch_check` (state-level) plus `FSMLoop.tamper_guard`/`.prepatch_check` + `*_ok` suppression flags (loop-level default) are the two-tier schema shape to extend if the gate is state-scoped; `EvaluateConfig` (same file) is the alternate home if the gate is grader-type-scoped instead — this choice must be made before adding a field
- `scripts/little_loops/fsm/fsm-loop-schema.json:368-386,608-613` — the JSON Schema mirror for `tamper_guard`/`prepatch_check`, needs a matching entry for whichever field is added

## Program Design

### Types

- `EvaluationResult`: `verdict: str`, `details: dict[str, Any]` (`scripts/little_loops/fsm/evaluators.py:56`)
- `HarnessEvalOutcome`: `passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult | None` (`scripts/little_loops/cli/harness.py:863`)

### Signatures

- `_grade(runner_label, result: RunnerResult, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`scripts/little_loops/cli/harness.py:1224`)
- `evaluate_llm_structured(output, prompt, model, max_output_chars=None) -> EvaluationResult` (`scripts/little_loops/fsm/evaluators.py:1067`)
- Sibling graders sharing the same `(output, ...) -> EvaluationResult` shape: `evaluate_exit_code`, `evaluate_output_numeric`, `evaluate_output_json`, `evaluate_output_contains`, `evaluate_classify`, `evaluate_harbor_scorer`, `evaluate_mcp_result`, `evaluate_blind_comparator`, `evaluate_contract` (all `scripts/little_loops/fsm/evaluators.py`) — none currently have deterministic unit tests over fixed synthetic inputs.

### Call Path

`_grade()` (`harness.py:1224`) -> `evaluate_llm_structured()` / other `evaluate_*` graders (`fsm/evaluators.py`) -> new deterministic unit-test suite exercising each `evaluate_*` function directly against fixed synthetic `(output, criteria)` fixtures, independent of `_grade()` and any live subject.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- All ten graders named in this issue's own Signatures list already have direct, zero-API-call unit tests exercising a clear pass and clear fail (mocked via a `mock_cli` fixture patching `subprocess.run` for the LLM-calling graders, per `test_fsm_evaluators.py:997-1005`; pure-function calls for the rest): `evaluate_exit_code` (`TestExitCodeEvaluator`, `test_fsm_evaluators.py:55`), `evaluate_output_numeric` (`TestOutputNumericEvaluator`, `:98`), `evaluate_output_json` (`TestOutputJsonEvaluator`, `:284`), `evaluate_output_contains` (`TestOutputContainsEvaluator`, `:358`), `evaluate_classify` (`TestClassifyEvaluator`, `:546`), `evaluate_llm_structured` (`TestLLMStructuredEvaluator`, `:976`), `evaluate_mcp_result` (`TestMcpResultEvaluator`, `:2194`), `evaluate_blind_comparator` (`TestBlindComparator`, `:2286`), `evaluate_contract` (`TestContractEvaluator`, `:2603`), and `evaluate_harbor_scorer` (`TestEvaluateHarborScorerVerdicts`, a separate file `test_benchmark_fragment.py:28`, not `test_fsm_evaluators.py`). This runs counter to this section's own "none currently have deterministic unit tests" line above.
- Two specific coverage gaps remain, confirmed by direct grep of the relevant test class: `evaluate_output_json` (`evaluators.py:324`) has no call site in `test_fsm_evaluators.py` asserting a `verdict == "no"` (fail) outcome or a value placed exactly at an `lt`/`gt`/`le`/`ge` threshold boundary — every existing call there asserts `"yes"` or `"error"` only. `evaluate_llm_structured` (`evaluators.py:1067`) has confidence-threshold tests only at a clearly-low confidence (`0.4` vs. `min_confidence=0.7`, `test_fsm_evaluators.py:1121,1131`), never at `confidence == min_confidence` exactly.
- No mechanism anywhere in `scripts/little_loops/` blocks a live-model probe from calling a grader whose tests are absent or failing — `_grade()` (`cli/harness.py:1224`) and the `evaluate()` dispatcher (`fsm/evaluators.py:1839`, a plain `if/elif` chain on `config.type`) invoke every grader unconditionally; a repo-wide search for gating terminology (`requires_test`, `grader_test`, `test_required`, a `--require-grader-tests`-style flag) returned zero hits. The closest existing conventions for "a check must pass before an action proceeds" are the FSM executor's state-scoped `tamper_guard`/`prepatch_check` policies (`fsm/executor.py:1601-2107`, `little_loops/prepatch_check.py`) and the learning-tests `release_gate` (`block`/`warn` policy, `learning_tests/gate.py`, `release_gate.py`) — neither is wired to an individual grader function's own test suite today.
- `_grade()` has no distinct handling for a grader that errors internally: an `EvaluationResult(verdict="error", ...)` (e.g. from `evaluators.py:1123`'s `BlockingJsonError` catch) is not in `is_abstention_verdict()`'s recognized set (`fsm/verdicts.py:25`, which only recognizes `cannot_judge`), so it falls through `_grade()`'s `elif eval_result.verdict != "yes": passed = False` (`harness.py:1311-1312`) and is indistinguishable from a legitimate semantic "no" in `_grade()`'s return value.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

1. `evaluate_output_json` (`fsm/evaluators.py:324`) has a test-covered fail case and a test-covered boundary case in `TestOutputJsonEvaluator` (`test_fsm_evaluators.py:284`) — today only `"yes"`/`"error"` outcomes are asserted there.
2. `evaluate_llm_structured` (`fsm/evaluators.py:1067`) has a test asserting the exact-boundary case `confidence == min_confidence` in `TestLLMStructuredEvaluator` (`test_fsm_evaluators.py:976`) — today the nearby cases only use a clearly-low confidence (`0.4` vs. `min_confidence=0.7`).
3. A grader with a deliberately inverted comparison is caught before any live run is dispatched: a check exists that a probe's configured grader has passing unit tests, wired into the path `_run_sample_loop()`/`_evaluate_and_report()` -> `_grade()` (`cli/harness.py:1224`) or into the `evaluate()` dispatcher (`fsm/evaluators.py:1839`) both share, and its refusal/warn behavior is itself test-covered.
4. `python -m pytest scripts/tests/test_fsm_evaluators.py scripts/tests/test_benchmark_fragment.py scripts/tests/test_cli_harness.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide the gate's schema home (`StateConfig` fields mirroring `tamper_guard`/`prepatch_check`, vs. an `EvaluateConfig` field) before writing `fsm/schema.py` and `fsm/fsm-loop-schema.json` changes
- Scope the gate to the live-model grading path, or explicitly handle `cli/loop/testing.py`'s direct `evaluate()` call and the ~29 loop YAMLs with `llm_structured`/`output_json`/`check_semantic` evaluate states, since an unscoped gate reaches every FSM loop run
- Update `test_builtin_loops.py`, `test_fsm_open_question_stall.py`, `test_feat3033_idle_timeout.py`, and `test_cli_harness.py::TestSampleLoopIntegration` if the gate is not scoped away from their non-live-model/default-grader call paths
- Reconcile `history_reader/harness.py:299-312` (`_rc_from_event`)'s parallel exit-code-banding reimplementation with any new gate behavior in `_grade()`
- Update `docs/reference/CLI.md`'s "Shared evaluator flags" table and Exit codes line, and correct the stale "no check ever flips `passed`" claim in `docs/guides/EVALUATION_GUIDE.md:96,547` and `docs/generalized-fsm-loop.md:546-549`
- Add a lint rule for the new field following `test_fsm_validation_evaluator_rules.py`'s `TestTamperGuardValidation`/`TestPrePatchCheckValidation` six-method shape, plus round-trip coverage following `test_fsm_schema.py:4842-4953`

## Impact

- **Priority**: P3 — grading bugs currently masquerade as ordinary model variance, which erodes trust in every verdict `ll-harness` produces; no live incident has yet been traced to this gap.
- **Effort**: Medium — requires enumerating existing graders, writing synthetic fixture cases per grader (clear pass, clear fail, threshold boundary), and wiring a check that blocks live dispatch when a grader's tests are absent or failing.
- **Risk**: Low — additive testing requirement; does not change grading behavior itself.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: deterministic unit tests for grading/scoring functions used by live-model probes, covering pass/fail/boundary cases; a check that these tests exist and pass before a grader is used against a live run.
- **Out of scope**: n-run redundancy for verdict counting (ENH-3415, shipped); score-splitting (what gets scored); information-isolation between builder/validator roles — per this issue's Design section, none of these test the grader's own code.

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-09-14T20:51:04 - `df520d06-750a-40b3-acb9-fb846e40ee7a.jsonl`
- `/ll:refine-issue` - 2026-09-14T20:30:28 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`

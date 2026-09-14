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
- ENH-3462
parent: EPIC-3475
epic: EPIC-3475
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Decision: the gate is a pytest meta-test, not a runtime check

The source pattern's "deterministic tier verifies the live tier" is a **CI-tier** discipline, not a per-probe runtime check. Per this repo's CI policy (`.claude/CLAUDE.md` § Testing & CI Policy: pure-Python gates are ordinary pytest tests), the gate is a single new test module — `scripts/tests/test_grader_coverage.py` — that:

1. Enumerates every `evaluate_*` function defined in `scripts/little_loops/fsm/evaluators.py` (17 today; see the inventory below).
2. Asserts each **in-scope grader** has, somewhere under `scripts/tests/`, a tagged test for every case kind its inventory row requires. Case kinds are declared with a `@pytest.mark.grader_case(<fn>, <kind>)` marker (registered in `scripts/pyproject.toml` `[tool.pytest.ini_options] markers`, alongside `integration`/`slow`/`conformance`/`no_parallel`), and the meta-test reads markers rather than parsing test names.
3. Fails with a message naming the grader and the missing case kind.

**Marker discovery is an AST scan, not session collection.** The meta-test walks `scripts/tests/*.py` with `ast` and extracts `pytest.mark.grader_case(...)` decorator arguments. It must *not* read `session.items` or use a `pytest_collection_modifyitems` hook: any subset run — `pytest scripts/tests/test_grader_coverage.py` alone, `-k`, `--lf`, or mutmut's per-mutant `-x -q -n0` selections — would then lack the tagged tests and fail the gate spuriously. The AST route is subset-proof and lets the meta-test's own negative tests feed a synthetic source string instead of mutating the real suite.

**Case-kind semantics.** `pass` and `fail` mean the grader's affirmative and negative routing outcomes, not literally `verdict == "yes"` / `"no"`: `evaluate_classify` returns the route token as its verdict, `evaluate_mcp_result` returns `tool_error`/`timeout`-style verdicts, and `evaluate_blind_comparator` returns a `dict` rather than an `EvaluationResult`. `boundary` is only meaningful where a numeric threshold exists, so the in-scope table declares required kinds per grader rather than demanding all three everywhere.

"Before any live run is dispatched" is satisfied because `python -m pytest scripts/tests/` is the merge gate for `main`, and every `local-editable` project on this machine runs `main` directly.

**Explicitly rejected**: a runtime gate that shells pytest from `_grade()` or the `evaluate()` dispatcher. It would re-run the suite once per live probe, reach every FSM loop run (the ~29 `llm_structured`/`output_json`/`check_semantic` loop YAMLs and `ll-loop test`), and require new `StateConfig`/JSON-schema fields plus a lint rule. All Wiring-Phase touchpoints below that only exist under the runtime-gate reading are struck.

### Grader inventory (`fsm/evaluators.py`)

**In scope** (grade a subject's output and return a routing verdict), with the case kinds each row requires:

| Grader | Line | Required kinds | Boundary means |
|---|---|---|---|
| `evaluate_output_numeric` | `:205` | pass, fail, boundary | value exactly at the `lt`/`gt`/`le`/`ge` threshold |
| `evaluate_output_json` | `:324` | pass, fail, boundary | extracted value exactly at the threshold |
| `evaluate_llm_structured` | `:1067` | pass, fail, boundary | `confidence == min_confidence` |
| `evaluate_exit_code` | `:176` | pass, fail | — |
| `evaluate_output_contains` | `:381` | pass, fail | — |
| `evaluate_classify` | `:523` | pass, fail | — |
| `evaluate_mcp_result` | `:968` | pass, fail | — |
| `evaluate_harbor_scorer` | `:1028` | pass, fail | — |
| `evaluate_blind_comparator` | `:1184` | pass, fail | — |
| `evaluate_contract` | `:1361` | pass, fail | — |
| `evaluate_comparator` | `:1636` | pass, fail | — |

The meta-test holds this table as its in-scope mapping (`{name: frozenset(kinds)}`), so adding a threshold to a grader later means adding `boundary` to its row.

**Exempt** (loop-control or advisory, not subject grading; verdicts are stall/continue signals rather than pass/fail): `evaluate_convergence` (`:438`), `evaluate_diff_stall` (`:577`), `evaluate_score_stall` (`:673`), `evaluate_open_question_stall` (`:756`), `evaluate_action_stall` (`:837`), `evaluate_advisor_consult` (`:1743`). The meta-test carries this exemption list explicitly so adding a new `evaluate_*` function without classifying it fails the test.

## Acceptance

1. `scripts/tests/test_grader_coverage.py` exists and passes on `main`.
2. Removing (or commenting out) every tagged test of a given kind for an in-scope grader makes the meta-test fail, naming the grader and the missing case kind. (A single removal need not trip it; graders may carry several tagged tests per kind.)
3. Adding a new `evaluate_*` function to `fsm/evaluators.py` without adding it to either the in-scope table or the exempt list makes the meta-test fail.
4. `TestOutputJsonEvaluator` gains a `verdict == "no"` case and a case with the value exactly at an `lt`/`gt`/`le`/`ge` threshold; `TestLLMStructuredEvaluator` gains a `confidence == min_confidence` exact-boundary case. Each is tagged with the `grader_case` marker.
5. The meta-test passes when invoked in isolation (`python -m pytest scripts/tests/test_grader_coverage.py`) and under `-k test_grader_coverage`, i.e. it does not depend on the rest of the suite being collected.
6. A deliberately inverted comparison in any in-scope grader (e.g. flipping `>=` to `<` in `evaluate_output_numeric`) fails at least one existing tagged fail-or-boundary test. Verified by running `mutmut` scoped to `fsm/evaluators.py` (the repo already carries `[tool.mutmut]` in `scripts/pyproject.toml`) and recording surviving mutants inside the eleven in-scope graders in the Resolution; a hand-inverted comparison is the fallback if mutmut is unavailable.
7. `python -m pytest scripts/tests/` passes.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for the two remaining test-coverage gaps and the missing dispatch gate.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- **New test file** — `scripts/tests/test_fsm_verdicts.py` tests `is_abstention_verdict()` directly; not previously listed among this issue's grader test files. It directly exercises the abstention-verdict machinery `_grade()`'s `elif eval_result.verdict != "yes": passed = False` branch depends on.
- **Two more "block-on-test-failure" precedents**, beyond the `tamper_guard`/`prepatch_check`/`release_gate` policies already cited above: `fleet_improve.gate()` (`fleet_improve.py:657-709`) shells `[sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *existing]` against two hardcoded test files and blocks on non-zero exit — but treats absent test files as a pass-through (not a block), only presence-then-failure trips it. This is the most literally on-point existing "run these test files, block if they fail" shape in the codebase, though scoped to built-in-loop YAML edits, not eval graders. `prepatch_check._run_pytest()`/`_parse_junit()` (`prepatch_check.py:279-363`) is a second, more granular precedent — shells pytest with `--junit-xml` and parses per-nodeid pass/fail/error/flaky — but its `_assign_flag` verdict polarity is inverted from what this issue needs: it flags a candidate test hard when it *passes* on the pre-patch worktree (proving nothing about a change), not when tests are absent or failing. No shared helper builds the `[..., "-m", "pytest", ...]` command list; both precedents construct it inline and independently — a new gate would be a third independent construction unless one is factored out.
- **Documentation citation discrepancy**: the existing citation `docs/generalized-fsm-loop.md:546-549` does not contain the "`passed` initializes to `True` and no check ever flips it" claim — that line range instead covers the `on_no`→`on_error` fallthrough rule and `cannot_judge` abstention documentation (BUG-3228/ENH-3185). The duplicated claim is confirmed only in `docs/guides/EVALUATION_GUIDE.md`, at both lines 95-97 and 546-549 within that single file. Before editing `generalized-fsm-loop.md` for this claim, its actual location (if any) needs re-locating; that file's `## Testing Strategy` section is confirmed real at line 1847.

### Files to Modify
- `scripts/tests/test_grader_coverage.py` — **new**; the meta-test described in Design. Enumerates `evaluate_*` in `fsm/evaluators.py` via `inspect`, AST-scans `scripts/tests/*.py` for `grader_case` marker decorators, and asserts per-grader required-kind coverage (from the in-scope table) plus classification of every function.
- `scripts/pyproject.toml` — add `grader_case` to `[tool.pytest.ini_options] markers` (`:281`) so `--strict-markers` (already in `addopts`) accepts it. Do not register via `conftest.py` `pytest_configure`; the repo registers all markers in pyproject.
- `scripts/tests/test_fsm_evaluators.py` — add the two missing cases: an `evaluate_output_json` fail-case and boundary-case (`TestOutputJsonEvaluator`, currently `test_fsm_evaluators.py:284-354`, only asserts `"yes"`/`"error"`), and an `evaluate_llm_structured` `confidence == min_confidence` exact-boundary case (`TestLLMStructuredEvaluator`, currently `test_fsm_evaluators.py:976-1798`, boundary tests only use a clearly-low confidence). Tag existing pass/fail/boundary tests for every in-scope grader with `grader_case`.
- `scripts/tests/test_benchmark_fragment.py` — tag `TestEvaluateHarborScorerVerdicts` (`:28-74`) cases with `grader_case`; it lives outside `test_fsm_evaluators.py`.

No production code changes. `cli/harness.py` and `fsm/evaluators.py` are untouched (see Design decision).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/evaluators.py` — read-only input to the meta-test's enumeration; any newly added `evaluate_*` function must be classified in-scope or exempt.
- `scripts/tests/test_fsm_evaluators.py`, `test_benchmark_fragment.py` — the only test modules that need marker tags; the nine other modules that import evaluator symbols (`test_fsm_executor.py`, `test_ll_loop_execution.py`, `test_builtin_loops.py`, etc.) are unaffected.

_Struck by review 2026-09-14 (runtime-gate reading rejected)_: `_grade()`/`evaluate()` call-site wiring, `cli/loop/testing.py`, `history_reader/harness.py:_rc_from_event` reconciliation, the ~29 loop-YAML blast radius, and the break-risk test lists.

### Conventions in Force
- Graders that would otherwise dispatch a live model call are tested by patching `subprocess.run` at the module level (`little_loops.fsm.evaluators.subprocess.run`) via a `mock_cli`/`_make_cli_response` fixture returning a canned CLI JSON envelope — evidence: `TestLLMStructuredEvaluator.mock_cli` (`test_fsm_evaluators.py:997-1005`), `TestBlindComparator` (`:2314`), `TestContractEvaluator` (`:2622`)
- Pure (non-LLM) graders get one `Test<EvaluatorName>Evaluator` class per function, methods named for the case (`_passes`/`_fails`, operator names), asserting both `result.verdict` and specific `result.details` keys — evidence: `TestExitCodeEvaluator` (`test_fsm_evaluators.py:55-98`, parametrized over exit-code→verdict tuples), `TestOutputNumericEvaluator` (`:98-227`, one `test_<op>_passes`/`test_<op>_fails` pair per operator)
- Repo-structure meta-tests that enumerate source artifacts and assert a coverage/companion invariant are the precedent for the gate shape — evidence: `scripts/tests/test_enh494_skill_companions.py` (SKILL.md line-limit + companion), `scripts/tests/test_policy_builder_node_gate.py` (external gate wrapped as pytest)

### Tests
- `scripts/tests/test_fsm_evaluators.py` — direct tests for 10 of the 11 in-scope graders (all but `evaluate_harbor_scorer`), including `TestComparatorEvaluator` (`:2464`) for `evaluate_comparator`
- `scripts/tests/test_benchmark_fragment.py` — `TestEvaluateHarborScorerVerdicts` (`:28-74`), the eleventh grader's direct tests, in a separate file from the rest
- `scripts/tests/test_cli_harness.py` — `TestGradeEvidenceChannels` (`:3682`) calls `_grade()` directly against synthetic `RunnerResult` fixtures with the LLM grader mocked at `little_loops.cli.harness.evaluate_llm_structured`; no existing test in this class exercises a deliberately-inverted grader or a test-presence/pass gate

- `scripts/tests/test_grader_coverage.py` — **new** meta-test (see Design). Its own tests: (a) all in-scope graders covered on `main`; (b) a synthetic test-source string with one required kind absent fails naming grader + kind; (c) an unclassified `evaluate_*` name fails; (d) the module passes when run in isolation (AC 5).
- `scripts/tests/test_learning_tests_version_staleness.py` — pure boundary-predicate pattern (`is_record_stale`), the same synthetic-fixed-input/boundary-covering shape this issue's directive requires for graders
- `scripts/tests/test_enh494_skill_companions.py` — precedent for a repo-invariant meta-test that enumerates source files and fails with a named offender

_Struck by review 2026-09-14 (runtime-gate reading rejected)_: the tamper_guard/prepatch_check lint, schema, and executor-hook precedents and the two break-risk test groups.

### Documentation

- `docs/generalized-fsm-loop.md` `## Testing Strategy` section (`:1847`) — add a short paragraph on the grader-coverage meta-test and the `grader_case` marker; this section already narrates the "Mock Strategy for LLM Evaluation" pointing at `TestLLMStructuredEvaluator`.
- `CONTRIBUTING.md` — one line: a new `evaluate_*` grader must be classified in `test_grader_coverage.py` and carry pass/fail/boundary `grader_case` tests.

**Not a doc correction**: the claim "`passed` initializes to `True` and no check ever flips it" at `docs/guides/EVALUATION_GUIDE.md:95-97,546-549` is about invoking `ll-harness` with neither `--exit-code` nor `--semantic`. It stays true under this issue and must not be edited. (An earlier wiring pass mis-cited `docs/generalized-fsm-loop.md:546-549` for the same claim; that range covers `on_blocked` routing and is unrelated.)

No `docs/reference/CLI.md` or `docs/reference/API.md` changes: no flag, exit code, or public signature is added.

### Configuration

None. No `fsm/schema.py` or `fsm-loop-schema.json` field is added (see Design decision).

## Program Design

### Types

- `EvaluationResult`: `verdict: str`, `details: dict[str, Any]` (`scripts/little_loops/fsm/evaluators.py:56`)
- `HarnessEvalOutcome`: `passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult | None` (`scripts/little_loops/cli/harness.py:863`)

### Signatures

- `_grade(runner_label, result: RunnerResult, args, *, expected_grade=None, side_effects=None) -> tuple[int, HarnessEvalOutcome]` (`scripts/little_loops/cli/harness.py:1224`)
- `evaluate_llm_structured(output, prompt, model, max_output_chars=None) -> EvaluationResult` (`scripts/little_loops/fsm/evaluators.py:1067`)
- Sibling in-scope graders: `evaluate_exit_code`, `evaluate_output_numeric`, `evaluate_output_json`, `evaluate_output_contains`, `evaluate_classify`, `evaluate_harbor_scorer`, `evaluate_mcp_result`, `evaluate_contract`, `evaluate_comparator` return `EvaluationResult`; `evaluate_blind_comparator` (`evaluators.py:1184`) returns `dict[str, Any]`, and `evaluate_contract`/`evaluate_comparator` take `(config: EvaluateConfig, ...)` rather than a bare `output`. The marker is agnostic to signature shape. All already have deterministic pass/fail unit tests (see findings below); the gaps are two missing fail/boundary cases and the absence of any invariant enforcing the coverage. Full 17-function inventory with exemptions is in Design.
- New marker: `@pytest.mark.grader_case(grader: str, kind: Literal["pass", "fail", "boundary"])` — registered in `scripts/pyproject.toml` `markers`.
- Meta-test discovery: `ast.parse` over each `scripts/tests/*.py`, matching `Call` decorators whose func resolves to `pytest.mark.grader_case`, yielding `(grader, kind)` string pairs. No pytest session state is consulted.

### Call Path

`python -m pytest scripts/tests/` -> `test_grader_coverage.py` collects `grader_case` markers from the session -> `inspect.getmembers(fsm.evaluators)` enumerates `evaluate_*` -> assert every in-scope grader has all three kinds and every function is classified. Production call path (`_grade()` `harness.py:1224` -> `evaluate_*`) is unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- All ten graders named in this issue's own Signatures list already have direct, zero-API-call unit tests exercising a clear pass and clear fail (mocked via a `mock_cli` fixture patching `subprocess.run` for the LLM-calling graders, per `test_fsm_evaluators.py:997-1005`; pure-function calls for the rest): `evaluate_exit_code` (`TestExitCodeEvaluator`, `test_fsm_evaluators.py:55`), `evaluate_output_numeric` (`TestOutputNumericEvaluator`, `:98`), `evaluate_output_json` (`TestOutputJsonEvaluator`, `:284`), `evaluate_output_contains` (`TestOutputContainsEvaluator`, `:358`), `evaluate_classify` (`TestClassifyEvaluator`, `:546`), `evaluate_llm_structured` (`TestLLMStructuredEvaluator`, `:976`), `evaluate_mcp_result` (`TestMcpResultEvaluator`, `:2194`), `evaluate_blind_comparator` (`TestBlindComparator`, `:2286`), `evaluate_contract` (`TestContractEvaluator`, `:2603`), and `evaluate_harbor_scorer` (`TestEvaluateHarborScorerVerdicts`, a separate file `test_benchmark_fragment.py:28`, not `test_fsm_evaluators.py`). This runs counter to this section's own "none currently have deterministic unit tests" line above.
- Two specific coverage gaps remain, confirmed by direct grep of the relevant test class: `evaluate_output_json` (`evaluators.py:324`) has no call site in `test_fsm_evaluators.py` asserting a `verdict == "no"` (fail) outcome or a value placed exactly at an `lt`/`gt`/`le`/`ge` threshold boundary — every existing call there asserts `"yes"` or `"error"` only. `evaluate_llm_structured` (`evaluators.py:1067`) has confidence-threshold tests only at a clearly-low confidence (`0.4` vs. `min_confidence=0.7`, `test_fsm_evaluators.py:1121,1131`), never at `confidence == min_confidence` exactly.
- No mechanism anywhere in `scripts/little_loops/` blocks a live-model probe from calling a grader whose tests are absent or failing — `_grade()` (`cli/harness.py:1224`) and the `evaluate()` dispatcher (`fsm/evaluators.py:1839`, a plain `if/elif` chain on `config.type`) invoke every grader unconditionally; a repo-wide search for gating terminology (`requires_test`, `grader_test`, `test_required`, a `--require-grader-tests`-style flag) returned zero hits. The closest existing conventions for "a check must pass before an action proceeds" are the FSM executor's state-scoped `tamper_guard`/`prepatch_check` policies (`fsm/executor.py:1601-2107`, `little_loops/prepatch_check.py`) and the learning-tests `release_gate` (`block`/`warn` policy, `learning_tests/gate.py`, `release_gate.py`) — neither is wired to an individual grader function's own test suite today.
- `_grade()` has no distinct handling for a grader that errors internally: an `EvaluationResult(verdict="error", ...)` (e.g. from `evaluators.py:1123`'s `BlockingJsonError` catch) is not in `is_abstention_verdict()`'s recognized set (`fsm/verdicts.py:25`, which only recognizes `cannot_judge`), so it falls through `_grade()`'s `elif eval_result.verdict != "yes": passed = False` (`harness.py:1311-1312`) and is indistinguishable from a legitimate semantic "no" in `_grade()`'s return value. **Spun out as BUG-3477** — it changes grading behavior, which this issue's Impact section excludes. Not in scope here.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- No evaluator type in `evaluate()`'s dispatch chain (14 branches in `fsm/evaluators.py`: `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `score_stall`, `open_question_stall`, `action_stall`, `llm_structured`, `mcp_result`, `harbor_scorer`, `comparator`, `contract`, `classify`, plus `advisor_consult`) currently checks grader-test status; no `unit_test`/`check_grader`-style evaluator type is present in the chain.
- `history_reader.runs.recent_test_runs()` (`history_reader/runs.py:40`) is the one existing "was the suite green" query, fed by `pytest_history_plugin.py`'s `LLHistoryPlugin` on `pytest_sessionfinish`, but only at whole-suite grain filtered by `branch`/`head_sha` — no per-file/per-nodeid query exists. Answering "did grader X's own tests pass" would require either post-filtering that query's `failing_names_json` for absence of any nodeid under the grader's test file, or invoking a fresh, targeted pytest subprocess (per the `prepatch_check._run_pytest`/`fleet_improve.gate` precedents in Integration Map above).
- Both existing `evaluate_llm_structured()` call paths — `_grade()` (`harness.py:1298`/`:1302`) and `evaluate()`'s `llm_structured` branch (`evaluators.py:2051-2058`) — converge on the same function and are each unconditional today; confirmed current by direct trace.

## Implementation Steps

1. `evaluate_output_json` (`fsm/evaluators.py:324`) has a test-covered fail case and a test-covered boundary case in `TestOutputJsonEvaluator` (`test_fsm_evaluators.py:284`) — today only `"yes"`/`"error"` outcomes are asserted there.
2. `evaluate_llm_structured` (`fsm/evaluators.py:1067`) has a test asserting the exact-boundary case `confidence == min_confidence` in `TestLLMStructuredEvaluator` (`test_fsm_evaluators.py:976`) — today the nearby cases only use a clearly-low confidence (`0.4` vs. `min_confidence=0.7`).
3. `scripts/pyproject.toml` `markers` gains `grader_case(grader, kind)`; every existing pass/fail/boundary test for the eleven in-scope graders in `test_fsm_evaluators.py` and `test_benchmark_fragment.py` is tagged per the required-kinds table in Design.
4. `scripts/tests/test_grader_coverage.py` exists: enumerates `evaluate_*` from `fsm/evaluators.py`, holds the in-scope required-kinds table and the exempt list from Design, AST-scans `scripts/tests/*.py` for `grader_case` decorators (never `session.items` or a collection hook), and fails naming the grader and missing kind. Its own negative tests (missing kind, unclassified function) run against a synthetic source string, not by mutating the real suite. Confirm it passes when run in isolation (AC 5).
5. Verify AC 6: run `mutmut run` scoped to `little_loops/fsm/evaluators.py` from `scripts/`, list survivors inside in-scope graders, record in Resolution. Fallback: hand-invert one comparison in `evaluate_output_numeric`, confirm a tagged test fails, revert.
6. Add the `## Testing Strategy` paragraph in `docs/generalized-fsm-loop.md` and the `CONTRIBUTING.md` line.
7. `python -m pytest scripts/tests/` passes.

### Wiring Phase

_Reviewed 2026-09-14: all six original wire-issue touchpoints (schema home, dispatcher scoping, break-risk test updates, `_rc_from_event` reconciliation, CLI.md/EVALUATION_GUIDE.md corrections, lint rule) were artifacts of the rejected runtime-gate reading and are struck. See Design § Decision._

## Impact

- **Priority**: P3 — grading bugs currently masquerade as ordinary model variance, which erodes trust in every verdict `ll-harness` produces; no live incident has yet been traced to this gap.
- **Effort**: Low — one new meta-test module, a marker registration, tagging ~11 existing test classes, two new test cases, two doc lines. No production code.
- **Risk**: Low — test-only change; does not change grading behavior itself.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: deterministic unit tests for grading/scoring functions used by live-model probes, covering pass/fail/boundary cases; a **CI-tier** meta-test that enforces this coverage on every `python -m pytest scripts/tests/` run.
- **Out of scope**: a runtime gate in `_grade()`/`evaluate()` (rejected, see Design); `_grade()` conflating `verdict="error"` with a semantic `"no"` (BUG-3477); n-run redundancy for verdict counting (ENH-3415, shipped); score-splitting (what gets scored); information-isolation between builder/validator roles — per this issue's Design section, none of these test the grader's own code.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-14:_

Verdict: **VALID**. Spot-checked every concrete claim in Integration Map, Program
Design, and Implementation Steps against current code (graph provider `codegraph`,
freshness `fresh`):

- Types/signatures (`EvaluationResult` `evaluators.py:56`, `HarnessEvalOutcome`
  `harness.py:863`, `_grade()` `harness.py:1224`, `evaluate_llm_structured()`
  `evaluators.py:1067`, `evaluate()` dispatcher `evaluators.py:1839`) all match.
- Both documented coverage gaps confirmed live: `TestOutputJsonEvaluator`
  (`test_fsm_evaluators.py:284-354`) asserts only `"yes"`/`"error"`, no `"no"` or
  boundary case; `TestLLMStructuredEvaluator` (`:976-1798`) has no
  `confidence == min_confidence` (0.7) exact-boundary case, only 0.4-vs-0.7.
- The documentation-citation-discrepancy note is accurate:
  `docs/generalized-fsm-loop.md:546-549` covers `on_blocked` routing, not the
  "`passed` initializes to `True`" claim, which is confirmed at
  `docs/guides/EVALUATION_GUIDE.md:95-97,546-549`.
- Negative claim corroborated: no `requires_test`/`grader_test`/`test_required`/
  `--require-grader-tests` hits anywhere under `scripts/little_loops/`.
- `## Proposed Solution` is absent, so check B6 (`PROPOSAL_UNSOUND`) does not apply.
- No active required decision-log rules to check against.
- `ll-verify-evidence --json` reports clean (0 findings).

Dependency hygiene: `blocked_by: ENH-3462` is satisfied (ENH-3462 is `done`); the
`## Blocks` backlink on ENH-3462 was added 2026-09-14.

_Review 2026-09-14 (manual, second pass):_ switched marker discovery from
session collection to an AST scan (subset runs, `--lf`, and mutmut's `-n0`
selections would otherwise fail the gate spuriously); replaced the blanket
pass/fail/boundary requirement with a per-grader required-kinds table (only
three graders have a numeric threshold; `classify`, `mcp_result`, and
`blind_comparator` do not return `"yes"`/`"no"`); moved marker registration to
`pyproject.toml` per repo convention; reworded AC 2 to "every tagged test of a
kind"; made the inverted-comparison check durable via the existing `[tool.mutmut]`
config; fixed the "9 of 10" count and the `-> EvaluationResult` shape claim.

_Review 2026-09-14 (manual):_ replaced the runtime-gate reading with a pytest
meta-test decision, corrected the false "none have unit tests" line, dropped the
mistaken EVALUATION_GUIDE.md correction, completed the 17-function grader inventory
with an explicit exemption list, rewrote Acceptance as six testable criteria, and
spun the `verdict="error"` conflation out as BUG-3477.

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-09-14T21:57:28 - `76fd614d-af9c-461c-9480-143acb792f32.jsonl`
- `/ll:verify-issues` - 2026-09-14T21:55:28 - `38ae2e66-1c37-4dba-9a6d-42c3e2738df2.jsonl`
- `/ll:confidence-check` - 2026-09-14T21:49:02 - `213a0053-67dd-4147-8bdb-b54b20072e38.jsonl`
- `/ll:verify-issues` - 2026-09-14T21:46:46 - `d75e579c-77cd-483a-b66a-e89390b5429b.jsonl`
- `/ll:verify-issues` - 2026-09-14T21:32:26 - `f4a1cb05-beaf-4c89-a67b-0a34555443d6.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:14:10 - `db66d56e-7abb-4271-a047-637a95835ae4.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:51:04 - `df520d06-750a-40b3-acb9-fb846e40ee7a.jsonl`
- `/ll:refine-issue` - 2026-09-14T20:30:28 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`

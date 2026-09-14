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

### Decision: the gate is a pytest meta-test, not a runtime check

The source pattern's "deterministic tier verifies the live tier" is a **CI-tier** discipline, not a per-probe runtime check. Per this repo's CI policy (`.claude/CLAUDE.md` § Testing & CI Policy: pure-Python gates are ordinary pytest tests), the gate is a single new test module — `scripts/tests/test_grader_coverage.py` — that:

1. Enumerates every `evaluate_*` function defined in `scripts/little_loops/fsm/evaluators.py` (17 today; see the inventory below).
2. Asserts each **in-scope grader** has, somewhere under `scripts/tests/`, a test that exercises a clear pass (`verdict == "yes"`), a clear fail (`verdict == "no"`), and a threshold boundary. Case kinds are declared with a `@pytest.mark.grader_case(<fn>, <kind>)` marker (registered in `conftest.py`), and the meta-test collects markers rather than parsing names.
3. Fails with a message naming the grader and the missing case kind.

"Before any live run is dispatched" is satisfied because `python -m pytest scripts/tests/` is the merge gate for `main`, and every `local-editable` project on this machine runs `main` directly.

**Explicitly rejected**: a runtime gate that shells pytest from `_grade()` or the `evaluate()` dispatcher. It would re-run the suite once per live probe, reach every FSM loop run (the ~29 `llm_structured`/`output_json`/`check_semantic` loop YAMLs and `ll-loop test`), and require new `StateConfig`/JSON-schema fields plus a lint rule. All Wiring-Phase touchpoints below that only exist under the runtime-gate reading are struck.

### Grader inventory (`fsm/evaluators.py`)

**In scope** (grade a subject's output and return a pass/fail verdict): `evaluate_exit_code` (`:176`), `evaluate_output_numeric` (`:205`), `evaluate_output_json` (`:324`), `evaluate_output_contains` (`:381`), `evaluate_classify` (`:523`), `evaluate_mcp_result` (`:968`), `evaluate_harbor_scorer` (`:1028`), `evaluate_llm_structured` (`:1067`), `evaluate_blind_comparator` (`:1184`), `evaluate_contract` (`:1361`), `evaluate_comparator` (`:1636`).

**Exempt** (loop-control or advisory, not subject grading; verdicts are stall/continue signals rather than pass/fail): `evaluate_convergence` (`:438`), `evaluate_diff_stall` (`:577`), `evaluate_score_stall` (`:673`), `evaluate_open_question_stall` (`:756`), `evaluate_action_stall` (`:837`), `evaluate_advisor_consult` (`:1743`). The meta-test carries this exemption list explicitly so adding a new `evaluate_*` function without classifying it fails the test.

## Acceptance

1. `scripts/tests/test_grader_coverage.py` exists and passes on `main`.
2. Removing (or commenting out) any one pass, fail, or boundary test for an in-scope grader makes the meta-test fail, naming the grader and the missing case kind.
3. Adding a new `evaluate_*` function to `fsm/evaluators.py` without adding it to either the in-scope or exempt list makes the meta-test fail.
4. `TestOutputJsonEvaluator` gains a `verdict == "no"` case and a case with the value exactly at an `lt`/`gt`/`le`/`ge` threshold; `TestLLMStructuredEvaluator` gains a `confidence == min_confidence` exact-boundary case. Each is tagged with the `grader_case` marker.
5. A deliberately inverted comparison in any in-scope grader (e.g. flipping `>=` to `<` in `evaluate_output_numeric`) fails at least one existing tagged fail-or-boundary test. Verified once by hand during implementation and recorded in the Resolution.
6. `python -m pytest scripts/tests/` passes.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for the two remaining test-coverage gaps and the missing dispatch gate.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- **New test file** — `scripts/tests/test_fsm_verdicts.py` tests `is_abstention_verdict()` directly; not previously listed among this issue's grader test files. It directly exercises the abstention-verdict machinery `_grade()`'s `elif eval_result.verdict != "yes": passed = False` branch depends on.
- **Two more "block-on-test-failure" precedents**, beyond the `tamper_guard`/`prepatch_check`/`release_gate` policies already cited above: `fleet_improve.gate()` (`fleet_improve.py:657-709`) shells `[sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *existing]` against two hardcoded test files and blocks on non-zero exit — but treats absent test files as a pass-through (not a block), only presence-then-failure trips it. This is the most literally on-point existing "run these test files, block if they fail" shape in the codebase, though scoped to built-in-loop YAML edits, not eval graders. `prepatch_check._run_pytest()`/`_parse_junit()` (`prepatch_check.py:279-363`) is a second, more granular precedent — shells pytest with `--junit-xml` and parses per-nodeid pass/fail/error/flaky — but its `_assign_flag` verdict polarity is inverted from what this issue needs: it flags a candidate test hard when it *passes* on the pre-patch worktree (proving nothing about a change), not when tests are absent or failing. No shared helper builds the `[..., "-m", "pytest", ...]` command list; both precedents construct it inline and independently — a new gate would be a third independent construction unless one is factored out.
- **Documentation citation discrepancy**: the existing citation `docs/generalized-fsm-loop.md:546-549` does not contain the "`passed` initializes to `True` and no check ever flips it" claim — that line range instead covers the `on_no`→`on_error` fallthrough rule and `cannot_judge` abstention documentation (BUG-3228/ENH-3185). The duplicated claim is confirmed only in `docs/guides/EVALUATION_GUIDE.md`, at both lines 95-97 and 546-549 within that single file. Before editing `generalized-fsm-loop.md` for this claim, its actual location (if any) needs re-locating; that file's `## Testing Strategy` section is confirmed real at line 1847.

### Files to Modify
- `scripts/tests/test_grader_coverage.py` — **new**; the meta-test described in Design. Enumerates `evaluate_*` in `fsm/evaluators.py` via `inspect`, collects `grader_case` markers from the collected test session, and asserts pass/fail/boundary coverage per in-scope grader plus classification of every function.
- `scripts/tests/conftest.py` — register the `grader_case` marker (`pytest_configure` → `config.addinivalue_line("markers", ...)`) so `--strict-markers` runs stay clean.
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
- `scripts/tests/test_fsm_evaluators.py` — direct tests for 9 of the 10 named graders (all but `evaluate_harbor_scorer`)
- `scripts/tests/test_benchmark_fragment.py` — `TestEvaluateHarborScorerVerdicts` (`:28-74`), the tenth grader's direct tests, in a separate file from the rest
- `scripts/tests/test_cli_harness.py` — `TestGradeEvidenceChannels` (`:3682`) calls `_grade()` directly against synthetic `RunnerResult` fixtures with the LLM grader mocked at `little_loops.cli.harness.evaluate_llm_structured`; no existing test in this class exercises a deliberately-inverted grader or a test-presence/pass gate

- `scripts/tests/test_grader_coverage.py` — **new** meta-test (see Design). Its own tests: (a) all in-scope graders covered on `main`; (b) a synthetic session with one marker removed fails naming grader + kind; (c) an unclassified `evaluate_*` name fails.
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
- Sibling in-scope graders sharing the same `(output, ...) -> EvaluationResult` shape: `evaluate_exit_code`, `evaluate_output_numeric`, `evaluate_output_json`, `evaluate_output_contains`, `evaluate_classify`, `evaluate_harbor_scorer`, `evaluate_mcp_result`, `evaluate_blind_comparator`, `evaluate_contract`, `evaluate_comparator` (all `scripts/little_loops/fsm/evaluators.py`). All already have deterministic pass/fail unit tests (see findings below); the gaps are two missing fail/boundary cases and the absence of any invariant enforcing the coverage. Full 17-function inventory with exemptions is in Design.
- New marker: `@pytest.mark.grader_case(grader: str, kind: Literal["pass", "fail", "boundary"])` — registered in `scripts/tests/conftest.py`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

1. `evaluate_output_json` (`fsm/evaluators.py:324`) has a test-covered fail case and a test-covered boundary case in `TestOutputJsonEvaluator` (`test_fsm_evaluators.py:284`) — today only `"yes"`/`"error"` outcomes are asserted there.
2. `evaluate_llm_structured` (`fsm/evaluators.py:1067`) has a test asserting the exact-boundary case `confidence == min_confidence` in `TestLLMStructuredEvaluator` (`test_fsm_evaluators.py:976`) — today the nearby cases only use a clearly-low confidence (`0.4` vs. `min_confidence=0.7`).
3. `scripts/tests/conftest.py` registers a `grader_case(grader, kind)` marker; every existing pass/fail/boundary test for the eleven in-scope graders in `test_fsm_evaluators.py` and `test_benchmark_fragment.py` is tagged.
4. `scripts/tests/test_grader_coverage.py` exists: enumerates `evaluate_*` from `fsm/evaluators.py`, holds the explicit in-scope and exempt lists from Design, collects `grader_case` markers from the session (a session-scoped fixture or `pytest_collection_modifyitems` hook in `conftest.py`), and fails naming the grader and missing kind. Its own negative tests (missing kind, unclassified function) run against a synthetic marker set, not by mutating the real suite.
5. Hand-verify AC 5 once: invert one comparison in `evaluate_output_numeric`, confirm a tagged test fails, revert, record in Resolution.
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

_Review 2026-09-14 (manual):_ replaced the runtime-gate reading with a pytest
meta-test decision, corrected the false "none have unit tests" line, dropped the
mistaken EVALUATION_GUIDE.md correction, completed the 17-function grader inventory
with an explicit exemption list, rewrote Acceptance as six testable criteria, and
spun the `verdict="error"` conflation out as BUG-3477.

## Status

**Open** | Created: 2026-09-13 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-09-14T21:46:46 - `d75e579c-77cd-483a-b66a-e89390b5429b.jsonl`
- `/ll:verify-issues` - 2026-09-14T21:32:26 - `f4a1cb05-beaf-4c89-a67b-0a34555443d6.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:14:10 - `db66d56e-7abb-4271-a047-637a95835ae4.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:51:04 - `df520d06-750a-40b3-acb9-fb846e40ee7a.jsonl`
- `/ll:refine-issue` - 2026-09-14T20:30:28 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`

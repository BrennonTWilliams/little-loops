---
id: BUG-3489
parent: EPIC-3493
epic: EPIC-3493
type: BUG
title: 'Policy-router runtime: stale LLM scores across passes and decision-table dispatch
  errors route to a success outcome'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:14:21Z'
labels:
- policy-builder
- BUG-3486
relates_to:
- BUG-3486
- BUG-3490
- FEAT-3474
- FEAT-3488
confidence_score: 90
outcome_confidence: 73
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3489: Policy-router runtime: stale LLM scores across passes and decision-table dispatch errors route to a success outcome

## Summary

Fix the connected runtime defects: stale per-dimension score files survive a second LLM scoring pass; scoring/dispatch failures can reach a user outcome because dispatch swallows artifact-read errors and the generated chain lacks complete failure routing; and `FSMExecutor._route()` resolves the normal `_` fallback before `_error`, so an `_error` sentinel is dead whenever `_` is declared. The executor precedence is fixed here (the `error` verdict consults `route.error` before `route.default`), which restores `_error`'s documented meaning for every route table rather than working around it per loop.

Split from BUG-3486 (2026-09-16 whole-builder review, defects f and g). Separate from catalog discovery in BUG-3490; coordinate serializer guards and reserved names with BUG-3486, which lands after this issue.

## Current Behavior

- The `policy_parse_scores` fragment (`scripts/little_loops/loops/lib/policy-router.yaml`, ~lines 84-116) writes `rubric-dim-<name>.txt` only for `DIMENSION:` lines present in the current pass and never deletes pre-existing files. `policy_table_dispatch` (same file, ~197-208) then reads every `rubric-dim-*.txt` via `os.listdir(run_dir)`. Running the fragment twice in one run dir, omitting a dimension on pass two, leaves the pass-one score in play. A previous `citations` score of 100 survives a second pass that emitted no citations line. The deterministic `frontmatter_scores` scorer already clears stale files via `_clean_slate()` (`scripts/little_loops/fsm/frontmatter_scores.py:158-169`).
- `_serializeDecisionTable()` (`scripts/little_loops/templates/policy_builder_core.mjs` ~800-804) sets `errorState = tokens[0] || fallbackState`, where `tokens[0]` is whichever outcome the first authored rule targets. No dedicated failure terminal is emitted for decision-table mode, so a dispatch or scoring failure can report successful completion. `_serializeIssueLifecycle()` (mjs ~974-1041) already emits an explicit `failed:` terminal and routes `_error: failed`.
- `FSMExecutor._route()` (`scripts/little_loops/fsm/executor.py` ~3323-3339) checks explicit verdict routes, then `route.default`, then `route.error`. With a route table present, ordinary verdict routing does not fall through to the state's `on_error`. A review probe with `_: accept`, `_error: failed`, and `on_error: failed` still routed the `error` verdict to `accept`. This contradicts `RouteConfig`'s own docstring (`schema.py` ~282-295: `error` is the "State for evaluation/execution errors") and the `policy-router.yaml` header that documents `_error` as the error fallback. The precedence order is the defect; `_error` is meant to catch the `error` verdict regardless of `_`.
- The shipped-loop audit found four classify states declaring both sentinels (by parsing `scripts/little_loops/loops/**/*.yaml` route tables; this does not bound effects on generated or consumer-authored loops): `rn-remediate.yaml` `diagnose` (~416-417) and `oracles/code-run-gate.yaml` `aggregate` (~478-479) point `_` and `_error` at the same target, so their behavior does not change; `policy-refine.yaml` `policy_dispatch` is fixed here anyway; `rn-remediate.yaml` `check_convergence` (~857-859) declares `_: check_remediation_budget` and `_error: gate_implement` with a comment saying a nonzero exit should fail open to `gate_implement`, so it is a live misroute today that the precedence fix corrects to the author's stated intent.
- Generated `score` and `parse_scores` states have unconditional `next` and no `on_error`; positive nonzero action exits can therefore advance into parsing or dispatch. The parser also exits successfully with no parsed dimensions and defaults missing aggregate to `0`. Aggregate is already overwritten on successful parses; stale dimensions are the existing successful-pass evidence leak.
- The stale-score leak is live in a shipped loop, not just a fragment-level hypothetical: `scripts/little_loops/loops/policy-refine.yaml` routes `light_repair` (line 75) and `deep_repair` (line 83) back to `score` via `next: score`, so pass two re-parses into a run dir still holding pass-one `rubric-dim-*.txt`. (`rethink`, line 91, routes `next: done` and is not part of this reproduction.) The same loop's dispatch declares `_: deep_repair` and `_error: done`, the identical success-misroute shape as the generated decision table.
- `_serializeIssueLifecycle()` has the same unreachable-sentinel defect: it emits `_: <fallback>` plus `_error: failed`, so with `_` present its `_error` never fires from `_route()`. It emits `on_error: failed` on scoring and verb states, but **not on `policy_dispatch`**. `policy-refine.yaml` also lacks dispatch `on_error`. Action-runner exceptions therefore bypass the intended failure terminal even after the precedence fix; `_error` and `on_error` cover distinct execution paths. The abstention-hold fallback (`_abstention_fallback`) is a separate consumer of `route.error`, not the dispatch failure path.
- The `policy-router.yaml` header advertises `_error` as an "optional error fallback" on the same state whose contract says `_` is required. Under current precedence that documented pattern is dead by construction; after the precedence fix it becomes correct as written.
- `_serializeDecisionTable()` has no guard against an authored outcome named `score`, `parse_scores`, or `policy_dispatch`: such a token emits a duplicate state key alongside the pipeline state of the same name. Only `done` is dodged today (`_doneStateName()`).
- `policy_table_dispatch` catches `FileNotFoundError` around the entire dimension-reading loop and then evaluates rules using an incomplete score mapping. A real interpolated-fragment probe with a dangling `rubric-dim-security.txt` symlink and rules `security:<65 -> repair` / `* -> accept` printed a misleading "run_dir not found" diagnostic, exited 0, emitted `accept`, and wrote `policy-action.txt`. Error routes cannot catch a read failure swallowed upstream.
- Authored `_` / `_error` tokens collide with generated route sentinels; more generally, `RouteConfig.from_dict()` removes every underscore-prefixed key from explicit verdict routes. BUG-3486 currently specifies a different reserved-name export and completion-name strategy from this issue; implementation needs the shared ownership contract below.
- The fragment header says callers may write `rubric-dim-*.txt` from a deterministic shell scorer alongside the LLM path, but nothing states that a clean-slate scorer wipes those files. `frontmatter_scores` already imposes this implicitly.

## Expected Behavior

Fresh scoring cannot use previous-pass evidence: every `policy_parse_scores` pass clears `rubric-dim-*.txt` and `rubric-aggregate.txt` before reading/parsing its input and publishing new scores. Other run artifacts survive. Recognized partial scoring remains valid under the contract below; wholly unparseable output fails. An omitted `AGGREGATE:` line produces no aggregate file, exactly as an omitted dimension produces no dimension file: routing never sees a score the scorer did not emit. `FSMExecutor._route()` resolves an `error` verdict against `route.error` (`_error`) before `route.default` (`_`), so `_error` means what the schema says it means whether or not `_` is declared; an explicit `error:` key still wins over both. Generated decision-table **and issue-lifecycle** loops route ordinary scoring/parsing action failures, dispatch nonzero exits/timeouts, and routable action-runner exceptions to an explicit failure terminal via `_error: failed` plus `on_error: failed`, without executing user outcome actions, even when the normal fallback is a success outcome. The shipped `policy-refine.yaml` receives the same failure routing, and `rn-remediate.yaml`'s `check_convergence` starts failing open to `gate_implement` as its comment intends. A single clean-slate scorer owns the score files per pass. An omitted dimension remains valid partial evidence; failure to enumerate the score directory or read a discovered artifact aborts dispatch before rule evaluation or publication of a new winning action. Deliberate executor aborts, including heredoc-collision protection, preserve their existing termination path and must not execute user outcome actions; they need not reach `failed`.

## Motivation

Users cannot trust routing decisions when evidence leaks between passes or when a failure lands on a success state. These runtime fixes unblock BUG-3486's subsequent builder work; the builder persistence work (ENH-3487) does not touch the runtime and is not blocked by this issue. FEAT-3488 currently treats BUG-3489 as related only; this issue does not establish a direct execution-handoff dependency.

## Proposed Solution

- **Fix executor precedence (root cause of the dead sentinel):** in `FSMExecutor._route()`, when a route table is present, resolve `verdict == "error"` against `state.route.error` **before** `state.route.default`. Explicit `routes[verdict]` entries and the `_uncertain` base-verdict fallback keep their current priority above both. Leave the `verdict == "no"` -> `route.error` shorthand and `_abstention_fallback` where they are. Update the `_route()` docstring's resolution-order list and any design doc it cites. Regression coverage: `_: accept`, `_error: failed`, verdict `error` -> `failed`; verdict `unknown` -> `accept`; explicit `error: retry` with `_error: failed` -> `retry`; `error_uncertain` with no explicit route resolves via the `error` base to `_error`; a table with `_` and no `_error` still sends `error` to `_`. This replaces the lint originally proposed here: a lint that flags `_`+`_error` would fire on every generated fixture and on the two harmless shipped states, and the lint's premise (that `_error` is unreachable by design) is wrong per the schema docstring.
- Extract the parser into a small importable module with pure `parse_scores()` and a file-writing entry point. Clear only `rubric-dim-*.txt` and `rubric-aggregate.txt` in `${context.run_dir}` before reading/parsing the new input. Preserve existing normalization and score text output. Cleanup/read/write failures must propagate as nonzero exits; dispatch must not consume any partial publication. The sequential state chain and failure routes make a transactional artifact framework unnecessary.
- **Dispatch read failures must propagate:** remove the broad `FileNotFoundError` recovery around dimension enumeration/reads. A dimension absent from the directory listing is valid missing evidence; a discovered file that cannot be read is an I/O failure, including disappearance between listing and opening or a dangling symlink. Directory-enumeration failures also propagate. Keep an omitted aggregate valid, but do not swallow failures when opening a discovered aggregate artifact. Complete score loading before evaluating rules or publishing a new `policy-action.txt`; propagate read and action-file write failures as nonzero exits with useful diagnostics. No cleanup or transaction framework is required for old `policy-action.txt`: routing consumes current stdout only, and callers must honor the failing exit status. Add a real interpolated-fragment regression with a broken dimension artifact and a success catch-all, rather than only mocking dispatch to return nonzero.
- **Scorer exclusivity contract:** state in the fragment header and `POLICY_ROUTER_GUIDE.md` that exactly one clean-slate scorer (`policy_parse_scores` or `frontmatter_scores`) owns `rubric-dim-*.txt` / `rubric-aggregate.txt` per pass; a caller that mixes a deterministic shell scorer with either fragment in the same pass loses whichever wrote first. This is documentation only; `frontmatter_scores` already behaves this way.
- **Scoring contract:** at least one recognized `DIMENSION` or `AGGREGATE` value is required. Empty output or output with neither raises a parse error and produces a nonzero exit. Partial output remains valid: omitted dimensions stay absent, aggregate-only output is valid, and **missing aggregate with recognized dimensions writes no `rubric-aggregate.txt`** (decision below). Preserve current recognition/normalization rules; broader score-range and format validation is outside this fix. Preserve `policy_rules` semantics: an absent dimension matches `!=`, other comparisons do not match, and catch-all rules still match. Missing evidence is not automatically a pipeline failure.
- **Decision — absent aggregate is absent, not `0`:** the current `agg = 0` default fabricates evidence of the same class this issue removes. A pass that omits the `AGGREGATE:` line would otherwise satisfy `aggregate:<65 -> escalate` on a score the scorer never produced. `policy_table_dispatch` already tolerates a missing `rubric-aggregate.txt` (`os.path.exists` guard), and the missing-dimension `!=` rule already defines the semantics for absent keys, so absent-aggregate semantics need no rule-evaluation change; dispatch I/O failure handling is tightened separately as described above. This is a deliberate behavior change from the current fragment, called out under Breaking Change. `lib/rubric-router.yaml`'s separate aggregate-only parser is untouched.
- Emit `failed: {terminal: true, failure: true}` in `_serializeDecisionTable()`. Set `on_error: failed` on `score`, `parse_scores`, and `policy_dispatch`. In the dispatch route table emit `_error: failed` (replacing the current `tokens[0]` target), retaining `_` for ordinary unmatched verdicts. With the precedence fix, `_error` handles nonzero exits/timeouts converted to evaluator `error` verdicts; no duplicate explicit `error:` key is emitted. Dispatch `on_error` handles routable action-runner exceptions through `_run_action_or_route`; negative signal exit codes on the classify path become evaluator `error` verdicts. Preserve explicit executor aborts such as `HeredocCollisionError`, which intentionally bypass `on_error` and terminate at the top-level handler. The invariant for these aborts is no user outcome action, not `failure_terminal == true`.
- **Lifecycle mode:** `_serializeIssueLifecycle()` already emits `failed:`, `_error: failed`, and `on_error: failed` on scoring/verb states, but not on dispatch. Add dispatch `on_error: failed` and mark the existing `failed` terminal with `failure: true`, alongside the shared serializer guard below. The executor precedence fix handles error verdicts; the added `on_error` handles routable action-runner exceptions. Test both paths with a success fallback. Lifecycle outcome-action semantics beyond dispatch routing remain out of scope.
- **Fix the shipped callers:** `policy-refine.yaml` gains a `failed: {terminal: true, failure: true}` state, `on_error: failed` on `score`/`parse_scores`/`policy_dispatch`, and `_error: failed` on its dispatch (replacing `_error: done`). Its `light_repair -> score` cycle is the canonical two-pass reproduction; base the two-pass regression on that shape. `rn-remediate.yaml` `check_convergence` needs no YAML change (the precedence fix makes its existing `_error: gate_implement` live); add a routing-level regression that proves an `error` verdict on that state reaches `gate_implement`. `rn-remediate.yaml` `diagnose` and `oracles/code-run-gate.yaml` `aggregate` are unaffected (identical targets) and need no change.
- **Header example:** the `policy-router.yaml` routing-handoff example keeps `_error: done`-style shape but the comment changes from "optional: error fallback" to state that `_error` catches the evaluator `error` verdict (nonzero exit / timeout) ahead of `_`, and that a dedicated failure terminal is the recommended target.
- **Shared reserved-name contract and ownership:** use one exported per-mode `RESERVED_STATE_NAMES` map and one exported `isReservedOutcomeToken(mode, token)` predicate in `policy_builder_core.mjs`, adopting the export name already proposed by BUG-3486. This issue establishes the minimum runtime sets: decision-table `{score, parse_scores, policy_dispatch, failed, error}` and issue-lifecycle `{score, policy_dispatch, done, failed, error}`. The predicate additionally rejects **every underscore-prefixed token**, including `_` and `_error`, because the runtime strips those from explicit verdict routes. Both serializers guard authored outcome names, rule targets, and fallback before emission; errors identify the offending token and ask the author to rename it and its references. BUG-3486 consumes and extends this same map/predicate for broader browser/model validation and other modes; it must not introduce a parallel reserved-name definition or lose the `error` and underscore-prefix protections. Its implementation must reconcile its currently different membership with this contract.
- **Completion-name scope:** BUG-3486 owns the existing `done`/`finished` collision and its proposed fixed `finished` auxiliary terminal. This issue preserves decision-table `_doneStateName()` behavior and keeps `done` legal. The guard here prevents the enumerated runtime-state and verdict/sentinel collisions; it does **not** claim to prevent every duplicate YAML key or malformed model until BUG-3486 lands. Existing drafts using newly forbidden tokens require migration before re-export. Reserve `failed` consistently with the lifecycle convention, while also emitting explicit `failure: true`; no dynamic failure-state allocation is needed.

## Implementation Steps

1. Add `_route()` precedence regressions in `scripts/tests/test_fsm_executor.py` (the five cases listed under Proposed Solution), then move the `verdict == "error"` / `route.error` check above `route.default` in `FSMExecutor._route()` and update its docstring. Run the full executor and validation suites before touching anything else; investigate any newly failing test and record actual compatibility changes rather than assuming every failure proves reliance on the old precedence. Recheck the shipped-loop audit; generated and consumer-authored loops are additional affected populations.
2. Add behavioral regressions for two-pass scoring and generated failure routing. Model the two-pass test on `policy-refine.yaml`'s `light_repair -> score` cycle. Use a success fallback so the old `_`-shadows-`_error` shape is exercised; inject scoring/parsing nonzero exits, dispatch nonzero exit/timeout, and a dispatch action exception. Assert the failure result and that no user outcome action runs. Cover both `_serializeDecisionTable()` and `_serializeIssueLifecycle()` output, and dispatch exceptions in resolved `policy-refine.yaml`. Separately preserve the executor abort path for heredoc collisions, asserting no user outcome action without requiring `failure_terminal == true`. Add a case asserting an omitted `AGGREGATE:` line leaves no `rubric-aggregate.txt` and that an `aggregate:<N` rule then does not match. Add a routing-level regression for `rn-remediate.yaml` `check_convergence`: verdict `error` -> `gate_implement`.
3. Extract the parser module, implement cleanup and the scoring contract above (absent aggregate writes no file), and wire the fragment to invoke it with exit propagation. Add actual interpolated-fragment execution tests as well as pure parser/module tests. Remove dispatch's broad `FileNotFoundError` recovery; reproduce a discovered-but-unreadable dimension with a dangling symlink, a success catch-all, and the real fragment. Assert nonzero exit, no winning stdout token, and no new winning action publication. Also cover normal omitted dimensions and enumeration/read/write failures.
4. Add the shared `RESERVED_STATE_NAMES` map and `isReservedOutcomeToken(mode, token)` predicate with the runtime sets and underscore-prefix rule above; invoke the guard in both serializers. Keep completion-name changes in BUG-3486, which consumes/extends these exports instead of defining another list. Add the explicit failure terminal, upstream `on_error` routes, and `_error: failed` / `on_error: failed` on dispatch to `_serializeDecisionTable()`; add dispatch `on_error: failed` and `failure: true` on `_serializeIssueLifecycle()`'s `failed` terminal. Verify ordinary successful routing and unmatched-token fallback in both modes.
5. Update `policy-refine.yaml`: add the `failed` terminal, `on_error: failed` on `score`/`parse_scores`/`policy_dispatch`, and `_error: failed` on dispatch in place of `_error: done`. Run `ll-loop validate` on it.
6. Regenerate `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` and `sample-issue-lifecycle.yaml` from their existing `.model.json`; change model input only if necessary for the agreed behavior. Update assertions in `scripts/tests/js/policy_validator.test.mjs`, `scripts/tests/test_policy_builder_emit.py`, and `scripts/tests/test_policy_builder_node_gate.py`; fixture equality and validation supplement execution tests.
7. Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` (required by `scripts/tests/test_enh3035_artifact_template_kit.py`).
8. Update `docs/guides/POLICY_ROUTER_GUIDE.md`, `docs/guides/LOOPS_GUIDE.md` (route-table resolution order), and the `policy-router.yaml` header/fragment contract to explain clean-slate/partial scoring, scorer exclusivity, absent-aggregate semantics, failure routing, the corrected `_error` precedence, and reserved-name migration. Reword the header's `_error` handoff comment as described under Proposed Solution. Document caller-supplied `on_error` on scoring/parsing/dispatch states and `_error` routing on dispatch states, the distinction between absent evidence and artifact-read failure, and preserved executor aborts. `policy-refine.yaml` is the only shipped caller of `policy_parse_scores`/`policy_table_dispatch` (verified by grep), so the caller audit for newly rejected unparseable output and absent aggregate is limited to it; do not claim all handwritten loops gain the builder's failure routes automatically.
9. Run focused parser, fragment, serialization, validation, and execution tests, then the full local suite: `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 - stale evidence and mis-routed failures make runtime routing wrong even when the preview is healthy
- **Effort**: Moderate - one executor precedence change with regressions, parser extraction, behavioral execution tests, serializer guards in both modes, caller update, and fixture regeneration
- **Risk**: Moderate - `_route()` is shared by every loop. The shipped-loop audit identifies four states with both sentinels, two with identical targets; this inventory does not limit the compatibility impact on generated or consumer-authored loops. Shared fragment I/O behavior and reserved-name compatibility need coverage.
- **Breaking Change**: Yes, bounded - `_error` now catches the `error` verdict ahead of `_` in every route table (generated and consumer-authored loops relying on `_` swallowing errors also change behavior; the shipped-loop inventory is recorded above); the per-mode runtime names and all underscore-prefixed authored outcome tokens are rejected before serialization; discovered-artifact read failures now abort dispatch instead of evaluating incomplete scores; wholly unparseable score output now exits nonzero; an omitted `AGGREGATE:` line no longer publishes `0`, so `aggregate:<N` rules stop matching on missing aggregate and fall through to later rules or the catch-all. Existing drafts must rename colliding tokens/references; existing fragment callers must supply error routing to stop on parser failure. Recognized partial-output semantics otherwise remain compatible.

## Integration Map

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/policy_rules.py` — `parse_rules(text)` (line 98) and `evaluate_rules(rules, scores)` (line 232) are consumed by `policy_table_dispatch`; both stay on their current signatures
- `scripts/little_loops/fsm/schema.py` — `RouteConfig.from_dict()` strips underscore-prefixed route keys (the serializer must reject such authored tokens); `StateConfig.failure` / `FSMLoop.get_failure_states()` define failure semantics; `FAILURE_TERMINAL_NAMES` supplies a backward-compatible default only. Emit explicit `failure: true`; no schema change is required.
- `scripts/little_loops/fsm/executor.py` — actual runtime routing: `_route()` (~3292-3339) is modified so `verdict == "error"` resolves `route.error` before `route.default`; explicit `routes[verdict]` and the `_uncertain` base fallback stay above both. Next-chained states still require `on_error` to stop on ordinary nonzero exits (the `next:` path at ~2162 consults `on_error` before `next`). `_abstention_fallback` (~3262) and the `no` -> `route.error` shorthand (~3337) are untouched.
- `scripts/little_loops/fsm/evaluators.py` — classify evaluation short-circuits nonzero exits/timeouts into `error` verdicts; generated dispatch must handle that exact token.
- `scripts/little_loops/fsm/route_table.py` — extracts/renders/edits route tables; it does not implement runtime routing. Existing editing coverage should preserve explicit verdict and sentinel routes.
- `scripts/little_loops/loops/policy-refine.yaml` — the only shipped caller of `policy_parse_scores`/`policy_table_dispatch` and the live reproduction of the two-pass leak (`light_repair`/`deep_repair` -> `next: score`; `rethink` routes `next: done` and is not part of the reproduction); modified in this issue to gain the `failed` terminal, scoring/parsing/dispatch `on_error: failed`, and dispatch `_error: failed`.
- `scripts/little_loops/loops/rn-remediate.yaml` — `check_convergence` (~857-859) declares `_` and `_error` with different targets; behavior changes under the precedence fix to match its own comment. `diagnose` (~416-417) declares both with identical targets; no change. No YAML edit in either; routing regression only.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `aggregate` (~478-479) declares both sentinels with identical targets; no change.
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — `_validate_classify_route_default` (~606) is the existing classify route lint; no new lint is added by this issue (the originally proposed dead-sentinel lint is dropped in favor of the executor fix).
- `scripts/little_loops/loops/lib/rubric-router.yaml` — supplies `rubric_score` and the separate aggregate-only rubric parser. Keep that parser's behavior outside this change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/loops/lib/policy-router.yaml` — `policy_parse_scores` fragment (~lines 72-115) and `policy_table_dispatch` fragment (~155-208)
- `scripts/little_loops/templates/policy_builder_core.mjs` — `_serializeDecisionTable(model)` at line 741; dispatcher call site at line 1056; precedent `_serializeIssueLifecycle(model)` at line 974
- `scripts/little_loops/fsm/policy_parse_scores.py` — new module proposed by this issue; confirmed absent from the tree today (no existing file or symbol matches this name)

**Conventions in Force**
- Clean-slate scoring already exists once in this codebase — `frontmatter_scores.py`'s `_clean_slate()` unlinks stale score files before a fresh pass; `test_frontmatter_scores.py::TestMainHappyPath::test_two_pass_clean_slate` is the existing test for that contract
- `_serializeIssueLifecycle()` demonstrates a dedicated `failed` terminal with `_error: failed`; that shape becomes correct once the executor precedence is fixed, so decision-table mode adopts the same shape rather than adding an `error:` key.

**Tests**
- `scripts/tests/test_policy_parse_scores.py` — new module tests for recognition, partial/invalid output, cleanup, two-pass artifacts, and file-operation failures
- `scripts/tests/test_frontmatter_scores.py` — nearest precedent for the two-pass clean-slate regression test this issue's Implementation Steps calls for
- `scripts/tests/test_policy_rules.py` — unit coverage for `parse_rules`/`evaluate_rules`
- `scripts/tests/test_fsm_fragments.py` — real interpolated parser/dispatch execution, including broken discovered score artifacts, omitted dimensions, I/O failures, and no winning publication on failure
- `scripts/tests/test_fsm_executor.py` — execution harness precedent; existing classify error coverage omits the normal fallback and therefore does not prove error routing with both `_` and `_error`. Gains the `_route()` precedence regressions. Add generated-loop execution coverage in the builder tests using a controlled action runner and resolved fragments.
- `scripts/tests/test_fsm_validation_reachability.py` — reachability tests touching failure-terminal routing
- `scripts/tests/test_policy_builder_emit.py`, `scripts/tests/test_policy_builder_node_gate.py`, `scripts/tests/js/policy_validator.test.mjs` — the three pinned tests this issue's Implementation Steps names for fixture regeneration
- `scripts/tests/test_policy_builder_corpus.py`, `scripts/tests/test_ll_loop_edit_routes.py` — additional decision-table/route-table corpus coverage
- `scripts/tests/test_enh3035_artifact_template_kit.py` — consumes `golden_policy_router_builder.html`, which this issue's Implementation Steps calls for regenerating

**Documentation**
- `docs/guides/POLICY_ROUTER_GUIDE.md` — names `policy_parse_scores`/`rubric-dim`/`on_error`; this issue's Implementation Steps already calls for updating it
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/ARCHITECTURE.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md` — each references `policy_parse_scores`/`policy_table_dispatch`/`rubric-dim`/`on_error` and may need adjustment once the new terminal and clean-slate step land

**Configuration**
- `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` + `.model.json` — regenerate YAML from the model; changing emitter behavior alone does not require changing the authored model
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — the pinned HTML fixture this issue's Implementation Steps calls for regenerating
- `scripts/tests/fixtures/policy_builder/sample-issue-lifecycle.yaml` + `.model.json` — existing fixture that already emits a `failed:` terminal; usable as a comparison point for the decision-table fixture once it gains one

## Program Design

### Types

No new data types or general scoring framework. Dispatch propagates artifact I/O failures before rule evaluation/publication. The parser gains a pure parsing function and small file-writing entry point; the serializer gains a reserved-namespace check, failure routes, and an explicitly marked failure terminal; the executor's route resolution order changes for one verdict.

### Signatures

- `FSMExecutor._route(state, verdict, ctx, _stripped=False) -> str | None` — unchanged signature; with a route table present, resolution order becomes: explicit `routes[verdict]`, `_uncertain` base fallback, then `route.error` when `verdict == "error"`, then `route.default`, then the `no` -> `route.error` shorthand.
- `_serializeDecisionTable(model) -> string` — unchanged signature; rejects authored tokens in the reserved set before emission, adds `failed: {terminal: true, failure: true}`, adds `on_error: failed` to all three pipeline states, and maps `_error` to `failed` in dispatch.
- `_serializeIssueLifecycle(model) -> string` — unchanged signature; applies the shared per-mode guard, adds `on_error: failed` on dispatch and `failure: true` to the existing `failed` terminal. Lifecycle verb behavior is unchanged.
- `export const RESERVED_STATE_NAMES` (mjs) — per-mode map of runtime-reserved names: decision-table `{score, parse_scores, policy_dispatch, failed, error}`; issue-lifecycle `{score, policy_dispatch, done, failed, error}`. BUG-3486 extends the same map for broader authoring validation and additional modes.
- `export function isReservedOutcomeToken(mode, token) -> boolean` — checks the applicable map entry plus `token.startsWith("_")`. Both serializers and BUG-3486's validation share this predicate; a finite set alone cannot express the runtime's underscore-prefix restriction.
- New module `scripts/little_loops/fsm/policy_parse_scores.py`:
  - `def main(argv: list[str] | None = None) -> int` — receives `<run_dir>`, creates the directory, cleans score artifacts, reads `policy_parse_scores-scores.txt`, parses, and writes scores. Returns nonzero with a diagnostic on parse or file-operation failure. The module entry point propagates this code to the shell.
  - `def parse_scores(output: str) -> tuple[int | None, dict[str, str]]` — extracts aggregate and normalized dimension scores; raises `ValueError` when neither is recognized. Recognized dimensions without aggregate return aggregate `None` (and `main` writes no `rubric-aggregate.txt`); recognized aggregate without dimensions returns an empty mapping. Preserve existing recognition/normalization and duplicate-dimension behavior.
  - `def _clean_slate(run_dir: Path) -> None` — unlinks only `rubric-dim-*.txt` and `rubric-aggregate.txt`; cleanup errors propagate.
- The shell fragment materializes captured output in `policy_parse_scores-scores.txt`, checks that writing it succeeded before invoking the module, and propagates the module's exit status. A failed input write must not reuse a previous raw-input file. Follow the neighboring fragments' `LL_PYTHON` interpreter override convention and pass the run-directory argument with shell-safe interpolation. Keep a real fragment execution smoke test alongside unit tests.

### Call Path

Success: `score` captures output -> `policy_parse_scores` writes raw input -> `main` -> `_clean_slate` -> read input -> `parse_scores` -> write aggregate/dimension artifacts -> `policy_table_dispatch` -> `parse_rules` / `evaluate_rules` -> classify verdict -> `FSMExecutor._route()` -> authored outcome or ordinary fallback.

Failure: scoring/parsing nonzero exit -> that state's `on_error: failed`; dispatch artifact enumeration/read failure or nonzero exit/timeout -> evaluator `error` verdict -> `FSMExecutor._route()` -> `RouteConfig.error` (`_error: failed` in YAML, now consulted before `RouteConfig.default`); routable dispatch action-runner exception -> `on_error: failed` in both generated modes and `policy-refine.yaml`. These paths reach the terminal with `failure: true` before user outcome actions run. Deliberate executor aborts such as `HeredocCollisionError` retain the top-level abort path and execute no user outcome action; do not reroute them just to satisfy a failure-terminal assertion.

`serializeLoopYaml` -> `_serializeDecisionTable` -> `validate_fsm` (Python round-trip in `scripts/tests/test_policy_builder_node_gate.py`).

## Acceptance Criteria

- [ ] Two-pass scoring followed by dispatch proves a removed dimension's previous score cannot select the old rule. Cover both a numeric comparison becoming non-matching and preserved missing-dimension `!=` behavior; normal catch-all routing remains available.
- [ ] Each parser invocation clears prior score artifacts. A missing aggregate with recognized dimensions writes no `rubric-aggregate.txt` and an `aggregate:<N` rule then does not match; aggregate-only output succeeds with no dimension artifacts; output with neither recognized aggregate nor dimensions exits nonzero without publishing new score files. Unrelated run artifacts survive.
- [ ] Cleanup/read/write failures propagate as nonzero exits. A failed raw-input write cannot invoke the parser on old input. A real interpolated-fragment test proves module invocation, artifact output, and nonzero exit propagation.
- [ ] A real interpolated `policy_table_dispatch` regression uses a discovered broken dimension artifact and a success catch-all: exit is nonzero, no winning token is emitted, and no new winning `policy-action.txt` is published. Directory-enumeration and discovered-artifact read failures propagate; ordinary omitted dimensions and aggregate remain valid, and action-file write failures exit nonzero. Mocking a nonzero dispatch result alone does not satisfy this criterion.
- [ ] `FSMExecutor._route()` unit tests: with `_: accept` and `_error: failed`, verdict `error` returns `failed` and verdict `unknown` returns `accept`; an explicit `error: retry` beats `_error`; `error_uncertain` with no explicit route resolves to `_error`; a table with `_` and no `_error` still sends `error` to `_`. The `_route()` docstring's resolution order matches the code.
- [ ] Executor and validation suites pass, with changes to existing expectations justified by actual routing semantics. Recheck the shipped-loop inventory under Current Behavior and record any additional affected shipped states. Do not assert that the four-state inventory bounds changes to generated or consumer-authored loops.
- [ ] Generated decision-table YAML emits `failed: {terminal: true, failure: true}`, `on_error: failed` on `score`, `parse_scores`, and `policy_dispatch`, and `_error: failed` (no `error:` key) in the dispatch route table.
- [ ] Execution tests with a success fallback prove scoring/parsing nonzero exits, dispatch nonzero exit/timeout, and a routable dispatch action-runner exception terminate with `failure_terminal == true`; no user outcome action runs. Scoring failure skips parsing/dispatch; parsing failure skips dispatch. Ordinary success and unmatched-token fallback still work.
- [ ] Generated issue-lifecycle YAML emits dispatch `on_error: failed` and `failure: true` on `failed`; execution tests with a success fallback prove both a dispatch evaluator `error` verdict and a routable action-runner exception reach `failed` without running a user outcome action.
- [ ] `policy-refine.yaml` declares a `failed` failure terminal, `on_error: failed` on `score`/`parse_scores`/`policy_dispatch`, and `_error: failed` on dispatch; it passes `ll-loop validate`. Execution coverage proves dispatch nonzero exits and routable action-runner exceptions reach the failure terminal without executing outcome actions.
- [ ] A routing-level regression proves `rn-remediate.yaml` `check_convergence` sends verdict `error` to `gate_implement`; no YAML change to that loop.
- [ ] Serializer tests in both covered modes reject their `RESERVED_STATE_NAMES` entries and underscore-prefixed tokens (including `_`, `_error`, and an ordinary `_custom` token) in outcome names, rule targets, and fallback before emission. Diagnostics explain renaming the token and references. The shared map/predicate is the integration contract for BUG-3486. Decision-table `done` remains legal and retains its existing dodge; comprehensive completion-name collision protection belongs to BUG-3486.
- [ ] Deliberate executor aborts such as heredoc-collision protection preserve their existing termination reason and execute no user outcome action. Tests do not require these aborts to reach `failed` or set `failure_terminal == true`.
- [ ] Fragment header and `POLICY_ROUTER_GUIDE.md` state the single-scorer-per-pass contract.
- [ ] Valid decision-table models still pass `validate_fsm` (runtime validation) in the Node gate round-trip test.
- [ ] Golden fixtures regenerated; full local suite passes.

## Scope Boundaries

Includes the `_route()` precedence fix for the `error` verdict, clean-slate LLM parsing, the explicit partial/invalid-output contract (absent aggregate is absent), the single-scorer-per-pass documentation contract, dispatch artifact-read failure propagation, generated decision-table and issue-lifecycle verdict/exception failure routing, the `policy-refine.yaml` caller fix, a `check_convergence` routing regression, and the reserved-namespace serializer guard required to land safely. BUG-3486 owns broader browser/model validation, completion-name collision protection, and editing, consuming/extending `RESERVED_STATE_NAMES` and `isReservedOutcomeToken` exported here; BUG-3490 owns catalog discovery.

Excludes changes to deliberate executor abort semantics, the `done`/`finished` completion-name strategy owned by BUG-3486, and any other `_route()` reordering (the `no` -> `route.error` shorthand, `_uncertain` handling, abstention fallback, and shorthand `on_*` routing are untouched), a validator lint for `_`+`_error` (dropped; the executor fix makes the shape correct), lifecycle outcome-action failure semantics beyond dispatch routing, arbitrary user outcome action-failure semantics, missing-dimension rule changes, general score-range/format validation, `lib/rubric-router.yaml`'s aggregate-only parser, and a transactional/generalized scoring framework. Handwritten loops other than `policy-refine.yaml` do not automatically receive `on_error` routes on their scoring states; document the fragment caller contract.

## Steps to Reproduce

1. Run the `policy_parse_scores` fragment twice in one temporary run directory, omitting a dimension on pass two; inspect the retained `rubric-dim-*.txt`.
2. Serialize the seeded decision-table model and inspect the `_error` sentinel: it names the first rule's target, not a failure state.
3. Construct a dispatch state with `_: accept` and `_error: failed`; feed an `error` verdict through `FSMExecutor._route()`. It returns `accept`, contradicting the `RouteConfig.error` docstring. An ordinary unknown verdict also returns `accept`.
4. Feed verdict `error` through `_route()` for `rn-remediate.yaml`'s `check_convergence` state: it returns `check_remediation_budget`, not the `gate_implement` its comment names.
5. Inject a nonzero exit into the generated `score` or `parse_scores` state and observe its unconditional `next` path in the absence of `on_error`.
6. Run the real interpolated dispatch fragment with a dangling `rubric-dim-security.txt` symlink in an otherwise valid run directory and rules `security:<65 -> repair` / `* -> accept`: observe exit 0, stdout `accept`, a misleading directory-missing diagnostic, and a winning action file despite the read failure.
7. Inject a `RuntimeError` from the dispatch action runner in generated lifecycle YAML or resolved `policy-refine.yaml`: without dispatch `on_error`, it follows the executor error path instead of the intended `failed` terminal.

## Root Cause

The LLM score parser lacks clean-slate handling, treats wholly unparseable output as a successful pass, and fabricates an aggregate of `0` when none was emitted. `_serializeDecisionTable()` omits upstream error routes and a dedicated failure terminal and reuses the first outcome token for `_error`. Independently, `FSMExecutor._route()` checks `route.default` before `route.error`, so `_error` is unreachable for the `error` verdict whenever `_` is declared; this contradicts the schema's documented meaning of `_error` and silently misroutes `_serializeIssueLifecycle()`, `policy-refine.yaml`, `rn-remediate.yaml` `check_convergence`, and the fragment header's own handoff example. Dispatch also swallows dimension-read `FileNotFoundError`, evaluating incomplete evidence with a success exit, while lifecycle and shipped dispatch states lack exception-specific `on_error` routes. Failure semantics must be established across the entire scoring/dispatch chain, and the executor must honor the sentinel the schema promises.

## Verification Notes

Architecture review follow-up (2026-09-16, inspected branch `main`): the current design incorporates dispatch exception routes for lifecycle and `policy-refine.yaml`, a reproduced swallowed artifact-read failure, the shared reserved-name contract with BUG-3486, and bounded abort/compatibility guarantees. Earlier verification below is historical; its blanket claim that all behavior matched did not establish complete dispatch exception or artifact-read handling. No runtime fix has been implemented by this issue edit.

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

- Current Behavior and the Integration Map both claimed `policy-refine.yaml` routes
  `light_repair`/`deep_repair`/`rethink` back to `score` via `next: score`. Verified
  against the live file: only `light_repair` (line 75) and `deep_repair` (line 83)
  route to `score`; `rethink` (line 91) routes `next: done` and is not part of the
  two-pass reproduction. Corrected both mentions in place; the underlying two-pass
  leak still reproduces via `light_repair`/`deep_repair` alone, so no other claim in
  the issue is affected.
- Every other file:line and behavioral claim checked (policy-router.yaml fragments,
  `frontmatter_scores._clean_slate()`, `policy_builder_core.mjs` serializer line
  numbers/behavior, `FSMExecutor._route()` precedence, `evaluators.py` error-verdict
  short-circuit, `policy_rules.py`, `schema.py`, `route_table.py`,
  `validation/evaluator_rules.py`, `rubric-router.yaml`, all named test files and
  fixtures) matches current code exactly.
- `ll-verify-evidence --json` on this file: clean (`ok: true`, 0 findings).
- Decisions check: `.ll/decisions.yaml` present, no active required rules — no
  conflict possible.
- Dependency refs (`relates_to`: BUG-3486, BUG-3490, FEAT-3474, FEAT-3488) all
  resolve to real issues. BUG-3486 is `open` (not done), so this is not a stale
  split from an already-resolved parent.
- Graph-assisted check: `ll-code --json status` → provider `codegraph`,
  `freshness: fresh`.
- Proposal-vs-code consequence check (B6): no PROPOSAL_UNSOUND findings. Minor,
  non-blocking gap noted: `route_table.py` in the Integration Map has no dedicated
  new AC, only "existing editing coverage should preserve."

## Status

**Open** | Created: 2026-09-16 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-16T23:29:28 - `993432ad-a051-4f1f-967b-f26e1cd3e891.jsonl`
- `/ll:verify-issues` - 2026-09-16T23:10:00 - `65d3c113-1c9d-45cd-b132-c02e6bee7024.jsonl`
- `/ll:refine-issue` - 2026-09-16T22:24:04 - `c7278f1b-df03-4464-a3c5-e94aa066b201.jsonl`
- review - 2026-09-16 - applied architecture review: explicit error-verdict routing, upstream failure routes, partial/invalid scoring contract, serializer collision guards and migration, behavioral execution coverage, corrected runtime integration and dependency scope
- review - 2026-09-16 - second pass, verified against executor/evaluators/serializer source: absent aggregate now writes no file instead of `0` (fabricated-evidence class); lifecycle serializer folded in (same one-line fix, same unreachable `_error`); `policy-refine.yaml` identified as live two-pass reproduction and fixed here; added `ll-loop validate` dead-sentinel lint; reframed `error` reservation as latent-defect fix and justified reserving `failed` over dodging it
- review - 2026-09-16 - third pass (architecture): replaced the dead-sentinel lint and the `error:` duplicate route key with a fix to `FSMExecutor._route()` precedence (`_error` before `_` for the `error` verdict), after enumerating the blast radius as four shipped states (two no-op, one fixed here, one `check_convergence` misroute corrected to its comment's intent). The lint as specified would have fired on the issue's own emitted fixtures and on two shipped loops, contradicting its AC. Widened the reserved-token guard from `{error, failed}` to the full generated-state namespace (`score`, `parse_scores`, `policy_dispatch` also emit duplicate keys today). Added the single-scorer-per-pass documentation contract. Confirmed `policy-refine.yaml` is the only shipped fragment caller.
- review - 2026-09-16 - folded follow-up architecture findings into the design, steps, and acceptance criteria: dispatch on_error in lifecycle and policy-refine; real artifact-read failure propagation; shared per-mode reserved names and underscore-prefix rejection coordinated with BUG-3486; completion-name scope retained there; deliberate executor aborts preserved; four-state impact claim bounded to audited shipped loops

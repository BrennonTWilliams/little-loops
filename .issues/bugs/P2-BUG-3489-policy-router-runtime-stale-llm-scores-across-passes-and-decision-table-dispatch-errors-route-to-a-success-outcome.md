---
id: BUG-3489
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
blocks:
- ENH-3487
- BUG-3486
relates_to:
- BUG-3486
- BUG-3490
- FEAT-3474
- FEAT-3488
---

# BUG-3489: Policy-router runtime: stale LLM scores across passes and decision-table dispatch errors route to a success outcome

## Summary

Fix two runtime defects in the policy-router loop fragments and decision-table YAML emission: stale per-dimension score files survive a second LLM scoring pass, and scoring/dispatch failures can reach a user outcome because the generated chain lacks complete failure routing. Adding a failure terminal alone is insufficient: the executor resolves the normal `_` fallback before `_error`, so dispatch must explicitly map the `error` verdict.

Split from BUG-3486 (2026-09-16 whole-builder review, defects f and g). Separate from catalog discovery in BUG-3490; coordinate serializer guards and reserved names with BUG-3486, which lands after this issue.

## Current Behavior

- The `policy_parse_scores` fragment (`scripts/little_loops/loops/lib/policy-router.yaml`, ~lines 84-116) writes `rubric-dim-<name>.txt` only for `DIMENSION:` lines present in the current pass and never deletes pre-existing files. `policy_table_dispatch` (same file, ~197-208) then reads every `rubric-dim-*.txt` via `os.listdir(run_dir)`. Running the fragment twice in one run dir, omitting a dimension on pass two, leaves the pass-one score in play. A previous `citations` score of 100 survives a second pass that emitted no citations line. The deterministic `frontmatter_scores` scorer already clears stale files via `_clean_slate()` (`scripts/little_loops/fsm/frontmatter_scores.py:158-169`).
- `_serializeDecisionTable()` (`scripts/little_loops/templates/policy_builder_core.mjs` ~800-804) sets `errorState = tokens[0] || fallbackState`, where `tokens[0]` is whichever outcome the first authored rule targets. No dedicated failure terminal is emitted for decision-table mode, so a dispatch or scoring failure can report successful completion. `_serializeIssueLifecycle()` (mjs ~974-1041) already emits an explicit `failed:` terminal and routes `_error: failed`.
- `FSMExecutor._route()` checks explicit verdict routes, then `route.default`, then `route.error`. With a route table present, ordinary verdict routing does not fall through to the state's `on_error`. A review probe with `_: accept`, `_error: failed`, and `on_error: failed` still routed the `error` verdict to `accept`; adding `error: failed` routed it to `failed`. The lifecycle serializer is a terminal-shape precedent, not proof that `_error` wins over `_`.
- Generated `score` and `parse_scores` states have unconditional `next` and no `on_error`; positive nonzero action exits can therefore advance into parsing or dispatch. The parser also exits successfully with no parsed dimensions and defaults missing aggregate to `0`. Aggregate is already overwritten on successful parses; stale dimensions are the existing successful-pass evidence leak.

## Expected Behavior

Fresh scoring cannot use previous-pass evidence: every `policy_parse_scores` pass clears `rubric-dim-*.txt` and `rubric-aggregate.txt` before reading/parsing its input and publishing new scores. Other run artifacts survive. Recognized partial scoring remains valid under the contract below; wholly unparseable output fails. Generated decision-table loops route scoring, parsing, and dispatch failures to an explicit failure terminal, without executing user outcome actions, even when the normal fallback is a success outcome.

## Motivation

Users cannot trust routing decisions when evidence leaks between passes or when a failure lands on a success state. These runtime fixes unblock ENH-3487 and BUG-3486's subsequent builder work. FEAT-3488 currently treats BUG-3489 as related only; this issue does not establish a direct execution-handoff dependency.

## Proposed Solution

- Extract the parser into a small importable module with pure `parse_scores()` and a file-writing entry point. Clear only `rubric-dim-*.txt` and `rubric-aggregate.txt` in `${context.run_dir}` before reading/parsing the new input. Preserve existing normalization and score text output. Cleanup/read/write failures must propagate as nonzero exits; dispatch must not consume any partial publication. The sequential state chain and failure routes make a transactional artifact framework unnecessary.
- **Scoring contract:** at least one recognized `DIMENSION` or `AGGREGATE` value is required. Empty output or output with neither raises a parse error and produces a nonzero exit. Partial output remains valid: omitted dimensions stay absent, aggregate-only output is valid, and missing aggregate with recognized dimensions writes fresh `0`. Preserve current recognition/normalization rules; broader score-range and format validation is outside this fix. Preserve `policy_rules` semantics: an absent dimension matches `!=`, other comparisons do not match, and catch-all rules still match. Missing evidence is not automatically a pipeline failure.
- Emit `failed: {terminal: true, failure: true}` in `_serializeDecisionTable()`. Set `on_error: failed` on `score`, `parse_scores`, and `policy_dispatch`. In the dispatch route table emit both **`error: failed`** and `_error: failed`, retaining `_` for ordinary unmatched verdicts. The explicit `error` entry handles nonzero exits/timeouts converted to evaluator error verdicts; dispatch `on_error` handles action exceptions. Keep shared executor precedence unchanged in this issue; any general precedence correction requires separate regression coverage and scope.
- **Collision handling lands here:** before serialization, reject authored `error` or `failed` tokens in outcome names, rule targets, or fallback (all sources of generated outcome states/route keys), with an actionable error asking the author to rename the token and its references. Never silently rename or emit duplicate YAML keys. BUG-3486 later integrates these same reserved names into its broader model/browser validation; this issue cannot depend on that later validation to emit safe YAML. Existing drafts using those names require migration before re-export.

## Implementation Steps

1. Add behavioral regressions for two-pass scoring and generated decision-table failure routing. Use a success fallback so `_` shadowing `_error` is exercised; inject scoring/parsing nonzero exits, dispatch nonzero exit/timeout, and a dispatch action exception. Assert the failure result and that no user outcome action runs.
2. Extract the parser module, implement cleanup and the scoring contract above, and wire the fragment to invoke it with exit propagation. Add one actual interpolated-fragment execution test as well as pure parser/module tests.
3. Add the serializer collision guards, explicit failure terminal, upstream `on_error` routes, and dispatch `error`/`_error`/`on_error` routes. Verify ordinary successful routing and unmatched-token fallback are preserved.
4. Regenerate `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` from its existing `.model.json`; change model input only if necessary for the agreed behavior. Update assertions in `scripts/tests/js/policy_validator.test.mjs`, `scripts/tests/test_policy_builder_emit.py`, and `scripts/tests/test_policy_builder_node_gate.py`; fixture equality and validation supplement execution tests.
5. Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` (required by `scripts/tests/test_enh3035_artifact_template_kit.py`).
6. Update `docs/guides/POLICY_ROUTER_GUIDE.md` and the fragment contract/example to explain clean-slate/partial scoring, failure routing, and reserved-name migration. Document caller-supplied `on_error` on parsing states and explicit `error` routing on dispatch states. Audit existing fragment callers for impact from newly rejected wholly unparseable output; do not claim all handwritten loops gain the builder's failure routes automatically.
7. Run focused parser, fragment, serialization, and execution tests, then the full local suite: `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 - stale evidence and mis-routed failures make runtime routing wrong even when the preview is healthy
- **Effort**: Moderate - parser extraction, behavioral execution tests, serializer guards, and fixture regeneration
- **Risk**: Moderate - shared fragment behavior and reserved-name compatibility need coverage; shared executor routing semantics remain unchanged
- **Breaking Change**: Yes, bounded - `error` and `failed` become reserved authored decision-table tokens, and wholly unparseable score output now exits nonzero. Existing drafts must rename colliding tokens/references; existing fragment callers must supply error routing to stop on parser failure. Recognized partial-output semantics remain compatible.

## Integration Map

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/policy_rules.py` — `parse_rules(text)` (line 98) and `evaluate_rules(rules, scores)` (line 232) are consumed by `policy_table_dispatch`; both stay on their current signatures
- `scripts/little_loops/fsm/schema.py` — `StateConfig.failure` / `FSMLoop.get_failure_states()` define failure semantics; `FAILURE_TERMINAL_NAMES` supplies a backward-compatible default only. Emit explicit `failure: true`; no schema change is required.
- `scripts/little_loops/fsm/executor.py` — actual runtime routing: `_route()` resolves explicit verdicts before `_` and `_error`; next-chained states require `on_error` to stop on ordinary nonzero exits. Exercise these paths without changing shared routing precedence.
- `scripts/little_loops/fsm/evaluators.py` — classify evaluation short-circuits nonzero exits/timeouts into `error` verdicts; generated dispatch must handle that exact token.
- `scripts/little_loops/fsm/route_table.py` — extracts/renders/edits route tables; it does not implement runtime routing. Existing editing coverage should preserve explicit verdict and sentinel routes.
- `scripts/little_loops/loops/policy-refine.yaml` — existing parser/dispatch fragment caller; audit the effect of newly rejected wholly unparseable output and caller-supplied failure routes.
- `scripts/little_loops/loops/lib/rubric-router.yaml` — supplies `rubric_score` and the separate aggregate-only rubric parser. Keep that parser's behavior outside this change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/loops/lib/policy-router.yaml` — `policy_parse_scores` fragment (~lines 72-115) and `policy_table_dispatch` fragment (~155-208)
- `scripts/little_loops/templates/policy_builder_core.mjs` — `_serializeDecisionTable(model)` at line 741; dispatcher call site at line 1056; precedent `_serializeIssueLifecycle(model)` at line 974
- `scripts/little_loops/fsm/policy_parse_scores.py` — new module proposed by this issue; confirmed absent from the tree today (no existing file or symbol matches this name)

**Conventions in Force**
- Clean-slate scoring already exists once in this codebase — `frontmatter_scores.py`'s `_clean_slate()` unlinks stale score files before a fresh pass; `test_frontmatter_scores.py::TestMainHappyPath::test_two_pass_clean_slate` is the existing test for that contract
- `_serializeIssueLifecycle()` demonstrates a dedicated `failed` terminal, but its `_error` route is also subject to executor fallback precedence. Use it as a terminal-shape precedent only; this issue fixes generated decision-table routing, not lifecycle dispatch routing.

**Tests**
- `scripts/tests/test_policy_parse_scores.py` — new module tests for recognition, partial/invalid output, cleanup, two-pass artifacts, and file-operation failures
- `scripts/tests/test_frontmatter_scores.py` — nearest precedent for the two-pass clean-slate regression test this issue's Implementation Steps calls for
- `scripts/tests/test_policy_rules.py` — unit coverage for `parse_rules`/`evaluate_rules`
- `scripts/tests/test_fsm_fragments.py` — fragment-level tests referencing `policy_parse_scores`/`policy-router.yaml`
- `scripts/tests/test_fsm_executor.py` — execution harness precedent; existing classify error coverage omits the normal fallback and therefore does not prove error routing with both `_` and `_error`. Add generated-loop execution coverage in the builder tests using a controlled action runner and resolved fragments.
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

No new data types or general scoring framework. The parser gains a pure parsing function and small file-writing entry point; the serializer gains collision checks, failure routes, and an explicitly marked failure terminal.

### Signatures

- `_serializeDecisionTable(model) -> string` — unchanged signature; rejects authored `error`/`failed` tokens before emission, adds `failed: {terminal: true, failure: true}`, adds `on_error: failed` to all three pipeline states, and maps both `error` and `_error` to `failed` in dispatch.
- New module `scripts/little_loops/fsm/policy_parse_scores.py`:
  - `def main(argv: list[str] | None = None) -> int` — receives `<run_dir>`, creates the directory, cleans score artifacts, reads `policy_parse_scores-scores.txt`, parses, and writes scores. Returns nonzero with a diagnostic on parse or file-operation failure. The module entry point propagates this code to the shell.
  - `def parse_scores(output: str) -> tuple[int, dict[str, str]]` — extracts aggregate and normalized dimension scores; raises `ValueError` when neither is recognized. Recognized dimensions without aggregate return aggregate `0`; recognized aggregate without dimensions returns an empty mapping. Preserve existing recognition/normalization and duplicate-dimension behavior.
  - `def _clean_slate(run_dir: Path) -> None` — unlinks only `rubric-dim-*.txt` and `rubric-aggregate.txt`; cleanup errors propagate.
- The shell fragment materializes captured output in `policy_parse_scores-scores.txt`, checks that writing it succeeded before invoking the module, and propagates the module's exit status. A failed input write must not reuse a previous raw-input file. Follow the neighboring fragments' `LL_PYTHON` interpreter override convention and pass the run-directory argument with shell-safe interpolation. Keep a real fragment execution smoke test alongside unit tests.

### Call Path

Success: `score` captures output -> `policy_parse_scores` writes raw input -> `main` -> `_clean_slate` -> read input -> `parse_scores` -> write aggregate/dimension artifacts -> `policy_table_dispatch` -> `parse_rules` / `evaluate_rules` -> classify verdict -> `FSMExecutor._route()` -> authored outcome or ordinary fallback.

Failure: scoring/parsing nonzero exit -> that state's `on_error: failed`; dispatch nonzero exit/timeout -> evaluator `error` verdict -> `RouteConfig.routes["error"]` (`error: failed` in YAML, distinct from the `_error` sentinel stored in `RouteConfig.error`); dispatch action exception -> `on_error: failed`. All reach the terminal with `failure: true` before user outcome actions run.

`serializeLoopYaml` -> `_serializeDecisionTable` -> `validate_fsm` (Python round-trip in `scripts/tests/test_policy_builder_node_gate.py`).

## Acceptance Criteria

- [ ] Two-pass scoring followed by dispatch proves a removed dimension's previous score cannot select the old rule. Cover both a numeric comparison becoming non-matching and preserved missing-dimension `!=` behavior; normal catch-all routing remains available.
- [ ] Each parser invocation clears prior score artifacts. A missing aggregate with recognized dimensions writes fresh `0`; aggregate-only output succeeds with no dimension artifacts; output with neither recognized aggregate nor dimensions exits nonzero without publishing new score files. Unrelated run artifacts survive.
- [ ] Cleanup/read/write failures propagate as nonzero exits. A failed raw-input write cannot invoke the parser on old input. A real interpolated-fragment test proves module invocation, artifact output, and nonzero exit propagation.
- [ ] Generated decision-table YAML emits `failed: {terminal: true, failure: true}`, `on_error: failed` on `score`, `parse_scores`, and `policy_dispatch`, and both `error: failed` and `_error: failed` in the dispatch route table.
- [ ] Execution tests with a success fallback prove scoring/parsing nonzero exits, dispatch nonzero exit/timeout, and a dispatch action exception terminate with `failure_terminal == true`; no user outcome action runs. Scoring failure skips parsing/dispatch; parsing failure skips dispatch. Ordinary success and unmatched-token fallback still work.
- [ ] Serializer tests reject authored `error` and `failed` in each of outcome names, rule targets, and fallback before YAML is emitted; errors explain renaming the token and references. This protection works before BUG-3486 lands.
- [ ] Valid decision-table models still pass `validate_fsm` (runtime validation) in the Node gate round-trip test.
- [ ] Golden fixtures regenerated; full local suite passes.

## Scope Boundaries

Includes clean-slate LLM parsing, the explicit partial/invalid-output contract, generated decision-table scoring/dispatch failure routing, and minimal serializer guards required to land safely. BUG-3486 owns broader browser/model validation and editing, consuming the reserved names established here; BUG-3490 owns catalog discovery.

Excludes shared executor precedence changes, lifecycle-mode dispatch repair, arbitrary user outcome action-failure semantics, missing-dimension rule changes, general score-range/format validation, and a transactional/generalized scoring framework. Existing handwritten loops do not automatically receive generated failure routes; document the fragment caller contract and audit impact. Do not describe the entire lifecycle serializer as a proven failure-routing reference.

## Steps to Reproduce

1. Run the `policy_parse_scores` fragment twice in one temporary run directory, omitting a dimension on pass two; inspect the retained `rubric-dim-*.txt`.
2. Serialize the seeded decision-table model and inspect the `_error` sentinel: it names the first rule's target, not a failure state.
3. Construct a dispatch state with `_: accept`, `_error: failed`, and `on_error: failed`; feed an `error` verdict through `FSMExecutor._route()`. It still returns `accept`. Add explicit `error: failed` and confirm the result changes to `failed`, while an ordinary unknown verdict still returns `accept`.
4. Inject a nonzero exit into the generated `score` or `parse_scores` state and observe its unconditional `next` path in the absence of `on_error`.

## Root Cause

The LLM score parser lacks clean-slate handling and treats wholly unparseable output as a successful pass. `_serializeDecisionTable()` omits upstream error routes and a dedicated failure terminal, reuses the first outcome token for `_error`, and supplies a normal fallback that takes precedence over that sentinel in the executor. Failure semantics must be established across the entire scoring/dispatch chain, not inferred from the presence of a terminal or `_error` field.

## Status

**Open** | Created: 2026-09-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-16T22:24:04 - `c7278f1b-df03-4464-a3c5-e94aa066b201.jsonl`
- review - 2026-09-16 - applied architecture review: explicit error-verdict routing, upstream failure routes, partial/invalid scoring contract, serializer collision guards and migration, behavioral execution coverage, corrected runtime integration and dependency scope

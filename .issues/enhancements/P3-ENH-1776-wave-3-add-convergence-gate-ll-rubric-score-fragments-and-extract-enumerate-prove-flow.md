---
id: ENH-1776
title: "Wave 3 \u2014 Add `convergence_gate`, `ll_rubric_score` Fragments and Extract\
  \ `enumerate-prove-flow`"
type: ENH
priority: P3
captured_at: '2026-05-29T01:01:55Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
depends_on: ENH-1775
decision_needed: false
confidence_score: 96
outcome_confidence: 74
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
size: Very Large
status: done
---

# ENH-1776: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`

## Summary

Add two shared evaluator fragments (`convergence_gate` and `ll_rubric_score`) that standardize repeated evaluator patterns across 10 loops combined, and extract the `enumerate → parse → flatten → prove` chain from two integration loops into a reusable flow.

## Current Behavior

**`convergence_gate` pattern** — 5 loops use the `convergence` evaluator type with duplicated direction, target, tolerance, and previous-value wiring:

- `test-coverage-improvement.yaml`
- `agent-eval-improve.yaml`
- `rl-coding-agent.yaml`
- `rl-policy.yaml`
- `harness-optimize.yaml`

**`ll_rubric_score` pattern** — all 5 harness loops use an LLM prompt with a multi-criterion weighted rubric, structured output with per-criterion scores, and ALL_PASS/ITERATE routing. The rubric structure is duplicated with different criteria names across loops.

**`enumerate-prove` chain** — `adopt-third-party-api.yaml` and `integrate-sdk.yaml` both contain nearly identical `parse_enumeration` (python3 heredoc), `flatten_targets`/`flatten_surfaces` (python3 comma-join), and delegation to `ready-to-implement-gate` — a four-state chain duplicated across both loops.

## Expected Behavior

**`convergence_gate` fragment** in `loops/lib/common.yaml`:

```yaml
convergence_gate:
  action_type: shell
  evaluate:
    type: convergence
    direction: maximize
    target: "${context.convergence_target}"
    tolerance: "${context.convergence_tolerance}"
    previous: "${captured.prev_value.output}"
```

**`ll_rubric_score` fragment** — a parameterized LLM prompt fragment that takes `context.rubric_criteria` (YAML/JSON), `context.pass_threshold`, and evaluates via `output_contains` on ALL_PASS.

**`enumerate-prove-flow`** extracted as a named, composable multi-state sequence that takes a source (URL or codebase path) and returns proven targets.

## Motivation

The convergence evaluator is used identically across 5 loops but has no fragment template — each loop re-specifies direction, target, and tolerance inline. The rubric scoring pattern is the core of every harness loop's quality gate but each copy is independent. The enumerate-prove chain is four states duplicated verbatim across two integration loops.

## Proposed Solution

1. Add `convergence_gate` fragment to `loops/lib/common.yaml`
2. Add `ll_rubric_score` fragment to `loops/lib/common.yaml` (or `lib/harness.yaml`)
3. Extract `enumerate-prove-flow` as a flow definition or sub-loop
4. Convert 5 convergence callers to reference the fragment
5. Convert 5 harness loops to reference `ll_rubric_score`
6. Convert `adopt-third-party-api.yaml` and `integrate-sdk.yaml` to use the flow
7. Run `ll-loop validate` on all modified loops
8. Run `python -m pytest scripts/tests/ -v --tb=short`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add `convergence_gate` fragment under `fragments:` key; provides `action_type: shell` and `evaluate: { type: convergence, direction: maximize }` as defaults
- `scripts/little_loops/loops/lib/harness.yaml` — add `ll_rubric_score` fragment (place alongside `playwright_screenshot`); provides `action_type: prompt`, rubric eval prompt with `${context.rubric}` and `${context.pass_threshold}`, `evaluate: { type: output_contains, pattern: "ALL_PASS" }`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — update `score` state to `fragment: ll_rubric_score` (this is the actual rubric target after Wave 2; NOT the 5 parent wrapper loops)
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — NEW oracle sub-loop; does not exist yet; extract `parse_enumeration` + flatten + `prove` states from both source loops
- `scripts/little_loops/loops/test-coverage-improvement.yaml` — convert `extract_percentage` state to `fragment: convergence_gate`
- `scripts/little_loops/loops/agent-eval-improve.yaml` — convert `route_quality` state to `fragment: convergence_gate`
- `scripts/little_loops/loops/rl-coding-agent.yaml` — convert `score` state to `fragment: convergence_gate`
- `scripts/little_loops/loops/rl-policy.yaml` — convert `score` state to `fragment: convergence_gate`
- `scripts/little_loops/loops/harness-optimize.yaml` — convert `gate` state to `fragment: convergence_gate`
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — replace `parse_enumeration` + `flatten_targets` + `prove` states with delegation to `oracles/enumerate-and-prove`
- `scripts/little_loops/loops/integrate-sdk.yaml` — replace `parse_enumeration` + `flatten_surfaces` + `prove` states with delegation to `oracles/enumerate-and-prove`

**Note**: The 5 harness parent loops (`html-website-generator`, `svg-image-generator`, `html-anything`, `hitl-md`, `hitl-compare`) are NOT in this list. After Wave 2 they are thin wrappers that pass `rubric:` through `with:` to `generator-evaluator.yaml`. The `ll_rubric_score` fragment goes into the oracle's `score` state only.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/fragments.py:resolve_fragments()` — fragment resolution engine (line 64); validates `fragment:` keys and merges fields; no changes but must accept new fragment names
- `scripts/little_loops/fsm/evaluators.py:evaluate_convergence()` — convergence evaluator implementation (line 351); no changes needed; validate only
- `scripts/little_loops/fsm/validation.py:_validate_with_bindings()` — validates `with:` param bindings for sub-loop invocations (line 326); needed for `enumerate-and-prove` oracle validation
- `scripts/little_loops/cli/loop/__main__.py` — `ll-loop validate` CLI entry point

### Similar Patterns
- `scripts/little_loops/loops/lib/harness.yaml:playwright_screenshot` — Wave 2 oracle-level fragment; reference for placing `ll_rubric_score` in `lib/harness.yaml`
- `scripts/little_loops/loops/rl-bandit.yaml:reward` — minimal convergence state (no `previous:` field); reference for `convergence_gate` fragment default shape
- `scripts/little_loops/loops/harness-optimize.yaml:gate` — convergence state with optional `previous: "${captured.prev_score.output}"`; shows the caller-optional override pattern
- `scripts/little_loops/loops/assumption-firewall.yaml` — third enumerate-prove variant using `ASSUMPTIONS_JSON:` tag; out of scope for this wave but demonstrates the pattern's generalizability
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` — existing oracle sub-loop with `parameters:` block and `max_iterations: 1`; reference structure for the new `enumerate-and-prove.yaml`

### Tests
- `scripts/tests/test_builtin_loops.py` — validates all 5 convergence-using loops and all 5 harness loops; must pass after fragment conversions
- `scripts/tests/test_fsm_fragments.py` — fragment resolution and validation tests; add coverage for new `convergence_gate` and `ll_rubric_score` fragments
- `scripts/tests/test_fsm_evaluators.py` — convergence evaluator tests (`evaluate_convergence` imported at line 21); passes without changes
- `scripts/tests/fixtures/fsm/analysis-numeric-stall.yaml` — existing convergence evaluator test fixture; reference for new fragment tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_harness_optimize.py` — dedicated `TestHarnessOptimizeStates` class with `test_gate_has_convergence_evaluator` (reads inline `evaluate.direction/previous/tolerance`) and `test_gate_routes_correctly` (reads inline `route:` block); **both will break** when `gate` adopts `convergence_gate` fragment; update to assert via `resolve_fragments()` result rather than raw YAML [Agent 3 finding]
- `scripts/tests/test_doc_counts.py` — has `test_generator_evaluator_is_runnable` pattern; add parallel `test_enumerate_and_prove_is_runnable` for the new oracle [Agent 3 finding]

Breaking tests that must be updated alongside the loop conversions:
- `test_builtin_loops.py::TestRlCodingAgentLoop::test_score_error_routes_to_diagnose` — reads `score.route.error` from raw YAML; `route:` must remain at state level (not absorbed by the fragment) [Agent 3 finding]
- `test_builtin_loops.py::TestAgentEvalImproveLoop::test_route_quality_error_routes_to_diagnose` — same pattern for `route_quality.route.error` [Agent 3 finding]
- `test_builtin_loops.py::TestAdoptThirdPartyApiLoop::test_prove_delegates_to_ready_to_implement_gate` — asserts `prove.loop == "ready-to-implement-gate"`; breaks when `prove` is replaced by delegation to `oracles/enumerate-and-prove` [Agent 3 finding]
- `test_builtin_loops.py::TestIntegrateSdkLoop::test_prove_delegates_to_ready_to_implement_gate` — same breakage [Agent 3 finding]
- `test_builtin_loops.py::TestIntegrateSdkLoop::test_scan_branches_to_both_enumerate_states` — asserts `scan_existing_usage.on_yes == "enumerate_from_code"`; if routing target name changes this breaks [Agent 3 finding]

New tests to write in `test_fsm_fragments.py` (following `TestHarnessYamlFragments` / `TestCommonYamlNewFragments` three-tier pattern):
- `TestConvergenceGateFragment` class — presence in `lib/common.yaml`, `evaluate.type == "convergence"`, non-empty `description:`, resolves via `resolve_fragments()` with caller-supplied overrides [Agent 3 finding]
- `TestLlRubricScoreFragment` class — presence in `lib/harness.yaml`, `evaluate.type == "output_contains"`, non-empty `description:`, resolves via `resolve_fragments()` [Agent 3 finding]
- Note: `test_all_common_yaml_fragments_have_description` and `test_all_harness_yaml_fragments_have_description` (existing) will automatically enforce the `description:` field on both new fragments

New tests to write in `test_builtin_loops.py`:
- `TestEnumerateAndProveOracle` class — required states (`parse_enumeration`, `flatten`, `prove`, `done`, `failed`), `parameters` block has `raw_enumeration` as required, `done` is terminal [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/reference.md` — has `## Fragment Catalog` tables listing every fragment by lib file; add `convergence_gate` row to the `lib/common.yaml` table and `ll_rubric_score` row to the `lib/harness.yaml` table [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — has `#### lib/common.yaml — type-pattern fragments` and `#### lib/harness.yaml` subsection fragment tables; add rows for the two new fragments [Agent 2 finding]
- `docs/reference/loops.md` — `### Fragment dependency` section for the `generator-evaluator` entry mentions only `playwright_screenshot`; update to include `ll_rubric_score` after the `score` state adopts the fragment [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Add `convergence_gate` fragment** to `scripts/little_loops/loops/lib/common.yaml` under `fragments:`:
   - Default fields: `action_type: shell`, `evaluate: { type: convergence, direction: maximize }`
   - Required caller overrides: `action:`, `evaluate.target`, `evaluate.tolerance`, `route.target`, `route.progress`, `route.stall`
   - Optional caller override: `evaluate.previous` (used by `rl-coding-agent` and `harness-optimize` which have dedicated `persist_prev` states writing to captured variables)

2. **Add `ll_rubric_score` fragment** to `scripts/little_loops/loops/lib/harness.yaml`:
   - Extract body from `generator-evaluator.yaml`'s `score` state: prompt action with `${context.rubric}` and `${context.pass_threshold}`, `evaluate: { type: output_contains, pattern: "ALL_PASS" }`
   - Caller must supply `on_yes:` and `on_no:` (routing varies by loop)
   - Add `import: - lib/harness.yaml` to `generator-evaluator.yaml` if not already present

3. **Update `generator-evaluator.yaml`** — replace `score` state body with `fragment: ll_rubric_score` plus caller-specific `on_yes:` and `on_no:` routes

4. **Create `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml`** — new oracle sub-loop:
   - `parameters:` block: `raw_enumeration` (string, required — the captured LLM output containing the `ENUMERATE_JSON:` line), `max_retries` (string, optional), `tag` (string, optional, default `ENUMERATE_JSON` — allows callers to vary the tag prefix)
   - States: `parse_enumeration` (fragment: `parse_tagged_json`, python3 heredoc scanning for `ENUMERATE_JSON:`, evaluate: `output_json .count gt 0`), `flatten` (action_type: shell, python3 comma-join of `data["targets"]`), `prove` (loop: `ready-to-implement-gate`, with: targets/max_retries), `done`, `failed`
   - Design note: `integrate-sdk.yaml` carries extra fields (`branch`, `requires_credentials`) in the JSON; the oracle's `flatten` state need only emit the comma-joined targets — extra fields are not consumed downstream by `ready-to-implement-gate`

5. **Convert 5 convergence callers** to `fragment: convergence_gate`:
   - `test-coverage-improvement.yaml:extract_percentage` — add `action:` (grep pipeline), `evaluate.target: "${context.coverage_target}"`, `evaluate.tolerance: 1`, `route: { target: commit, progress: identify_gaps, stall: identify_gaps }`
   - `agent-eval-improve.yaml:route_quality` — `evaluate.target: "${context.quality_target}"`, `evaluate.tolerance: 0.03`, `route: { target: done, progress: refine_config, stall: done, error: diagnose }`
   - `rl-coding-agent.yaml:score` — `evaluate.target: "${context.reward_target}"`, `evaluate.tolerance: 0.05`, `evaluate.previous: "${captured.prev_reward.output}"`, `route: { target: done, progress: improve, stall: act, error: diagnose }`
   - `rl-policy.yaml:score` — `evaluate.target: "${context.reward_target}"`, `evaluate.tolerance: 0.05`, `route: { target: done, progress: improve, stall: act, error: diagnose }`
   - `harness-optimize.yaml:gate` — `evaluate.target: "${context.target_score}"`, `evaluate.tolerance: 0.02`, `evaluate.previous: "${captured.prev_score.output}"`, `route: { target: commit_and_log, progress: commit_and_log, stall: revert_and_log, error: revert_and_log }`

6. **Convert `adopt-third-party-api.yaml`** — replace `parse_enumeration` + `flatten_targets` + `prove` states with a single delegation state: `loop: oracles/enumerate-and-prove`, `with: { raw_enumeration: "${captured.raw_enumeration.output}", max_retries: "2" }`, `on_success: build_playbook`, `on_failure/on_error: build_playbook_partial`

7. **Convert `integrate-sdk.yaml`** — replace `parse_enumeration` + `flatten_surfaces` + `prove` states with delegation state: `loop: oracles/enumerate-and-prove`, `with: { raw_enumeration: "${captured.raw_enumeration.output}", max_retries: "${context.max_retries}" }`, `on_success: scaffold_integration`, `on_failure/on_error: diagnose_and_block`

8. Run `ll-loop validate` on all 11 modified files

9. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_fsm_evaluators.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Add `import: - lib/common.yaml`** to the 4 convergence-caller loops that currently lack it — `agent-eval-improve.yaml` (has only `lib/benchmark.yaml`), `rl-coding-agent.yaml` (no `import:` at all), `rl-policy.yaml` (no `import:` at all), `harness-optimize.yaml` (has only `lib/benchmark.yaml`). Without this, `resolve_fragments()` will raise "fragment 'convergence_gate' not found" at validation time.

11. **Update `skills/create-loop/reference.md`** — add `convergence_gate` row to the `lib/common.yaml` Fragment Catalog table and `ll_rubric_score` row to the `lib/harness.yaml` table.

12. **Update `docs/guides/LOOPS_GUIDE.md`** — add rows for `convergence_gate` and `ll_rubric_score` in the `#### lib/common.yaml` and `#### lib/harness.yaml` subsection fragment tables.

13. **Update `docs/reference/loops.md`** — add `ll_rubric_score` alongside `playwright_screenshot` in the `### Fragment dependency` section for the `generator-evaluator` entry.

14. **Update `scripts/tests/test_harness_optimize.py`** — `TestHarnessOptimizeStates::test_gate_has_convergence_evaluator` and `test_gate_routes_correctly` read inline YAML fields; update both to call `resolve_fragments()` and assert on the resolved state, or move assertions to check that the raw YAML contains a `fragment: convergence_gate` key instead of inline fields.

15. **Update `scripts/tests/test_builtin_loops.py`** breaking tests:
    - `TestRlCodingAgentLoop::test_score_error_routes_to_diagnose` and `TestAgentEvalImproveLoop::test_route_quality_error_routes_to_diagnose` — verify `route:` remains at state level (not in fragment) and update if routing assertions need adjustment.
    - `TestAdoptThirdPartyApiLoop::test_prove_delegates_to_ready_to_implement_gate` and `TestIntegrateSdkLoop::test_prove_delegates_to_ready_to_implement_gate` — update to assert delegation to `oracles/enumerate-and-prove` instead of `ready-to-implement-gate`.
    - `TestIntegrateSdkLoop::test_scan_branches_to_both_enumerate_states` — update routing target assertions if state name changes.

16. **Add `TestConvergenceGateFragment` and `TestLlRubricScoreFragment`** test classes to `scripts/tests/test_fsm_fragments.py` following the three-tier pattern of `TestHarnessYamlFragments`. Both new fragments must include a non-empty `description:` field or the existing `test_all_*_yaml_fragments_have_description` tests will fail.

17. **Add `TestEnumerateAndProveOracle`** class to `scripts/tests/test_builtin_loops.py` — assert required states, `parameters` block, `done` terminal, oracle loads with `is_runnable_loop()`.

18. **Add `test_enumerate_and_prove_is_runnable`** to `scripts/tests/test_doc_counts.py` following the `test_generator_evaluator_is_runnable` pattern.

19. Run full test suite: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_fsm_evaluators.py scripts/tests/test_harness_optimize.py scripts/tests/test_doc_counts.py -v --tb=short`

## Success Metrics

- `convergence_gate` fragment eliminates 5 duplicate convergence evaluator definitions
- `ll_rubric_score` fragment eliminates 5 duplicate rubric-scoring states
- `enumerate-prove-flow` eliminates 4 duplicated states across 2 integration loops
- All modified loops pass `ll-loop validate`
- Test suite passes with no regressions

## Scope Boundaries

- Fragment additions and flow extraction only — no behavioral changes
- `ll_rubric_score` should build on the `generator-evaluator` sub-loop from Wave 2 if applicable
- Only the listed loops; no new convergence or rubric patterns introduced

## API/Interface

N/A - No public API changes

## Impact

- **Priority**: P3 — Medium ROI; further standardizes evaluator patterns but builds on Waves 1-2
- **Effort**: Medium — 3 items across ~12 loops; `ll_rubric_score` design depends on Wave 2's sub-loop interface
- **Risk**: Low-Medium — Convergence fragment is trivial (pure evaluator); rubric fragment must handle varying criteria structures
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop composition and evaluator types |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions |

## Labels

`enhancement`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **High enumeration breadth and import wiring gap** — 4 convergence-caller loops (`agent-eval-improve`, `rl-coding-agent`, `rl-policy`, `harness-optimize`) currently have no `import: - lib/common.yaml` block (`rl-coding-agent` and `rl-policy` have NO import block at all); omitting wiring step 10 causes silent `convergence_gate` fragment-not-found errors at validate-time.
- **Four tests break mid-implementation** — `test_gate_has_convergence_evaluator` and `test_gate_routes_correctly` in `test_harness_optimize.py`; `test_prove_delegates_to_ready_to_implement_gate` (×2) in `test_builtin_loops.py`; update these in lockstep with their corresponding loop conversions rather than deferring all test fixes to the end.

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `c6dce40a-cc3b-4007-8d3c-a0949c8b5a06.jsonl`
- `/ll:wire-issue` - 2026-06-02T04:33:08 - `0a8c5ddf-318f-4392-9c7f-83c23c7dd911.jsonl`
- `/ll:refine-issue` - 2026-06-02T04:25:04 - `b2ffd042-1b9e-4f58-afe6-70becf622ec6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T20:39:39 - `878c5913-3278-47e9-865c-2f4ceb07948f.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T01:15:49 - `fe72aa2c-e995-4907-94b6-587fa28e4586.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): ENH-1775 (Wave 2) moves rubric scoring into the `generator-evaluator` sub-loop. After Wave 2, the 5 harness parent loops are thin wrappers delegating to that sub-loop — they no longer contain inline rubric states. This issue's `ll_rubric_score` fragment MUST target `loops/oracles/generator-evaluator.yaml` (the sub-loop), NOT the 5 parent wrapper loops. The `enumerate-prove-flow` shares `adopt-third-party-api.yaml` and `integrate-sdk.yaml` with Wave 2's `parse_tagged_json` fragment; the flow MUST compose from Wave 2's fragment. Coordinate fragment placement with ENH-1774 (uses `cli.yaml`) — use `common.yaml` for new fragments to maintain consistency across waves.

## Status

**Done** | Created: 2026-05-28 | Priority: P3

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-01
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1871: Wave 3a — Add `convergence_gate` Fragment and Convert 5 Convergence Callers
- ENH-1872: Wave 3b — Add `ll_rubric_score` Fragment and Update `generator-evaluator` Oracle
- ENH-1873: Wave 3c — Create `enumerate-and-prove` Oracle and Convert 2 Integration Loops

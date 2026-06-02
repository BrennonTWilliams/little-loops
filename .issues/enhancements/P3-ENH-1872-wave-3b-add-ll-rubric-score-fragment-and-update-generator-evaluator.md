---
id: ENH-1872
title: "Wave 3b \u2014 Add `ll_rubric_score` Fragment and Update `generator-evaluator`\
  \ Oracle"
type: ENH
status: done
priority: P3
parent: ENH-1776
depends_on: ENH-1775
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-02 05:22:59+00:00
---

# ENH-1872: Wave 3b — Add `ll_rubric_score` Fragment and Update `generator-evaluator` Oracle

## Summary

Add the `ll_rubric_score` shared evaluator fragment to `loops/lib/harness.yaml` and update the `generator-evaluator` oracle's `score` state to reference the fragment.

## Parent Issue

Decomposed from ENH-1776: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`

## Current Behavior

The `generator-evaluator.yaml` oracle's `score` state inlines a multi-criterion weighted rubric LLM prompt with `output_contains: ALL_PASS` routing. This rubric pattern is the same core structure that was duplicated across 5 harness loops before Wave 2 centralized it in the oracle.

## Expected Behavior

A `ll_rubric_score` fragment in `loops/lib/harness.yaml` holds the canonical rubric-scoring action and evaluator; the oracle's `score` state becomes `fragment: ll_rubric_score` plus caller-supplied `on_yes:` / `on_no:` routing.

## Proposed Solution

### Implementation Steps

1. **Add `ll_rubric_score` fragment** to `scripts/little_loops/loops/lib/harness.yaml`:
   - Alongside existing `playwright_screenshot` fragment
   - `action_type: prompt` with rubric prompt body referencing `${context.rubric}` and `${context.pass_threshold}`
   - `evaluate: { type: output_contains, pattern: "ALL_PASS" }`
   - Caller must supply `on_yes:` and `on_no:` (routing varies by loop)
   - Must include non-empty `description:` field (enforced by `test_all_harness_yaml_fragments_have_description`)

2. **Update `scripts/little_loops/loops/oracles/generator-evaluator.yaml`**:
   - Replace `score` state body with `fragment: ll_rubric_score` plus caller-specific `on_yes:` and `on_no:` routes
   - Add `import: - lib/harness.yaml` if not already present

3. **Add `TestLlRubricScoreFragment`** class to `scripts/tests/test_fsm_fragments.py` following the three-tier pattern of `TestHarnessYamlFragments`:
   - Presence in `lib/harness.yaml`
   - `evaluate.type == "output_contains"`
   - Non-empty `description:`
   - Resolves via `resolve_fragments()`

4. **Update docs** for `ll_rubric_score`:
   - `skills/create-loop/reference.md` — add row to `lib/harness.yaml` Fragment Catalog table
   - `docs/guides/LOOPS_GUIDE.md` — add row in `#### lib/harness.yaml` subsection fragment table
   - `docs/reference/loops.md` — add `ll_rubric_score` alongside `playwright_screenshot` in the `### Fragment dependency` section for `generator-evaluator`

5. Run `ll-loop validate` on `generator-evaluator.yaml`

6. Run `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle.test_score_uses_output_contains_all_pass` (line 5207) — replace assertions on inline `evaluate` dict (`type == "output_contains"`, `pattern == "ALL_PASS"`) with `assert state.get("fragment") == "ll_rubric_score"` to match the post-extraction YAML structure
8. Update `scripts/little_loops/loops/README.md` fragment library table row (line 167) for `lib/harness.yaml` — extend description to name both `playwright_screenshot` and `ll_rubric_score` fragments

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Fragment action body**: The current `score` state (`generator-evaluator.yaml:64–79`) references **three** context variables: `${context.run_dir}`, `${context.rubric}`, and `${context.pass_threshold}`. The `ll_rubric_score` fragment's `action:` body must include all three so callers that don't override `action:` get the full rubric prompt. The `pass_threshold` default (`6`) and `rubric` default (`""`) are declared at the loop's `context:` block (line 40–42) and in `parameters:` (lines 23–29) — the fragment itself does not need to re-declare defaults.

**`import:` already present**: `generator-evaluator.yaml:36–37` already contains `import: - lib/harness.yaml`. Step 2 requires no conditional import add — it is guaranteed.

**Score state routing to preserve**: After extracting to the fragment, the caller state retains `on_yes: done`, `on_no: generate`, `on_error: generate` (these are caller-supplied and are NOT part of the fragment body).

**Test tier-3 assertions**: `TestLlRubricScoreFragment` Tier 3 (`resolve_fragments` integration) must assert `action_type == "prompt"` (not `"shell"`), `evaluate["type"] == "output_contains"`, `evaluate["pattern"] == "ALL_PASS"`, and `"fragment" not in state`. Re-use the `_load_harness_yaml()` static helper defined at `test_fsm_fragments.py:TestHarnessYamlFragments:1389–1400` — either copy it into the new class or call the sibling class's method. The analogous prompt-type test class to follow is `TestScorePlanQualityFragment` (lines 1267–1323).

**Doc table column counts differ by file**:
- `skills/create-loop/reference.md` `### lib/harness.yaml fragments` table (line ~1140) — **3 columns**: `Fragment | Provides | Caller must supply`
- `docs/guides/LOOPS_GUIDE.md` `#### lib/harness.yaml` subsection (line ~3285) — **4 columns**: `Fragment | Description | Provides | Caller must supply`
- `docs/reference/loops.md` `### Fragment dependency` (line ~236) — **one sentence**; extend to mention `ll_rubric_score` alongside `playwright_screenshot` and state it is used in the `score` state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/harness.yaml` — add `ll_rubric_score` fragment alongside `playwright_screenshot`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — replace `score` state with `fragment: ll_rubric_score`; add `import: - lib/harness.yaml` if missing
- `scripts/tests/test_fsm_fragments.py` — add `TestLlRubricScoreFragment` class
- `skills/create-loop/reference.md` — add `ll_rubric_score` row to harness.yaml table
- `docs/guides/LOOPS_GUIDE.md` — add `ll_rubric_score` row
- `docs/reference/loops.md` — update `generator-evaluator` fragment dependency section

### Dependent Files (read-only)
- `scripts/little_loops/fsm/fragments.py:resolve_fragments()` — no changes; validates fragment keys and merges fields

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/html-website-generator.yaml` — delegates to `oracles/generator-evaluator` as sub-loop; no changes needed but must still pass `rubric` and `pass_threshold` in `with:` [Agent 1 finding]
- `scripts/little_loops/loops/html-anything.yaml` — delegates to `oracles/generator-evaluator` as sub-loop [Agent 1 finding]
- `scripts/little_loops/loops/hitl-md.yaml` — delegates to `oracles/generator-evaluator` as sub-loop [Agent 1 finding]
- `scripts/little_loops/loops/p5js-sketch-generator.yaml` — delegates to `oracles/generator-evaluator` as sub-loop [Agent 1 finding]
- `scripts/little_loops/loops/svg-image-generator.yaml` — delegates to `oracles/generator-evaluator` as sub-loop [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — fragment library table row (line 167) describes `lib/harness.yaml` as containing only `playwright_screenshot`; must update to mention `ll_rubric_score` [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestGeneratorEvaluatorOracle.test_score_uses_output_contains_all_pass` (line 5207) — **BREAKING**: asserts inline `evaluate.type == "output_contains"` and `evaluate.pattern == "ALL_PASS"` directly on the `score` state; after fragment extraction the state only has `fragment: ll_rubric_score` with no inline `evaluate` block — must update to assert `state.get("fragment") == "ll_rubric_score"` [Agent 3 finding]

### Similar Patterns
- `scripts/little_loops/loops/lib/harness.yaml:playwright_screenshot` — reference for fragment shape and placement in harness.yaml
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:score` — source state to extract into the fragment

## Success Metrics

- `ll_rubric_score` fragment present in `lib/harness.yaml`
- `generator-evaluator.yaml` passes `ll-loop validate` with `fragment: ll_rubric_score`
- `TestLlRubricScoreFragment` passes
- No regressions in `test_builtin_loops.py`

## Impact

- **Priority**: P3 - Reduces inline duplication in the oracle's `score` state; part of Wave 3 harness centralization
- **Effort**: Small - One fragment addition, one state replacement, one test class, three doc table rows
- **Risk**: Low - Fragment extraction preserves existing behavior; test suite in `test_builtin_loops.py` validates oracle
- **Breaking Change**: No (test assertions updated in same PR)

## Scope Boundaries

**In scope**: Adding `ll_rubric_score` to `lib/harness.yaml`; replacing `score` state body in `generator-evaluator.yaml`; updating `TestGeneratorEvaluatorOracle.test_score_uses_output_contains_all_pass`; adding `TestLlRubricScoreFragment`; updating three doc tables.

**Out of scope**: Changes to the 5 sub-loop callers (`html-website-generator`, `html-anything`, `hitl-md`, `p5js-sketch-generator`, `svg-image-generator`) — they already pass `rubric` and `pass_threshold` in `with:` and require no changes. No behavioral changes to scoring logic itself.

## Labels

`loops`, `harness`, `enhancements`, `wave-3`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-02T05:18:45 - `e98841da-665b-4a6e-ae0a-5bd3c3bb3bfe.jsonl`
- `/ll:wire-issue` - 2026-06-02T05:13:30 - `185e8111-8d9d-4a78-b133-681b1a67f9e9.jsonl`
- `/ll:refine-issue` - 2026-06-02T05:09:04 - `886f12cb-b6f2-4ced-bf07-b455102c72d1.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `7dcd5926-1318-4ce3-9453-ad5366eda2c9.jsonl`

---
id: ENH-1872
title: "Wave 3b — Add `ll_rubric_score` Fragment and Update `generator-evaluator` Oracle"
type: ENH
priority: P3
parent: ENH-1776
depends_on: ENH-1775
size: Small
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

### Similar Patterns
- `scripts/little_loops/loops/lib/harness.yaml:playwright_screenshot` — reference for fragment shape and placement in harness.yaml
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:score` — source state to extract into the fragment

## Success Metrics

- `ll_rubric_score` fragment present in `lib/harness.yaml`
- `generator-evaluator.yaml` passes `ll-loop validate` with `fragment: ll_rubric_score`
- `TestLlRubricScoreFragment` passes
- No regressions in `test_builtin_loops.py`

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`

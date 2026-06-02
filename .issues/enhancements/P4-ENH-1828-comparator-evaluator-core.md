---
id: ENH-1828
title: "Comparator Evaluator \u2014 Core Implementation"
type: ENH
priority: P4
status: done
parent: ENH-1793
depends_on:
- ENH-1792
- FEAT-1790
labels:
- enhancement
- loops
- evaluator
- regression-detection
size: Large
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-31 23:20:09+00:00
---

# ENH-1828: Comparator Evaluator — Core Implementation

## Summary

Implement the `comparator` evaluator type in the FSM harness: schema extension, evaluator function wrapping `evaluate_blind_comparator()`, validation rules, dispatcher wiring, and all associated tests and documentation for the evaluator itself.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — add `evaluate_comparator()` function (insert after `evaluate_blind_comparator` at ~line 1082, before `evaluate()` at line 1085); add `elif` branch to dispatcher; do NOT touch `_EXIT_CODE_AWARE_EVALUATORS`
- `scripts/little_loops/fsm/schema.py` — extend `EvaluateConfig.type` Literal (line 56) and add new optional fields; update `to_dict()`/`from_dict()`
- `scripts/little_loops/fsm/validation.py` — add `"comparator"` to `EVALUATOR_REQUIRED_FIELDS` (line 64); update `NON_LLM_EVALUATOR_TYPES` exclusion set (line 77); update MR-1 prose in `_validate_meta_loop_evaluation()` (~lines 959–965)
- `scripts/little_loops/fsm/__init__.py` — add `evaluate_comparator` to import block (line 87 area) and `__all__` (line 164+)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — extend `evaluateConfig` with `comparator` type and required `baseline_path`; add `if/then` conditional to enforce `baseline_path` as required when `type == "comparator"`, following the existing per-type conditional pattern
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Evaluation Phases section
- `docs/guides/LOOPS_GUIDE.md` — evaluator table (~line 1628)
- `docs/generalized-fsm-loop.md` — inline YAML type-list comment at line 305
- `docs/reference/API.md` — new evaluator type entry; add `evaluate_comparator` to import block example alongside `evaluate_blind_comparator`; add `"comparator"` to `EvaluateConfig.type` Literal block (~line 4222–4228)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — `_EVALUATE_TYPE_DISPLAY` dict (line 863) maps evaluator type strings to display labels; add `"comparator": "comparator"` (or a humanized label) so `ll-loop show` renders it cleanly rather than falling through to the raw string

### Tests to Add/Update
- `scripts/tests/test_fsm_evaluators.py` — add `TestComparatorEvaluator`; update `TestEvaluateDispatcher` parametrize lists (exit_code_124 list at line 552; nonzero_generalized list at line 611; do NOT touch nonzero_exit_code_aware list at line 633)
- `scripts/tests/test_fsm_schema.py` — add roundtrip tests following `TestMcpToolSchema` pattern (~line 1877)
- `scripts/tests/test_fsm_validation.py` — add `TestComparatorEvaluatorValidation` following `TestHarborScorerEvaluatorValidation` (~line 345)
- `scripts/tests/test_fsm_schema_fuzz.py` — add `"comparator"` to `valid_types` list at line 44

### Key Existing Anchors
- `evaluate_blind_comparator()` — `evaluators.py:911` (last evaluator before dispatcher; `evaluate_comparator` inserts after it)
- `evaluate()` dispatcher — `evaluators.py:1085` (not 953 — see research correction below)
- `_EXIT_CODE_AWARE_EVALUATORS` — function-local frozenset inside `evaluate()`, lines 1121–1130 (6 current members: exit_code, mcp_result, harbor_scorer, diff_stall, action_stall, llm_structured)
- `EvaluateConfig.type` Literal — `schema.py:56–67` (10 current types; `"comparator"` absent)
- `EVALUATOR_REQUIRED_FIELDS` — `validation.py:64` (10 entries); `NON_LLM_EVALUATOR_TYPES` is DERIVED from it at line 77 (not a separate literal set)
- `evaluate_blind_comparator` FSM export — `fsm/__init__.py:87` and `__all__` at line 222

### Research Corrections

_Added by `/ll:refine-issue` — codebase analysis identified these corrections to the Implementation Steps:_

1. **Dispatcher line number**: `evaluate()` is at `evaluators.py:1085`, not line 953 as stated in the Dispatcher section heading. The if/elif chain ends at line 1264 with an `else: raise ValueError`.
2. **`evaluate_comparator` insertion point**: Should be inserted AFTER `evaluate_blind_comparator` (~line 1082 end), BEFORE `evaluate()` (line 1085). The heading reference "evaluators.py:779" is stale — line 779 is mid-file between `evaluate_harbor_scorer` (701) and `evaluate_llm_structured` (740). The natural insertion point is ~line 1083.
3. **Top-level `__init__.py` is a no-op**: `scripts/little_loops/__init__.py` imports ONLY `RouteContext, RouteDecision` from `little_loops.fsm` — it has NO evaluator function exports at all. Skip the step that adds `evaluate_comparator` there; only `scripts/little_loops/fsm/__init__.py` needs updating.
4. **`_validate_harness_multimodal_evaluator_blind_spot` investigation resolved**: The function only checks `state.evaluate.type != "output_contains"` — it does not enumerate other types. Adding `"comparator"` to any registry has NO effect on this function. No update needed.
5. **`evaluate_blind_comparator` returns `dict[str, Any]`**, not `EvaluationResult`. `evaluate_comparator()` must build and return an `EvaluationResult` from the dict keys (`harness_pass`, `baseline_pass`, `confidence`, `reason`, `raw`).

## Parent Issue

Decomposed from ENH-1793: Blind Cross-Iteration Comparator

## Proposed Solution

Add `evaluate_comparator()` — a thin wrapper around the already-landed `evaluate_blind_comparator()` — that reads a baseline from disk, runs N blind A/B comparisons (`min_pairs`), takes a majority vote, and returns `yes`/`no`/`tie`/`no_baseline`. Extend the schema and validation to recognize the new type and enforce MR-1 correctly (comparator calls the LLM and must NOT satisfy MR-1's non-LLM requirement).

## Implementation Steps

### Schema (`scripts/little_loops/fsm/schema.py:56–66`)

Extend `EvaluateConfig.type` `Literal[...]` with `"comparator"`. Add optional fields:
- `baseline_path: str | None = None`
- `auto_promote: bool = False`
- `min_pairs: int = 1`

Extend `from_dict()` / `to_dict()` with `.get()` reads and serialization.

### Evaluator function (`scripts/little_loops/fsm/evaluators.py:779`)

Add `evaluate_comparator(config: EvaluateConfig, output: str, context: InterpolationContext) -> EvaluationResult`:

1. Read `Path(config.baseline_path) / "output.txt"` → `no_baseline` if missing
2. Call `evaluate_blind_comparator(output_harness, output_baseline, prompt=config.prompt)` in a loop `config.min_pairs` times
3. Majority vote: `harness_pass` count vs `baseline_pass` count → `yes`/`no`/`tie`
4. If `auto_promote=True` and verdict is `yes`, write `output` to `<baseline_path>/output.txt`

**`evaluate_blind_comparator()` signature (verified, FEAT-1790 landed at `evaluators.py:911`):**
```python
def evaluate_blind_comparator(
    output_harness: str,
    output_baseline: str,
    prompt: str | None = None,
    model: str = DEFAULT_LLM_MODEL,
    timeout: int = 1800,
) -> dict[str, Any]:
```
Return dict keys: `harness_pass` (bool), `baseline_pass` (bool), `confidence` (float), `reason` (str), `raw` (dict).

Do NOT add `"comparator"` to `_EXIT_CODE_AWARE_EVALUATORS` (function-local frozenset at line 1121; being IN the set exempts from nonzero-exit short-circuit — comparator must remain outside so non-zero action exit → `verdict="error"`).

### Dispatcher (`scripts/little_loops/fsm/evaluators.py:953`)

Add `elif eval_type == "comparator": return evaluate_comparator(config, output, context)` in the `evaluate()` dispatcher.

### Validation (`scripts/little_loops/fsm/validation.py:64`)

1. Add `"comparator": ["baseline_path"]` to `EVALUATOR_REQUIRED_FIELDS`
2. Update `NON_LLM_EVALUATOR_TYPES` exclusion — comparator calls the LLM via `evaluate_blind_comparator()` and must NOT satisfy MR-1:

```python
NON_LLM_EVALUATOR_TYPES: frozenset[str] = frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {
    "llm_structured",
    "comparator",
}
```

3. Update MR-1 `ValidationError` prose in `_validate_meta_loop_evaluation()` (~lines 960–965) to include `comparator` in the human-readable hint string.

### Module exports

- `scripts/little_loops/fsm/__init__.py` — export `evaluate_comparator` alongside `evaluate_blind_comparator`
- ~~`scripts/little_loops/__init__.py`~~ — **skip this**: Research Correction #3 confirmed the top-level `__init__.py` has no evaluator exports whatsoever (imports only `RouteContext, RouteDecision`). No update needed there.

### Baseline storage convention

Use `.loops/baselines/<loop>/output.txt` (sibling of `runs/`, not inside timestamped run dirs). Document in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` Evaluation Phases section.

### JSON Schema

`scripts/little_loops/fsm/fsm-loop-schema.json` — extend `evaluateConfig` with `comparator` type and required `baseline_path` field.

## Tests

### `scripts/tests/test_fsm_evaluators.py`

Add `TestComparatorEvaluator` class; mock at `little_loops.fsm.evaluators.subprocess.run`; patch `little_loops.fsm.evaluators.random.choice` for shuffle tests:
- `test_no_baseline_when_file_missing` — no file → `no_baseline` verdict
- `test_harness_wins` — majority `harness_pass=True` → `yes`
- `test_baseline_wins` — majority `baseline_pass=True` → `no`
- `test_tie` — equal counts → `tie`
- `test_auto_promote_writes_file` — `auto_promote=True` + `yes` → writes `output.txt`
- `test_shuffle_correctness` — judge prompt is always symmetric

Update `TestEvaluateDispatcher`:
- Add `"comparator"` to `test_dispatch_exit_code_124_short_circuits_to_error` parametrize list at lines 551–562 (all types receive the exit_code=124 timeout short-circuit)
- Do NOT add to `test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators` list (comparator is not exit-code-aware)
- Add `"comparator"` to `test_dispatch_nonzero_exit_generalized_short_circuit` parametrize list (exit-code-blind evaluators: non-zero action exit → `verdict="error"`)

### `scripts/tests/test_fsm_schema.py`

Add `EvaluateConfig` roundtrip tests following `TestMcpToolSchema` at line 1859:
- `test_comparator_evaluator_type_is_valid`
- `test_comparator_round_trips_through_dict`
- `test_comparator_baseline_path_field_roundtrip`
- `test_comparator_auto_promote_field_roundtrip`
- `test_comparator_min_pairs_field_roundtrip`

### `scripts/tests/test_fsm_validation.py`

Add `TestComparatorEvaluatorValidation` class following `TestHarborScorerEvaluatorValidation` at line 345:
- `test_comparator_requires_baseline_path` — validates `EVALUATOR_REQUIRED_FIELDS` entry
- `test_mr1_fires_for_meta_loop_with_only_comparator_evaluator` — validates `NON_LLM_EVALUATOR_TYPES` exclusion

Investigate `TestHarnessMultimodalEvaluatorBlindSpot.test_does_not_fire_with_non_output_contains_evaluator` — check whether `_validate_harness_multimodal_evaluator_blind_spot` hardcodes evaluator type checks that could incorrectly match `comparator`; update if needed.

### `scripts/tests/test_fsm_schema_fuzz.py`

Add `"comparator"` to `valid_types` list at line 44.

## Documentation

- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add comparator to Evaluation Phases, placement guidance: after `check_semantic` (or replacing it for regression-sensitive harnesses)
- `docs/guides/LOOPS_GUIDE.md` — new `comparator` row in evaluator table with: verdicts (`yes`/`no`/`tie`/`no_baseline`), LLM-based flag, required `baseline_path`
- `docs/generalized-fsm-loop.md` — inline YAML comment at line 305 — add `"comparator"` to the type list
- `docs/reference/CLI.md` — **do NOT add `comparator` to the MR-1 non-LLM evaluator list** (~line 460); `comparator` is LLM-based (excluded from `NON_LLM_EVALUATOR_TYPES`) and does NOT belong in the non-LLM "safe" list. No change needed to this file.
- `docs/reference/API.md` — document new evaluator type

## Acceptance Criteria

- [x] `evaluate_comparator()` correctly identifies better output in ≥90% of controlled A/B test pairs
- [x] Bootstrap path works: first run with no baseline auto-promotes and routes `yes`
- [x] Parity errors route as `tie` → `yes` without stalling
- [x] Zero instances of label-leakage — judge prompt is always symmetric and blind
- [x] `NON_LLM_EVALUATOR_TYPES` excludes `"comparator"` so MR-1 is correctly enforced
- [x] All dispatcher parametrize lists updated correctly
- [x] Tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py -v -k "comparator"`

## Resolution

Implemented `evaluate_comparator()` as a thin wrapper around `evaluate_blind_comparator()` that reads a baseline from `.loops/baselines/<loop>/output.txt`, runs `min_pairs` blind A/B comparisons, takes a majority vote, and returns `yes`/`no`/`tie`/`no_baseline`. Bootstrap path (no baseline + `auto_promote=True`) promotes the first output and returns `yes`. Extended schema, validation, dispatcher, FSM `__init__`, `_EVALUATE_TYPE_DISPLAY`, and JSON schema. Four test files and four doc files updated. All 35 targeted tests pass; ruff clean.

## Session Log
- `/ll:ready-issue` - 2026-05-31T23:09:30 - `b962a168-f6c5-436e-bdf4-86254ad51309.jsonl`
- `/ll:wire-issue` - 2026-05-31T23:04:48 - `1a13ed93-b8a7-49c2-8baf-bbb2652aa866.jsonl`
- `/ll:refine-issue` - 2026-05-31T22:56:12 - `36204f50-5197-4f00-8190-750426767650.jsonl`
- `/ll:issue-size-review` - 2026-05-31T00:00:00 - `328bc3bf-da89-4021-981a-e4291a0ad2e5.jsonl`
- `/ll:confidence-check` - 2026-05-31T23:30:00 - `936a6f6c-c23b-4cea-8c24-915f50c68bb7.jsonl`
- `/ll:manage-issue` - 2026-05-31T23:20:09Z - `7352193a-c9c9-481a-ac33-751f341773fe.jsonl`

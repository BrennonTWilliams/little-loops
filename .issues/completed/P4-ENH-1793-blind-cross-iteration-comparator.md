---
id: ENH-1793
title: Blind Cross-Iteration Comparator
type: ENH
priority: P4
captured_at: '2026-05-29T19:08:54Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: done
depends_on:
- ENH-1792
labels:
- enhancement
- loops
- evaluator
- regression-detection
parent: EPIC-1663
confidence_score: 100
outcome_confidence: 74
score_complexity: 9
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 25
size: Very Large
---

# ENH-1793: Blind Cross-Iteration Comparator

## Summary

Add a `check_comparator` evaluator that performs an anonymized A/B comparison between the current iteration's output and a previously-successful output stored in `.loops/runs/<loop>/baseline/`. Catches *quality regressions* that the absolute `check_semantic` YES/NO judge misses — outputs that still pass the threshold but are objectively worse than what the harness produced before.

## Current Behavior

The `check_semantic` evaluator is the sole quality gate for harness outputs. It grades each iteration's output against a fixed prompt and routes on YES/NO. While effective for catching catastrophic failures, this absolute threshold model is blind to gradual output degradation — a run that returns "summary is reasonable" YES on a one-paragraph stub and on a three-paragraph well-cited revision treats them as equivalent.

## Expected Behavior

A new `comparator` evaluator type enables blind A/B comparison between current iteration output and a previously-successful baseline. The harness can detect quality regressions (outputs that pass the absolute threshold but are objectively worse than prior runs) and route accordingly — advancing only when the new output equals or beats the baseline. On first run (no baseline), the comparator bootstraps by auto-promoting the current output as the initial baseline.

## Motivation

Our current `check_semantic` evaluator is *absolute*: it grades each iteration's output against a fixed prompt and routes on YES/NO. This is fine for catching catastrophic failures but blind to gradual degradation. A run that returns "summary is reasonable" YES on a one-paragraph stub *and* on a three-paragraph well-cited revision treats them as equivalent.

`revfactory/harness`'s "Comparator" agent (`references/skill-testing-guide.md` §5-2) addresses this with *blind A/B* — two outputs anonymized as A and B, judge picks which is better. This is a different signal from absolute scoring:
- Absolute judge: "Is this acceptable?" (binary, threshold-based)
- Comparator: "Is this better than what we had?" (ordinal, drift-detecting)

Use it to catch regressions when refining harness prompts, models, or skills.

This depends on having a reliable previous baseline to compare against. Sequencing: ship FEAT-1790 (A/B baseline) and ENH-1792 (variance diagnostics) first — both produce the data this evaluator consumes. Hence P4.

## Proposed Solution

Add a `comparator` evaluator that performs anonymized A/B comparison between the current iteration's output and a previously-successful baseline stored in `.loops/runs/<loop>/baseline/`. The evaluator:

1. Reads the current output and the baseline output
2. Randomly shuffles labels (A/B) so the judge cannot tell which is which
3. Calls the host runner with a comparison prompt (e.g. "Which output better satisfies the refinement criteria — A or B?")
4. Returns `yes` (current wins majority), `no` (baseline wins), `tie` (within noise threshold), or `no_baseline` (first run)
5. Optionally auto-promotes current to baseline on `yes` (configurable via `auto_promote`)

New module in `scripts/little_loops/evaluators/`. Schema extension to `ll-loop validate` for `action_type: comparator` with required `baseline_path`. Manual baseline management via `ll-loop promote-baseline <loop>`.

## Success Metrics

- [ ] Comparator correctly identifies the better output in ≥90% of controlled A/B test pairs (5 known pairs: 2 current-wins, 2 baseline-wins, 1 tie)
- [ ] Bootstrap path works: first run with no baseline auto-promotes and routes `yes`
- [ ] Parity errors (A=B within noise) route as `tie` → `yes` without stalling the loop
- [ ] Zero instances of label-leakage — judge prompt is always symmetric and blind to which is current vs baseline

## Use Case

A harness author updates a `check_semantic` prompt to be "less strict" because too many runs were failing. Subsequent runs all pass — but the outputs are now visibly worse. With a comparator gate:

```yaml
check_comparator:
  action_type: comparator
  baseline_path: ".loops/runs/harness-refine-issue/baseline/"
  evaluate:
    type: comparator
    prompt: >
      Which output better satisfies the refinement criteria —
      A or B? Consider depth of analysis, codebase grounding,
      and concrete actionability.
  on_yes: advance      # current beats baseline → advance, update baseline
  on_no: execute       # baseline still better → retry
```

The judge sees both outputs labelled only `A` and `B` (random shuffle per call) without knowing which is the new candidate. If the new output wins on majority of pairs across N items, baseline gets refreshed; otherwise the harness is flagged as having regressed.

## API/Interface

New evaluator kind:

```yaml
evaluate:
  type: comparator
  baseline_path: <dir>          # where prior successful outputs live
  prompt: <comparison criteria> # the judge's question
  min_pairs: 3                  # require N comparisons before deciding
```

Verdicts:
- `yes` — current wins ≥ majority of pairs
- `no` — baseline wins majority
- `tie` — within noise threshold (route same as `yes` to avoid stalling)
- `no_baseline` — first run with no prior to compare against (route same as `yes` to bootstrap)

Baseline management: on `yes`, optionally promote current outputs to baseline (configurable `auto_promote: true|false`). Manual promotion via `ll-loop promote-baseline <loop>`.

## Implementation Steps

1. **Baseline storage convention** — `.loops/runs/<loop>/baseline/<item_id>.txt` (or similar). Document in run-directory schema.
2. **Comparator evaluator** — new module in `scripts/little_loops/evaluators/`. Reads baseline + current output, randomly shuffles labels, calls host runner with comparison prompt, parses YES/NO/TIE.
3. **Schema** — extend `ll-loop validate` to accept `action_type: comparator` and required `baseline_path`.
4. **Baseline lifecycle** — `auto_promote` config + `ll-loop promote-baseline <loop>` CLI for manual control.
5. **Tests** — pytest cases: current-wins, baseline-wins, tie, no-baseline (bootstrap), shuffle correctness (judge never sees consistent labelling).
6. **Docs** — add to `AUTOMATIC_HARNESSING_GUIDE.md` Evaluation Phases, placement guidance: after `check_semantic` (or replacing it for regression-sensitive harnesses).

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references for each step:_

1. **`fsm/schema.py:56–66`** — Extend `EvaluateConfig.type` `Literal[...]` with `"comparator"`; add `baseline_path: str | None = None`, `auto_promote: bool = False`, `min_pairs: int = 1` as optional fields; extend `from_dict()` with `.get()` reads and `to_dict()` serialization
2. **`fsm/validation.py:64`** — Add `"comparator": ["baseline_path"]` to `EVALUATOR_REQUIRED_FIELDS`; explicitly add `"comparator"` to `NON_LLM_EVALUATOR_TYPES` exclusion (it calls the LLM — must not satisfy MR-1's non-LLM pairing requirement; currently derived as `frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {"llm_structured"}` which would incorrectly include it)
3. **`fsm/evaluators.py:779`** — Add `evaluate_comparator(config: EvaluateConfig, output: str, context: InterpolationContext) -> EvaluationResult` near `evaluate_blind_comparator()`; reads `Path(config.baseline_path) / "output.txt"` (→ `no_baseline` if missing), calls `evaluate_blind_comparator()` `config.min_pairs` times with majority vote, maps to `yes`/`no`/`tie`, optionally writes `output` to baseline on `auto_promote`
4. **`fsm/evaluators.py:953`** — Add `elif eval_type == "comparator": return evaluate_comparator(config, output, context)` in the `evaluate()` dispatcher; add `"comparator"` to `_EXIT_CODE_AWARE_EVALUATORS` so action failures short-circuit to `error` before baseline comparison
5. **`fsm/__init__.py`** — Add `evaluate_comparator` to module exports alongside `evaluate_blind_comparator`
6. **Baseline storage** — Use `.loops/baselines/<loop>/output.txt` convention (sibling of `runs/`, not inside timestamped run dirs); document in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` Evaluation Phases
7. **`cli/loop/__init__.py`** — Add `promote-baseline` subcommand: takes `<loop>` arg, finds latest run's harness output in `.loops/runs/<loop>-*/`, copies to `.loops/baselines/<loop>/output.txt`; run `ll-loop promote-baseline <loop>`
8. **`scripts/tests/test_fsm_evaluators.py`** — Add `TestComparatorEvaluator` class; mock `little_loops.fsm.evaluators.subprocess.run`; patch `little_loops.fsm.evaluators.random.choice` for shuffle tests; test cases: `no_baseline` (no file → `no_baseline` verdict), `harness_wins` (majority `harness_pass=True` → `yes`), `baseline_wins` (majority `baseline_pass=True` → `no`), `tie` (equal → `tie`), `auto_promote_writes_file`, `shuffle_correctness`
9. **Run tests**: `python -m pytest scripts/tests/test_fsm_evaluators.py -v -k "comparator"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/tests/test_fsm_evaluators.py::TestEvaluateDispatcher` — add `"comparator"` to the `test_dispatch_exit_code_124_short_circuits_to_error` parametrize list at lines 551–562 (and the correct `test_dispatch_nonzero_exit_*` list at lines 621–627); these will break at import time once `"comparator"` is a valid dispatch type
11. Add `TestComparatorEvaluatorValidation` to `scripts/tests/test_fsm_validation.py` — `test_comparator_requires_baseline_path` (validates `EVALUATOR_REQUIRED_FIELDS` entry) and `test_mr1_fires_for_meta_loop_with_only_comparator_evaluator` (validates `NON_LLM_EVALUATOR_TYPES` exclusion); follow `TestHarborScorerEvaluatorValidation` pattern
12. Add comparator schema tests to `scripts/tests/test_fsm_schema.py` — `EvaluateConfig` roundtrip for each new field (`baseline_path`, `auto_promote`, `min_pairs`); follow `TestMcpToolSchema` at line 1859
13. Add `test_promote_baseline_subcommand_registered` to `scripts/tests/test_ll_loop_execution.py::TestCmdSimulate` and `test_promote_baseline_no_runs` to `scripts/tests/test_ll_loop_integration.py`; follow `test_diagnose_evaluators_*` patterns
14. Add `"comparator"` to `valid_types` list in `scripts/tests/test_fsm_schema_fuzz.py` at line 44
15. Update `docs/guides/LOOPS_GUIDE.md` evaluator table — new `comparator` row with: verdicts (`yes`/`no`/`tie`/`no_baseline`), LLM-based flag, required `baseline_path`
16. Update `docs/generalized-fsm-loop.md` inline YAML comment (line 305) — add `"comparator"` to the type list
17. Update `.claude/CLAUDE.md` `## CLI Tools` section — add `ll-loop promote-baseline` entry

### Corrections & Clarifications (Refine Pass 2)

_Added by `/ll:refine-issue` — corrections to findings from previous refine pass, verified against live code:_

**Step 4 — `_EXIT_CODE_AWARE_EVALUATORS` (CORRECTED):** Do NOT add `"comparator"` to `_EXIT_CODE_AWARE_EVALUATORS`. The set is a function-local frozenset inside `evaluate()` at line 1121; being IN the set EXEMPTS an evaluator from the nonzero-exit short-circuit (opposite of what step 4 stated). Since comparator should produce `verdict="error"` when the action fails (no meaningful output to compare), it must remain outside the set — which is the default. Only add the `elif eval_type == "comparator": return evaluate_comparator(config, output, context)` dispatch branch; no change to `_EXIT_CODE_AWARE_EVALUATORS`.

**Step 2 — `NON_LLM_EVALUATOR_TYPES` derivation (CLARIFIED):** The derivation at `validation.py:79–81` is `frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {"llm_structured"}`. After adding `"comparator"` to `EVALUATOR_REQUIRED_FIELDS`, it will be automatically included in `NON_LLM_EVALUATOR_TYPES` — which is WRONG since `evaluate_comparator()` calls the LLM via `evaluate_blind_comparator()`. Must update the exclusion set:

```python
NON_LLM_EVALUATOR_TYPES: frozenset[str] = frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {
    "llm_structured",
    "comparator",
}
```

**Wiring step 10 — parametrize list (CORRECTED):** Add `"comparator"` to the **first** parametrize list only (`test_dispatch_exit_code_124_short_circuits_to_error` at lines 551–562 — all types receive the exit_code=124 timeout short-circuit). Do NOT add to the **second** list (`test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators` at lines 621–627) — that list covers exit-code-aware evaluators exempt from nonzero-exit short-circuit, and `"comparator"` is explicitly not in that set.

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

`evaluate_comparator()` calls this in a loop `min_pairs` times, passing `config.prompt`. Return dict keys: `harness_pass` (bool), `baseline_pass` (bool), `confidence` (float), `reason` (str), `raw` (dict). Error paths set both to `False` with `confidence=0.0`. Majority vote: count `harness_pass=True` vs `baseline_pass=True` across N calls; equal counts → `tie`.

### Wiring Phase 2 (added by `/ll:wire-issue`)

_Additional touchpoints identified in second wiring pass:_

18. Update `scripts/little_loops/__init__.py` — add `evaluate_comparator` to the existing `from little_loops.fsm.evaluators import (...)` block and to `__all__`; the package already exports `evaluate_blind_comparator` via the same mechanism
19. Update `scripts/little_loops/cli/loop/info.py` — add `"comparator": "blind comparator"` (or similar label) to `_EVALUATE_TYPE_DISPLAY` dict so `ll-loop show --verbose` renders a human-readable label instead of the raw string
20. Update `scripts/little_loops/fsm/validation.py` — in `_validate_meta_loop_evaluation()` (~lines 960–965), add `comparator` to the human-readable prose enumeration in the `ValidationError` message; the `NON_LLM_EVALUATOR_TYPES` set logic is auto-correct once step 2 is done, only the hint string needs updating
21. Confirm `scripts/little_loops/cli/loop/__init__.py` `known_subcommands` set (lines 47–75) includes `"promote-baseline"` — step 7 adds the subcommand handler but this guard also must be updated or `ll-loop promote-baseline` is treated as a loop name
22. Update `scripts/tests/test_fsm_evaluators.py::TestEvaluateDispatcher.test_dispatch_nonzero_exit_generalized_short_circuit` parametrize list — add `"comparator"` (evaluator is exit-code-blind; non-zero action exit code → `verdict="error"`)
23. Update `docs/reference/CLI.md` — add `comparator` to the non-LLM evaluator enumeration in the MR-1 rule section (~line 460)
24. Investigate `scripts/tests/test_fsm_validation.py::TestHarnessMultimodalEvaluatorBlindSpot` — check whether `_validate_harness_multimodal_evaluator_blind_spot` hardcodes evaluator type checks; update if the validator pattern-matches type strings that would incorrectly trigger for `comparator`

## Integration Map

### Files to Modify
- `scripts/little_loops/evaluators/comparator.py` — new evaluator module
- `scripts/little_loops/evaluators/__init__.py` — register new evaluator type
- `scripts/little_loops/schema/` — extend loop YAML schema for `action_type: comparator` + `baseline_path`
- `scripts/little_loops/ll_loop/validate.py` — validate comparator config

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — add `evaluate_comparator` to `from little_loops.fsm.evaluators import (...)` block and `__all__`; top-level package already exports `evaluate_blind_comparator` via same pattern [Agent 1 finding]
- `scripts/little_loops/cli/loop/info.py` — add `"comparator"` to `_EVALUATE_TYPE_DISPLAY` dict so `ll-loop show --verbose` renders a human-readable label rather than the raw string [Agent 2 finding]
- `scripts/little_loops/fsm/validation.py` — update MR-1 `ValidationError` prose enumeration in `_validate_meta_loop_evaluation()` (~lines 960–965) to include `comparator`; code logic is auto-correct via `NON_LLM_EVALUATOR_TYPES` but the human-readable hint string needs updating [Agent 2 finding]
- `scripts/little_loops/cli/loop/__init__.py` — add `"promote-baseline"` to `known_subcommands` set (lines 47–75); without this guard `ll-loop promote-baseline` is misinterpreted as a loop name and prepended with `"run"` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/ll_loop/runner.py` — evaluator dispatch; add `comparator` case
- `scripts/little_loops/fsm_evaluator.py` — evaluator type registry

### Similar Patterns
- Existing `check_semantic` evaluator in `scripts/little_loops/evaluators/` — follow same registration pattern
- `ll-loop run` baseline mode in `.issues/features/P2-FEAT-1790-ab-baseline-mode-for-ll-loop-run.md` — sibling A/B work

### Tests
- `scripts/tests/test_evaluators.py` — add comparator test cases
- Test fixtures in `scripts/tests/fixtures/baseline/` — sample baseline outputs for comparisons

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — new tests: `test_comparator_evaluator_type_is_valid`, `test_comparator_round_trips_through_dict`, `test_comparator_baseline_path_field_roundtrip`, `test_comparator_auto_promote_field_roundtrip`, `test_comparator_min_pairs_field_roundtrip`; follow pattern of `TestMcpToolSchema` at line 1859 [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — new `TestComparatorEvaluatorValidation` class: `test_comparator_requires_baseline_path`; new MR-1 test: `test_mr1_fires_for_meta_loop_with_only_comparator_evaluator` (comparator calls LLM via `evaluate_blind_comparator()` — must NOT satisfy MR-1 non-LLM requirement); follow `TestHarborScorerEvaluatorValidation` at line 345 and `TestMetaLoopValidation` at line 741 [Agent 2 + 3 finding]
- `scripts/tests/test_ll_loop_execution.py` — new `test_promote_baseline_subcommand_registered` in `TestCmdSimulate`, following pattern of `test_diagnose_evaluators_subcommand_registered` at line 1453 [Agent 3 finding]
- `scripts/tests/test_ll_loop_integration.py` — new functional test `test_promote_baseline_no_runs` (no runs dir → informative message / non-zero exit), following pattern of `test_diagnose_evaluators_no_history` at line 543 [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py::TestEvaluateDispatcher` — **will break on add**: parametrize list at lines 551–562 (`test_dispatch_exit_code_124_short_circuits_to_error`) and lines 621–627 (`test_dispatch_nonzero_exit_*`) must include `"comparator"` in the correct list depending on `_EXIT_CODE_AWARE_EVALUATORS` membership (issue step 4 adds `"comparator"` to that set) [Agent 2 + 3 finding]
- `scripts/tests/test_fsm_schema_fuzz.py` — `valid_types` list at line 44 needs `"comparator"` added (won't break but gaps fuzz coverage) [Agent 3 finding]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py::TestEvaluateDispatcher.test_dispatch_nonzero_exit_generalized_short_circuit` — **third parametrize list** not covered by wiring step 10: this BUG-1815 test covers exit-code-blind evaluators; `"comparator"` is not in `_EXIT_CODE_AWARE_EVALUATORS` so it must be added here (`non-zero action exit → verdict="error"`) [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py::TestHarnessMultimodalEvaluatorBlindSpot.test_does_not_fire_with_non_output_contains_evaluator` — **investigate before implementing**: check whether `_validate_harness_multimodal_evaluator_blind_spot` hardcodes evaluator type checks that could incorrectly match `comparator`; update if needed [Agent 3 finding]

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add comparator to Evaluation Phases
- `docs/reference/API.md` — document new evaluator type

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — evaluator table (at `Evaluators interpret action output` section) needs a new `comparator` row with verdicts, latency tier, and action type requirements [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — inline YAML comment at line 305 (`# exit_code, output_numeric, ...`) lists all evaluator type values; add `"comparator"` [Agent 2 finding]
- `.claude/CLAUDE.md` — `## CLI Tools` section needs a new entry for `ll-loop promote-baseline` alongside `ll-loop run` [Agent 2 finding]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-loop validate` MR-1 rule section (~line 460) enumerates non-LLM evaluator types (`exit_code`, `output_numeric`, etc.); add `comparator` to this prose list [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — actual file paths from codebase analysis (issue's Integration Map had wrong paths):_

#### Files to Modify (Corrected)
- `scripts/little_loops/fsm/schema.py:56–66` — `EvaluateConfig.type` `Literal[...]` union; add `"comparator"` + new optional fields: `baseline_path: str | None = None`, `auto_promote: bool = False`, `min_pairs: int = 1`; extend `from_dict()` / `to_dict()`
- `scripts/little_loops/fsm/evaluators.py:779–953` — add `evaluate_comparator()` function wrapping existing `evaluate_blind_comparator()` (already landed in FEAT-1790); add `elif eval_type == "comparator":` branch in the `evaluate()` dispatcher at line ~953
- `scripts/little_loops/fsm/validation.py:64` — add `"comparator": ["baseline_path"]` to `EVALUATOR_REQUIRED_FIELDS`; also explicitly add `"comparator"` to the LLM-exclusion set alongside `"llm_structured"` in `NON_LLM_EVALUATOR_TYPES` (comparator calls the LLM via `evaluate_blind_comparator()` — it must NOT satisfy MR-1's non-LLM pairing requirement)
- `scripts/little_loops/fsm/__init__.py` — export `evaluate_comparator` alongside existing evaluator exports
- `scripts/little_loops/fsm/fsm-loop-schema.json` — extend `evaluateConfig` JSON Schema definition with `comparator` type and required `baseline_path` field

#### Dependent Files (Callers/Importers — Corrected)
- `scripts/little_loops/fsm/executor.py:1203` — `FSMExecutor._evaluate()` already dispatches to `evaluate()` from `evaluators.py`; no direct changes needed (the `elif` branch in `evaluate()` handles dispatch)
- `scripts/little_loops/cli/loop/__init__.py` — add `promote-baseline` subcommand (does not exist yet)

#### Similar Patterns (Corrected)
- `scripts/little_loops/fsm/evaluators.py:608` — `evaluate_llm_structured()` — exact host-runner call + JSON envelope parse pattern to follow
- `scripts/little_loops/fsm/evaluators.py:779` — `evaluate_blind_comparator()` — the core A/B logic; `evaluate_comparator()` is a thin wrapper that reads from disk + loops for `min_pairs`
- `scripts/little_loops/ab_writer.py` — `write_ab_json()` / `read_ab_json()` — artifact storage pattern for per-run results (not baseline promotion, but shows the `run_dir`-relative write pattern)

#### Tests (Corrected)
- `scripts/tests/test_fsm_evaluators.py` — correct file (issue references `test_evaluators.py` which does not exist); add `TestComparatorEvaluator` class; mock at `little_loops.fsm.evaluators.subprocess.run`; patch `little_loops.fsm.evaluators.random.choice` for shuffle-correctness tests

#### Architecture: Baseline Storage Path
The issue references `.loops/runs/<loop>/baseline/` but actual run dirs are timestamped: `.loops/runs/<loop>-<YYYYMMDDTHHMMSS>/`. A cross-run baseline that survives between iterations must live outside per-run dirs. Recommended convention: `.loops/baselines/<loop>/` (sibling of `runs/`, created on first auto-promote). The `baseline_path` config field in the YAML should point here (e.g., `.loops/baselines/harness-refine-issue/`).

#### Architecture: `min_pairs` Requires Multiple LLM Calls
`evaluate_blind_comparator()` runs one A/B comparison per call. To honor `min_pairs: N`, `evaluate_comparator()` must call it N times and take a majority vote (`harness_pass` count vs. `baseline_pass` count across N calls). Tie: both counts equal → `tie` verdict.

#### Architecture: `auto_promote` Write Path
When `auto_promote: true` and verdict is `yes`, write current `output` to `<baseline_path>/output.txt` (single-file baseline, overwritten on each promotion). The evaluator receives the `output` string and `config.baseline_path`; no `run_dir` needed. Use `pathlib.Path(config.baseline_path).mkdir(parents=True, exist_ok=True)` before writing.

## Acceptance Criteria

- [ ] Comparator evaluator runs against `baseline_path` files, returns yes/no/tie/no_baseline
- [ ] Label shuffling verified (judge prompt is symmetric in A/B)
- [ ] First-run bootstrap path works (no baseline → auto-promote current)
- [ ] `auto_promote` and manual `ll-loop promote-baseline` both functional
- [ ] Tests cover all four verdict cases plus shuffle correctness
- [ ] Docs updated with use case and placement guidance

## Scope Boundaries

- Multi-baseline support (comparing against N prior successful runs) — single baseline is sufficient for v1.
- Auto-rollback to baseline on regression — this evaluator only signals; rollback is a separate concern.
- Tournament-style multi-iteration brackets — single A/B per iteration only.

## Impact

- **Priority**: P4 — deprioritized behind FEAT-1790 (A/B baseline) and ENH-1792 (variance diagnostics), which produce the data this evaluator consumes. Not on the critical path for harness operation.
- **Effort**: Medium — new evaluator module, schema extension, CLI command for manual baseline promotion, and test coverage across four verdict cases.
- **Risk**: Low — entirely opt-in; no existing evaluator paths are changed. The comparator is an additional gate, not a replacement for `check_semantic`.
- **Breaking Change**: No

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | New evaluator slots into the documented chain |
| `.issues/features/P2-FEAT-1790-ab-baseline-mode-for-ll-loop-run.md` | Sibling A/B work — that one produces with/without baselines; this consumes prior-success baselines |
| `.issues/enhancements/P3-ENH-1792-detect-non-discriminating-evaluators-from-history.md` | Variance diagnostics that motivate having a regression-sensitive gate |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-31_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Large file footprint from wiring completeness** — wiring passes correctly identified ~6 additional touchpoints (test dispatcher parametrize lists, `info.py` display dict, `CLAUDE.md`, `CLI.md` prose enumeration), pushing site count to 20 (16+ breadth tier). Each site is small/mechanical so per-site risk is low; risk is execution overhead and chance of missing one touchpoint in a 20-file sweep. Mitigation: integration map enumerates all sites with specific line numbers.
- **`TestHarnessMultimodalEvaluatorBlindSpot` investigation** (step 24) — one "investigate before implementing" note; must be resolved early to confirm no hardcoded type check incorrectly fires for `comparator`.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-31
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1828: Comparator Evaluator — Core Implementation
- ENH-1829: Comparator Evaluator — Baseline Lifecycle CLI

## Session Log
- `/ll:issue-size-review` - 2026-05-31T00:00:00 - `328bc3bf-da89-4021-981a-e4291a0ad2e5.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00 - `3b490bcf-413e-4fe3-b2ed-61f7df62034d.jsonl`
- `/ll:wire-issue` - 2026-05-31T22:44:21 - `72a30597-27f7-46c1-abe8-736c98410497.jsonl`
- `/ll:refine-issue` - 2026-05-31T22:36:05 - `f8a69d39-2c55-48c5-8b59-4b25a3eea94c.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00 - `3598727d-c1b2-449b-bcac-1ffd3f832915.jsonl`
- `/ll:wire-issue` - 2026-05-31T00:00:00 - `c77f9c9d-319a-4328-aa81-b007232a7239.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:17 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:refine-issue` - 2026-05-31T05:35:34 - `959041b3-877b-4e0b-bb02-ec35d5072a0a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:format-issue` - 2026-05-29T19:41:01 - `fbb9c3ab-f0e7-4ee0-b9e9-75aa887611e6.jsonl`
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`

---

## Status
open

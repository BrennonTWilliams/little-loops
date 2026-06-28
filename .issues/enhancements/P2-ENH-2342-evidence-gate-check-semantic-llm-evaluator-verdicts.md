---
id: ENH-2342
type: ENH
priority: P2
status: open
discovered_date: 2026-06-27
captured_at: '2026-06-27T05:17:49Z'
discovered_by: capture-issue
decision_needed: false
labels:
- evaluator
- loop-quality
- llm-accuracy
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2342: Evidence-Gate check_semantic LLM Evaluator Verdicts

## Summary

Change the LLM-evaluator prompt contract so every Yes/No/Partial verdict must cite verbatim evidence from the trajectory and defaults to the conservative verdict (No/Partial) when evidence is absent. This applies to `check_semantic` / `llm_structured` evaluator states in FSM loops and to LLM-judged states in meta-loops.

## Current Behavior

`check_semantic` and `llm_structured` loop states ask an LLM to judge whether a condition is met and return a structured verdict. The prompt contract does not require the model to quote evidence from the trajectory — it can assert "Yes, the task is complete" without citing any specific output. This is the pattern that makes LLM self-grades ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4% as noted in CLAUDE.md).

## Expected Behavior

Every `check_semantic` prompt template includes a mandatory evidence block:

```
For each condition you judge:
- State Yes, No, or Partial
- Quote the EXACT line(s) from the trajectory that support your verdict (verbatim, in quotes)
- If you cannot find a verbatim quote, your verdict MUST be No (or Partial if unsure)
```

An LLM that returns a verdict without a matching quote is treated as returning the conservative default. This is enforced in the evaluator parsing layer, not just by prompt instruction.

## Motivation

Two independent papers in the 05-26-2026 research batch converge on this pattern:

- **SELFCOMPACT**: its rubric requires verbatim citations for every yes/no condition; ablation shows removing the rubric collapses quality to the naive baseline (46.4% → 41.0%). The rubric (not the act of compacting) is where the gain comes from.
- **RL-collapse PRS prompt**: "state the root cause in 1–2 lines, then provide 2–4 pieces of evidence from the interaction log." Grounding in citations is what makes both evaluators reliable.

This is a **prompt-template change, not an architecture change**, and it directly attacks the documented LLM self-grade accuracy problem. It pairs with MR-1 (non-LLM evaluator required alongside LLM judges) to make the LLM side of that pair meaningfully discriminating rather than defaulting to optimism.

## Proposed Solution

**1. Update the shared `check_semantic` prompt template** (wherever it lives in `scripts/little_loops/`) to add the evidence contract:

```python
CHECK_SEMANTIC_EVIDENCE_CONTRACT = """
IMPORTANT: For each condition you evaluate:
1. State your verdict: Yes / No / Partial
2. Provide a VERBATIM quote from the output that supports your verdict (exact text, in quotes)
3. If you cannot quote specific text, your verdict is automatically No (or Partial if context suggests partial progress)

Do not assert a verdict without evidence. "The task appears complete" is not evidence.
"""
```

**2. Update the verdict parser** in `llm_structured` / `check_semantic` to validate that returned verdicts include a non-empty evidence field. If the evidence field is empty or missing, coerce the verdict to `No` (or `partial` if the current route table has a `partial` branch).

**3. Add a loop validator check** in `ll-loop validate` (or as an advisory in `ll-loop diagnose-evaluators`) that detects `check_semantic` states whose prompt template omits the evidence contract. Severity: WARNING. Rationale: the contract can't be enforced at parse time if the template never asked for evidence.

**4. Update the `AUTOMATIC_HARNESSING_GUIDE.md` and loop authoring docs** to document the evidence-gating contract as a standard requirement alongside MR-1.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — **primary change target**
  - `DEFAULT_LLM_SCHEMA` (lines 62–87): add `"evidence": {"type": "string", "description": "..."}` to `properties` and to `required` list
  - `evaluate_llm_structured()` (lines 813–982): inject `CHECK_SEMANTIC_EVIDENCE_CONTRACT` into `effective_prompt` construction (line 843); add evidence coercion after verdict extraction (line 961: `verdict = str(llm_result.get("verdict", "error"))`) — if `llm_result.get("evidence", "").strip()` is empty, coerce to `"no"` (or `"partial"` if state has `on_partial`)
- `scripts/little_loops/fsm/validation.py` — add new `_validate_llm_evidence_contract()` function (same pattern as `_validate_meta_loop_evaluation()` at line 1132); call it from `validate_fsm()` after line 1102 (the final call in the chain)

### Dependent Files (Callers/Importers)
- 28+ loop YAML files using `llm_structured` or `check_semantic` states — affected at runtime; no YAML edits required (coercion in `evaluate_llm_structured()` handles absent evidence automatically):
  - `scripts/little_loops/loops/harness-multi-item.yaml` — has two `llm_structured` states (check_mcp at line 130, check_semantic at line 147)
  - `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — `check_semantic` state at line 133
  - `scripts/little_loops/loops/fix-quality-and-tests.yaml`, `loop-specialist-eval.yaml`, `integrate-sdk.yaml`, `goal-cluster.yaml`, `agent-eval-improve.yaml`, `eval-driven-development.yaml`, and ~20 others
  - `scripts/little_loops/loops/lib/common.yaml:47` — `llm_gate` fragment (action_type: prompt + evaluate.type: llm_structured) — the fragment itself doesn't specify `prompt:` for the evaluator, so the validator must check caller-supplied `evaluate.prompt` at the state level

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — **main FSM execution path**; imports `evaluate_llm_structured` (line 29) and `EvaluationResult` (line 25); calls `evaluate_llm_structured()` inside `_evaluate()` at line 1419 (note: previously cited as `_run_evaluate_step()` at line 1451 — confirmed name is `_evaluate()`); emits `evaluate` events at lines 1461–1468 and 1502–1509 via `**result.details` spread (additive — new `evidence`/`evidence_coerced` keys appear automatically as flat event keys, no destructuring to break) [Agent 1 + Agent 3 verification]
- `scripts/little_loops/cli/harness.py` — `ll-harness` CLI semantic-check path; imports `evaluate_llm_structured` (line 18) and calls it at line 215; new `evidence` field in result.details will be available in harness output — no code changes expected but confirm output rendering doesn't assume a fixed details schema [Agent 1 finding]

_Second refinement pass — additional consumers of `**result.details` spread (no code changes needed; awareness only):_
- `scripts/little_loops/fsm/persistence.py` — `_write_meta_eval_entry()` at line 713 reads `event.get("reason")` as a flat spread key; `_handle_event()` at lines 664–684 rebuilds `_last_result["details"]` from flat event filter (new keys auto-included via `{k: v for k, v in event.items() if k not in ("event", "ts", "type", "verdict")}`); no code change needed but `evidence`/`evidence_coerced` will appear in archived meta-eval.jsonl entries
- `scripts/little_loops/cli/loop/_helpers.py` — `LiveDisplayCallback.__call__()` at lines 736–786 reads `event.get("reason")`, `event.get("confidence")`, `event.get("error")` as flat spread keys; new fields safe to add [Agent 3 finding]
- `scripts/little_loops/cli/loop/info.py` — `format_event()` at lines 439–476 reads `event.get("reason")`, `event.get("confidence")`, plus `llm_model`, `llm_latency_ms`, `llm_prompt`, `llm_raw_output` as flat keys; new fields safe to add [Agent 3 finding]
- `scripts/little_loops/analytics/variance.py` — `_collect_state_verdicts()` at line 98 reads `event.get("verdict")` from archived JSONL; `evidence_coerced` key will silently appear in future event archives — no functional break [Agent 3 finding]
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test()` at lines 133–136 iterates all `details.items()` for display (new keys will show in `ll-loop test` output, which is desirable); line 166 uses `"error" in eval_result.details` (safe — no collision with `evidence`/`evidence_coerced`) [Agent 3 finding]

### Similar Patterns
- `_validate_meta_loop_evaluation()` in `validation.py` (line 1132) — exact model for MR-7: define a function, check a condition per state, append `ValidationError(message=..., path=f"states.{state_name}.evaluate", severity=ValidationSeverity.WARNING)`
- `ValidationSeverity.WARNING` and `ValidationError` dataclass (lines 34–60 in `validation.py`) — already imported
- `NON_LLM_EVALUATOR_TYPES` frozenset (lines 80–86 in `validation.py`) — for checking if `evaluate.type == "llm_structured"`; excludes `"llm_structured"`, `"comparator"`, and `"contract"` from `EVALUATOR_REQUIRED_FIELDS.keys()`
- `validate_fsm()` call chain (line 929 in `validation.py`; appends calls from ~line 1073 to 1102) — append `errors.extend(_validate_llm_evidence_contract(fsm))` after line 1102 (`_validate_capture_reachability`, the current last call)

### Tests
- `scripts/tests/test_fsm_evaluators.py:800+` — `TestLLMStructuredEvaluator` class; model new tests here: `test_empty_evidence_coerces_to_no()`, `test_empty_evidence_coerces_to_partial_when_partial_branch()`, `test_present_evidence_passes_through()`
- `scripts/tests/test_fsm_validation.py:939+` — `TestMetaLoopValidation` class (note: not `TestMetaLoopEvaluationValidation`); model new `TestLLMEvidenceContractValidation` class here following same `_simple_fsm()` / `_meta_fsm()` helper pattern

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break without updates** (mock `_cli_stdout()` helper at line 802 lacks `evidence` field — every test asserting `"yes"` or `"partial"` will have verdict coerced to `"no"`):
- `test_success_verdict` (line 838) — asserts `"yes"`, will coerce to `"no"` [Agent 3 finding]
- `test_low_confidence_without_suffix` (line 878) — asserts `"yes"`, will coerce [Agent 3 finding; note: issue previously named this `test_low_confidence_no_suffix` — confirmed name is `test_low_confidence_without_suffix`]
- `test_low_confidence_with_suffix` (line 889) — asserts `"yes_uncertain"`, will coerce [Agent 3 finding]
- `test_result_as_dict_in_envelope` (line ~1011) — asserts `"yes"`, will coerce [Agent 3 finding; note: issue previously named this `test_result_field_present` at line 1007 — confirmed name is `test_result_as_dict_in_envelope`]
- `test_raw_response_in_details` (line 1083) — asserts `"yes"`, will coerce [Agent 3 finding]
- `test_envelope_as_direct_result` (line 1110) — asserts `"yes"`, will coerce [Agent 3 finding]
- `test_partial_verdict` (line 869) — depends on coercion design [Agent 3 finding]
- `TestEvaluateDispatcherLLM.test_dispatch_llm_structured` (line 1168) — asserts `"yes"`, will coerce [Agent 3 finding]
- `TestEvaluateDispatcherLLM.test_dispatch_llm_with_config_options` (line 1180) — asserts `"yes_uncertain"`, will coerce [Agent 3 finding]

**Root fix**: Update `_cli_stdout()` static helper (line 802) to add an `evidence` parameter with non-empty default; `TestEvaluateDispatcherLLM` has its own duplicate `_cli_stdout()` at line 1143 that also needs updating. [Agent 3 finding]

**Tests that are safe** (error paths / `"no"` verdicts / non-LLM evaluator types): `test_timeout`, `test_cli_error`, `test_empty_output`, `test_api_error_in_json`, `test_structured_output_missing`, `test_jsonl_output_uses_last_line` (returns `"no"`, the coercion target) [Agent 3 finding]

**End-to-end gap**: No test exercises `evaluate_llm_structured()` coercion → `FSMExecutor._evaluate()` routing → next-state selection. The integration path between evidence coercion in `evaluators.py` and `executor.py` state routing is untested — consider adding one integration test in `test_ll_loop_execution.py`. [Agent 3 finding]

_Second refinement pass — additional tests with `EvaluationResult` mocks missing `evidence` (low priority — these mock at executor level, bypassing `evaluate_llm_structured()` coercion entirely):_
- `scripts/tests/test_fsm_executor.py` — ~20 occurrences of `EvaluationResult(verdict=..., details={})` at lines 306, 358, 386, 611, 1295–1462; these patch `_evaluate()` directly and are not affected by the coercion in `evaluate_llm_structured()`; no updates required unless the integration test (step 15) confirms coercion lives at the executor level [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` — `TestContributedEvaluatorDispatch` at lines 1871, 1903, 1938 uses `EvaluationResult(verdict="yes", details={})` contributed-evaluator mocks; same isolation as above — no updates required [Agent 3 finding]
- `scripts/tests/test_cli_harness.py` — `TestSemanticEvaluator` patches `evaluate_llm_structured` directly at lines 602, 628, 652 with `EvaluationResult(verdict=..., details={"confidence": 0.9})`; unlike `_cli_stdout()` these patch the function's return value, so if `evaluate_llm_structured()` itself returns `evidence_coerced: true` when `evidence` is absent, these mocks bypass coercion; recommend adding `"evidence": "Found in output"` to the `details` dict in line 602 mock and confirm lines 628/652 still test the intended "no evidence → coerce" path [Agent 3 finding]
- `scripts/tests/test_fsm_persistence.py` — `test_meta_eval_written_on_llm_structured_in_meta_loop()` at line 1076 constructs `evaluate` event with `"reason": "..."` as a top-level flat key; adding `evidence` to `details` will cause it to also appear as a flat key via `**result.details` spread; this test may need to assert `event.get("llm_evidence")` if `_write_meta_eval_entry()` is updated to log the new field [Agent 3 finding]

_Second wiring pass (added by `/ll:wire-issue`):_

**Additional breaking test** (not previously flagged):
- `test_default_values_used()` at line 1094 in `test_fsm_evaluators.py` — asserts `json.dumps(DEFAULT_LLM_SCHEMA)` via string comparison at line 1108; adding `"evidence"` to `DEFAULT_LLM_SCHEMA.properties` and `required` will change the serialized JSON and break this assertion — update the expected schema dict in this test [Agent 3 finding]

**Import block** (`test_fsm_validation.py` lines 24–43) imports every `_validate_*` function from `validation.py` by name; `_validate_llm_evidence_contract` must be added to this import block when the function is written [Agent 3 finding]

**YAML fixture files** (conditional — will trigger MR-8 WARNING when `_validate_llm_evidence_contract()` checks all `llm_structured` states for evidence keywords in `evaluate.prompt`):
- `scripts/tests/fixtures/fsm/broken-verify-loop.yaml:9` — `llm_structured` state with `evaluate.prompt:` containing no evidence keywords [Agent 3 finding]
- `scripts/tests/fixtures/fsm/assess-rubric-drift.yaml:11` — same gap [Agent 3 finding]
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml:12` — same gap [Agent 3 finding]
- `scripts/tests/fixtures/fsm/custom-on-routing.yaml:6` — same gap [Agent 3 finding]

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add evidence-contract section (currently documents `check_semantic` at lines 27, 62, 95)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — reference evidence-gating alongside MR-1 (which is documented at line 93)
- `.claude/CLAUDE.md` § Loop Authoring — document the new validator rule (MR-7) and severity

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:627-633` — **MR rule listing** documents MR-1 through MR-6 + suppression flags; **MR-7 must be added here** matching the same format [Agent 2 finding]
- `docs/reference/API.md:4985-4990` — duplicate MR rule listing; **MR-7 must be added here** as well [Agent 2 finding]
- `docs/reference/API.md:4337-4342` — suppression flags listing (`meta_self_eval_ok`, `partial_route_ok`, etc.); add suppression flag for MR-7 if one is defined (e.g. `evidence_contract_ok: bool = False`) [Agent 2 finding]
- `docs/reference/API.md:4662-4748` — `EvaluationResult` and `evaluate_llm_structured()` reference docs; **update to document `evidence: str` and `evidence_coerced: bool` in `EvaluationResult.details`** for `llm_structured` evaluations [Agent 2 finding]
- `docs/reference/loops.md:117` — meta-eval.jsonl schema lists `llm_verdict`, `llm_rationale`; if evidence is logged to this file (as `llm_evidence`), this schema table needs updating [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:597` — `check_semantic` row in evaluator table ("LLM judges output quality"); may mention evidence-contract requirement [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:290` — `llm_structured` evaluator verdict table (`yes / no / blocked / partial`); evidence coercion behavior (absent evidence → `"no"`) is undocumented [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — duplicate `llm_structured` type table; same verdict-coercion gap [Agent 2 finding]
- `skills/create-loop/reference.md` — **must update**: `check_semantic` state template used by the `/ll:create-loop` wizard lacks evidence-contract in `evaluate.prompt` template; loops generated by the wizard will immediately trigger MR-7 WARNING [Agent 2 finding]
- `scripts/little_loops/cli/loop/config_cmds.py` in `cmd_validate()` — imports `ValidationSeverity`; formats all violations in JSON output; new MR-7 WARNINGs will appear in `ll-loop validate` output for every loop with `llm_structured` states lacking evidence keywords [Agent 2 finding]
- `scripts/little_loops/analytics/variance.py` in `generate_recommendation()` — matches `evaluator_type == "llm_structured"` to recommend "broaden judge criteria"; evidence coercion will shift pass/fail distribution and change `p*(1-p)` variance values reported by `ll-loop calibrate-budget` (advisory; no code change needed) [Agent 2 finding]

_Second wiring pass (added by `/ll:wire-issue`):_

> **Critical — MR Rule Numbering Collision**: All references to "MR-7" in this issue for the new evidence-contract validation rule are incorrect. MR-7 is already assigned to the bash `:-` interpolation escape rule (ENH-2348), confirmed in `.claude/CLAUDE.md` lines 167–174, `docs/reference/CLI.md` line 633, `docs/reference/API.md` line 4992, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` line 99, and `skills/review-loop/reference.md` line 46. The evidence-contract rule must be numbered **MR-8** throughout all implementation, documentation, and CLAUDE.md. Every step in this issue that writes "MR-7" for the new rule should be read as "MR-8".

- `skills/review-loop/reference.md:40-47` — **Validation Rules table** lists MR-1 through MR-7 explicitly; a new MR-8 row must be appended matching the existing format (`| MR-8 (WARNING) | ... | evidence_contract_ok: true |`); this file has no corresponding implementation step [Agent 2 finding]
- `skills/create-loop/loop-types.md` — `check_semantic` state template blocks at lines ~803–811 and ~898–905 each contain `evaluate.prompt:` fields without evidence-contract language; step 14 covers `skills/create-loop/reference.md` only — this file is a separate source of wizard-generated templates and also needs updating or wizard-generated loops will immediately trigger MR-8 WARNING [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:26,85,291,304,469` — section heading `## The Design Rules (MR-1…MR-7)` and its ToC entry (line 26) both hard-code MR-7 as the ceiling; rule table at lines 91–99 needs MR-8 row; prose enumerations at lines 291 and 304 list `MR-2/MR-3/.../MR-7` and must extend to MR-8; cross-reference at line 469 reads `MR-1…MR-7` — all need updating; no numbered implementation step exists for this file [Agent 2 finding]
- `.claude/CLAUDE.md` § Loop Authoring — already documents MR-1 through MR-7 in one-paragraph-per-rule format (`ll-loop validate enforces rule N as SEVERITY. Suppress with flag_ok: true. See ENH-XXXX.`); MR-8 paragraph must be added in exact same format; this is the canonical authoring reference that loop authors consult first — no numbered implementation step exists for this file [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/evaluators.py:62-87` — `DEFAULT_LLM_SCHEMA` currently has `verdict`, `confidence`, `reason` in `required`; `evidence` field must be added to both `properties` and `required`
- `scripts/little_loops/fsm/evaluators.py:842-848` — `effective_prompt = prompt or DEFAULT_LLM_PROMPT`; evidence contract injected here via `effective_prompt = (prompt or DEFAULT_LLM_PROMPT) + CHECK_SEMANTIC_EVIDENCE_CONTRACT`
- `scripts/little_loops/fsm/evaluators.py:961` — verdict extraction: `verdict = str(llm_result.get("verdict", "error"))`; coercion block goes immediately after this line
- `scripts/little_loops/fsm/evaluators.py:969-981` — `EvaluationResult` construction includes `details["reason"]`; add `details["evidence"]` and `details["evidence_coerced"]` bool for observability
- `scripts/little_loops/fsm/validation.py:1067-1079` — call chain in `validate_fsm()` where new `_validate_llm_evidence_contract(fsm)` should be added
- `scripts/little_loops/fsm/validation.py:80-83` — `NON_LLM_EVALUATOR_TYPES` derivation pattern; `"llm_structured"` is explicitly excluded from this set, confirming it's the only LLM evaluator type
- `scripts/little_loops/loops/lib/common.yaml:47-59` — `llm_gate` fragment uses `action_type: prompt` + `evaluate.type: llm_structured` but does NOT specify `evaluate.prompt`; callers supply their own `prompt:` at the state level — the validator must inspect `state.evaluate.prompt` (which may be `None` for callers using default prompts)
- Coercion direction when evidence is absent: check `state.on_partial is not None` to decide between `"no"` and `"partial"` — but this state context is NOT available inside `evaluate_llm_structured()` (which only receives the `schema` and `prompt`). **Resolution**: coerce to `"no"` unconditionally in the parser (safest-fail direction); caller loops can still route `on_no` → retry if partial progress is expected

## Implementation Steps

1. **`evaluators.py` — add `CHECK_SEMANTIC_EVIDENCE_CONTRACT` constant** before `DEFAULT_LLM_SCHEMA` (line 62); inject it into `effective_prompt` at line 843: `effective_prompt = (prompt or DEFAULT_LLM_PROMPT) + "\n\n" + CHECK_SEMANTIC_EVIDENCE_CONTRACT`
2. **`evaluators.py` — extend `DEFAULT_LLM_SCHEMA`** (lines 62–87): add `"evidence": {"type": "string", "description": "Verbatim quote from action output supporting verdict; empty string means no evidence found"}` to `properties`; add `"evidence"` to the `required` list
3. **`evaluators.py` — add evidence coercion** after line 961 (`verdict = str(llm_result.get("verdict", "error"))`): `if not llm_result.get("evidence", "").strip(): verdict = "no"` — always coerce to `"no"` (coercing to `"partial"` based on `on_partial` is NOT possible here since `evaluate_llm_structured()` has no state context); add `"evidence": llm_result.get("evidence", ""), "evidence_coerced": (was_empty)` to `details`
4. **`validation.py` — add `_validate_llm_evidence_contract()`** function following the exact pattern of `_validate_meta_loop_evaluation()` (line 1132): iterate states, check `_is_llm_judged(state)` (line 1387; helper already exists in same file), check if `state.evaluate` is not None and `state.evaluate.prompt` does not contain any of `{"verbatim", "quote", "evidence"}` (case-insensitive); emit `ValidationError(..., severity=ValidationSeverity.WARNING)` with path `f"states.{state_name}.evaluate.prompt"`. Note: Path B states (no `evaluate:` block, action is `"prompt"`) have `state.evaluate is None` — these are not checkable by the validator; they inherit `DEFAULT_LLM_PROMPT` which will include the evidence contract after Step 1.
5. **`validation.py` — call from `validate_fsm()`** after line 1102 (after `_validate_capture_reachability`, the last call in the chain): `errors.extend(_validate_llm_evidence_contract(fsm))`
6. **Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`** with evidence-contract section (add after the LLM-as-Judge section)
7. **Write tests in `test_fsm_evaluators.py`** (`TestLLMStructuredEvaluator` class, line 799+): `test_empty_evidence_coerces_to_no()`, `test_populated_evidence_passes_through()`, `test_evidence_coercion_logged_in_details()`
8. **Write tests in `test_fsm_validation.py`**: new `TestLLMEvidenceContractValidation` class (model after `TestMetaLoopValidation` at line 939 — note: class previously referenced as `TestMetaLoopEvaluationValidation` which does not exist); test: WARNING fires when prompt missing evidence keywords, does not fire when `"verbatim"` present, does not fire when no `evaluate:` block, does not fire for non-LLM evaluators

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Update `_cli_stdout()` mock helper in `test_fsm_evaluators.py`** (line 802) — add `evidence: str = "Found in output"` parameter to the static helper; propagate through `structured_output` dict; do the same for `TestEvaluateDispatcherLLM._cli_stdout()` duplicate at line 1143. This is the root fix — without it, 7+ existing tests will break (coercion fires on absent evidence and changes `"yes"` to `"no"`). Separately update `test_partial_verdict` depending on coercion design.
10. **Update `docs/reference/CLI.md:633`** — add MR-7 entry to the validation-rules list (between MR-6 and the suppression flag paragraph): `"MR-7 (WARNING): check_semantic/llm_structured state prompt does not include evidence-contract keywords (verbatim, quote, evidence); verdicts may default to optimism. Suppress with evidence_contract_ok: true."`
11. **Update `docs/reference/API.md:4985-4990`** — add matching MR-7 entry to the second MR-rule listing.
12. **Update `docs/reference/API.md:4337-4342`** — add `evidence_contract_ok: bool = False` suppression flag entry if MR-7 supports one.
13. **Update `docs/reference/API.md:4662`** (`EvaluationResult` docs) — document that `llm_structured` evaluations now populate `details["evidence"]` (verbatim quote or empty string) and `details["evidence_coerced"]` (bool; True if verdict was downgraded).
14. **Update `skills/create-loop/reference.md`** `check_semantic` state template — add evidence-contract language to the `evaluate.prompt:` field so wizard-generated loops do not immediately trigger MR-7.
15. **Add integration test in `test_ll_loop_execution.py`** (optional but recommended) — exercise the full path: mock `evaluate_llm_structured()` returning empty `evidence` → confirm FSM routes to `on_no` rather than `on_yes`, verifying coercion propagates through `FSMExecutor._evaluate()` (confirmed name at line 1419; not `_run_evaluate_step()`).

_Second wiring pass (added by `/ll:wire-issue`):_

> **Critical**: Steps 10–15 above reference the new evidence-contract validator rule as "MR-7". MR-7 is already taken by ENH-2348 (bash `:-` escape rule). Implement the new rule as **MR-8** in all code, rule names, suppression flags (`evidence_contract_ok`), documentation, and CLAUDE.md entries.

16. **Update `.claude/CLAUDE.md` § Loop Authoring** — add MR-8 paragraph following the exact format of MR-7 (lines 167–174): `ll-loop validate enforces rule 8 as WARNING severity (rule MR-8). A check_semantic/llm_structured state whose prompt omits evidence-contract keywords (verbatim, quote, evidence) may default to optimism. Suppress with evidence_contract_ok: true. See ENH-2342.`
17. **Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`** — change section heading (line 85) and ToC entry (line 26) from `MR-1…MR-7` to `MR-1…MR-8`; append MR-8 row to the rule table (after line 99); extend prose enumerations at lines 291 and 304 to include MR-8; update cross-reference at line 469 from `MR-1…MR-7` to `MR-1…MR-8`
18. **Add MR-8 row to `skills/review-loop/reference.md`** — append to Validation Rules table (lines 40–47): `| MR-8 (WARNING) | check_semantic/llm_structured state prompt missing evidence-contract keywords (verbatim, quote, evidence) — verdicts may default to optimism | evidence_contract_ok: true |`
19. **Update `skills/create-loop/loop-types.md`** — add evidence-contract language to `evaluate.prompt:` in check_semantic template blocks at lines ~803–811 and ~898–905 (step 14 covers `reference.md` only; this file is the separate template source the wizard renders)
20. **Update `test_default_values_used()` in `test_fsm_evaluators.py`** (line 1094) — the assertion at line 1108 compares against `json.dumps(DEFAULT_LLM_SCHEMA)`; update the expected dict to include the new `"evidence"` property so the string comparison continues to pass

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_is_llm_judged()` already exists in `validation.py` at line 1387 (used by `_validate_partial_route_dead_end()` / MR-4 rule) — reuse it directly in the new validator function; it returns `True` for states with `evaluate.type in ("llm_structured", "check_semantic")` or `action_type in ("prompt", "slash_command")` with no evaluate block; also returns `True` when `action_type is None` and `state.action` starts with `"/"`
- `check_semantic` is **a state-name convention, not an evaluator type** — no special Python handling; all such states use `evaluate.type: llm_structured`. The validator must check `_is_llm_judged(state)` or `state.evaluate.type == "llm_structured"`, not match on state names.
- No shared Python constant exists for the check_semantic prompt — each loop YAML defines its own inline `evaluate.prompt:` string. The `DEFAULT_LLM_PROMPT` applies only to Path B states (no evaluate block at all). After Step 1, `DEFAULT_LLM_PROMPT` will carry the evidence contract forward; inline prompts in loop YAMLs must add `"evidence"` or `"verbatim"` to trigger the new validator to pass cleanly (the runtime coercion catches them either way, but the validator gives authors early warning).
- `evaluate_llm_structured()` is called via two paths: Path A (explicit `evaluate:` block in YAML), Path B (no evaluate block + `action_type: "prompt"`). Evidence coercion in Steps 1–3 covers both paths since `CHECK_SEMANTIC_EVIDENCE_CONTRACT` is injected into `DEFAULT_LLM_PROMPT` and custom prompts alike.

## Impact

- **Priority**: P2 — directly addresses the documented 33–55% LLM self-grade accuracy failure (SHOR Table 1; Sonnet 4.6 = 33.4%); pairs with MR-1 to make LLM evaluators meaningfully discriminating rather than optimism-defaulting
- **Effort**: Medium — prompt template injection is low-risk; parser coercion + schema enforcement + validator rule + test coverage adds up; documentation updates straightforward
- **Risk**: Low — conservative coercion (No/Partial when evidence absent) is the safe-fail direction; validator is WARNING only; no existing loop YAMLs require modification
- **Breaking Change**: Yes — `llm_structured` / `check_semantic` output schema adds required `evidence: str` field; loops whose prompts don't elicit evidence will have verdicts coerced to conservative (intended behavior)

## Scope Boundaries

- **In scope**: prompt-template contract constant, verdict parser coercion logic, `ll-loop validate` WARNING rule, documentation updates
- **Out of scope**: modifying existing loop YAML files to add evidence prompts (runtime enforcement handles this; loops fix forward as authors encounter the WARNING)
- **Out of scope**: non-LLM evaluators (`exit_code`, `output_numeric`, `convergence`, `diff_stall`, `mcp_result`) — evidence contract applies only to LLM-judged states
- **Out of scope**: replacing MR-1 (non-LLM pairing requirement) — this enhancement is additive, not a substitute
- **Out of scope**: retroactive backfilling of evidence in archived loop run transcripts

## Success Metrics

- `ll-loop validate` detects `check_semantic` states missing the evidence-contract keyword with 0 false negatives in the test suite
- Verdict coercion triggers and is logged when `evidence` is empty or missing (covered by unit tests)
- `AUTOMATIC_HARNESSING_GUIDE.md` evidence-contract section passes `ll-check-links` and `ll-verify-docs`
- No regression in existing loop runs where evidence is already present in prompts

## API/Interface

Updated `llm_structured` / `check_semantic` structured output schema:

```python
# Verdict schema — evidence field added (required)
class SemanticVerdict(BaseModel):
    verdict: Literal["yes", "no", "partial"]
    evidence: str  # Verbatim quote from trajectory; empty string → coerced to conservative verdict
    reasoning: str | None = None
```

New `ll-loop validate` rule:
- **Severity**: WARNING
- **Trigger**: `check_semantic` state whose prompt template does not contain evidence-contract keywords (`"verbatim"`, `"quote"`, or `"evidence"`)
- **Message**: `check_semantic state missing evidence contract — verdicts may default to optimism`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/05-26-2026-batch/SYNTHESIS-and-recommendations.md` | Source recommendation #2; SELFCOMPACT + PRS findings |
| `.claude/CLAUDE.md` § Loop Authoring MR-1 | The non-LLM pairing rule this enhances |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Where the evidence contract must be documented |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Evaluator health context |

## Status

**Open** | Created: 2026-06-27 | Priority: P2

## Session Log
- `/ll:wire-issue` - 2026-06-28T03:58:15 - `b4f024df-10c6-4292-bb5a-b6ebe140c266.jsonl`
- `/ll:refine-issue` - 2026-06-28T03:43:00 - `9e930281-60b2-460b-9976-e02ec135e310.jsonl`
- `/ll:refine-issue` - 2026-06-28T03:40:11 - `9e930281-60b2-460b-9976-e02ec135e310.jsonl`
- `/ll:confidence-check` - 2026-06-27T07:30:00Z - `bf286adc-6a4d-472a-9eb6-d1ddc002a4ea.jsonl`
- `/ll:wire-issue` - 2026-06-27T06:12:20 - `5eb6d3df-3646-4ad2-82ed-98bdde238fad.jsonl`
- `/ll:refine-issue` - 2026-06-27T05:33:35 - `15663aad-3484-4d3c-b333-946a0e331e1a.jsonl`
- `/ll:format-issue` - 2026-06-27T05:22:57 - `9f4322ee-5b7f-41c1-ae57-47e6963891ed.jsonl`
- `/ll:capture-issue` - 2026-06-27T05:17:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd21288e-7370-4e7e-8040-6f118e73e291.jsonl`

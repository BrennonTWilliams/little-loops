---
id: ENH-2342
type: ENH
priority: P2
status: open
discovered_date: 2026-06-27
captured_at: "2026-06-27T05:17:49Z"
discovered_by: capture-issue
decision_needed: false
labels: ["evaluator", "loop-quality", "llm-accuracy"]
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
- `scripts/little_loops/fsm/validation.py` — add new `_validate_llm_evidence_contract()` function (same pattern as `_validate_meta_loop_evaluation()` at line 1124); call it from `validate_fsm()` after line 1079

### Dependent Files (Callers/Importers)
- 28+ loop YAML files using `llm_structured` or `check_semantic` states — affected at runtime; no YAML edits required (coercion in `evaluate_llm_structured()` handles absent evidence automatically):
  - `scripts/little_loops/loops/harness-multi-item.yaml` — has two `llm_structured` states (check_mcp at line 130, check_semantic at line 147)
  - `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — `check_semantic` state at line 133
  - `scripts/little_loops/loops/fix-quality-and-tests.yaml`, `loop-specialist-eval.yaml`, `integrate-sdk.yaml`, `goal-cluster.yaml`, `agent-eval-improve.yaml`, `eval-driven-development.yaml`, and ~20 others
  - `scripts/little_loops/loops/lib/common.yaml:47` — `llm_gate` fragment (action_type: prompt + evaluate.type: llm_structured) — the fragment itself doesn't specify `prompt:` for the evaluator, so the validator must check caller-supplied `evaluate.prompt` at the state level

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — **main FSM execution path**; imports `evaluate_llm_structured` (line 29) and `EvaluationResult` (line 25); calls `evaluate_llm_structured()` at line 1451 inside `_run_evaluate_step()`; after ENH-2342 the returned `EvaluationResult.details` dict will include `evidence` and `evidence_coerced` fields — review `_run_evaluate_step()` to confirm details are passed through without destructuring that would break [Agent 1 finding]
- `scripts/little_loops/cli/harness.py` — `ll-harness` CLI semantic-check path; imports `evaluate_llm_structured` (line 18) and calls it at line 215; new `evidence` field in result.details will be available in harness output — no code changes expected but confirm output rendering doesn't assume a fixed details schema [Agent 1 finding]

### Similar Patterns
- `_validate_meta_loop_evaluation()` in `validation.py` (lines 1124–1177) — exact model for MR-7: define a function, check a condition per state, append `ValidationError(message=..., path=f"states.{state_name}.evaluate", severity=ValidationSeverity.WARNING)`
- `ValidationSeverity.WARNING` and `ValidationError` dataclass (lines 34–60 in `validation.py`) — already imported
- `NON_LLM_EVALUATOR_TYPES` frozenset (lines 80–83 in `validation.py`) — for checking if `evaluate.type == "llm_structured"`
- `validate_fsm()` call chain (lines 1067–1079 in `validation.py`) — append `errors.extend(_validate_llm_evidence_contract(fsm))` here

### Tests
- `scripts/tests/test_fsm_evaluators.py:800+` — `TestLLMStructuredEvaluator` class; model new tests here: `test_empty_evidence_coerces_to_no()`, `test_empty_evidence_coerces_to_partial_when_partial_branch()`, `test_present_evidence_passes_through()`
- `scripts/tests/test_fsm_validation.py:971+` — `TestMetaLoopEvaluationValidation` class; model new `TestLLMEvidenceContractValidation` class here following same `_simple_fsm()` / `_meta_fsm()` helper pattern

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break without updates** (mock `_cli_stdout()` helper at line 802 lacks `evidence` field — every test asserting `"yes"` or `"partial"` will have verdict coerced to `"no"`):
- `test_success_verdict` (line 838) — asserts `"yes"`, will coerce to `"no"` [Agent 3 finding]
- `test_low_confidence_no_suffix` (line 879) — asserts `"yes"`, will coerce [Agent 3 finding]
- `test_low_confidence_with_suffix` (line 889) — asserts `"yes_uncertain"`, will coerce [Agent 3 finding]
- `test_result_field_present` (line 1007) — asserts `"yes"`, will coerce [Agent 3 finding]
- `test_raw_response_in_details` (line 1083) — asserts `"yes"`, will coerce [Agent 3 finding]
- `test_envelope_as_direct_result` (line 1110) — asserts `"yes"`, will coerce [Agent 3 finding]
- `test_partial_verdict` (line 869) — depends on coercion design [Agent 3 finding]
- `TestEvaluateDispatcherLLM.test_dispatch_llm_structured` (line 1168) — asserts `"yes"`, will coerce [Agent 3 finding]
- `TestEvaluateDispatcherLLM.test_dispatch_llm_with_config_options` (line 1180) — asserts `"yes_uncertain"`, will coerce [Agent 3 finding]

**Root fix**: Update `_cli_stdout()` static helper (line 802) to add an `evidence` parameter with non-empty default; `TestEvaluateDispatcherLLM` has its own duplicate `_cli_stdout()` at line 1143 that also needs updating. [Agent 3 finding]

**Tests that are safe** (error paths / `"no"` verdicts / non-LLM evaluator types): `test_timeout`, `test_cli_error`, `test_empty_output`, `test_api_error_in_json`, `test_structured_output_missing`, `test_jsonl_output_uses_last_line` (returns `"no"`, the coercion target) [Agent 3 finding]

**End-to-end gap**: No test exercises `evaluate_llm_structured()` coercion → `FSMExecutor._run_evaluate_step()` routing → next-state selection. The integration path between evidence coercion in `evaluators.py` and `executor.py` state routing is untested — consider adding one integration test in `test_ll_loop_execution.py`. [Agent 3 finding]

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
4. **`validation.py` — add `_validate_llm_evidence_contract()`** function following the exact pattern of `_validate_meta_loop_evaluation()` (line 1124): iterate states, check `_is_llm_judged(state)` (helper already exists in same file), check if `state.evaluate` is not None and `state.evaluate.prompt` does not contain any of `{"verbatim", "quote", "evidence"}` (case-insensitive); emit `ValidationError(..., severity=ValidationSeverity.WARNING)` with path `f"states.{state_name}.evaluate.prompt"`. Note: Path B states (no `evaluate:` block, action is `"prompt"`) have `state.evaluate is None` — these are not checkable by the validator; they inherit `DEFAULT_LLM_PROMPT` which will include the evidence contract after Step 1.
5. **`validation.py` — call from `validate_fsm()`** at line ~1080 (after existing `_validate_artifact_overwrite` call): `errors.extend(_validate_llm_evidence_contract(fsm))`
6. **Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`** with evidence-contract section (add after the LLM-as-Judge section)
7. **Write tests in `test_fsm_evaluators.py`** (`TestLLMStructuredEvaluator` class, line 800+): `test_empty_evidence_coerces_to_no()`, `test_populated_evidence_passes_through()`, `test_evidence_coercion_logged_in_details()`
8. **Write tests in `test_fsm_validation.py`**: new `TestLLMEvidenceContractValidation` class (model after `TestMetaLoopEvaluationValidation` at line 971); test: WARNING fires when prompt missing evidence keywords, does not fire when `"verbatim"` present, does not fire when no `evaluate:` block, does not fire for non-LLM evaluators

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Update `_cli_stdout()` mock helper in `test_fsm_evaluators.py`** (line 802) — add `evidence: str = "Found in output"` parameter to the static helper; propagate through `structured_output` dict; do the same for `TestEvaluateDispatcherLLM._cli_stdout()` duplicate at line 1143. This is the root fix — without it, 7+ existing tests will break (coercion fires on absent evidence and changes `"yes"` to `"no"`). Separately update `test_partial_verdict` depending on coercion design.
10. **Update `docs/reference/CLI.md:633`** — add MR-7 entry to the validation-rules list (between MR-6 and the suppression flag paragraph): `"MR-7 (WARNING): check_semantic/llm_structured state prompt does not include evidence-contract keywords (verbatim, quote, evidence); verdicts may default to optimism. Suppress with evidence_contract_ok: true."`
11. **Update `docs/reference/API.md:4985-4990`** — add matching MR-7 entry to the second MR-rule listing.
12. **Update `docs/reference/API.md:4337-4342`** — add `evidence_contract_ok: bool = False` suppression flag entry if MR-7 supports one.
13. **Update `docs/reference/API.md:4662`** (`EvaluationResult` docs) — document that `llm_structured` evaluations now populate `details["evidence"]` (verbatim quote or empty string) and `details["evidence_coerced"]` (bool; True if verdict was downgraded).
14. **Update `skills/create-loop/reference.md`** `check_semantic` state template — add evidence-contract language to the `evaluate.prompt:` field so wizard-generated loops do not immediately trigger MR-7.
15. **Add integration test in `test_ll_loop_execution.py`** (optional but recommended) — exercise the full path: mock `evaluate_llm_structured()` returning empty `evidence` → confirm FSM routes to `on_no` rather than `on_yes`, verifying coercion propagates through `FSMExecutor._run_evaluate_step()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_is_llm_judged()` already exists in `validation.py` (used by `_validate_partial_route_dead_end()` / MR-4 rule) — reuse it directly in the new validator function; it returns `True` for states with `evaluate.type in ("llm_structured", "check_semantic")` or `action_type == "prompt"` with no evaluate block
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
- `/ll:wire-issue` - 2026-06-27T06:12:20 - `5eb6d3df-3646-4ad2-82ed-98bdde238fad.jsonl`
- `/ll:refine-issue` - 2026-06-27T05:33:35 - `15663aad-3484-4d3c-b333-946a0e331e1a.jsonl`
- `/ll:format-issue` - 2026-06-27T05:22:57 - `9f4322ee-5b7f-41c1-ae57-47e6963891ed.jsonl`
- `/ll:capture-issue` - 2026-06-27T05:17:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd21288e-7370-4e7e-8040-6f118e73e291.jsonl`

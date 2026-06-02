---
id: FEAT-1791
title: '`check_contract` Boundary-Mismatch Evaluator'
type: FEAT
priority: P3
captured_at: '2026-05-29T19:08:54Z'
completed_at: '2026-06-01T19:50:21Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: done
labels:
- feature
- loops
- evaluator
- qa
- integration
parent: EPIC-1663
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1791: `check_contract` Boundary-Mismatch Evaluator

## Summary

Add a new evaluator kind (`check_contract` / `evaluate.type: contract`) that reads two related artifacts simultaneously and asserts contract alignment between them — API response shape ↔ consumer hook type, file path ↔ link `href`, state-transition map ↔ actual `.update({status})` calls. Designed as a stronger replacement for `check_semantic` in build-feature harnesses where "did this PR break the contract between producer and consumer?" is the actual quality bar.

## Current Behavior

The loop FSM currently provides these evaluator types:

- **Mechanical**: `exit_code`, `output_numeric`, `mcp_result`, `convergence`, `diff_stall`
- **Semantic**: `llm_structured` (evaluates a single output blob against a prompt)

None of these evaluators read *both sides of an interface simultaneously*. When a harness implements a producer (e.g., API endpoint) and a consumer (e.g., front-end hook), there is no built-in way to assert that their contracts align. Harness authors must hand-roll paired checks inside `check_semantic` prompts, which are single-output evaluators by design and tend to evaluate one artifact at a time.

## Expected Behavior

A new `contract` evaluator type (`evaluate.type: contract`) is available. Harness authors declare one or more `(producer, consumer)` pairs with optional regex extraction patterns and a contract rule. The evaluator:

1. Reads both files in each pair
2. Applies optional regex to extract the relevant slices
3. Composes a focused LLM judge prompt with both slices side-by-side
4. Returns a per-pair verdict and routes the FSM accordingly

Verdicts: `yes` (all pairs aligned → `on_yes`), `no` (any pair fails → `on_no`), `error` (file unreadable or regex no-match → `on_no`).

## Motivation

`revfactory/harness`'s `qa-agent-guide.md` documents (with 7 production bug case studies from SatangSlide) a failure class our current evaluators miss: **boundary mismatch** — two components each correctly implemented but disagreeing at the integration seam. Static type checks and existence checks miss these because:

- TypeScript generic casts (`fetchJson<SlideProject[]>()`) make the compiler accept any runtime shape
- `npm run build` exit-code 0 ≠ runtime correctness
- "API endpoint exists" ≠ "API response shape matches consumer expectation"

Our current evaluators address two layers — mechanical (`exit_code`, `output_numeric`, `mcp_result`) and semantic (`llm_structured`) — but nothing reads *both sides of an interface at once*. `check_semantic` could in principle do this with the right prompt, but in practice it tends to evaluate a single output blob, not a paired (producer, consumer) read.

This issue formalizes the pattern as a distinct evaluator kind so harness authors can declare integration gates explicitly rather than hand-rolling them in semantic prompts.

## Use Case

A user has a harness that implements a new API endpoint and its corresponding front-end hook. They want to gate progression on shape alignment. They write:

```yaml
check_contract:
  action_type: contract
  pairs:
    - producer: "src/app/api/projects/route.ts"
      producer_pattern: "NextResponse\\.json\\((.+?)\\)"
      consumer: "src/hooks/useProjects.ts"
      consumer_pattern: "fetchJson<(.+?)>"
      contract: "shape and field names must align (camelCase on both sides, no wrapping mismatch)"
  evaluate:
    type: contract
  on_yes: check_invariants
  on_no: execute
```

The evaluator reads both files, extracts the producer's response shape and the consumer's expected type, and asks an LLM judge a focused question: *"Does this producer shape satisfy this consumer contract?"* — with both code blocks in the prompt. Routes to `on_yes` only on a clean match.

## API/Interface

New evaluator kind:

```yaml
evaluate:
  type: contract
```

State-level config (under the state, not under `evaluate`):

```yaml
check_contract:
  action_type: contract  # new action_type — runs the contract read+compare, no shell needed
  pairs:                 # one or more producer/consumer pairs
    - producer: <path>
      producer_pattern: <regex>   # optional — extract just the relevant slice
      consumer: <path>
      consumer_pattern: <regex>
      contract: <string>          # the alignment rule the judge enforces
  evaluate:
    type: contract
    severity: error               # any pair-level failure routes on_no
  on_yes: <state>
  on_no: <state>
```

Verdicts: `yes` (all pairs aligned), `no` (any pair fails), `error` (file unreadable / pattern matches zero hits).

## Implementation Steps

1. **Schema** — add `"contract"` to the `Literal[...]` union in `EvaluateConfig.type` in `scripts/little_loops/fsm/schema.py:EvaluateConfig`; add a `pairs: list[dict] | None = None` field; update both `to_dict()` and `from_dict()` to handle the new field.

2. **Validation** — add `"contract": ["pairs"]` to `EVALUATOR_REQUIRED_FIELDS` in `scripts/little_loops/fsm/validation.py:64`; since `contract` uses an LLM judge, it must be explicitly excluded from `NON_LLM_EVALUATOR_TYPES` (line 80) so meta-loop MR-1 lint correctly flags states that use it without a paired non-LLM evaluator.

3. **Executor action mode** — add `if state.action_type == "contract": return "contract"` to `_action_mode()` in `scripts/little_loops/fsm/executor.py:1357`; handle the `"contract"` mode in `_execute_state()` to skip shell/prompt action execution entirely (action output = `""`, exit_code = `0`) and proceed directly to `_evaluate()`.

4. **Evaluator function** — add `evaluate_contract(config, context)` to `scripts/little_loops/fsm/evaluators.py`; it reads each pair's producer/consumer files, applies optional regex extraction, composes a focused LLM judge prompt with both slices, calls `resolve_host().build_blocking_json(...)` using the identical pattern from `evaluate_llm_structured()` (lines ~740–910; `resolve_host().build_blocking_json(...)` call at line 777); add an `elif eval_type == "contract":` branch in the `evaluate()` dispatcher; add `"contract"` to `_EXIT_CODE_AWARE_EVALUATORS` frozenset at line 1187 (the evaluator reads files itself, not action output).

5. **Verdict normalization** — `evaluate_contract()` returns `EvaluationResult(verdict="yes"|"no"|"error", details={"pair_results": [...]})` so `audit-loop-run` can render which specific pair failed.

6. **Tests** — add `TestContractEvaluator` class to `scripts/tests/test_fsm_evaluators.py` following the `TestLLMStructuredEvaluator` mock pattern (`patch("little_loops.fsm.evaluators.subprocess.run")`); cover: aligned pair (`yes`), mismatched field names (`no`), camelCase/snake_case mismatch (`no`), missing file (`error`), regex no-match (`error`); add dispatcher test in `TestEvaluateDispatcher`; update the `_EXIT_CODE_AWARE_EVALUATORS` parametrize lists.

7. **Docs** — add `check_contract` section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` between the `check_mcp` section (line 107) and the `check_skill` section (line 162); it is deterministic-input + LLM-judged, cheaper than `check_skill`'s full agentic session.

8. **Example** — add a commented `check_contract` block to `scripts/little_loops/loops/harness-multi-item.yaml` (or create `scripts/little_loops/loops/examples/contract-demo.yaml` after creating the subdirectory).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Export `evaluate_contract` from `scripts/little_loops/fsm/__init__.py` — add to the import line alongside `evaluate_blind_comparator` and add to `__all__` (lines 82–95)
10. Update `scripts/tests/test_fsm_schema_fuzz.py` — add `"contract"` to `valid_types` list (line 44)
11. Update `scripts/tests/test_fsm_evaluators.py` — add `"contract"` to `test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators` parametrize (line 626)
12. Add `TestContractEvaluatorValidation` class to `scripts/tests/test_fsm_validation.py` (follow `TestComparatorEvaluatorValidation` at line 391)
13. Add contract round-trip tests to `scripts/tests/test_fsm_schema.py` (follow `TestMcpToolSchema` at line 1819)
14. Add `test_action_type_contract_skips_runner` to `scripts/tests/test_fsm_executor.py:TestActionType` (follow `TestActionTypeMcpTool` at line 403)
15. Update `docs/guides/LOOPS_GUIDE.md` — add `contract` row to evaluator catalog table; add to exit-code-aware prose paragraph
16. Add commented `check_contract` block to `scripts/little_loops/loops/harness-single-shot.yaml` between `check_mcp` and `check_skill` gates

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — add `evaluate_contract()` function; add `elif eval_type == "contract":` branch in `evaluate()` dispatcher; add `"contract"` to `_EXIT_CODE_AWARE_EVALUATORS` frozenset (line 1187)
- `scripts/little_loops/fsm/schema.py` — add `"contract"` to `EvaluateConfig.type` `Literal[...]` union; add `pairs: list[dict] | None = None` field; update `to_dict()` / `from_dict()`
- `scripts/little_loops/fsm/executor.py` — add `"contract"` case to `_action_mode()` (line 1357); handle contract mode in `_execute_state()` to skip action execution
- `scripts/little_loops/fsm/validation.py` — add `"contract": ["pairs"]` to `EVALUATOR_REQUIRED_FIELDS` (line 64); explicitly exclude `"contract"` from `NON_LLM_EVALUATOR_TYPES` (line 80)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `check_contract` section between `check_mcp` (line 107) and `check_skill` (line 162)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — add `evaluate_contract` to imports and `__all__` exports (same pattern as `evaluate_llm_structured`, `evaluate_blind_comparator`, etc. at lines 82–95)
- `scripts/little_loops/loops/harness-single-shot.yaml` — add commented `check_contract` block between `check_mcp` and `check_skill` gates (companion annotated template; keeps it consistent with harness-multi-item.yaml)
- `scripts/tests/test_fsm_schema_fuzz.py` — add `"contract"` to `valid_types` list (line 44); without this, the fuzz strategy never generates `contract`-typed configs

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:FSMExecutor._evaluate()` — calls `evaluate()` dispatcher; `FSMExecutor._action_mode()` routes action types — both touched in Step 3 above
- `scripts/little_loops/cli/loop/__init__.py` — `validate` subcommand transitively calls `validation.py`; no direct changes needed (schema changes propagate automatically)

### Similar Patterns
- `evaluate_llm_structured()` in `scripts/little_loops/fsm/evaluators.py` — identical `resolve_host().build_blocking_json(...)` + `subprocess.run` + envelope-parsing pattern to follow
- `evaluate_blind_comparator()` in the same file — shows how multi-pair verdict normalization works
- `EVALUATOR_REQUIRED_FIELDS` entries with required fields (e.g., `"comparator": ["baseline_path"]`) — model for `"contract": ["pairs"]`

### Tests
- `scripts/tests/test_fsm_evaluators.py` — add `TestContractEvaluator` class (follow `TestLLMStructuredEvaluator` mock pattern at line 650); add `TestEvaluateDispatcher.test_dispatch_contract`; add `"contract"` to `test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators` parametrize (line 626); do NOT add `contract` to `test_dispatch_exit_code_124_short_circuits_to_error` (line 553) or `test_dispatch_nonzero_exit_generalized_short_circuit` (line 604) — `contract` is exit-code-aware and exempt from those lists

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — add `contract` type validity, round-trip, and `pairs`-field omission tests (follow `TestMcpToolSchema` pattern at line 1819); cover: `EvaluateConfig(type="contract")` validity, `pairs` field serialized/deserialized correctly, `pairs=None` omitted from `to_dict()` output
- `scripts/tests/test_fsm_validation.py` — add `TestContractEvaluatorValidation` class (follow `TestComparatorEvaluatorValidation` at line 391); cover: `pairs` required-field check (missing `pairs` raises error), MR-1 fires when meta-loop uses only a `contract` evaluator (same as `comparator` since both are excluded from `NON_LLM_EVALUATOR_TYPES`)
- `scripts/tests/test_fsm_executor.py` — add `test_action_type_contract_skips_runner` in `TestActionType` (line 268); verify that a state with `action_type="contract"` never invokes `MockActionRunner` (follow `TestActionTypeMcpTool` pattern at line 403)
- `scripts/tests/test_fsm_schema_fuzz.py` — add `"contract"` to `valid_types` list (line 44); will silently under-test the new type without this update

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `check_contract` section between `check_mcp` (line 107) and `check_skill` (line 162)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — add `contract` row to the `### Evaluators` catalog table; add `contract` to the exit-code-aware evaluator prose paragraph in that section (same paragraph that names `diff_stall`, `action_stall`, `llm_structured`, etc.)

### Configuration
- N/A

## Acceptance Criteria

- [ ] `ll-loop validate` accepts the new schema and rejects malformed `pairs:` blocks with clear errors
- [ ] Evaluator runs without spawning a shell action (action_type: contract is self-contained)
- [ ] Multi-pair states report which specific pair failed
- [ ] Documentation added to AUTOMATIC_HARNESSING_GUIDE.md with placement guidance
- [ ] Tests cover aligned, mismatched, file-missing, regex-no-match cases

## Impact

- **Priority**: P3 — Important for harness quality but not blocking existing workflows; `check_semantic` is an available workaround
- **Effort**: Medium — New evaluator module (~100-150 lines), schema extension, tests, and docs; no changes to existing evaluators
- **Risk**: Low — Net-new code path behind `action_type: contract`; existing loops and evaluators unaffected
- **Breaking Change**: No

## Out of Scope

- Auto-detecting producer/consumer pairs from the codebase (that's a separate skill, possibly an extension to `/ll:audit-architecture`).
- Code mutation to *fix* mismatches (this evaluator only reports; fixes belong to the harness's `execute` retry).

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | New evaluator slots into the existing evaluation chain documentation |
| `scripts/little_loops/fsm/evaluators.py` | Where the evaluator function lives; see `evaluate_llm_structured()` for the LLM judge call pattern |
| `scripts/little_loops/fsm/schema.py:EvaluateConfig` | Dataclass for `evaluate:` block config — add `pairs` field here |
| `scripts/little_loops/fsm/validation.py:EVALUATOR_REQUIRED_FIELDS` | Master registry of valid evaluator types — add `"contract": ["pairs"]` here |
| `scripts/little_loops/fsm/executor.py:FSMExecutor._action_mode` | Action type dispatcher — add `"contract"` self-contained mode here |
| `scripts/little_loops/loops/harness-multi-item.yaml` | Harness template to extend with a commented `check_contract` example block |

## Session Log
- `/ll:ready-issue` - 2026-06-01T19:38:34 - `64311e66-c2b0-43ee-8958-99a54082ecb2.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `34f84fcf-43f5-4359-b8a7-255b2b1e5f21.jsonl`
- `/ll:wire-issue` - 2026-06-01T20:00:00 - `current.jsonl`
- `/ll:refine-issue` - 2026-06-01T19:26:42 - `393dcf8d-0e5a-4ff6-ba4d-fb43986db4b5.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T19:28:53 - `aea29468-dd94-4692-a4e8-f97561c7c2a7.jsonl`
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`

---

## Status
open

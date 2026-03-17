---
discovered_date: 2026-03-17
discovered_by: analyze-loop
source_loop: general-task
source_state: check_done
---

# BUG-794: check_done LLM evaluator JSON parse failure in general-task loop

## Summary

The `check_done` state uses an `llm_structured` evaluator to determine if the task is complete. The LLM returned a text preamble before the JSON verdict object, causing the JSON parser to fail with `"Expecting value: line 1 column 1 (char 0)"`. The loop routed to `failed` and terminated at iteration 3 instead of completing normally.

## Loop Context

- **Loop**: `general-task`
- **State**: `check_done`
- **Signal type**: eval_failure
- **Occurrences**: 1
- **Last observed**: 2026-03-17T21:34:32.219467+00:00

## History Excerpt

From loop status at failure:

```json
{
  "current_state": "failed",
  "iteration": 3,
  "last_result": {
    "verdict": "error",
    "details": {
      "error": "Failed to parse LLM response: Expecting value: line 1 column 1 (char 0)",
      "raw_preview": "{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"duration_ms\":46906,\"result\":\"The evaluation report covers all 7 guides with documented fixes. The git log confirms multiple commits correcting inaccuracies. The task appears complete.\\n\\n{\\\"verdict\\\": \\\"yes\\\""
    }
  }
}
```

The LLM included a natural-language explanation before the JSON object (e.g. `"The evaluation report covers all 7 guides...\n\n{"verdict": "yes"}`). The evaluator tried to parse the full `result` string as JSON and failed on the leading text.

## Expected Behavior

The `llm_structured` evaluator should extract the JSON object from the LLM response even when the model includes a preamble before the JSON. Alternatively, the system prompt for the evaluator should more reliably enforce JSON-only output.

## Proposed Fix

Use the `claude` CLI's `--json-schema` flag (structured outputs, print mode only) to enforce schema-validated JSON output at the model level, eliminating preamble at the source:

```
claude -p <prompt> --output-format json --json-schema '<schema-json>' ...
```

This replaces the current approach of embedding the schema in the user prompt and hoping the model complies. The CLI validates the model's response against the schema before returning it, so `result` is always a schema-conformant dict — no preamble possible.

The user prompt is also simplified to remove the redundant "Respond with ONLY valid JSON matching this schema" instruction and the inline schema dump, since enforcement moves to the CLI flag.

## Acceptance Criteria

- [x] `llm_structured` evaluator passes `--json-schema` to `claude` CLI so model output is schema-validated
- [x] User prompt no longer embeds schema or JSON-only instruction (schema enforcement is at CLI level)
- [ ] Test coverage updated to reflect `--json-schema` flag in mocked CLI invocations

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: in `evaluate_llm_structured()` at line 643
- **Cause**: `llm_result = json.loads(raw_result)` where `raw_result` is the `"result"` field from the Claude CLI JSON envelope. When the model prepends natural-language text before the JSON object (e.g. `"The task is complete.\n\n{\"verdict\": \"yes\"...}`), `json.loads` fails because the string does not start with `{`. The `json.JSONDecodeError` is caught at line 658 and returned as `EvaluationResult(verdict="error", ...)`. Because `check_done` in `.loops/general-task.yaml:53` routes `on_error: failed`, the loop terminates immediately.

The user prompt at lines 561-566 already instructs `"Respond with ONLY valid JSON (no markdown fences, no explanation)"` but this does not reliably suppress preamble — especially when the shell action output fed to the evaluator contains multi-sentence narrative (as in the failing run).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — primary fix at lines 638-663; specifically the `elif raw_result:` branch (line 642) that calls `json.loads(raw_result)` without fallback extraction

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — calls `evaluate()` dispatcher which calls `evaluate_llm_structured()`
- `.loops/general-task.yaml:40-53` — `check_done` state definition; uses `llm_structured` evaluator with `on_error: failed`

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py:619-628` — the JSONL fallback that already splits on `"\n"` and retries `json.loads` on the last line; the preamble fix should follow the same spirit of "try, then fall back"
- `scripts/little_loops/fsm/evaluators.py:291-295` — `evaluate_output_contains` regex-with-fallback pattern (try regex, fall back gracefully)
- `scripts/little_loops/output_parsing.py:54-115` — `parse_ready_issue_output()` multi-strategy cascade for extracting structured data from mixed LLM text; closest existing template for robust fallback recovery
- Prior bug `.issues/completed/P2-BUG-015-ready-issue-verdict-parsing-failure.md` — same class of problem (LLM output doesn't match expected format); fix required two rounds, combining robust parsing + stricter prompts

### Other Affected Loops
All loops using `llm_structured` evaluators are vulnerable to this same failure:
- `loops/fix-quality-and-tests.yaml`, `loops/issue-refinement.yaml`, `loops/sprint-build-and-validate.yaml`, `loops/issue-staleness-review.yaml`, `loops/issue-size-split.yaml`, `loops/rl-coding-agent.yaml`, `loops/evaluation-quality.yaml`, `loops/apo-feedback-refinement.yaml`

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestLLMStructuredEvaluator` class (line 551); use `_cli_stdout()` helper and `mock_cli` fixture pattern to add new test cases
- `scripts/tests/test_ll_loop_errors.py` — covers `general-task` error scenarios; may need updating
- `scripts/tests/test_builtin_loops.py` — audits all `llm_structured` evaluate states in built-in loops

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — documents `llm_structured` evaluator; may need a note on preamble robustness

## Implementation Steps

1. **Fix `evaluate_llm_structured()` in `evaluators.py`** *(done)*:
   - Simplify `user_prompt` to remove the inline schema and JSON-only instruction (lines 561-566)
   - Add `"--json-schema", json.dumps(effective_schema)` to the `cmd` list after `--output-format json`

2. **Update tests** in `scripts/tests/test_fsm_evaluators.py`: mock CLI invocations should include `--json-schema` in the expected command args; preamble-handling test cases are no longer needed (the CLI prevents preamble).

3. **Run tests**: `python -m pytest scripts/tests/test_fsm_evaluators.py -v`

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-17 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-03-17T21:45:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34031d6c-5edf-4e1a-8019-bb589774481d.jsonl`

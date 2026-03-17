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

Two options:
1. **Robust parsing**: In the `llm_structured` evaluator, use a regex or `json.loads` with fallback to scan for the first `{` and attempt to parse from there before failing.
2. **Stricter prompt**: Strengthen the system prompt to prohibit any text before the JSON object (e.g., add `"Output ONLY the JSON object. Do not include any explanation or preamble."`).

Option 1 is more resilient; option 2 reduces but doesn't eliminate the failure mode.

## Acceptance Criteria

- [ ] `llm_structured` evaluator succeeds when LLM returns preamble text before the JSON object
- [ ] Loop does not route to `failed` due to JSON parse errors that could be recovered
- [ ] Test coverage for evaluator handling of mixed text+JSON responses

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-17 | Priority: P2

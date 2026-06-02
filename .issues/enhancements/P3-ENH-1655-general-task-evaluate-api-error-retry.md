---
id: ENH-1655
type: ENH
priority: P3
status: cancelled
discovered_date: 2026-05-23
discovered_by: audit-loop-run
confidence_score: 85
outcome_confidence: 80
relates_to: [ENH-1650, BUG-1657]
depends_on: []
---

# ENH-1655: Action API errors should retry instead of terminating the loop

## Summary

Transient Claude CLI API failures in `general-task` prompt-action states still route `on_error: diagnose → failed`, killing long-running loops on ephemeral infra errors. The original trigger was an `llm_structured` evaluator in `check_done`, but ENH-1658 replaced that evaluator with a shell counter (`count_done`). No `llm_structured` evaluators remain in `general-task.yaml`. The surviving risk is now in the five prompt-action states (`define_done`, `plan`, `execute`, `check_done`, `continue_work`) — any one of which can fail with a transient API error and immediately route to `diagnose → failed`.

## Motivation

This enhancement would:
- Prevent losing hours of forward progress due to ephemeral infrastructure failures — the `2026-05-23T224029` run lost 34 minutes of work on a single empty-error-string API failure
- The `execute` and `continue_work` states are the hot path in long-running loops; a transient error on iteration 14 of a 30-iteration run discards all prior completed iterations
- Retry with `max_retries: 2` adds at most a few minutes of latency on failure and saves the full run on recovery — far cheaper than restarting from scratch
- Cost: two retries (~$0.60 extra per failure at Sonnet pricing) is negligible compared to losing the run

## Current Behavior

During the `2026-05-23T224029` run of `general-task`, iteration 14's `check_done` evaluate call returned:
```json
{"verdict": "error", "api_error": true, "error": "claude CLI error: "}
```

This was a transient API/infra failure (empty error string, no underlying logic issue). The `on_error: diagnose` routing immediately moved to `diagnose → failed`, discarding 34 minutes of forward progress. The loop had successfully completed 5 prior evaluate calls without issues.

After ENH-1658, the `llm_structured` evaluator path is gone, but the same failure mode survives via prompt-action errors: `define_done`, `plan`, `execute`, `check_done`, and `continue_work` all use `action_type: prompt` and route `on_error: diagnose`. A transient API error on any of these states terminates the run identically.

## Expected Behavior

Prompt-action states that encounter a transient API error retry the failed Claude CLI call up to `max_retries` times (default 2) before routing to `on_error`. On successful retry, the loop continues forward from that state, preserving all prior iteration progress. On retry exhaustion, the existing `on_error: diagnose` routing applies unchanged.

## Proposed Solution

Add `retry_on_api_error: true` to prompt-action states so the harness retries the Claude CLI call before escalating to `on_error`. The highest-impact states are `execute` and `continue_work` (the hot path for long runs); `define_done` and `plan` are one-shot setup states where retry is less critical but still beneficial.

Minimal fix for the hot-path states in `general-task`:
```yaml
states:
  execute:
    action_type: prompt
    retry_on_api_error: true
    max_retries: 2
    # ... existing action/next/on_error unchanged

  continue_work:
    action_type: prompt
    retry_on_api_error: true
    max_retries: 2
    # ... existing action/next/on_error unchanged
```

Broader fix: consider making `retry_on_api_error: true` the harness default for all `action_type: prompt` states across all loops, since prompt actions that fail due to API errors leave no side effects and are safe to retry.

## Implementation Steps

1. Check whether `retry_on_api_error` is already supported in `scripts/little_loops/loop_runner.py` — if not, implement retry logic in the runner before touching loop YAML files
2. Add `retry_on_api_error: true` and `max_retries: 2` to `execute` and `continue_work` states in `loops/general-task.yaml` (highest-impact, hot-path states)
3. Optionally extend to `define_done` and `plan` states in the same file for full coverage
4. Evaluate adding `retry_on_api_error: true` as a harness default for all `action_type: prompt` states to benefit all loops without per-file changes
5. Test: run `ll-loop run general-task` and verify retry behavior triggers correctly on API error

## API/Interface

New YAML keys for loop state definitions:

```yaml
# On any action_type: prompt state
retry_on_api_error: true    # boolean, default false; retries on transient API/CLI errors before on_error routing
max_retries: 2              # integer; number of retry attempts before escalating to on_error
```

If implemented as a harness default, no per-state YAML changes are required for existing loops.

## Integration Map

### Files to Modify
- `loops/general-task.yaml` — add `retry_on_api_error: true`, `max_retries: 2` to `execute`, `continue_work` (and optionally `define_done`, `plan`) states

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — implement retry logic if not yet supported by the harness runner
- `grep -r "action_type: prompt" loops/` — identify other loops that would benefit from retry once the harness supports it

### Similar Patterns
- `grep -r "on_error: diagnose" loops/` — find all loops with the same failure-path pattern

### Tests
- TBD — identify loop execution tests covering `on_error` routing and API error handling

### Documentation
- N/A if adding per-state YAML keys only; update loop authoring docs if adding `retry_on_api_error` as a new harness default

### Configuration
- N/A

## Impact

- Eliminates the most common cause of premature loop termination observed in production
- Each evaluate call costs $0.30–$0.32 (Sonnet); retrying twice is still far cheaper than losing the entire run
- Applies to any loop using `llm_structured` evaluators with `on_error: diagnose`

---

## Scope Boundaries

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1650 (debug-loop-run signal for single evaluate-error termination) remains valid even after this issue ships — it targets exhausted-retry and non-retryable paths. BUG-1657 touches `general-task.check_done` prompt content; this issue adds `retry_on_api_error` keys to prompt-action states. No conflict expected, but implement in sequential commits to keep the YAML diffs readable.

**Retargeted 2026-05-24**: ENH-1658 has landed (`42cf8529`) — `check_done`'s `llm_structured` evaluator is replaced by the `count_done` shell counter. No `llm_structured` evaluators remain in `general-task.yaml`. This issue is now retargeted to prompt-action states (`execute`, `continue_work`, and optionally `define_done`/`plan`) where transient API errors still route directly to `diagnose → failed`. The `depends_on: [ENH-1658]` dependency is satisfied and removed.

**Complementary issue**: ENH-1671 (delta-aware `check_done` prompt) reduces per-iteration session duration, which in turn reduces API-failure exposure. Neither ENH-1655 nor ENH-1671 is complete alone: shorter sessions reduce failure probability; retry handles failures when they still occur. Implement both for complete coverage.


## Labels

`loop-reliability`, `retry`, `resilience`, `general-task`

## Status

**Cancelled** | Created: 2026-05-23 | Priority: P3

## Cancellation Note

Superseded by **ENH-1677** (apply existing `max_retries`/`on_retry_exhausted` mechanism to `execute` and `continue_work` in `general-task.yaml`) and **ENH-1678** (add `retryable_exit_codes` filter to the runner). The `retry_on_api_error` flag proposed here does not exist in the harness and is not needed — the `on_error: self` + `max_retries` pattern (ENH-713) covers the same failure mode. ENH-1677 delivers the concrete YAML fix; ENH-1678 adds exit-code precision. Nothing in this issue's scope is left uncovered.

## Session Log
- `/ll:format-issue` - 2026-05-24T17:25:35 - `a5267084-551d-4f30-8319-d02e8535f537.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T13:37:49 - `1c29e127-5f7b-421f-9734-c94217103bba.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`

---

## Tradeoff Review Note

**Reviewed**: 2026-05-24 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first — retarget after ENH-1658 lands. The current scope targets the `llm_structured` evaluator in `check_done`, which ENH-1658 will replace with a shell counter. Implementing as-written would immediately become dead code. After ENH-1658 lands, retarget the retry mechanism to remaining LLM-evaluated states (e.g. `diagnose`).
- `/ll:tradeoff-review-issues` - 2026-05-24T13:57:35 - `f0630921-fb2f-426a-a549-1a1d30e210f9.jsonl`

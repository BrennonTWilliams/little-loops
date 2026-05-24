---
id: ENH-1655
type: ENH
priority: P3
status: open
discovered_date: 2026-05-23
discovered_by: audit-loop-run
confidence_score: 85
outcome_confidence: 80
relates_to: [ENH-1650, BUG-1657]
---

# ENH-1655: Evaluate API errors should retry instead of terminating the loop

## Summary

The `general-task` loop's `check_done` state routes evaluate errors to `diagnose → failed` via `on_error`, which means any transient Claude CLI API failure kills the entire loop. A 34-minute run making steady forward progress (5 complete `continue_work → check_done` cycles) was terminated by a single empty API error in the evaluate step.

## Problem

During the `2026-05-23T224029` run of `general-task`, iteration 14's `check_done` evaluate call returned:
```json
{"verdict": "error", "api_error": true, "error": "claude CLI error: "}
```

This was a transient API/infra failure (empty error string, no underlying logic issue). The `on_error: diagnose` routing immediately moved to `diagnose → failed`, discarding 34 minutes of forward progress. The loop had successfully completed 5 prior evaluate calls without issues.

The root cause is structural: `evaluate` errors are treated identically to `action` errors — both route to `on_error`. But evaluate failures are fundamentally different: they are read-only judgments that can be safely retried, unlike action failures that may have left side effects.

## Proposal

Add retry-on-API-error semantics to the evaluate step, or treat API errors as soft failures that route to `on_no` (or a dedicated retry path) rather than `on_error`.

Minimal fix for `general-task`:
```yaml
states:
  check_done:
    evaluate:
      type: llm_structured
      prompt: "..."
      retry_on_api_error: true
      max_retries: 2
```

Broader fix: consider making this the default behavior for all `llm_structured` evaluators across all loops, since evaluate calls are idempotent reads.

## Impact

- Eliminates the most common cause of premature loop termination observed in production
- Each evaluate call costs $0.30–$0.32 (Sonnet); retrying twice is still far cheaper than losing the entire run
- Applies to any loop using `llm_structured` evaluators with `on_error: diagnose`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1650 (debug-loop-run signal for single evaluate-error termination) remains valid even after this issue ships — it targets exhausted-retry and non-retryable paths. Coordinate edits with BUG-1657: both touch `general-task.check_done.evaluate` in `loops/general-task.yaml` — this issue modifies `on_error` routing, BUG-1657 modifies `prompt` content. Implement in the same PR or sequential commits to avoid merge conflicts on the same YAML block.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`

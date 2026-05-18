---
id: BUG-1612
type: BUG
priority: P3
title: Add pre-terminal diagnose states to refine-to-ready-issue, rl-coding-agent, agent-eval-improve loops
status: open
parent: BUG-1606
size: Small
---

# BUG-1612: Add pre-terminal diagnose states to refine-to-ready-issue, rl-coding-agent, agent-eval-improve loops

## Summary

Add a pre-terminal `diagnose` state to `refine-to-ready-issue`, `rl-coding-agent`, and `agent-eval-improve` loop YAML files. Update `test_builtin_loops.py` for `refine-to-ready-issue`.

## Parent Issue

Decomposed from BUG-1606: Add pre-terminal diagnose states to 12 affected loop YAML files

## Background

`scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` calls `return self._finish("terminal")` BEFORE executing any terminal state action. An `action:` field on a `failed` terminal never executes. The correct pattern is a separate non-terminal `diagnose` state that runs the diagnostic prompt and routes `next: failed`.

These three loops have complex routing patterns with multiple states feeding into `failed` — the `refine-to-ready-issue` loop is particularly complex with 8+ states routing to `failed`.

## Affected Loops

| Loop | File | Failed State Line | States routing to `failed` |
|------|------|-------------------|----------------------------|
| `refine-to-ready-issue` | `scripts/little_loops/loops/refine-to-ready-issue.yaml` | 349 | `resolve_issue`, `check_lifetime_limit`, `verify_scores_persisted_final`, `check_readiness`, `retry_confidence_check`, `issue_size_review`, `write_broke_down`, others → `on_error`/`on_no`/`on_retry_exhausted: failed` (8+ states) |
| `rl-coding-agent` | `scripts/little_loops/loops/rl-coding-agent.yaml` | 134 | `score` → convergence evaluator `route: error: failed` |
| `agent-eval-improve` | `scripts/little_loops/loops/agent-eval-improve.yaml` | 105 | `run_eval`, `score_results`, `analyze_failures`, `route_quality`, `refine_config` → `on_retry_exhausted`/`on_error`/`route: error: failed` (6 states) |

## Implementation Steps

### For each loop:

1. Read the loop YAML and carefully enumerate ALL states routing to `failed` (especially `refine-to-ready-issue` which has 8+ such states).

2. Add the appropriate `diagnose` state immediately before the `failed` terminal:

**`refine-to-ready-issue`** — artifact: issue file via `${captured.issue_id.output}`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The refine-to-ready-issue loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - Report the issue ID being refined: ${captured.issue_id.output}
    - Identify which state failed (resolve_issue, check_lifetime_limit, check_readiness, etc.).
    - If the issue file exists, read its current status and last session log entry.
    - Identify the most likely failure cause (e.g., issue not found, lifetime limit exceeded, size-review decomposed it).

    Write a one-paragraph diagnostic summary the operator can use to re-run or inspect the issue.
  next: failed

failed:
  terminal: true
```

**`rl-coding-agent`** — no file artifacts; uses captured variables:
```yaml
diagnose:
  action_type: prompt
  action: |
    The rl-coding-agent loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - Report the last known observation: ${captured.observation.output}
    - Report the last known reward: ${captured.prev_reward.output}
    - Identify the most likely failure cause (convergence evaluator error in the score state).

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust the eval suite.
  next: failed
```

**`agent-eval-improve`** — artifacts: `evals/results/` via `${context.task_suite}`:
```yaml
diagnose:
  action_type: prompt
  action: |
    The agent-eval-improve loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - Check the evals/results/ directory for any partial evaluation output.
    - Report which state exhausted retries (run_eval, score_results, analyze_failures, or refine_config).
    - If any captured variables are available (eval_results, scores, failure_analysis), summarize them.
    - Identify the most likely failure cause.

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust eval configuration.
  next: failed
```

3. Update routing for each loop:
   - `refine-to-ready-issue`: all 8+ states with `on_error: failed`, `on_no: failed`, or `on_retry_exhausted: failed` → replace `failed` with `diagnose`. Use a grep pass to catch every occurrence: `grep -n ": failed" scripts/little_loops/loops/refine-to-ready-issue.yaml`
   - `rl-coding-agent`: `score` convergence evaluator `route: error: failed` → `route: error: diagnose`
   - `agent-eval-improve`: all 6 states with `on_retry_exhausted`/`on_error`/`route: error: failed` → `diagnose`. Grep first: `grep -n ": failed" scripts/little_loops/loops/agent-eval-improve.yaml`

4. Update `scripts/tests/test_builtin_loops.py`:
   - `TestRefineToReadyIssueSubLoop.test_breakdown_issue_on_error_is_failed` (line 696): change assertion target from `"failed"` → `"diagnose"`
   - Add `"diagnose"` to any required-states sets in `TestRefineToReadyIssueSubLoop`
   - Add `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` to `TestRefineToReadyIssueSubLoop`

5. Run `python -m pytest scripts/tests/test_builtin_loops.py -k "RefineToReady" scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py -v` and confirm all pass.

**Note**: `test_builtin_loops.py` is also modified by BUG-1610 and BUG-1611. Run this child last among the three to avoid file conflicts.

## Acceptance Criteria

- `refine-to-ready-issue.yaml`, `rl-coding-agent.yaml`, `agent-eval-improve.yaml` each have a `diagnose` state with `next: failed` before the `failed` terminal
- All states that previously routed to `failed` now route to `diagnose` — verified with grep (no remaining `on_error: failed`, `on_no: failed`, `on_retry_exhausted: failed` except within the `diagnose` state itself which has `next: failed`)
- Each `diagnose` state references the loop's actual artifacts or captured variables
- `test_builtin_loops.py` updated for RefineToReadyIssue test class
- All listed tests pass

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3772e425-1416-4cc8-baac-8e0f351122fa.jsonl`

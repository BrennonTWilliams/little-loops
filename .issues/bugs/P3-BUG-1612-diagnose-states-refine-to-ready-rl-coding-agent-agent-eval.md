---
id: BUG-1612
type: BUG
priority: P3
title: Add pre-terminal diagnose states to refine-to-ready-issue, rl-coding-agent,
  agent-eval-improve loops
status: done
completed_at: 2026-05-18T09:16:52Z
parent: BUG-1606
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
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
| `refine-to-ready-issue` | `scripts/little_loops/loops/refine-to-ready-issue.yaml` | 349 | `resolve_issue`, `check_lifetime_limit`, `verify_scores_persisted_final`, `retry_confidence_check`, `write_broke_down`, others → `on_error`/`on_no`/`on_retry_exhausted: failed` (8 states, 10 edges) |
| `rl-coding-agent` | `scripts/little_loops/loops/rl-coding-agent.yaml` | 134 | `score` → convergence evaluator `route: error: failed` |
| `agent-eval-improve` | `scripts/little_loops/loops/agent-eval-improve.yaml` | 105 | `run_eval`, `score_results`, `analyze_failures`, `route_quality`, `refine_config` → `on_retry_exhausted`/`on_error`/`route: error: failed` (5 states, 6 edges) |

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add `diagnose` state before line 349 (`failed` terminal); redirect 10 routing edges across 8 states
- `scripts/little_loops/loops/rl-coding-agent.yaml` — add `diagnose` state before line 134 (`failed` terminal); redirect 1 routing edge in `score` state
- `scripts/little_loops/loops/agent-eval-improve.yaml` — add `diagnose` state before line 105 (`failed` terminal); redirect 6 routing edges across 5 states
- `scripts/tests/test_builtin_loops.py` — update `TestRefineToReadyIssueSubLoop` (line 696+)

### States Routing to `failed` — Exact Line Numbers

**refine-to-ready-issue.yaml** (10 edges across 8 states):
| State | Routing key | Line |
|-------|-------------|------|
| `resolve_issue` | `on_error: failed` | 34 |
| `check_lifetime_limit` | `on_error: failed` | 77 |
| `refine_issue` | `on_error: failed` | 83 |
| `retry_confidence_check` | `on_error: failed` | 158 |
| `verify_scores_persisted_final` | `on_no: failed` | 193 |
| `verify_scores_persisted_final` | `on_error: failed` | 194 |
| `check_outcome` | `on_error: failed` | 258 |
| `check_refine_limit` | `on_error: failed` | 299 |
| `check_scores_from_file` | `on_error: failed` | 332 |
| `breakdown_issue` | `on_error: failed` | 338 |

**rl-coding-agent.yaml** (1 edge):
| State | Routing key | Line |
|-------|-------------|------|
| `score` | `route: { error: failed }` | 109 |

**agent-eval-improve.yaml** (6 edges across 5 states):
| State | Routing key | Line |
|-------|-------------|------|
| `run_eval` | `on_retry_exhausted: failed` | 30 |
| `score_results` | `on_retry_exhausted: failed` | 43 |
| `analyze_failures` | `on_retry_exhausted: failed` | 56 |
| `analyze_failures` | `on_error: failed` | 66 |
| `route_quality` | `route: { error: failed }` | 80 |
| `refine_config` | `on_retry_exhausted: failed` | 93 |

### Reference Patterns
- `scripts/little_loops/loops/general-task.yaml:97` — `diagnose` + `failed` pattern with `${env.PWD}/.loops/tmp/` artifact checks
- `scripts/little_loops/loops/rl-policy.yaml:55` — `diagnose` for `route: { error: diagnose }` wiring (same pattern as `rl-coding-agent`)
- `scripts/tests/test_builtin_loops.py:2618` — `test_diagnose_routes_to_failed` / `test_diagnose_is_not_terminal` test group pattern

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestRefineToReadyIssueSubLoop` at line 696; `test_breakdown_issue_on_error_is_failed` asserts `"failed"` — must change to `"diagnose"`

### Tests (Wiring Pass)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **new class** `TestRlCodingAgentLoop` needed; neither `rl-coding-agent` nor `agent-eval-improve` have structural test classes at all. At minimum add `test_diagnose_routes_to_failed`, `test_diagnose_is_not_terminal`, `test_score_error_routes_to_diagnose` for `rl-coding-agent`. Follow `TestSvgImageGeneratorLoop` pattern (line 2520). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — **new class** `TestAgentEvalImproveLoop` needed; add `test_diagnose_routes_to_failed`, `test_diagnose_is_not_terminal`, plus routing assertions for each of the 5 redirected states (`run_eval`, `score_results`, `analyze_failures`, `route_quality`, `refine_config`). [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — `agent-eval-improve` Notes paragraph references `on_retry_exhausted: failed` as the routing target; after the fix this becomes `on_retry_exhausted: diagnose`. Update prose to reflect new routing. [Agent 2 finding]

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
   - `agent-eval-improve`: all 5 states (6 edges) with `on_retry_exhausted`/`on_error`/`route: error: failed` → `diagnose`. Grep first: `grep -n ": failed" scripts/little_loops/loops/agent-eval-improve.yaml`

4. Update `scripts/tests/test_builtin_loops.py`:
   - `TestRefineToReadyIssueSubLoop.test_breakdown_issue_on_error_is_failed` (line 696): change assertion target from `"failed"` → `"diagnose"`
   - Add `"diagnose"` to any required-states sets in `TestRefineToReadyIssueSubLoop`
   - Add `test_diagnose_routes_to_failed` and `test_diagnose_is_not_terminal` to `TestRefineToReadyIssueSubLoop`

   **Test pattern to follow** (from `TestSvgImageGeneratorLoop` at `test_builtin_loops.py:2613`):
   ```python
   def test_diagnose_routes_to_failed(self, data: dict) -> None:
       """diagnose state must route to failed."""
       state = data["states"].get("diagnose", {})
       assert state.get("next") == "failed"

   def test_diagnose_is_not_terminal(self, data: dict) -> None:
       """diagnose state must not be a terminal state."""
       state = data["states"].get("diagnose", {})
       assert not state.get("terminal", False)
   ```

5. Run `python -m pytest scripts/tests/test_builtin_loops.py -k "RefineToReady" scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py -v` and confirm all pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `TestRlCodingAgentLoop` class to `scripts/tests/test_builtin_loops.py` — no structural test class exists for `rl-coding-agent`; add `test_diagnose_routes_to_failed`, `test_diagnose_is_not_terminal`, `test_score_error_routes_to_diagnose`. Follow `TestSvgImageGeneratorLoop` pattern (line 2520).
7. Add `TestAgentEvalImproveLoop` class to `scripts/tests/test_builtin_loops.py` — no structural test class exists for `agent-eval-improve`; add `test_diagnose_routes_to_failed`, `test_diagnose_is_not_terminal`, and routing assertions for each of the 5 redirected states.
8. Update `docs/guides/LOOPS_GUIDE.md` — `agent-eval-improve` Notes paragraph: change `on_retry_exhausted: failed` to `on_retry_exhausted: diagnose`.

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
- `/ll:manage-issue` - 2026-05-18T09:16:52 - `bf3fb87f-278b-48c9-b597-12b4f3947a22.jsonl`
- `/ll:ready-issue` - 2026-05-18T09:13:23 - `bf3fb87f-278b-48c9-b597-12b4f3947a22.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `697417bf-f86d-4109-9048-9654ee92178e.jsonl`
- `/ll:wire-issue` - 2026-05-18T09:07:28 - `a44ff833-9598-4234-9c06-5bd61e331ca0.jsonl`
- `/ll:refine-issue` - 2026-05-18T09:02:52 - `68664e8c-d8de-4564-a340-cd4b0b7bec08.jsonl`
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `3772e425-1416-4cc8-baac-8e0f351122fa.jsonl`

---
id: BUG-1606
type: BUG
priority: P3
title: "Add pre-terminal diagnose states to 12 affected loop YAML files"
status: open
parent: BUG-1603
size: Large
---

# BUG-1606: Add pre-terminal diagnose states to 12 affected loop YAML files

## Summary

Add a pre-terminal `diagnose` state to every built-in loop `failed` terminal state that currently lacks a diagnostic action. The FSM executor fires `_finish("terminal")` before executing any terminal state action, so an inline `action:` on the `failed` state has no effect — the correct pattern is a separate `diagnose` (or `report`) state that routes to `failed` as its terminal.

## Parent Issue

Decomposed from BUG-1603: failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history

## Background

`scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` at lines 307–325 checks `if state_config.terminal:` and calls `return self._finish("terminal")` BEFORE executing any state action. This means an `action:` field on a `failed` terminal never executes.

The correct pattern (already used by `rn-refine.yaml:282–283`) is a pre-terminal `diagnose` or `report` state that:
1. Executes the diagnostic prompt action
2. Routes (`next:`) to the `failed` terminal state

Reference implementation: `scripts/little_loops/loops/hitl-compare.yaml:278–292` — the `failed` state there has an `action_type: prompt` diagnostic action AND routes from a preceding state. Study the routing structure carefully.

## Affected Loops

| Loop | File | Failed State Line |
|------|------|-------------------|
| `html-anything` | `scripts/little_loops/loops/html-anything.yaml` | 221 |
| `svg-textgrad` | `scripts/little_loops/loops/svg-textgrad.yaml` | 295 |
| `general-task` | `scripts/little_loops/loops/general-task.yaml` | 97 |
| `rn-plan` | `scripts/little_loops/loops/rn-plan.yaml` | 288 |
| `rn-refine` | `scripts/little_loops/loops/rn-refine.yaml` | 302 |
| `recursive-refine` | `scripts/little_loops/loops/recursive-refine.yaml` | 818 |
| `refine-to-ready-issue` | `scripts/little_loops/loops/refine-to-ready-issue.yaml` | 349 |
| `rl-coding-agent` | `scripts/little_loops/loops/rl-coding-agent.yaml` | 134 |
| `rl-policy` | `scripts/little_loops/loops/rl-policy.yaml` | 55 |
| `agent-eval-improve` | `scripts/little_loops/loops/agent-eval-improve.yaml` | 105 |
| `prompt-across-issues` | `scripts/little_loops/loops/prompt-across-issues.yaml` | 99 (state: `error`) |
| `svg-image-generator` | `scripts/little_loops/loops/svg-image-generator.yaml` | 169 |

## Implementation Steps

### For each affected loop:

1. Read the loop YAML and identify:
   - All states that route to `failed` (or `error` for `prompt-across-issues`) — these are where `diagnose` will be inserted
   - What output artifacts the loop produces (e.g., `critique.md`, `review.md`, `plan-rubric.md`, `task.md`) — the diagnostic prompt must reference the loop's specific artifacts

2. Add a `diagnose` state (or `diagnose_failure`) immediately before the `failed` terminal:
   ```yaml
   diagnose:
     action_type: prompt
     action: |
       The <loop-name> loop has terminated with an unrecoverable failure.

       Diagnose what happened:
       - If ${captured.run_dir.output}/<artifact>.md exists, read it and summarize
         the last recorded scores or evaluation results.
       - Identify the most likely failure cause.

       Write a one-paragraph diagnostic summary the operator can use to re-run
       or adjust inputs.
     next: failed

   failed:
     terminal: true
   ```

3. Update all transitions that previously routed to `failed` to instead route to `diagnose`.

4. Each loop needs a **loop-specific** diagnostic prompt (not a generic copy-paste) that names the actual output artifacts for that loop. Budget ~10–15 min per loop for content authoring.

### Reference patterns

- `scripts/little_loops/loops/rn-refine.yaml:279` — `report` state as pre-terminal workaround (existing pattern)
- `scripts/little_loops/loops/hitl-compare.yaml:278–292` — canonical model with specific artifact paths

## Acceptance Criteria

- All 12 loop YAML files have a pre-terminal `diagnose` (or equivalent) state before their `failed`/`error` terminal
- Each `diagnose` state names the loop's actual output artifacts in its action prompt
- The `failed` terminal state itself retains only `terminal: true` (no action needed there)
- `ll-loop history <loop-name>` shows meaningful diagnostic output after a failure scenario
- No existing routing broken: all states that previously went to `failed` now go to `diagnose` (which routes to `failed`)

## Labels

`bug`, `loops`, `fsm`, `diagnostics`

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbd13cdc-51a4-41ee-85fe-30c33cc936aa.jsonl`

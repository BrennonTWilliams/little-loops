---
id: BUG-1609
type: BUG
priority: P3
title: Add pre-terminal diagnose states to rn-plan and rn-refine loops
status: done
completed_at: 2026-05-18T08:24:26Z
parent: BUG-1606
size: Small
decision_needed: false
confidence_score: 95
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1609: Add pre-terminal diagnose states to rn-plan and rn-refine loops

## Summary

Add a pre-terminal `diagnose` state to the `rn-plan` and `rn-refine` loop YAML files, and update `test_rn_plan.py` assertions that currently reference `"failed"` routing to instead reference `"diagnose"`.

## Parent Issue

Decomposed from BUG-1606: Add pre-terminal diagnose states to 12 affected loop YAML files

## Background

`scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` calls `return self._finish("terminal")` BEFORE executing any terminal state action. An `action:` field on a `failed` terminal never executes. The correct pattern is a separate non-terminal `diagnose` state that runs the diagnostic prompt and routes `next: failed`.

Structural model: `scripts/little_loops/loops/rn-refine.yaml:304` — `report` state (non-terminal action → `next: done`).
Content model: `scripts/little_loops/loops/hitl-compare.yaml:278` — but do NOT replicate its structure (its `failed` also has `terminal: true` which silences the action).

## Affected Loops

| Loop | File | Failed State Line | States routing to `failed` |
|------|------|-------------------|----------------------------|
| `rn-plan` | `scripts/little_loops/loops/rn-plan.yaml` | 288 | `score` (line 270) → `on_error: failed` |
| `rn-refine` | `scripts/little_loops/loops/rn-refine.yaml` | 327 | `init` (line 40), `score` (line 284), `verify_score` (line 302) → `on_error: failed` |

## Implementation Steps

### For each loop:

1. Read the loop YAML and identify:
   - All states that route to `failed` (listed above)
   - Output artifacts (both loops: `plan-rubric.md`, `plan.md` in `${captured.run_dir.output}/`)

2. Add a `diagnose` state immediately before the `failed` terminal:

**`rn-plan`** diagnostic prompt:
```yaml
diagnose:
  action_type: prompt
  action: |
    The rn-plan loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${captured.run_dir.output}/plan-rubric.md exists, read it and report the last rubric scores.
    - If ${captured.run_dir.output}/plan.md exists, note how far the plan was developed.
    - Identify the most likely failure cause (most commonly: LLM error in the score state).

    Write a one-paragraph diagnostic summary the operator can use to re-run or adjust inputs.
  next: failed

failed:
  terminal: true
```

**`rn-refine`** diagnostic prompt:
```yaml
diagnose:
  action_type: prompt
  action: |
    The rn-refine loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - If ${captured.run_dir.output}/plan-rubric.md exists, read it and report the last rubric scores.
    - If ${captured.run_dir.output}/plan.md exists, note whether any refinement occurred.
    - If failure was in the init state, report whether the source plan file was found.
    - Identify the most likely failure cause.

    Write a one-paragraph diagnostic summary the operator can use to re-run or locate the source plan.
  next: failed
```

3. Update all transitions that previously routed to `failed` to instead route to `diagnose`:
   - `rn-plan`: `score.on_error: failed` → `score.on_error: diagnose`
   - `rn-refine` (line 40, 284, 302): `init.on_error: failed` → `init.on_error: diagnose`, `score.on_error: failed` → `score.on_error: diagnose`, `verify_score.on_error: failed` → `verify_score.on_error: diagnose`

4. Update `scripts/tests/test_rn_plan.py`:
   - `TestRnPlanYaml.test_score_state_uses_all_very_high_sentinel` (line ~105): change `state.get("on_error") == "failed"` → `== "diagnose"`
   - `TestRnPlanYaml.test_required_states_exist` (line ~50): add `"diagnose"` to the required states set

5. Verify `scripts/tests/test_rn_refine.py::TestRoutingStructure` still passes (no changes needed — tests `score.on_yes`/`report`/`done` chain, not `failed` routing).

6. Run `python -m pytest scripts/tests/test_rn_plan.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py -v` and confirm all pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add `TestDiagnoseRouting` class to `scripts/tests/test_rn_refine.py` — use `_load_rn_refine()` pattern (already in the file) with `load_and_validate` attribute access; assert `init.on_error == "diagnose"`, `score.on_error == "diagnose"`, `verify_score.on_error == "diagnose"`, `diagnose` exists in `fsm.states`, `diagnose.action_type == "prompt"`, `diagnose.next == "failed"`
8. Update `docs/generalized-fsm-loop.md` section `### Failure Terminals Must Include a Diagnostic Action` (~line 1579) — replace the YAML code example and surrounding prose to show the two-state `diagnose → failed` split rather than the old single-state pattern

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/loops/rn-plan.yaml` — add `diagnose` state before `failed` (line 288); update `score.on_error` (line 270)
- `scripts/little_loops/loops/rn-refine.yaml` — add `diagnose` state before `failed` (line 327); update `init.on_error` (line 40), `score.on_error` (line 284), `verify_score.on_error` (line 302)
- `scripts/tests/test_rn_plan.py` — update `test_required_states_exist` (line 50) and `test_score_state_uses_all_very_high_sentinel` (line 105)

**Structural Model to Follow**
- `scripts/little_loops/loops/rn-refine.yaml:297` — `report` state: `action_type: prompt` + `next: done`, followed by bare `terminal: true` anchor; replicate this exact split for `diagnose` → `failed`

**Do NOT follow**
- `scripts/little_loops/loops/hitl-compare.yaml:278` — `failed` state there has both `terminal: true` and an action body; the terminal short-circuit silences the action (same bug being fixed here)

**Tests**
- `scripts/tests/test_rn_plan.py` — `test_required_states_exist` (line 50): add `"diagnose"` to required set; `test_score_state_uses_all_very_high_sentinel` (line 105): change `== "failed"` → `== "diagnose"`
- `scripts/tests/test_rn_refine.py` — `TestRoutingStructure` (line 191): no changes needed; asserts `score`→`verify_score`→`report`→`done` chain only, not `failed` routing
- `scripts/tests/test_fsm_executor.py` — no changes needed (uses synthetic FSMs)
- `scripts/tests/test_fsm_schema.py` — no changes needed (`test_terminal_only_state_valid` still applies since `failed` stays bare)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_refine.py` — new tests needed (no `on_error` routing tests exist in this file); add a `TestDiagnoseRouting` class using `_load_rn_refine()` + attribute access (`load_and_validate`) to assert: `init.on_error == "diagnose"`, `score.on_error == "diagnose"`, `verify_score.on_error == "diagnose"`, `diagnose` state exists, `diagnose.action_type == "prompt"`, `diagnose.next == "failed"` [Agent 3 finding]
- `scripts/tests/test_rn_plan.py` — optionally add `diagnose.action_type == "prompt"` and `diagnose.next == "failed"` structure assertions beyond required-states set [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — section `### Failure Terminals Must Include a Diagnostic Action` (~line 1579) contains a YAML example showing the old single-state pattern (`failed` with both `action_type: prompt` and `terminal: true`) that contradicts the two-state split being adopted here; update code example and prose to show the `diagnose → failed` split [Agent 2 finding]

## Acceptance Criteria

- `rn-plan.yaml` and `rn-refine.yaml` each have a `diagnose` state with `next: failed` before the `failed` terminal
- Each `diagnose` state names loop-specific artifacts (`plan-rubric.md`, `plan.md`) in the action prompt
- `failed` terminal retains only `terminal: true`
- `test_rn_plan.py` assertions updated: `on_error` → `"diagnose"`, `"diagnose"` in required states
- All listed tests pass

---

**Priority**: P3 | **Created**: 2026-05-18

## Resolution

Added `diagnose` pre-terminal state to `rn-plan` and `rn-refine` loops. All `on_error` transitions now route to `diagnose` instead of directly to `failed`. Updated `test_rn_plan.py` assertions and added `TestDiagnoseRouting` to `test_rn_refine.py`. Updated `docs/generalized-fsm-loop.md` to document the two-state split pattern.

## Session Log
- `/ll:ready-issue` - 2026-05-18T08:20:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/796e3931-2c23-4720-bcb5-65cf0fd448c6.jsonl`
- `/ll:wire-issue` - 2026-05-18T08:15:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4cc4dffa-9f8f-4f62-88c5-761913898880.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e6746de-9af3-417e-811f-66de387d51c7.jsonl`
- `/ll:refine-issue` - 2026-05-18T08:10:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e6b2734-8873-49d8-8fa8-492ffcacc300.jsonl`
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3772e425-1416-4cc8-baac-8e0f351122fa.jsonl`

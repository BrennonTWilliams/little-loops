---
id: BUG-1603
type: BUG
priority: P3
title: "failure terminal states in built-in loops have no diagnostic action \u2014\
  \ silent failure in ll-loop history"
discovered_date: 2026-05-17
discovered_by: loop-audit
status: done
confidence_score: 90
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
size: Very Large
---

# BUG-1603: failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history

## Summary

`hitl-compare.yaml`'s `failed` terminal state (and at least one other built-in harness loop) declares `terminal: true` with no `action:`. When the loop hits this state, `ll-loop history` shows the state name (`failed`) but no diagnostic context: no last evaluation scores, no indication of which state failed, no actionable information. Every other terminal state pattern in the library includes an action summarizing results.

## Current Behavior

Failure terminal states (e.g., `failed` in `hitl-compare.yaml` and `html-anything.yaml`) declare `terminal: true` with no `action:`. When the loop reaches this state, `ll-loop history` shows only the state name (`failed`) with no diagnostic context — no evaluation scores, no indication of which prior state caused the failure, no actionable information for the operator.

## Expected Behavior

Every failure terminal state should include an `action_type: prompt` diagnostic action that reads available artifacts (`critique.md`, `review.md`, etc.) and outputs a brief operator-facing summary. `ll-loop history` should show meaningful diagnostic context after any failure.

## Steps to Reproduce

1. Run `ll-loop run html-anything` with inputs that cause the loop to fail (e.g., malformed HTML task)
2. Observe the loop reaches the `failed` terminal state
3. Run `ll-loop history html-anything` — observe `final_state: failed` with no diagnostic output
4. Compare with `hitl-compare` `failed` state (which now has a diagnostic action) to see the difference

## Root Cause

- **File**: `scripts/little_loops/loops/html-anything.yaml`
- **Anchor**: `failed` terminal state definition (lines 223–226)
- **Cause**: Terminal state declares `terminal: true` without an `action:` field. The authoring convention requiring diagnostic actions on failure terminals was not yet documented or enforced when these loops were authored.

## Affected Loops

| Loop | File | State |
|------|------|-------|
| `hitl-compare` | `scripts/little_loops/loops/hitl-compare.yaml` | `failed` |
| `html-anything` | `scripts/little_loops/loops/html-anything.yaml` | `failed` |

Other harness loops likely have the same pattern — a sweep of `scripts/little_loops/loops/` for `terminal: true` without a preceding `action:` would identify all instances.

### Codebase Research Findings

_Added by `/ll:refine-issue` — sweep of `scripts/little_loops/loops/` completed:_

| Loop | File | State | Line |
|------|------|-------|------|
| `html-anything` | `scripts/little_loops/loops/html-anything.yaml` | `failed` | 221 |
| `svg-textgrad` | `scripts/little_loops/loops/svg-textgrad.yaml` | `failed` | 295 |
| `general-task` | `scripts/little_loops/loops/general-task.yaml` | `failed` | 97 |
| `rn-plan` | `scripts/little_loops/loops/rn-plan.yaml` | `failed` | 288 |
| `rn-refine` | `scripts/little_loops/loops/rn-refine.yaml` | `failed` | 302 |
| `recursive-refine` | `scripts/little_loops/loops/recursive-refine.yaml` | `failed` | 818 |
| `refine-to-ready-issue` | `scripts/little_loops/loops/refine-to-ready-issue.yaml` | `failed` | 349 |
| `rl-coding-agent` | `scripts/little_loops/loops/rl-coding-agent.yaml` | `failed` | 134 |
| `rl-policy` | `scripts/little_loops/loops/rl-policy.yaml` | `failed` | 55 |
| `agent-eval-improve` | `scripts/little_loops/loops/agent-eval-improve.yaml` | `failed` | 105 |
| `prompt-across-issues` | `scripts/little_loops/loops/prompt-across-issues.yaml` | `error` | 99 |

Note: `prompt-across-issues.yaml` uses state name `error` instead of `failed` — same pattern, different name.

## Proposed Solution

Add a `action_type: prompt` action to each failure terminal that:
1. Reads any available diagnostic artifacts (`critique.md`, `review.md`, etc.)
2. Identifies the most likely failure state
3. Outputs a brief operator-facing summary

Example for `hitl-compare`:

```yaml
  failed:
    action_type: prompt
    action: |
      The hitl-compare loop has terminated with an unrecoverable error.

      Diagnose what failed:
      - If ${captured.run_dir.output}/critique.md exists, read it and summarize the last evaluation scores.
      - If ${captured.run_dir.output}/review.md exists, report how many items were identified for review.
      - Identify the most likely failure cause (most commonly: LLM error in the score state).

      Write a one-paragraph diagnostic summary so the operator can diagnose and re-run.
    terminal: true
```

## Convention Change

Add to `docs/generalized-fsm-loop.md` under a new "Authoring Conventions" section:

> A failure terminal state must always include an `action_type: prompt` diagnostic action. A terminal with no action produces a blank entry in `ll-loop history`; a diagnostic action costs nothing extra (runs once at termination) and makes failure immediately visible without inspecting raw event files.

The `create-loop` wizard should also warn when generating a `failed` terminal with no action.

## Implementation Steps

1. Add `action_type: prompt` diagnostic action to `html-anything.yaml` `failed` terminal state (model after `hitl-compare.yaml` lines 278–292)
2. Sweep `scripts/little_loops/loops/` for all `terminal: true` states lacking `action:` and apply the same fix
3. Commit staged changes to `docs/generalized-fsm-loop.md` authoring-convention section
4. Update `skills/create-loop/SKILL.md` wizard to warn when generating a `failed` terminal with no action
5. Verify: run failing loop scenario; confirm `ll-loop history` shows diagnostic output

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

0. **(CRITICAL — confirmed)** `scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` at lines 307–325 confirms the `if state_config.terminal:` block calls `return self._finish("terminal")` at line 325 **before** executing the state's action. **DECIDED**: Adding `action:` directly to `failed` terminal states has no effect. Use the pre-terminal `diagnose` state pattern (as in `rn-refine.yaml:282–283`) for all 11 loops. The `hitl-compare` inline-action model shown in the Proposed Solution example is not the correct model — it does not execute.
1a. Add `scripts/little_loops/loops/svg-image-generator.yaml` to the affected-loops sweep — bare `failed` terminal at lines 169–173 (same pattern, missing from original table).
4b. After adding `validate_failure_terminal_action()` to `validation.py`, choose `ValidationSeverity.WARNING` (not ERROR) so `test_fsm_schema.py:test_terminal_only_state_valid()` and inline executor test fixtures pass without modification; document the severity choice.
5b. Update per-loop tests at `test_builtin_loops.py:1967, 2354, 2717, 2914, 3071` — add companion assertion `assert state.get("action") is not None` after YAML fix lands.
5c. Add `TestFailureTerminalActionValidation` class to `test_fsm_validation.py` following the `TestDescriptionFieldValidation` pattern.
5d. Add `test_all_failure_terminals_have_diagnostic_action` to `TestBuiltinLoopFiles` in `test_builtin_loops.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 reference**: `scripts/little_loops/loops/hitl-compare.yaml:278–292` is the canonical model. The state has `action_type: prompt`, a multi-bullet `action:` block naming specific artifact paths (`${captured.run_dir.output}/critique.md`, etc.), then `terminal: true`.
- **Step 2 (sweep complete)**: 11 loops confirmed affected — see Affected Loops Codebase Research Findings table above for file paths and line numbers.
- **Step 3 (docs status)**: `docs/generalized-fsm-loop.md` already has `## Authoring Conventions` at line 1577 with `### Failure Terminals Must Include a Diagnostic Action` at line 1579, including a canonical YAML template. The step is to ensure any staged changes are committed — the content is likely already present.
- **Step 4 (create-loop scope)**: Warning at `skills/create-loop/SKILL.md:143` already exists. The real gap is `skills/create-loop/loop-types.md` — all wizard-generated templates emit bare `done: terminal: true` and no `failed` state. Update the templates to emit a `failed` terminal with a loop-name-specific diagnostic action.
- **Step 6 (optional — add validation)**: `scripts/little_loops/fsm/validation.py` has no automated check for missing actions on failure terminals (`validate_failure_terminal_action()` does not exist). Adding one to `validation.py` would prevent regression and eliminate reliance on prose warnings alone. Cross-reference `scripts/tests/test_fsm_validation.py` for the test pattern.
- **Runner behavior — verify before bulk apply**: `scripts/little_loops/loops/rn-refine.yaml:279` comment states the FSM runner "fires loop_complete immediately on routing to a terminal without entering it," and uses a pre-terminal `report` state as a workaround. Verify that `hitl-compare.yaml`'s `failed` action actually executes (not just present in YAML) before applying the pattern to all 11 loops. If the runner skips terminal actions, the correct fix is the `report`-before-`done` workaround from `rn-refine.yaml:279`.

## Impact

- **Priority**: P3 — failure states are reachable in normal use; silent failure makes debugging harder
- **Effort**: Low — add a prompt action to each affected `failed` state
- **Risk**: Minimal — terminal states run once; a prompt action that reads missing files is graceful
- **Breaking Change**: No

## Labels

`bug`, `loops`, `fsm`, `html-anything`, `diagnostics`

---

**Priority**: P3 | **Created**: 2026-05-17

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/html-anything.yaml:221` — `failed` state: add `action_type: prompt` + `action:` block
- `scripts/little_loops/loops/svg-textgrad.yaml:295` — `failed` state: same fix
- `scripts/little_loops/loops/general-task.yaml:97` — `failed` state: same fix
- `scripts/little_loops/loops/rn-plan.yaml:288` — `failed` state: same fix
- `scripts/little_loops/loops/rn-refine.yaml:302` — `failed` state: same fix
- `scripts/little_loops/loops/recursive-refine.yaml:818` — `failed` state: same fix
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:349` — `failed` state: same fix
- `scripts/little_loops/loops/rl-coding-agent.yaml:134` — `failed` state: same fix
- `scripts/little_loops/loops/rl-policy.yaml:55` — `failed` state: same fix
- `scripts/little_loops/loops/agent-eval-improve.yaml:105` — `failed` state: same fix
- `scripts/little_loops/loops/prompt-across-issues.yaml:99` — `error` state: same fix
- `skills/create-loop/loop-types.md` — add `failed` terminal with diagnostic action to wizard-generated templates
- `docs/generalized-fsm-loop.md:1577` — verify staged authoring-convention changes are committed

### Reference Implementation
- `scripts/little_loops/loops/hitl-compare.yaml:278–292` — canonical `failed` state with `action_type: prompt` diagnostic action; model all fixes after this

### Tests
- `scripts/tests/test_builtin_loops.py` — add `test_all_failure_terminals_have_diagnostic_action` to `TestBuiltinLoopFiles`; iterate built-in loops, find `terminal: true` states with failure-suggesting names (`failed`, `error`, `aborted`), assert `action` is not `None`/empty
- `scripts/tests/test_fsm_validation.py` — if automated enforcement is added to `validation.py`, add `TestFailureTerminalActionValidation` class following the `TestDescriptionFieldValidation` pattern (tests that bare failure terminal emits WARNING, adding `action` suppresses it)
- `scripts/tests/test_fsm_schema.py` — **`test_terminal_only_state_valid()` at line ~951–963** explicitly asserts `StateConfig(terminal=True)` with no action produces zero errors; if the new check is `ValidationSeverity.ERROR`, this test must be updated; if `WARNING` (recommended), it passes unchanged [Agent 2 + 3 finding]
- `scripts/tests/test_fsm_executor.py` — lines 3834 and 3858 contain inline `failed: terminal: true` YAML fixtures; if `validate_fsm()` is called on them, they emit the new warning (may need `action:` added to those fixtures or the warning filtered) [Agent 3 finding]
- Per-loop tests at `test_builtin_loops.py:1967, 2354, 2717, 2914, 3071` already assert `terminal: true` on `failed` states — after the YAML fix lands, add a companion assertion `assert state.get("action") is not None` to each [Agent 3 finding]

### Optional Enforcement
- `scripts/little_loops/fsm/validation.py` — no existing check for missing terminal actions; add `validate_failure_terminal_action()` to `_validate_state_action()` call chain

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — line 812 references `ll-loop history agent-eval-improve` to diagnose a `failed` state; remains accurate but will show richer diagnostic output after fix; no change required unless clarification note is desired [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — **CRITICAL**: `FSMExecutor.run()` at lines ~307–325 checks `if state_config.terminal:` and calls `_finish("terminal")` BEFORE executing any action; if unmodified, an `action:` field added to a `failed` terminal state will never execute — verify this before bulk-applying fixes; if the short-circuit fires first, the correct pattern is a pre-terminal `diagnose`/`report` state (the workaround already documented at `rn-refine.yaml:282–283`)
- `scripts/little_loops/fsm/validation.py` — `validate_fsm()` per-state loop at the `errors.extend(_validate_state_action(...))` call site is where the new `validate_failure_terminal_action()` is wired in [Agent 2 finding]
- `scripts/little_loops/cli/loop/testing.py` — `ll-loop test --state failed` currently prints `"no action to test"` (line 50); after fix it finds and runs the diagnostic action; behavior is correct but needs awareness [Agent 2 finding]

### Additional Affected File (not in original sweep)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/svg-image-generator.yaml` — has a bare `failed` terminal at lines 169–173 (`HARNESS` comment present, `terminal: true`, no `action:`); same pattern as the 11 loops in the table above but was not included in the sweep — add to the affected-loops table and apply the same fix

---

## Verification Notes

**Verdict**: OUTDATED — Re-verified 2026-05-17

- `scripts/little_loops/loops/hitl-compare.yaml` — `failed` terminal state now has a `action_type: prompt` diagnostic action ✓ (fix applied at lines 278–292)
- `scripts/little_loops/loops/html-anything.yaml:223–226` — `failed` terminal state still has only `terminal: true` with no `action:` ✗ (bug persists)
- `docs/generalized-fsm-loop.md` — has staged changes; convention documentation may be in progress (not yet committed)
- Remaining scope: add diagnostic action to `html-anything.yaml` `failed` state + commit `generalized-fsm-loop.md` authoring-convention section


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-18 (re-check after `/ll:decide-issue`)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Proposed Solution and Implementation Steps still reference `hitl-compare.yaml` as the canonical model, but executor.py:325 confirms terminal actions never execute. The correct approach (pre-terminal `diagnose` state) is only in Wiring step 0 — read Wiring step 0 first as the authoritative implementation guide.

### Outcome Risk Factors
- Body text inconsistency: Proposed Solution and Implementation Steps describe the inline-action-on-terminal approach; the decided pre-terminal `diagnose` state pattern is documented only in Wiring step 0 — treat Wiring step 0 as authoritative
- 12 loop-specific diagnostic prompts required: each affected YAML needs a customized `diagnose` state naming its own output artifacts (critique.md, review.md, plan-rubric.md, etc.) — not a mechanical uniform substitution; budget ~10–15 min per loop for content authoring

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-18
- **Reason**: Issue too large for single session (score: 9/11 — Very Large)

### Decomposed Into
- BUG-1606: Add pre-terminal diagnose states to 12 affected loop YAML files
- BUG-1607: Update docs, create-loop wizard, and validation for failure terminal convention
- BUG-1608: Add test coverage for failure terminal diagnostic action requirement

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbd13cdc-51a4-41ee-85fe-30c33cc936aa.jsonl`
- `/ll:confidence-check` - 2026-05-18T02:41:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/868ad7ff-5134-4abc-be3d-7b1974ab0307.jsonl`
- `/ll:decide-issue` - 2026-05-18T07:39:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e8dacdf-1a43-4fa8-9fc4-1e0c26fe183e.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f3e8c8a-56e8-42d1-962f-1b9123e15590.jsonl`
- `/ll:wire-issue` - 2026-05-18T07:34:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdd4c28f-092b-44f6-b6e5-d3d60d73042a.jsonl`
- `/ll:refine-issue` - 2026-05-18T07:28:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04710424-5961-447e-bcb0-7b1019912227.jsonl`
- `/ll:format-issue` - 2026-05-18T05:16:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb7f2fc9-52f4-4d22-8182-c197fa8741c5.jsonl`
- `/ll:verify-issues` - 2026-05-18T04:53:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2807bd8b-4e79-4b76-994d-e6f6cae14245.jsonl`

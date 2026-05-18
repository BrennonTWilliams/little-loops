---
id: BUG-1607
type: BUG
priority: P3
title: Update docs, create-loop wizard, and validation for failure terminal convention
status: open
parent: BUG-1603
size: Very Large
decision_needed: false
confidence_score: 95
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-1607: Update docs, create-loop wizard, and validation for failure terminal convention

## Summary

Solidify the failure-terminal convention at the tooling level so new loops authored via the create-loop wizard emit the correct pre-terminal `diagnose` state pattern, the docs convention section is committed, and an optional automated check in `validation.py` prevents regression.

## Parent Issue

Decomposed from BUG-1603: failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history

## Implementation Steps

### Step 1 — Verify and commit docs/generalized-fsm-loop.md

`docs/generalized-fsm-loop.md` already has `## Authoring Conventions` at line 1577 with `### Failure Terminals Must Include a Diagnostic Action` at line 1579 (content added by a prior pass). Verify the authoring-convention section is complete and accurate, then ensure it is committed.

The convention text should describe the **pre-terminal `diagnose` state pattern** (not inline action on terminal), since that is what actually executes given the FSM executor behavior (`executor.py:307–325` fires terminal before any action).

### Step 2 — Update skills/create-loop/loop-types.md wizard templates

All wizard-generated templates in `skills/create-loop/loop-types.md` currently emit bare `failed: terminal: true` with no preceding diagnostic state. Update each template to emit:

```yaml
diagnose_failure:
  action_type: prompt
  action: |
    The loop has terminated with an unrecoverable failure.

    Diagnose what happened:
    - Check for any output artifacts in ${captured.run_dir.output}/ and summarize.
    - Identify the most likely failure cause.

    Write a one-paragraph diagnostic summary the operator can use to re-run.
  next: failed

failed:
  terminal: true
```

Also verify `skills/create-loop/SKILL.md:143` warning is accurate.

### Step 3 — Add validate_failure_terminal_action() to validation.py (optional enforcement)

In `scripts/little_loops/fsm/validation.py`, add a `validate_failure_terminal_action()` function wired into the `_validate_state_action()` call chain:

- Detect terminal states whose name suggests failure (`failed`, `error`, `aborted`) that have no preceding state routing to a diagnostic action (or no `action:` on the terminal itself as a looser check)
- Use `ValidationSeverity.WARNING` (not ERROR) so `test_fsm_schema.py:test_terminal_only_state_valid()` and inline executor test fixtures pass without modification
- Document the severity choice in a comment

Wire it into `validate_fsm()` at the `errors.extend(_validate_state_action(...))` call site.

### Step 4 — Update docs/reference/API.md (Wiring Phase, added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis:_

In `docs/reference/API.md` under section `#### validate_fsm` (within `### little_loops.fsm.validation`), add a new bullet to the "Checks performed" list:
- Warns (WARNING) when a failure-named terminal state (e.g. `failed`, `error`, `aborted`) has no predecessor state routing through a diagnostic action before the terminal.

## Integration Map

### Files to Modify
- `docs/generalized-fsm-loop.md:1577-1606` — authoring-convention section already present; verify accuracy, then ensure it is committed
- `skills/create-loop/loop-types.md:1060-1064` — the sub-loop composition `escalate` state has both `action_type: shell` and `terminal: true` (shell action silently skipped by executor); split into two-state `diagnose_failure → failed` pattern
- `skills/create-loop/SKILL.md:143` — warning text describes "terminal: true with no action: field" but misses the case where an action IS on the terminal (like `escalate`); update to describe the two-state pre-terminal pattern
- `scripts/little_loops/fsm/validation.py` — add `validate_failure_terminal_action(fsm: FSMLoop) -> list[ValidationError]` (needs full FSM, not per-state, to check predecessor routing); wire into `validate_fsm()` after the per-state loop alongside the reachability check, using `errors.extend(...)`
- `docs/reference/API.md` — add bullet to `validate_fsm` "Checks performed" list for the new failure-terminal diagnostic predecessor check [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Must Not Break)
- `scripts/tests/test_fsm_schema.py:951` — `test_terminal_only_state_valid()` filters by `ValidationSeverity.ERROR`, so a WARNING-severity result passes safely; no change needed
- `scripts/tests/test_fsm_schema.py:1015` — `test_multiple_terminal_states()` uses the same ERROR-filter pattern; safe; fixture uses `failure_end` (not `failed`/`error`/`aborted`) so new check may or may not trigger depending on name-match logic
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` surfaces warnings via `for w in warnings: print(f"  ⚠ {w}")`; after BUG-1607, `ll-loop validate` on non-compliant loops will print the new WARNING; no code change needed, intentional user-visible behavior change [Wiring pass added by `/ll:wire-issue`]

### Similar Patterns to Follow
- `scripts/little_loops/loops/general-task.yaml:97-112` — canonical `diagnose → failed` two-state pattern to model wizard template update after
- `scripts/little_loops/fsm/validation.py:762-769` — unreachable-state WARNING pattern to follow for `validate_failure_terminal_action()`
- `scripts/tests/test_fsm_schema.py:951` — severity-filter idiom `[e for e in errors if e.severity == ValidationSeverity.ERROR]` for test assertions

### Tests
- `scripts/tests/test_fsm_schema.py:951` — `test_terminal_only_state_valid()` must pass unchanged after Step 3
- `scripts/tests/test_fsm_validation.py` — model `TestFailureTerminalActionValidation` class after `TestDescriptionFieldValidation` at line 81 (BUG-1608 scope)
- `scripts/tests/test_builtin_loops.py` — add `test_all_failure_terminals_have_diagnostic_action()` (BUG-1608 scope)
- `scripts/tests/test_create_loop.py` — `TestLoopFileValidation` fixtures use inline YAML; after Step 2 adds `diagnose_failure → failed` to wizard templates, check whether existing fixtures still represent valid loop shapes; update any bare `failed: terminal: true` fixtures to match new template output [Wiring pass added by `/ll:wire-issue`]

### Documentation
- `docs/generalized-fsm-loop.md:1577-1606` — verify authoring-convention section then commit (Step 1)
- `docs/reference/API.md` — `validate_fsm` "Checks performed" list needs new bullet for failure-terminal diagnostic predecessor check (Step 4) [Wiring pass added by `/ll:wire-issue`]
- `skills/review-loop/reference.md` — FA-2 fix template at `### FA-2: Missing Failure Terminal` shows bare `failed: terminal: true`; Dimension 3 Resilience scoring at `### Dimension 3: Resilience` scores 5 for "explicit failure terminal" without requiring a diagnostic predecessor — both misaligned with the new validator WARNING; consider updating here or as follow-up [Wiring pass added by `/ll:wire-issue`]
- `skills/review-loop/SKILL.md:193` — QC-9 note at `### QC-9: Missing Failure Terminal` accepts "a non-terminal error-handling state that eventually routes to a failure terminal" without requiring the two-state diagnose pattern — misaligned with new validation convention [Wiring pass added by `/ll:wire-issue`]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 (docs/generalized-fsm-loop.md):**
- The authoring-convention section at lines 1577-1606 is already complete and accurate. It explains both the two-state split requirement and the executor's behavior (`_finish("terminal")` fires at `executor.py:308` before any action). No content changes needed — just verify it is committed.

**Step 2 (loop-types.md wizard templates):**
- Research shows most templates (`Fix Until Clean`, `Maintain Constraints`, `Drive a Metric`, `Run a Sequence`, `Harness Variant A/B`, all RL variants) only have `done: terminal: true` (success terminal) and no separate failure terminal. No change needed for those.
- The only failure terminal across all templates is the sub-loop composition example (`escalate` at line 1060-1064): it has `action_type: shell` AND `terminal: true` on the same state — the shell action is silently skipped by `executor.py:308`. This is the one template requiring the two-state fix.
- `SKILL.md:143` warning currently triggers only for "no `action:` field" on a failure terminal, missing the case where an action IS present (as in `escalate`). Update to describe the two-state pre-terminal diagnose pattern as the required convention.

**Step 3 (validation.py):**
- `validate_failure_terminal_action()` needs the full `fsm: FSMLoop` object (not just a single state) to check whether failure-named terminals have any predecessor state routing to a diagnostic intermediary. Wire it after the per-state loop, alongside the reachability analysis (line ~760), not inside the per-state loop.
- Signature pattern to follow: `_validate_parameters(fsm: FSMLoop) -> list[ValidationError]` (line 208).
- WARNING severity pattern to model after: `scripts/little_loops/fsm/validation.py:762-769` (unreachable-state check).
- `test_fsm_schema.py:951` (`test_terminal_only_state_valid`) already filters `[e for e in errors if e.severity == ValidationSeverity.ERROR]`, so a WARNING-severity result from the new function will not break it — no test modification needed for that test.

## Acceptance Criteria

- `docs/generalized-fsm-loop.md` authoring-convention section accurately describes the pre-terminal `diagnose` state pattern and is committed
- `skills/create-loop/loop-types.md` wizard templates emit a pre-terminal `diagnose_failure` state before any `failed` terminal
- (Optional) `validation.py` warns when a failure-named terminal state has no preceding diagnostic state; severity is WARNING not ERROR

## Labels

`bug`, `fsm`, `diagnostics`, `tooling`, `docs`

---

**Priority**: P3 | **Created**: 2026-05-18

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-18_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Test coverage gap: `validate_failure_terminal_action()` will ship without dedicated unit tests in this issue's scope — BUG-1608 defers those tests; if the function has a subtle logic error in its predecessor-routing check, it won't be caught until BUG-1608 is implemented. Consider adding a minimal happy/sad path test inline.
- Name-match scope: `test_multiple_terminal_states` (test_fsm_schema.py:1015) uses fixture state `failure_end`, not `failed`/`error`/`aborted` — the issue explicitly notes this "may or may not trigger depending on name-match logic." Define the exact set of failure-named terminal state names before writing the function body.

## Session Log
- `/ll:wire-issue` - 2026-05-18T09:30:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5571e64c-0146-4ce6-b685-6d24fc815c29.jsonl`
- `/ll:refine-issue` - 2026-05-18T09:23:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa0f6b63-a498-4ea8-b762-333bb5e7342c.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee00bd56-eb77-430a-9e44-072d6272930a.jsonl`
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbd13cdc-51a4-41ee-85fe-30c33cc936aa.jsonl`

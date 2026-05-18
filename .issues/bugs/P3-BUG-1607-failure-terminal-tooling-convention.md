---
id: BUG-1607
type: BUG
priority: P3
title: "Update docs, create-loop wizard, and validation for failure terminal convention"
status: open
parent: BUG-1603
size: Medium
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

## Acceptance Criteria

- `docs/generalized-fsm-loop.md` authoring-convention section accurately describes the pre-terminal `diagnose` state pattern and is committed
- `skills/create-loop/loop-types.md` wizard templates emit a pre-terminal `diagnose_failure` state before any `failed` terminal
- (Optional) `validation.py` warns when a failure-named terminal state has no preceding diagnostic state; severity is WARNING not ERROR

## Labels

`bug`, `fsm`, `diagnostics`, `tooling`, `docs`

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbd13cdc-51a4-41ee-85fe-30c33cc936aa.jsonl`

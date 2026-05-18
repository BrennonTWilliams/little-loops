---
id: BUG-1603
type: BUG
priority: P3
title: "failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history"
discovered_date: 2026-05-17
discovered_by: loop-audit
status: open
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

## Impact

- **Priority**: P3 — failure states are reachable in normal use; silent failure makes debugging harder
- **Effort**: Low — add a prompt action to each affected `failed` state
- **Risk**: Minimal — terminal states run once; a prompt action that reads missing files is graceful
- **Breaking Change**: No

## Labels

`bug`, `loops`, `fsm`, `html-anything`, `diagnostics`

---

**Priority**: P3 | **Created**: 2026-05-17

## Verification Notes

**Verdict**: OUTDATED — Re-verified 2026-05-17

- `scripts/little_loops/loops/hitl-compare.yaml` — `failed` terminal state now has a `action_type: prompt` diagnostic action ✓ (fix applied at lines 278–292)
- `scripts/little_loops/loops/html-anything.yaml:223–226` — `failed` terminal state still has only `terminal: true` with no `action:` ✗ (bug persists)
- `docs/generalized-fsm-loop.md` — has staged changes; convention documentation may be in progress (not yet committed)
- Remaining scope: add diagnostic action to `html-anything.yaml` `failed` state + commit `generalized-fsm-loop.md` authoring-convention section


## Session Log
- `/ll:format-issue` - 2026-05-18T05:16:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb7f2fc9-52f4-4d22-8182-c197fa8741c5.jsonl`
- `/ll:verify-issues` - 2026-05-18T04:53:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2807bd8b-4e79-4b76-994d-e6f6cae14245.jsonl`

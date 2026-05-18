---
discovered_date: 2026-05-17
discovered_by: loop-audit
status: open
---

# BUG-1603: failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history

## Summary

`hitl-compare.yaml`'s `failed` terminal state (and at least one other built-in harness loop) declares `terminal: true` with no `action:`. When the loop hits this state, `ll-loop history` shows the state name (`failed`) but no diagnostic context: no last evaluation scores, no indication of which state failed, no actionable information. Every other terminal state pattern in the library includes an action summarizing results.

## Affected Loops

| Loop | File | State |
|------|------|-------|
| `hitl-compare` | `scripts/little_loops/loops/hitl-compare.yaml` | `failed` |
| `html-anything` | `scripts/little_loops/loops/html-anything.yaml` | `failed` |

Other harness loops likely have the same pattern — a sweep of `scripts/little_loops/loops/` for `terminal: true` without a preceding `action:` would identify all instances.

## Fix

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

## Impact

- **Priority**: P3 — failure states are reachable in normal use; silent failure makes debugging harder
- **Effort**: Low — add a prompt action to each affected `failed` state
- **Risk**: Minimal — terminal states run once; a prompt action that reads missing files is graceful

---

**Priority**: P3 | **Created**: 2026-05-17

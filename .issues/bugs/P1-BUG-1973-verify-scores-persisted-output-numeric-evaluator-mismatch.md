---
id: BUG-1973
title: "rn-remediate: verify_scores_persisted uses output_numeric evaluator but action outputs a string"
type: BUG
priority: P1
status: open
captured_at: '2026-06-06T03:29:25Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
relates_to:
- BUG-1972
labels:
- rn-implement
- rn-remediate
- evaluator
- loop-defect
---

# BUG-1973: rn-remediate verify_scores_persisted output_numeric evaluator mismatch

## Summary

The `verify_scores_persisted` state in the rn-remediate sub-loop (inlined in rn-implement) uses
`evaluate.type: output_numeric` but the shell action outputs a human-readable success string
(`"Scores persisted for ENH-1924: confidence=91, outcome=87"`). The evaluator cannot parse this
as a number, emits `verdict: error`, and routes via `on_error: failed` — terminating the sub-loop
before it can reach `check_readiness → implement`.

This is the **single-point failure** that prevents any issue from being implemented by rn-implement.
Every confidence check succeeds (exit 0 from `assess`), but every run crashes at the very next state.

## Steps to Reproduce

1. Run `rn-implement` against any ready issue (e.g. `ll-loop run rn-implement` processing ENH-1924).
2. Let the `assess` confidence check complete — it passes with exit 0.
3. Observe: the inlined rn-remediate sub-loop terminates `failed` at the `verify_scores_persisted`
   state because the `output_numeric` evaluator cannot parse the action's success string.

## Current Behavior

At `verify_scores_persisted`, the shell action outputs a human-readable success string
(`"Scores persisted for ENH-1924: confidence=91, outcome=87"`), but the state's `output_numeric`
evaluator expects a plain number. The evaluator fails to parse it, emits `verdict: error`, and
routes via `on_error: failed`, terminating the rn-remediate sub-loop before it can reach
`check_readiness → implement`. As a result, no issue is ever implemented by rn-implement.

## Expected Behavior

`verify_scores_persisted` should evaluate the action's **exit code** (0 = scores persisted,
1 = file-not-found or missing fields), since the action already encodes success/failure that way.
A successful persistence (exit 0) should route to `check_readiness → implement`; a failure (exit 1)
should route to `failed`.

## Root Cause

The `output_numeric` evaluator with `fragment_bindings.counter_key / max_retries` is a counter-pattern
meant to track retry counts emitted as plain numbers. The `verify_scores_persisted` action instead
outputs a status message. These are mismatched: the action's exit code already encodes success/failure
(exit 1 on file-not-found or missing fields, exit 0 on success), so the correct evaluator is `exit_code`.

## Evidence

Run `2026-06-06T032504` (rn-implement processing ENH-1924):

```
event: evaluate
type: output_numeric
verdict: error
error: "Cannot parse as number: Scores persisted for ENH-1924: confidence=91, outcome=87\n"
```

ENH-1924 had readiness 91/100 (> threshold 85) and outcome 87/100 (> threshold 75) — fully ready to
implement — but was skipped because rn-remediate terminated `failed` at this state.

## Proposed Solution

In the rn-remediate sub-loop definition (inline `_subloop` in `loops/rn-implement.yaml`),
change `verify_scores_persisted.evaluate`:

```yaml
  verify_scores_persisted:
    evaluate:
-     type: output_numeric
-     operator: lt
-     target: "${param.max_retries}"
+     type: exit_code
    fragment_bindings: ~    # remove — no longer needed
    on_yes: check_readiness
    on_no: failed
    on_error: failed
```

The action's exit-code contract is already correct:
- exit 1 if issue file not found for ID
- exit 1 if `confidence_score` or `outcome_confidence` missing from frontmatter
- exit 0 (implicit) on success

## Impact

- **Severity**: CRITICAL — blocks rn-implement from implementing any issue
- **Blast radius**: All rn-implement runs, regardless of input issue

---

**Open** | Created: 2026-06-06 | Priority: P1

## Session Log
- `/ll:format-issue` - 2026-06-06T03:41:01 - `b23a2893-543d-4167-8343-e752c0206d37.jsonl`

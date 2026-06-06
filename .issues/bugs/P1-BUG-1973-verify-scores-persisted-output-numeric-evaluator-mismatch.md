---
id: BUG-1973
title: 'rn-remediate: verify_scores_persisted uses output_numeric evaluator but action
  outputs a string'
type: BUG
priority: P1
status: done
captured_at: '2026-06-06T03:29:25Z'
completed_at: '2026-06-06T04:09:00Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
relates_to:
- BUG-1972
labels:
- rn-implement
- rn-remediate
- evaluator
- loop-defect
confidence_score: 96
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 23
size: Medium
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

In `scripts/little_loops/loops/rn-remediate.yaml` (a standalone loop invoked by rn-implement,
not an inline subloop), change `verify_scores_persisted` to remove the `fragment: retry_counter`
dependency (which injects the `output_numeric` evaluator) and replace with an explicit `exit_code`
evaluator:

```yaml
  verify_scores_persisted:
    action_type: shell
    action: |
      ID="${context.issue_id}"
      ISSUE_FILE=$(find .issues -name "*-$ID-*" ! -path "*/completed/*" 2>/dev/null | head -1)
      if [ -z "$ISSUE_FILE" ]; then
        echo "ERROR: Issue file not found for $ID"
        exit 1
      fi
      CONFIDENCE=$(grep '^confidence_score:' "$ISSUE_FILE" | head -1 | awk '{print $2}')
      OUTCOME=$(grep '^outcome_confidence:' "$ISSUE_FILE" | head -1 | awk '{print $2}')
      if [ -z "$CONFIDENCE" ] || [ -z "$OUTCOME" ]; then
        echo "ERROR: confidence_score or outcome_confidence missing for $ID"
        exit 1
      fi
      ll-issues show "$ID" --json > "${context.run_dir}/pre_scores_${ID}.json" 2>/dev/null
      echo "Scores persisted for $ID: confidence=$CONFIDENCE, outcome=$OUTCOME"
    evaluate:
      type: exit_code
-   # Removed: fragment: retry_counter  (injected output_numeric evaluator — wrong for this action)
-   # Removed: with: counter_key / max_retries  (retry_counter fragment params, no longer needed)
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

## Resolution

Replaced `fragment: retry_counter` (which injects `output_numeric` evaluator) with explicit
`action_type: shell` + `evaluate: type: exit_code` in both `verify_scores_persisted` and
`verify_re_assess_scores` states. Updated two tests (`test_verify_scores_persisted_uses_retry_counter`
→ `test_verify_scores_persisted_uses_exit_code_evaluator`, same for `verify_re_assess_scores`)
that previously asserted the broken fragment usage.

## Session Log
- `/ll:ready-issue` - 2026-06-06T04:01:56 - `d0d182db-229c-431f-80be-8debdbc2f8d2.jsonl`
- `/ll:format-issue` - 2026-06-06T03:41:01 - `b23a2893-543d-4167-8343-e752c0206d37.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00Z - `bf3719b0-31e7-4794-a41c-534efbeeeff1.jsonl`
- `/ll:manage-issue` - 2026-06-06T04:09:00Z - `fix`

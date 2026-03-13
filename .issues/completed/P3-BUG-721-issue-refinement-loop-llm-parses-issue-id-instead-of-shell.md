---
discovered_date: 2026-03-13
discovered_by: audit
confidence_score: 100
outcome_confidence: 100
completed_date: 2026-03-13
---

# BUG-721: issue-refinement loop asks LLM to parse issue ID instead of using shell

## Summary

`loops/issue-refinement.yaml` — the three prompt states (`format_issues`, `score_issues`,
`refine_issues`) all instructed Claude to "extract the issue ID" from the captured classifier
output at runtime. This is unnecessary LLM work: the classifier always emits a line of the
form `NEEDS_FORMAT BUG-042`, so the second field is trivially parseable with `awk`.

## Root Cause

No `parse_id` intermediate state existed between the `evaluate` classifier and the routing
states. Prompt actions received the raw `${captured.classify.output}` and delegated ID
extraction to the LLM rather than providing the ID directly.

## Fix

Added a `parse_id` shell state that runs immediately after `evaluate` emits a non-`ALL_DONE`
line:

```yaml
parse_id:
  action: echo "${captured.classify.output}" | awk '{printf $2}'
  action_type: shell
  capture: "issue_id"
  evaluate:
    type: exit_code
  on_success: route_format
  on_error: evaluate
```

`awk '{printf $2}'` extracts the issue ID without a trailing newline, storing it as
`captured.issue_id.output`. All three prompt actions were then simplified to reference
`${captured.issue_id.output}` directly:

- `format_issues`: removed "Extract the issue ID..." instruction; hardcoded ID in commands
- `score_issues`: same
- `refine_issues`: same

## Files Modified

- `loops/issue-refinement.yaml`

## Verification

- Shell action string interpolation confirmed: `executor.py:554` calls `interpolate()` on
  all action templates regardless of `action_type`, so `${captured.X.output}` works in
  shell actions.
- `evaluate`'s `on_failure` updated to target `parse_id` (was `route_format`).

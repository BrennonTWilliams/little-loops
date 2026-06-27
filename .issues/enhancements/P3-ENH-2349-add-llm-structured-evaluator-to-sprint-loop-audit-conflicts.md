---
id: ENH-2349
title: "Add llm_structured evaluator to sprint-build-and-validate audit_conflicts state"
type: ENH
status: open
priority: P3
captured_at: "2026-06-27T21:16:24Z"
discovered_date: "2026-06-27"
discovered_by: capture-issue
labels:
- loops
- fsm
- sprint
- evaluators
relates_to:
- BUG-2347
---

# ENH-2349: Add llm_structured evaluator to sprint-loop audit_conflicts state

## Summary

`sprint-build-and-validate.yaml` has **zero** `llm_structured` evaluators — all five gated
states rely on shell exit codes. The `audit_conflicts` state runs
`/ll:audit-issue-conflicts --auto` and unconditionally proceeds (`next: commit`), so any
non-zero or no-op outcome is treated as success. Add an `llm_structured` evaluator that
scores whether each reported conflict was actually addressed (issue files mutated, scope
merged, or explicit deferral noted) before committing.

## Motivation

Per `.claude/CLAUDE.md` § Loop Authoring (rubric audit), a loop with no LLM-judged measure
of its quality-bearing steps cannot detect rubric drift. In the audited run the conflict
audit did produce a real BUG-367/BUG-368 scope merge, but the FSM had no way to verify that
the audit's *output* matched its *claim* — it would have committed regardless.

This is the lowest-priority audit finding and is explicitly deferrable: it adds latency and
non-determinism and should land only after BUG-2346 and BUG-2347 let the loop complete a
real run. Note the meta-loop rule MR-1 (`.claude/CLAUDE.md`): an `llm_structured` evaluator
in a meta-loop must be paired with a non-LLM evaluator in the routing chain — pair this with
an `exit_code` / file-existence check rather than relying on the LLM grade alone.

## Current Behavior

```yaml
audit_conflicts:
  action_type: prompt
  action: |
    Read the sprint file .sprints/${captured.sprint_name.output}.yaml to get the issue list.
    Run `/ll:audit-issue-conflicts --auto` once for all sprint issues as a single grouped call.
  capture: conflict_result
  next: commit          # proceeds unconditionally
```

## Expected Behavior

`audit_conflicts` evaluates whether each reported conflict was addressed and routes a
below-threshold result to a retry / manual-review path rather than straight to `commit`,
while satisfying MR-1 (a non-LLM evaluator also present in the chain).

## Implementation Steps

1. Add an `llm_structured` evaluator to `audit_conflicts` scoring confidence that all
   reported conflicts were addressed; set a `min_confidence` (~0.7).
2. Add `on_no` / `on_error` routing to an `audit_conflicts_retry` (or `manual_review`)
   state instead of dead-ending or silently committing.
3. Satisfy MR-1: pair with a non-LLM evaluator (e.g. an `exit_code` check that the audit
   command succeeded, or a diff/file-mutation check) in the routing chain.
4. Run `ll-loop diagnose-evaluators sprint-build-and-validate` to confirm the new evaluator
   has healthy variance (not toothless).

## Acceptance Criteria

- [ ] `audit_conflicts` has an `llm_structured` evaluator with a threshold and full routing.
- [ ] A below-threshold audit does not silently route to `commit`.
- [ ] MR-1 is satisfied (non-LLM evaluator paired in the chain); `ll-loop validate` passes.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

open

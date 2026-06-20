---
id: ENH-2238
title: 'POLICY_ROUTER_GUIDE: simulate claim inaccurate for policy-router loops'
type: ENH
priority: P3
status: done
completed_at: 2026-06-20 04:09:46+00:00
area: docs
file: docs/guides/POLICY_ROUTER_GUIDE.md
testable: false
---

## Summary

The POLICY_ROUTER_GUIDE incorrectly claims that `ll-loop simulate` lets users confirm which routing rule fires for a given score set in policy-router loops. Simulation only traces FSM state connectivity — it cannot execute shell actions, so policy rule evaluation never occurs.

## Current Behavior

`docs/guides/POLICY_ROUTER_GUIDE.md` lines 159–161 say:

> You don't have to trace the table by hand — `ll-loop simulate policy-refine` walks FSM
> execution interactively without invoking real commands, so you can confirm which rule fires
> for a given score set before committing to a real run.

This is inaccurate. `SimulationActionRunner.run()` returns
`ActionResult(output="[simulated output for: ...]", exit_code=<user-chosen>)` for every
action — including shell ones. Since `policy_parse_scores` and `policy_table_dispatch` are
both `action_type: shell`, simulation:

1. Does **not** write score files (`rubric-dim-*.txt`, `rubric-aggregate.txt`) to `run_dir/`
2. Does **not** evaluate any policy rules against real scores
3. Produces synthetic output that the `classify` evaluator cannot parse into a rule token,
   so every simulated run routes through the `_:` catch-all

The claim that simulate lets the user "confirm which rule fires" is therefore false for
policy-router loops. Simulation traces state connectivity but provides no information about
rule evaluation outcomes.

## Evidence

- `scripts/little_loops/fsm/runners.py:297–302` — `SimulationActionRunner.run()` always
  returns `output="[simulated output for: ...]"`
- `scripts/little_loops/loops/lib/policy-router.yaml` — both fragments are `action_type: shell`

## Expected Behavior

The guide accurately describes what `ll-loop simulate` can and cannot do for policy-router loops. Users who want to validate rule routing are directed to the correct approach (manual trace or real/mocked artifact run).

## Motivation

This enhancement would:
- **User trust**: Users who follow the guide and try `ll-loop simulate` to validate routing always see the `_:` catch-all fire regardless of their score set — confusing behavior with no explanation in the current text.
- **Documentation accuracy**: The POLICY_ROUTER_GUIDE is the primary reference for policy-router loop authoring; inaccurate guidance about available validation tools misleads loop authors.

## Proposed Solution

Replace the misleading sentence with accurate guidance. Options:

**Option A** — Clarify simulate's actual scope and redirect for rule testing:

> You don't have to trace the table by hand — the worked trace above shows the step-by-step
> evaluation. `ll-loop simulate policy-refine` can trace FSM state connectivity without
> running real LLM calls, but it cannot evaluate policy rules (shell actions are not
> executed in simulation). To confirm which rule fires for a given score set, trace the
> table manually or run the loop with a real or mocked artifact.

**Option B** — Remove the simulate sentence and keep only the manual trace guidance (already
present in the paragraph above).

## Scope Boundaries

- **In scope**: Correcting the inaccurate claim on lines 159–161 of `POLICY_ROUTER_GUIDE.md`
- **Out of scope**: Changing how `ll-loop simulate` works; updating other guides that reference simulate; adding new simulation capabilities for policy routing

## Integration Map

### Files to Modify
- `docs/guides/POLICY_ROUTER_GUIDE.md` — lines 159–161 (the misleading simulate claim)

### Dependent Files (Callers/Importers)
- N/A — documentation-only change; no code imports this file

### Similar Patterns
- Other guide docs that reference `ll-loop simulate` may warrant accuracy review (not in scope)

### Tests
- N/A — documentation-only change; no automated tests to update

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — primary file to modify

### Configuration
- N/A

## Implementation Steps

1. Choose Option A or Option B from Proposed Solution (Option A preferred — retains simulate context and redirects correctly)
2. Edit `docs/guides/POLICY_ROUTER_GUIDE.md` lines 159–161 with the corrected text
3. Read surrounding paragraph to confirm it flows cohesively

## Impact

- **Priority**: P3 — Low-priority documentation correction; confusing but not harmful
- **Effort**: Small — Single paragraph edit in one file
- **Risk**: Low — Documentation-only; no code execution paths affected
- **Breaking Change**: No

## Labels

`docs`, `documentation-fix`, `policy-router`

## Status

**Open** | Created: 2026-06-19 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-20T04:08:45 - `9dd6ef7f-7695-469a-9db5-31c9d7c492ba.jsonl`
- `/ll:format-issue` - 2026-06-20T03:51:39 - `26736b38-8a55-4123-887a-77a72b341010.jsonl`

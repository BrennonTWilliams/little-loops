---
id: ENH-2238
title: "POLICY_ROUTER_GUIDE: simulate claim inaccurate for policy-router loops"
type: ENH
priority: P3
status: open
area: docs
file: docs/guides/POLICY_ROUTER_GUIDE.md
---

## Problem

`docs/guides/POLICY_ROUTER_GUIDE.md` line 159–161 says:

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

## Proposed Fix

Replace the misleading sentence with accurate guidance. Options:

**Option A** — Clarify simulate's actual scope and redirect for rule testing:

> You don't have to trace the table by hand — the worked trace above shows the step-by-step
> evaluation. `ll-loop simulate policy-refine` can trace FSM state connectivity without
> running real LLM calls, but it cannot evaluate policy rules (shell actions are not
> executed in simulation). To confirm which rule fires for a given score set, trace the
> table manually or run the loop with a real or mocked artifact.

**Option B** — Remove the simulate sentence and keep only the manual trace guidance (already
present in the paragraph above).

## Impact

Low-priority documentation correction. Users who try to use simulate to validate policy
routing will see it always route to `_:` (deep_repair in policy-refine) regardless of scores,
which is confusing but not harmful.

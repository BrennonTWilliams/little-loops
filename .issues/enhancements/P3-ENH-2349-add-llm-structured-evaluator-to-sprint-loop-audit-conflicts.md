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

1. In `scripts/little_loops/loops/sprint-build-and-validate.yaml`, modify the `audit_conflicts`
   state: remove `next: commit` and add an `evaluate:` block directly on the state. Use
   `source: "${captured.conflict_result.output}"` so the judge reads the already-captured
   audit output rather than the current action's stdout. Add `on_yes: commit`,
   `on_no: audit_conflicts_retry`, `on_partial: audit_conflicts_retry`, `on_error: commit`.
   The `ll_gate` fragment from `lib/common.yaml` (line 47) provides the `action_type: prompt`
   + `evaluate: {type: llm_structured}` boilerplate; either reference the fragment or add the
   evaluate block inline.

2. Add an `audit_conflicts_retry` state (prompt action that re-runs
   `/ll:audit-issue-conflicts --auto` after reviewing the prior output, capturing into
   `conflict_result`, routing `next: commit`).

3. MR-1 is already satisfied at the loop level — `_validate_meta_loop_evaluation()` in
   `scripts/little_loops/fsm/validation.py` performs a loop-wide scan (not per-state) and the
   loop already contains `exit_code` evaluators in `route_input`, `extract_sprint_issues`,
   `route_create`, and `run_sprint`. No extra non-LLM state is needed.

4. Note on `min_confidence`: per `scripts/little_loops/fsm/evaluators.py` and `schema.py`,
   `min_confidence` (default 0.5) only changes routing when combined with
   `uncertain_suffix: true` — without it, routing is driven solely by the `verdict` string
   from the LLM's JSON response. Setting `min_confidence: 0.7` documents intent but does not
   tighten routing on its own. The judge prompt wording is what controls verdict quality.

5. Run `ll-loop validate sprint-build-and-validate` (MR-1/MR-4 checks) and then
   `ll-loop diagnose-evaluators sprint-build-and-validate` to confirm the new evaluator has
   healthy Bernoulli variance `p*(1-p) ≥ 0.05` across ≥10 runs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Capture variable available**: `${captured.conflict_result.output}` holds the full text
  of Claude's `/ll:audit-issue-conflicts --auto` run. The evaluator's `source:` field accepts
  this reference because the capture is written before `_evaluate()` is called in
  `scripts/little_loops/fsm/executor.py`.
- **Self-referencing pattern**: `outer-loop-eval.yaml:generate_report` uses
  `source: "${captured.improvement_report.output}"` where `improvement_report` is the same
  state's own capture key — confirming self-reference works.
- **Routing fallback**: `_route()` in `executor.py` falls back from `on_no` to `on_error`
  when `on_no` is absent; always declare both explicitly.
- **`max_steps` impact**: Adding 2 new states (`audit_conflicts` evaluate path + retry)
  adds at most 2 extra steps per retry cycle. Current `max_steps: 16` may be tight;
  consider incrementing to 18.

## Acceptance Criteria

- [ ] `audit_conflicts` has an `llm_structured` evaluator with a threshold and full routing.
- [ ] A below-threshold audit does not silently route to `commit`.
- [ ] MR-1 is satisfied (non-LLM evaluator paired in the chain); `ll-loop validate` passes.

## Impact

- **Priority**: P3 — low-priority quality improvement; explicitly deferrable until BUG-2346 and BUG-2347 are resolved
- **Effort**: Small — single YAML edit adding one `llm_structured` evaluator plus a retry/review state to `sprint-build-and-validate.yaml`
- **Risk**: Low — isolated to the `audit_conflicts` state; existing `exit_code` routing is unchanged; `ll-loop validate` will catch MR-1 violations before the loop can run
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding an `llm_structured` evaluator to the `audit_conflicts` state in `sprint-build-and-validate.yaml` only
- **Out of scope**: Adding LLM evaluators to other states in the sprint loop
- **Out of scope**: Modifying or replacing the existing `exit_code` evaluators in the loop
- **Out of scope**: Changing the behavior of `/ll:audit-issue-conflicts` itself
- **Out of scope**: Broader FSM refactoring beyond this single state addition

## Integration Map

### Files to Modify
- `loops/sprint-build-and-validate.yaml` — add `llm_structured` evaluator and `on_no`/`on_error` routing to `audit_conflicts` state

### Dependent Files (Callers/Importers)
- N/A — loop YAML is invoked directly via `ll-loop run sprint-build-and-validate`

### Similar Patterns
- `scripts/little_loops/loops/outer-loop-eval.yaml` in `generate_report` — `slash_command` + `llm_structured` with `source: "${captured.improvement_report.output}"` (self-referencing capture), `min_confidence: 0.7`, full four-route table; closest structural match to `audit_conflicts`
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` in `check-quality` — `prompt` + `llm_structured` (no `source:`), grades its own output, full four-route table; demonstrates the `ll_gate` fragment pattern
- `scripts/little_loops/loops/loop-specialist-eval.yaml` in `check_skill` — `prompt` + `llm_structured` with `source:` and `min_confidence: 0.7`, multi-condition judge prompt; reference for scoring structured audit output
- `scripts/little_loops/loops/eval-driven-development.yaml` in `route_eval` — action-less pure-router state with `llm_structured` and `source:` from prior state's capture
- `scripts/little_loops/loops/lib/common.yaml` `llm_gate` fragment (line 47) — ready-made `action_type: prompt` + `evaluate: {type: llm_structured}` template; `audit_conflicts` could use `fragment: llm_gate`

### Tests
- N/A — loop YAML changes are validated via `ll-loop validate sprint-build-and-validate` and `ll-loop diagnose-evaluators sprint-build-and-validate` (no unit tests for loop YAML)

### Documentation
- N/A — no documentation update required for an internal loop evaluator addition

### Configuration
- N/A

## Session Log
- `/ll:refine-issue` - 2026-06-27T21:32:33 - `265ed482-e8e6-4a78-a5cf-d16f10ac38ee.jsonl`
- `/ll:format-issue` - 2026-06-27T21:21:09 - `d9d01f4a-6f9b-4201-87a6-de089e4470ef.jsonl`
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

**Open** | Created: 2026-06-27 | Priority: P3

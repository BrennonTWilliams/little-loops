---
id: ENH-2032
title: Extract duplicated rn-* states into common.yaml fragments + ll_commit adoption
type: ENH
priority: P3
parent: ENH-1777
relates_to:
- ENH-2033
- ENH-1775
- ENH-1776
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: loop-audit
decision_needed: false
status: open
confidence_score: 100
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 15
---

# ENH-2032: Extract duplicated rn-* states into common.yaml fragments + ll_commit adoption

## Summary

A loop audit of the `rn-*` family (the most complex built-in loops) found three
single-state patterns copied verbatim (or near-verbatim) across loops, plus
three loops still hand-rolling `/ll:commit` instead of using the existing
`ll_commit` fragment. Extract the three patterns into parameterized fragments in
`scripts/little_loops/loops/lib/common.yaml` and migrate the commit states. This
continues the Wave 1–4 extraction effort (ENH-1775/1776/1777/1854/1875).

This is the low-risk, mechanical half of the audit. The sequential research
chain shared by `rn-plan`/`rn-refine` is tracked separately in
[[ENH-2033]].

## Motivation

Each duplicated state is a maintenance liability: a bug fix or rubric change must be applied to 2–3 identical copies instead of one authoritative definition. The rn-* family is the most complex and most frequently modified group of loops, so the blast radius of each missed update is disproportionately high. Fragment extraction directly continues the Wave 1–4 effort (ENH-1775/1776/1777/1854/1875) and brings the rn-* loops to parity with the rest of the harness, where similar patterns already reference shared fragments.

## Parent Issue

Continues ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows.

## Current Behavior

Three duplicated single-state patterns in the `rn-*` family:

### F3 — 9-dimension plan `score` state (verbatim)

`rn-plan.yaml:227` and `rn-refine.yaml:264` contain a byte-for-byte identical
`score` state: a `prompt` action that scores a plan against the same 9 rubric
dimensions (breadth, depth, complexity, clarity, consistency, logic_strategy,
feasibility, testability, risk_mitigation) on a LOW/MEDIUM/HIGH/VERY-HIGH scale,
rewrites `plan-rubric.md`, and emits the `ALL_VERY_HIGH` sentinel evaluated by an
`output_contains` evaluator.

> Note: this is **distinct** from `lib/score-plan-quality.yaml`'s
> `score_plan_quality` fragment, which is a different *4-dimension batch* scorer
> for `rn-plan-apo`. Do not conflate the two; use a new fragment name.

### F4 — `diagnose` failure handler (near-verbatim)

`rn-plan.yaml:284` and `rn-refine.yaml:363` share a `diagnose` terminal handler:
"the loop has terminated with an unrecoverable failure… read the rubric if it
exists… identify the most likely failure cause… write a one-paragraph diagnostic
summary," then `next: failed`. The only differences are the loop name and one or
two loop-specific bullets. (There are 14 `diagnose` states repo-wide; this issue
only normalizes the two rn-* ones, but the fragment is reusable by the rest.)

### F5 — sub-loop `rate_limit_diagnostic` (identical modulo one word)

`rn-remediate.yaml` and `rn-decompose.yaml` share a `rate_limit_diagnostic`
shell state: write `RATE_LIMITED` to `${context.run_dir}/subloop_outcome_<ID>.txt`,
echo a `[RATE_LIMIT]` log line, and `next: failed`. They differ only in the
operation word ("remediation" vs "decomposition").

> Scope note: `rn-implement.yaml`'s `rate_limit_diagnostic` is the *queue/parent*
> variant (appends a timestamp to `rate_limits.txt`, `next: dequeue_next`) — a
> different behavior. It is **out of scope**; the fragment covers only the
> sub-loop variant.

### F6 — inline `/ll:commit` instead of the `ll_commit` fragment

Three loops hand-roll a `commit` state with an inline `/ll:commit` prompt action
instead of using the existing `fragment: ll_commit` (in
`lib/prompt-fragments.yaml`, already adopted by 6 loops):

- `issue-discovery-triage.yaml:commit`
- `issue-refinement.yaml:commit`
- `sprint-build-and-validate.yaml:commit`

## Expected Behavior

- `lib/common.yaml` gains three fragments: `plan_rubric_score`,
  `loop_failure_diagnose`, `subloop_rate_limit_diagnostic`.
- `rn-plan`, `rn-refine`, `rn-remediate`, `rn-decompose` reference the fragments
  and drop their inline copies; behavior is unchanged.
- The three commit states use `fragment: ll_commit`, preserving each loop's
  existing `next:` target and commit-message intent (some pass a specific message
  or `--auto`; verify the fragment supports the caller supplying these, else keep
  the message inline alongside the fragment).

## Proposed Solution

1. **`plan_rubric_score`** (F3) in `lib/common.yaml`: `action_type: prompt` with
   the 9-dimension scoring body; evaluator `output_contains` / `pattern:
   ALL_VERY_HIGH`. Caller supplies `on_yes`/`on_no`/`on_error`. Model after
   existing `llm_gate` / `convergence_gate` fragments. Include a `description:`
   block (required by the fragment-description test).
2. **`loop_failure_diagnose`** (F4): `action_type: prompt`, parameterized via
   `parameters:` on `loop_name` (and an optional `extra_bullets` string), fixed
   `next: failed`. Callers bind with `with: {loop_name: rn-plan}` etc.
3. **`subloop_rate_limit_diagnostic`** (F5): `action_type: shell`, parameterized
   on `operation` (the log word) and `outcome_token` (default `RATE_LIMITED`),
   fixed `next: failed`.
4. **Migrate F6**: replace the three inline commit states with `fragment:
   ll_commit`, retaining each `next:` and message.
5. Run `ll-loop validate` on every touched loop; add fragment tests; update the
   fragment catalog docs.

## Implementation Steps

1. Add `plan_rubric_score` fragment to `lib/common.yaml` (action_type: prompt, 9-dimension scorer, output_contains evaluator)
2. Add `loop_failure_diagnose` fragment with `loop_name` parameter (fixed `next: failed`)
3. Add `subloop_rate_limit_diagnostic` fragment with `operation` parameter (fixed `next: failed`)
4. Migrate rn-plan and rn-refine: inline `score` → `plan_rubric_score`, inline `diagnose` → `loop_failure_diagnose`
5. Migrate rn-remediate and rn-decompose: inline `rate_limit_diagnostic` → `subloop_rate_limit_diagnostic`
6. Migrate three inline commit states to `fragment: ll_commit` (retain each loop's `next:` and message)
7. Run `ll-loop validate` on all touched loops; add fragment integration tests; update catalog docs

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add the three fragments (each
  needs a `description:` field).
- `scripts/little_loops/loops/rn-plan.yaml` — `score` → `plan_rubric_score`;
  `diagnose` → `loop_failure_diagnose` (`with: {loop_name: rn-plan}`).
- `scripts/little_loops/loops/rn-refine.yaml` — same two conversions
  (`with: {loop_name: rn-refine}`).
- `scripts/little_loops/loops/rn-remediate.yaml` — `rate_limit_diagnostic` →
  `subloop_rate_limit_diagnostic` (`with: {operation: remediation}`).
- `scripts/little_loops/loops/rn-decompose.yaml` — same
  (`with: {operation: decomposition}`).
- `scripts/little_loops/loops/issue-discovery-triage.yaml`,
  `issue-refinement.yaml`, `sprint-build-and-validate.yaml` — commit → `ll_commit`.

### Reference Patterns
- `lib/common.yaml` fragments `llm_gate`, `convergence_gate`, `shell_exit`,
  `retry_counter` (the parameterized-fragment model with `parameters:`/`with:`).
- `lib/prompt-fragments.yaml:ll_commit` — the migration target for F6.
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()`, `_deep_merge()`
  (merge semantics; read before editing).

### Tests & Docs
- `scripts/tests/test_fsm_fragments.py` — add fragment-presence + `resolve_fragments`
  integration tests for the three new fragments, following the existing
  `TestConvergenceGateFragment` pattern; the
  `test_all_common_yaml_fragments_have_description` test auto-covers them once
  `description:` is present.
- `skills/create-loop/reference.md` and `docs/guides/LOOPS_GUIDE.md` — append the
  three new fragments to the `lib/common.yaml` fragment catalog tables.

## Acceptance Criteria

- [ ] `plan_rubric_score`, `loop_failure_diagnose`, `subloop_rate_limit_diagnostic`
      exist in `lib/common.yaml`, each with a `description:`.
- [ ] `rn-plan`, `rn-refine`, `rn-remediate`, `rn-decompose` reference the new
      fragments; the inline copies are removed.
- [ ] The three commit states use `fragment: ll_commit` with original `next:`/message.
- [ ] `ll-loop validate` passes for every touched loop.
- [ ] `python -m pytest scripts/tests/test_fsm_fragments.py` passes (including new tests).
- [ ] Behavior parity: a smoke run of `rn-plan` / `rn-remediate` reaches the same
      terminal states with equivalent artifacts as before.

## Scope Boundaries

- `rn-implement.yaml`'s `rate_limit_diagnostic` (queue/parent variant, `next: dequeue_next`) is **out of scope** — different behavior from the sub-loop variant.
- The 12 other `diagnose` states repo-wide (beyond the 2 rn-* ones) are **out of scope** — the fragment is reusable by them but their migration is not part of this issue.
- No new loop behaviors or logic changes — pure extraction/migration with behavior parity.
- The rn-plan/rn-refine sequential research chain is tracked separately in ENH-2033.

## Impact

- **Priority**: P3 — maintenance improvement; no user-visible behavior change, but reduces future bug blast-radius in the most-complex loops
- **Effort**: Small — all extractions are mechanical (verbatim or near-verbatim copies); the `parameters:`/`with:` pattern is already established in `lib/common.yaml`
- **Risk**: Low — behavior is unchanged; existing fragment resolver tests cover the mechanism; `ll-loop validate` catches structural errors before merge
- **Breaking Change**: No

## Labels

`loop-refactor`, `fragments`, `maintenance`, `rn-loops`, `captured`

## Status

**Open** | Created: 2026-06-08 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-09T02:33:17 - `48fd4c40-d1dc-4aa8-8bd4-b98c0e5aaac7.jsonl`
- `/ll:format-issue` - 2026-06-09T01:28:13 - `b8cd5b00-183b-4a0c-a5fc-6f9113d43c0a.jsonl`

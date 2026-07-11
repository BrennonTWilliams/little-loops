---
id: BUG-2605
title: autodev's fast-path decision gates bypass check_decision_decidable/deposit_options validation
type: BUG
status: open
priority: P2
captured_at: "2026-07-11T18:07:11Z"
discovered_date: "2026-07-11"
discovered_by: capture-issue
relates_to:
- BUG-2513
- BUG-2519
- BUG-2595
- ENH-2443
labels:
- loops
- fsm
- autodev
- decide-issue
- decision-gate
---

# BUG-2605: autodev's fast-path decision gates bypass check_decision_decidable/deposit_options validation

## Summary

`autodev.yaml` has four states that detect `decision_needed: true` and route
toward `/ll:decide-issue`. Only one of them — `decide_current`
(`autodev.yaml:196-231`) — goes through the `check_decision_decidable` →
`deposit_options` → `record_options_deposited` detour that ENH-2443 added to
validate enumerable options exist (and deposit them via
`/ll:refine-issue --auto` if not) before invoking decide. The other three
route straight to `run_decide` with zero validation:

- `check_decision_at_dequeue` (`autodev.yaml:107-119`, added by BUG-2513)
- `check_decision_after_refine` (`autodev.yaml:170-178`)
- `check_decision_before_size_review` (`autodev.yaml:639-651`, added by BUG-2519)

`rn-remediate.yaml` has the equivalent detour wired correctly on its one
decision-check entry point (`rn-remediate.yaml:264-296`) — autodev is the
outlier.

## Current Behavior

When an issue is dequeued with `decision_needed: true` already set (the most
common case — the flag was set by a prior refine pass, not discovered mid-loop),
`check_decision_at_dequeue` routes directly to `run_decide`, which invokes
`/ll:decide-issue ${ID} --auto`. If the issue's `## Proposed Solution` has no
enumerable `### Option A/B` blocks (a very common shape — see BUG's sibling
finding that ~40 of ~70 currently-flagged issues are in this state, checked via
`ll-issues check-decidable`), decide-issue's own auto-recovery either doesn't
run or doesn't produce options, leaving `decision_needed: true` unchanged. The
BUG-2595 guard (`assert_decision_cleared`) then correctly refuses to hand the
issue to `implement_current` and routes it to `record_decision_unresolved`
instead — but the issue never got a real chance at option deposition first,
because the fast path skipped straight past `check_decision_decidable` /
`deposit_options`.

Confirmed live: `ll-loop run autodev ENH-2492 -q` (run dir
`.loops/runs/autodev-20260711T104104/`) drained ENH-2492 to
`autodev-decision-unresolved.txt` on 2026-07-11 despite the issue passing
confidence (96) and outcome (77) thresholds — the decision gate was never
given the deposit-options detour to attempt.

## Expected Behavior

All four decision-check states funnel through the same
`check_decision_decidable` → `deposit_options` → `record_options_deposited`
sequence before `run_decide` runs, exactly like `decide_current` already does.
This gives every decision-gated issue one bounded attempt (the existing
write-once marker `autodev-decide-options-deposited`, cleared at
`dequeue_next`) to have options deposited via `/ll:refine-issue --auto` before
decide-issue is asked to choose one — instead of `run_decide` firing against
unstructured prose and reliably no-oping.

## Motivation

This closes the loop on BUG-2513/BUG-2519/BUG-2595, which each fixed a
different symptom of the same decision-gate cluster (routing bypass on
non-success, `on_success` coupling, missing post-decide verification) without
addressing that most entry points never attempt option deposition at all. The
practical effect today: `autodev` runs against any issue with a stale/prose-only
`decision_needed: true` flag deterministically drain to
`decision-unresolved` every single run, with no forward progress, even though
the ENH-2443 machinery to fix exactly this exists in the file — it's just not
reachable from the states that actually fire first.

## Proposed Solution

Rewire the `on_yes` target of the three bypass states from `run_decide` to
`check_decision_decidable`:

- `check_decision_at_dequeue.on_yes`: `run_decide` → `check_decision_decidable`
- `check_decision_after_refine.on_yes`: `run_decide` → `check_decision_decidable`
- `check_decision_before_size_review.on_yes`: `run_decide` → `check_decision_decidable`

`check_decision_decidable` (`autodev.yaml:212-231`) already reads
`captured.input.output` generically (not tied to any one caller), already
short-circuits via the `autodev-decide-options-deposited` marker to bound the
detour to one deposit attempt, and already routes to `run_decide` on both its
`on_yes` (decidable) and `on_error` arms — so downstream wiring needs no
changes. This is a mechanical retarget of three `on_yes:` values, not a new
state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — retarget `on_yes` on lines 117,
  176, and 649 from `run_decide` to `check_decision_decidable`.

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml:209` (`decide_current.on_yes`) —
  the existing correct wiring to model the other three states after.
- `scripts/little_loops/loops/rn-remediate.yaml:264-296` — the sibling loop's
  correctly-wired single entry point.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `rn-remediate.yaml` is not uniformly clean — it has a **second** decision-check
  entry point, `check_decision_needed_post` (`rn-remediate.yaml:725-735`,
  reached from `mark_refined`/`mark_wired`), which routes `on_yes` **directly to
  `decide`**, bypassing `check_decision_decidable` exactly like the three buggy
  autodev states this issue fixes. Only `check_decision_needed`
  (`rn-remediate.yaml:264-269` → `check_decision_decidable` at 271-296) is the
  correct pattern to model after; `check_decision_needed_post` shares this bug's
  defect and is out of scope here, but may warrant its own follow-up issue.

### Tests
- `scripts/tests/test_builtin_loops.py` — add/extend routing assertions that
  `check_decision_at_dequeue`, `check_decision_after_refine`, and
  `check_decision_before_size_review` all route their `on_yes` arm through
  `check_decision_decidable`, mirroring any existing assertion for
  `decide_current`.

### Documentation
- N/A — no user-facing CLI/config surface changes.

## Implementation Steps

1. Update the three `on_yes:` targets in `autodev.yaml` as described above.
2. Run `ll-loop validate autodev` to confirm the FSM still validates cleanly.
3. Add/extend routing tests in `test_builtin_loops.py`.
4. Re-run `ll-loop run autodev ENH-2492 -q` (or another currently-stuck
   `OPTIONS_MISSING` issue) to confirm it now attempts `deposit_options`
   instead of draining straight to `decision-unresolved`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Step 3 touches **two** test files, not one: `scripts/tests/test_builtin_loops.py`'s
  routing assertions for these states are duplicated in
  `scripts/tests/test_autodev_decision_gate.py` (the dedicated BUG-2513/BUG-2519
  structural-test suite). Both files must be updated in lockstep.
- Two **existing** assertions currently pin the pre-fix (buggy) routing and will
  fail once the `on_yes:` retarget lands — these must be *updated*, not merely
  extended:
  - `test_builtin_loops.py:2761-2772` `test_check_decision_after_refine_routes_correctly`
    — the `on_yes == "run_decide"` assertion (lines 2764-2766) must become
    `on_yes == "check_decision_decidable"`.
  - `test_builtin_loops.py:3028-3035` `test_check_decision_before_size_review_on_yes_routes_to_run_decide`
    — asserts `on_yes == "run_decide"`; retarget to `check_decision_decidable`
    (and rename to match).
  - `test_autodev_decision_gate.py:135-143` `test_check_decision_at_dequeue_on_yes_routes_to_run_decide`
    — same assertion, separate file.
  - `test_autodev_decision_gate.py:334-342` `test_check_decision_before_size_review_on_yes_routes_to_run_decide`
    — same assertion, separate file.
- `check_decision_at_dequeue` has **no existing on_yes-routing test** in either
  file today — only the `dequeue_next → check_decision_at_dequeue` linkage is
  tested (`test_builtin_loops.py:2578-2584`,
  `test_autodev_decision_gate.py:167-174`). This needs a **net-new** test in
  both files. Model it on the existing correct precedent:
  `test_builtin_loops.py:3152-3160` `test_decide_current_on_yes_routes_to_check_decision_decidable`
  (the ENH-2443 assertion for `decide_current`, which already asserts the
  target state this bug retargets the other three toward).

## Impact

- **Priority**: P2 - Blocks forward progress on a large fraction of the
  backlog (~40 of ~70 issues currently flagged `decision_needed: true` are in
  `OPTIONS_MISSING`); autodev cannot make progress on any of them without
  manual intervention.
- **Effort**: Small - three `on_yes:` retargets in one YAML file, no new
  states or Python code.
- **Risk**: Low - reuses existing, already-tested states and marker logic;
  the target state (`check_decision_decidable`) already handles arbitrary
  callers.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.claude/CLAUDE.md` | Loop Authoring section — FSM validation rules (`ll-loop validate`) |

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-07-11T18:40:42 - `4566a976-60c6-45f6-b2d7-8afae702a6fd.jsonl`
- `/ll:capture-issue` - 2026-07-11T18:07:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37898a30-ea4e-4972-91db-a694a29a9e31.jsonl`

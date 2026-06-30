---
id: ENH-2406
title: '`rn-implement`: pre-dequeue learning-readiness gate (mirror ENH-2008 blocked_by gate)'
type: ENH
priority: P3
status: open
relates_to:
- EPIC-2207
- ENH-2008
- ENH-2319
- ENH-2402
- ENH-2405
labels:
- rn-implement
- learning-tests
- orchestration
- efficiency
---

# ENH-2406: `rn-implement` pre-dequeue learning-readiness gate (mirror ENH-2008 blocked_by gate)

## Summary

The learning gate fires **inside** `ll-auto --only` (ENH-2319's deliberate single
choke-point), so by the time a learning-gate block is detected, the issue has already been
dequeued and consumed an implement slot — and the block surfaces only as a
`LEARNING_GATE_BLOCKED` marker that rn-remediate/autodev classify *after* the failed implement
attempt. ENH-2008 already established the fix-pattern for the structurally-identical
`blocked_by` case: a cheap pre-dequeue gate in `rn-implement`'s router that defers the issue
*before* spending a remediation/implement budget. This issue mirrors that pattern for
learning-readiness: check the dequeued issue's `learning_tests_required` against the registry
(stale-aware) right after dequeue, and route a still-unproven issue to a distinct
learning-blocked outcome before `run_remediation` runs.

## Current Behavior

- `dequeue_next → fifo_pop`/`select_next` pops an issue with **no** learning-readiness check.
- `check_depth → run_remediation` enters `rn-remediate`, which eventually calls
  `ll-auto --only`; the learning gate inside `process_issue_inplace`
  (`issue_manager.py:854-869`) runs `proof-first-task` and, if a target can't be proven,
  prints `LEARNING_GATE_BLOCKED` and exits 1.
- rn-remediate's `check_learning_gate` state then classifies that marker post-hoc (the
  ordering of this classifier vs. `check_impl_auth` was the subject of extended debate — a
  symptom of the gate being discovered late and reverse-engineered from one exit code).
- The implement slot and any preceding remediation passes are already spent.

## Expected Behavior

- After dequeue (both `fifo_pop` and `select_next`), before `check_depth`/`run_remediation`,
  `rn-implement` checks the dequeued issue's `learning_tests_required` via the stale-aware
  gate (`scripts/little_loops/learning_tests/gate.py`).
- If unproven/refuted targets remain, route directly to a learning-blocked terminal/record
  state (mirroring ENH-2008's `mark_deferred`) with a "prove with /ll:explore-api" reason —
  skipping `run_remediation` entirely. The issue re-surfaces once its deps are proven.
- If all targets are proven (or none registered), proceed as today.
- The in-`ll-auto` gate (ENH-2319) **remains** as defense-in-depth: this is an earlier,
  cheaper, FSM-visible check, not a relocation. With it in place, the post-implement
  `check_learning_gate` classifier becomes a rarely-hit safety net whose internal ordering
  stops mattering.

## Motivation

1. **Wasted budget** — a learning-blocked issue can burn remediation passes before the
   in-`ll-auto` gate stops it; the pre-dequeue check skips that, exactly as ENH-2008 does for
   `blocked_by`.
2. **Visible, routable signal** — today the FSM infers a rich gate verdict from a single exit
   code + grep. A first-class pre-dequeue state lets the loop route learning-blocked issues
   distinctly without the fragile post-failure classifier chain.
3. **Honors the established pattern** — ENH-2008 already routes on `blocked_by` frontmatter
   post-dequeue; `learning_tests_required` is the same shape of first-class readiness
   frontmatter and deserves the same treatment.

## Implementation Steps

1. Add a `check_learning_ready` state in `rn-implement` after dequeue and before
   `check_depth`, reading the dequeued issue's `learning_tests_required` and calling the
   stale-aware gate helper for each target.
2. On any unproven/refuted target → route to a `mark_learning_blocked` record state
   (model on ENH-2008's `mark_deferred`): tag `failures.txt` with `LEARNING_GATE_BLOCKED`,
   surface the `/ll:explore-api` remedy, and `next: dequeue_next`.
3. On all-proven / no-targets → `check_depth` as today.
4. Demote rn-remediate/autodev's post-implement `check_learning_gate` to an explicit
   safety-net comment; do **not** change its routing in this issue (that ordering is settled
   separately).
5. Coordinate with ENH-2405 so the pre-dequeue check and the in-`ll-auto` gate prove the same
   registered target list.

## Scope Boundaries

- **In scope**: a post-dequeue learning-readiness gate in `rn-implement`'s router; a distinct
  learning-blocked record path; documenting the post-implement classifier as a safety net.
- **Out of scope**: removing the ENH-2319 in-`ll-auto` gate (kept as defense-in-depth);
  changing `blocked_by` handling (ENH-2008); auto-running `/ll:explore-api` from inside
  rn-implement (the in-`ll-auto` gate already does that via `type: learning`); the
  auth-vs-learning-gate classifier ordering (settled separately).

## Acceptance Criteria

1. An issue with an unproven `learning_tests_required` target is routed to the learning-blocked
   path **without** entering `run_remediation` (verified by run trace / no remediation pass
   recorded).
2. An issue with all targets proven proceeds to `check_depth` unchanged.
3. An issue with no `learning_tests_required` field is unaffected.
4. The in-`ll-auto` learning gate still fires for callers that bypass `rn-implement`
   (ll-parallel, ll-sprint) — i.e. the choke point is intact.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — add a `check_learning_ready` state and its
  routing evaluator on the `check_blocked_by`/`route_blocked_by` → `check_depth` edge (mirrors
  `check_blocked_by`/`route_blocked_by`, `rn-implement.yaml:353-461`); add a `mark_learning_blocked`
  record state near `mark_deferred` (`rn-implement.yaml:912`)
- `scripts/little_loops/loops/rn-remediate.yaml` — demote `check_learning_gate`
  (`rn-remediate.yaml:452`) to an explicit safety-net comment; no routing change in this issue

### Dependent Files (Callers/Importers)
- None outside `rn-implement.yaml` — the new state is purely an additional router edge

### Similar Patterns
- `check_blocked_by` / `route_blocked_by` (`rn-implement.yaml:353-461`) — the ENH-2008 pre-dequeue
  gate this issue mirrors, including the fail-open-to-`check_depth` shape
- `mark_deferred` (`rn-implement.yaml:912`) — model for `mark_learning_blocked`'s record-and-requeue
  shape
- the in-`ll-auto` learning gate in `process_issue_inplace`
  (`scripts/little_loops/issue_manager.py:854-869`) — the ENH-2319 choke point this pre-dequeue
  check front-runs but does not replace; calls the same stale-aware gate helper
  (`scripts/little_loops/learning_tests/gate.py`)

### Tests
- `scripts/tests/test_rn_implement.py` — new `TestLearningReadyGate` class (mirrors
  `TestBlockedByGate`, `test_rn_implement.py:804`)
- `scripts/tests/test_rn_remediate.py` — update/annotate `check_learning_gate` coverage to reflect
  its safety-net role (no routing change expected)

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — note the pre-dequeue learning-readiness gate
  alongside the existing `blocked_by` gate note (ENH-2008)

### Configuration
- N/A

## API/Interface

N/A — no public API changes. This adds internal FSM router states (`check_learning_ready`,
`mark_learning_blocked`) to `rn-implement.yaml`, not a function/class signature or CLI argument.

## Impact

- **Priority**: P3 — efficiency + clarity improvement on a working path; not blocking.
- **Effort**: Small–Medium — one router state + one record state in `rn-implement`, modeled
  directly on ENH-2008.
- **Risk**: Low–Medium — additive router state; must not double-block or regress the
  across-runners choke point. Pairs with ENH-2405.
- **Breaking Change**: No.

## Labels

`enhancement`, `rn-implement`, `learning-tests`, `orchestration`, `efficiency`

## Session Log
- `/ll:format-issue` - 2026-06-30T21:24:21 - `13874c47-a99b-4643-8187-fc2c7bf0ae42.jsonl`
- `/ll:capture-issue` - 2026-06-30T21:17:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/517f4fde-43d5-44f7-afc7-41dd7c15be45.jsonl`

## Status

**Open** | Created: 2026-06-30 | Priority: P3

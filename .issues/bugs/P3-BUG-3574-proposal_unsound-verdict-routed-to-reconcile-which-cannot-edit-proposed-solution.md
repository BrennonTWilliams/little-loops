---
id: BUG-3574
type: BUG
title: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
---

# BUG-3574: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution

## Summary

In `refine-to-ready-issue.yaml`, `check_proposal_unsound` (ENH-3250) routes a
`verify_verdict: PROPOSAL_UNSOUND` to `check_reconcile_limit` → `/ll:reconcile-issue`. Its
comment describes the failure as the Proposed Solution itself contradicting the code. But
reconcile's binding contract (`commands/reconcile-issue.md`, "Contract") rewrites only
`## Implementation Steps`, `## Acceptance Criteria`, `## Integration Map` and, conditionally,
`## Scope Boundaries`. It does not rewrite `## Proposed Solution` or decision rationale.
Reconcile can fix drifted directives, but not a refuted chosen design.

## Current Behavior

A genuinely unsound proposal is sent to a remedy that cannot edit it. It burns the reconcile
budget and eventually defers.

## Expected Behavior

Directive drift goes to reconcile. A refuted selected proposal goes to a bounded design
revision (re-open the decision via `resolve-decision`, or refine with a design focus), then
wire and verify the revised approach.

## Steps to Reproduce

1. Take an issue whose Proposed Solution, implemented as written, contradicts the code it names
2. Run refine-to-ready-issue; verify-issues persists `verify_verdict: PROPOSAL_UNSOUND`
3. Observe the route to `/ll:reconcile-issue`, which leaves `## Proposed Solution` untouched per its contract; the verdict recurs until the reconcile budget is spent

## Motivation

Unsound proposals are exactly the cases where implementation would do the most damage. Routing them to a remedy that cannot touch the proposal guarantees a wasted budget and eventual deferral.

## Proposed Solution

Have `/ll:verify-issues --check` distinguish two sub-kinds, e.g. `DIRECTIVE_DRIFT` (the
directives contradict the code, but the proposal is sound) versus `PROPOSAL_UNSOUND`
(the chosen approach itself is refuted). Route the first to reconcile and the second to
decision/design revision. Alternatively, keep one verdict and have
`check_proposal_unsound` inspect which section the evidence cites.

## Integration Map

- `commands/verify-issues.md` (§B6 verdict taxonomy)
- `scripts/little_loops/cli/issues/check_verify_verdict.py` (new query mode if split)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` `check_proposal_unsound`

## Implementation Steps

1. Decide: split the verdict in verify-issues, or inspect cited sections in the gate
2. Add the new verdict/query mode to `check_verify_verdict.py`
3. Route refuted proposals to resolve-decision/design refinement, then wire and verify
4. Tests for both routes

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low

## Acceptance Criteria

- [ ] A refuted Proposed Solution is never routed only to reconcile
- [ ] Directive-only drift still routes to reconcile

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`

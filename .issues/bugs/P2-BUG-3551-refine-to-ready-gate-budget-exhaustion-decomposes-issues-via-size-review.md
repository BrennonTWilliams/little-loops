---
id: BUG-3551
title: refine-to-ready-issue decomposes issues when a structure gate exhausts the shared refine budget
type: BUG
priority: P2
status: open
discovered_date: '2026-09-24'
labels:
- loops
- refine-to-ready-issue
---

# refine-to-ready-issue decomposes issues when a structure gate exhausts the shared refine budget

## Summary

`check_refine_limit` (target 2) allows exactly one `refine_followup` per run, and
six routes share it: a non-VALID verify verdict (`check_proposal_unsound.on_no`),
the hedge scan (`check_hedge_attempts.on_yes`), `check_placeholders.on_no`,
`check_design.on_no`, reconcile exhaustion (`check_reconcile_limit.on_no`), and
`check_readiness.on_no`. Exhaustion always routes to `breakdown_issue`
(`/ll:issue-size-review --auto`). Size review is the remedy for an issue whose
*scores* stay low after refinement (scope too large) — it is the wrong remedy for
an issue that still lacks a `## Program Design` section, still carries template
placeholders, or still has false claims.

## Current Behavior

A structure gate that is still red after the one `refine_followup` (or that fires
after another gate already spent it) routes `check_refine_limit.on_no →
breakdown_issue`, decomposing an issue that is not too big.

## Expected Behavior

Budget exhaustion reached from a structure gate exits via `failed` with a
distinct terminal class (`gate_unmet`) so callers see "not ready, needs human
attention", not a decomposition. Exhaustion reached from `check_readiness`
(score-driven) keeps routing to `breakdown_issue`. The refine budget stays
shared (check_design's Decision Rationale Option B).

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue <ID>` on an issue whose first refine
   leaves an unresolved hedge (`check_hedge_attempts` spends the followup).
2. After `refine_followup`, `check_design` fails (no `## Program Design`).
3. `check_refine_limit` reads 2 → `breakdown_issue` runs size review.

## Proposed Solution

Add `check_gate_refine_limit` — same counter file as `check_refine_limit`
(`refine-to-ready-refine-count`), `on_yes: refine_followup`, `on_no:
record_gate_unmet`. Retarget the structure-gate routes to it.
`record_gate_unmet` writes `gate_unmet` to `refine-terminal-class` and exits via
`failed`. The hedge route keeps its BUG-3170 semantics: an exhausted budget on a
hedge reading proceeds to `check_placeholders` rather than failing.

## Program Design

Loop YAML only (`scripts/little_loops/loops/refine-to-ready-issue.yaml`); no
Python changes. New states `check_gate_refine_limit`, `check_hedge_refine_limit`,
`record_gate_unmet`. autodev's `skip_inflight` treats any non-`infra` class as
`refine_failed`, so no consumer change is needed.

## Impact

- **Priority**: P2 — silently decomposes healthy issues under autodev/standalone runs.
- **Effort**: Small — routing change plus tests.
- **Risk**: Low — only exhaustion targets change; happy path untouched.

## Acceptance Criteria

- Structure-gate exhaustion routes to `record_gate_unmet` → `failed`, writing `gate_unmet`.
- `check_readiness.on_no` still reaches `breakdown_issue` on exhaustion.
- Hedge exhaustion proceeds to `check_placeholders`.
- `python -m pytest scripts/tests/test_builtin_loops.py` passes; `ll-loop validate refine-to-ready-issue` is clean.

## Related

- BUG-3170 (hedge bound), ENH-3248 (reconcile rung), BUG-3249 (design gate), BUG-3552, BUG-3553

## Status

Open

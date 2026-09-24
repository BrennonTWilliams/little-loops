---
id: EPIC-3565
type: EPIC
title: Autodev readiness contract hardening from 2026-09-24 audit
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:31:05Z'
---

# EPIC-3565: Autodev readiness contract hardening from 2026-09-24 audit

## Summary

Umbrella for the findings of the 2026-09-24 external audit of `autodev` and its sub-loops
(`refine-to-ready-issue`, `oracles/resolve-decision`, `oracles/verify-confidence-scores`,
`ready-to-implement-gate`). The audit verdict: autodev covers most useful capabilities on its
normal path (preflight → refine → wire → normalize → verify → gates → confidence → ll-auto →
closure verification), but that readiness contract does not hold on every route. Side paths
bypass preparation, some evidence checks accept stale or absent results, and some stops skip
final accounting.

All ten findings (F1–F10) were checked against source. Five cheap, targeted fixes landed in
commit `9a5d0f523` (plus follow-up test fixes). The rest need design decisions and are open
children here. The last child consolidates the duplicated parent/child repair routing into
one preparation controller. It is deliberately blocked until the behavioral fixes are
covered by regression tests.

## Motivation

- Every little-loops project on this machine is `local-editable` against this checkout, so
  autodev routing defects show up across all of them.
- The outer loop has grown to ~87 states, with repair and rescoring policy duplicated
  between parent and child. That makes contract gaps like F1 easy to introduce and hard to
  see.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Tests
- TBD - identify shared test infrastructure

### Documentation
- TBD - docs that need updates

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope

In scope: the audit's findings F1–F10 and the consolidation proposal.

Out of scope: adding more skills to the happy path. The audit explicitly advises against
that. Also out of scope: the audit's composite scorecard, which is a judgment, not a
measurement.

## Children
- **BUG-3566** — Autodev pre-deferral remedy dispatcher binds env vars to ll-issues instead of python3 (open)
- **BUG-3567** — Autodev rate-limit exits bypass finalize_done and summary.json (open)
- **BUG-3568** — Autodev residual decision group reaches implement_current with decision_needed armed (open)
- **BUG-3569** — Autodev dequeue-time decision resolution bypasses preflight and refine pipeline (open)
- **BUG-3570** — Confidence-check skill misstates format-check --fix repair coverage (open)
- **BUG-3571** — Refine-to-ready accepts stale or absent verify verdict and confidence scores (open)
- **BUG-3572** — Failed spike suppresses unproven-mechanism outcome cap in confidence-check (open)
- **FEAT-3573** — Autodev code formatting and quality evidence gate before closure credit (open)
- **BUG-3574** — PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution (open)
- **ENH-3575** — Structured policy gate field replacing prose gate-phrase grep in autodev (open)
- **ENH-3576** — Format-check repair coverage for missing and boilerplate sections with format-issue fallback (open)
- **ENH-3577** — Consolidate autodev issue preparation into a single controller loop (open)













## Acceptance Criteria

- [ ] Every child issue is `done` or `cancelled`
- [ ] Every edge into `implement_current` passes the same preparation gates as the normal path
- [ ] Every autodev exit writes `summary.json` with a truthful verdict

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2
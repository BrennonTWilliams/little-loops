---
id: EPIC-3565
type: EPIC
title: Autodev readiness contract hardening from 2026-09-24 audit
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:31:05Z'
relates_to:
- ENH-3597
- FEAT-3598
- ENH-3601
- ENH-3602
- ENH-3600
- BUG-3603
- ENH-3590
- ENH-3607
- ENH-3609
- ENH-3610
- ENH-3611
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

## Goal

Every route into implementation passes the same current-evidence readiness contract as autodev's normal path, and every run ends with truthful accounting. Then consolidate the duplicated preparation routing behind regression tests.

## Motivation

- Every little-loops project on this machine is `local-editable` against this checkout, so
  autodev routing defects show up across all of them.
- The outer loop has grown to 105 states, with repair and rescoring policy duplicated
  between parent and child. That makes contract gaps like F1 easy to introduce and hard to
  see.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`, `refine-to-ready-issue.yaml`, `oracles/resolve-decision.yaml`, `oracles/verify-confidence-scores.yaml`
- `skills/confidence-check/`, `skills/spike/`, `skills/manage-issue/`

### Dependent Files (Callers/Importers)
- See children

### Similar Patterns
- See children

### Tests
- See children

### Documentation
- See children

### Configuration
- N/A

## Impact

- **Priority**: P2 — the autodev readiness contract does not hold on every route
- **Effort**: Large (sum of children)
- **Risk**: Medium — autodev is live in every local-editable project

## Scope

In scope: the audit's findings F1–F10 and the consolidation proposal.

Out of scope: adding more skills to the happy path. The audit explicitly advises against
that. Also out of scope: the audit's composite scorecard, which is a judgment, not a
measurement.

## Children
- **BUG-3566** — Autodev pre-deferral remedy dispatcher binds env vars to ll-issues instead of python3 (done)
- **BUG-3567** — Autodev rate-limit exits bypass finalize_done and summary.json (done)
- **BUG-3568** — Autodev residual decision group reaches implement_current with decision_needed armed (done)
- **BUG-3569** — Autodev dequeue-time decision resolution bypasses preflight and refine pipeline (done)
- **BUG-3570** — Confidence-check skill misstates format-check --fix repair coverage (done)
- **BUG-3571** — Refine-to-ready accepts stale or absent verify verdict and confidence scores (done)
- **BUG-3572** — Failed spike suppresses unproven-mechanism outcome cap in confidence-check (cancelled — split into BUG-3591, BUG-3592, BUG-3593)
- **FEAT-3573** — Autodev code formatting and quality evidence gate before closure credit (open)
- **BUG-3574** — PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution (done)
- **ENH-3575** — Structured policy gate field replacing prose gate-phrase grep in autodev (done)
- **ENH-3576** — Format-check repair coverage for missing and boilerplate sections with format-issue fallback (done)
- **ENH-3577** — Consolidate autodev issue preparation into a single controller loop (done — decomposed into ENH-3597, FEAT-3598, ENH-3599, ENH-3601, ENH-3602, ENH-3600)
- **BUG-3588** — Autodev post-repair rescoring accepts stale or absent confidence scores (done)
- **BUG-3591** — Confidence-check suppresses unproven-mechanism cap on attempted-only spikes (done)
- **BUG-3592** — Spike treats any non-zero Verification exit as a refutation (done)
- **BUG-3593** — Loops do not route refuted or inconclusive spike verdicts (done)
- **ENH-3597** — Emit a typed per-issue run record from refine-to-ready-issue (open)
- **FEAT-3598** — Add ll-issues next-obligation deterministic preparation selector (open)
- **ENH-3599** — Move spike and decision repair routing from autodev into refine-to-ready-issue (open)
- **ENH-3601** — Move autodev second-pass preparation routing into a preparation controller (open)
- **ENH-3602** — Single budget owner for learning-proof evidence (open)
- **ENH-3600** — Drive autodev ledger from run records and remove preparation handshake files (open)
- **BUG-3603** — Autodev pre-implement proof gate fails open into implement_current (open)

Moved out 2026-09-25: **ENH-3590** (advise consult) is a new capability, not an audit
finding. It stays linked through `relates_to`.

### Implementation order

BUG-3603, ENH-3597, ENH-3602 (independent) → FEAT-3598 → ENH-3599 → ENH-3601 → FEAT-3573 →
ENH-3600. FEAT-3573 blocks only ENH-3600, which rewrites the same closure accounting.
- **ENH-3604** — Adopt ll-issues next-obligation inside refine-to-ready-issue and settle next-action delegation (open)
- **ENH-3609** — Route autodev on the child run record outcome and ledger child stops (open)
- **ENH-3610** — Move autodev decision repair into refine-to-ready-issue behind an obligation selector (open)
- **ENH-3611** — Move autodev spike and proof-gate repair into refine-to-ready-issue (open)
- **ENH-3612** — manage-issue Phase 4 runs configured verification commands verbatim (open)
- **ENH-3613** — Autodev summary.json splits cancelled from implemented closures (open)
- **BUG-3614** — Autodev DECISION re-entry routes lifetime-capped issues to breakdown (open)








## Acceptance Criteria

- [ ] Every child issue is `done` or `cancelled`
- [ ] Every edge into `implement_current` passes the same preparation gates as the normal path (enforced by BUG-3603's structural invariant test)
- [ ] Every autodev exit writes `summary.json` with a truthful verdict

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-09-24T19:42:30 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
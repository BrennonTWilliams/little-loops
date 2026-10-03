---
id: EPIC-3710
type: EPIC
title: 'll-next: next-action arena'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:44:30Z'
relates_to:
- FEAT-3714
---

# EPIC-3710: ll-next: next-action arena

## Summary

Deliver `ll-next`, an advisory CLI that recommends the next project action across a fixed menu of verbs (implement, refine, resolve-blocker, run-loop, run-sprint, capture-issues) using auditable, deterministic scoring. Split out of FEAT-3561 after an Opus pre-implementation review (2026-10-03): core CLI first, then recommendation evidence/shared history, a choice-agreement backtest, and extra generators. Default output gives each available verb a first-round opportunity; pressure is opt-in.

**Closure criterion:** `ll-next` ships for six verbs with documented gates, coverage, unavailable-data behavior and exit codes; recommendation events/explicit acknowledgements and observed attribution never fabricate ignored labels; optional activity pressure is bounded and disabled by default; a reproducible as-of implement-issue choice-agreement report includes origin uncertainty and sample coverage. `--execute`, learned weights, LLM reranking, and the three finding-backed verbs are out of scope.

## Impact

- **Priority:** P3 — project-wide decision support; advisory only.
- **Effort:** Large across four slices; each independently reviewable.
- **Risk:** High — persuasive but wrong rankings from stale signals or misattributed acceptance. Mitigated by explicit missing-data states and unknown-not-ignored acceptance.
- **Breaking Change:** No; existing `next-*` CLIs are untouched.

## Children

- **FEAT-3561** — `ll-next` core: advisory CLI, four generators, gates/coverage, round-robin fill (open; blocked by FEAT-3681)
- **FEAT-3711** — recommendation events, shared read-only history, observed/explicit acceptance and opt-in activity pressure (open; blocked by FEAT-3561)
- **FEAT-3712** — As-of `implement-issue` backtest report (open; blocked by FEAT-3561)
- **FEAT-3713** — capture-issues and run-sprint generators (open; blocked by FEAT-3561 and FEAT-3711's shared reader)

## Goal

A user can ask "what should I do next?" and get a short, legible, evidence-backed list across action types, with every missing signal, veto and fallback reported rather than guessed.

## Scope

Four children. The core owns the CLI/output Schema, pure snapshot/scoring and round-robin fill with no history access/writes. The events child owns the only history migration/shared reader and adds opt-in pressure. The backtest is independent of the events child; extra generators reuse its reader and are sequenced after it.

## Detached / deferred (not children; `relates_to` this epic)

- **FEAT-3714** (P4, deferred) — persisted findings store for `pay-tech-debt`, `update-docs` and `meta` verbs. No persisted source exists today (`.ll/ll-doc-drift-state.json` holds only `last_check_ts`), so those generators cannot ship honestly. Detached because deferred is non-terminal and would strand the epic branch.
- **FEAT-3681** — scorer extraction and `next` config surface; prerequisite of FEAT-3561, already detached from this epic.
- Decision-rule compliance gate and decisions-based historical-signal axis — deferred until decision rules carry machine-evaluable scope (today only issue-scoped structure is machine-readable).

## Implementation order

FEAT-3681 → FEAT-3561 → { FEAT-3711, FEAT-3712 }; FEAT-3711 → FEAT-3713. FEAT-3711 claims the next free history schema version at implementation time (currently 58 → 59 if still free). ENH-3678/ENH-3679 are done and supply rebuild gating/short-timeout seams; the recommendation writer must explicitly use those seams.

## Status

**Open** | Created: 2026-10-03 | Priority: P3

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

Deliver `ll-next`, an advisory CLI that recommends the next project action across a fixed menu of verbs (implement, refine, resolve-blocker, run-loop, run-sprint, capture-issues) using auditable, deterministic scoring. Split out of FEAT-3561 after an Opus pre-implementation review (2026-10-03): the original single issue bundled nine generators, a schema migration, pressure/acceptance learning and a backtest, and the cut that follows real dependencies is core CLI first, then events/pressure, backtest and extra generators as independent follow-ups.

**Closure criterion:** `ll-next` ships for the six in-scope verbs with documented gates, coverage and exit codes; recommendation events record display and explicit/derived acceptance honestly; an as-of `implement-issue` backtest report exists with a contamination-aware ground truth. `--execute`, learned weights, LLM reranking, and the three finding-backed verbs are out of scope.

## Impact

- **Priority:** P3 — project-wide decision support; advisory only.
- **Effort:** Large across four slices; each independently reviewable.
- **Risk:** High — persuasive but wrong rankings from stale signals or misattributed acceptance. Mitigated by explicit missing-data states and unknown-not-ignored acceptance.
- **Breaking Change:** No; existing `next-*` CLIs are untouched.

## Children

- **FEAT-3561** — `ll-next` core: advisory CLI, four generators, gates/coverage, round-robin fill (open; blocked by FEAT-3681)
- **FEAT-3711** — `recommendation_events`, derived acceptance and time-based bucket pressure (open; blocked by FEAT-3561)
- **FEAT-3712** — As-of `implement-issue` backtest report (open; blocked by FEAT-3561)
- **FEAT-3713** — `capture-issues` and `run-sprint` generators (open; blocked by FEAT-3561)
- **FEAT-3711** — ll-next recommendation_events, derived acceptance and time-based bucket pressure (open)
- **FEAT-3712** — As-of implement-issue backtest report for ll-next (open)
- **FEAT-3713** — ll-next capture-issues and run-sprint generators (open)




## Goal

A user can ask "what should I do next?" and get a short, legible, evidence-backed list across action types, with every missing signal, veto and fallback reported rather than guessed.

## Scope

Four children. The core issue owns the CLI, schema, scoring integration and cross-type fill with no persisted state. The events child owns the only `SCHEMA_VERSION` bump and replaces round-robin with pressure. The backtest and extra-generator children are independent once the core lands.

## Detached / deferred (not children; `relates_to` this epic)

- **FEAT-3714** (P4, deferred) — persisted findings store for `pay-tech-debt`, `update-docs` and `meta` verbs. No persisted source exists today (`.ll/ll-doc-drift-state.json` holds only `last_check_ts`), so those generators cannot ship honestly. Detached because deferred is non-terminal and would strand the epic branch.
- **FEAT-3681** — scorer extraction and `next` config surface; prerequisite of FEAT-3561, already detached from this epic.
- Decision-rule compliance gate and decisions-based historical-signal axis — deferred until decision rules carry machine-evaluable scope (today only issue-scoped structure is machine-readable).

## Implementation order

FEAT-3681 → FEAT-3561 → { FEAT-3711, FEAT-3712, FEAT-3713 } (independent of one another). FEAT-3711 carries the only `SCHEMA_VERSION` bump (58 → 59); ENH-3678 (done) already stops it from auto-spawning a full rebuild.

## Status

**Open** | Created: 2026-10-03 | Priority: P3
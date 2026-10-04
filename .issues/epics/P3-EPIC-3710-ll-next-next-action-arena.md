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
- FEAT-3722
- ENH-3720
---

# EPIC-3710: ll-next: next-action arena

## Summary

Deliver `ll-next`, an advisory CLI that recommends the next project action across a fixed menu of verbs (implement, refine, resolve-blocker, run-loop, run-sprint, capture-issues) using auditable, deterministic scoring and explicit eligibility evidence. Split out of FEAT-3561 after an Opus pre-implementation review (2026-10-03), then slimmed by further Opus reviews (2026-10-04): core CLI first, then a shared read-only history reader, recommendation events with explicit acceptance and extra generators. The historical backtest was cancelled after its source audit found insufficient clean-base confirmed-manual evidence. Default output gives each available verb a first-round opportunity; capture-issues is an activity-gated singleton with freshness unknown, rather than an invented freshness score.

**Closure criterion:** `ll-next` ships for six verbs with documented gates, per-verb coverage/evidence-only behavior, unavailable-data behavior and exit codes; recommendation events and explicit acknowledgements never fabricate ignored labels and require project ownership/existing schema; the core checkpoint and six-verb command-usability checks are recorded. FEAT-3712's source-audit no-go supplies the permitted insufficient-evidence outcome instead of a diagnostic report. `--execute`, learned weights, LLM reranking, activity pressure/automatic attribution (FEAT-3722), scan-age/freshness telemetry and the three finding-backed verbs are out of scope.

## Impact

- **Priority:** P3 — project-wide decision support; advisory only.
- **Effort:** Large across four active slices; each independently reviewable.
- **Risk:** High — persuasive but wrong rankings from stale signals. Mitigated by lower-bounded curves, explicit missing-data states, unknown-not-ignored acceptance, and a go/pause check after the core.
- **Breaking Change:** No; existing `next-*` CLIs are untouched.

## Children

- **FEAT-3561** — `ll-next` core: advisory CLI, four generators, gates/coverage, round-robin fill (open; blocked by FEAT-3681)
- **FEAT-3721** — shared read-only `HistorySnapshot` reader, local-only (open; blocked by FEAT-3561)
- **FEAT-3711** — recommendation events, `accept`/`feedback` explicit acceptance (open; blocked by FEAT-3561 and FEAT-3721)
- **FEAT-3712** — As-of `implement-issue` backtest diagnostic report (**cancelled**; pre-implementation source audit: no supported structured source supplies the required clean recorded base paired with confirmed-manual choice provenance; full design retained)
- **FEAT-3713** — capture-issues and run-sprint generators (open; blocked by FEAT-3561 and FEAT-3721)

## Goal

A user can ask "what should I do next?" and get a short, legible, evidence-backed list across action types, with every missing signal, veto and fallback reported rather than guessed.

## Scope

Five linked children: four open, one cancelled. The core owns the CLI/output Schema, pure snapshot/scoring (lower-bounded curves at nominal defaults, no coverage multiplier) and round-robin fill with no history access/writes; it ends with an implement-ranking comparison plus mixed-verb usefulness checkpoint. FEAT-3721 owns the shared local-only reader with bounded primary-key walks, exact recommendation lookups and explicit 250 ms read-lock waits; it does not promise unavailable indexes or a total deadline. The events child owns the only history migration and a narrow existing-store no-ensure write seam; normal recommendations never initialize/migrate history. Extra generators reuse the reader without depending on events: sprint ranking plus an activity-only scan offer with unknown freshness. Backend-wide deadline machinery remains ENH-3720.

## Detached / deferred (not children; `relates_to` this epic)

- **FEAT-3714** (P4, deferred) — persisted findings store for `pay-tech-debt`, `update-docs` and `meta` verbs. No persisted source exists today (`.ll/ll-doc-drift-state.json` holds only `last_check_ts`), so those generators cannot ship honestly. Detached because deferred is non-terminal and would strand the epic branch.
- **FEAT-3681** — scorer extraction and `next` config surface; prerequisite of FEAT-3561, already detached from this epic.
- **FEAT-3722** (P4, deferred) — `ProducerEvidence` automatic observed-acceptance attribution and opt-in activity pressure, cut from FEAT-3711 (observational, nothing to attribute yet). Full design preserved there.
- **ENH-3720** (P4) — cross-backend total-deadline plumbing (`backend.py`/`libsql.py`/`hrana.py`), split from FEAT-3711; unlocks remote history for ll-next. v1 is local-only, so it is not on the critical path.
- Decision-rule compliance gate and decisions-based historical-signal axis — deferred until decision rules carry machine-evaluable scope (today only issue-scoped structure is machine-readable).

## Implementation order

FEAT-3681 → FEAT-3561 (walking-skeleton checkpoint and recorded go/pause decision for all follow-ons) → FEAT-3721 → { FEAT-3711, FEAT-3713 }. FEAT-3712's source audit already ran independently of core implementation and cancelled that slice. FEAT-3711 claims the next free history schema version at implementation time (currently 58 → 59 if still free). ENH-3678/ENH-3679 are done and supply rebuild gating/per-lock timeout seams; readers must pass their own 250 ms timeout explicitly, and recording must avoid implicit schema setup. Deliberate initialization uses existing `ll-session migrate`; remote history/deadline work is ENH-3720.

## Review Notes

- 2026-10-04: Code/schema audit plus `/ll:advise` with Opus (confidence 0.78) corrected failing curve-factor defaults, impossible index/deadline promises, missing project ownership and source/coverage handoffs. Removed unused scan-freshness/weight machinery and producer-registration leftovers. All five original children remain linked for progress accounting; FEAT-3712 is terminally cancelled with a recorded source-contract no-go, avoiding a deferred child that would strand closure.

## Status

**Open** | Created: 2026-10-03 | Priority: P3

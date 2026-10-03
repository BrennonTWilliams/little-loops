---
id: FEAT-3713
type: FEAT
title: ll-next capture-issues and run-sprint generators
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
---

# FEAT-3713: ll-next capture-issues and run-sprint generators

## Summary

Add the `capture-issues` and `run-sprint` candidate generators to `ll-next`, each with explicit axes, applicability and an acceptance-producer entry. Split out of FEAT-3561 because their scoring axes and acceptance producers were undefined there.

## Current Behavior

After FEAT-3561, `ll-next` covers `implement-issue`, `refine-issue`, `resolve-blocker` and `run-loop`. Stale discovery scans and runnable sprints are never recommended.

## Expected Behavior

- **`run-sprint`** — source: existing `.sprints/*.yaml` only; no auto-clustering. Display `ll-sprint run NAME`. Defined axes (initial defaults, pinned by fixtures, tunable via keyed `next` config): share of the sprint's issues ready **and** unblocked, mean priority, days since the sprint last ran. Gate: unblocked-ness on the sprint's first wave. Sprints with no remaining open issues yield no candidate.
- **`capture-issues`** — source: a stale discovery signal with a configured scan scope (`scan.focus_dirs`); no candidate without a known scope. Axes: days since last scan, commits touching the scope since the last scan (information freshness). Display `/ll:scan-codebase` with the scope named, never an invented argument.
- Each verb gets a named acceptance producer registered with FEAT-3711's table (sprint run events / `orchestration_runs`; `skill_events` for scan-codebase/capture-issue) or stays `unknown`.

## Motivation

These two verbs round out the actions a user actually chooses between and have real persisted sources, unlike the finding-backed verbs deferred to FEAT-3714.

## Proposed Solution

Two independently testable generator functions plus entries in the axes × verbs applicability/default-weights matrix; no change to selection logic.

## Integration Map

### Files to Modify

- Candidate-generator modules from FEAT-3561, `scripts/little_loops/config-schema.json` (keyed `next` entries for these verbs), tests, `docs/reference/CLI.md`/`CONFIGURATION.md`.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority:** P3
- **Effort:** Medium
- **Risk:** Low–Medium — sprint readiness derivation and scan-staleness signals must come from persisted data only.
- **Breaking Change:** No.

## Scope Boundaries

- **In scope:** the two generators, their axes/gates/weights, producer entries, fixtures for empty-source and populated cases, docs.
- **Out of scope:** auto-clustered sprints, `--execute`, finding-backed verbs (FEAT-3714).

## Acceptance Criteria

- [ ] Both generators yield no candidate when their source is absent (no `.sprints/`, no scope, no remaining open issues), tested.
- [ ] Emitted commands name existing sprints/scopes and carry no invented arguments.
- [ ] Axes, applicability and default weights are in the matrix and pinned by fixed-clock fixtures.
- [ ] Acceptance producers are named or the verb stays `unknown`.
- [ ] `python -m pytest scripts/tests/` passes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P3

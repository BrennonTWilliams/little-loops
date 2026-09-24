---
id: BUG-3537
type: BUG
title: reconcile-issue leaves resolved Concerns and stale confidence scores uncleared
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T01:32:52Z'
---

# BUG-3537: reconcile-issue leaves resolved Concerns and stale confidence scores uncleared

## Summary

`/ll:reconcile-issue` rewrites an issue's directive sections but leaves the `### Concerns` bullets in `## Confidence Check Notes` describing the now-fixed contradictions as live, and leaves `outcome_confidence` / `confidence_score` at their pre-reconcile values. Gates and readers that consult the notes or scores keep seeing the issue as contradictory until someone edits it by hand.

## Current Behavior

`commands/reconcile-issue.md` states its purpose as stopping `/ll:confidence-check` from re-flagging the same Concern and the Readiness score from plateauing. Its rewrite scope covers Implementation Steps, Acceptance Criteria and Integration Map (plus conditional sections), and excludes `## Confidence Check Notes`. It does not mark stored scores stale; the only nudge is a suggestion in its CONCERNS output to re-run `/ll:confidence-check`. The stale Concerns and scores therefore survive a successful reconcile and were cleared only by a manual edit.

## Expected Behavior

After a successful reconcile, each Concern the rewrite resolved is struck through with a `Resolved` note (or the Confidence Check Notes section is marked stale), and the stored confidence scores are flagged stale or reset so downstream gates (`refine-to-ready`, `decide-issue`, readiness thresholds) do not act on pre-reconcile values.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

- `commands/reconcile-issue.md` — scope and output steps.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 — the issue body is correct; the stale notes and scores mislead gates and readers.
- **Effort**: Small — a bounded addition to the reconcile command's output step.
- **Risk**: Low.

## Steps to Reproduce

1. Take an issue whose `## Confidence Check Notes` lists Concerns that its Acceptance Criteria contradict (observed on BUG-3530, 2026-09-24; `outcome_confidence: 59`).
2. Run `/ll:reconcile-issue BUG-3530`. It rewrites Acceptance Criteria (delete-all-replayable-channels, rollout-not-duplicated) and strikes the withdrawn design hint in Verification Notes; `reconcile_attempted: true` is set.
3. Read the issue afterwards: the Concerns in Confidence Check Notes still present the fixed contradictions as open, and `outcome_confidence` is still 59 (LOW).

## Acceptance Criteria

- [ ] After a reconcile that resolves a Concern, the matching bullet in `## Confidence Check Notes` is struck through with a resolution note, or the section is marked stale.
- [ ] Stored `confidence_score` / `outcome_confidence` are flagged stale or cleared after a successful reconcile, so a gate cannot treat them as current.
- [ ] Reconcile still leaves Concerns it did not resolve untouched.
- [ ] A test covers the reconcile output for an issue with a stale Concern and scores.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T01:32:57 - `2f8f7a22-ff27-4b63-912d-b3be6e3850a5.jsonl`

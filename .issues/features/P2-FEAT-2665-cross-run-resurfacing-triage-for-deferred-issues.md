---
id: FEAT-2665
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T02:50:02Z'
discovered_date: '2026-07-18'
discovered_by: capture-issue
parent: EPIC-2663
relates_to: [ENH-2664, ENH-2666, ENH-2533, FEAT-1680]
blocked_by: [ENH-2664]
labels:
- loops
- issue-lifecycle
- observability
---

# FEAT-2665: Cross-run resurfacing/triage for automation-deferred issues

## Summary

Provide a cross-run mechanism that surfaces automation-deferred issues back to a
human for triage, so issues that fail an automated readiness/remediation gate
don't disappear from the backlog. This is the direct fix for the ENH-2464 /
ENH-2465 / ENH-2466 drop.

## Use Case

After `rn-implement-20260717T165621` deferred ENH-2464, ENH-2465, and ENH-2466,
they vanished from every default view and no run ever brought them back. A
maintainer wants a single command (and/or an end-of-run + session-end report)
that answers: *"what did automation set aside, why, and how long ago?"* — so they
can re-open, re-scope, or intentionally close each one.

## Current Behavior

- `deferred` is excluded from active selection (`sprint.py:15` — active is
  `{open, in_progress, blocked}`) and from default listings
  (`issue_parser.py:1250` skips `done/cancelled/deferred`).
- The only auto-resurfacing, `re_enqueue_unblocked` (rn-implement.yaml:782),
  runs *within a single run* and only for `blocked_by` reasons.
- The sole manual path is `ll-issues list --status deferred`, which does not
  distinguish automation from human deferral and has no staleness/aging view.

## Proposed Behavior

- A triage surface listing `deferred_by: automation` issues (from ENH-2664) with
  `deferred_reason` and age, sorted so the "remediation stalled" class ranks
  highest.
- Delivery options (decide during refinement): a dedicated CLI
  (`ll-issues deferred-triage` or a `list` flag), a session-end sweep/report
  (precedent: FEAT-1680's session-end status sweep), and/or an rn-implement
  end-of-run callout referencing the parked set.

## API/Interface

- New read-only reporting command or flag; no change to selection semantics.
- Consumes the frontmatter fields defined by ENH-2664.

## Implementation Steps

1. Query issues with `status: deferred` + `deferred_by: automation`, joining reason + age.
2. Render a triage report (CLI + optional session-end hook).
3. Wire an rn-implement end-of-run callout naming the parked issues (complements ENH-2533's summary.json).
4. Tests: a deferred-by-automation fixture appears in the triage output; human-deferred does not.

## Impact

- **Priority**: P2 — closes the loop that silently dropped real backlog issues.
- **Effort**: Medium.
- **Risk**: Low — read-only surfacing; depends on ENH-2664's fields.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-18T02:50:02Z

---

## Status

- **Current**: open
- **Last Updated**: 2026-07-18

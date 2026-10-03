---
id: FEAT-3714
type: FEAT
title: Persisted findings store for ll-next pay-tech-debt, update-docs and meta verbs
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:17Z'
relates_to:
- EPIC-3710
- FEAT-3561
deferred_by: human
deferred_date: '2026-10-03T17:45:43Z'
---

# FEAT-3714: Persisted findings store for ll-next pay-tech-debt, update-docs and meta verbs

## Summary

Define a persisted findings store so `ll-next` can honestly recommend `pay-tech-debt`, `update-docs` and `meta` actions. Deferred: no persisted source exists today, and label-filtered issue fallbacks would duplicate `implement-issue` candidates.

## Current Behavior

`.ll/ll-doc-drift-state.json` holds only `last_check_ts`. Tech-debt and harness-audit results are not persisted as structured findings, so generators for these verbs would either invent findings or pass vacuous empty-source tests.

## Expected Behavior

Audit/docs-drift/harness-audit commands persist structured findings (id, kind, target, severity, detected-at, status) to a queryable store. `ll-next` generators for the three verbs read that store and yield nothing when it is empty. Revive when demand for these verbs is demonstrated after the EPIC-3710 core ships.

## Motivation

Completes the nine-verb taxonomy from the original FEAT-3561 design without fabricating candidates.

## Proposed Solution

Out of scope until revived; decide store location (history.db table vs `.ll/` file) and the producers (`audit-architecture`, docs-drift check, harness audit) then.

## Integration Map

Deferred. Files, tests and docs to be determined when the issue is revived; candidate touch points are `audit-architecture`, the docs-drift check, the harness audit and the `ll-next` generators.

## Implementation Steps

Deferred. Decide store location and producers on revival, then follow the EPIC-3710 generator pattern (explicit empty-source behavior, named acceptance producer).

## Use Case

After revival, `ll-next` recommends `update-docs` only because a persisted docs-drift finding names the drifted file.

## Acceptance Criteria

- [ ] Deferred; acceptance criteria are written when the issue is revived (store location, producers, empty-source behavior per verb).

## Impact

- **Priority:** P4
- **Effort:** Large
- **Risk:** Medium — new persistence and producer changes across several commands.
- **Breaking Change:** No.

## Scope Boundaries

- **Out of scope:** everything until the issue is un-deferred.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P4

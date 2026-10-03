---
id: FEAT-3714
type: FEAT
title: Persisted findings store for ll-next pay-tech-debt, update-docs and meta verbs
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:17Z'
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

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

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

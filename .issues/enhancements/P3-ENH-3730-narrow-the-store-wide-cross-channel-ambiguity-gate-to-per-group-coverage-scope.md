---
id: ENH-3730
type: ENH
title: Narrow the store-wide cross-channel ambiguity gate to per-group coverage scope
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T02:23:16Z'
parent: EPIC-3562
relates_to:
- ENH-3723
- ENH-3543
---

# ENH-3730: Narrow the store-wide cross-channel ambiguity gate to per-group coverage scope

## Summary

Evaluate the cross-channel ambiguity check in `select_usage_coverage` per coverage group (or per verified identity) instead of store-wide, so verified host/session groups can be `non_overlapping` while unverifiable rows stay `overlap_unresolved`. This is Option C from ENH-3723; it changes ENH-3543's coverage contract and needs its own design.

## Current Behavior

`select_usage_coverage` computes `ambiguous_cross_channel` once over every row: a live channel and at least one non-live channel are present, and any row anywhere lacks a verified identity. `_classify_coverage` then marks every group `overlap_unresolved` with reason `unverified_cross_channel_identity`.

Measured read-only on 2026-10-04 against the local store (517,222 `usage_events` rows): all 20,045 coverage groups are `overlap_unresolved`, `selected_rows` is empty, and every unscoped consumer returns no canonical figure: `ll-ctx-stats` all-history and per-model, `aggregate_usage`, `cost_attribution`, `waste_attribution` and the snapshot selection. The report-window `since` filter is applied after reconciliation, so it does not help.

Two independent populations trip the gate (verified 2026-10-04): 482,949 Claude `transcript` rows with NULL `host_basis`, and all 266 `channel='live'` rows (NULL `session_id` and `identity_basis`). Reconciling either population alone does not clear it.

## Expected Behavior

Ambiguity is evaluated within the scope that can actually overlap. A verified host/session group (as the scoped session reader already treats it) is `non_overlapping` even when unrelated unverified rows exist elsewhere in the store. Unverifiable rows, including sessionless live rows, remain `overlap_unresolved` with a stable reason. Identity is never inferred from timestamps, counts or order, and live rows are not joined to transcript rows without a native key (ENH-3543, ENH-3655).

## Motivation

Today the gate makes unscoped canonical reporting unavailable for the whole store regardless of any provenance policy decision. ENH-3723 chose an interim, scope-local alternative: a `channel=` scope on `select_usage_coverage` for the quality consumer, leaving the store-wide gate unchanged. This issue is the root-cause fix that would let the other unscoped consumers publish canonical figures for verified groups.

## Proposed Solution

TBD - requires design. Open question: evaluate per `_coverage_key` group versus per verified identity, and whether live rows can ever certify without a native key. Must keep source, snapshot and `ll-ctx-stats` parity and must not weaken the session reader's verified-identity requirement.

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

- **Priority:** P3 - improves what unscoped reports can publish; ENH-3723 does not depend on it.
- **Risk:** Medium - changes ENH-3543's coverage contract; a loosened gate could over-certify overlap.

## Scope Boundaries

- **In scope:** the ambiguity computation in `scripts/little_loops/history_reader/usage.py`, parity tests across source, snapshot and `ll-ctx-stats`, and API/CLI docs for the changed coverage contract.
- **Out of scope:** the legacy-NULL, estimated/mixed and quality qualification policy (ENH-3723), joining live and transcript rows by timestamp or count, and promoting unknown-provenance rows to measured.

## Related

ENH-3723 (interim `channel=` scope, quality consumer), ENH-3543 (coverage selector), ENH-3655, EPIC-3562.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-05 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-05T02:23:32 - `dd4da702-03cb-4aad-8b85-189a7f98afba.jsonl`

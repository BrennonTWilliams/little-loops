---
id: ENH-3666
type: ENH
title: Batch backfill --rebuild commits to shorten history.db write lock
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T15:29:40Z'
---

# ENH-3666: Batch backfill --rebuild commits to shorten history.db write lock

## Summary

`rebuild()` in `scripts/little_loops/session_store/lifecycle.py` wipes and re-derives all JSONL-sourced cache tables inside one `BEGIN IMMEDIATE` transaction, so `history.db` is write-locked for the whole replay. On a large store this exceeds the 5000 ms `_BUSY_TIMEOUT_MS` (`session_store/schema.py`) that every other `ll-*` process waits, and their telemetry writes fail.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

Observed 2026-09-29 with a ~9.6 GB `history.db` and a ~1 GB WAL: a detached `little_loops.cli.backfill_worker ... --rebuild` (spawned from the session-start hook) held the write lock for minutes. A concurrent `ll-issues list --group-by epic` logged `cli_event_context: enter failed for 'll-issues' (OperationalError: database is locked)` (`session_store/writers.py`, `cli_event_context`), dropped its `cli_events` row, and took ~12s wall time. Every ll-* command and loop run during a rebuild is affected, not just this one.

## Proposed Solution

Shorten the write-lock window of `rebuild()` without exposing a partially replaced table set. Options to evaluate:

- Build derived tables into shadow tables (or a side DB) in batched transactions, then swap in one short transaction.
- Commit per `_backfill_*` phase with a "rebuild in progress" meta marker so readers/next start can detect and resume an incomplete rebuild.
- Yield the lock between batches (commit + brief sleep) so waiting writers can interleave.

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

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Constraints

- The current single transaction is deliberate: the `except` branch comment says "A failed replay must not expose a partially replaced rollout set." Any batching design must preserve that atomic-visibility guarantee or replace it with an explicit in-progress marker.
- `last_rebuild_version` and `_set_usage_derive_checkpoint` must only be set once the whole rebuild has completed.
- Related but separate: the `database is locked` warning severity and the telemetry-insert timeout are not in scope here.

## Acceptance Criteria

- During `--rebuild` on a large DB, no single write transaction holds the lock longer than `_BUSY_TIMEOUT_MS`.
- A concurrent `ll-*` command during a rebuild logs no `database is locked` warning and records its `cli_events` row.
- An interrupted or failed rebuild leaves readers with either the full old or the full new derived data (or a detectable in-progress state), never a silent partial set.
- Existing rebuild tests pass; add one covering concurrent writer during rebuild.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-29T15:29:47 - `85fc47a8-e1b6-45fa-ba9d-e5941d3c8ece.jsonl`

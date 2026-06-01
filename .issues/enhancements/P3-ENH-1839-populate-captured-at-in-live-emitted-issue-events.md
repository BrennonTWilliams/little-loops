---
id: ENH-1839
title: Populate captured_at in live-emitted issue events
type: ENH
priority: P3
status: open
captured_at: '2026-06-01T03:52:30Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- ENH-1711
parent: EPIC-1707
---

# ENH-1839: Populate captured_at in live-emitted issue events

## Summary

Fix `issue_lifecycle.py` event payloads and `SQLiteTransport.send()` to populate `captured_at` in live-emitted `issue_events` rows, which are currently always NULL. This eliminates ENH-1711's backfill dependency: the `issue_sessions` VIEW will work immediately after an issue is created, without requiring a manual `backfill` pass first.

## Motivation

ENH-1711 (Option A) creates an `issue_sessions` VIEW that joins `issue_events` to `message_events` via overlapping timestamps. The VIEW filters `WHERE ie.captured_at IS NOT NULL`, meaning it only returns results for issues whose `captured_at` was set by `_backfill_issues()`. Live-emitted rows (from `create_issue_from_failure`, `close_issue`, etc.) never include `captured_at` in their event payloads, so they are silently excluded. Users who work on an issue in a session immediately see zero rows in `ll-history sessions <ID>` until they run backfill.

The fix is narrow: `issue_lifecycle.py` already reads `captured_at` from issue frontmatter in several places; it just doesn't include it in the event dict it emits.

## Implementation Steps

1. In `scripts/little_loops/issue_lifecycle.py`, update each of the 6 emit sites to include `"captured_at"` in the event dict passed to `emit_issue_event()`. The value should be read from the issue's frontmatter `captured_at` field (already parsed in context at each site). Emit sites: `create_issue_from_failure`, `close_issue`, `complete_issue_lifecycle`, `defer_issue`, `undefer_issue`, `skip_issue`.
2. In `scripts/little_loops/session_store.py`, update `SQLiteTransport.send()` to read `event.get("captured_at")` and include it in the `INSERT INTO issue_events` tuple. The field already exists in the schema (added in v2); the transport just discards it today.
3. Verify `_backfill_issues()` is unaffected — it writes `captured_at` directly from the parsed frontmatter dict and does not go through `emit_issue_event()`.

## API / Interface Changes

No public API changes. `captured_at` is an existing column in `issue_events`; this change starts populating it from live events in addition to backfill.

## Acceptance Criteria

- After creating or transitioning an issue in a live session, `SELECT captured_at FROM issue_events WHERE issue_id = '<ID>'` returns a non-NULL value without running `ll-session backfill`.
- `ll-history sessions <ID>` (from ENH-1711) returns session rows immediately after working on the issue, without a prior backfill pass.
- Existing backfill tests in `scripts/tests/test_session_store.py` continue to pass unchanged.

## Session Log
- `/ll:capture-issue` - 2026-06-01T03:52:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43c6ff18-cbc3-4adc-b83d-de514a9863c0.jsonl`

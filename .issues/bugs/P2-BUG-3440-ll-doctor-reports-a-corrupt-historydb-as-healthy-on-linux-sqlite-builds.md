---
id: BUG-3440
type: BUG
title: ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3440: ll-doctor reports a corrupt history.db as healthy on Linux SQLite builds

## Summary

_history_db_data (cli/doctor.py ~451-459) probes readability with `SELECT 1`, a constant expression that does not force a page-1 header read on every SQLite build; on CI a 54-byte garbage file returns status=full instead of unsupported. Replace with `PRAGMA quick_check` or validate the 16-byte header magic before connecting, and add a regression test asserting both probes agree so the check cannot silently degrade again (A3).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]


## Session Log
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`

---
id: ENH-3746
title: Redact raw_line on remote raw_events push (session_store/lifecycle.py:777/840)
type: ENH
priority: P1
status: open
parent: ENH-3743
relates_to:
- ENH-3750
captured_at: "2026-10-05T00:00:00Z"
labels: [redaction, history-db, session-store, remote-push, security]
---

# ENH-3746: Redact raw_line on remote raw_events push (session_store/lifecycle.py:777/840)

## Summary

Second insert site for ENH-3743. The `_REMOTE_RAW_INSERT` path
(lifecycle.py:777 and :840) ships `raw_line` to a shared remote store
when one is configured (none is today, but the path exists and is the
canonical credential-leak surface if a remote store is ever enabled).
Redact at the source so the remote store never sees plaintext.

## Acceptance Criteria

- `_REMOTE_RAW_INSERT` calls `pii.redact_pii(raw_line)` before serializing
  to the remote.
- Same redactor purity property tests as ENH-3745.
- New integration test: stub a remote sink, ingest a session with a known
  credential in the log content, assert the payload shipped to the sink
  contains the redaction marker, not the original.
- Path is exercised in CI today via the local-only test path; ensure the
  remote branch tests pass too (extend the local lifecycle test fixture to
  exercise the remote code path with a stub).

## Out of Scope

- Local insert site (lifecycle.py:873) — separate issue ENH-3745.
- refresh_usage_source site (lifecycle.py:1581) — separate issue ENH-3747.
- Backfill of stored rows — separate issue ENH-3748.

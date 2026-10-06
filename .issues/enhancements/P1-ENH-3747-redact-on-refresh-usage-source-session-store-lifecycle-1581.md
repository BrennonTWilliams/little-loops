---
id: ENH-3747
title: Redact raw_line on refresh_usage_source insert (session_store/lifecycle.py:1581)
type: ENH
priority: P1
status: open
parent: ENH-3743
relates_to:
- ENH-3750
captured_at: "2026-10-05T00:00:00Z"
labels: [redaction, history-db, session-store, refresh-usage, security]
---

# ENH-3747: Redact raw_line on refresh_usage_source insert (session_store/lifecycle.py:1581)

## Summary

Third insert site for ENH-3743. `refresh_usage_source` re-reads an existing
file and inserts new raw_events rows. The path is independent of the
detect-then-insert path (ENH-3745) and the remote push (ENH-3746): it
walks rows it hasn't seen yet and persists them. Without redaction, a
file that was scanned and inserted under the ENH-3745 fix and later
edited to add a credential would still get re-inserted on refresh.

## Acceptance Criteria

- `refresh_usage_source` calls `pii.redact_pii(raw_line)` before each
  insert it issues.
- New test: pre-populate history.db with rows inserted by a non-redacting
  path, run refresh_usage_source on a file that has been edited to
  introduce a credential, assert the new raw_events rows carry the
  redacted content.
- Idempotency: re-running refresh on the same file is a no-op (existing
  behavior preserved).

## Out of Scope

- Local insert site (lifecycle.py:873) — separate issue ENH-3745.
- Remote push site (lifecycle.py:777/:840) — separate issue ENH-3746.
- Backfill of stored rows — separate issue ENH-3748.

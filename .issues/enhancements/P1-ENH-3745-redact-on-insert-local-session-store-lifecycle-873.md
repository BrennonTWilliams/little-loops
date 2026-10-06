---
id: ENH-3745
title: Redact raw_line on local raw_events insert (session_store/lifecycle.py:873)
type: ENH
priority: P1
status: open
parent: ENH-3743
captured_at: "2026-10-05T00:00:00Z"
labels: [redaction, history-db, session-store, security]
---

# ENH-3745: Redact raw_line on local raw_events insert (session_store/lifecycle.py:873)

## Summary

First of three insert sites for ENH-3743 (the promoted P0 redaction-on-write spec).
The local raw_events insert at session_store/lifecycle.py:873 must call
`pii.redact_pii()` on `raw_line` before persisting, so host log content
never reaches .ll/history.db with credentials intact.

## Acceptance Criteria

- `lifecycle.py:873` calls `pii.redact_pii(raw_line)` before insert.
- A property test exercises the redactor on a corpus of fixtures covering:
  provider API key prefixes, bearer tokens, credentialed URIs (postgres://,
  mysql://, mongodb://, redis://), high-entropy strings (>= 4.5 bits/char
  across 20+ chars), and known-benign inputs (low-entropy prose, code
  snippets, README excerpts).
- Redaction is pure (no I/O) so the redactor itself remains property-testable.
- `test_redaction_unit.py` asserts no preexisting keys are returned verbatim
  and that no benign input is over-redacted (no false positive).
- Integration test: write a fixture session to log files, run detect_local →
  run lifecycle insert path, assert raw_events.raw_line has no credential
  strings.
- Existing redactor consumers (`sft-corpus`, `cli/logs.py:1864`,
  `cli/loop/evidence.py:28`) keep their behavior unchanged.

## Out of Scope

- Remote push site (lifecycle.py:777/:840) — separate issue ENH-3746.
- refresh_usage_source site (lifecycle.py:1581) — separate issue ENH-3747.
- Backfill of stored rows — separate issue ENH-3748.
- Rule family additions (new patterns) — separate issue ENH-3749.

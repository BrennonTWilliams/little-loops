---
id: ENH-3748
title: One-time redaction backfill of raw_events.raw_line for stored rows
type: ENH
priority: P1
status: open
parent: ENH-3743
captured_at: "2026-10-05T00:00:00Z"
labels: [redaction, history-db, backfill, security]
---

# ENH-3748: One-time redaction backfill of raw_events.raw_line for stored rows

## Summary

Per the scope addition in ENH-3743 (backlog-audit 2026-10-05 §1),
the exposure is already live on existing spoke history.dbs:
spoke `c08c79b89` has 34,212 Claude Code rows with `thinking` blocks,
15,410 of them with non-empty plaintext reasoning. After the ENH-3745
insert-side fix lands, new writes are clean, but stored rows still carry
plaintext credentials until a backfill redacts them in place.

## Acceptance Criteria

- New CLI command (e.g. `ll-history redact-backfill` or a one-shot script)
  walks every row in `raw_events`, runs `pii.redact_pii(raw_line)`, and
  updates rows whose content changed. Idempotent: a second run is a
  no-op (verifies by re-running and asserting zero rows updated).
- Backfill reports: count of rows scanned, count of rows redacted, count
  by redaction-family (key prefix / bearer token / credentialed URI /
  entropy heuristic).
- Backfill is opt-in (not auto-run on migrate): invocation requires an
  explicit flag or subcommand so it can be scheduled (or skipped) per
  project. Auto-running on migrate would corrupt IR-cached exports whose
  raw_line is hashed.
- Property test: the backfill function is pure-of-side-effects-against-input
  (running on a copy produces identical row state to running on the source).
- Tested against a synthetic history.db with seeded plaintext credentials
  across all four families; asserts post-backfill rows are clean.

## Out of Scope

- Insert-side fixes — separate issues ENH-3745/3746/3747.
- Rule family additions — separate issue ENH-3749.

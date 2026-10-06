---
id: ENH-3750
title: Extend redact_pii() coverage to other PII-bearing history.db tables (cli_events, file_events, hook_events, etc.)
type: ENH
priority: P2
status: open
parent: ENH-3743
captured_at: "2026-10-05T00:00:00Z"
labels: [redaction, history-db, scope-deferral, security]
relates_to:
- ENH-3745
- ENH-3746
- ENH-3747
- ENH-3748
- ENH-3749
---

# ENH-3750: Extend redact_pii() coverage to other PII-bearing history.db tables

## Scope boundary (per Cooper's question on ENH-3743 handoff)

ENH-3743's promotion scope is deliberately raw_events-only — title and
"Promotion scope" clause in the spec enumerate only the three raw_events
insert sites (lifecycle.py:873/777/840/1581) plus the backfill of stored
raw_events rows. The spec body mentions "every path that lands in
history.db or an export" but the **promotion scope narrows it to
raw_events + backfill**, with "Exports beyond ingest are follow-on work,
not this unit."

This issue captures the rest of history.db's PII-bearing tables that
are deliberately deferred so the gap doesn't get lost. Per Cooper's
ENH-3743 review:

> raw_events is the source-of-truth for the JSONL-derived tables
> (tool_events, message_events, assistant_messages, skill_events,
> sessions), so redacting it + rebuild covers those. But the
> direct-write tables are explicitly outside raw_events' scope per
> ARCHITECTURE — cli_events, file_events, hook_events, usage_events
> (live writer), commit_events, issue_events, test_run_events.
> cli_events and file_events in particular can carry raw command lines
> and paths that may themselves contain PII.

## Acceptance Criteria

- Enumerate each direct-write table and characterize its PII risk:
  - `cli_events` — raw command lines from `cli/logs.py`/`cli/ctx_stats.py`
    writers; high risk (commands may embed credentials in argv/env).
  - `file_events` — file paths from write/edit tool traces; medium risk
    (paths may contain credentials, e.g. `~/.ssh/id_rsa`).
  - `hook_events` — hook payload captures; medium risk (provider
    metadata).
  - `usage_events` (live writer only) — non-rollout token usage; medium
    risk (token counts, model metadata).
  - `commit_events` — commit metadata; low risk (subjects + shas).
  - `issue_events` — issue lifecycle events; low risk (titles + statuses).
  - `test_run_events` — test result metadata; low risk.
- For each table identified as carrying PII, scope a redaction pass that
  reuses `pii.redact_pii()` (extended in ENH-3749).
- Backfill (analogue to ENH-3748) for each high/medium-risk table.
- Add a verification primitive to `ll-verify-docs` (or similar) that
  asserts every direct-write table's PII risk characterization has been
  reviewed within the last 90 days, so the deferred gap doesn't silently
  persist.

## Out of Scope

- The raw_events redaction itself — separate issues ENH-3745/3746/3747
  (insert) and ENH-3748 (backfill). This issue picks up where they
  leave off.

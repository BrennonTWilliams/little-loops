---
id: ENH-1621
type: ENH
priority: P4
status: open
discovered_date: 2026-05-22
discovered_by: manage-issue
blocked_by:
- FEAT-1112
relates_to:
- FEAT-1112
labels:
- enhancement
- carved-out
---

# ENH-1621: Migrate analyze-* skills to query the session DB

## Summary

Route `ll-history` (`main_history()`) and `ll-workflows` (`analyze_workflows()`)
to read from the unified session store (`.ll/session.db`, FEAT-1112) instead of
re-parsing scattered JSON/markdown source files on every invocation.

## Motivation

This is **Step 6 / Acceptance Criterion 3 of FEAT-1112**, carved out during
implementation (2026-05-22). FEAT-1112 shipped the session store, the
`SQLiteTransport` sink, the `ll-session` query CLI, and the `backfill()`
routine — but the two skill migrations were deferred because the schema as
specified does not carry enough fields to reconstruct what the two entry points
consume:

- `main_history()` → `scan_completed_issues()` returns rich `IssueInfo`
  objects (completed_date, type, priority, score_* fields, body excerpts).
  `issue_events` stores only (issue_id, transition, discovered_by, ts).
- `analyze_workflows()` consumes user **message text** + a pattern YAML;
  `tool_events` stores tool names/hashes, not message bodies.

Migrating without first widening the schema would mean rewriting the analysis
logic on SQL rows — a regression risk for two working CLIs.

## Expected Behavior

- Decide per target: widen the schema (new migration) to carry the needed
  columns, or store a JSON/body blob the query path can rehydrate.
- `main_history()` and `analyze_workflows()` query the DB when populated,
  falling back to source-file parsing when the DB is empty/absent (no
  regression for un-backfilled projects).
- `ll-session backfill` (or session-start ingestion) keeps the DB current.

## Acceptance Criteria

- Both entry points query `.ll/session.db` when it is populated.
- Behavior is unchanged for projects with no/empty DB (fallback path).
- A schema migration (version 2+) is added if new columns are required.
- Tests cover the DB-backed path and the fallback path for both CLIs.

## Impact

- **Priority**: P4 — completes FEAT-1112's analyze-migration criterion.
- **Effort**: Medium — schema extension + two CLI data-source swaps + tests.
- **Risk**: Medium — touches two shipped CLIs; fallback path mitigates.
- **Breaking Change**: No

## References

- Parent: FEAT-1112 (Unified Session Store) — see its plan at
  `thoughts/shared/plans/2026-05-22-FEAT-1112-management.md` (§Scope decision).

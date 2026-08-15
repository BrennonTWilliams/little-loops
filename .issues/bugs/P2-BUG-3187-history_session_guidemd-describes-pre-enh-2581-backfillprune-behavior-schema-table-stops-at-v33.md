---
id: BUG-3187
type: BUG
title: HISTORY_SESSION_GUIDE.md describes pre-ENH-2581 backfill/prune behavior, schema
  table stops at v33
priority: P2
status: done
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:36Z'
completed_at: '2026-08-15T19:31:32Z'
---

# BUG-3187: HISTORY_SESSION_GUIDE.md describes pre-ENH-2581 backfill/prune behavior, schema table stops at v33

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/guides/HISTORY_SESSION_GUIDE.md` describes pre-ENH-2581 backfill/prune behavior and its schema-migration table stops at v33 (schema version itself was already fixed to 40 directly in this audit; this issue is the remaining, non-mechanical rewrite work).

## Current Behavior

- Lines 58-91 (version table): stops at v33, omitting v31 (`harness_events`, ENH-2739), v34 (`context_pressure_events`, ENH-2507), v35 (`review_events`, ENH-2512), v36 (`issue_num` column + collision-merge, ENH-2771), v37 (`loop_runs.failure_terminal`, ENH-2814), v38 (`orchestration_runs.base_sha`/`base_dirty`, ENH-2866), v39 (`harness_events` content-hash columns, ENH-141), v40 (`prepatch_evidence` table, ENH-2997).
- Lines 97-124 ("What Gets Recorded" table): no rows for `harness_events`, `review_events`, `context_pressure_events`, or `prepatch_evidence`.
<!-- ll-prose-ok: raw_events is a SQL table (schema.py), not a def-site symbol; not a stale reference -->
- Lines 136-174 (Getting Started: Backfill): describes `backfill()` populating `tool_events`/`message_events`/`assistant_messages`/`sessions`/`user_corrections` and shows a JSON output example. Per ENH-2581, `backfill()` (`scripts/little_loops/session_store/lifecycle.py`) now only ingests into `raw_events`; those other tables require `ll-session rebuild` or `ll-session backfill --rebuild`. The actual CLI (`main_session()` in `scripts/little_loops/cli/session.py`) prints a single human-readable `logger.success(...)` line, not JSON.
- Lines 485-508 (Retention & Pruning): describes `prune()` deleting rows from `tool_events`, `cli_events`, `file_events`, `message_events` independently. Per ENH-2581, `prune()` now operates only on `raw_events` rows already marked `compacted=1`, and its `deleted` dict has a single key `{"raw_events": N}`. The doc never mentions the required `ll-session compact` prerequisite step.
- Line 204 (`ll-session search --kind`): omits `harness`, `verdict`, `context_pressure`, `review` from the enumerated `VALID_KINDS` list (schema.py) — `verdict` is even used elsewhere in the same doc at line 383.
- Line 242 (`ll-session export --tables`): omits `session_lifecycle_event`, `harness_event`, `prompt_opt_event`, `verdict_event`, `context_pressure_event`.
- Lines 552-556 (Configuration Reference table): omits `analytics.capture.hooks` and `analytics.capture.usage_events` (both default `true` in config-schema.json).

## Expected Behavior

Guide accurately reflects post-ENH-2581 backfill/prune semantics (raw_events-only, compact-then-prune flow), lists all schema migrations through v40, and documents all `--kind`/`--tables` enum values and config keys currently in code.

## Motivation

This is the canonical guide for `ll-session`/history tooling; stale backfill/prune docs will actively mislead someone trying to reclaim disk space (running `prune` without first running `compact` silently deletes nothing) or trying to find a specific table's events via `--kind`/`--tables`.

## Impact

- **Priority**: P2 — the backfill/prune section describes a materially different (and non-functional, if followed literally) workflow.
- **Effort**: Medium — requires reading `scripts/little_loops/session_store/lifecycle.py` and `scripts/little_loops/session_store/schema.py::_MIGRATIONS` closely and rewriting several sections, not just a text swap.
- **Risk**: None — doc-only change.


## Status

**Open** | Created: 2026-08-15 | Priority: P2

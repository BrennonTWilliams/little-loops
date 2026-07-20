---
id: BUG-2706
title: cli_event_context crashes every ll-* CLI when history.db is locked
type: BUG
priority: P2
status: done
discovered_date: '2026-07-20'
discovered_by: capture-issue
captured_at: '2026-07-20T01:21:48Z'
labels:
- session-store
- cli
- telemetry
- resilience
- EPIC-1707
decision_needed: false
completed_at: '2026-07-20T01:21:48Z'
---

# BUG-2706: cli_event_context crashes every ll-* CLI when history.db is locked

## Summary

`ll-issues show 2701` crashed with `sqlite3.OperationalError: database is locked`,
raised from the first statement inside `cli_event_context`
(`scripts/little_loops/session_store.py:1216`) — the analytics
`INSERT INTO cli_events` that wraps the *entire* body of `main_issues()`. The
command never reached its actual (read-only) work of rendering the issue.

`cli_event_context` wraps ~20+ `ll-*` entry points (`ll-issues`, `ll-sync`,
`ll-deps`, `ll-config`, `ll-session`, `ll-code`, `ll-harness`, `ll-queue`, the
`ll-verify-*` family, …). Because its enter `INSERT` and exit `UPDATE` ran
unguarded, any lock on the shared analytics DB killed the user's command before
it did any work — even purely read-only commands.

## Current Behavior

*(pre-fix)* When `.ll/history.db` is locked or unavailable, the analytics
`INSERT INTO cli_events` inside `cli_event_context` raises
`sqlite3.OperationalError: database is locked`, which propagates out of the
context manager and aborts the entire `ll-*` command with a traceback and no
useful output — regardless of whether the command itself needs the DB.

## Expected Behavior

Analytics is best-effort: a missing, locked, or otherwise unavailable
`history.db` must never block the wrapped command. The `cli_events` row is
skipped (with a logged warning) and the command runs to completion, exactly as
`skill_event_context` already behaves under the EPIC-1707 contract.

## Impact

Every `ll-*` CLI wrapped by `cli_event_context` (~20+ entry points, including
read-only ones like `ll-issues show`, `ll-config get`, `ll-deps`) became
unusable whenever the shared analytics DB was contended — which happens routinely
once `history.db` grows large and concurrent writers (hooks, loops, other CLIs)
hold the WAL write lock past the 5 s busy timeout. High blast radius for a
non-essential telemetry write.

## Root Cause

- **File**: `scripts/little_loops/session_store.py`
- **Anchor**: `cli_event_context()` — unguarded `conn = connect(...)` +
  `INSERT INTO cli_events` on enter and `UPDATE cli_events` in `finally`.
- **Cause**: `cli_event_context` violated the EPIC-1707 graceful-degradation
  contract that its sibling `skill_event_context` already follows
  (`session_store.py:1287` — "a missing or locked database never blocks the run …
  the row is skipped"). Analytics is best-effort everywhere else; this was the one
  place an optional bookkeeping write could crash the tool.
- **Contributing condition**: `.ll/history.db` had bloated to ~3.8 GB
  (4,037,713,920 bytes; ~985k pages × 4 KB — header verified valid, not corrupt).
  On a WAL DB that large, write/checkpoint locks routinely exceed the module's
  `_BUSY_TIMEOUT_MS = 5000` (5 s) window when any concurrent writer (SessionStart
  hooks, running `rn-*` loops, other `ll-*` startups) holds the lock, so the
  analytics `INSERT` intermittently hit `database is locked`.

## Steps to Reproduce

1. Have a large/contended `.ll/history.db` (or hold a write lock:
   `python -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); c.execute('BEGIN IMMEDIATE')"`).
2. Run `ll-issues show <ID>`.
3. Observe a traceback ending in `sqlite3.OperationalError: database is locked`
   from `cli_event_context`, with the command producing no output.

## Fix

Made `cli_event_context` fail-open, mirroring `skill_event_context`:

- Guarded the enter connect + `INSERT` + `commit` in `try/except sqlite3.Error`.
  On failure it logs a warning, closes/nulls the connection, and **still yields**
  so the wrapped command runs normally.
- The exit `UPDATE`/`commit`/`close` runs only when a row was actually inserted
  (`conn is not None and row_id is not None`), wrapped in its own
  `try/except sqlite3.Error` so a lock on exit can't mask a successful command.
- Preserved existing semantics for the happy path and for real errors raised by
  the wrapped body (`exit_code = 1; raise` still propagates command failures).

Scope was deliberately limited to the fail-open change; `_BUSY_TIMEOUT_MS` stayed
at 5000 (raising it only makes contended commands hang longer). Reclaiming the
3.8 GB DB remains a **manual** operational step (never auto-trigger `raw_events`
compact/prune):

```bash
ll-session compact --and-prune
ll-session recompress --batch 500
sqlite3 .ll/history.db 'VACUUM;'
```

## Files Changed

- `scripts/little_loops/session_store.py` — `cli_event_context` fail-open guards.
- `scripts/tests/test_session_store.py` — 2 new tests in `TestCliEventContext`
  (`test_cli_event_locked_db_does_not_crash_body`,
  `test_cli_event_locked_exit_update_does_not_mask_success`).

## Verification

- `python -m pytest scripts/tests/test_session_store.py -k cli_event -q` → 8 passed.
- Live: `ll-issues show 2701` succeeds against the real 3.8 GB DB **and** under a
  deliberately held `BEGIN IMMEDIATE` write lock (exit 0, issue rendered; only a
  stderr warning logged).
- `python -m mypy scripts/little_loops/session_store.py` and `ruff check` clean.
- Full suite (`python -m pytest scripts/tests/`): 15,520 passed, 38 skipped.

## Acceptance Criteria

- [x] A locked/absent `history.db` on enter no longer crashes `ll-*` commands; the
  `cli_events` row is skipped and the command body runs.
- [x] A lock on the exit `UPDATE` does not raise out of an otherwise-successful
  command.
- [x] Genuine errors from the wrapped command body still propagate with
  `exit_code = 1`.
- [x] Regression tests cover both the enter-lock and exit-lock paths.

## Status

**Done** — fixed and verified 2026-07-20. Fail-open guards landed in
`cli_event_context`; regression tests added; full suite green (15,520 passed).
The DB-shrink remediation (`ll-session compact --and-prune` → `recompress` →
`VACUUM`) is left as a manual operational follow-up per the never-auto-prune
policy.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-20T01:22:31 - `f755a306-3301-4aaf-b211-0cdaefb2de8e.jsonl`

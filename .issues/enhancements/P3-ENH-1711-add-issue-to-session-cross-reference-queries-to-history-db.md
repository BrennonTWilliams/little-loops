---
id: ENH-1711
title: Add issue-to-session cross-reference queries to history.db
type: ENH
priority: P3
status: done
captured_at: '2026-05-26T01:31:23Z'
completed_at: '2026-06-01T04:05:04Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
relates_to:
- ENH-1710
parent: EPIC-1707
blocked_by:
- ENH-1752
decision_needed: false
confidence_score: 98
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
labels:
- enhancement
- history-db
---

# ENH-1711: Add issue-to-session cross-reference queries to history.db

## Summary

Enable querying which sessions touched a given issue (and vice versa) by joining `issue_events` lifecycle timestamps with co-occurring `message_events` and `tool_events` session IDs in `history.db`.

## Current Behavior

`history.db` stores `issue_events` (with `issue_id` and lifecycle timestamps) and `message_events`/`tool_events` (with `session_id` and timestamps) in separate tables with no explicit join between them. There is no way to query which sessions worked on a given issue: `ll-history` has no `sessions` subcommand and `ll-session recent` accepts no `--issue` filter.

## Expected Behavior

- An `issue_sessions` VIEW joins `issue_events` to `message_events` via overlapping timestamps, making the implicit link explicit and queryable.
- `ll-history sessions <ID>` lists sessions that touched the issue, including their JSONL paths.
- `ll-session recent --issue <ID>` filters output to sessions that co-occurred with the given issue's active period.

## Motivation

`history.db` contains both `issue_events` (with `issue_id` and timestamps) and `message_events` / `tool_events` (with `session_id` and timestamps). The link between them is implicit: a session "worked on" an issue if its messages overlap the issue's active period. Making this join explicit and queryable closes the second gap in the issue → session → log drill-down chain.

Practically: `ll-history show ENH-1710` should be able to list the sessions that worked on that issue, and `ll-session recent --issue ENH-1710` should filter to those sessions.

## Implementation Steps

1. **Depends on ENH-1710** for the `sessions` table (session_id → JSONL path mapping).
2. Add a `CREATE VIEW issue_sessions AS ...` that joins `issue_events` to `message_events` via overlapping timestamps within the same `session_id`. A session "touches" an issue if any of its messages fall between `captured_at` and `completed_at` (or now, if open).
3. Alternatively, add a `session_id` column to `issue_events` populated when an `issue.*` event is emitted during a live session (the `SQLiteTransport` already has session context available via the event payload).
4. Add `ll-session recent --issue <ID>` filter flag.
5. Add `ll-history sessions <ID>` subcommand that lists sessions by issue ID with their JSONL paths.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A (VIEW approach) — lower risk, backfill-dependent:**

> **Selected:** Option A (VIEW approach) — perfect utility reuse (11/12 vs 6/12); Option B's INSERT OR IGNORE dedup constraint leaves session_id NULL for any previously-backfilled row, undermining its real-time accuracy advantage.

The `issue_events` table has `captured_at` and `completed_at` columns (added in v2), but **they are NULL for all live-emitted rows** — `issue_lifecycle.py` event payloads never include these fields; only `_backfill_issues()` populates them. The VIEW query requires `captured_at IS NOT NULL`, meaning it only works after a backfill pass. Add as v5 migration in `session_store.py:_MIGRATIONS`:

```sql
CREATE VIEW issue_sessions AS
SELECT ie.issue_id,
       me.session_id,
       s.jsonl_path,
       MIN(me.ts) AS first_message_ts,
       MAX(me.ts) AS last_message_ts
FROM issue_events ie
JOIN message_events me
  ON me.ts >= ie.captured_at
 AND (ie.completed_at IS NULL OR me.ts <= ie.completed_at)
LEFT JOIN sessions s ON s.session_id = me.session_id
WHERE ie.captured_at IS NOT NULL
GROUP BY ie.issue_id, me.session_id;
```

Also consider whether `SQLiteTransport.send()` should be updated to populate `captured_at` from `event.get("captured_at")` — it already extracts the field but `issue_lifecycle.py` emits it as `None`.

**Option B (Column approach) — real-time accuracy, higher complexity:**

- `ALTER TABLE issue_events ADD COLUMN session_id TEXT` as v5 migration
- The existing `UNIQUE INDEX idx_issue_events_dedup ON issue_events(issue_id, transition)` means `INSERT OR IGNORE` silently drops duplicate `(issue_id, transition)` pairs — only the *first* session to trigger a transition records its ID
- All 6 emit sites in `scripts/little_loops/issue_lifecycle.py` (`create_issue_from_failure`, `close_issue`, `complete_issue_lifecycle`, `defer_issue`, `undefer_issue`, `skip_issue`) must import `get_current_session_jsonl` from `session_log.py` and add `session_id` to their event dicts
- `SQLiteTransport.send()` must read `event.get("session_id")` and include it in the `INSERT` tuple (file: `scripts/little_loops/session_store.py`, function `SQLiteTransport.send()`)
- `_backfill_issues()` INSERT must add `session_id=None` to avoid column count mismatch

**CLI additions (both options):**

- `ll-session recent --issue <ID>`: add optional `--issue` arg to `recent_parser` in `scripts/little_loops/cli/session.py:main_session()`; filter `message_events` by session IDs returned from `issue_sessions` view or direct query
- `ll-history sessions <ID>`: add `sessions` subparser with positional `issue_id` to `scripts/little_loops/cli/history.py:main_history()`; follow the `path` subcommand pattern from `cli/session.py` (`connect()` + `try/finally conn.close()`)

**New query function (both options):**

Add `sessions_for_issue(issue_id, *, limit, db)` to `scripts/little_loops/history_reader.py` following the `related_issue_events()` pattern (`_connect_readonly` + `_row_to_dataclass`). Define a `SessionRef` dataclass with `session_id: str`, `jsonl_path: str | None`, `first_message_ts: str | None`, `last_message_ts: str | None`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-31.

**Selected**: Option A (VIEW approach)

**Reasoning**: Option A scores 11/12 vs Option B's 6/12. Every needed utility is directly reusable without modification — `_MIGRATIONS` append pattern (v1–v4 established), `_connect_readonly` (4 call sites), `_row_to_dataclass` (4 call sites), `related_issue_events()` as a 1:1 structural template, and `TestSchemaV4` 3-test class as a direct copy target. Option B's structural blocker is the `idx_issue_events_dedup` UNIQUE INDEX on `(issue_id, transition)` — `INSERT OR IGNORE` silently drops any duplicate `(issue_id, transition)` pair, meaning real-time `session_id` is never written for issues previously touched by backfill, leaving the column NULL for the majority of rows and negating Option B's real-time accuracy advantage.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (VIEW) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B (Column) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: `_connect_readonly` (4 call sites), `_row_to_dataclass` (4 call sites), `related_issue_events()` is a 1:1 structural template for `sessions_for_issue()`, `TestSchemaV4` 3-test pattern is directly copyable; no existing `CREATE VIEW` DDL but the migration runner handles it identically
- Option B: `get_current_session_jsonl` returns `Path | None` not a session_id string (translation step not yet written at any emit site); `INSERT OR IGNORE` with `idx_issue_events_dedup` on `(issue_id, transition)` silently discards real-time session_id for any backfilled row, confirmed by `TestBackfillDedup.test_double_backfill_produces_single_row`

## Scope Boundaries

- **In scope**: `issue_sessions` VIEW (Option A — selected by `/ll:decide-issue`), `SessionRef` dataclass, `sessions_for_issue()` query function, `ll-session recent --issue` filter, `ll-history sessions` subcommand, v5 schema migration, tests and docs.
- **Out of scope**: Option B (session_id column on `issue_events`) — rejected due to `INSERT OR IGNORE` dedup constraint silently dropping real-time session IDs for backfilled rows.
- **Out of scope**: Real-time session tracking without a prior `backfill` pass (VIEW requires `captured_at IS NOT NULL`).
- **Out of scope**: Cross-issue session analytics, session timeline visualizations, or aggregated statistics beyond the basic session-issue join.

## API / Interface Changes

- New `issue_sessions` view (or `session_id` column on `issue_events`).
- `ll-session recent --issue <ID>` flag.
- `ll-history sessions <ID>` subcommand.

## Acceptance Criteria

- `ll-history sessions ENH-1710` returns at least one session row after that issue has been worked on in a session where backfill was run.
- `ll-session recent --issue <ID>` filters output to matching sessions.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — add v5 migration entry to `_MIGRATIONS`; increment `SCHEMA_VERSION` to 5; update `SQLiteTransport.send()` (Option B only); update `_backfill_issues()` (Option B only)
- `scripts/little_loops/history_reader.py` — add `SessionRef` dataclass; add `sessions_for_issue()` query function using `_connect_readonly` + `_row_to_dataclass` pattern
- `scripts/little_loops/cli/session.py` — add `--issue <ID>` optional filter to `recent` subparser in `main_session()`
- `scripts/little_loops/cli/history.py` — add `sessions <ID>` subcommand with positional `issue_id` argument
- `scripts/little_loops/issue_lifecycle.py` — add `session_id` to all 6 event emit sites (Option B only); import `get_current_session_jsonl` from `session_log.py`

### Dependent Files (No Changes Required)
- `scripts/little_loops/transport.py:wire_transports()` — constructs `SQLiteTransport`; migration applies automatically via `ensure_db()`
- `scripts/little_loops/hooks/session_start.py` — calls `ensure_db()`; v5 migration runs on next session start
- `scripts/little_loops/cli_args.py:add_json_arg()` — shared `--json/-j` helper; reuse for new subcommands
- `scripts/little_loops/cli/output.py:print_json()` — reuse for JSON output in new subcommands

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — re-exports `SQLiteTransport`; v5 migration is transparent, no change needed
- `scripts/little_loops/issue_manager.py` — imports `SQLiteTransport`, calls `close_issue()` / `complete_issue_lifecycle()` from `issue_lifecycle`; Option B's additive event-dict change is backward-compatible, no signature change needed
- `scripts/little_loops/parallel/orchestrator.py` — calls `complete_issue_lifecycle()` and other `issue_lifecycle` functions; same backward-compat guarantee
- `scripts/little_loops/fsm/executor.py` — calls `complete_issue_lifecycle()` from `issue_lifecycle` and already imports from `session_log`; no change needed
- `scripts/little_loops/cli/sync.py` — calls `close_issue()` and `complete_issue_lifecycle()`; no change needed
- `scripts/little_loops/sync.py` — calls `complete_issue_lifecycle()`; no change needed
- `scripts/little_loops/cli/issues/skip.py` — calls issue_lifecycle functions; no change needed
- `scripts/little_loops/fsm/rate_limit_circuit.py` — calls `create_issue_from_failure()`; no change needed
- `scripts/little_loops/workflow_sequence/io.py` — imports `connect`, `_backfill_messages` from `session_store`; v5 migration auto-applies via `connect()` → `ensure_db()`
- `scripts/little_loops/hooks/post_tool_use.py` — imports `connect`, `ensure_db` from `session_store`; v5 migration transparent

### Similar Patterns
- `scripts/little_loops/session_store.py:_MIGRATIONS[3]` — v4 migration DDL (ENH-1710 `CREATE TABLE sessions`); model v5 after this
- `scripts/little_loops/session_store.py:_apply_migrations()` — migration runner; increment `SCHEMA_VERSION = 4` → `5`
- `scripts/little_loops/cli/session.py:main_session()` path subcommand — `connect()` + `try/finally conn.close()` + positional arg pattern to follow for `ll-history sessions`
- `scripts/little_loops/history_reader.py:related_issue_events()` — `_connect_readonly` + `_row_to_dataclass` + graceful empty-list return pattern for `sessions_for_issue()`

### Tests
- `scripts/tests/test_session_store.py` — add `TestSchemaV5` following `TestSchemaV4` pattern: `test_issue_sessions_view_exists_after_ensure_db`, `test_v4_db_upgrades_to_v5`
- `scripts/tests/test_history_reader.py` — add tests for `sessions_for_issue()` (empty result, match case, missing DB); also add entries to `TestMissingDatabase` and `TestEmptyTables` parallel to existing `related_issue_events` entries
- `scripts/tests/test_ll_session.py` — add to `TestArgumentParsing`: `test_recent_issue_arg_accepted`; add to `TestMainSession`: `test_recent_filtered_by_issue` (with `--json` variant)
- `scripts/tests/test_issue_history_cli.py` — add new class for `sessions <ID>` subcommand following `TestSummaryDbSource` integration pattern (`--config` flag, real DB, `capsys` output capture)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_lifecycle.py` — Option B only: add test verifying `session_id` key is present in the event dict emitted by each of the 6 emit sites (`create_issue_from_failure`, `close_issue`, `complete_issue_lifecycle`, `defer_issue`, `undefer_issue`, `skip_issue`); all other assertions in this file are backward-compatible with additive event-dict changes

### Documentation
- `docs/reference/CLI.md` — add `ll-session recent --issue` and `ll-history sessions` entries
- `.claude/CLAUDE.md` — update `ll-session` and `ll-history` CLI descriptions

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — documents `history_reader` module; add `SessionRef` dataclass and `sessions_for_issue()` function entries following the existing `related_issue_events()` row pattern

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. (Option B only) Verify all 7 callers of issue_lifecycle functions (`issue_manager.py`, `parallel/orchestrator.py`, `fsm/executor.py`, `cli/sync.py`, `sync.py`, `cli/issues/skip.py`, `fsm/rate_limit_circuit.py`) require no API changes — the `session_id` addition is to the event dict payload only; function signatures are unchanged.
7. Update `docs/reference/API.md` — add `SessionRef` dataclass row and `sessions_for_issue(issue_id, *, limit, db)` row to the `little_loops.history_reader` table section.
8. (Option B only) Add tests to `scripts/tests/test_issue_lifecycle.py` verifying `session_id` is present in events emitted by each of the 6 emit sites.

## Impact

- **Priority**: P3 — Closes the issue → session → log drill-down chain; useful for debugging and auditing but not blocking any core workflow.
- **Effort**: Medium — 4 files to modify plus 2 new CLI subcommands; all follow established `_MIGRATIONS` / `_connect_readonly` / `_row_to_dataclass` patterns.
- **Risk**: Low — Additive schema migration (CREATE VIEW only); no changes to existing tables, indexes, or function signatures.
- **Breaking Change**: No

## Labels

`enhancement`, `history-db`

## Status

---

open

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-31_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Open decision on core schema approach** — Option A (VIEW) vs Option B (session_id column) significantly changes implementation scope: Option B requires modifying 6 emit sites in `issue_lifecycle.py` and importing `get_current_session_jsonl` across all of them, while Option A is purely additive but backfill-dependent. This open decision should be resolved before starting.
- **Option A accuracy gap** — the VIEW approach only works after a `backfill` pass (captured_at is NULL for live-emitted rows); this limits real-time usefulness and may disappoint users who expect sessions to appear immediately after working on an issue.

## Resolution

**Approach**: Option A (VIEW-based join). Added `issue_sessions` VIEW as v5 migration in `session_store.py`. Added `SessionRef` dataclass and `sessions_for_issue()` to `history_reader.py`. Added `ll-session recent --issue <ID>` and `ll-history sessions <ID>` CLI commands. Full test coverage across 4 test files. Docs updated in `CLI.md`, `API.md`, and `CLAUDE.md`.

**Changes**: `session_store.py` (v5 migration + SCHEMA_VERSION=5), `history_reader.py` (SessionRef + sessions_for_issue), `cli/session.py` (recent --issue), `cli/history.py` (sessions subcommand), 4 test files, 3 doc files.

## Session Log
- `/ll:manage-issue` - 2026-06-01T04:05:04Z
- `/ll:ready-issue` - 2026-06-01T03:54:16 - `8c64760f-9ce2-4b5d-953e-dc65031d6230.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00 - `43c6ff18-cbc3-4adc-b83d-de514a9863c0.jsonl`
- `/ll:decide-issue` - 2026-06-01T03:49:15 - `766dd291-5212-4d63-9ba0-6d82517a09bb.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00 - `7f1a5019-7e22-4c0c-bcac-ca9b58602490.jsonl`
- `/ll:wire-issue` - 2026-06-01T03:42:04 - `d5468dc9-53e0-4323-afe2-7210b9f7fd12.jsonl`
- `/ll:refine-issue` - 2026-06-01T03:35:58 - `5e1c1f32-3582-4bb8-9a33-a4eac92518c2.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:40 - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`

---
id: BUG-2770
title: set-status writes a snapshot but no issue_event, silently breaking session
  lookup
type: BUG
priority: P2
status: done
discovered_by: capture-issue
discovered_date: 2026-07-24
captured_at: '2026-07-24T22:09:37Z'
completed_at: '2026-07-25T03:54:04Z'
labels:
- history
- session-store
- observability
relates_to:
- BUG-1882
- BUG-2769
decision_needed: false
parent: EPIC-2791
confidence_score: 98
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
---

# BUG-2770: `set-status` writes a snapshot but no `issue_event`, silently breaking session lookup

## Summary

No row has been written to `issue_events` since `FEAT-2711` on
2026-07-23T19:59. Every issue closed after that point has an `issue_snapshots`
row but no `issue_events` row. Because **both** branches of the
`issue_sessions` VIEW are rooted in `issue_events`, `ll-session recent --issue`
returns "No sessions found" for all of them, and `issue_effort()` returns
`None`, silently degrading every history-backed planning signal.

## Steps to Reproduce

1. `ll-issues set-status BUG-2757 done` (or let a loop close an issue).
2. `sqlite3 .ll/history.db "select * from issue_events where issue_id='BUG-2757'"`
   → **0 rows**.
3. `sqlite3 .ll/history.db "select * from issue_snapshots where issue_id='BUG-2757'"`
   → 1 row, correctly keyed.
4. `ll-session recent --issue BUG-2757` → `No sessions found for BUG-2757.`

## Current Behavior

Observed 2026-07-24 — every issue closed on 2026-07-24 fails, everything at or
before the last `issue_events` row resolves:

| Issue | `issue_snapshots` | `issue_events` | `ll-session recent --issue` |
|-------|:---:|:---:|---|
| `BUG-2755`…`BUG-2767` | ✅ | ❌ | No sessions found |
| `FEAT-2711` (last event row) | ✅ | ✅ | resolves to JSONL path |
| `BUG-2640` | ✅ | ✅ | resolves to JSONL path |

`issue_events` currently holds 1931 rows, of which only **8** have a non-NULL
`session_id` — so even historically, the authoritative-join branch of the view
is carrying almost nothing and most resolution depends on the deprecated
timestamp-overlap fallback.

## Expected Behavior

Closing an issue by any supported path records an `issue_events` row (with
`session_id` populated per ENH-2462) in addition to the content snapshot, so
`issue_sessions` can link the issue to the sessions that worked on it.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/set_status.py`
- **Anchor**: `cmd_set_status` (the post-write side-effect block, ~line 131-139)
- **Cause**: the transition side-effect calls **only**
  `record_issue_snapshot(db_path, args.issue_id, args.status, str(path))`. It
  never publishes an event to the EventBus. Meanwhile `issue_events` rows are
  written exclusively by the `elif event_type.startswith("issue."):` branch of
  `SQLiteTransport` (`session_store.py`, ~line 2949), which only fires for
  bus events whose type is prefixed `issue.`. `set-status` therefore produces a
  snapshot-shaped half-record by construction.

Note `StateManager._emit("state.issue_completed", ...)` (`state.py:201`) does
**not** satisfy that branch either — its type is prefixed `state.`, not
`issue.`, so it lands in no issue table.

The 2026-07-23 cutoff most likely marks the point where the dominant
issue-closing path became `set-status` (directly or via loops) rather than the
bus-emitting `ll-auto` path — worth confirming by bisecting that day's commits
before fixing.

## Motivation

This is a silent, compounding loss of the exact data the history layer exists to
provide. Sessions are the join key between an issue and everything learned while
working it — `ll-history-context`, `issue_effort()`, go/no-go correction
penalties, and the planning-skill history reads all degrade to "no data" without
raising an error, which reads identically to "this issue was easy." EPIC-1707
built this layer specifically to feed planning; it is currently accumulating
issues it cannot account for.

## Proposed Solution

1. Confirm the cutover by bisecting commits from 2026-07-23 around the
   issue-closing path.
2. Have `set_status.py` emit an `issue.<transition>` bus event alongside the
   snapshot call, carrying `issue_id`, `session_id`, `issue_type`, `priority`,
   `captured_at`, and `completed_at` from the frontmatter it has already parsed
   — the payload `SQLiteTransport` already expects.
3. Alternatively (or additionally), give `record_issue_snapshot()` a sibling
   `record_issue_event()` and call both from the one place that owns the
   transition, so the two tables cannot diverge again.
4. Add a regression test asserting that a `set-status` transition produces a row
   in **both** `issue_events` and `issue_snapshots`, with `session_id` populated.
5. Consider a `ll-verify-*` gate (or a check in the existing suite) asserting the
   two tables do not diverge by more than a small margin, so a future
   half-wired path fails loudly.
6. Backfill the gap: `_backfill_issues()` reads `status`/`captured_at`/
   `completed_at` from frontmatter and can reconstruct the missing rows for
   already-closed issues, though it cannot recover `session_id`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Decision precedent contradicts Proposed-Solution Option 2 (bus emit).**
  `.ll/decisions.d/cc8c106b-f941-4273-aa9c-eac33a81e5c0.json` (ENH-2466,
  2026-07-19) already evaluated and **rejected** "Approach C (event-bus
  emit)" for this exact call site, in favor of the direct-call recorder
  idiom (`record_issue_snapshot`/`record_commit_event`/
  `record_test_run_event`/`record_skill_event`), citing: EventBus is scoped
  to FSM-loop/issue-lifecycle only, has a hardcoded 2-family
  `SQLiteTransport` dispatch, and a bus emit would need new DES-variant
  registration. The `set_status.py` comment ("Decision 2: Option C — direct
  call... without EventBus") is citing this same decision. **This means
  Option 2 in Proposed Solution below should be dropped**; Option 3 (a
  `record_issue_event()` sibling, direct-called exactly like
  `record_issue_snapshot()`) is the one consistent with established
  precedent, not an "alternatively."
- **No `record_issue_event()` exists yet anywhere in the codebase.**
  `issue_events` rows are currently written from exactly one place:
  the inline `INSERT OR IGNORE INTO issue_events(...)` inside
  `SQLiteTransport.send()`'s `elif event_type.startswith("issue."):` branch
  (`scripts/little_loops/session_store.py:2957-2973`), plus the one-time
  backfill seeding routine (`session_store.py:~3073-3107`). A new
  `record_issue_event(db_path, issue_id, transition, *, session_id=None,
  issue_type=None, priority=None, discovered_by=None, captured_at=None,
  completed_at=None)` should extract that same `INSERT OR IGNORE` shape,
  mirroring `record_issue_snapshot()`'s signature style
  (`session_store.py:1359-1409`, `db_path: Path | str` first arg).
- **Transition mapping to reuse**: `_ISSUE_TRANSITION_MAP` /
  `_derive_transition()` (`session_store.py:2874-2886`) maps event-type
  strings like `"issue.completed"` → `"done"`. `set_status.py` already has
  the target status string directly (`args.status`) so `record_issue_event`
  can take the transition as a plain string — no need to round-trip through
  a synthetic `"issue.<type>"` string.
- **`_index()` FTS side effect**: the `issue.` branch also calls
  `_index(conn, content=f"{issue_id} {issue_type}", kind="issue",
  ref=issue_id, ...)` for search indexing — the new `record_issue_event()`
  should replicate this so `ll-session search`/FTS parity with the
  bus-emitted path is preserved.
- **`session_id` availability at the call site**: `set_status.py` does not
  currently import a session-id helper. `issue_lifecycle.py`'s
  `_session_id_or_none()` (lines 33-38, wraps
  `little_loops.session_log.get_current_session_id()` in try/except) is the
  established best-effort pattern to reuse rather than hand-rolling a new
  one.
- **`state.py:201`/`StateManager.mark_completed`** confirmed to emit
  `"state.issue_completed"` (not `"issue.completed"`) via `_emit`
  (`state.py:104-107`) — this event type matches neither the `issue.`
  branch nor `_LOOP_EVENT_TYPES` in `SQLiteTransport.send()`, so it is
  silently dropped (falls to the trailing `else: return`,
  `session_store.py:2991-2992`). Confirms the issue text's claim; not a
  second path to fix, just a dead end to leave alone.
- **Test pattern to model the regression test after**: 
  `scripts/tests/test_session_store.py`, class `TestSQLiteTransportIssueEvents`
  (`test_records_issue_completed_event`, line ~934) shows the
  send-row-assert shape (`transport.send({...}); rows = recent(db,
  kind="issue")`). A direct-call equivalent for `record_issue_event()`
  should follow the `record_issue_snapshot()` roundtrip tests at
  `test_session_store.py:~3964`
  (`test_record_issue_snapshot_roundtrip`,
  `test_record_issue_snapshot_idempotent` — `INSERT OR IGNORE` idempotency
  already has a precedent test to copy).
- **Primary set-status test file**: `scripts/tests/test_set_status_cli.py`
  (not `test_issues_set_status.py` as originally guessed) is the actual
  existing test file for `cmd_set_status`.
- **Parent epic**: this issue's `parent: EPIC-2791` is
  `.issues/epics/P2-EPIC-2791-history-event-bus-and-issue-id-keying.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/set_status.py` — the transition side-effect block (`cmd_set_status`, lines 131-139)
- `scripts/little_loops/session_store.py` — add `record_issue_event()` sibling to `record_issue_snapshot()` (line 1359), modeled on the inline `INSERT OR IGNORE` in `SQLiteTransport.send()` (lines 2957-2973)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store.py` — also add `"record_issue_event"` to the `__all__` export list (line ~96, alongside `"record_issue_snapshot"`) and to the module docstring's `Public API:` block (lines 16-46), following the one-line convention used by every recorder added since ENH-2458 (`record_X(db,...): write one row to Y + search_index (ENH-NNNN)`) — otherwise it won't be importable the same way `set_status.py` imports `record_issue_snapshot` today. No new DES variant or `_KIND_TABLE`/schema migration is needed: this is a direct-call recorder (not a bus emission), reuses the existing `issue_events` table and `"issue"` kind, and the existing `idx_issue_events_dedup` unique index on `(issue_id, transition)` already provides idempotency. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` — `sessions_for_issue()`, `issue_effort()`
  (both query the `issue_sessions` VIEW)
- `scripts/little_loops/cli/session.py` — `recent --issue` handler
- `ll-history-context` — per-issue effort and correction reads
- `scripts/little_loops/issue_lifecycle.py` — `_session_id_or_none()` (lines 33-38), the session-id helper to reuse rather than reimplement

### Tests
- `scripts/tests/test_session_store.py` — `TestSQLiteTransportIssueEvents` (line ~934), `record_issue_snapshot` roundtrip tests (line ~3964) to model a `record_issue_event()` test suite after

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store.py` — add `test_record_issue_event_roundtrip` and `test_record_issue_event_idempotent`, mirroring `test_record_issue_snapshot_roundtrip`/`test_record_issue_snapshot_idempotent` (~line 3975/4004): raw `SELECT` against `issue_events` after the call, then a duplicate call asserting `COUNT(*) == 1` via the existing `idx_issue_events_dedup` unique index on `(issue_id, transition)`. Also worth a `recent(db, kind="issue")` read-side check per `TestSQLiteTransportIssueEvents::test_records_issue_completed_event` (line 934), since that's the consumer-facing read path. [Agent 3 finding]
- `scripts/tests/test_set_status_cli.py` — the actual existing test file for `cmd_set_status` (corrects the issue's original guess of `test_issues_set_status.py`); none of its current 25 tests inspect `.ll/history.db`, so add a new end-to-end test that runs `ll-issues set-status` and asserts a row now exists in `issue_events` (not just `issue_snapshots`) — closes the actual gap this issue is about. No existing test in this file mocks or asserts call count on `record_issue_snapshot`, so adding the new call is confirmed non-breaking. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` — the producer/channel narrative (~line 148 "Issues directory" section) and schema-version table currently describe only two `issue_events` write channels (backfill + EventBus-emitted `issue.*` via `SQLiteTransport`); update to document the new third channel (direct-call `record_issue_event()` from `set_status.py`) [Agent 2 finding]
- `docs/reference/CLI.md` — the `ll-issues set-status` / `sst` section (~line 1648) documents flags but not any event-recording side effect; consider noting that `set-status` now writes an `issue_events` row alongside the snapshot [Agent 2 finding]

## Impact

- **Priority**: P2 — silent and ongoing; every issue closed since 2026-07-23 is
  unattributable to a session, and the failure mode is indistinguishable from
  "no history exists."
- **Effort**: Small to Medium — the emit is small; confirming the cutover and
  backfilling the gap is the larger half.
- **Risk**: Low — additive write on a path that already touches the DB.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | history-db producer/consumer flow (ENH-1753) |
| `docs/reference/API.md#little_loopssession_store` | `record_issue_snapshot`, `SQLiteTransport` |

## Notes

Distinct from the resolved `BUG-1882` (empty `sessions` table — that table now
holds 7289 rows) and from `BUG-2769` (malformed frontmatter `id` mis-keying
rows). `BUG-2769` explicitly scoped this gap out; this issue is that scope.

## Session Log
- `/ll:manage-issue` (bug fix) - 2026-07-25T03:53:39Z - `007133a9-26bd-44cb-a425-4db030220844.jsonl`
- `/ll:confidence-check` - 2026-07-24T00:00:00Z - `a9a36f84-e993-4be5-88ae-cc84a927138f.jsonl`
- `/ll:wire-issue` - 2026-07-25T03:40:56 - `0b295482-379f-4a24-92bb-a29fc380f943.jsonl`
- `/ll:refine-issue` - 2026-07-25T03:32:28 - `5f991db7-9059-434c-8950-3e84c456c36b.jsonl`
- `/ll:capture-issue` - 2026-07-24T22:09:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65a565ab-fdff-4457-9611-217b87d7512a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2

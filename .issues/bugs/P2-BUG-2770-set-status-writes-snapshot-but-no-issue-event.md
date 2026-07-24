---
id: BUG-2770
title: set-status writes a snapshot but no issue_event, silently breaking session lookup
type: BUG
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-07-24
captured_at: '2026-07-24T22:09:37Z'
labels:
- history
- session-store
- observability
relates_to:
- BUG-1882
- BUG-2769
decision_needed: false
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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/set_status.py` — the transition side-effect block
- `scripts/little_loops/session_store.py` — possible `record_issue_event()` sibling

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` — `sessions_for_issue()`, `issue_effort()`
  (both query the `issue_sessions` VIEW)
- `scripts/little_loops/cli/session.py` — `recent --issue` handler
- `ll-history-context` — per-issue effort and correction reads

### Tests
- `scripts/tests/test_session_store.py`
- `scripts/tests/test_issues_set_status.py` (or equivalent)

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
- `/ll:capture-issue` - 2026-07-24T22:09:37Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65a565ab-fdff-4457-9611-217b87d7512a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2

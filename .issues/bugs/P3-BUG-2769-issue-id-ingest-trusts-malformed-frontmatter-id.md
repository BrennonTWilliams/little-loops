---
id: BUG-2769
title: Issue-id ingest trusts malformed frontmatter id, silently mis-keying history rows
type: BUG
priority: P3
status: open
discovered_by: manual
discovered_date: 2026-07-24
captured_at: '2026-07-24T22:10:00Z'
labels:
- history
- session-store
- data-integrity
decision_needed: false
parent: EPIC-2791
---

# BUG-2769: Issue-id ingest trusts malformed frontmatter `id`, silently mis-keying history rows

## Summary

Every `.ll/history.db` ingest path takes the issue file's frontmatter `id:` value
verbatim, and only falls back to parsing `TYPE-NNN` out of the **filename** when
`id` is entirely absent. An `id` that is present but malformed — e.g. `id: 2756`
or `id: "1294"` instead of `id: BUG-2756` — sails straight through, and the row
lands under a key no query will ever match. The issue then appears "missing"
from history while actually being present under a bare-numeric key.

## Steps to Reproduce

1. Write an issue file whose frontmatter has `id: 2756` (bare number) but whose
   filename is `P2-BUG-2756-....md`.
2. Transition it: `ll-issues set-status BUG-2756 done` (or let a loop close it).
3. Query history: `sqlite3 .ll/history.db "select * from issue_snapshots where
   issue_id='BUG-2756'"` → **0 rows**.
4. `sqlite3 .ll/history.db "select issue_id from issue_snapshots where issue_id
   not like '%-%'"` → `2756`.

## Current Behavior

Four ingest sites read the id and none validate its shape:

- `scripts/little_loops/session_store.py:3090` (`_backfill_issues`) — `fm.get("id")`,
  `_FILENAME_TYPE_RE` fallback only when falsy.
- `scripts/little_loops/session_store.py:3152` (`_backfill_snapshots`) — same pattern.
- `scripts/little_loops/session_store.py:1383` (`record_issue_snapshot`) — takes
  `issue_id` from its caller with no normalization.
- `scripts/little_loops/session_store.py:2989` (`SQLiteTransport` issue-event
  branch) — passes the event payload's `issue_id` through to both `issue_events`
  and `record_issue_snapshot`.

`_index()` is called with the same unvalidated value as its `ref`, so the FTS5
`search_index` rows are mis-keyed in lockstep.

Observed corruption in the live DB before repair (2026-07-24):

| Table | Key written | Should have been |
|-------|-------------|------------------|
| `issue_snapshots` | `2756` | `BUG-2756` |
| `issue_events` | `1182` | `BUG-1182` |
| `issue_events` | `1294` | `BUG-1294` |
| `issue_events` | `1548` | `ENH-1548` |

Four issue files carried the defect (`BUG-1182`, `BUG-1294`, `BUG-2756`,
`ENH-1548`); `BUG-1294` used the quoted form `id: "1294"`, so a naive
`^id: [0-9]+$` grep misses that variant.

## Expected Behavior

An id that disagrees with the filename's `TYPE-NNN` is normalized to the
filename-derived canonical form before any write, so `issue_events`,
`issue_snapshots`, and `search_index.ref` are always keyed `TYPE-NNN`. A
malformed `id` should additionally be surfaced by `ll-issues format-check`
rather than silently repaired forever.

## Root Cause

- **File**: `scripts/little_loops/session_store.py`
- **Anchors**: `_backfill_issues`, `_backfill_snapshots`, `record_issue_snapshot`,
  `SQLiteTransport._write` (issue branch)
- **Cause**: `_FILENAME_TYPE_RE` (`session_store.py:3045`) is used only as an
  *absence* fallback, never as a *validator*. The frontmatter value is trusted
  whenever it is truthy, and `INSERT OR IGNORE` on the
  `(issue_id, transition)` dedup index means the bad row inserts cleanly with
  no constraint to trip.

## Proposed Solution

1. Add a `normalize_issue_id(raw: object, file_path: str | Path | None) -> str | None`
   helper in `session_store.py` (near `_FILENAME_TYPE_RE`): if `raw` already
   matches `^(BUG|ENH|FEAT|EPIC)-\d+$`, return it; else derive from the filename;
   else, if `raw` is a bare integer/numeric string and the filename gives a type,
   splice them; else fall back to the filename match, then `None`.
2. Route all four ingest sites through it, including the `ref=` passed to
   `_index()`.
3. Log at WARN when normalization changes the value, so the underlying file
   defect is visible rather than papered over.
4. Add a check to `ll-issues format-check` that flags frontmatter `id` not
   matching `TYPE-NNN` or disagreeing with the filename.
5. Tests: `tmp_path` issue file with `id: 2756` / `id: "1294"` / absent `id` /
   correct `id`, each asserted to produce a `TYPE-NNN` key in both
   `issue_snapshots` and `search_index`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — the four ingest sites + new helper
- `scripts/little_loops/cli/issues/format_check.py` — new frontmatter-id check

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/set_status.py:134-137` — passes
  `args.issue_id` straight to `record_issue_snapshot`
- `scripts/little_loops/observability/schema.py:504` — documents
  `record_issue_snapshot` as an `issue_snapshots` writer

### Tests
- `scripts/tests/test_session_store.py` — backfill and snapshot round-trips
- `scripts/tests/test_issues_format_check.py` (or equivalent) — new id check

## Impact

- **Priority**: P3 — silent, low-frequency history-data loss. No user-visible
  runtime failure; the issue simply vanishes from `ll-session` / `ll-history`
  queries and from any FTS lookup by id.
- **Effort**: Small — one helper, four call sites, one lint check.
- **Risk**: Low — normalization is strictly narrowing toward the canonical form.
- **Breaking Change**: No

## Notes

The four affected files' frontmatter and the corresponding DB rows were repaired
by hand on 2026-07-24 (`UPDATE issue_snapshots/issue_events/search_index` to the
canonical `TYPE-NNN` keys; verified 0 remaining bare-numeric keys and
`INSERT INTO search_index VALUES('integrity-check')` clean). This issue covers
preventing recurrence, not the one-time cleanup.

Separately observed while investigating and **not** covered here: `issue_events`
has recorded nothing since `FEAT-2711` on 2026-07-23, while `issue_snapshots`
kept receiving rows through 2026-07-24 (`BUG-2755`, `-2757`…`-2767`). That is an
independent gap in the event-write path and may warrant its own issue.

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3

---
id: BUG-3236
type: BUG
title: 'issue_sessions view drift: issue_num absent on already-migrated databases,
  silently emptying session and effort readers'
priority: P1
status: open
discovered_by: feat-3183-pre-implementation-review
discovered_date: '2026-08-17'
labels:
- history-db
- session-store
- silent-failure
relates_to:
- FEAT-3183
- ENH-2771
testable: true
---

# BUG-3236: `issue_sessions` view drift leaves `issue_num` absent on migrated databases

## Summary

On this repo's `.ll/history.db` — reporting `schema_version = 41` — the `issue_sessions`
view is the **pre-v36** definition and has no `issue_num` column. Every reader that
queries `issue_sessions WHERE issue_num = ?` raises
`sqlite3.OperationalError: no such column: issue_num`, and every one of them catches
`sqlite3.Error` and returns an empty result. The failure is therefore **silent**:
`ll-history sessions <ID>` prints nothing, `issue_effort()` returns `None`, and
`recent_issue_velocity()` returns `[]` — none of which is distinguishable from
"this issue genuinely has no recorded sessions."

## Steps to Reproduce

Requires a database that crossed schema v36 before the current code — a freshly created
one will **not** reproduce this. This checkout's `.ll/history.db` is one such database.

```bash
python - <<'PY'
import sqlite3
c = sqlite3.connect('.ll/history.db')
print('version:', c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
print('cols:', [r[1] for r in c.execute('PRAGMA table_info(issue_sessions)')])
PY
# -> version: 41
# -> cols: ['issue_id', 'session_id', 'jsonl_path', 'first_message_ts', 'last_message_ts']

ll-history sessions ENH-3195
# -> logs "sqlite3.OperationalError: no such column: issue_num", prints no rows
```

To construct one from scratch: apply migrations 0–34, stamp
`meta.schema_version = 41` directly, then run any affected reader.

## Current Behavior

Verified against this checkout's `.ll/history.db`:

```
meta.schema_version                    41
PRAGMA table_info(issue_sessions)      issue_id, session_id, jsonl_path,
                                       first_message_ts, last_message_ts
                                       (no issue_num)
issue_events.issue_num                 present
idx_issue_events_dedup                 ON issue_events(issue_num, transition)  -- v36 form
legacy_issue_sessions_ts_overlap       present
```

So migration 36 (`schema.py` migration index 35, ENH-2771) applied its `ALTER TABLE`
and index statements but its final two statements — `DROP VIEW IF EXISTS
issue_sessions` / `CREATE VIEW issue_sessions ...` — are not reflected in
`sqlite_master`. The live view is the v16 (ENH-2462) definition.

Reproduced failures against that database:

```python
sessions_for_issue("ENH-3195", db=".ll/history.db")   # -> []   (logs OperationalError)
issue_effort("ENH-3195",       db=".ll/history.db")   # -> None (logs OperationalError)
recent_issue_velocity(         db=".ll/history.db")   # -> []   (logs OperationalError)
```

```
$ ll-history sessions ENH-3195
history_reader: sessions_for_issue query failed
sqlite3.OperationalError: no such column: issue_num
(no rows)
```

### Affected call sites

| Site | Behavior on drift |
|---|---|
| `history_reader.py:2100` `sessions_for_issue()` | returns `[]`, warns |
| `history_reader.py:2130` `issue_effort()` | returns `None`, warns |
| `history_reader.py:2178` `recent_issue_velocity()` | returns `[]` (calls `issue_effort` per row) |
| `history_reader.py:2218` issue-outcome join | affected by the same view |
| `history_reader.py:2576` summary-node join | joins on `session_id` only — unaffected |
| `cli/history.py:406` `ll-history sessions` | prints nothing |
| `cli/session.py:469,503` session filtering by issue | empty filter result |
| `cli/history_context.py:263` effort context | no effort data |

## Root Cause

**Undetermined, and the fix does not depend on it.** Two things were ruled out:

- **A fresh database is correct.** `ensure_db()` on a new path produces
  `issue_sessions` with `issue_num`. (Verified.)
- **The current upgrade path is correct.** Hand-applying migrations 0–34, stamping
  `schema_version = 35`, then calling `ensure_db()` produces the v36 view with
  `issue_num`. (Verified.) `_split_sql_statements(_MIGRATIONS[35])` yields all 14
  statements including the `DROP VIEW` / `CREATE VIEW` pair, and `_apply_migrations()`
  runs the whole migration inside one `BEGIN IMMEDIATE` with `ROLLBACK` on any
  exception — so a partial apply cannot happen under today's code.

Candidate explanations (not distinguished): the database crossed v36 under a code
revision whose migration list differed at that index, or a migration was applied by a
process that did not run the view statements. Git history shows the view redefinition
present in `6a402cf8` (ENH-2771), the same commit that bumped `SCHEMA_VERSION` to 36.

**The load-bearing fact is the one that is certain: whatever produced the drift, the
current code can never repair it.** `_apply_migrations()` short-circuits on
`_current_version(conn) >= len(_MIGRATIONS)` (`schema.py:1065`), so a database whose
recorded version is current is never re-examined, regardless of whether its structure
matches. There is no structural verification anywhere and no repair path.

## Expected Behavior

1. A database at `schema_version = 41` has an `issue_sessions` view with `issue_num`.
2. A structural mismatch between recorded version and actual schema is detected and
   repaired, or at minimum reported — not silently converted into empty results.
3. A query failure inside a history reader is distinguishable by the caller from a
   genuine empty result.

## Fix

**1. Append a v42 migration that rebuilds the view idempotently.** Views are cheap to
`DROP` / `CREATE`, so re-issuing the v36 view definition is safe on both drifted and
correct databases. This must be a *new appended migration* — editing migration 36 in
place will not re-run on any database that has already passed it, which is precisely
the set that needs the repair.

**2. Do not let the readers keep swallowing this.** The `except sqlite3.Error: return
[]` pattern is correct for a missing database but wrong for a malformed query against a
present one. At minimum, log at `error` rather than `warning` when the database exists
and the view is present but the query failed. Consider a sentinel return or an explicit
`raise` behind a strict flag so callers can tell "no sessions" from "query broken."

**3. Add a structural assertion to the test suite.** A test that, for the current
`SCHEMA_VERSION`, asserts every view's column set matches its definition would have
caught this. The cheap version: assert `issue_num` is in
`PRAGMA table_info(issue_sessions)` after `ensure_db()` on both a fresh database and one
stamped at each prior version.

**4. Consider a lightweight structural check in `ensure_db()`** — the fast path already
returns without taking the write lock when the version is current; a single
`PRAGMA table_info` on one sentinel view would keep that path cheap while making drift
self-healing rather than permanent. Weigh against startup cost; option 1 alone fixes the
known instance.

## Program Design

No new public types. The change is one appended migration plus a test helper.

### Signatures

- `_stamp_version(conn, version) -> None` — test helper; writes `meta.schema_version`
  directly, making drift constructible in a test.
- `test_issue_sessions_view_has_issue_num_on_fresh_db() -> None` — fresh-database assertion.
- `test_issue_sessions_view_repaired_on_drifted_db() -> None` — the regression gate.

### Files

**`scripts/little_loops/session_store/schema.py`**

- `SCHEMA_VERSION = 42` — bumped.
- `_MIGRATIONS[41]` — a new entry containing exactly `DROP VIEW IF EXISTS issue_sessions;`
  followed by the v36 `CREATE VIEW issue_sessions AS ...` body, copied verbatim from
  `_MIGRATIONS[35]` (`schema.py:888-908`). Deliberately duplicated rather than factored
  into a shared constant: migration entries are historical records and must not change
  when the view definition next evolves. A comment on the entry states this and cites
  BUG-3236.

**`scripts/tests/test_session_store_schema.py`**

- `_stamp_version(conn: sqlite3.Connection, version: int) -> None` — writes `meta.schema_version`
  directly; the helper that makes drift constructible in a test.
- `test_issue_sessions_view_has_issue_num_on_fresh_db() -> None` — `ensure_db()` on a new
  path, assert `issue_num` in `PRAGMA table_info(issue_sessions)`.
- `test_issue_sessions_view_repaired_on_drifted_db() -> None` — build a database with the
  pre-v36 view, stamp it to the pre-fix current version, call `ensure_db()`, assert the
  column appears. This is the regression gate.

If item 2 (reader error surfacing) is taken in the same change, it touches
`history_reader.py:2107` and `:2136` only — log level and message, no signature change.

### Call Path

1. `ensure_db()` — `scripts/little_loops/session_store/schema.py:1088`; the entry point every
   `ll-*` startup path calls.
2. `_apply_migrations()` — `scripts/little_loops/session_store/schema.py:1050`; short-circuits
   on `_current_version(conn) >= len(_MIGRATIONS)`, which is why a drifted database at the
   current version is never re-examined. Bumping `SCHEMA_VERSION` to 42 is what makes this
   check fall through again on already-migrated databases.
3. `_current_version()` — `scripts/little_loops/session_store/schema.py:1033`; reads
   `meta.schema_version`, the value that is correct while the structure is not.
4. `_split_sql_statements()` — `scripts/little_loops/session_store/schema.py:1020`; splits the
   new migration into its `DROP VIEW` / `CREATE VIEW` pair, each executed via `conn.execute()`
   inside the existing `BEGIN IMMEDIATE`.
5. `sessions_for_issue()` — `scripts/little_loops/history_reader.py:2094`; the first reader to
   go green again, and the one `ll-history sessions` calls.
6. `issue_effort()` — `scripts/little_loops/history_reader.py:2126`; second reader, feeding
   `recent_issue_velocity()` at `scripts/little_loops/history_reader.py:2178`.

## Impact

- **Priority**: P1 — a shipped user-facing command (`ll-history sessions`) returns
  nothing on an affected database, and two library readers silently return empty. The
  failure mode is indistinguishable from "no data," so it does not get reported.
- **Blast radius**: any database that crossed v36 before the current code, on any
  project. Unknown how many; this checkout's is one. A fresh install is unaffected,
  which is why the test suite never caught it.
- **Blocks**: FEAT-3183, whose session→issue joins all key on `issue_num`.
- **Effort**: Small — one appended migration plus tests. Items 2–4 are the durable
  part and can be scoped separately.
- **Breaking Change**: No.

## Acceptance Criteria

- A database stamped at `schema_version = 41` with the pre-v36 `issue_sessions` view
  gains `issue_num` after `ensure_db()`.
- `ll-history sessions <ID>`, `issue_effort()`, and `recent_issue_velocity()` return
  real data on this repo's `.ll/history.db` after the fix.
- A test asserts the `issue_sessions` column set for the current `SCHEMA_VERSION`, on
  both a fresh database and one upgraded from a stamped older version.
- A history-reader query that fails against an existing, readable database is
  distinguishable in logs from an empty result.

## Status

- [ ] open

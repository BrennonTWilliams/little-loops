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
learning_tests_required:
- sqlite3
verify_verdict: VALID
confidence_score: 96
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 23
---

# BUG-3236: `issue_sessions` view drift leaves `issue_num` absent on migrated databases

## Summary

On this repo's `.ll/history.db` — reporting `schema_version = 41` — the `issue_sessions`
view is a **variant that never shipped** and has no `issue_num` column. Every reader that
queries `issue_sessions WHERE issue_num = ?` raises
`sqlite3.OperationalError: no such column: issue_num`, and every one of them catches
`sqlite3.Error` and returns an empty result. The failure is therefore **silent**:
`ll-history sessions <ID>` prints nothing, `issue_effort()` returns `None`, and
`recent_issue_velocity()` returns `[]` — none of which is distinguishable from
"this issue genuinely has no recorded sessions."

## Steps to Reproduce

Requires a database that crossed schema v36 under the uncommitted migration body
described in [Root Cause](#root-cause) — a freshly created one will **not** reproduce
this, and neither will one upgraded by today's committed code. This checkout's
`.ll/history.db` is one such database.

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

Migration 36 (`schema.py` migration index 35, ENH-2771) applied its `ALTER TABLE` and
index statements, and it *did* run a `DROP VIEW` / `CREATE VIEW issue_sessions` pair —
but with a body that matches neither the v16 nor the committed v36 definition. See
[Root Cause](#root-cause) for the live SQL.

### Additional drift on the same database (not `issue_sessions`)

Diffing the live schema against a fresh `ensure_db()` — comparing PRAGMA-derived
column sets and index names, not `sqlite_master.sql` text — turns up three missing
indexes:

| Index | Migration | Kind | Consequence of absence |
|---|---|---|---|
| `idx_assistant_messages_dedup` | v11 (`schema.py:306`) | UNIQUE | `INSERT OR IGNORE` idempotency for `assistant_messages` is not enforced |
| `idx_summary_nodes_retention_dedup` | v19 (`schema.py:484`) | UNIQUE | same, for `kind = 'retention'` summary nodes |
| `idx_summary_nodes_parent_id` | v10 (`schema.py:287`) | plain | DAG parent traversal unindexed |

This is **out of scope for this fix** — see [Fix](#fix) item 5 for the reasoning and
the hard-failure risk that motivates the split.

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

**The migration ran against a working-tree-only revision of `_MIGRATIONS[35]` that was
never committed.** The live view is a third variant, distinct from both v16 and the
committed v36:

```sql
CREATE VIEW issue_sessions AS
    SELECT ie.issue_id, ie.session_id, s.jsonl_path,
           MIN(ie.ts) AS first_message_ts, MAX(ie.ts) AS last_message_ts
    FROM issue_events ie
    LEFT JOIN sessions s ON s.session_id = ie.session_id
    WHERE ie.session_id IS NOT NULL
    GROUP BY ie.issue_num, ie.session_id          -- v36-shaped (v16 groups by issue_id)
    UNION ALL
    SELECT l.issue_id, l.session_id, l.jsonl_path, l.first_message_ts, l.last_message_ts
    FROM legacy_issue_sessions_ts_overlap l
    JOIN issue_events le ON le.issue_id = l.issue_id   -- exists in NO commit
    WHERE le.issue_num NOT IN (
        SELECT issue_num FROM issue_events
        WHERE session_id IS NOT NULL AND issue_num IS NOT NULL
    ) OR le.issue_num IS NULL;
```

It references `issue_num` internally but never projects it — an in-progress state of the
ENH-2771 rewrite, halfway between keying on `issue_id` and keying on `issue_num`.
Evidence:

- `git log -S "JOIN issue_events le ON le.issue_id" --all` returns **no commits**. The
  live body has no committed ancestor.
- `6a402cf8` (ENH-2771), the commit that bumped `SCHEMA_VERSION` to 36, introduced the
  migration already projecting `issue_num AS issue_num`. The only later touch is
  `2b2abdb9` (the `session_store.py` → subpackage split), which moved the text unchanged.
- Committed v36 uses `CAST(substr(l.issue_id, ...) AS INTEGER)` for the legacy branch;
  the live view uses a `JOIN issue_events le` instead.

This is the source repo, and every little-loops project on this machine is
`local-editable` against this checkout — so an `ll-*` invocation during the ENH-2771 work
migrated these databases with the then-uncommitted migration body. That is precisely the
"editing a migration in place after databases have already passed it" failure the
[Fix](#fix) warns against, arrived at through the working tree rather than through a
committed edit.

Two things are correct and were verified:

- **A fresh database is correct.** `ensure_db()` on a new path produces
  `issue_sessions` with `issue_num`.
- **The current upgrade path is correct.** Hand-applying migrations 0–34, stamping
  `schema_version = 35`, then calling `ensure_db()` produces the committed v36 view with
  `issue_num`. `_split_sql_statements(_MIGRATIONS[35])` yields all 14 statements including
  the `DROP VIEW` / `CREATE VIEW` pair, and `_apply_migrations()` runs the whole migration
  inside one `BEGIN IMMEDIATE` with `ROLLBACK` on any exception — so a partial apply cannot
  happen under today's code. **`schema.py:888-908` never shipped in a broken form.**

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

> **Implementation trap — do not compare `sqlite_master.sql` text.** SQLite stores the
> *original* `CREATE` statement verbatim and never rewrites it, so a comment added to a
> `CREATE TABLE` body after the table was created reads as drift forever. A naive text
> diff of this checkout's database against a fresh one flags `raw_events` as drifted;
> the only difference is a block comment added to the `raw_events` DDL long after the
> table existed. The structure is identical. Any structural check must compare
> **PRAGMA-derived column sets and index names**, never SQL strings.

**5. Index drift is real but deliberately out of scope here.** The three missing indexes
listed under [Current Behavior](#current-behavior) are genuine drift, and not confined to
this database — two other local databases (at v40 and v41) each lack one despite having a
correct `issue_sessions` view. They are **not** repaired by this fix. The reason to split
rather than fold them into the same v42 migration:

`CREATE UNIQUE INDEX` fails outright on any database that accumulated duplicate rows
while the index was missing. `_apply_migrations()` rolls back the entire migration and
re-raises, `ensure_db()` propagates, and **every `ll-*` command on that project hard-fails
at startup** — converting a silent read bug into a total outage. This checkout happens to
have zero duplicate groups in both `assistant_messages` (68,693 rows) and `summary_nodes`
(0 rows), but that is luck, not a guarantee for other affected databases. A correct index
repair must delete duplicates before creating each UNIQUE index, which is a materially
larger and riskier change than the view rebuild. File it as a follow-up.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- Verified against current `schema.py`: `_MIGRATIONS` is a flat `list[str]` (opens line 111, closes line 998), `SCHEMA_VERSION = 41` is a plain module constant (line 21) kept in sync with `len(_MIGRATIONS)` by hand — not derived. Appending one entry makes `len(_MIGRATIONS) == 42`, occupying 0-based index 41, matching this issue's `_MIGRATIONS[41]` citation. `_apply_migrations()`'s loop (`schema.py:1050-1086`) needs no change to pick up the new entry: with `schema_version = 41` and `len(_MIGRATIONS) = 42`, the line-1065 short-circuit (`41 >= 42`) is false, the loop runs `range(41, 42)` (index 41 only), and stamps `schema_version = 42` on completion — this is the same mechanism every prior migration append has exercised.
- **New gap, not previously noted**: `SCHEMA_VERSION == 41` is hard-coded as a literal assertion in 9 separate places across `scripts/tests/test_session_store_schema.py` (lines 650, 664, 716, 813, 1035, 1076, 1130, 1195, 1413), plus one each in `test_session_store_writers.py`, `test_assistant_messages.py`, and `test_session_store_lifecycle.py`. All of these must be updated to `42` alongside the `SCHEMA_VERSION` bump or they fail as an unrelated-looking regression.
- `history_reader.py:2107` and `:2136` confirmed to be the exact `logger.warning("history_reader: <fn> query failed", exc_info=True)` lines this issue cites for item 2's log-level change. This warning+sentinel shape is uniform across 60+ `except sqlite3.Error:` sites in `history_reader.py` (`_connect_readonly` at :422-436, `find_user_corrections`, `recent_file_events`, etc.) — there is currently no log-level distinction anywhere in the file between "database missing" and "query failed against a present database," so item 2 would establish a new convention, not extend an existing one. `sessions_for_issue`'s own docstring (`history_reader.py:2092-2093`) already documents that its empty-list return conflates three distinct causes (absent view, no sessions, unavailable db) into one indistinguishable signal.
- Two prior idempotent `DROP VIEW IF EXISTS issue_sessions` / `CREATE VIEW issue_sessions AS ...` precedents already exist for this exact view: v16/ENH-2462 (`schema.py:372,386`) and v36/ENH-2771 (`schema.py:888-909`). Both are unconditional statement pairs (SQLite `CREATE VIEW` has no `IF NOT EXISTS` combinable with a column-list change) — confirms this fix's rebuild approach matches the established idiom for "a view's column list changed," as opposed to `ALTER TABLE ... ADD COLUMN`, which is the idiom used everywhere a *table* (not a view) gains a column.
- No `_stamp_version(conn, version)` helper exists anywhere in the codebase today. The closest existing analogue, `_bootstrap_schema_at(db, version)` (`test_session_store_schema.py:1134-1154`), replays real `_MIGRATIONS[:version]` DDL *and* stamps `schema_version` together — it only ever constructs a database whose recorded version matches its actual structure. No existing helper stamps a version number against a schema that does *not* match it, which is exactly the drifted scenario this issue's regression test needs to construct; `_stamp_version` fills a genuinely unprecedented gap and should not be conflated with `_bootstrap_schema_at`.
- Migration entry comment convention is inconsistent in the file as written: entries before ~v37 use `# vNN (ISSUE-ID): ...` (e.g. `schema.py:164,180,196`); v37+ entries drop the `vNN` prefix (`schema.py:910,922,939,966`). Either form is accepted today (unenforced); the new entry may follow either.
- Existing per-migration tests use a dedicated `TestSchemaVNN` class per migration (e.g. `TestSchemaV27`, `TestSchemaV28`) rather than bare module-level test functions — the two new test names in this issue's Program Design (`test_issue_sessions_view_has_issue_num_on_fresh_db`, `test_issue_sessions_view_repaired_on_drifted_db`) can be added as module-level functions or under a new `TestSchemaV42`-style class; both shapes coexist in the current file (module-level functions also appear, e.g. `test_v1_db_upgrades_to_v2_idempotently`).

_Added by pre-implementation review — 2026-08-17 — verified against the live database:_

- **The fix is empirically validated.** Applying the two `issue_sessions` statements from
  `_MIGRATIONS[35]` to a copy of this checkout's `.ll/history.db` produces
  `['issue_id', 'issue_num', 'session_id', 'jsonl_path', 'first_message_ts', 'last_message_ts']`,
  after which `sessions_for_issue("ENH-3195")` returns a real `SessionRef` and
  `issue_effort("ENH-3195")` returns `{'session_count': 1, 'cycle_time_days': 0.0}`.
  Acceptance criteria 1 and 2 are satisfiable exactly as written.
- **No type-affinity trap in the readers.** `sessions_for_issue()` passes
  `normalize_issue_id(issue_id)` into `WHERE issue_num = ?`; `normalize_issue_id`
  (`session_store/writers.py:145`) returns `int | None`, so `"ENH-3195"` arrives as
  `3195` and matches the INTEGER column. Worth having checked — a `str` return would have
  let the migration land, the tests pass, and the readers still return nothing.
- The repaired view's `jsonl_path` is `NULL` for the sampled issue (no matching `sessions`
  row), and `cycle_time_days` is `0.0` because the v36 dedup index keeps one
  `issue_events` row per `(issue_num, transition)`. The data is thin but real; do not read
  a sparse result after the fix as the fix having failed.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:8887` — the `from little_loops.session_store import (SCHEMA_VERSION,        # 38` line already carries a stale inline value comment (live value is 41, not 38, even before this fix); bumping `SCHEMA_VERSION` to 42 is a natural point to correct it to `# 42` while in the area. Optional — the comment is pre-existing drift, not something this fix's diff newly breaks. [Agent 2 finding]

## Impact

- **Priority**: P1 — a shipped user-facing command (`ll-history sessions`) returns
  nothing on an affected database, and two library readers silently return empty. The
  failure mode is indistinguishable from "no data," so it does not get reported.
- **Blast radius**: measured, not estimated. A sweep of all 31 `.ll/history.db` files on
  this machine finds **three** drifted databases at `schema_version >= 36`: this
  checkout's (v41), and two others (v41 and v39). Every database below v36 legitimately
  lacks `issue_num` — that is staleness, not drift, and `ensure_db()` will migrate them
  correctly whenever they are next opened.
- **Released users are almost certainly unaffected.** The committed migration body has
  always projected `issue_num` (see [Root Cause](#root-cause)); only databases migrated
  by an uncommitted working-tree revision of `_MIGRATIONS[35]` — i.e. local-editable
  projects on the development machine during the ENH-2771 work — can be drifted. The fix
  is still worth shipping as a migration: it is idempotent and cheap on correct
  databases, and there is no way to prove the set is closed. A fresh install is
  unaffected, which is why the test suite never caught it.
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


## Session Log
- `/ll:confidence-check` - 2026-08-17T17:19:11 - `83adf706-3c34-48ba-adbd-2ccf3898278d.jsonl`
- `/ll:verify-issues` - 2026-08-17T17:17:33 - `038b6ab4-3b9f-4cfd-a4d6-dac5e7366086.jsonl`
- `/ll:wire-issue` - 2026-08-17T17:15:27 - `72df34c5-4823-4f9c-bb82-d4eea9e4edcc.jsonl`
- `/ll:refine-issue` - 2026-08-17T17:08:25 - `0d1d5748-87d3-4915-a4de-db31a62296c5.jsonl`

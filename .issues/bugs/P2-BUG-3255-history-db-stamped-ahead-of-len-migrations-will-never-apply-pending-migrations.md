---
id: BUG-3255
type: BUG
title: A history.db stamped ahead of len(_MIGRATIONS) silently never applies pending migrations
priority: P2
status: open
testable: true
discovered_by: enh-3242-pre-implementation-review
discovered_date: '2026-08-18'
labels:
- history-db
- session-store
- schema-drift
- silent-failure
relates_to:
- ENH-3242
- BUG-3236
- BUG-3241
---

# BUG-3255: A `history.db` stamped ahead of `len(_MIGRATIONS)` silently never applies pending migrations

## Summary

`_apply_migrations()` short-circuits on `_current_version(conn) >= len(_MIGRATIONS)`
(`session_store/schema.py:1229`). The comparison is `>=`, not `==`, so a database whose
recorded `meta.schema_version` is *greater* than the number of migrations the installed code
carries is treated as current forever — including after new migrations are added, because
`45 >= 44` is still true.

This is not hypothetical. **This repo's own `.ll/history.db` records `schema_version = 45`
against `SCHEMA_VERSION = 43` / `len(_MIGRATIONS) = 43`.** When migration 44 lands, it will
not apply here, silently and permanently.

## Current Behavior

```
$ python -c "import sqlite3; print(sqlite3.connect('file:.ll/history.db?mode=ro',uri=True)
    .execute(\"select key,value from meta where key like '%version%'\").fetchall())"
[('schema_version', '45'), ('last_rebuild_version', '43')]

$ python -c "from little_loops.session_store import schema as S;
    print(S.SCHEMA_VERSION, len(S._MIGRATIONS))"
43 43
```

`git log -S'SCHEMA_VERSION = 45' -- scripts/little_loops/session_store/schema.py` returns **no
commits** — 45 was never a released or committed version. It was stamped by an uncommitted
working-tree state run against the live database, which is exactly the drift mechanism
ENH-3242's Motivation section describes: every little-loops project on this machine is
`local-editable` against this checkout, so any `ll-*` invocation during in-progress migration
work runs the working-tree `_MIGRATIONS` against real databases. Here it left a version stamp
rather than a structural change.

Structurally the database is currently fine — its full PRAGMA-derived manifest diffs clean
against a fresh `ensure_db()` build at v43, in both directions. The defect is the version
accounting, and its consequence is future.

## Steps to Reproduce

Against this repository's working tree (the affected database is already in this state):

1. Read the recorded version and compare it to the installed migration count:

   ```bash
   python -c "import sqlite3; print(sqlite3.connect('file:.ll/history.db?mode=ro',uri=True)
       .execute(\"select value from meta where key='schema_version'\").fetchone())"   # ('45',)
   python -c "from little_loops.session_store import schema as S; print(len(S._MIGRATIONS))"  # 43
   ```

2. Confirm no released version ever declared 45:
   `git log -S'SCHEMA_VERSION = 45' -- scripts/little_loops/session_store/schema.py` → no output.

From a clean state, the same condition is reproducible in isolation:

1. `ensure_db(tmp)` on a temp path.
2. `UPDATE meta SET value = '45' WHERE key = 'schema_version'`.
3. Append a 44th entry to `_MIGRATIONS` (e.g. `CREATE TABLE probe (id INTEGER);`).
4. `ensure_db(tmp)` again → returns without applying it; `probe` does not exist and the
   recorded version stays 45. No error, no log line.

## Expected Behavior

A database recording a version the installed code cannot account for is either repaired or
reported, not silently accepted as current. At minimum, adding migration 44 must not silently
skip it on such a database.

## Root Cause

Two independent contributors:

1. **`>=` in the fast path** (`schema.py:1229`). `>` is the "impossible" case and is not
   distinguished from `==`. The loop body is equally permissive: `range(version,
   len(_MIGRATIONS))` is empty when `version > len(_MIGRATIONS)`, so even past the fast path
   nothing would apply.
2. **Nothing rejects a forward stamp when it is written.** `_apply_migrations()` writes
   `str(index + 1)` per migration with no upper bound check against what the file declares, so
   a working tree carrying extra migrations stamps a number a later checkout cannot honour.

## Fix

Not yet decided; the shape needs a call. Sketch of the options:

- **Detect and report only** — leave the data alone and surface it through ENH-3242's new
  `ll-doctor` check, whose version guard already branches on `recorded > len(_MIGRATIONS)`.
  ENH-3242 re-rates that branch from `informational` to a real finding on the strength of this
  bug. Cheapest, but leaves the affected database broken until someone acts.
- **Clamp on read** — treat `recorded > len(_MIGRATIONS)` as "unknown, re-verify" and fall
  through to the migration loop rather than short-circuiting. Dangerous without structural
  verification: re-running migrations 44–45's *predecessors* is a no-op only because the DDL is
  `IF NOT EXISTS`, which is not guaranteed for future migration bodies.
- **Repair migration** — a future migration that resets an over-stamped `meta.schema_version`
  down to its own index. Consistent with BUG-3241's v43 repair-migration precedent, but it
  cannot run on the very databases that need it, since they short-circuit before reaching it.
  This circularity is the crux of the fix decision.

Whichever lands, the fast-path comparison should distinguish `>` from `>=` so the impossible
case is at least visible.

## Program Design

### Signatures

No new symbols required for the detect-only resolution; the change is confined to existing
functions.

- `_apply_migrations(conn: sqlite3.Connection) -> None` (`session_store/schema.py:1214`) —
  fast-path comparison at `:1229` splits `recorded > len(_MIGRATIONS)` out of the `>=` branch.
  Whether that branch logs, raises, or falls through is the open fix decision above.
- `_current_version(conn: sqlite3.Connection) -> int` (`:1197`) — unchanged; it faithfully
  reports what is stamped, and the defect is in how the caller interprets an over-large value.

### Call Path

`ensure_db()` (`:1253`) -> `_apply_migrations()` (`:1214`) -> `_current_version()` (`:1197`)
-> fast-path comparison (`:1229`). Every `ll-*` invocation reaches this via
`cli_event_context()` (`session_store/writers.py:483`) and `hooks/session_start.py:132-135`,
so any behavior change here has the ~52-caller blast radius ENH-3242's Option A deliberately
avoided — an argument for resolving this by detection in `ll-doctor` rather than by changing
the fast path's control flow.

Detection-only path (if that resolution is chosen): `ll-doctor` ->
`_run_registered_checks()` (`cli/doctor.py:116`) -> ENH-3242's `_schema_drift_data()` ->
version guard's `recorded > len(_MIGRATIONS)` branch. ENH-3242 already specifies that branch
as a finding on the strength of this bug, so detection ships with no additional work here.

## Impact

- **Priority**: P2 — no symptom today (the affected database is structurally correct and the
  next migration has not been written), but the failure is silent, permanent, and lands the
  moment migration 44 is added. Detection-only is cheap and can ship with ENH-3242.
- **Scope**: at least one database (this repo's). The other 12 surveyed under `~/AIProjects`
  record 13–40, all legitimately behind, none ahead — so the blast radius today is small, but
  the mechanism that produced it is routine for this repo's development model.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] A test asserts the behavior of `_apply_migrations()` against a database stamped above
      `len(_MIGRATIONS)`, pinning whichever resolution is chosen rather than leaving the case
      untested.
- [ ] The fast path distinguishes `recorded > len(_MIGRATIONS)` from `recorded ==
      len(_MIGRATIONS)` rather than collapsing both into `>=`.
- [ ] This repo's `.ll/history.db` is either repaired or has its state documented as knowingly
      accepted.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of ENH-3242's pre-implementation review (2026-08-18). ENH-3242 covers *detecting*
this state via its `ll-doctor` version guard; the repair decision is this issue.

## Status

- [ ] open

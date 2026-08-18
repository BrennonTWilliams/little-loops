---
id: BUG-3255
type: BUG
title: A history.db stamped ahead of len(_MIGRATIONS) silently never applies pending
  migrations
priority: P2
status: done
completed_at: '2026-08-18T23:41:29Z'
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
confidence_score: 100
outcome_confidence: 84
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3255: A `history.db` stamped ahead of `len(_MIGRATIONS)` silently never applies pending migrations

## Summary

`_apply_migrations()` short-circuits on `_current_version(conn) >= len(_MIGRATIONS)`
(`session_store/schema.py:1233`). The comparison is `>=`, not `==`, so a database whose
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

### The over-stamp is routine, not exotic

The uncommitted-working-tree mechanism above produced *this* database's state, but it is not
the common way to reach `recorded > len(_MIGRATIONS)`. The ordinary trigger is **checking out
a commit older than the database** — `git bisect`, verifying a release tag, or working on a
branch that predates a migration. In that state the installed `_MIGRATIONS` is legitimately
shorter than what the database has genuinely applied, and the database genuinely carries the
newer structure.

Today this is harmless in both directions: `45 >= 43` no-ops on the old checkout, and `45 >=
45` no-ops on return to HEAD. **Any resolution must preserve that**, because an unconditional
stamp rewrite would make the old checkout destroy the version accounting and cause migrations
44–45 to re-run against a database that already has them on return to HEAD — turning a
currently-benign situation into a breaking one. This is why the chosen fix is guarded on a
structural check rather than clamping unconditionally (see Fix).

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

1. **`>=` in the fast path** (`schema.py:1233`). `>` is the "impossible" case and is not
   distinguished from `==`. The loop body is equally permissive: `range(version,
   len(_MIGRATIONS))` is empty when `version > len(_MIGRATIONS)`, so even past the fast path
   nothing would apply.
2. **Nothing rejects a forward stamp when it is written.** `_apply_migrations()` writes
   `str(index + 1)` per migration with no upper bound check against what the file declares, so
   a working tree carrying extra migrations stamps a number a later checkout cannot honour.

## Fix

**Decided 2026-08-18: self-healing stamp clamp in the fast path, *guarded by a structural
manifest check*, plus ENH-3242 detection for visibility. The repair-migration option is
rejected.**

### Chosen resolution

On `recorded > len(_MIGRATIONS)`, compare the database's actual structure against what
`len(_MIGRATIONS)` is supposed to produce. Only if they match is the stamp rewritten *down* to
`len(_MIGRATIONS)`; otherwise the stamp is left alone and the condition is logged. Nothing is
ever re-run: the clamp corrects version accounting only, and the next `ensure_db()` after
migration 44 lands applies it through the ordinary loop.

The guard is what separates the two populations that both present as `recorded >
len(_MIGRATIONS)`:

- **Over-stamped but structurally at `len(_MIGRATIONS)`** (this repo's database, and the
  working-tree drift mechanism generally) — manifest matches, clamp is safe and correct.
- **Legitimately ahead** (older checkout / downgraded install, per Current Behavior) — the
  database really does carry v44/v45 objects, the manifest does *not* match, and the stamp must
  be preserved so returning to HEAD stays a no-op.

```python
if recorded > len(_MIGRATIONS):
    # Compare objects/indexes only — NOT the whole manifest dict, whose
    # "schema_version" key is _current_version(conn) and so always differs here.
    live = _schema_manifest(conn)
    reference = _reference_manifest_at(len(_MIGRATIONS))
    if (live["objects"], live["indexes"]) == (reference["objects"], reference["indexes"]):
        logger.warning(
            "session_store: history.db records schema_version=%d but installed code "
            "carries %d migrations; structure matches %d, resetting stamp",
            recorded, len(_MIGRATIONS), len(_MIGRATIONS),
        )
        # fall through to the write lock and clamp the stamp before the loop
    else:
        logger.warning(
            "session_store: history.db records schema_version=%d, ahead of this install's "
            "%d migrations, and its structure does not match %d; leaving the stamp intact "
            "(run `ll-doctor` for the structural diff)",
            recorded, len(_MIGRATIONS), len(_MIGRATIONS),
        )
        return
elif recorded == len(_MIGRATIONS):
    return
```

**Both manifest helpers already exist** — `_schema_manifest()` and `_reference_manifest_at()`
(`schema.py:1417`), landed by ENH-3242 and used by `cli/doctor.py:449-455`. This is new
composition, not new machinery: `doctor.py`'s drift check returns early on `recorded >
len(_MIGRATIONS)` and never performs this particular comparison itself.

**Two mandatory implementation details:**

1. **Compare `objects`/`indexes` only.** `_schema_manifest()` returns
   `{"schema_version": _current_version(conn), "objects": …, "indexes": …}`. A whole-dict `==`
   would compare `45` against `43` and *always* report a mismatch, silently disabling the clamp
   in exactly the case it exists for.
2. **Clamp inside the lock, not just in the fast path.** The existing code deliberately re-reads
   `version = _current_version(conn)` inside `BEGIN IMMEDIATE` (`schema.py:1240`) to close the
   fresh-database race. That in-lock read must *also* be clamped before it reaches
   `range(version, len(_MIGRATIONS))`, and the `meta.schema_version` write must happen inside
   the same transaction. Patching only the pre-lock fast path leaves the stamp unwritten.

**Cost.** `_reference_manifest_at()` replays the full migration sequence into an in-memory
database, measured at ~5.0ms (its own docstring). This is paid only on the `recorded >
len(_MIGRATIONS)` branch — never in steady state, where the `==` branch still returns lock-free
and the ~52-caller hot path pays nothing.

**Log, do not raise.** `hooks/session_start.py:132-135` wraps `ensure_db()` in
`contextlib.suppress(Exception)`, so a raise is invisible exactly where it would first fire and
only surfaces later via `writers.py:521` — as a hard failure on every `ll-*` invocation, for a
database that is structurally fine. That is the worst of both behaviors. This applies to both
guard branches: the mismatch branch returns, it does not raise.

**Residual risk (small, and no longer the main one).** With the guard, a wrongly-clamped
database requires a structural coincidence: over-stamped *and* structurally identical to
`len(_MIGRATIONS)` *and* a future migration that collides. Worth recording explicitly, because
the original framing of this risk was wrong: re-applying a migration is **not** reliably a loud
`table already exists` error. Measured across `_MIGRATIONS`, 29 of 31 `CREATE TABLE` and all
108 `CREATE INDEX` statements use `IF NOT EXISTS`, so they re-run silently. Re-application is
loud only for the 28 `ALTER TABLE … ADD COLUMN` statements — and a migration shaped
`CREATE TABLE IF NOT EXISTS` + `DELETE FROM … dedup` (four such blocks exist, e.g.
`schema.py:864-883`) would re-run silently and **delete rows accumulated since**. The migration
loop's `BEGIN IMMEDIATE` / `ROLLBACK` contains the damage when *some* statement in the script
raises, but that is not guaranteed for an all-idempotent script. The structural guard is what
makes this residual rather than accepted.

### Out of scope: `last_rebuild_version`

`hooks/session_start.py:191` gates its rebuild on `if _last_rebuild_version < SCHEMA_VERSION:`
— the same silent-skip shape, fed by the same drift producer (`lifecycle.py:985` writes the
working tree's `SCHEMA_VERSION`). This repo's database reads `last_rebuild_version = 43`, equal
to `SCHEMA_VERSION`, so it is benign today.

**This fix rewrites `meta.schema_version` only and must not touch `last_rebuild_version`.**
Recorded here so the adjacency does not have to be rediscovered; a forward-stamped
`last_rebuild_version` is a separate issue if it is ever observed.

### Why not the alternatives

- **Unconditional clamp (no manifest guard)** — the originally decided shape, rejected on
  review. It is correct for this repo's database but wrong for the more common trigger: an
  older checkout would rewrite a legitimately-ahead stamp down, and returning to HEAD would
  re-run migrations the database already has (see Current Behavior). The guard costs ~5.0ms on
  a branch that is never taken in steady state.
- **Detect-only (`ll-doctor`)** — kept, but as visibility, not as the resolution. It is a pull
  mechanism against a push failure: nobody runs `ll-doctor` on a schedule, and the failure
  window opens the moment migration 44 is written, likely in the same session. It also does not
  scale past this one database — the producing mechanism (local-editable checkout running
  in-progress `_MIGRATIONS` against live databases) recurs, and each recurrence needs a human to
  notice and hand-fix.
- **Clamp on read (fall through to the loop)** — inert as originally described. With
  `recorded = 45` and `len(_MIGRATIONS) = 43`, `range(45, 43)` is empty; falling through takes
  the write lock and does nothing, and the stamp stays 45. Clamping the *loop start* to
  `len(_MIGRATIONS)` gives `range(43, 43)` — also empty. Only clamping the *stamp* changes
  anything, which is the chosen resolution above.
- **Repair migration** — rejected. The circularity is fatal, not merely awkward: a migration at
  index 43 is reached via `range(version, len(_MIGRATIONS))`, which is empty at `version = 45`,
  so the repair cannot run on the only databases that need it. Making it reachable requires
  changing the fast path first — at which point the fast-path change alone has already done the
  job. BUG-3241's v43 repair-migration precedent (`schema.py:1029-1161`) does not transfer: it
  assumes the migration loop is reachable.

### Port to `queue_store.py`

The guarded clamp ports to the duplicated fast path at `queue_store.py:172-173` in shape, but
not verbatim: `queue_store.py` has no manifest machinery of its own (`_schema_manifest()` /
`_reference_manifest_at()` are `session_store`-only, and ENH-3242's drift check covers
`history.db` alone), so the port needs either an equivalent manifest pair for `queue.db` or a
deliberate decision to clamp unconditionally there on a smaller, lower-risk schema.

Still out of this issue's Program Design scope, but the chosen resolution is the one of the
three that transfers at all — a repair migration would not have. **No follow-up issue exists
yet**; ENH-3242's Integration Map already flags that a fix here "needs a parallel decision for
`queue_store.py` to be complete." File one when this ships, or the two schema systems diverge
on drift coverage silently.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

The fix is scoped to `schema.py`; `writers.py`, `session_start.py`, and `lifecycle.py` are call sites whose current behavior constrains which resolution is safe, and `queue_store.py` carries the identical defect but is out of scope.

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — fast-path comparison at `:1233` (`_apply_migrations()`), plus the in-lock version re-read at `:1240`. The whole change is scoped to this file, per Program Design; the manifest helpers the guard calls (`_schema_manifest()`, `_reference_manifest_at()` at `:1417`) already live here.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/writers.py:521` — `cli_event_context()` (`:483`) calls `_pkg.connect()`, which calls `ensure_db()` -> `_apply_migrations()`; this is the hot path for all ~52 `ll-*` CLI callers.
- `scripts/little_loops/hooks/session_start.py:132-135` — calls `ensure_db()` directly, wrapped in `contextlib.suppress(Exception)`; a resolution that makes the fast path raise on `recorded > len(_MIGRATIONS)` is silently swallowed here and never surfaces to the user.
- `scripts/little_loops/session_store/lifecycle.py:857` — calls `ensure_db()` during backfill.
- `scripts/little_loops/queue_store.py:172-173` — an independently-maintained duplicate of the identical `_current_version()`/`_apply_migrations()` fast-path pattern for `queue.db`. ENH-3242's Integration Map already flags that a fix here "needs a parallel decision for `queue_store.py` to be complete." Not in this issue's Program Design scope, but the two schema systems diverge on drift coverage if only one is fixed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/doctor.py` (`_schema_drift_data()`, ~line 398-455, ENH-3242, already implemented uncommitted) — its `recorded > len(_MIGRATIONS)` branch returns an error note containing the literal string `"...will never apply to this database until repaired (see BUG-3255)"`. This is a read-only detection path (never calls `ensure_db()`), so it keeps firing for any database not yet touched by this fix's clamp, but the note text itself becomes misleading once BUG-3255 ships (it reads as still-open). No test asserts the literal `"BUG-3255"` substring (`test_cli_doctor_install_checks.py::test_version_ahead_is_a_finding_not_informational` only asserts `status`/`severity`/version numbers appear), so the note can be edited freely without breaking tests.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/doctor.py` — update or remove the `(see BUG-3255)` fragment in `_schema_drift_data()`'s error note once this fix ships, so the message doesn't read as pointing at a still-open bug.
- `scripts/tests/test_cli_doctor_install_checks.py:389-391` — `test_version_ahead_is_a_finding_not_informational`'s docstring states "This repo's own history.db is in exactly this state (BUG-3255)"; this becomes stale prose (not a failing assertion) once the clamp self-heals this repo's `.ll/history.db`, per Acceptance Criteria's last checkbox.

### Tests
- `scripts/tests/test_session_store_schema.py:2012-2024` — `_stamp_version(conn, version)` writes `meta.schema_version` directly, bypassing migration application. This is the existing helper for constructing a version-drifted fixture database, already used by `TestSchemaV42IssueSessionsRepair`/`TestSchemaV43IndexRepair`, but no existing use stamps a version *above* `len(_MIGRATIONS)` — the exact untested case Acceptance Criteria #1 asks for.
- `scripts/tests/test_session_store_schema.py:1134-1154` — `_bootstrap_schema_at(db, version)` replays `_MIGRATIONS[:version]` into a fresh fixture; pairs with `_stamp_version()` to build a "structurally-correct-at-N, stamped-above-N" database.
- `scripts/tests/test_session_store_schema.py:2129-2134` — `test_schema_version_matches_migrations_length()` guards a different invariant (`SCHEMA_VERSION == len(_MIGRATIONS)`, both in-code constants); it does not and cannot catch a live database's stored value exceeding `len(_MIGRATIONS)`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_doctor_install_checks.py:389-415` — `TestSchemaDrift.test_version_ahead_is_a_finding_not_informational` (ENH-3242, already implemented) already builds the exact over-stamped fixture (`ensure_db()` then `UPDATE meta SET value = SCHEMA_VERSION + 2`) for the read-only detection path. The new AC #4 test should mirror this fixture-construction shape but call `ensure_db()` a second time (instead of `_schema_drift_data()`) and assert the clamp + a WARNING log, rather than reinventing fixture setup.
_Review pass added 2026-08-18 (manifest guard):_
- The AC #4 mismatch fixture ("stamped ahead **and** structurally different") has no existing
  analog — `_bootstrap_schema_at()` + `_stamp_version()` always produce a structure matching
  some real migration index. Build it by bootstrapping at `len(_MIGRATIONS)`, stamping ahead,
  then executing one extra DDL statement directly on the connection (e.g.
  `CREATE TABLE ahead_probe (id INTEGER);`) so the live manifest's `objects` gains an entry the
  reference lacks. That is the shape a genuinely-ahead database has.
- No existing test in `test_session_store_schema.py` uses `caplog`; the WARNING-log assertion required by Acceptance Criteria #3 has a directly reusable pattern in `scripts/tests/test_session_store_writers.py:703-716` and `:718-739` (`caplog.at_level(logging.WARNING, logger="little_loops.session_store.writers")` around a `record_issue_snapshot()` call) — same shape applies with `logger="little_loops.session_store.schema"` (the module's `logging.getLogger(__name__)`, `schema.py:23`), which already has a precedent WARNING call site at `schema.py:1282-1286` for the legacy session.db rename fallback.

## Program Design

### Signatures

No new symbols required; the change is confined to existing functions.

- `_apply_migrations(conn: sqlite3.Connection) -> None` — `session_store/schema.py:1218`;
  fast-path comparison at `:1233` splits `recorded > len(_MIGRATIONS)` out of the `>=` branch.
  That branch compares `objects`/`indexes` against `_reference_manifest_at(len(_MIGRATIONS))`
  and either falls through to clamp the stamp inside the existing transaction (match) or logs
  and returns (mismatch). Both paths log at WARNING; neither raises (decided — see Fix). The
  in-lock re-read at `:1240` is clamped in the same change.
- `_current_version(conn: sqlite3.Connection) -> int` — `session_store/schema.py:1201`;
  unchanged, it faithfully reports what is stamped, and the defect is in how the caller
  interprets an over-large value.
- `_schema_manifest(conn: sqlite3.Connection) -> SchemaManifest` and
  `_reference_manifest_at(version: int) -> SchemaManifest` — `session_store/schema.py:1417` and
  just above it; both unchanged and already in this module (ENH-3242). Called by the new guard.
  Their return dicts carry a `schema_version` key that must be excluded from the comparison —
  see Fix's mandatory implementation detail #1.

### Call Path

`ensure_db()` (`:1257`) -> `_apply_migrations()` (`:1218`) -> `_current_version()` (`:1201`)
-> fast-path comparison (`:1233`). Every `ll-*` invocation reaches this via
`cli_event_context()` (`session_store/writers.py:483`) and `hooks/session_start.py:132-135`,
so any behavior change here has the ~52-caller blast radius ENH-3242's Option A deliberately
avoided. The chosen clamp keeps that radius at zero in steady state: the `==` branch still
returns lock-free, and the new branch is taken only by an over-stamped database, once, before
it self-corrects.

Detection path (ENH-3242, retained for visibility alongside the clamp): `ll-doctor` ->
`_run_registered_checks()` (`cli/doctor.py:116`) -> ENH-3242's `_schema_drift_data()` ->
version guard's `recorded > len(_MIGRATIONS)` branch. ENH-3242 already specifies that branch
as a finding on the strength of this bug, so detection ships with no additional work here.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- `scripts/little_loops/queue_store.py:154-210` duplicates the identical `_current_version()`/`_apply_migrations()`/`ensure_db()` shape (fast path at `:172-173`) for `queue.db`, independently maintained (its docstring cross-references `session_store._apply_migrations` for rationale but shares no code). Confirmed out of scope for this issue — this Program Design is `schema.py`-only.
- `scripts/little_loops/hooks/session_start.py:132-135` calls `ensure_db()` wrapped in `contextlib.suppress(Exception)`. Relevant to the Fix section's "clamp on read" and "repair migration" options: if either resolution raises on the impossible `recorded > len(_MIGRATIONS)` case, this call site swallows it silently at session start — the raise would only surface on the next `ll-*` CLI invocation via `cli_event_context()` (`writers.py:521`), which is not blanket-suppressed.
- No existing codebase convention resolves the three-way Fix choice: BUG-3241's repair-migration precedent (`schema.py:1029-1161`) is the only structural analog, and it explicitly does not transfer without modification (per that migration's own dedup-then-index pattern, which assumes the migration loop is reachable). The issue's own "circularity" framing for the repair-migration option is accurate, not a placeholder for missing research.

## Impact

- **Priority**: P2 — no symptom today (the affected database is structurally correct and the
  next migration has not been written), but the failure is silent, permanent, and lands the
  moment migration 44 is added. The chosen guarded clamp is a ~25-line change to one function,
  reusing ENH-3242's existing manifest helpers, with no steady-state cost; ENH-3242's detection
  ships alongside it at no additional work.
- **Scope**: at least one database (this repo's). The other 12 surveyed under `~/AIProjects`
  record 13–40, all legitimately behind, none ahead — so the blast radius today is small, but
  the mechanism that produced it is routine for this repo's development model.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] The fast path distinguishes `recorded > len(_MIGRATIONS)` from `recorded ==
      len(_MIGRATIONS)` rather than collapsing both into `>=`; the `==` branch still returns
      without taking the write lock.
- [ ] On `recorded > len(_MIGRATIONS)` **and** a structural match, `_apply_migrations()`
      rewrites `meta.schema_version` down to `len(_MIGRATIONS)` inside the existing
      `BEGIN IMMEDIATE` transaction, and does **not** re-run any already-applied migration. The
      in-lock `version` re-read (`schema.py:1240`) is clamped too, so the stamp write and the
      `range(version, len(_MIGRATIONS))` bound agree.
- [ ] The structural match compares `objects` and `indexes` only, **not** the whole
      `_schema_manifest()` dict — whose `schema_version` key would always differ on precisely
      the databases the clamp exists for. (AC #4 fails if this is got wrong.)
- [ ] On `recorded > len(_MIGRATIONS)` **and** a structural mismatch — the
      legitimately-ahead / older-checkout case — `meta.schema_version` is left **unchanged**,
      verified by a test that stamps ahead *and* adds a structural difference, calls
      `ensure_db()`, and asserts the stamp still reads the higher value.
- [ ] Both branches log at WARNING and neither raises — verified by a test asserting
      `ensure_db()` returns normally in each case (a raise would be swallowed by
      `hooks/session_start.py:132-135`'s `contextlib.suppress(Exception)`).
- [ ] A test builds a "structurally-correct-at-N, stamped-above-N" fixture via
      `_bootstrap_schema_at(db, 43)` + `_stamp_version(conn, 45)` (with `_MIGRATIONS` still at
      43), calls `ensure_db()` once, and asserts the stamp is clamped down to 43 (a single call
      cannot both clamp and apply a migration that didn't exist yet when the clamp ran — see
      Fix's "nothing is re-run" design). The test then appends a probe migration
      (`CREATE TABLE probe (id INTEGER);`) and calls `ensure_db()` a second time, asserting the
      probe table now exists and `meta.schema_version` reads 44 — i.e. the clamp unblocks the
      *next* migration on a subsequent call, not the same one.
- [ ] A test asserts the clamp is a no-op for `recorded == len(_MIGRATIONS)` and
      `recorded < len(_MIGRATIONS)`, so normal and behind-by-N databases are unaffected. For
      the `==` case, assert the manifest guard is not reached at all (it must not cost ~5.0ms
      on the hot path) — e.g. by monkeypatching `_reference_manifest_at` to raise.
- [ ] `meta.last_rebuild_version` is untouched by this change (see Fix's out-of-scope note) —
      asserted in the clamp test.
- [ ] `cli/doctor.py`'s `_schema_drift_data()` error note no longer reads as pointing at an
      open bug: replace the `(see BUG-3255)` fragment with text describing the surviving
      mismatch case (a database genuinely ahead of this install), since the match case now
      self-heals on the next `ensure_db()`. No test asserts the literal substring.
- [ ] **Manual, one-shot:** this repo's `.ll/history.db` reads `schema_version = 43` after an
      `ll-*` invocation against the fixed code, repaired by the clamp with no manual step. Not a
      test, and it cannot be re-verified once it fires — because every project here is
      `local-editable`, the database will self-heal incidentally as soon as the fix exists in
      the working tree. The pre-fix state is captured at
      `postmortems/bug-3255-history-db-meta-before.json` (`schema_version=45`,
      `last_rebuild_version=43`, recorded 2026-08-18); diff against it to evidence the repair.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of ENH-3242's pre-implementation review (2026-08-18). ENH-3242 covers *detecting*
this state via its `ll-doctor` version guard; the repair decision is this issue.

## Status

- [ ] open


## Session Log
- `/ll:confidence-check` - 2026-08-18T23:24:55 - `7d37dca4-85e0-44bd-98a3-f5245bba41c6.jsonl`
- `/ll:confidence-check` - 2026-08-18T21:14:54 - `f6640f14-422f-4dbe-8922-f925a192302f.jsonl`
- `/ll:wire-issue` - 2026-08-18T20:46:21 - `44a85abf-b40c-4da8-961d-a5effae2f301.jsonl`
- `/ll:refine-issue` - 2026-08-18T20:29:15 - `6cc83876-f03b-40a3-88c3-eca5f080de05.jsonl`

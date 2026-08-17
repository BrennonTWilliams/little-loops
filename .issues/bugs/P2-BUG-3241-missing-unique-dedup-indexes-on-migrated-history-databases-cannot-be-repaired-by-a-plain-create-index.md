---
id: BUG-3241
type: BUG
title: Missing UNIQUE dedup indexes on migrated history databases cannot be repaired
  by a plain CREATE INDEX
priority: P2
status: done
testable: true
discovered_by: bug-3236-pre-implementation-review
discovered_date: '2026-08-17'
completed_at: 2026-08-17T00:00:00Z
labels:
- history-db
- session-store
- schema-drift
relates_to:
- BUG-3236
- ENH-3242
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3241: Missing UNIQUE dedup indexes on migrated history databases

## Summary

Independently of BUG-3236's `issue_sessions` view drift, a sweep of all 53 `.ll/history.db`
files on this machine finds three indexes missing from databases whose recorded
`schema_version` is well past the migration that creates them. The two UNIQUE ones are
load-bearing: they are what makes the `INSERT OR IGNORE` re-derivation in
`session_store.lifecycle.rebuild()` idempotent. Without them, idempotency is unenforced.

They are **not** repaired by BUG-3236's v42 migration, and they cannot be repaired by
simply appending `CREATE UNIQUE INDEX` — see [Root Cause](#root-cause).

## Current Behavior

| Index | Migration | Kind | Consequence of absence |
|---|---|---|---|
| `idx_assistant_messages_dedup` | v11 (`schema.py:306`) | UNIQUE | `INSERT OR IGNORE` idempotency for `assistant_messages` is unenforced |
| `idx_summary_nodes_retention_dedup` | v19 (`schema.py:484`) | UNIQUE | same, for `kind = 'retention'` summary nodes |
| `idx_summary_nodes_parent_id` | v10 (`schema.py:287`) | plain | DAG parent traversal unindexed |

The drift is widespread and not correlated with the `issue_sessions` drift: databases with
a perfectly correct `issue_sessions` view are missing indexes, and vice versa. Roughly two
dozen of the 53 local databases are missing at least one, spanning versions v12 through
v41.

Detection (do **not** compare `sqlite_master.sql` text — see BUG-3236's implementation
trap):

```python
import sqlite3
c = sqlite3.connect("file:.ll/history.db?mode=ro", uri=True)
have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
missing = {"idx_assistant_messages_dedup",
           "idx_summary_nodes_retention_dedup",
           "idx_summary_nodes_parent_id"} - have
```

## Expected Behavior

A database at the current `SCHEMA_VERSION` has every index its migration history creates,
or the discrepancy is detected and repaired — without any `ll-*` command hard-failing at
startup.

## Steps to Reproduce

1. On any `.ll/history.db` whose recorded `meta.schema_version` is past migration v11
   (`idx_assistant_messages_dedup`) and v19 (`idx_summary_nodes_retention_dedup`), run the
   detection snippet from [Current Behavior](#current-behavior):
   ```python
   import sqlite3
   c = sqlite3.connect("file:.ll/history.db?mode=ro", uri=True)
   have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
   missing = {"idx_assistant_messages_dedup",
              "idx_summary_nodes_retention_dedup",
              "idx_summary_nodes_parent_id"} - have
   ```
2. Observe `missing` is non-empty even though `schema_version` claims the creating
   migrations already ran.
3. Attempt the naive repair — append `CREATE UNIQUE INDEX IF NOT EXISTS
   idx_assistant_messages_dedup ON assistant_messages(session_id, ts, content);` as a new
   migration and run `ensure_db()` against a copy of the database seeded with a duplicate
   `(session_id, ts, content)` row.
4. Observe `_apply_migrations()` raises `sqlite3.IntegrityError`, rolls back the whole
   migration, and `ensure_db()` propagates the exception — every `ll-*` command on that
   project now hard-fails at startup.

## Root Cause

Two separate questions, and only the second is settled.

**Why they are missing: undetermined.** All three are created with
`CREATE [UNIQUE] INDEX IF NOT EXISTS` inside migrations that certainly ran (the databases
are past those versions), and `_apply_migrations()` runs each migration inside a single
`BEGIN IMMEDIATE` with `ROLLBACK` on any exception, so a partial apply cannot happen under
today's code. As with BUG-3236, the most likely explanation is a working-tree-only revision
of the migration body executing in a `local-editable` project, but unlike BUG-3236 there is
no surviving artifact to prove it. Do not spend implementation time re-litigating this; the
repair does not depend on the answer.

**Why the obvious repair is unsafe: settled.** Appending
`CREATE UNIQUE INDEX IF NOT EXISTS ...` to a new migration fails outright on any database
that accumulated duplicate rows while the index was missing. `_apply_migrations()` rolls
back the whole migration and re-raises, `ensure_db()` propagates, and **every `ll-*`
command on that project hard-fails at startup** — converting a silent, low-impact
correctness gap into a total outage for that project. That asymmetry is the entire reason
this was split out of BUG-3236 rather than folded into its v42 migration.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/session_store/schema.py` — append one new entry to `_MIGRATIONS: list[str]` (defined `schema.py:111`), following the `_apply_migrations()`/`ensure_db()` mechanics at `schema.py:1081` and `schema.py:1120`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/schema.py:21` — `SCHEMA_VERSION` constant must be bumped 42 → 43 by hand. `_apply_migrations()` drives entirely off `len(_MIGRATIONS)` (`schema.py:1096`); `SCHEMA_VERSION` is a separate, hand-maintained int nothing in `schema.py` asserts equal to `len(_MIGRATIONS)`. Appending the migration without bumping this constant silently desyncs the two. [Agent 2 finding]

### Dependent Files (Callers/Consumers of the affected indexes)
- `scripts/little_loops/session_store/writers.py:3021-3068` — `_backfill_assistant_messages()`, `INSERT OR IGNORE` at `writers.py:3064-3068`, relies on `idx_assistant_messages_dedup` for idempotency during `rebuild()`
- `scripts/little_loops/session_store/lifecycle.py:1152-1227` — `compact()`; its rowcount-based `INSERT OR IGNORE` + fallback `SELECT` (`lifecycle.py:1204-1220`) relies on `idx_summary_nodes_retention_dedup`; without it, repeated `compact()` runs over the same session/date-range insert new duplicate `retention` rows instead of reusing the prior one — idempotency degrades to silent duplicate accumulation rather than raising
- `scripts/little_loops/session_store/lifecycle.py:928` — `rebuild()`, wipes `_REBUILD_TABLES` (includes `assistant_messages`, `summary_nodes`, `summary_spans`) and replays `raw_events` through the `_backfill_*` parsers above
- `scripts/little_loops/hooks/session_start.py:132-135` — wraps `ensure_db()` in `contextlib.suppress(Exception)`; a stuck migration here is currently swallowed with no logging
- `scripts/little_loops/history_reader.py:422-438` — `_connect_readonly()` catches `sqlite3.Error` around `ensure_db(db_path)`, logs a WARNING, returns `None`; downstream readers see "no connection" rather than the underlying migration failure

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py` — re-export hub for `_MIGRATIONS`, `SCHEMA_VERSION`, `ensure_db`, `_apply_migrations` (lines 96-110, 117-161); no code change needed but confirms the blast radius below [Agent 1 finding]
- 45 CLI entry points call `cli_event_context()`, which calls `ensure_db()` at startup — representative examples: `scripts/little_loops/cli/history.py`, `scripts/little_loops/cli/doctor.py`, `scripts/little_loops/cli/session.py`, `scripts/little_loops/cli/compact_session.py`; this is the concrete mechanism behind "every `ll-*` command hard-fails at startup" in this issue's Root Cause section — no per-file change needed, but confirms the failure-mode scope is the full CLI surface, not just the session-store internals [Agent 1 finding]

### Conventions in Force
- Migrations in `_MIGRATIONS` are idempotent multi-statement SQL strings using `IF NOT EXISTS` (or `DROP ... IF EXISTS` + unconditional `CREATE` for views, since SQLite has no `CREATE VIEW IF NOT EXISTS`) — evidence: `schema.py:111-997` throughout.
- The one existing "dedup rows before creating a UNIQUE index" migration, v36/ENH-2771 (`schema.py:851-885`), orders its statements as backfill → dedup `DELETE` (via `ROW_NUMBER() OVER (PARTITION BY ...) ORDER BY ts ASC`, keeping the earliest `ts`) → `DROP INDEX IF EXISTS` → `CREATE UNIQUE INDEX IF NOT EXISTS`, and its own comment states this ordering is load-bearing.
- Plain (non-UNIQUE) index migrations never pair with a dedup `DELETE` anywhere in `_MIGRATIONS` — evidence: `idx_summary_nodes_parent_id` at v10 (`schema.py:287-288`), `idx_issue_events_session_id` at v16 (`schema.py:371`).
- `_apply_migrations()` wraps the entire pending range (not each migration individually) in one `BEGIN IMMEDIATE` / rollback-on-`BaseException` transaction (`schema.py:1050-1086`); statements are split on `;` via `_split_sql_statements()` (`schema.py:1020`) rather than `executescript()`, deliberately, since `executescript()`'s implicit commit would drop the write lock mid-sequence.

### Tests
- `scripts/tests/test_session_store_schema.py` — per-version migration test classes (e.g. `TestSchemaV9`, `TestSchemaV10`, `TestSchemaV12`, `TestSchemaV27`); the `_bootstrap_schema_at(db, version)` helper (`test_session_store_schema.py:1134-1154`) replays real `_MIGRATIONS[:version]` entries to construct an old-schema-version fixture — the established convention for this kind of test. A byte-identical copy of this helper exists in `scripts/tests/test_session_store_writers.py:1045-1065` (not shared between the two files).
- No existing test in `scripts/tests/` inserts duplicate rows that violate a not-yet-created UNIQUE index and asserts repair — this is new fixture territory the regression-test AC requires. `test_dedup_on_source_path_and_line_no` (`test_session_store_schema.py:945-968`) is the nearest existing test but covers application-level idempotency (calling `backfill_raw_events` twice), not pre-existing duplicate rows at the migration/SQL level.

_Wiring pass added by `/ll:wire-issue`:_
- Bumping `SCHEMA_VERSION` breaks 21 hardcoded `assert SCHEMA_VERSION == 42` literals across three files that must be updated to `43`: 15 in `scripts/tests/test_session_store_schema.py` (lines 650, 664-665, 716-717, 795, 812-813, 1034-1035, 1075-1076, 1130, 1413, 1453, 1497, 1547, 1622, 1682, 1750, 1815, 1883, 1928, 1983), 5 in `scripts/tests/test_session_store_writers.py` (lines 470-471, 1153, 1283, 1540, 1738), and 1 in `scripts/tests/test_assistant_messages.py:88` (`test_schema_version_is_12`) — this last file was not previously listed and is not otherwise in scope for this issue [Agent 2 + Agent 3 findings]
- `scripts/tests/test_session_store_lifecycle.py:1486` — asserts `int(row["value"]) == SCHEMA_VERSION` dynamically (references the constant, not a literal); no edit needed, but its `TestCompact` class (from line 1806) has no coverage of duplicate `summary_nodes` rows colliding on `(session_id, ts_start, ts_end) WHERE kind='retention'` — closest gap to the FK-repointing risk already flagged in this issue's Codebase Research Findings [Agent 3 finding]
- Fixture pattern to model the new regression test on: combine `_bootstrap_schema_at()` (bootstrap at the version before the new migration) with the insert-then-upgrade shape of `TestSchemaV15SkillCompletionColumns.test_v14_db_upgrades_preserving_dispatch_only_rows` (`test_session_store_schema.py:1170-1198`) — insert duplicate rows under the old schema, then run `ensure_db()` and assert survivors + index existence. `TestSchemaV42IssueSessionsRepair.test_issue_sessions_view_repaired_on_drifted_db` (`test_session_store_schema.py:2040-2094`) is the closest existing "drifted DB gets repaired by `ensure_db()`" precedent, using a `_stamp_version()` helper (`test_session_store_schema.py:2012`) [Agent 3 finding]
- No existing test asserts `raw_events.summary_node_id` behavior when the `summary_nodes` row it references is deleted (the dangling-FK risk already flagged in this issue's Codebase Research Findings); `raw_events.REFERENCES summary_nodes(id)` (`schema.py:480-481`) is declarative-only — no `PRAGMA foreign_keys=ON` observed in these tests [Agent 3 finding]

### Behavior Parity
N/A — no existing file is being rewritten, deleted, or delegated away; this is an additive migration.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:8883,8887` — states "Current schema version: 38" and `SCHEMA_VERSION, # 38`; already 4 versions stale before this issue, widens to 5. Not test-enforced; optional to update alongside this change. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md:56` and its `| Version | Issue | Adds |` table (lines 58-99) — stops at v40, would go 3 versions behind once this issue's migration lands. Not test-enforced. [Agent 2 finding]
- `docs/ARCHITECTURE.md:621-662` — a separate `| Version | Object | Purpose |` table, stops at v38 and individually documents `idx_assistant_messages_dedup` at v11 (`ARCHITECTURE.md:635`) without noting a later migration had to repair it. Not test-enforced. [Agent 2 finding]

## Program Design

### Types

N/A — no new Python types; the fix is a plain SQL string appended to the existing
`_MIGRATIONS` list (`schema.py`).

### Signatures

- `_MIGRATIONS: list[str]` — append one new entry (v43): FK repoint `UPDATE` + dedup
  `DELETE` + `CREATE UNIQUE INDEX IF NOT EXISTS` for the two UNIQUE indexes, plus a blanket
  `CREATE INDEX IF NOT EXISTS` re-assertion of every non-UNIQUE index. Executed the same way
  every other entry is. Exact SQL in [Proposed Solution](#proposed-solution).

### Call Path

`ensure_db()` -> `_apply_migrations()` -> `_MIGRATIONS` (new dedup-then-index migration
entry, inside the same `BEGIN IMMEDIATE` / `ROLLBACK`-on-exception transaction as every
other migration)

## Proposed Solution

One new migration (v43), standalone — see [Scope](#scope-relative-to-enh-3242). The two
UNIQUE indexes need a dedup pass first; the plain indexes do not.

**Survivor rule (settled — do not re-open):** `MIN(rowid)` for `assistant_messages`,
`MIN(id)` for `summary_nodes`. The `ROW_NUMBER() ... ORDER BY ts ASC` form of the v36
precedent (`schema.py:851-885`) is **not** reusable here: `summary_nodes` has no `ts`
column, and its `ts_start`/`ts_end` are themselves *inside* the dedup key, so a `ts`
ordering is undefined for that table. What v36 *is* the precedent for is the NULL guard
(`WHERE issue_num IS NOT NULL` on both its DELETE and its index, `schema.py:874-884`) —
that part is load-bearing here, see below.

### `assistant_messages` — dedup, then UNIQUE index

Safe as the simple form: all three key columns are `NOT NULL` (`schema.py:297-303`), the
key covers every meaningful column, and nothing holds an FK-shaped reference to
`assistant_messages.id`. No NULL guard and no repoint step needed.

```sql
DELETE FROM assistant_messages
 WHERE rowid NOT IN (
   SELECT MIN(rowid) FROM assistant_messages
    GROUP BY session_id, ts, content
 );
CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_messages_dedup
    ON assistant_messages(session_id, ts, content);
```

### `summary_nodes` — repoint FKs, dedup, then UNIQUE index

**The `assistant_messages` shape must NOT be copied verbatim to this table.** It is wrong
in two independent ways, each of which destroys data:

1. **Scope to `kind = 'retention'`.** The index is *partial*
   (`WHERE kind = 'retention'`, `schema.py:484-485`). An unscoped
   `GROUP BY session_id, ts_start, ts_end` also groups `leaf` and `condensed` rows, which
   share those exact key columns under their own partial index
   (`idx_summary_nodes_leaf_dedup`, `schema.py:283-284`). Leaf rows carry live
   `summary_spans` children and `parent_id` edges, so deleting one shreds the summary DAG —
   damage entirely outside what this issue set out to repair.
2. **Exclude NULL keys.** `session_id`, `ts_start`, `ts_end` are all nullable
   (`schema.py:273-275`), and a NULL `session_id` is a real, expected value for retention
   rows: `compact()` buckets by `row["session_id"]` typed `str | None`
   (`lifecycle.py:1193`) and its fallback lookup uses `session_id IS ?`
   (`lifecycle.py:1215-1217`) precisely to handle it. SQLite treats NULLs as **distinct**
   in a UNIQUE index, so such rows can never violate it — but `GROUP BY` treats NULLs as
   **equal**, so an unguarded DELETE removes rows the index would have accepted. Pure
   gratuitous loss.

Repoint before deleting (`raw_events.summary_node_id`, `schema.py:480-481`, points into
exactly the `kind = 'retention'` subset this DELETE targets — populated by `compact()` at
`lifecycle.py:1211-1227`):

```sql
-- 1. repoint FK references from each non-survivor to its group's survivor
UPDATE raw_events
   SET summary_node_id = (
     SELECT MIN(s2.id) FROM summary_nodes s2
      WHERE s2.kind = 'retention'
        AND s2.session_id IS (SELECT s1.session_id FROM summary_nodes s1
                               WHERE s1.id = raw_events.summary_node_id)
        AND s2.ts_start = (SELECT s1.ts_start FROM summary_nodes s1
                            WHERE s1.id = raw_events.summary_node_id)
        AND s2.ts_end   = (SELECT s1.ts_end   FROM summary_nodes s1
                            WHERE s1.id = raw_events.summary_node_id)
   )
 WHERE summary_node_id IS NOT NULL
   AND EXISTS (SELECT 1 FROM summary_nodes s1
                WHERE s1.id = raw_events.summary_node_id
                  AND s1.kind = 'retention'
                  AND s1.ts_start IS NOT NULL AND s1.ts_end IS NOT NULL);

-- 2. delete non-survivors, scoped to retention AND to non-NULL keys
DELETE FROM summary_nodes
 WHERE kind = 'retention'
   AND session_id IS NOT NULL AND ts_start IS NOT NULL AND ts_end IS NOT NULL
   AND id NOT IN (
     SELECT MIN(id) FROM summary_nodes
      WHERE kind = 'retention'
        AND session_id IS NOT NULL AND ts_start IS NOT NULL AND ts_end IS NOT NULL
      GROUP BY session_id, ts_start, ts_end
   );

-- 3. create the index
CREATE UNIQUE INDEX IF NOT EXISTS idx_summary_nodes_retention_dedup
    ON summary_nodes(session_id, ts_start, ts_end) WHERE kind = 'retention';
```

Note the asymmetry between steps 1 and 2: the repoint uses `IS` for `session_id` (so
NULL-session retention rows still get repointed if their group is collapsed), while the
DELETE excludes NULL keys entirely (because those rows are never collapsed). Since step 2
never deletes a NULL-`session_id` row, step 1's NULL-tolerant match is harmless — but the
two must not be "simplified" into using the same predicate.

**The three statements above were executed against a synthetic drifted database** (real
`summary_nodes`/`raw_events` DDL; a duplicate `retention` pair, a NULL-`session_id`
`retention` pair, a colliding `leaf` pair, and `raw_events` rows pointing at both
non-survivors). Confirmed: the lower-`id` retention row survives and its duplicate is
deleted; both NULL-`session_id` rows survive; both `leaf` rows survive; the `raw_events`
reference is repointed to the survivor; zero dangling `summary_node_id` values remain; a
second run is a no-op. The `CREATE UNIQUE INDEX` also succeeded *with the NULL-key duplicate
pair still present*, which is the direct demonstration of the NULL-distinct semantics
argued above.

**Complete repoint surface — verified, do not widen.** `raw_events.summary_node_id` is the
only reference at risk. The other two references into `summary_nodes.id` never point at
`retention` rows: `summary_spans.summary_id` (`schema.py:279`) is written only for
`kind = 'leaf'` (`lifecycle.py:293-303`), and `parent_id` (`schema.py:272`) is set only on
`leaf`/`condensed` rows (`lifecycle.py:326-327`, `657-662`).

### Plain indexes — re-assert all of them, not just the one observed missing

`idx_summary_nodes_parent_id` is the only *observed*-missing plain index, but the
three-index list in [Current Behavior](#current-behavior) is what a sweep of this machine
found — not the complete v42 index inventory. Because `CREATE INDEX IF NOT EXISTS` on a
non-UNIQUE index cannot fail, the migration should re-assert **every** non-UNIQUE index the
schema defines, repairing unobserved drift at zero added risk. The two UNIQUE ones stay
explicit with their dedup passes above; do **not** blanket re-assert UNIQUE indexes, which
is precisely the hard-failure mode this issue exists to avoid.

### Scope relative to ENH-3242

Ships as its own migration (v43). ENH-3242 is a *detector* — a checked-in structural
manifest plus an on-demand check — not a repairer, so it cannot subsume this work.
BUG-3241 repairs the known drift; ENH-3242 later makes the next instance loud.

### Remaining open question

- **Cost on large tables.** The `DELETE ... GROUP BY` is a full scan plus a temp B-tree,
  and it runs inside the startup write lock on every project at next `ensure_db()`. 68,693
  rows on this checkout is trivial; confirm the shape is acceptable before assuming it
  holds for a much larger database.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Bump `SCHEMA_VERSION` at `scripts/little_loops/session_store/schema.py:21` from `42` to `43` by hand — it is not derived from `len(_MIGRATIONS)`.
- Update the 21 hardcoded `assert SCHEMA_VERSION == 42` literals to `43`: 15 in `scripts/tests/test_session_store_schema.py`, 5 in `scripts/tests/test_session_store_writers.py`, 1 in `scripts/tests/test_assistant_messages.py:88`. See exact line numbers in Integration Map → Tests.
- Write the new regression test using the `_bootstrap_schema_at()` + insert-duplicate-rows-then-`ensure_db()` pattern described in Integration Map → Tests.
- Add a one-line guard test asserting `SCHEMA_VERSION == len(_MIGRATIONS)`. Verified absent:
  the only references to `len(_MIGRATIONS)` anywhere in `scripts/` are
  `session_store/schema.py:1096`, `schema.py:1104`, and the parallel pair in
  `queue_store.py:172,180` — no test asserts the equality. Since hand-desync of these two
  is the trap flagged above, this makes the whole failure class loud instead of silent.
- BUG-3236 has **landed** (`4beb93b2`): v42 is present in `_MIGRATIONS`,
  `TestSchemaV42IssueSessionsRepair` exists, and `SCHEMA_VERSION == len(_MIGRATIONS) == 42`
  is confirmed on `main`. The "sequence after BUG-3236" constraint is already satisfied — no
  further sequencing work.
- Scope question ("own migration vs. part of ENH-3242") is **settled**: standalone v43. See
  Proposed Solution → Scope relative to ENH-3242.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Dangling FK risk in `summary_nodes` dedup delete, not currently listed as an open question**: `raw_events.summary_node_id` (`ALTER TABLE raw_events ADD COLUMN summary_node_id INTEGER`, `scripts/little_loops/session_store/schema.py:480`) is a live reference into `summary_nodes.id`, populated by `compact()` (`scripts/little_loops/session_store/lifecycle.py:1211-1227`) for `kind = 'retention'` rows specifically — the exact `summary_nodes` subset this issue's dedup delete targets. A `MIN(rowid)`-only delete (as currently drafted) removes non-survivor `summary_nodes` rows without checking whether any `raw_events.summary_node_id` points at them, which would orphan those references. Any dedup delete on `summary_nodes` must first repoint `raw_events.summary_node_id` from each non-survivor id to its group's survivor id, before deleting the non-survivor rows. **Resolved** — repoint `UPDATE` drafted in [Proposed Solution](#summary_nodes--repoint-fks-dedup-then-unique-index), and the repoint surface verified complete at `raw_events.summary_node_id` alone (`summary_spans.summary_id` and `parent_id` never reference `retention` rows).
- **Existing precedent uses `ROW_NUMBER() OVER (PARTITION BY ...) ORDER BY ts ASC`, not `MIN(rowid)`**: the only existing "dedup-then-unique-index" migration in this codebase, v36/ENH-2771 (`scripts/little_loops/session_store/schema.py:851-885`), selects its survivor via `ROW_NUMBER() OVER (PARTITION BY issue_num, transition ORDER BY ts ASC) ... WHERE rn = 1`, keeping the earliest `ts` — not `MIN(rowid)`. Its own comment (`schema.py:838-848`) states the ordering (backfill, then dedup DELETE, then `DROP INDEX IF EXISTS` + `CREATE UNIQUE INDEX IF NOT EXISTS`) is load-bearing. `MIN(rowid)` and `ROW_NUMBER() ... ORDER BY ts ASC` are not necessarily equivalent (`rowid` order need not match `ts` order on a table that has had rows deleted/reinserted), so reusing the `ROW_NUMBER()`/`ts`-ordered form matches the one precedent this codebase has already reasoned through, rather than introducing a second, differently-ordered survivor rule. **Superseded** — the `ts`-ordered form is not applicable to `summary_nodes`, which has no `ts` column and whose `ts_start`/`ts_end` sit *inside* the dedup key. Settled rule is `MIN(rowid)`/`MIN(id)`; what v36 *is* the binding precedent for here is its NULL guard, not its ordering. See [Proposed Solution](#proposed-solution).
- **`_apply_migrations()` only ever runs the pending range**: `_apply_migrations()` (`scripts/little_loops/session_store/schema.py:1050-1086`) loops `for index in range(version, len(_MIGRATIONS))` — it does not re-run already-applied entries. Because the affected databases have `schema_version` already recorded past v11/v19 (that is this issue's premise), a newly appended migration runs standalone; it does not re-execute the original v11/v19 statements. The existing `assistant_messages`/`summary_nodes` table rows are untouched by re-running v11/v19 — only the new appended migration's own statements execute.
- **No FK risk for `assistant_messages`**: its columns (`id, ts, content, session_id, tool_use_count`; `schema.py:297-303`) are exactly the dedup key (`session_id, ts, content`) plus one non-key column, and no other table holds a foreign-key-shaped reference to `assistant_messages.id` — a `MIN(rowid)` (or `ROW_NUMBER()`/`ts`-ordered) delete is safe there with no repointing step needed.

## Impact

- **Priority**: P2 — real but currently latent. Measured on this checkout: zero duplicate
  groups in `assistant_messages` (68,693 rows) and `summary_nodes` (0 rows), i.e. the
  missing index has not yet cost anything here. The exposure is that nothing prevents it,
  and a naive repair attempt is far more damaging than the defect.
- **Interaction with BUG-3236**: BUG-3236's `SCHEMA_VERSION` bump triggers a
  `rebuild()` on every project at next SessionStart, and that rebuild's `INSERT OR IGNORE`
  is exactly the path these indexes protect. A rebuild has already run at v41 on this
  checkout's database *without* `idx_assistant_messages_dedup` and produced zero
  duplicates, so the replay path appears not to emit them — but that is one observation,
  not a guarantee.
- **Breaking Change**: No, if implemented as specified. Yes, catastrophically, if
  implemented as a bare `CREATE UNIQUE INDEX`.

## Acceptance Criteria

- [ ] A database carrying duplicate `(session_id, ts, content)` rows in
      `assistant_messages` is repaired by `ensure_db()` — duplicates removed, UNIQUE index
      created — without raising.
- [ ] A database already carrying the indexes is unaffected (idempotent, no row deletions).
- [ ] All three indexes are present after `ensure_db()` on a database stamped at a version
      past their creating migrations but structurally missing them.
- [ ] A regression test constructs the duplicate-rows case explicitly; it must not rely on
      any local database happening to be clean.
- [ ] The `summary_nodes` dedup does not delete any `leaf` or `condensed` row, and does not
      delete any `retention` row whose `(session_id, ts_start, ts_end)` contains a NULL —
      SQLite's UNIQUE index accepts those, so the repair must too.
- [ ] After repair, no `raw_events.summary_node_id` references a deleted `summary_nodes.id`:
      every non-NULL `summary_node_id` resolves to an existing row.
- [ ] `SCHEMA_VERSION == len(_MIGRATIONS)` is asserted by a test.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of BUG-3236 during its pre-implementation review. BUG-3236 documents the
`sqlite_master.sql` text-comparison trap that applies to any structural check written here.

## Status

- [ ] open


## Session Log
- `/ll:ready-issue` - 2026-08-17T19:27:10 - `676a273b-145a-4506-854d-a60a012321cb.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:24:22 - `35d64d8e-092e-4c90-875f-40feb688fbd4.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:06:24 - `3098ae6c-d494-47ea-a3e0-bfd1d90e6eaf.jsonl`
- `/ll:wire-issue` - 2026-08-17T18:58:52 - `4375f1ee-af64-420b-8e51-de7f17563fd4.jsonl`
- `/ll:refine-issue` - 2026-08-17T18:44:49 - `73e92a5b-b52b-41fd-896b-d930c6b15dc8.jsonl`
- `/ll:format-issue` - 2026-08-17T18:39:06 - `73e92a5b-b52b-41fd-896b-d930c6b15dc8.jsonl`

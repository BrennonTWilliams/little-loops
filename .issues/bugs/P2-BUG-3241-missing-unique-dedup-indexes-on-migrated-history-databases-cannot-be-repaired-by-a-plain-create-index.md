---
id: BUG-3241
type: BUG
title: Missing UNIQUE dedup indexes on migrated history databases cannot be repaired
  by a plain CREATE INDEX
priority: P2
status: open
testable: true
discovered_by: bug-3236-pre-implementation-review
discovered_date: '2026-08-17'
labels:
- history-db
- session-store
- schema-drift
relates_to:
- BUG-3236
- ENH-3242
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

## Proposed Solution

A migration that deletes duplicates before creating each UNIQUE index, keeping the
lowest `rowid` of each duplicate group:

```sql
DELETE FROM assistant_messages
 WHERE rowid NOT IN (
   SELECT MIN(rowid) FROM assistant_messages
    GROUP BY session_id, ts, content
 );
CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_messages_dedup
    ON assistant_messages(session_id, ts, content);
```

with the analogous pair for `idx_summary_nodes_retention_dedup`, and a plain
`CREATE INDEX IF NOT EXISTS` for `idx_summary_nodes_parent_id` (no dedup needed — a
non-UNIQUE index cannot fail on duplicate rows).

Open questions for implementation:

- **Cost on large tables.** The `DELETE ... GROUP BY` is a full scan plus a temp B-tree.
  68,693 rows on this checkout is trivial; confirm the shape is acceptable before assuming
  it holds for a much larger database, since it runs inside the startup write lock.
- **`MIN(rowid)` as the survivor.** Correct for `assistant_messages`, where duplicate rows
  are byte-identical by construction (the index key covers every meaningful column).
  Verify the same holds for `summary_nodes` retention rows before reusing the pattern —
  if those rows carry columns outside the index key, picking an arbitrary survivor is a
  silent data decision, not a no-op.
- Whether this ships as its own migration or as part of ENH-3242's general structural
  repair. Sequence after BUG-3236 either way.

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
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of BUG-3236 during its pre-implementation review. BUG-3236 documents the
`sqlite_master.sql` text-comparison trap that applies to any structural check written here.

## Status

- [ ] open

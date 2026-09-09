---
target: sqlite3
date: '2026-09-08'
status: proven
assertions:
- claim: with isolation_level=None, conn.in_transaction stays False immediately after an INSERT (no implicit transaction), unlike default isolation level where it is True until commit
  result: pass
- claim: in WAL mode, a reader connection can SELECT successfully while a separate writer connection holds an open, uncommitted BEGIN IMMEDIATE transaction
  result: pass
- claim: a second writer attempting BEGIN IMMEDIATE while another write transaction is open blocks (not immediate error) up to PRAGMA busy_timeout, then raises sqlite3.OperationalError once the timeout elapses
  result: pass
- claim: PRAGMA table_info(table) on a table with a composite primary key numbers the pk column 1-based by key-column position, not as a plain boolean
  result: pass
- claim: ATTACH DATABASE 'other.db' AS other lets a single connection query other.table alongside main tables
  result: pass
- claim: UNION ALL + SUM() across main.t and other.t in one query aggregates rows from both attached databases
  result: pass
- claim: Python's sqlite3 foreign_keys pragma defaults to 0 (off) per-connection, even on a build with FK support compiled in
  result: pass
- claim: INSERT ... ON CONFLICT(col) DO UPDATE SET ... RETURNING * performs an upsert and returns the affected row
  result: pass
- claim: ATTACH DATABASE on a nonexistent file path creates the file lazily only on first write, not at ATTACH time
  result: fail
- claim: 'ATTACH DATABASE ''file:<path>?mode=ro'' AS r0 on a sqlite3.connect('':memory:'', uri=True) connection works, including for a WAL-mode source; an INSERT into r0.<table> raises "attempt to write a readonly database"'
  result: pass
- claim: An unqualified SELECT ... FROM t resolves to a persistent main.t VIEW defined as a UNION ALL over attached-schema tables (e.g. r0.t, r1.t), even though r0.t/r1.t tables exist
  result: fail
- claim: 'CORRECTIVE (supersedes the claim above): SQLite rejects CREATE VIEW main.<name> outright when the view body references any attached-database object at all (error "view <name> cannot reference objects in database <schema>") -- this applies even to a single attached schema, not just multi-schema UNION ALL. Only CREATE TEMP VIEW can span attached schemas; an unqualified SELECT then resolves to that temp view per the temp -> main -> attached search order'
  result: pass
- claim: A CREATE TEMP VIEW spanning attached schemas (the corrected mechanism) remains queryable after PRAGMA query_only = ON, which blocks further CREATE statements
  result: pass
- claim: PRAGMA r0.table_info(<view>) returns the column list for a view defined inside an attached schema
  result: pass
- claim: conn.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED) returns 10 here; conn.setlimit(...) can lower it but cannot raise it above the compile-time max (a setlimit above the max is silently clamped back to the max)
  result: pass
raw_output_path: .ll/learning-tests/raw/sqlite3.txt
---

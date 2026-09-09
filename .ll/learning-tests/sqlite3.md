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
raw_output_path: .ll/learning-tests/raw/sqlite3.txt
---

---
target: libsql
date: '2026-09-22'
status: proven
assertions:
- claim: libsql.connect(database=path) returns a Connection, not a sqlite3.Connection
    subclass, supporting execute/cursor/commit/rollback/close
  result: pass
- claim: Connection.execute() returns a Cursor with fetchone/fetchall/description/lastrowid/rowcount
  result: pass
- claim: fetched rows are plain tuples with no named/dict-like access, no default
    row factory
  result: pass
- claim: cursor.lastrowid reflects the inserted rowid after INSERT; cursor.rowcount
    reflects affected rows after UPDATE/DELETE
  result: pass
- claim: Connection.in_transaction toggles across execute()/commit(), and writes
    are visible via a fresh connection after commit()
  result: pass
- claim: invalid SQL and constraint violations raise libsql.Error, not sqlite3.Error
    or a subclass of it
  result: fail
- claim: connect() works with a bare local path or ':memory:' without requiring
    auth_token or other remote-only kwargs
  result: pass
raw_output_path: .ll/learning-tests/raw/libsql.txt
---

---
target: sqlite3
date: '2026-07-20'
status: proven
assertions:
- claim: UNIQUE constraint + INSERT OR IGNORE is idempotent (duplicate insert is a silent no-op, no exception)
  result: pass
- claim: cursor.rowcount is 1 on a genuine insert and 0 when INSERT OR IGNORE hits a UNIQUE conflict
  result: pass
- claim: UPDATE against a WHERE clause matching zero rows leaves cursor.rowcount at 0 (safe best-effort update pattern)
  result: pass
- claim: ALTER TABLE ADD COLUMN leaves the new column NULL on pre-existing rows
  result: pass
- claim: sqlite3.Row supports dict-like column access by name
  result: pass
raw_output_path: .ll/learning-tests/raw/sqlite3.txt
---

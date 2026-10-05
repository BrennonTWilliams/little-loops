---
target: SQLite
date: '2026-10-05'
status: proven
assertions:
- claim: 'a file:<path>?mode=ro URI with uri=True opens an existing database for reads and rejects writes with OperationalError'
  result: pass
- claim: 'a mode=ro URI on a missing path raises OperationalError and does not create the file'
  result: pass
- claim: 'plain sqlite3.connect(str(path)) without uri creates a missing database file'
  result: pass
- claim: 'an unescaped ''?'' in the path of a file: URI truncates the path at the ''?'' and creates or opens a different database'
  result: pass
- claim: 'an unescaped ''#'' in the path of a file: URI truncates the path at the ''#'' and opens a different (empty) database'
  result: pass
- claim: 'an unescaped ''%41'' in the path of a file: URI is percent-decoded and targets a different path'
  result: pass
- claim: 'urllib.parse.quote(path) or Path.as_uri() escaping opens the correct database for paths containing ''?'', ''#'', ''%41'' and spaces'
  result: pass
raw_output_path: .ll/learning-tests/raw/sqlite.txt
---

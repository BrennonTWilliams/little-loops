---
target: SQLite FTS5
date: '2026-10-06'
status: proven
assertions:
- claim: FTS5 virtual tables are available in the Python sqlite3 build
  result: pass
- claim: UNINDEXED columns are stored and returned in results but are not searchable via MATCH
  result: pass
- claim: bm25() returns negative scores and ORDER BY ascending puts the best match first
  result: pass
- claim: an unquoted hyphenated token like BUG-3761 raises OperationalError, while the quoted phrase matches
  result: pass
- claim: invalid MATCH syntax (unbalanced quote) raises sqlite3.OperationalError
  result: pass
- claim: the default tokenizer matches case-insensitively
  result: pass
- claim: a WHERE filter on an UNINDEXED column can be combined with MATCH
  result: pass
raw_output_path: .ll/learning-tests/raw/sqlite-fts5.txt
---

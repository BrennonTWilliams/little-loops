---
target: sql.js
date: '2026-08-25'
status: proven
assertions:
- claim: initSqlJs({wasmBinary}) initializes the engine and issues no fetch() during
    init
  result: pass
- claim: without wasmBinary, sql.js resolves the .wasm through locateFile — the file://
    fetch that must be avoided
  result: pass
- claim: DecompressionStream('gzip') inflates a gzipped SQLite file to byte-identical
    bytes
  result: pass
- claim: new SQL.Database(inflatedBytes) opens the inflated snapshot and exposes only
    the CTAS-projected columns
  result: pass
- claim: sql.js executes DELETE against the in-memory DB — there is no built-in read-only
    mode
  result: pass
- claim: db.exec() runs every semicolon-separated statement in one call, so a leading-SELECT
    check alone is insufficient
  result: pass
- claim: re-instantiating new SQL.Database(embeddedBytes) restores mutated rows — the
    "reset snapshot" action works
  result: pass
- claim: PRAGMA query_only=1 makes sql.js reject writes at the engine level ("attempt
    to write a readonly database")
  result: pass
- claim: PRAGMA query_only is reversible from the query box — a guardrail, not a boundary
  result: pass
- claim: sql-wasm.wasm 1.14.2 is 658410 bytes raw / 877880 base64; glue 46535 bytes;
    fixed floor ~924 KB per artifact
  result: pass
- claim: the same behaviour holds in a browser opened over file:// (proof ran under
    node v22.22.3, not a browser)
  result: untested
raw_output_path: .ll/learning-tests/raw/sqljs.txt
---

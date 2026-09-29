---
target: hrana-http
date: '2026-09-28'
status: proven
assertions:
- claim: '`/v3/pipeline` is drivable with stdlib `http.client` POST + Bearer auth
    on both endpoints; `execute` returns typed `cols`/`rows`/`affected_row_count`/`last_insert_rowid`,
    `baton` and `base_url` are null after a `close` request (one HTTP round trip per
    execute)'
  result: pass
- claim: 'a non-null `baton` continues the same server-side stream: an uncommitted
    row is visible on the same baton, invisible to a fresh stream, and visible to
    all after `commit` sent with the baton'
  result: pass
- claim: an atomic `batch` with step conditions (`begin`, conditional inserts, conditional
    `commit`, `not ok` conditional `rollback`) rolls back on a failed step, skips
    the commit, and leaks no rows; the all-success batch commits both rows
  result: pass
- claim: database errors carry a structured `error.code` with no message matching
    (constraint `SQLITE_CONSTRAINT`, parse error `SQL_PARSE_ERROR`, missing table
    `SQLITE_UNKNOWN`) identically on sqld and Turso; NOT NULL and PRIMARY KEY violations
    share `SQLITE_CONSTRAINT`
  result: pass
- claim: 'authentication failure is a structured HTTP status, not message text (Turso:
    empty token 401, malformed JWT 400; read-only token write is a 200 with code `BLOCKED`);
    proven on Turso only because the local sqld runs unauthenticated'
  result: pass
- claim: 'an expired stream is reported with a distinct `STREAM_EXPIRED` code on both
    endpoints (sqld: HTTP 400 with a top-level error body `code: STREAM_EXPIRED`;
    Turso instead rolls the idle transaction back and returns `SQLITE_BUSY` with the
    reason only in the message, so expired and busy are indistinguishable by code)'
  result: fail
- claim: a second `BEGIN IMMEDIATE` while another stream holds a write transaction
    fails with `SQLITE_BUSY` (both endpoints instead block until the server reaps
    the idle holder — sqld ~5s, Turso ~10s — then succeed, with no error)
  result: fail
- claim: four concurrent migration batches (`begin immediate`, `create table if not
    exists`, `insert or ignore`, conditional `commit`, conditional `rollback` in one
    atomic `batch`) serialize safely — all four committed, exactly one schema row,
    sqld 0.0s / Turso 0.2s (the old F4 livelocked >120s)
  result: pass
- claim: a client connect to a blackholed host is bounded by the socket timeout (`timeout=2.0`
    raised `TimeoutError` at 2.01-2.02s on both runs; libsql binding blocked ~75s)
  result: pass
- claim: 'a socket read timeout is honoured: a silent server raised `TimeoutError`
    at 1.00s, and a long remote query with `timeout=1.0` raised at 1.00s (sqld) /
    1.19s (Turso)'
  result: pass
- claim: other threads keep running during slow and normal remote requests — a 10ms
    ticker thread's max gap was 0.013s over ~4-5s on both endpoints (libsql binding
    froze every thread)
  result: pass
- claim: 'latency of `select 1` through a fresh `http.client` connection: sqld median
    1ms; Turso Cloud median 180ms (min 161ms, max 254ms), one HTTP round trip per
    pipeline execute'
  result: pass
raw_output_path: .ll/learning-tests/raw/hrana-http.txt
---

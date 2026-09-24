---
target: libsql remote
date: '2026-09-23'
status: proven
assertions:
- claim: libsql.connect(url, auth_token=...) in remote mode connects and executes
    against both self-hosted sqld (http://) and Turso Cloud (libsql://); connect()
    itself is lazy and touches no network until the first execute
  result: pass
- claim: a wrong or missing auth token fails fast (<0.35s) with builtins.ValueError
    carrying the Hrana api error (sqld 401; Turso 401 for empty token, 400 for a malformed
    JWT)
  result: pass
- claim: "a connect to an unreachable host returns within a configured bound \u2014\
    \ connect(timeout=) is ignored and the first execute against a blackholed IP blocks\
    \ ~75s on the OS TCP connect timeout (refused port and unknown Turso host do fail\
    \ in <0.4s)"
  result: fail
- claim: "a Python thread-based deadline can bound a hung libsql network call \u2014\
    \ the driver holds the GIL for the whole call, freezing every thread in the process"
  result: fail
- claim: connect(isolation_level=None) gives manual transaction control; explicit
    BEGIN IMMEDIATE/COMMIT work and in_transaction toggles False -> True -> False
  result: pass
- claim: "Connection.isolation_level is assignable after connect (as schema._apply_migrations\
    \ does) \u2014 it is read-only (AttributeError); only connect(isolation_level=...)\
    \ sets it"
  result: fail
- claim: rollback after a mid-migration failure leaves meta.schema_version and the
    partial DDL unchanged (verified via a fresh connection)
  result: pass
- claim: the full _MIGRATIONS chain (52 migrations, 244 statements incl. FTS5) applies
    from empty in one BEGIN IMMEDIATE transaction (sqld 4.7s, Turso 26.2s)
  result: pass
- claim: repeat initialization on a current schema is a no-op (0 statements executed)
  result: pass
- claim: "two concurrent initializers serialize \u2014 the loser's interactive transaction\
    \ is aborted server-side (sqld TRANSACTION_TIMEOUT ~5s; Turso SQLITE_BUSY stream-idle\
    \ ~10s) and its ROLLBACK then raises 'no transaction is active'; final schema\
    \ is correct but naive retry livelocks on Turso (>120s)"
  result: fail
- claim: PRAGMA table_info and meta.schema_version reads work for the schema-ahead
    check
  result: pass
- claim: INSERT OR IGNORE rowcount (1 new / 0 duplicate), executemany, lastrowid,
    rowcount and cursor.description behave as with sqlite3
  result: pass
- claim: one connection can be shared across threads under a lock (default _check_same_thread
    did not raise); per-thread connections also work
  result: pass
- claim: "an ambiguous commit is detectable \u2014 with the COMMIT response dropped\
    \ (sqld via proxy) the client raises ValueError 'connection closed before message\
    \ completed' while the commit landed; an idempotent marker re-read on a fresh\
    \ connection detects it; the client's in_transaction stays stale True (TLS Turso\
    \ endpoint not proxied)"
  result: pass
- claim: "a statement timeout is settable \u2014 connect(timeout=1.0) did not cancel\
    \ a 60-87s query and the driver exposes no statement-timeout API"
  result: fail
- claim: 'cold-connect and warm-statement latency recorded: sqld cold 103ms / warm
    20ms median; Turso Cloud cold 339ms / warm 79ms median (each execute is 2 HTTP
    round trips: describe + batch)'
  result: pass
- claim: "database errors raise sqlite3.Error subclasses \u2014 all are builtins.ValueError\
    \ with a Hrana-formatted message; the SQLite code (SQLITE_CONSTRAINT, SQLITE_BUSY,\
    \ ...) appears only in the message text"
  result: fail
- claim: "an idle connection stays usable \u2014 sqld expires the stream after ~10s\
    \ idle (STREAM_EXPIRED, permanent; the connection must be replaced); Turso survives\
    \ 20s idle outside a transaction but rolls back an interactive transaction idle\
    \ >~10s"
  result: fail
- claim: "executescript reports errors in remote mode \u2014 it swallows every error\
    \ silently, stops at the first failure, and can leave a transaction open"
  result: fail
- claim: 'probe: FTS5 virtual table creation, MATCH and bm25() work on both endpoints'
  result: pass
- claim: "probe: PRAGMA journal_mode = WAL, busy_timeout and query_only are accepted\
    \ \u2014 all rejected on both endpoints (sqld unsupported statement; Turso SQL\
    \ not allowed statement)"
  result: fail
- claim: "probe: ATTACH DATABASE to a local file works \u2014 rejected on both endpoints"
  result: fail
- claim: "probe: VACUUM works \u2014 rejected on both endpoints"
  result: fail
- claim: "probe: conn.create_function (Python UDF) is available \u2014 Connection\
    \ has no create_function attribute"
  result: fail
raw_output_path: .ll/learning-tests/raw/libsql-remote.txt
proven_package: libsql
proven_version: 0.1.11
---

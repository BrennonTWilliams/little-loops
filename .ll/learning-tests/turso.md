---
target: Turso
date: '2026-10-06'
status: proven
assertions:
- claim: 'GET /v1/organizations on api.turso.tech with a Bearer TURSO_API_KEY returns 200 application/json, a list of org objects each carrying slug, type and tursodb_enabled'
  result: pass
- claim: 'GET /v1/organizations/{slug}/databases returns {"databases": [...]} where each entry has Name, Hostname, group, regions, primaryRegion and sleeping'
  result: pass
- claim: 'a bad or missing API token is a structured HTTP 401 with a JSON {"error": ...} body (message is a JWT parse error, "token contains an invalid number of segments")'
  result: pass
- claim: 'GET /v1/locations returns {"locations": {code: description}} as a dict (10 entries, e.g. aws-ap-northeast-1)'
  result: pass
- claim: 'the hostname of a libsql:// database URL maps to exactly one Platform API database Hostname, and GET /v1/organizations/{slug}/databases/{name} returns {"database": {...}}'
  result: pass
- claim: 'a missing database name is a 404 JSON {"error": "could not find database with name X: record not found"}'
  result: pass
- claim: 'GET /v1/organizations/{slug}/databases/{name}/stats returns 200 -- actual: 404 with keys code, error, hint on this plan'
  result: fail
- claim: 'pyturso (import turso, 0.8.2) is a distinct package from libsql; turso.connect(path) returns turso.lib.Connection, not a sqlite3.Connection'
  result: pass
- claim: 'pyturso local file DB behaves DB-API like sqlite3: cursor/execute/commit, lastrowid and rowcount set after INSERT, fetchall returns plain tuples, data persists across reconnect, and :memory: works'
  result: pass
- claim: 'pyturso raises a full DB-API 2.0 exception hierarchy (IntegrityError < DatabaseError < Error < Exception) with SQLite-style messages, syntax errors are DatabaseError'
  result: pass
- claim: 'pyturso exceptions are sqlite3.Error subclasses -- actual: rooted at its own turso.lib.Error(Exception), so except sqlite3.Error does not catch them'
  result: fail
- claim: 'pyturso cursor.description carries column type info -- actual: only column names, the other six slots are None'
  result: fail
- claim: 'pyturso supports FTS5 virtual tables -- actual: DatabaseError "Parse error: no such module: fts5"'
  result: fail
- claim: 'pyturso 0.8.2 exposes a remote or sync connection API -- actual: no sync or remote names in the public turso namespace'
  result: fail
raw_output_path: .ll/learning-tests/raw/turso.txt
---

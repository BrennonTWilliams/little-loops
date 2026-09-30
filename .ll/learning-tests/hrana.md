---
target: hrana
date: '2026-09-29'
status: proven
assertions:
- claim: '`GET /health` answers 200 unauthenticated on Turso Cloud, while `GET /version`
    requires auth (401 without a token)'
  result: pass
- claim: '`/v2/pipeline` and `/v3/pipeline` both accept the same JSON pipeline body
    and return the same top-level keys `base_url`, `baton`, `results`'
  result: pass
- claim: 'typed values round-trip: integer is a JSON string (9007199254740993 keeps
    full precision), float is a JSON number, text keeps non-ASCII, blob is `base64`
    (not `value`), null is `{type: null}`'
  result: pass
- claim: 'named arguments bind via `named_args: [{name, value}]` (`:a + :b` gives
    "42")'
  result: pass
- claim: int64 extremes (9223372036854775807, -9223372036854775808) come back exactly
    as decimal strings
  result: pass
- claim: 'result `cols` entries carry `name` and `decltype`, and decltype is returned
    exactly as written in the DDL (`integer`) -- actual: normalised to upper case
    (`INTEGER`, `TEXT`)'
  result: fail
- claim: '`describe` returns `params`, `cols` and `is_readonly` without executing
    the statement (an unnamed `?` param has `name: null`)'
  result: pass
- claim: '`sequence` runs a multi-statement script and returns `{type: sequence}`;
    both inserts landed'
  result: pass
- claim: '`store_sql` ids are scoped to the stream: reusable with the same baton,
    unknown on a fresh stream (error `SQLITE_UNKNOWN`)'
  result: pass
- claim: a failed request inside a pipeline does not abort it -- HTTP 200 with result
    types [error, ok, ok] and later requests still run
  result: pass
- claim: '`want_rows: false` suppresses `rows` but still reports `rows_read`'
  result: pass
- claim: 'JSON can be POSTed to `/v3-protobuf/pipeline` -- actual: Turso answers 404
    route not found; JSON is served on `/v3/pipeline` only'
  result: fail
- claim: malformed input is a structured HTTP 400 with a JSON `error` (unknown request
    `type` lists valid variants; empty body is an EOF parse error), and `GET /v3/pipeline`
    is 404
  result: pass
raw_output_path: .ll/learning-tests/raw/hrana.txt
---

---
id: ENH-2624
title: Compress raw_events payload columns (lossless zlib)
type: ENH
priority: P3
status: done
discovered_date: 2026-07-12
captured_at: '2026-07-12T00:00:00Z'
completed_at: '2026-07-13T02:22:28Z'
discovered_by: capture-issue
relates_to:
- ENH-2581
- ENH-2623
labels:
- enhancement
- history-db
- performance
- captured
---

# ENH-2624: Compress raw_events payload columns (lossless zlib)

## Summary

Store the two large `raw_events` payload columns (`raw_line` and `parsed_json`)
as zlib-compressed BLOBs instead of uncompressed TEXT, losslessly shrinking the
source-of-truth table that dominates `.ll/history.db`. A backward-compatible
pack/unpack layer lets legacy uncompressed TEXT rows and new compressed BLOB rows
coexist, so no destructive schema migration is required. A new batched
`ll-session recompress` maintenance command converts pre-existing rows off the
hot path and VACUUMs.

## Motivation

Investigating a `UserPromptSubmit` hook timeout (`hook timed out after 5s`)
revealed `.ll/history.db` had grown to **3.8 GB**, with `raw_events` accounting
for **3.0 GB (79%)** per `dbstat`. The hook writes a tiny `skill_events` row, but
under write contention with bulk ingest it waits up to `busy_timeout = 5000 ms`
— exactly the 5 s hook budget — and times out.

The data volume was **not** the problem; the storage format was:

- `raw_line` — the verbatim JSONL line (source of truth; the only payload column
  ever read back, by `rebuild()`).
- `parsed_json` — `json.dumps(record)`, a re-serialization of `raw_line`, **never
  read by any code path**, ~2.75 KB/row.

Both were stored uncompressed. zlib compresses these JSONL payloads ~2.9× per-row
(~4.6× in batch), so the real event information is ~300–650 MB. Goal: retain
every one of the 442k events, byte-for-byte recoverable, while shrinking the file
— without deleting history and without freezing the DB during migration.

## Current Behavior

- `_backfill_raw_events()` inserted `line` and `json.dumps(record)` as TEXT.
- `_iter_events()` (the sole payload reader, feeding all of `rebuild()`) read
  `raw_line` verbatim.
- `compact()` / `prune()` touch only `id`/`ts`/`session_id`/`compacted`/
  `summary_node_id` — never the payload.
- No compression anywhere in `scripts/little_loops`.

## Expected Behavior

- New `raw_events` rows store `raw_line`/`parsed_json` as zlib BLOBs.
- `rebuild()` transparently decompresses; output is byte-identical to pre-change.
- Legacy TEXT rows still read correctly (str/bytes dispatch), so a
  partially-converted table is always valid.
- `ll-session recompress [--batch N]` converts existing TEXT rows in short
  per-batch transactions, then VACUUMs; idempotent and resumable.

## Proposed Solution

Implemented (see Resolution). Store compressed BLOBs in the existing columns via
SQLite dynamic typing (no DDL), with `_pack_payload`/`_unpack_payload` helpers and
an off-hot-path batched recompress command. No `SCHEMA_VERSION` bump.

## Scope Boundaries

**In scope:** compress both payload columns losslessly; a maintenance command to
convert existing rows.

**Out of scope (deferred):** dropping the never-read `parsed_json` column (user
chose to keep and compress it); separating `raw_events` into its own DB file; WAL
checkpoint tuning; decoupling `busy_timeout` from the hook timeout; and adding a
configurable DB path / unifying path resolution (captured as ENH-2623).

## Acceptance Criteria

- [x] `raw_line`/`parsed_json` written as compressed BLOBs by backfill.
- [x] `_unpack_payload` round-trips (unicode/empty/large) and passes legacy TEXT
      through unchanged.
- [x] Mixed legacy-TEXT + compressed-BLOB table rebuilds correctly.
- [x] Existing `rebuild()` regression tests pass unchanged (byte-identical output).
- [x] `ll-session recompress` converts legacy rows, is idempotent, and reports
      before/after DB size.
- [x] `python -m pytest scripts/tests/test_session_store.py
      scripts/tests/test_ll_session.py` passes (335 tests); ruff + mypy clean.

## Implementation Steps

1. `session_store.py`: add `zlib` import, `_PAYLOAD_ZLIB_LEVEL`,
   `_pack_payload()` / `_unpack_payload()`.
2. Compress on write in `_backfill_raw_events()`; decompress on read in
   `_iter_events()` (cursor branch).
3. Add `recompress_raw_events(db, batch_size=2000)` — batched UPDATE of
   `typeof(...) = 'text'` rows + final VACUUM.
4. `cli/session.py`: `ll-session recompress [--batch N]` subcommand + dispatch,
   docstring, and epilog example.
5. Document the compressed-BLOB storage in the v19 migration comment and in
   `.claude/CLAUDE.md`'s `ll-session` entry.
6. Tests: `TestRawEventsPayloadCompression` (6) + `TestRecompressSubcommand` (3).

## Impact

- Files changed: `scripts/little_loops/session_store.py`,
  `scripts/little_loops/cli/session.py`, `scripts/tests/test_session_store.py`,
  `scripts/tests/test_ll_session.py`, `.claude/CLAUDE.md`.
- Reduces the dominant contributor to `.ll/history.db` size (~2.9× on
  `raw_events`), easing WAL checkpoint cost and lock-contention pressure that the
  interactive hook write path competes with.

## Sources

- `dbstat` analysis of `.ll/history.db` (3.8 GB; `raw_events` = 3.0 GB).
- Per-row zlib benchmark on live `parsed_json` (2.9× at level 6; decompress
  ~9 µs/row).
- `scripts/little_loops/session_store.py`: `_backfill_raw_events`,
  `_iter_events`, `rebuild`.

## Status

done — completed 2026-07-13.

## Resolution

Shipped the compressed-BLOB storage with a backward-compatible pack/unpack layer,
a batched off-hot-path `ll-session recompress` command, and full test coverage
(335 passing across the session-store and CLI suites; ruff and mypy clean). No
schema-version bump was needed — SQLite dynamic typing stores BLOBs in the
existing nominally-TEXT columns, and legacy TEXT rows coexist with new BLOB rows
via a `str`/`bytes` dispatch in `_unpack_payload`.

A follow-up gap surfaced during implementation — `resolve_history_db()` and
`ensure_db()` resolve the DB path differently (env-always vs env-only-for-default),
which caused `recompress_raw_events()` to briefly open the wrong DB — captured as
**ENH-2623** (configurable `history.db_path` + unified resolution).

Live conversion of the existing 3.8 GB DB is operator-run
(`ll-session recompress`) and intentionally not performed automatically, to keep
it off the interactive hook path.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-13T02:23:10 - `62204b71-3643-40b2-be84-11df8a50da1d.jsonl`

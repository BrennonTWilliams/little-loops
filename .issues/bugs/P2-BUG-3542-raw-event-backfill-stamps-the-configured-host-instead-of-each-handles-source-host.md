---
id: BUG-3542
type: BUG
title: Raw-event backfill stamps the configured host instead of each handle's source
  host
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:14Z'
labels:
- observability
- multi-host
relates_to:
- ENH-3528
- ENH-3532
blocks:
- ENH-3532
---

# BUG-3542: Raw-event backfill stamps the configured host instead of each handle's source host

## Summary

`_backfill_raw_events` (`little_loops.session_store.lifecycle`) writes `raw_events.host` from `effective_host` (the explicit `--host` argument, or the ambient `resolve_host().name`) instead of each `SessionHandle.host`. Parsing already dispatches on `handle.host`, so a Codex handle ingested by a Claude-configured process is parsed as Codex but stored with `host='claude-code'`. Split out of ENH-3532 because it can ship now and ENH-3528's host attribution depends on it.

## Current Behavior

- `_backfill_raw_events(conn, handles, *, host=None)` computes `effective_host = host if host is not None else resolve_host().name` and stamps that on every row, whatever `handle.host` says.
- ENH-3532's fixture probe confirmed that a Codex handle ingested under a Claude host replays with the wrong host.
- Existing rows cannot be told apart: a non-NULL `raw_events.host` may be the ingesting host rather than the source host.

## Expected Behavior

- New raw rows record `handle.host`. The explicit `--host` override (ENH-3166, `ll-session backfill --host qwen`) keeps working, because `handles_from_paths(jsonl_files, effective_host)` already builds its handles with that host.
- A persisted discriminator tells corrected writes apart from legacy rows, e.g. a `host_basis` column (`'handle'` for new writes, NULL for legacy) added by an append-only migration. Readers treat legacy host values as unverified.
- Legacy rows are not bulk-relabelled from model name, path spelling, or timestamps.

## Steps to Reproduce

1. With `orchestration.host_cli` = `claude-code`, call `backfill_raw_events(db, handles=[<Codex SessionHandle for scripts/tests/fixtures/codex/rollout-exec.jsonl>])`.
2. <!-- ll-evidence-ok: reproduction step, not a quoted artifact -->
   `SELECT DISTINCT host FROM raw_events WHERE source_path LIKE '%rollout-exec%'`.
3. Observe `claude-code`; expected `codex`.

## Scope Boundaries

- **In scope**: host stamping for new raw rows; attribution discriminator; legacy rows read as unverified.
- **Out of scope**: recovering hosts for legacy rows; usage ingestion (ENH-3532); reporting (ENH-3528).

## Program Design

### Types

- New nullable `raw_events.host_basis TEXT` column — `'handle'` for rows written after this fix, NULL for legacy rows.

### Signatures

- `_backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle], *, host: str | None = None) -> int` — unchanged; stamps `handle.host` per row.
- `backfill_raw_events(db, *, jsonl_files=None, handles=None, since_ts=None, host=None)` — unchanged; `host` continues to seed `handles_from_paths` for plain paths.

### Call Path

- `backfill_raw_events` → `handles_from_paths` → `_backfill_raw_events` → `iter_events` → `raw_events` INSERT with `handle.host`

## Integration Map

- `scripts/little_loops/session_store/lifecycle.py` (`_backfill_raw_events`, `backfill_raw_events`, rebuild cursor), `session_store/schema.py` + `schema_manifest.json` (migration at the next free version, currently v55).
- Tests: `test_session_store_lifecycle.py`, schema/manifest tests.

## Impact

- **Priority**: P2 — mislabels mixed-host history; blocks certified host attribution in ENH-3528/ENH-3532.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Ingesting a Codex handle and a Claude handle in one batch under a Claude-configured process stores each row with its own host; this survives `--rebuild`.
- [ ] `ll-session backfill --host <host>` over plain JSONL paths still stamps the requested host.
- [ ] New rows carry the verified-attribution discriminator; pre-migration rows read as unverified, and a test covers both.
- [ ] The docstring and `docs/guides/HISTORY_SESSION_GUIDE.md` describe the new host semantics.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This bug owns the raw-ingest source-host correction and the `host_basis` attribution discriminator (split out of ENH-3532). ENH-3532 only consumes it, and ENH-3528's host attribution depends on it; ENH-3528 references to ENH-3532 owning this work should be read as BUG-3542.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:59 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`

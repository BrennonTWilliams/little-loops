---
id: BUG-3542
type: BUG
title: Raw-event backfill stamps the configured host instead of each handle's source
  host
priority: P2
status: open
parent: EPIC-3562
epic: EPIC-3562
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
- A persisted discriminator tells corrected writes apart from legacy rows, e.g. a `host_basis` column (`'handle'` for new writes, NULL for legacy) added by an append-only migration. Readers treat legacy host values as unverified. This is mandatory: `raw_events.host` is `NOT NULL` (`schema.py:477`), so every legacy row carries a plausible-looking host.
- Legacy rows are not bulk-relabelled from model name, path spelling, or timestamps.
- **Attribution survives replay.** `--rebuild` replays `raw_events` through `_iter_events_with_host` (`session_store/writers.py:3454`). `_backfill_usage_events` then writes the stored host straight into `usage_events.host` and derives `provider_vendor = vendor_for_runner(host)` (`writers.py:3682-3683`). Stamping `host_basis` on raw rows alone would therefore give replayed usage rows a certified-looking vendor. The fix:
  - The rebuild cursor (`lifecycle.py:1002`) selects `host_basis`.
  - `_iter_events_with_host` yields it: extend the tuple and update every `_backfill_*` unpacking site.
  - `_backfill_usage_events` persists it on `usage_events` through a nullable `usage_events.host_basis` column in the same migration. A NULL-basis raw row yields a NULL-basis usage row, so its `host` / `provider_vendor` read as unverified downstream.
- **Legacy Qwen normalization is preserved.** The replay shim branches on the stored host (`if host == "qwen":`, `writers.py:3484`). It keeps doing so regardless of `host_basis`, so a legacy qwen row is still normalized on replay even though its host is not certified for reporting. Fix the shim's docstring, which claims it is keyed on record shape alone.
- **Re-ingestion never certifies legacy rows.** Raw inserts are `INSERT OR IGNORE` on `(source_path, line_no)` (`lifecycle.py:803`, `schema.py:489-490`). Re-running a backfill over an already-ingested source leaves the existing rows untouched, with their host and a NULL `host_basis`. That is the intended no-relabel behavior, and a test pins it.
- **The handle wins over `host=`.** When both `handles` and a conflicting `host=` are passed, each row stores `handle.host`. `host` only seeds `handles_from_paths` for plain `jsonl_files` paths. Remove the now-unused `host` keyword from the private `_backfill_raw_events` so the conflict cannot be reintroduced. Production already passes both, on the Codex path in `cli/session.py` (~701-707, 758-765).

## Steps to Reproduce

1. With `orchestration.host_cli` = `claude-code`, call `backfill_raw_events(db, handles=[<Codex SessionHandle for scripts/tests/fixtures/codex/rollout-exec.jsonl>])`.
2. <!-- ll-evidence-ok: reproduction step, not a quoted artifact -->
   `SELECT DISTINCT host FROM raw_events WHERE source_path LIKE '%rollout-exec%'`.
3. Observe `claude-code`; expected `codex`.

## Scope Boundaries

- **In scope**: host stamping for new raw rows; the attribution discriminator on `raw_events` and on replay-derived `usage_events`; legacy rows read as unverified; the replay, Qwen, re-ingestion and handle-precedence contracts above.
- **Out of scope**: recovering hosts for legacy rows; live usage ingestion (ENH-3532); reporting that honors `host_basis` (ENH-3528).
- **Test ownership and landing order.** BUG-3542 lands first and owns every test up to the storage layer: raw rows, replayed usage rows, re-ingestion, and handle precedence. ENH-3528 lands after it and owns the reporting-layer tests, i.e. `ll-ctx stats` / exports rendering legacy attribution as unverified. ENH-3528 currently says verified attribution "is tested in BUG-3542" (its lines 31, 124). Read that as the storage half only. ENH-3528 also still names ENH-3532 as the owner of the raw-ingest fix (lines 44, 82, 140, 152, 161); that owner is BUG-3542.

## Program Design

### Types

- New nullable `raw_events.host_basis TEXT` column — `'handle'` for rows written after this fix, NULL for legacy rows.
- New nullable `usage_events.host_basis TEXT` column (same migration). It is copied from the source raw row on replay; NULL marks the row's `host` / `provider_vendor` as unverified.

### Signatures

- `_backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle]) -> int` — stamps `handle.host` and `host_basis='handle'` per row; the unused `host` keyword is removed.
- `backfill_raw_events(db, *, jsonl_files=None, handles=None, since_ts=None, host=None)` — unchanged; `host` only seeds `handles_from_paths` for plain paths and never overrides an explicit handle.
- `_iter_events_with_host(source) -> Generator[tuple[str, str, str | None, str | None], None, None]` — yields `(raw_line, source_label, host, host_basis)`.

### Call Path

- `backfill_raw_events` → `handles_from_paths` → `_backfill_raw_events` → `iter_events` → `raw_events` INSERT with `handle.host`
- `rebuild` → `_raw_events_cursor` (selects `host_basis`) → `_iter_events_with_host` → `_backfill_usage_events` → `usage_events` INSERT with `host_basis`

## Integration Map

- `scripts/little_loops/session_store/lifecycle.py`: `_backfill_raw_events` (INSERT at :803), `backfill_raw_events` (:847-855), `backfill()` (:1123), rebuild `_raw_events_cursor` (:1002).
- `scripts/little_loops/session_store/writers.py`: `_iter_events_with_host` (:3454, Qwen shim at :3484), `_backfill_usage_events` (:3603, host / vendor at :3682-3683), and every other `_backfill_*` that unpacks the helper's tuple.
- `scripts/little_loops/session_store/schema.py` + `schema_manifest.json`: migration at the next free version (currently v55) adding both columns.
- `scripts/little_loops/cli/session.py` (~701-707, 758-765): the Codex path passes both `handles` and `host`, so confirm behavior is unchanged.
- Tests: `test_session_store_lifecycle.py`, the writers/rebuild tests, and schema/manifest tests.

## Impact

- **Priority**: P2 — mislabels mixed-host history; blocks certified host attribution in ENH-3528/ENH-3532.
- **Effort**: Medium — the replay path adds a second column and a tuple change across the `_backfill_*` consumers.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Ingesting a Codex handle and a Claude handle in one batch under a Claude-configured process stores each row with its own host; this survives `--rebuild`.
- [ ] `ll-session backfill --host <host>` over plain JSONL paths still stamps the requested host.
- [ ] New rows carry the verified-attribution discriminator; pre-migration rows read as unverified, and a test covers both.
- [ ] After `--rebuild`, a usage row replayed from a NULL-basis raw row has NULL `host_basis`, and one replayed from a `'handle'` row has `'handle'`.
- [ ] A legacy (NULL-basis) raw row with `host='qwen'` in raw qwen wire format is still normalized on replay.
- [ ] Re-running a backfill over an already-ingested legacy source leaves those rows' `host` and NULL `host_basis` unchanged.
- [ ] A Codex handle passed together with `host='claude-code'` stores `host='codex'`.
- [ ] The docstring and `docs/guides/HISTORY_SESSION_GUIDE.md` describe the new host semantics.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This bug owns the raw-ingest source-host correction and the `host_basis` attribution discriminator (split out of ENH-3532). ENH-3532 only consumes it, and ENH-3528's host attribution depends on it; ENH-3528 references to ENH-3532 owning this work should be read as BUG-3542.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:59 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`

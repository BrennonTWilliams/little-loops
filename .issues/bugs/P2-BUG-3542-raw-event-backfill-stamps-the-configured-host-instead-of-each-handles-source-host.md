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
- ENH-3528
confidence_score: 100
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
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
  - `_iter_events_with_host` yields it as a fourth tuple element. It yields `host_basis=None` whenever the source lacks the column: two-column `(raw_line, source_path)` cursors, three-column `(raw_line, source_path, host)` cursors, and `list[Path]` file inputs. Guard the index the way `host` is already guarded (`len(row) > 3`, beside the existing `len(row) > 2` at `writers.py:3483`).
  - Only two call sites unpack the host-bearing tuple: `_iter_events` (`writers.py:3510`) and `_backfill_usage_events` (`writers.py:3629`). `_iter_events` keeps returning `(raw_line, source_label)` pairs, so every other `_backfill_*` consumer stays unchanged.
  - `_backfill_usage_events` persists it on `usage_events` through a nullable `usage_events.host_basis` column in the same migration. A NULL-basis raw row yields a NULL-basis usage row, so its `host` / `provider_vendor` read as unverified downstream.
- **NULL basis qualifies raw-derived attribution only.** `host_basis` describes how a row's `host` was derived from `raw_events`. On `usage_events` it is meaningful only for replay-derived rows (`channel='transcript'`). Live rows written by `record_usage_event` get their `host` from the actual invocation (ENH-3538). They also leave `host_basis` NULL, but that NULL does not make their host unverified. `host_basis` never alters or implies token `provenance`.
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
- **Test ownership and landing order.** BUG-3542 lands first (it `blocks` ENH-3528). It owns every test up to the storage layer: raw rows, iterator replay, replayed usage rows, schema upgrade, re-ingestion, incremental append, and handle precedence. ENH-3528 lands after it and owns reporting and export consumption of `host_basis`. That covers the reporting-layer tests for both verified and legacy (unverified) attribution in `ll-ctx-stats` and exports.
- **Codex usage rows are out of scope.** `_backfill_usage_events` reads only Claude-shaped `assistant` records with `message.usage` (`writers.py:3634-3641`). The Codex rollout fixtures therefore produce zero usage rows, and Codex usage ingestion is ENH-3532. Mixed Codex/Claude attribution is tested at `raw_events` and iterator replay. Propagation into `usage_events` is tested with Claude-shaped usage records.

## Program Design

### Types

- New nullable `raw_events.host_basis TEXT` column — `'handle'` for rows written after this fix, NULL for legacy rows.
- New nullable `usage_events.host_basis TEXT` column (same migration). It is copied from the source raw row on replay. On replay-derived rows (`channel='transcript'`), NULL marks `host` / `provider_vendor` as unverified. Live rows also leave it NULL, but their host comes from the invocation and is not unverified. It never affects `provenance`.

### Signatures

- `_backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle]) -> int` — stamps `handle.host` and `host_basis='handle'` per row; the unused `host` keyword is removed.
- `backfill_raw_events(db, *, jsonl_files=None, handles=None, since_ts=None, host=None)` — unchanged; `host` only seeds `handles_from_paths` for plain paths and never overrides an explicit handle.
- `_iter_events_with_host(source) -> Generator[tuple[str, str, str | None, str | None], None, None]` — yields `(raw_line, source_label, host, host_basis)`; `host_basis` is `None` for two- and three-column cursors and for file inputs.
- `_iter_events(source) -> Generator[tuple[str, str], None, None]` — unchanged; still yields pairs.

### Call Path

- `backfill_raw_events` → `handles_from_paths` → `_backfill_raw_events` → `iter_events` → `raw_events` INSERT with `handle.host`
- `rebuild` → `_raw_events_cursor` (selects `host_basis`) → `_iter_events_with_host` → `_backfill_usage_events` → `usage_events` INSERT with `host_basis`

## Integration Map

- `scripts/little_loops/session_store/lifecycle.py`: `_backfill_raw_events` (INSERT at :803), `backfill_raw_events` (:847-855), `backfill()` (:1123), rebuild `_raw_events_cursor` (:1002).
- `scripts/little_loops/session_store/writers.py`: `_iter_events_with_host` (:3454, row guard at :3483, Qwen shim at :3484), `_iter_events` (:3508, unpacks at :3510), `_backfill_usage_events` (:3603, unpacks at :3629, host / vendor at :3682-3683). No other `_backfill_*` unpacks the host-bearing tuple.
- `scripts/little_loops/session_store/schema.py` + `schema_manifest.json`: migration at the next free version (currently v55) adding both columns.
- `scripts/little_loops/cli/session.py` (~701-707, 758-765): the Codex path passes both `handles` and `host`, so confirm behavior is unchanged.
- Tests: `test_session_store_lifecycle.py`, the writers/rebuild tests, and schema/manifest tests.
- `scripts/tests/test_enh3538_token_observations.py::TestReplay` (:227): its three-value unpacks at :236 and :242 break when the tuple grows. Update them, and add two-column-cursor and file-input cases that assert `host_basis is None`.

## Impact

- **Priority**: P2 — mislabels mixed-host history; blocks certified host attribution in ENH-3528/ENH-3532.
- **Effort**: Medium — the replay path adds a second column and a tuple change across the `_backfill_*` consumers.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Ingesting a Codex handle and a Claude handle in one batch under a Claude-configured process stores each `raw_events` row with its own host and `host_basis='handle'`. On rebuild, `_iter_events_with_host` over the `raw_events` cursor replays each row with that host and basis.
- [ ] Claude-shaped `assistant` usage records ingested through a handle propagate `host` and `host_basis='handle'` into `usage_events` after `--rebuild`. The Codex fixtures produce no usage rows; Codex usage ingestion is ENH-3532.
- [ ] `_iter_events_with_host` yields `host_basis=None` for two-column cursors, three-column cursors and `list[Path]` inputs. `_iter_events` still yields pairs.
- [ ] `ll-session backfill --host <host>` over plain JSONL paths still stamps the requested host.
- [ ] New rows carry the verified-attribution discriminator; pre-migration rows read as unverified, and a test covers both.
- [ ] After `--rebuild`, a usage row replayed from a NULL-basis raw row has NULL `host_basis`, and one replayed from a `'handle'` row has `'handle'`.
- [ ] A legacy (NULL-basis) raw row with `host='qwen'` in raw qwen wire format is still normalized on replay.
- [ ] Re-running a backfill over an already-ingested legacy source leaves those rows' `host` and NULL `host_basis` unchanged.
- [ ] Appending events to an already-ingested legacy file, then backfilling it, leaves the existing rows untouched. The appended rows get `handle.host` and `host_basis='handle'`, so one source holds both kinds of row.
- [ ] A populated v54 database upgraded twice (migration is idempotent) keeps `raw_events.host_basis` and `usage_events.host_basis` NULL on every legacy row.
- [ ] Live `usage_events` rows keep their invocation-derived `host` and `provenance` unchanged by the migration.
- [ ] A Codex handle passed together with `host='claude-code'` stores `host='codex'`.
- [ ] The docstring and `docs/guides/HISTORY_SESSION_GUIDE.md` describe the new host semantics.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This bug owns the raw-ingest source-host correction and the `host_basis` attribution discriminator (split out of ENH-3532). ENH-3532 only consumes it, and ENH-3528's host attribution depends on it; ENH-3528 references to ENH-3532 owning this work should be read as BUG-3542.


## Session Log
- `/ll:confidence-check` - 2026-09-24T21:53:41 - `75725027-e884-41d2-8414-83c4661c85da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:59 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`

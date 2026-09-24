---
id: ENH-3532
type: ENH
title: Ingest Codex historical rollout token usage into usage_events
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:39Z'
labels:
- observability
- multi-host
blocked_by:
- ENH-3528
- BUG-3530
- BUG-3531
---

# ENH-3532: Ingest Codex historical rollout token usage into usage_events

## Summary

Ingest Codex historical rollout usage (`event_msg` / `token_count`) into `usage_events` with defined normalization, deduplication, and rebuild behavior. This is Delivery B split out of ENH-3528: it builds on ENH-3528's per-observation provenance columns and on the Codex normalization fix in BUG-3531. Codex live `turn.completed` capture already works and must keep working.

## Current Behavior

- Codex live usage reaches `usage_events` via `usage_from_event` → runner `ActionResult.usage_events` → `FSMExecutor._finish` → `record_usage_event`.
- Historical rollout `token_count` events are read only by `ctx_stats._codex_cache_usage` for a cache-hit rate; they never reach `usage_events`.
- `session_store` `_iter_events` yields line/source labels and drops the cursor's host except for Qwen replay.

## Expected Behavior

Codex rollout usage is persisted as normalized, provenance-labeled observations. Repeated notifications, cumulative snapshots, and compaction resets never inflate totals; live and historical coverage of the same work is never summed twice; ingestion and rebuild are idempotent.

## Integration Map

- `scripts/little_loops/session_store/{codex,sessions,writers,lifecycle}.py` — rollout normalization, source identity, `_backfill_usage_events`, host identity through `_iter_events`.
- `scripts/little_loops/subprocess_utils.py`, `cli/ctx_stats.py` — shared normalizer; `_codex_cache_usage` may read from `usage_events` once ingested.
- Tests: `test_session_store_writers.py`, `test_session_store_lifecycle.py`, Codex parser tests, `scripts/tests/fixtures/codex/rollout-interactive.jsonl`.
- Docs: `docs/codex/usage.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/HOST_COMPATIBILITY.md`.

## Impact

- **Priority**: P2.
- **Effort**: Medium — accounting rules and overlap reconciliation are the bulk.
- **Risk**: Medium to high — wrong grain handling double-counts tokens.

## Design

Normalize native events into the canonical contract shared with live capture (BUG-3531):

- Input columns represent uncached input plus separate cache-read/cache-write components; partial/inconsistent components remain identifiable rather than inventing a measured split.
- Output totals must not add reasoning tokens again when already included; establish with fixtures.
- Distinguish per-request counts (`last_token_usage`) from cumulative snapshots (`total_token_usage`). Repeated notifications must not duplicate usage; compaction/reset boundaries must not produce negative deltas or cross-session attribution. Do not blindly sum either field.
- Carry host, session, acquisition channel (`rollout`), observation scope/time, provenance (`measured`), and a stable source identity. Rate-limit-only events (`info: null`) and events without usage create no rows.
- Document which keys establish request identity and reset boundaries. If live invocation totals cannot be matched to transcript requests, keep both but select one coverage basis per scope in aggregates; never deduplicate merely by equal token values.

## Acceptance Criteria

- [ ] Historical rollout usage reaches `usage_events` through a fixture-backed normalizer shared with live capture; live capture continues to work.
- [ ] Fixtures cover repeated notifications, per-request vs cumulative values, compaction resets, multiple sessions, malformed/partial records, rate-limit-only records, and observed-model absence. Valid distinct requests with equal counts remain distinct.
- [ ] Live/historical overlap has a documented identity/coverage policy; aggregates do not double-count overlapping coverage.
- [ ] Repeated ingestion and rebuild leave canonical totals stable and preserve live-only rows (relies on BUG-3530).
- [ ] Mixed-host history is labeled from stored observations, never from the currently configured host.

## Scope Boundaries

- **In scope**: Codex rollout `token_count` normalization and ingestion into `usage_events`, request/snapshot/reset identity, live-vs-historical coverage policy, idempotent replay.
- **Prerequisites**: ENH-3528 (provenance/host/channel columns), BUG-3530 (rebuild preserves live rows), BUG-3531 (shared Codex input normalizer).
- **Out of scope**: other hosts (ENH-3534); Codex pricing; changing live capture beyond BUG-3531.

## Program Design

### Types

- `UsageObservation` — normalized record: nullable token components, host, channel, scope, observed-at, source identity, provenance, observed model.

### Signatures

- `normalize_codex_usage(event: dict[str, Any], *, session_id: str, prior: dict[str, int] | None = None) -> list[UsageObservation]` — returns zero or one observation per event; `prior` carries the last cumulative snapshot for reset/duplicate detection.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing; extended to route Codex rollouts through the normalizer.

### Call Path

- `_backfill_usage_events` → `normalize_codex_usage` → `usage_events` insert
- `usage_from_event` → `record_usage_event` (live path, unchanged except BUG-3531)

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `_iter_events` (`writers.py` L3430) yields `(raw_line, source_label)` only; `_codex_cache_usage` (`ctx_stats.py` L356) is the sole rollout `token_count` reader; `_backfill_usage_events` (L3568) and `normalize_codex_usage` (not yet present, as proposed) consistent with Program Design. Dependency note: blockers BUG-3530/BUG-3531/ENH-3528 all open; BUG-3530/3531 lack `blocks:` backlinks (advisory).

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `channel` column is introduced by BUG-3530 (not ENH-3528); list BUG-3530 as its owner in Prerequisites. Rollout rows tagged `rollout` are replayable, so BUG-3530's `rebuild()` must delete them alongside `transcript` rows to keep "repeated ingestion and rebuild leave canonical totals stable" true.

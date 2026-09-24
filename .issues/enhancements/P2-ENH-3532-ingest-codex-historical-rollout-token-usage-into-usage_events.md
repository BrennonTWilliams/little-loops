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
- ENH-3538
- BUG-3531
relates_to:
- ENH-3528
---

# ENH-3532: Ingest Codex historical rollout token usage into usage_events

## Summary

Ingest Codex historical rollout usage (`event_msg` / `token_count`) into `usage_events` with defined normalization, deduplication, and rebuild behavior. This is Delivery B split out of ENH-3528: it builds on ENH-3538's per-observation provenance/host/observation-time columns (the foundation extracted from ENH-3528) and on the Codex normalization fix in BUG-3531. It does not depend on ENH-3528's reporting work; ENH-3528 reports the rollout rows once both land. Codex live `turn.completed` capture already works and must keep working.

## Current Behavior

- Codex live usage reaches `usage_events` via `usage_from_event` → runner `ActionResult.usage_events` → `FSMExecutor._finish` → `record_usage_event`.
- Historical rollout `token_count` events are read only by `ctx_stats._codex_cache_usage` for a cache-hit rate; they never reach `usage_events`.
- `parse_codex_rollout` yields a `SessionEvent` whose payload is the inner Codex object. `_backfill_raw_events` serializes that payload: stored usage records have `type='token_count'`, not the original `event_msg` envelope. Timestamp, session ID, outer event type, and line position are stored separately; native envelope ordinals are not preserved by this path.
- The in-progress metadata iterator in `scripts/little_loops/session_store/writers.py` supplies line/source/host, but not the other replay metadata. The rebuild cursor in `scripts/little_loops/session_store/lifecycle.py` selects only `raw_line, source_path, host` ordered by database ID.
- `_backfill_raw_events` stamps the ingesting/configured host instead of `SessionHandle.host`. Preserving `raw_events.host` alone can therefore mislabel Codex history as another host.
- The foundation's observation type has no session/invocation identity fields, and the executor supplies neither identity when persisting live usage. The raw-ingest function in `scripts/little_loops/session_store/lifecycle.py` documents uniqueness as `(source_path, line_no)`, which does not deduplicate moved or copied rollouts.

## Expected Behavior

Codex rollout usage is persisted as normalized, provenance-labeled observations. Repeated notifications, cumulative snapshots, and compaction resets never inflate verified consumption totals. Reconciled live/historical coverage contributes once; unmatched coverage remains explicitly unresolved, never advertised as deduplicated consumption. Ingestion and rebuild are idempotent.

## Integration Map

- `scripts/little_loops/session_store/{codex,sessions,writers,lifecycle}.py` — rollout normalization, metadata-bearing replay, verified source host, stable source identity and idempotent `_backfill_usage_events`.
- `scripts/little_loops/session_store/{schema,queries}.py`, `schema_manifest.json` — append-only migration for observation identity/uniqueness and any required attribution/coverage metadata; shared aggregate selection; safe export compatibility. Reuse ENH-3538's columns rather than adding them again.
- `scripts/little_loops/subprocess_utils.py`, `fsm/{runners,executor}.py` — live thread/session and invocation identity plumbing through callbacks, collected observations, and persistence. This issue owns that extension beyond BUG-3531's normalization.
- `scripts/little_loops/cli/ctx_stats.py`, `history_reader/{models,usage}.py`, `cli/artifact/dashboard.py` and its export template — consume the same coverage-selection result for usage, cost, waste, and exports. `_codex_cache_usage` may use stored observations only when session selection and coverage remain equivalent.
- Tests: `test_session_store_writers.py`, `test_session_store_lifecycle.py`, schema/manifest tests, Codex parser tests, `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, `test_feat3304_artifact_dashboard.py`, and `scripts/tests/fixtures/codex/`.
- Docs: `docs/codex/usage.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/HOST_COMPATIBILITY.md`.

## Impact

- **Priority**: P2.
- **Effort**: Provisional medium to large — replay metadata, live identity plumbing, persisted uniqueness, and cross-reader coverage selection are required; re-estimate after the readiness gates below.
- **Risk**: Medium to high — wrong grain handling double-counts tokens.

## Design

Normalize native events into the canonical contract shared with live capture (BUG-3531):

- Input columns represent uncached input plus separate cache-read/cache-write components; partial/inconsistent components remain identifiable rather than inventing a measured split.
- Output totals must not add reasoning tokens again when already included; establish with fixtures.
- Distinguish per-request counts (`last_token_usage`) from cumulative snapshots (`total_token_usage`). Repeated notifications must not duplicate usage; compaction/reset boundaries must not produce negative deltas or cross-session attribution. Do not blindly sum either field.
- Carry verified host, session, acquisition channel (`rollout`), observation scope/time, stable source identity, and conservative row provenance. `measured` requires BUG-3531's producer-contract gate for this acquisition path, a consistent input split, and valid known output; malformed/partial or unproven observations remain `unknown`. Omitted cache-write is not zero without path-specific evidence. Rate-limit-only events (`info: null`) and absent usage create no rows; malformed or present-but-empty usage follows BUG-3531's container contract.

### Replay input and host attribution

Introduce a usage-specific metadata record carrying the parsed payload plus outer event type, event timestamp, session ID, verified host/host-attribution basis, source position and its basis, and a diagnostic source label. Both raw rollout envelopes and stored inner payloads adapt to this record before normalization. Select the necessary `raw_events` columns explicitly; never expect `timestamp`, `sessionId`, or `ordinal` inside a stored `token_count` payload. Preserve the existing two-tuple `_iter_events` API for unrelated consumers.

This issue owns correcting new raw ingestion to stamp `handle.host`; the configured host may select discovery/parsing defaults but must not overwrite an already typed handle. Persist enough attribution evidence to distinguish corrected writes from legacy ingest-host labels on later rebuilds. The exact schema discriminator must be specified before implementation readiness. Existing rows may recover a source host only from trustworthy source/session evidence; otherwise expose an unknown host with a reason. Neither a non-NULL legacy `raw_events.host` nor the currently configured host proves source identity. Do not bulk relabel old rows by model, path spelling, or timestamp proximity. Correct new ingestion and legacy qualification are prerequisites to certified host-specific rollout reporting within this issue. ENH-3528 may ship independently with uncertain historical host attribution explicitly unknown.

### Observation identity, state, and persistence

Separate **source-event identity** (the same recorded event ingested again) from **request identity** (multiple notifications describing the same work). A source path or database row ID is not a durable observation identity. Prefer a verified native event/request identity scoped by host and session; a native ordinal also needs its verified stream/reset namespace. A session plus original source position is a fallback only when fixtures establish that the position survives copying/archiving and identifies the same stream. Do not synthesize identity from equal token counts, timestamps, or content hashes alone; distinct requests may have identical usage.

Before implementation readiness, record the exact persisted key, fallback rules, reset namespace, and uniqueness constraint in this issue, backed by the producer fixtures. Add the key and a scoped unique index in an append-only migration; do not place all unknown identities under a shared sentinel key. A repeated key with conflicting content must surface a conflict, not silently overwrite or count twice. When identity cannot be established, retain uncertainty and exclude it from claims of verified deduplicated consumption.

Use explicit mutable normalization state per verified session/stream, including prior cumulative components, reset epoch/boundaries, and request/notification identity evidence. The interactive fixture has multiple usage observations within one `task_started`/`task_complete` turn: a turn ID alone is not a request key. Keep state isolated when rebuild order interleaves sessions; do not depend on `ORDER BY id` being chronological within each source. Define ordering and incomplete-prefix behavior. A prior cumulative snapshot alone does not resolve repeated notifications, resets, or equal-count distinct requests. Preserve the last trustworthy baseline across malformed notifications according to a fixture-backed rule; never fabricate a delta from unknown components.

`channel='rollout'` is replayable. BUG-3530's existing `channel IS NOT 'live'` rebuild predicate already includes it; test that behavior rather than adding a conflicting deletion rule. Perform derived-row replacement and replay transactionally so interruption cannot leave half-rebuilt accounting; preserve live rows and make retries stable. Test source relocation and copies as well as repeated ingestion of an unchanged path.

### Live identity and coverage selection

This issue owns carrying host-observed thread/session identity and a distinct local invocation correlation ID through live collection into `usage_events`. Capture observed identity from the verified producer events; never call a generated correlation ID host-observed. If one invocation can contain several turns, preserve their boundaries. Document how that invocation maps to rollout requests and coverage intervals after BUG-3531 resolves terminal-event scope. Do not substitute `run_id`, state name, timestamp windows, or model selection for request identity. Add fields/callback plumbing as needed; the foundation's current `TokenUsage` alone is insufficient.

Implement one shared coverage-selection policy consumed by usage, cost, waste, and export readers:

1. Retain source observations and per-channel subtotals for audit. Select exactly one basis only when identity and interval evidence establish equivalent coverage. Prefer the complete request-level rollout set over its matching live invocation total; do not suppress the live total for a partial rollout set. If only the live total covers the entire verified interval, select it. Missing token components remain missing and must not be filled by mixing overlapping channels.
2. Demonstrably disjoint intervals may be added. Partial historical coverage, unmatched legacy live rows, conflicting observations, and ambiguous interval/request identity remain `coverage='overlap_unresolved'` or `unknown` as appropriate, with reasons; they do not become verified consumption totals. Do not drop an entire session's live rows merely because any rollout row exists.
3. Align with ENH-3528: any unresolved combined numeric field is an **unreconciled observation sum**, with unknown aggregate provenance and visible channel subtotals. Reconciled aggregates count the selected coverage once and disclose their basis. Cost/waste/export paths cannot bypass this policy with direct all-row sums. Safe exports must preserve the selection/qualification needed to reproduce the reported meaning without exposing private source labels.

The selector and minimal coverage qualification are owned here so ingestion does not require ENH-3528 to have landed; ENH-3528 owns the richer JSON Pointer/rendering contract and consumes these semantics when both land. Exact reconciliation of Claude live/transcript overlap remains outside this issue.

### Implementation readiness gates

Do not treat the older VALID verification as implementation readiness. Resolve the fixture-backed source/request key, reset/ordering rules, host-attribution discriminator, and live-to-rollout identity/interval mapping in this issue before proceeding. If the producer cannot supply enough evidence for a case, explicitly select the conservative unresolved behavior above rather than inventing a match.

## Acceptance Criteria

- [ ] Historical rollout usage reaches `usage_events` through a fixture-backed normalizer shared with live capture; live capture continues to work.
- [ ] Fixtures cover repeated notifications, per-request vs cumulative values, compaction resets, multiple sessions, malformed/partial records, rate-limit-only records, and observed-model absence. Valid distinct requests with equal counts remain distinct.
- [ ] Live/historical overlap has a documented identity/coverage policy; verified consumption aggregates count matched coverage once, while unmatched/partial coverage stays explicitly unresolved with channel subtotals.
- [ ] Repeated ingestion and rebuild leave canonical totals stable and preserve live-only rows (relies on BUG-3530).
- [ ] Mixed-host history is labeled from stored observations, never from the currently configured host.
- [ ] The same fixture ingested directly and replayed from stored inner payloads produces equivalent observations, including session, event time, outer type, and source position. Existing `_iter_events` consumers remain compatible.
- [ ] Ingest a Codex handle under a Claude-configured process and mixed-host handles in one batch: each new raw/usage row retains its verified source host through rebuild. Legacy mislabeled/NULL host rows remain unknown unless source evidence recovers the host; attribution qualification survives exports.
- [ ] Source/request keys, fallback rules, reset namespace, host-attribution discriminator, and database uniqueness are documented and fixture-backed before implementation readiness. Tests cover archive/move, copied sources, repeated notifications, conflicting duplicate keys, equal-count distinct requests, and unknown identities.
- [ ] Interleaved sessions, out-of-order ingestion, incomplete prefixes, malformed snapshots, and compaction/reset boundaries cannot share normalization state or produce fabricated deltas. Multiple request observations in one turn remain distinct.
- [ ] Live thread/session and invocation correlation identity survives parser → runner → executor → database; locally generated IDs remain distinguishable from host-observed IDs. No matching by run ID or timestamp proximity alone.
- [ ] Complete matched coverage selects one basis; partial rollout coverage, unmatched legacy rows, and ambiguous intervals remain explicitly qualified. Usage, cost, waste, and shareable export tests assert identical selection/qualification, including ENH-3528's unreconciled-sum fallback.
- [ ] Rebuild and interrupted/retried replay preserve live-only rows and never leave partially replaced rollout accounting. Source relocation/copy does not change canonical totals for verified identities.
- [ ] Partial/malformed and unproven rollout observations remain `unknown`; only producer-verified, consistent complete rows become `measured`. Empty and wrong-type usage containers obey BUG-3531's contract without raising or fabricating zero.

## Scope Boundaries

- **In scope**: Codex rollout normalization/ingestion, metadata-bearing replay, corrected source-host attribution and legacy qualification, request/snapshot/reset identity, persisted uniqueness, live identity plumbing, shared live-vs-historical coverage selection and minimum reader/export qualification, idempotent replay.
- **Prerequisites**: ENH-3538 (provenance/host/observation-time columns, nullable components, host-preserving replay iterator), BUG-3531 (shared `normalize_codex_input`). BUG-3530 (`channel` column; rebuild preserves live rows) is done.
- **Out of scope**: other-host usage ingestion (ENH-3534); Codex pricing; changing live token normalization beyond BUG-3531; exact Claude overlap reconciliation; ENH-3528's richer rendering contract. The shared raw-ingest host correction and live identity plumbing are explicit exceptions to the earlier live-capture boundary.

## Implementation Steps

1. Resolve the readiness gates with producer fixtures after BUG-3531's contract investigation; write the key, host-attribution, state/order, and live-coverage decisions into this issue.
2. Add metadata-bearing adapters for direct files and database replay; correct new raw-event source-host stamping and conservatively qualify legacy attribution.
3. Add persisted observation identity/uniqueness and per-session normalization state; implement transactional, idempotent rollout replay with relocation/copy/interruption regressions.
4. Carry live identities and intervals to persistence; implement the shared coverage selector and apply it to usage, cost, waste, and exports. Preserve unresolved observation sums and channel subtotals.
5. Verify end-to-end ingestion/rebuild/reporting against malformed, partial, mixed-host, overlapping, and legacy fixtures; update schemas/docs/export contracts and run focused tests plus required project checks.

## Program Design

### Types

- `UsageReplayRecord` — parsed payload plus outer event type, session ID, verified host/attribution basis, event time, source position/basis, and diagnostic source label; no assumption that the payload is an envelope.
- `CodexUsageState` — per-session/stream cumulative baseline, reset epoch, ordering boundary, and identity/notification evidence; maintained explicitly by the caller.
- `UsageObservation` — ENH-3538's nullable token components and provenance plus channel, session/invocation correlation, verified source/request identity, coverage interval/basis and attribution metadata. Extend/wrap `TokenUsage` rather than duplicating its component semantics; do not assume the foundation already supplies these identities.
- Coverage-selection result — selected observations/basis, per-channel subtotals, unresolved observations and reasons; shared across aggregation/export readers.

### Signatures

- `normalize_codex_usage(record: UsageReplayRecord, *, state: CodexUsageState) -> list[UsageObservation]` — proposed interface; zero or one observation plus explicit updates to per-session state. Input splitting and container/component rules delegate to BUG-3531; callers partition/order records using the resolved identity contract.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing; extended to route Codex rollouts through the normalizer.

### Call Path

- direct envelope / stored payload + database columns → `UsageReplayRecord` → per-session `normalize_codex_usage` → idempotent `usage_events` write
- live identity events + `usage_from_event` → runner/executor identity retention → `record_usage_event`
- persisted observations → shared coverage selector → usage/cost/waste/export readers → ENH-3528 provenance rendering when available

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `_iter_events` (`writers.py` L3430) yielded `(raw_line, source_label)` only; `_codex_cache_usage` (`ctx_stats.py` L356) was the sole rollout `token_count` reader. The earlier dependency assessment is superseded: BUG-3530 is done, prerequisites are ENH-3538 and BUG-3531, and BUG-3531 has a `blocks` backlink. The prospective implementation gaps below were not resolved by that verification.

### Applied pre-implementation review 2026-09-24

Fixture probes confirmed replay receives an inner `token_count` payload without session/time/ordinal, and a Codex handle ingested under a Claude host replays with the wrong host. Added metadata-bearing replay, source-host qualification, explicit readiness gates for persisted identity and per-session state, live identity plumbing, and shared coverage selection with conservative unresolved behavior. Folded rebuild ownership into Design; the current deletion predicate already covers rollout rows. Expanded ACs for relocation/copy/interruption, partial overlap, and conditional measured provenance. The review's 34 focused existing tests and evidence checks passed, but do not establish the new producer/identity contracts. Specification changes only; readiness gates remain outstanding.

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`

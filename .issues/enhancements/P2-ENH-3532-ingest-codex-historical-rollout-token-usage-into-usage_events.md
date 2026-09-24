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
- BUG-3542
relates_to:
- ENH-3528
- ENH-3543
blocks:
- ENH-3543
---

# ENH-3532: Ingest Codex historical rollout token usage into usage_events

## Summary

Ingest Codex historical rollout usage (`event_msg` / `token_count`) into `usage_events` with defined normalization, deduplication, and rebuild behavior. This is Delivery B split out of ENH-3528: it builds on ENH-3538's per-observation provenance/host/observation-time columns (the foundation extracted from ENH-3528) and on the Codex normalization fix in BUG-3531. Both are done. It does not depend on ENH-3528's reporting work; ENH-3528 lands first and reports the rollout rows conservatively. Codex live `turn.completed` capture already works and must keep working.

**Split 2026-09-24:** the raw-ingest source-host correction → BUG-3542 (prerequisite); live identity plumbing and the shared live/rollout coverage selector → ENH-3543 (follows this issue). This issue keeps rollout normalization, persisted identity/uniqueness, metadata-bearing replay and idempotent rebuild.

## Current Behavior

- Codex live usage reaches `usage_events` via `usage_from_event` → runner `ActionResult.usage_events` → `FSMExecutor._finish` → `record_usage_event`.
- Historical rollout `token_count` events are read only by `ctx_stats._codex_cache_usage` for a cache-hit rate; they never reach `usage_events`.
- `parse_codex_rollout` yields a `SessionEvent` whose payload is the inner Codex object. `_backfill_raw_events` serializes that payload: stored usage records have `type='token_count'`, not the original `event_msg` envelope. Timestamp, session ID, outer event type, and line position are stored separately; native envelope ordinals are not preserved by this path.
- The in-progress metadata iterator in `scripts/little_loops/session_store/writers.py` supplies line/source/host, but not the other replay metadata. The rebuild cursor in `scripts/little_loops/session_store/lifecycle.py` selects only `raw_line, source_path, host` ordered by database ID.
- `_backfill_raw_events` stamps the ingesting/configured host instead of `SessionHandle.host`; BUG-3542 fixes this and adds a verified-attribution discriminator, which this issue's replay consumes.
- Live observations carry no session/invocation identity (ENH-3543 owns adding it). The raw-ingest function in `scripts/little_loops/session_store/lifecycle.py` documents uniqueness as `(source_path, line_no)`, which does not deduplicate moved or copied rollouts.

## Expected Behavior

Codex rollout usage is persisted as normalized, provenance-labeled observations. Repeated notifications, cumulative snapshots, and compaction resets never inflate verified consumption totals. Reconciled live/historical coverage contributes once; unmatched coverage remains explicitly unresolved, never advertised as deduplicated consumption. Ingestion and rebuild are idempotent.

## Integration Map

- `scripts/little_loops/session_store/{codex,sessions,writers,lifecycle}.py` — rollout normalization, metadata-bearing replay, verified source host, stable source identity and idempotent `_backfill_usage_events`.
- `scripts/little_loops/session_store/{schema,queries}.py`, `schema_manifest.json` — append-only migration for observation identity/uniqueness and any required attribution/coverage metadata; shared aggregate selection; safe export compatibility. Reuse ENH-3538's columns rather than adding them again.
- `scripts/little_loops/cli/ctx_stats.py` — `_codex_cache_usage` may switch to stored observations only when session selection stays equivalent (optional).
- Tests: `test_session_store_writers.py`, `test_session_store_lifecycle.py`, schema/manifest tests, Codex parser tests, `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, `test_feat3304_artifact_dashboard.py`, and `scripts/tests/fixtures/codex/`.
- Docs: `docs/codex/usage.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/HOST_COMPATIBILITY.md`.

## Impact

- **Priority**: P2.
- **Effort**: Medium — BUG-3531 removed cumulative differencing; the remaining work is replay metadata, persisted uniqueness and idempotent rebuild.
- **Risk**: Medium to high — wrong grain handling double-counts tokens.

## Design

Normalize native events into the canonical contract shared with live capture (BUG-3531):

- Input columns represent uncached input plus separate cache-read/cache-write components; partial/inconsistent components remain identifiable rather than inventing a measured split.
- Output totals must not add reasoning tokens again when already included; establish with fixtures.
- Distinguish per-request counts (`last_token_usage`) from cumulative snapshots (`total_token_usage`). Repeated notifications must not duplicate usage; compaction/reset boundaries must not produce negative deltas or cross-session attribution. Do not blindly sum either field.
- Carry verified host, session, acquisition channel (`rollout`), observation scope/time, stable source identity, and conservative row provenance. `measured` applies BUG-3531's (done) producer-contract gate for this acquisition path, a consistent input split, and valid known output; malformed/partial or unproven observations remain `unknown`. Omitted cache-write is not zero without path-specific evidence. Rate-limit-only events (`info: null`) and absent usage create no rows; malformed or present-but-empty usage follows BUG-3531's container contract.

### Replay input and host attribution

Introduce a usage-specific metadata record carrying the parsed payload plus outer event type, event timestamp, session ID, verified host/host-attribution basis, source position and its basis, and a diagnostic source label. Both raw rollout envelopes and stored inner payloads adapt to this record before normalization. Select the necessary `raw_events` columns explicitly; never expect `timestamp`, `sessionId`, or `ordinal` inside a stored `token_count` payload. Preserve the existing two-tuple `_iter_events` API for unrelated consumers.

Source-host correction for new raw ingestion, and its attribution discriminator, are BUG-3542. Replay reads that discriminator. Rows it marks verified carry their host into `usage_events`; legacy rows get an unknown host with a reason. Neither a non-NULL legacy `raw_events.host` nor the currently configured host proves source identity.

### Observation identity, state, and persistence

Separate **source-event identity** (the same recorded event ingested again) from **request identity** (multiple notifications describing the same work). A source path or database row ID is not a durable observation identity. Prefer a verified native event/request identity scoped by host and session; a native ordinal also needs its verified stream/reset namespace. A session plus original source position is a fallback only when fixtures establish that the position survives copying/archiving and identifies the same stream. Do not synthesize identity from equal token counts, timestamps, or content hashes alone; distinct requests may have identical usage.

Before implementation readiness, record the exact persisted key, fallback rules, reset namespace, and uniqueness constraint in this issue, backed by the producer fixtures. Add the key and a scoped unique index in an append-only migration; do not place all unknown identities under a shared sentinel key. A repeated key with conflicting content must surface a conflict, not silently overwrite or count twice. When identity cannot be established, retain uncertainty and exclude it from claims of verified deduplicated consumption.

Use explicit mutable state per verified session/stream for key/span bookkeeping and notification-identity evidence; no prior cumulative components are needed (readiness gate 3). The interactive fixture has multiple usage observations within one `task_started`/`task_complete` turn: a turn ID alone is not a request key. Keep state isolated when rebuild order interleaves sessions; do not depend on `ORDER BY id` being chronological within each source. Define ordering and incomplete-prefix behavior. A prior cumulative snapshot alone does not resolve repeated notifications, resets, or equal-count distinct requests. Preserve the last trustworthy baseline across malformed notifications according to a fixture-backed rule; never fabricate a delta from unknown components.

`channel='rollout'` is replayable. BUG-3530's existing `channel IS NOT 'live'` rebuild predicate already includes it; test that behavior rather than adding a conflicting deletion rule. Perform derived-row replacement and replay transactionally so interruption cannot leave half-rebuilt accounting; preserve live rows and make retries stable. Test source relocation and copies as well as repeated ingestion of an unchanged path.

### Live identity and coverage selection

Moved to ENH-3543. Until it lands, rollout rows and live rows for the same work coexist, and readers expose them as an unreconciled observation sum (ENH-3528's conservative contract). Rows written here must carry the source identity (session ID + `task_started`/`task_complete` span) that ENH-3543 needs for matching.

### Implementation readiness gates

**Already resolved by BUG-3531 and its committed fixtures (`scripts/tests/fixtures/codex/`, `codex-cli 0.152.1`). Adopt these; do not re-investigate:**

- **Per-request vs cumulative:** persist one observation per `last_token_usage`; never difference or sum `total_token_usage`. `total` restarts on `exec resume`, so it is not a durable cumulative baseline (fixture: invocation 2 `last` = `total` = 19559/19328/0/5).
- **Containers:** Decision 1 "Rollout containers": missing or null `info` means no usage; `info` without `last_token_usage` means no observation, with no fallback to `total`; empty, null or non-object `last_token_usage`, or non-object `info`, counts once as excluded. Nothing raises.
- **Zero:** an all-zero rollout `last_token_usage` is a valid zero observation (the live all-zero rule does not apply).
- **Reasoning:** `reasoning_output_tokens` is already included in `output_tokens` (`rollout-interactive.jsonl`); never add it again.
- **Input split:** `normalize_codex_input`; omitted cache-write is unknown.
- **Session identity:** rollout `session_meta.payload.session_id` equals live `thread.started.thread_id` (`rollout-exec-resume.jsonl` / `exec-json-turn.jsonl`).
- **Relocation:** archiving moves the rollout to `~/.codex/archived_sessions/` without changing its content (fixture README § Archive-behavior), so `source_path` is not identity, but content position within one session's file is stable across archive.

**Still open; record decisions here before implementation:**

1. **Request key.** Candidate: `(host, session_id, ordinal_of_token_count_within_session_file)`. The fixtures show a top-level `ordinal` on each rollout line; verify it survives replay (the stored inner payload lacks it, so `_backfill_raw_events` must persist it or `line_no` must be proven equivalent) and archive. Duplicate `token_count` notifications for one request: check `rollout-interactive.jsonl` for a repeated `last_token_usage` with no intervening model request. If none exists in any fixture, record "no duplicate notifications observed in 0.152.1" and let the unique key handle exact re-ingestion only.
2. **Reset namespace.** Mid-invocation compaction is uncaptured. Decide the conservative rule: since `last_token_usage` is per request, compaction does not affect per-request rows; only the span-sum consistency check in ENH-3543 is affected.
3. **Ordering.** Normalization no longer needs cumulative state (item 1 above), so per-session mutable state reduces to the key/span bookkeeping. Confirm and simplify `CodexUsageState` accordingly.

If a case lacks producer evidence, choose the conservative unresolved behavior rather than inventing a match.

## Acceptance Criteria

- [ ] Historical rollout usage reaches `usage_events` (`channel='rollout'`) through `normalize_codex_input` and BUG-3531's rollout container rules; `rollout-exec-resume.jsonl` yields exactly three rows (58504 input / 46080 cached / 0 cache-write in total); live capture continues to work.
- [ ] Fixtures cover repeated notifications, per-request vs cumulative values, compaction resets, multiple sessions, malformed/partial records, rate-limit-only records, and observed-model absence. Valid distinct requests with equal counts remain distinct.
- [ ] Repeated ingestion and rebuild leave canonical totals stable and preserve live-only rows (relies on BUG-3530).
- [ ] Rollout rows take their host from BUG-3542's verified attribution, never from the currently configured host; legacy-attributed rows carry an unknown host with a reason.
- [ ] The same fixture ingested directly and replayed from stored inner payloads produces equivalent observations, including session, event time, outer type, and source position. Existing `_iter_events` consumers remain compatible.
- [ ] Source/request keys, fallback rules, reset namespace, host-attribution discriminator, and database uniqueness are documented and fixture-backed before implementation readiness. Tests cover archive/move, copied sources, repeated notifications, conflicting duplicate keys, equal-count distinct requests, and unknown identities.
- [ ] Interleaved sessions, out-of-order ingestion, incomplete prefixes, malformed snapshots, and compaction/reset boundaries cannot share normalization state or produce fabricated deltas. Multiple request observations in one turn remain distinct.
- [ ] Each rollout row persists the session ID and `task_started`/`task_complete` span that ENH-3543 matches on.
- [ ] Rebuild and interrupted/retried replay preserve live-only rows and never leave partially replaced rollout accounting. Source relocation/copy does not change canonical totals for verified identities.
- [ ] Partial/malformed and unproven rollout observations remain `unknown`; only producer-verified, consistent complete rows become `measured`. Empty and wrong-type usage containers obey BUG-3531's contract without raising or fabricating zero.

## Scope Boundaries

- **In scope**: Codex rollout normalization/ingestion, metadata-bearing replay, request/reset identity, persisted uniqueness, idempotent transactional replay.
- **Prerequisites**: BUG-3542 (verified source host). ENH-3538, BUG-3531 and BUG-3530 are done.
- **Split out**: BUG-3542 (raw-ingest host correction); ENH-3543 (live identity plumbing, shared coverage selector, reader/export selection).
- **Out of scope**: other-host usage ingestion (ENH-3534); Codex pricing; changing live token normalization beyond BUG-3531; exact Claude overlap reconciliation; ENH-3528's richer rendering contract.

## Implementation Steps

1. Close the three open readiness gates above against the fixtures and record the decisions here.
2. Add metadata-bearing adapters for direct files and database replay (persist the rollout `ordinal` if needed), reading BUG-3542's attribution.
3. Add persisted observation identity/uniqueness; implement transactional, idempotent rollout replay with relocation/copy/interruption regressions.
4. Verify ingestion/rebuild against malformed, partial, mixed-host and legacy fixtures; update schemas/docs and run focused tests plus required project checks.

## Program Design

### Types

- `UsageReplayRecord` — parsed payload plus outer event type, session ID, verified host/attribution basis, event time, source position/basis, and diagnostic source label; no assumption that the payload is an envelope.
- `CodexUsageState` — per-session key/span bookkeeping (current `task_started` span, request ordinal); no cumulative baseline, since observations come from `last_token_usage` only (readiness gate 3).
- `UsageObservation` — ENH-3538's nullable token components and provenance plus channel, session ID, verified source/request identity, turn span and attribution metadata (live invocation correlation is ENH-3543). Extend/wrap `TokenUsage` rather than duplicating its component semantics; do not assume the foundation already supplies these identities.

### Signatures

- `normalize_codex_usage(record: UsageReplayRecord, *, state: CodexUsageState) -> list[UsageObservation]` — proposed interface; zero or one observation plus explicit updates to per-session state. Input splitting and container/component rules delegate to BUG-3531; callers partition/order records using the resolved identity contract.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing; extended to route Codex rollouts through the normalizer.

### Call Path

- direct envelope / stored payload + database columns → `UsageReplayRecord` → per-session `normalize_codex_usage` → `normalize_codex_input` → `record_usage_event` (idempotent `usage_events` write)
- persisted observations → ENH-3528 conservative reporting (unreconciled sum until ENH-3543)

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `_iter_events` (`writers.py` L3430) yielded `(raw_line, source_label)` only; `_codex_cache_usage` (`ctx_stats.py` L356) was the sole rollout `token_count` reader. The earlier dependency assessment is superseded: BUG-3530 is done, prerequisites are ENH-3538 and BUG-3531, and BUG-3531 has a `blocks` backlink. The prospective implementation gaps below were not resolved by that verification.

### Applied pre-implementation review 2026-09-24

Fixture probes confirmed replay receives an inner `token_count` payload without session/time/ordinal, and a Codex handle ingested under a Claude host replays with the wrong host. Added metadata-bearing replay, source-host qualification, explicit readiness gates for persisted identity and per-session state, live identity plumbing, and shared coverage selection with conservative unresolved behavior. Folded rebuild ownership into Design; the current deletion predicate already covers rollout rows. Expanded ACs for relocation/copy/interruption, partial overlap, and conditional measured provenance. The review's 34 focused existing tests and evidence checks passed, but do not establish the new producer/identity contracts. Specification changes only; readiness gates remain outstanding.

### Pre-implementation review 2026-09-24 (split)

Removed the resolved blockers (ENH-3538, BUG-3531); now blocked by BUG-3542. Imported BUG-3531's resolved decisions into the readiness gates, leaving three open gates (request key, reset namespace, ordering). Moved live identity and coverage selection to ENH-3543, and host correction to BUG-3542.

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`

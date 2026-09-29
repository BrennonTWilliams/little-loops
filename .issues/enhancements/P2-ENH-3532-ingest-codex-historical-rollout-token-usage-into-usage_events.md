---
id: ENH-3532
type: ENH
title: Ingest Codex historical rollout token usage into usage_events
priority: P2
status: done
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
completed_at: '2026-09-29T08:22:41Z'
captured_at: '2026-09-24T00:20:39Z'
labels:
- observability
- multi-host
relates_to:
- BUG-3542
- ENH-3528
- ENH-3543
- ENH-3546
- ENH-3647
- ENH-3651
- ENH-3655
blocks:
- ENH-3543
- ENH-3549
- ENH-3534
reconcile_attempted: true
confidence_score: 85
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

# ENH-3532: Ingest Codex historical rollout token usage into usage_events

## Summary

Ingest Codex historical rollout usage (`event_msg` / `token_count`) into `usage_events` with defined normalization, deduplication, and rebuild behavior. This is Delivery B split out of ENH-3528: it builds on ENH-3538's per-observation provenance/host/observation-time columns (the foundation extracted from ENH-3528) and on the Codex normalization fix in BUG-3531. Both are done. It does not depend on ENH-3528's reporting work; ENH-3528 lands first and reports the rollout rows conservatively. Codex live `turn.completed` capture already works and must keep working.

**Split 2026-09-24, updated 2026-09-29:** the raw-ingest source-host correction → BUG-3542 (completed prerequisite); live identity plumbing → ENH-3647; shared live/rollout coverage selector → ENH-3543; incremental derive and catch-up → ENH-3651. This issue keeps rollout normalization, persisted identity/uniqueness, metadata-bearing replay and idempotent full-rebuild materialization.

## Current Behavior

- Codex live usage reaches `usage_events` via `usage_from_event` → runner `ActionResult.usage_events` → `FSMExecutor._finish` → `record_usage_event`.
- Historical rollout `token_count` events are read only by `ctx_stats._codex_cache_usage` for a cache-hit rate; they never reach `usage_events`.
- `parse_codex_rollout` yields a `SessionEvent` whose payload is the inner Codex object. `_backfill_raw_events` serializes that payload: stored usage records have `type='token_count'`, not the original `event_msg` envelope. Timestamp, session ID, outer event type, and line position are stored separately; native envelope ordinals are not preserved by this path.
- The existing metadata iterator in `scripts/little_loops/session_store/writers.py` supplies line/source/host, but not the other replay metadata. The rebuild cursor in `scripts/little_loops/session_store/lifecycle.py` selects `raw_line, source_path, host, host_basis` ordered by database ID.
- `_backfill_raw_events` previously stamped the ingesting/configured host instead of `SessionHandle.host`; BUG-3542 (completed) fixed this and added a verified-attribution discriminator, which this issue's replay consumes.
- **Derivation is rebuild-only (2026-09-29).** `_backfill_usage_events` is called from `rebuild()` alone (`session_store/lifecycle.py`), a full delete-then-replay of the derived tables; the SessionStart worker's `backfill_incremental` is ingest-only (`raw_events`) and passes `--rebuild` only when `SCHEMA_VERSION` has advanced. This issue adds the rollout normalizer and verifies full-rebuild materialization; ENH-3651 owns the shared incremental derive (including rollout after this normalizer lands), initial catch-up and checkpoint. ENH-3549's Codex cutover waits for the combined ingest → derive → read test.
- Live observations carry no session/invocation identity (ENH-3647 owns adding it). The raw-ingest function in `scripts/little_loops/session_store/lifecycle.py` documents uniqueness as `(source_path, line_no)`, which does not deduplicate moved or copied rollouts.

## Expected Behavior

Codex rollout usage is persisted as normalized, provenance-labeled observations. Repeated notifications, cumulative snapshots, and compaction resets never inflate verified consumption totals. Reconciled live/historical coverage contributes once; unmatched coverage remains explicitly unresolved, never advertised as deduplicated consumption. Ingestion and rebuild are idempotent.

## Integration Map

- `scripts/little_loops/session_store/{codex,sessions,writers,lifecycle}.py` — rollout normalization, metadata-bearing replay, verified source host, stable source identity and idempotent `_backfill_usage_events`.
- `scripts/little_loops/session_store/{schema,queries}.py`, `scripts/little_loops/session_store/schema_manifest.json` — append-only migration for observation identity/uniqueness and any required attribution/coverage metadata; identity fields consumed by ENH-3543; aggregate selection and export reconciliation belong to ENH-3543. Reuse ENH-3538's columns rather than adding them again.
- `scripts/little_loops/cli/ctx_stats.py` — ENH-3549 owns switching cache reporting to stored observations with equivalent session selection; no second reader migration belongs here.
- `scripts/little_loops/issue_history/quality_regressions.py` — counts `usage_events` rows `WHERE session_id IS NOT NULL` per session for model-composition weights; today that predicate means `channel = 'transcript'`. Rollout rows carrying a `session_id` would silently enter the weighting, so pin the query to `channel = 'transcript'` (no-op if ENH-3647 landed first). ENH-3543 decides whether it later reads through the selector.
- `scripts/little_loops/issue_history/agent_quality.py` — `_usage_totals` (cost per issue) reads every `usage_events` row with a non-NULL `session_id` through `select_usage_observations`. Rollout (and, after ENH-3647, live) rows carrying a `session_id` would double-count tokens and add unpriced rows that can drop priced coverage below the threshold and hide the verdict. Pin it to `channel = 'transcript'` alongside `quality_regressions` until ENH-3543 routes it through the reconciling selector.
- Schema: this issue's migration is ordered in the epic's § Schema coordination with ENH-3647 and ENH-3546; ~20 tests pin `SCHEMA_VERSION`.
- Tests: `test_session_store_writers.py`, `test_session_store_lifecycle.py`, schema/manifest tests, Codex parser tests, `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, `test_feat3304_artifact_dashboard.py`, and `scripts/tests/fixtures/codex/`.
- Docs: `docs/codex/usage.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/HOST_COMPATIBILITY.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

**Conventions in force (pattern-finder, this pass):**
- Usage replay is one function fed by a shared iterator: `_backfill_usage_events` (`writers.py`) reads `_iter_events_with_host`, which yields `(line, source_label, host, host_basis)`; other `_backfill_*` parsers use the two-tuple `_iter_events` wrapper. The `rebuild()` cursor in `lifecycle.py` already selects `raw_line, source_path, host, host_basis` (v55 added `host_basis`) — Current Behavior now records all four cursor columns after the epic review. The iterator reads extra columns positionally, guarded by row length, so added replay metadata (line number, ordinal) must extend the cursor and tuple in lockstep while leaving `_iter_events` callers intact.
- `_backfill_usage_events` accepts only `type == "assistant"` records with `message.usage`; Codex `token_count` is an `event_msg` payload and is not admitted today. Only qwen has a replay-time host shim (keyed on `host == "qwen"`). `_codex_cache_usage` (`cli/ctx_stats.py`) is the only current `token_count` reader and reads live files via `iter_events(handle)`, not `raw_events`.
- Codex token normalization has a single entry point: `normalize_codex_input` (`subprocess_utils.py`) returning frozen `CodexInputSplit(uncached_input, cache_read, cache_write, consistent)`; missing values are never coerced to zero. `TokenUsage` already carries nullable components, `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis` (ENH-3538).
- Provenance for backfilled rows is set differently per path today: the backfill path hardcodes `unknown`/`request`, while `_codex_cache_usage` labels its aggregate `measured`. The issue's conditional-`measured` rule is a decision, not an inherited convention.
- `usage_events` has no uniqueness constraint today (`record_usage_event` docstring states so); columns arrive via nullable `ALTER TABLE ADD COLUMN` (v29 `run_id`, v53 `channel`, v54 provenance/host/scope/observed_at, v55 `host_basis`); v53 is the only migration that backfilled. Current `SCHEMA_VERSION` is 55, so this lands as v56, and ~20 tests hardcode `SCHEMA_VERSION == 55` in `test_session_store_schema.py`.
- Migrations are an append-only `_MIGRATIONS` list of SQL strings, each preceded by a `# vN (ISSUE-ID): ...` comment, split on `;` by `_split_sql_statements` (no semicolons in literals). Unique indexes are named `idx_<table>_dedup`; scoped uniqueness uses a partial `WHERE` (e.g. `idx_summary_nodes_leaf_dedup`, `idx_issue_events_dedup`). **Contested**: original migrations create the index bare, while a later repair migration deletes duplicates first because a bare create on existing duplicates raises `IntegrityError` and rolls back — `usage_events` already holds duplicate-prone rows, so the repair-first shape is the one that applies. Writers rely on such indexes through `INSERT OR IGNORE`, which silently swallows conflicting content — the issue's "conflict must surface" requirement diverges from that convention and needs a deliberate mechanism.
- `schema_manifest.json` is PRAGMA-derived and regenerated (snippet in the `TestSchemaManifest` docstring), guarded by `test_schema_manifest_matches_checked_in_file`; it records partial-unique flags but not the `WHERE` predicate.
- Rebuild scope is `_REBUILD_TABLE_PREDICATES["usage_events"] = "channel IS NOT 'live'"` (`lifecycle.py`), whose comment already names `rollout` as replayable. `rebuild()` issues per-table DELETEs, replays, then one `conn.commit()`, with no explicit `BEGIN`/`SAVEPOINT` in `lifecycle.py` — transactional atomicity of derived-row replacement is not an existing property and must be established and tested.
- Test convention for rebuild idempotency: `test_rebuild_derives_codex_tool_events` (`test_session_store_lifecycle.py`) copies a `scripts/tests/fixtures/codex/` rollout into a temp `.codex/sessions/` tree, runs `detect_sessions` → `backfill` → `rebuild`, then re-runs `rebuild` and asserts equal counts; `test_usage_rows_carry_host_basis_after_rebuild` shows `usage_events` assertions post-rebuild. Fixtures `rollout-interactive.jsonl`, `rollout-exec.jsonl`, `rollout-exec-resume.jsonl` already contain `token_count` records.
- Searched, no precedent: another host's `token_count` ingestion into `usage_events`; any unique index on `usage_events`; `line_no`/`source_path` columns on `usage_events`.

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

### Persisted key and evidence boundary

The earlier candidate `(host, session_id, ordinal)` is invalid for forks and paginated threads (gate 1 below). For `token_usage_record`, test `(host, response_id)` against current-version fixtures; for older `token_count`, test `(host, payload.id, verified stream discriminator, native ordinal)`. Record the exact migration/index and fallback decision before implementation; do not substitute physical line number or token-event sequence for native ordinal without evidence. In the trimmed `rollout-exec-resume.jsonl`, token events are at physical lines 6, 7, 12 with native ordinals 15, 18, 27. Direct and database replay must preserve the chosen position basis. Legacy rows without that basis remain unresolved rather than acquiring a fabricated native identity.

Exact re-ingestion deduplication and duplicate notifications for one request are separate guarantees. The current captures contain no repeated usage notification demonstrating that second case. Synthetic fixtures can test conservative behavior, but cannot establish a producer contract. Do not label unknown request uniqueness as verified deduplicated consumption merely because all rows have `channel='rollout'`.

Use existing `usage_events.session_id` for the verified host-observed **thread** ID (`session_meta.payload.id`) on both rollout and live rows, qualified by host and an identity-basis marker. The root/parent `payload.session_id` is not this column in a fork. Reuse existing `invocation_id` for local correlation in ENH-3647. This issue and ENH-3647 must agree on span/identity-basis field names before either migration; no second unjoined session column or duplicate invocation column.

### Live identity and coverage selection

Live identity capture moved to ENH-3647; coverage selection moved to ENH-3543. Until the selector lands, rollout rows and live rows for the same work coexist, and readers expose them as an unreconciled observation sum (ENH-3528's conservative contract). Rows written here must carry the source identity (host + thread ID + `task_started`/`task_complete` span) that ENH-3543 needs for matching.

### Implementation readiness gates

**Already resolved by BUG-3531 and its committed fixtures (`scripts/tests/fixtures/codex/`, `codex-cli 0.152.1`). Adopt these; do not re-investigate:**

- **Per-request vs cumulative:** persist one observation per `last_token_usage`; never difference or sum `total_token_usage`. `total` restarts on `exec resume`, so it is not a durable cumulative baseline (fixture: invocation 2 `last` = `total` = 19559/19328/0/5).
- **Containers:** Decision 1 "Rollout containers": missing or null `info` means no usage; `info` without `last_token_usage` means no observation, with no fallback to `total`; empty, null or non-object `last_token_usage`, or non-object `info`, counts once as excluded. Nothing raises.
- **Zero:** an all-zero rollout `last_token_usage` is a valid zero observation (the live all-zero rule does not apply).
- **Reasoning:** `reasoning_output_tokens` is already included in `output_tokens` (`rollout-interactive.jsonl`); never add it again.
- **Input split:** `normalize_codex_input`; omitted cache-write is unknown.
- **Session identity in the non-fork fixtures:** rollout `session_meta.payload.session_id` equals live `thread.started.thread_id` (`rollout-exec-resume.jsonl` / `exec-json-turn.jsonl`). Forks disprove that equality as a general rule; gate 1c uses `payload.id` for the thread ID.
- **Relocation:** archiving moves the rollout to `~/.codex/archived_sessions/` without changing its content (fixture README § Archive-behavior), so `source_path` is not identity, but content position within one session's file is stable across archive.

**Fixture findings recorded 2026-09-28 (epic review; `codex-cli 0.152.1`):**

- Every line in all three rollout fixtures carries a top-level `ordinal` (34/34, 14/14, 13/13).
- Within `rollout-exec-resume.jsonl` the ordinal is monotonic across `exec resume`: invocation 1's span occupies ordinals 1–19 and invocation 2's 21–28 in the same file. Resume does not start a new ordinal namespace.
- In untrimmed captures `ordinal == physical line − 1` (`rollout-interactive.jsonl`: lines 16/24/28/33 ↔ ordinals 15/23/27/32); only the trimmed fixture separates them. That is why ordinal, not line, must be persisted.
- No fixture contains a repeated `last_token_usage`: the four interactive observations (14002/107, 21854/135, 22068/82, 26079/237) are distinct and each follows a tool-call output. Recorded: **no duplicate notifications observed in 0.152.1.**
- `task_started` and `task_complete` carry `payload.turn_id`, a native span key. It is the span identity ENH-3543 matches on; it is not a request key (the interactive turn holds four observations).
- `session_meta.payload.context_window.window_id` exists on every session. It is an unverified lead for the compaction/reset namespace (gate 2).
- **Corpus findings 2026-09-29** (local `~/.codex/sessions`, newer than the fixtures): forks reuse the parent's `payload.session_id` with ordinals restarting at 0; 44 events in 20 files (0.154/0.155 alphas) repeat the previous event's `total_token_usage`, 39 of them with an identical `last_token_usage`; 0.154+ adds `token_usage_record` alongside `token_count`. The "no duplicate notifications observed" statement above holds for 0.152.1 only. Gate 1 records the consequences; add a fixture per shape (see Acceptance Criteria).

**Readiness gates:**

### Implemented schema and conservative request contract (2026-09-29)

The v56 migration adds `raw_events.ordinal` alongside physical `line_no`. It adds nullable `usage_events.identity_basis`, `turn_id`, `request_id`, `request_identity_basis`, `stream_id`, `source_ordinal`, and `source_line_no`. **Shared contract for ENH-3647:** `session_id` is the host-observed Codex thread ID (`session_meta.payload.id` / live `thread.started.thread_id`), `identity_basis='host_observed'` only for verified identity, and `invocation_id` remains the locally generated live invocation ID. `turn_id` names the rollout's native closed span; `request_id` holds `token_usage_record.response_id`. Do not create duplicate session/invocation columns in ENH-3647.

Current 0.158.0 exec/resume/fork captures confirm `token_usage_record` and an adjacent `token_count` describe the same request; replay prefers the native response record when both have identical usage and adjacent native ordinals. A mixed synthetic stream retains an old-shape-only `token_count` as an unknown observation. Exact replayed copies of a native response collapse during rebuild; conflicting reuse retains unknown rows with a diagnostic. Older `token_count` has no proven global request identity. `stream_id` (`thread ID : session_meta timestamp`) is diagnostic, **not** a uniqueness key: the page discriminator and global response-ID uniqueness remain unproven. No unique index is created at v56. Legacy raw rows with NULL ordinal remain unverified rather than receiving a fabricated key.

The 0.158.0 fork has a new `session_meta.payload.id` **and** `payload.session_id`; `forked_from_id` names the parent. Its live total includes inherited parent usage (ENH-3655), while its rollout request is scoped to the new thread. Earlier 0.152.1 fork corpus behavior differs; the thread ID rule is stable across both. Rollout `provenance='measured'` requires a valid disjoint input split, valid output, an observed model, a closed turn, a verified source host/thread, and a native response ID without conflict. Old-shape-only, partial, malformed, legacy-host and incomplete-span rows remain `unknown`; all live/rollout overlap remains unresolved for ENH-3543. The focused implementation plan is `thoughts/shared/plans/2026-09-29-ENH-3532-management.md`.

1. **Request key — REVISED 2026-09-29 (supersedes the earlier `(host, session_id, ordinal)` proposal, which fails on real data).** Corpus review of `~/.codex/sessions` (9,572 rollouts; fixtures are `codex-cli 0.152.1`, sessions there are written by 0.154/0.155/0.158 alphas) and a second-model consult (`/ll:advise`, opus) found:
   - **Forks collide.** `codex fork` exists in 0.152.1. In a fork, `session_meta.payload.session_id` is the **parent's** id, `payload.id` is the fork's own, `payload.forked_from_id` is set, and ordinals restart at 0. Of 15 forked rollouts (235 token events), 31 events share `(session_id, ordinal)` with a parent event carrying *different* usage — false conflicts under the old key. Forks do not copy parent usage.
   - **`payload.id` alone also collides.** 3 thread ids span more than one file (attributed to Codex Desktop paginated threads: several files, same `id`/`session_id`, ordinals restarting at 0; not independently confirmed here).
   - **Two event shapes.** 0.154+ writes a top-level `token_usage_record` event (own `ordinal`; payload `thread_id`, `turn_id`, `session_id`, `root_turn_id`, `response_id`, `usage{input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens, total_tokens}`, `turn_token_usage`, `thread_token_usage`) *in addition to* `token_count`. Every one of 123 scanned files with records also had `token_count` with info, so reading both double-counts every request. `cache_write_input_tokens` is reported there.

   Revised rules (confirm each against fixtures at implementation start):
   - **a. Observation source.** Prefer `token_usage_record` for a request when current-version producer evidence establishes its `response_id` and span coverage: candidate key `(host, response_id)`, span `turn_id`, keep `root_turn_id`. Do **not** suppress every `token_count` merely because another record in the file has the new shape. Capture a mixed/partial stream and prove whether each old-shape request has a new-shape counterpart. Where that cannot be established, keep the candidate explicitly unresolved for audit rather than silently discarding it or counting both as verified consumption. Older rollouts with no `token_usage_record` use `token_count.last_token_usage`.
   - **b. Key without a `response_id`.** `(host, payload.id, stream discriminator, ordinal)`. Candidate discriminator: the file's `session_meta.timestamp` (backed by only 3 threads — verify before relying on it). No physical-line fallback.
   - **c. Meaning of `session_id` on usage rows.** Decide once, record here and in ENH-3647/ENH-3549. Recommended: the **thread** id (`payload.id`), matching `sessions.py` (`payload.get("id")`), `SessionHandle` and `raw_events.session_id`, so ENH-3549's handle lookup agrees. Keep `forked_from_id` / root id as separate attributes if needed. Subagent threads differ from their parent under this rule; that is intended.
   - **d. Duplicate notifications.** Consecutive events in one stream with identical `total_token_usage` **and** identical `last_token_usage` are a duplicate notification (39 of 44 same-total events in the corpus). Same total with a *different* `last_token_usage` (the other 5) are real requests with a non-advancing total and must be counted. Equality signal only: never difference or sum `total_token_usage`.
   - **e. Legacy ordinals.** `_backfill_raw_events` uses `INSERT OR IGNORE` on `(source_path, line_no)`, so the new nullable `raw_events.ordinal` is never filled for existing rows, and archived files have moved. Either re-read sources once with an `UPDATE`, or keep legacy rows explicitly unresolved (no key, excluded from verified-deduplicated claims). Pick one and test it.
   - **f. Per-stream state** is keyed by `(thread, stream discriminator)`, never `session_id` alone; rebuild's `ORDER BY id` must not interleave subagent or page streams into one duplicate comparison.
   - **g. Uniqueness and conflicts.** Partial unique indexes for the two key shapes (`channel = 'rollout'` and the key columns non-NULL), created repair-first per the migration convention. A repeated key with conflicting content surfaces a diagnostic, not `INSERT OR IGNORE`. A wrong key forces drop-and-recreate plus a rebuild in every editable-install project, so land the key decision before the migration.
   - **Not verified (advisor dissent):** whether all 15 forks are subagent spawns (14 confirmed); whether `raw_events.session_id` for Codex is `payload.id` in every path (inferred from `session_id_for`); whether 0.155 `exec --json` emits turn ids.
2. **Reset namespace — decided (conservative).** `last_token_usage` is per request, so compaction does not affect per-request rows; only ENH-3543's span-sum consistency check is affected. Record `window_id` on the span if cheap, so ENH-3543 can detect a mid-span window change and downgrade to unresolved.
3. **Ordering — closed.** No cumulative state is needed; `CodexUsageState` holds only the current span `turn_id` and the session ID.

If a case lacks producer evidence, choose the conservative unresolved behavior rather than inventing a match.

## Acceptance Criteria

- [x] Physical line, native ordinal, and token-event sequence remain distinct through trimmed-file/direct/DB replay fixtures; unknown request uniqueness stays explicitly unresolved even in rollout-only reports.
- [x] The shared session/span schema is recorded with ENH-3543 before migrations; existing `session_id`/`invocation_id` columns are reused with explicit identity basis.

- [x] Historical rollout usage reaches `usage_events` (`channel='rollout'`) through `normalize_codex_input` and BUG-3531's rollout container rules; `rollout-exec-resume.jsonl` yields exactly three rows (12424 uncached input / 46080 cache-read / 0 cache-write / 122 output in total; native inclusive input is 58504); live capture continues to work.
- [x] Fixtures cover repeated notifications, per-request vs cumulative values, compaction resets, multiple sessions, malformed/partial records, rate-limit-only records, and observed-model absence. Valid distinct requests with equal counts remain distinct.
- [x] Repeated ingestion and rebuild leave canonical totals stable and preserve live-only rows (relies on BUG-3530).
- [x] This issue verifies full-rebuild materialization; ENH-3651 supplies the shared incremental derive and catch-up. Before ENH-3549's Codex cutover, their combined ingest → incremental derive → read flow is tested end to end, including Codex raw rows ingested before ENH-3651's checkpoint or before this normalizer lands.
- [x] Rollout rows take their host from BUG-3542's verified attribution, never from the currently configured host; legacy-attributed rows carry an unknown host with a reason.
- [x] The same fixture ingested directly and replayed from stored inner payloads produces equivalent observations, including session, event time, outer type, and source position. Existing `_iter_events` consumers remain compatible.
- [x] Source/request keys, fallback rules, reset namespace, host-attribution discriminator, and database uniqueness are documented and fixture-backed before implementation readiness. Tests cover archive/move, copied sources, repeated notifications, conflicting duplicate keys, equal-count distinct requests, and unknown identities.
- [x] Interleaved sessions, out-of-order ingestion, incomplete prefixes, malformed snapshots, and compaction/reset boundaries cannot share normalization state or produce fabricated deltas. Multiple request observations in one turn remain distinct.
- [x] Each rollout row persists the session ID and the `task_started`/`task_complete` span `turn_id` that ENH-3543 matches on.
- [x] Rollout rows with a `session_id` do not change `quality_regressions` model-composition output (channel pin + regression test).
- [x] Rebuild and interrupted/retried replay preserve live-only rows and never leave partially replaced rollout accounting. Source relocation/copy does not change canonical totals for verified identities.
- [x] Partial/malformed and unproven rollout observations remain `unknown`; only producer-verified, consistent complete rows become `measured`. Empty and wrong-type usage containers obey BUG-3531's contract without raising or fabricating zero.

- [x] The persisted key is unique on fork, resume, archive and paginated-thread fixtures: a forked rollout and its parent never collide, and two files sharing a `payload.id` are distinguished by the stream discriminator (fixtures added, including a captured fork).
- [x] With `token_usage_record` present for a proven request, exactly one observation per `response_id` is selected and its overlapping `token_count` is not also counted. A mixed/partial-stream fixture proves that old-shape-only requests are retained with the appropriate qualification. A fixture from a 0.154+ producer records its version.
- [x] Duplicate rule: identical `total_token_usage` + identical `last_token_usage` collapses to one observation; identical total with different `last_token_usage` keeps both (fixtures for each).
- [x] The legacy-ordinal policy (re-read once vs. explicitly unresolved) is recorded and tested; existing rows never silently acquire a fabricated key.
- [x] Rollout rows with a `session_id` change neither `quality_regressions` nor `agent_quality` cost-per-issue output (channel pins + regression tests).

## Scope Boundaries

- **In scope**: Codex rollout normalization/ingestion, metadata-bearing replay, request/reset identity, persisted uniqueness, idempotent transactional replay.
- **Prerequisites** (all done): BUG-3542 (verified source host), ENH-3538, BUG-3531 and BUG-3530.
- **Split out**: BUG-3542 (raw-ingest host correction); ENH-3647 (live identity plumbing); ENH-3543 (shared coverage selector and reader/export selection); ENH-3651 (incremental derive and catch-up).
- **Out of scope**: other-host usage ingestion (ENH-3534); Codex pricing; changing live token normalization beyond BUG-3531; exact Claude overlap reconciliation; ENH-3528's richer rendering contract.

## Implementation Steps

1. Capture a fork fixture and a 0.154+ fixture (`token_usage_record`, a re-emitted notification, a non-advancing total, a subagent, a paginated thread); share join-critical paired captures with ENH-3655. Confirm gate 1's revised rules and record the final migration/index; gates 2–3 are closed.
2. Add metadata-bearing adapters for direct files and database replay (persist the rollout `ordinal` if needed), reading BUG-3542's attribution.
3. Add persisted observation identity/uniqueness; implement transactional, idempotent rollout replay with relocation/copy/interruption regressions.
4. Verify ingestion/rebuild against malformed, partial, mixed-host and legacy fixtures; update schemas/docs and run focused tests plus required project checks.

## Program Design

### Types

- `UsageReplayRecord` — parsed payload plus outer event type, session ID, verified host/attribution basis, event time, source position/basis, and diagnostic source label; no assumption that the payload is an envelope.
- `CodexUsageState` — per-thread/stream key/span bookkeeping (current `task_started` span, request ordinal); no cumulative baseline, since older observations come from `last_token_usage` only (readiness gate 3).
- `UsageObservation` — ENH-3538's nullable token components and provenance plus channel, thread ID, verified source/request identity, turn span and attribution metadata (live invocation correlation is ENH-3647). Extend/wrap `TokenUsage` rather than duplicating its component semantics; do not assume the foundation already supplies these identities.

### Signatures

- `normalize_codex_usage(record: UsageReplayRecord, *, state: CodexUsageState) -> list[UsageObservation]` — proposed interface; zero or one observation plus explicit updates to per-session state. Input splitting and container/component rules delegate to BUG-3531; callers partition/order records using the resolved identity contract.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing; extended to route Codex rollouts through the normalizer.

### Call Path

- direct envelope / stored payload + database columns → `UsageReplayRecord` → per-thread/stream `normalize_codex_usage` → `normalize_codex_input` → `record_usage_event` (idempotent `usage_events` write)
- persisted observations → ENH-3528 conservative reporting (unreconciled sum until ENH-3543)

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `_iter_events` (`writers.py` L3430) yielded `(raw_line, source_label)` only; `_codex_cache_usage` (`ctx_stats.py` L356) was the sole rollout `token_count` reader. The earlier dependency assessment is superseded: BUG-3530 is done, prerequisites are ENH-3538 and BUG-3531, and BUG-3531 has a `blocks` backlink. The prospective implementation gaps below were not resolved by that verification.

### Applied pre-implementation review 2026-09-24

Fixture probes confirmed replay receives an inner `token_count` payload without session/time/ordinal, and a Codex handle ingested under a Claude host replays with the wrong host. Added metadata-bearing replay, source-host qualification, explicit readiness gates for persisted identity and per-session state, live identity plumbing, and shared coverage selection with conservative unresolved behavior. Folded rebuild ownership into Design; the current deletion predicate already covers rollout rows. Expanded ACs for relocation/copy/interruption, partial overlap, and conditional measured provenance. The review's 34 focused existing tests and evidence checks passed, but do not establish the new producer/identity contracts. Specification changes only; readiness gates remain outstanding.

### Pre-implementation review 2026-09-24 (split)

Historical split: BUG-3542 was the remaining prerequisite then; it is now done, as are ENH-3538 and BUG-3531. Imported BUG-3531's resolved decisions into the readiness gates, leaving three open gates (request key, reset namespace, ordering). Moved live identity and coverage selection to ENH-3543, and host correction to BUG-3542.

## Status

**Done** | Created: 2026-09-24 | Priority: P2

---

## Scope Boundary

**Current rule (updated 2026-09-29):** This issue persists the rollout thread ID (`session_meta.payload.id`) in `usage_events.session_id`, plus the `task_started`/`task_complete` span on each rollout row. A fork's `payload.session_id` names its parent and must not replace the thread ID. ENH-3647 owns live identity capture and local invocation correlation; ENH-3543 owns coverage selection. Use existing `session_id` for both channels with verified host/identity basis, and reuse existing `invocation_id` for local correlation. Agree remaining span/basis field names with ENH-3647 before either migration; do not add duplicate identity columns.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 48/100 → LOW

### Concerns
- Prerequisite prose refreshed by the epic review: BUG-3542 is done; identity/readiness decisions below remain outstanding.
- Three readiness gates (request key, reset namespace, ordering) were open at scoring time. 2026-09-28: gates 2 and 3 closed from fixtures; gate 1 has a proposed key and index pending a fork-session check. Re-score after confirming.
- The session-identity column must be agreed with ENH-3543 before either migration lands (see Scope Boundary note).

- 2026-09-29: the score above predates the revised gate 1 (fork/paginated-thread collisions, `token_usage_record`, duplicate rule). Re-score after the fixtures land.

### Outcome Risk Factors
- Moderate-to-deep per-site complexity across ~8 source modules plus an append-only schema migration and transactional replay.
- Unresolved design decisions on observation identity/uniqueness (request key, reset namespace, ordering) leave ambiguity; wide reader/test surface.

## Session Log
- `/ll:manage-issue` - 2026-09-29T08:22:26 - `688ef729-26a9-43d5-8442-56084d826e08.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T01:38:47 - `00481f16-3cf9-4411-85c4-2628bffdfe50.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:33:29 - `8209a6c5-0048-4df0-9c81-a0ae9f75a965.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T01:19:08 - `49a0f922-81ea-47c1-887c-a8f9378dfd2a.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:06:55 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:02:39 - `f35cbaf1-740e-46e5-84c9-0ecf04a645f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T23:55:44 - `2bb94109-d967-427c-a647-9b0a7a8e368e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:29 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`


## Resolution

- **Action**: Implement
- **Completed**: 2026-09-29
- **Status**: Done

### Changes Made

- Versioned Codex rollout captures, replay identity, mixed-shape deduplication and conservative provenance now persist through full and incremental derivation.

### Verification Results

- Full local suite: 27,525 passed, 301 skipped.
- Ruff lint and format, host-map verifier and private-reference verifier: passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency; a run with the project config and Python 3.12 target reports existing `no-any-return` and `unused-ignore` errors across the package.

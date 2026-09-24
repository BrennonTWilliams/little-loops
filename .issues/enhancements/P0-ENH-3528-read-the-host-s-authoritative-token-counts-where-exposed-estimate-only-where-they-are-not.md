---
id: ENH-3528
title: Read the host's authoritative token counts where exposed; estimate only where they are not
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- observability
- multi-host
---

# Read the host's authoritative token counts where exposed; estimate only where they are not

## Summary

Make token provenance explicit per observation and metric. Host capabilities describe which telemetry a host can expose; they cannot determine whether every figure from that host is measured. Deliver labeling/provenance first, then add Codex historical rollout usage ingestion with defined normalization, deduplication, and rebuild behavior. Preserve useful context estimates where no measurement of the same quantity and interval is available.

## Current Behavior

- `ll-ctx-stats` fallback text already says `Estimated tokens in context`, and fallback JSON uses `estimated_tokens`. The gap is consistent provenance across token figures, context pressure, aggregates, and exports.
- `_print_json` already has a top-level `source` with values `sqlite | fallback | none`, describing the store. This meaning must not change.
- `usage_events` stores live per-invocation usage and historical assistant `message.usage` records. It has no observation provenance or host column, and its live writer uses plain INSERT without a uniqueness constraint.
- Codex live `turn.completed` usage already reaches `usage_from_event` → runner `ActionResult.usage_events` → `FSMExecutor._finish` → `record_usage_event` when capture is enabled. The missing path is historical rollout `event_msg/token_count` ingestion into `usage_events`; `_codex_cache_usage` already reads those events for cache-rate reporting.
- Codex input counts include cached/cache-write tokens; the Claude-shaped usage columns and pricing calculation treat those components separately. `_codex_cache_usage` subtracts cache components, but `usage_from_event` currently forwards Codex input unchanged. Source labels alone do not correct this semantic mismatch.
- `context-monitor.sh` combines measured baselines with estimates and adds heuristic overhead even after the `result_token_count` branch. The stored `estimated_tokens` is not automatically a measured context-occupancy value when a host reports usage.
- `RUNTIME_HOST_CAPABILITIES` describes runtime operations for eight hosts; the six-host adapter map describes artifact emission. Runtime `token_reporting` is currently an advisory report row, not per-observation provenance.
- Schema version is 52 at review time. SessionStart requests a rebuild after a version advance; `rebuild()` deletes `usage_events` before replaying raw transcripts. Live-only rows and their state detail cannot be assumed reconstructible.

## Expected Behavior

Each rendered token figure is traceable to its metric, scope, observation source, and provenance. Available host-reported usage is normalized and preferred over estimates of the same quantity and interval. Missing telemetry is unavailable, not zero. Context estimates remain estimates until an applicable context measurement replaces them. Mixed-host and mixed-source history is labeled from stored observations, never from the host currently running the report.

## Design

### Capability and provenance are separate

Add typed telemetry availability to the runtime host map, distinguished by metric and acquisition channel (for example, live invocation usage versus rollout usage). Include explicit supported/unsupported/unknown entries for runtime hosts and derive or check the existing `token_reporting` report against them. Do not add `HostCapabilityEntry.token_source` to the build-time adapter map or infer provenance with `token_source_for(host)`.

Record provenance at the observation boundary:

- `measured`: a host-reported count for the identified quantity and interval, including exact normalization of its cache components.
- `estimated`: any heuristic contribution, including a measured baseline plus estimated tool/turn overhead.
- `unknown`: a value exists but its provenance cannot be established, including unverifiable legacy rows.
- `mixed`: aggregate-only metadata when known measured and estimated observations contribute. Keep component totals/counts so the composition is visible. Unknown contributions make aggregate provenance unknown while preserving the known breakdown.

Unavailable is a value/availability state, not an estimate: use `null` with an explanation in provenance metadata for absent fields. Do not infer zero from missing keys unless the specific host/event contract and a fixture establish that omission means zero. Preserve trustworthy legacy classifications only when the original acquisition path can be demonstrated, not guessed from model names or the currently configured host.

### Metrics, scope, and freshness

Keep these quantities distinct: per-request/per-invocation consumption, cumulative session consumption, and current context occupancy. Identify session/invocation scope and observation time wherever known. Store the acquisition channel separately from the measured/estimated classification.

Replace an estimate only with an applicable measurement of the same metric, scope, and interval. Never use cumulative usage as current context occupancy or add a cumulative total to its constituent request counts. A context sample becomes stale when relevant context changes or compaction occurs; expose its observation boundary/staleness rather than presenting it as current. Between measurements, an existing supported estimator may continue with `estimated` provenance. Without either a valid measurement or estimator, report unavailable.

Retain the context estimator for its existing use cases. Remove redundant estimation only within a path where equivalent authoritative data is actually supplied. No estimator-wide deletion or new cross-host context monitor is required.

### Delivery A: labeling and observation provenance

Make the labeling slice independently useful before new Codex ingestion. Audit `ll-ctx-stats` usage totals/by-model, cache token figures and ratios, fallback total/breakdown, waste token totals, and context-pressure derivations. A measured numerator does not make a heuristic derived figure measured. Do not broaden this issue into time-saved or other non-token metrics.

Keep existing numeric field locations and the top-level `source`. Add a `token_provenance` mapping keyed by stable metric paths, including nested figures (for example `usage_by_model.totals.input_tokens`). Each entry identifies provenance, metric/scope, channel and observation time where known, availability/completeness, and aggregate composition where relevant. A deterministic path convention for dynamic per-model/per-tool keys must be documented and tested. Use the same semantic metadata for text labels and exports; do not wrap existing numbers in new objects.

Preserve JSON compatibility where existing values remain valid. Correctly changing an absent measurement previously coerced to zero into `null` is an intentional semantic correction: document the affected fields and update consumer tests. Partial aggregates retain their numeric subtotal but identify missing contributors; all-missing measurements return `null`, never a misleading measured zero.

Persist provenance and source identity alongside affected usage observations, and retain estimated provenance for existing context-state/pressure data. Keep requested/resolved model selections separate from observed model identity, following ENH-3527's contract. An unknown observed model remains unknown; it must not become a hint, assumed model ID, or zero-cost claim. Neither issue requires the other's implementation to land first.

### Delivery B: Codex historical usage ingestion

Codex is the selected first host. Add rollout usage ingestion while preserving its existing live capture; Qwen/Gemini/OMP and other new ingestion paths are deferred.

Normalize native events into a documented canonical contract shared by live and historical consumers:

- Input columns represent uncached input plus separate cache-read/cache-write components. For Codex, derive uncached input from inclusive input and validated cache components. Partial/inconsistent components must remain identifiable rather than inventing a measured split.
- Output totals must not add reasoning tokens again when they are already included; establish this with fixtures.
- Identify per-request counts separately from cumulative snapshots. Repeated notifications must not duplicate usage; compaction/reset boundaries must not produce negative deltas or cross-session attribution. Do not blindly sum either `total_token_usage` or every repeated `last_token_usage` snapshot.
- Carry host, session, acquisition channel, observation scope/time, and a stable source identity where available. Missing usage or rate-limit-only events do not create zero-usage rows.
- Use fixture-backed event identity and accounting rules. Document which keys establish request identity and reset boundaries. If live invocation totals cannot be matched to finer-grained transcript requests, preserve both sources but select one coverage basis per scope in aggregates; do not sum overlapping coverage or deduplicate merely by equal token values.

### Storage, replay, and exports

Choose the persisted representation and coverage reconciliation before adding ingestion. Add nullable/default-compatible columns using append-only migrations; use the next available schema version rather than assuming 53 remains free. Legacy values with unproven provenance remain unknown.

A migration-triggered rebuild must preserve live-only usage, state/run associations, and source metadata. Rebuild only replaceable transcript-derived coverage, or reconcile replay against durable source identities before replacing records. Repeated ingestion/rebuild must leave canonical totals stable. When overlap cannot be proved, expose uncertain coverage or exclude overlapping sources from the combined total; never silently double-count or discard unmatched live observations.

The shareable export must retain non-sensitive provenance needed to interpret its token figures. Add safe provenance columns to `_SHAREABLE_COLUMNS`, update the allowlist version/hash and fixtures together, and omit private transcript paths/raw source identifiers. Derived export metadata must explain any redacted acquisition identity. Carry provenance through `UsageEvent`, history readers, and dashboard token exports affected by the new columns.

## Acceptance Criteria

- [ ] Runtime telemetry capabilities describe availability by metric/channel, cover the runtime registry, and agree with `token_reporting`; provenance is not selected from the current host or build-time adapter map.
- [ ] Text and JSON label all token/derived-context figures in `ll-ctx-stats`, including fallback breakdown, usage-by-model, cache, waste, and pressure. Existing top-level `source` and numeric field locations remain intact; additive `token_provenance` paths are documented/tested.
- [ ] Tests cover measured, estimated, unknown, mixed, unavailable, partial, and legacy data; a missing field is not a measured zero. Aggregation preserves source composition across multiple hosts.
- [ ] Context estimates are replaced only by equivalent in-scope measurements; measured baselines plus overhead remain estimated. Tests cover missing/stale measurements, tool activity between observations, and compaction invalidation without removing existing fallback estimation.
- [ ] Codex live capture continues to work, and historical rollout usage reaches `usage_events` through a fixture-backed normalizer. Input/cache components and reasoning/output inclusion have a single documented meaning across both paths and downstream pricing.
- [ ] Fixtures cover repeated notifications, per-request versus cumulative values, compaction resets, multiple sessions, malformed/partial records, rate-limit-only records, and observed-model absence. Valid distinct requests with equal counts remain distinct.
- [ ] Live/historical overlap has a documented identity/coverage policy. Repeated ingestion and rebuild preserve canonical totals without double-counting overlapping invocation/request coverage.
- [ ] Migration and SessionStart-triggered rebuild tests preserve live-only rows, run/state associations, and provenance; old schemas and unknown legacy origins remain readable. Manifest/version pins are updated together.
- [ ] History readers and shareable dashboard exports retain safe provenance, with allowlist version/hash and fixture updates; no private source paths are added to exports.
- [ ] Requested/resolved model identity is never presented as host-observed identity; unavailable pricing is not reported as measured zero cost. Semantic JSON corrections and the new provenance contract are documented.
- [ ] Labeling/provenance can ship before the new Codex ingestion path, with independent validation for each delivery.

## Scope Boundaries

- **In scope**: runtime telemetry availability, per-observation provenance, `ll-ctx-stats` labeling/export contract, Codex live/historical normalization and historical ingestion, overlap reconciliation, migration/rebuild safety, and affected history/dashboard exports.
- **Out of scope**: improving estimator accuracy; deleting the context estimator globally; using consumption as occupancy; adding ingestion for Qwen or other hosts; new context monitors; changing time-saved/non-token metrics; new model pricing/routing; a universal provenance rewrite of unrelated CLIs.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py`, `cli/verify_host_map.py`, `cli/doctor.py` — typed runtime telemetry and report consistency. `adapters/capabilities.py` stays a build-time emission map.
- `scripts/little_loops/subprocess_utils.py`, `fsm/runners.py`, `fsm/executor.py` — live normalization, `TokenUsage` compatibility, acquisition identity, observed-model handling, and persisted usage metadata.
- `scripts/little_loops/session_store/{codex,sessions,writers}.py` — native rollout normalization, stable source/coverage identity, legacy raw-event replay, and provenance-aware writes. `_iter_events` currently yields line/source labels and drops the cursor's host except for Qwen replay; preserve necessary host identity deliberately.
- `scripts/little_loops/session_store/{schema,lifecycle,queries}.py`, `schema_manifest.json` — append-only migrations, safe rebuild, canonical coverage, shareable columns/version.
- `scripts/little_loops/cli/ctx_stats.py` — aggregators, `_codex_cache_usage`, `_render_fallback`, `_print_json`, and provenance rendering for both store and fallback branches.
- `scripts/little_loops/history_reader/{models,usage,context}.py`, `cli/artifact/dashboard.py` and its `dashboard.llat` template — provenance/completeness through readers and export.
- `hooks/scripts/context-monitor.sh`, `context-handoff-sentinel.sh`, `scripts/little_loops/loops/context-health-monitor.yaml` — estimated/stale labels and observation-boundary metadata where needed; preserve existing threshold behavior.

### Dependent Files and Similar Patterns

- `scripts/little_loops/hooks/session_start.py` — version-triggered `--rebuild`; test this path, not only explicit manual rebuild.
- `pricing.py`, `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `init/core.py` — audit assumptions about token components, null values, coverage, and new columns; update affected consumers without expanding to unrelated metrics.
- `test_cli_ctx_stats.py::TestCacheHitRateInOutput` is an additive-output precedent, but old byte-identical rendering expectations may need explicit updates when estimate/provenance labels change.
- Existing `record_usage_event`/`_backfill_usage_events` illustrate two acquisition grains, not a deduplication solution. `lifecycle._REBUILD_TABLES` currently includes usage, so preserving live-only rows requires actual rebuild changes.

### Tests

- `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, context reader tests — mixed/unknown/partial data, unchanged store `source`, numeric locations, provenance paths, host-independent aggregation, and null-versus-zero behavior.
- `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py` — existing Codex live capture, canonical input/cache semantics, source identity, unknown observed models, and backward-compatible callbacks.
- `test_session_store_writers.py`, `test_session_store_lifecycle.py`, Codex parser tests, `fixtures/codex/rollout-interactive.jsonl` — native ingestion, duplicate/repeated snapshots, reset boundaries, overlapping source grains, repeat replay, and live-only preservation.
- `test_session_store_schema.py`, `test_assistant_messages.py` — migration, manifest, old-schema behavior and version pins. Add a SessionStart/backfill-worker regression covering automatic rebuild with live-only usage.
- `test_feat3304_artifact_dashboard.py` — allowlist version/hash, fixture DDL, safe provenance export, and missing/partial totals.
- `test_hooks_integration.py` — context estimates after measured baselines, freshness, compaction, labels, and unchanged threshold behavior.
- `test_host_runner.py`, `test_verify_host_map.py`, `test_cli_doctor.py`, `test_history_store_chokepoint_gate.py` — runtime telemetry parity and history-read boundaries.

### Documentation

Update `docs/reference/{CLI,API,HOST_COMPATIBILITY,CONFIGURATION}.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md`, and relevant context-monitor examples in `BUILTIN_HOOKS_GUIDE.md`, `SESSION_HANDOFF.md`, and `docs/development/TROUBLESHOOTING.md`. Document canonical count meanings, partial/mixed/unknown provenance, JSON compatibility corrections, shareable fields, and replay guarantees. Check `docs/observability/{otel-mapping,realized-savings-verification}.md` and `docs/codex/usage.md` for affected token semantics. Do not assume the JSON contract documentation is unaffected before checking its stated coverage.

## Implementation Steps

1. Establish fixture-backed metric/scope and live-versus-historical accounting contracts. Correct the Codex live-ingestion premise and characterize existing counts before changing normalization.
2. Implement typed runtime telemetry availability and per-observation metadata. Plan source identity, live-row preservation, and export-safe columns together; append the migration only with safe rebuild behavior covered by tests.
3. Ship Delivery A: persist available provenance, conservatively classify legacy values, render labels and additive `token_provenance`, preserve store `source`, and document any null/completeness corrections. No new Codex historical ingestion is required for this slice.
4. Implement Delivery B: normalize Codex live and historical usage to the canonical cache/input/output contract; ingest rollouts with explicit request/snapshot/reset identity and coverage reconciliation.
5. Exercise migration-triggered rebuild, repeat replay, live-only records, overlapping sources, and mixed-host history. Update manifest/version pins and shareable allowlist/hash/fixtures in the same change as the schema/export contract.
6. Update affected readers, exports, context examples, and docs. Run focused parser/writer/rebuild/render tests, then the required local suite and applicable lint/type checks.

## Program Design

### Types and Contracts

- `TokenProvenance = Literal["measured", "estimated", "unknown"]` for observations; aggregate metadata also permits `mixed` and includes source composition/completeness.
- A frozen runtime telemetry capability describes availability for a metric/channel. It is not a token value's provenance.
- A normalized observation carries nullable token components, host/channel, metric/scope, observation time, available source identity, provenance, and observed model separately from requested/resolved selection. Choose its concrete representation with the existing `TokenUsage` compatibility requirements in view.
- Persisted usage metadata and coverage identity support idempotent ingestion and selective/reconciled rebuild. Legacy rows need an explicit unknown-origin policy rather than a measured default.

### Signatures and Data Flow

- `normalize_codex_usage(...)` returns normalized observations with scope/identity or no observation for events without usage. Live and historical adapters share count semantics without equating invocation totals with per-request rows.
- `record_usage_event(...)` accepts additive metadata while retaining existing callers; `_backfill_usage_events(...)` uses equivalent semantics and the same coverage rules.
- `_aggregate_usage_events(db_path)` aggregates canonical non-overlapping coverage and returns provenance/completeness alongside existing numeric fields; it does not consult the currently configured host to classify historical values.
- `_render_fallback` and `_print_json` render the same provenance contract, preserving the top-level store `source`.

`host event / estimator → normalize quantity and scope → attach provenance and source identity → persist/reconcile coverage → aggregate values and provenance → text / JSON / safe export`.

## Impact

- **Priority**: P0 (retained from issue triage).
- **Effort**: Medium to high — labeling is separable, but normalization, source overlap, and rebuild safety are substantive storage work.
- **Risk**: Medium to high — incorrect grain/cache normalization can double-count tokens, and migration-triggered replay can lose live-only data.
- **Breaking Change**: Additive provenance metadata and unchanged store `source`; intentional missing-value/token-semantic corrections must be documented and covered by consumer tests.

## Verification Notes

Review corrections applied on 2026-09-23: separated runtime capability from observed provenance; retained metric-appropriate estimation; corrected Codex live capture and selected its historical ingestion; specified normalization, unavailable/mixed values, model identity, safe export, overlap, and migration/replay guarantees. Reconciled research and wiring into the directive sections. The review's 30 focused existing tests passed; evidence checks returned no findings. New acceptance criteria remain implementation work.

## Status

**Open** | Created: 2026-09-23 | Priority: P0

## Session Log
- `/ll:verify-issues` - 2026-09-24T00:01:43 - `d1e0cad9-5218-4c39-a990-a91f5f18af0d.jsonl`
- `/ll:wire-issue` - 2026-09-23T23:43:26 - `96fe3651-90ba-4862-a958-697a2df577cc.jsonl`
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:59:16 - `f909c28b-1081-4c2f-b215-fc2794a9d5b6.jsonl`

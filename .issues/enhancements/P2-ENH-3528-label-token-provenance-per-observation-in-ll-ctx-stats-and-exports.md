---
id: ENH-3528
title: Label token provenance per observation in ll-ctx-stats and exports
type: ENH
priority: P2
status: open
discovered_date: '2026-09-23'
blocked_by:
- BUG-3530
labels:
- observability
- multi-host
---

# Label token provenance per observation in ll-ctx-stats and exports

## Summary

Make token provenance explicit per observation and metric. Host capabilities describe which telemetry a host can expose; they cannot determine whether every figure from that host is measured. This issue is the labeling/provenance slice (formerly "Delivery A"): runtime telemetry availability, per-observation provenance persisted with usage rows, and a provenance contract rendered by `ll-ctx-stats` and carried through history readers and shareable exports. New Codex historical rollout ingestion is split out to ENH-3532; other hosts to ENH-3534. Preserve useful context estimates where no measurement of the same quantity and interval is available.

## Current Behavior

- `ll-ctx-stats` fallback text already says `Estimated tokens in context`, and fallback JSON uses `estimated_tokens`. The gap is consistent provenance across token figures, context pressure, aggregates, and exports.
- `_print_json` already has a top-level `source` with values `sqlite | fallback | none`, describing the store. This meaning must not change.
- `usage_events` stores live per-invocation usage and historical assistant `message.usage` records. It has no observation provenance or host column, and its live writer uses plain INSERT without a uniqueness constraint.
- Codex live `turn.completed` usage already reaches `usage_events` (`usage_from_event` → runner `ActionResult.usage_events` → `FSMExecutor._finish` → `record_usage_event`) but stores cache-inclusive input in the uncached-input column — tracked separately as BUG-3531.
- `context-monitor.sh` combines measured baselines with estimates and adds heuristic overhead even after the `result_token_count` branch. The stored `estimated_tokens` is not automatically a measured context-occupancy value when a host reports usage.
- `RUNTIME_HOST_CAPABILITIES` describes runtime operations for eight hosts; the six-host adapter map describes artifact emission. Runtime `token_reporting` is currently an advisory report row in `ll-doctor`, not per-observation provenance.
- Schema version is 52 at review time. SessionStart requests a rebuild after a version advance, and `rebuild()` currently deletes all `usage_events` rows including live-only ones — BUG-3530, which this issue is blocked by because its own migration would trigger that loss.

## Expected Behavior

Each rendered token figure is traceable to its metric, scope, observation source, and provenance. Missing telemetry is unavailable, not zero. Context estimates remain estimates until an applicable context measurement replaces them. Mixed-host and mixed-source history is labeled from stored observations, never from the host currently running the report.

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

### Labeling and the `token_provenance` contract

Audit `ll-ctx-stats` usage totals/by-model, cache token figures and ratios, fallback total/breakdown, waste token totals, and context-pressure derivations. A measured numerator does not make a heuristic derived figure measured. Do not broaden this issue into time-saved or other non-token metrics.

Keep existing numeric field locations and the top-level `source`. Add a top-level `token_provenance` object whose keys are **RFC 6901 JSON Pointers** to the numeric field they describe, relative to the JSON document root (e.g. `/usage_by_model/totals/input_tokens`). Dynamic keys such as model IDs and tool names are embedded verbatim with standard JSON Pointer escaping (`~` → `~0`, `/` → `~1`); dots need no escaping, so model IDs like `claude-haiku-4.5` stay unambiguous. Each value identifies provenance, metric/scope, channel and observation time where known, availability/completeness, and aggregate composition where relevant. Text rendering uses the same semantic metadata. Do not wrap existing numbers in new objects.

Preserve JSON compatibility where existing values remain valid. Correctly changing an absent measurement previously coerced to zero into `null` is an intentional semantic correction: document the affected fields and update consumer tests. Partial aggregates retain their numeric subtotal but identify missing contributors; all-missing measurements return `null`, never a misleading measured zero.

### Storage, exports, and model identity

Persist provenance, host, and acquisition channel alongside usage observations with nullable/default-compatible columns in an append-only migration at the next free schema version (do not assume 53). This migration requires BUG-3530's rebuild fix to have landed. Legacy rows with unproven provenance remain `unknown`. Existing context-state/pressure data retains `estimated` provenance.

The shareable export must retain non-sensitive provenance needed to interpret its token figures. Add safe provenance columns to `_SHAREABLE_COLUMNS`, bump `_SHAREABLE_ALLOWLIST_VERSION` and update the hash and fixtures together, and omit private transcript paths/raw source identifiers. Carry provenance through `UsageEvent`, history readers, and dashboard token exports affected by the new columns.

Keep requested/resolved model selections separate from observed model identity, following ENH-3527's contract. An unknown observed model remains unknown; it must not become a hint, assumed model ID, or zero-cost claim. Neither issue requires the other to land first.

## Acceptance Criteria

- [ ] Runtime telemetry capabilities describe availability by metric/channel, cover the runtime registry, and agree with `token_reporting`; provenance is not selected from the current host or build-time adapter map.
- [ ] Text and JSON label all token/derived-context figures in `ll-ctx-stats`, including fallback breakdown, usage-by-model, cache, waste, and pressure. Existing top-level `source` and numeric field locations remain intact.
- [ ] `token_provenance` keys are RFC 6901 JSON Pointers; tests cover escaping of `~` and `/` in dynamic model/tool keys, dotted model IDs, and that every pointer resolves to an existing numeric (or `null`) field in the same document.
- [ ] Tests cover measured, estimated, unknown, mixed, unavailable, partial, and legacy data; a missing field is not a measured zero. Aggregation preserves source composition across multiple hosts.
- [ ] Context estimates are replaced only by equivalent in-scope measurements; measured baselines plus overhead remain estimated. Tests cover missing/stale measurements, tool activity between observations, and compaction invalidation without removing existing fallback estimation.
- [ ] Migration adds provenance/host/channel columns; migration-triggered SessionStart rebuild preserves live-only rows and their provenance (with BUG-3530 landed); old schemas and unknown legacy origins remain readable. Manifest/version pins updated together.
- [ ] History readers and shareable dashboard exports retain safe provenance, with allowlist version/hash and fixture updates; no private source paths are added to exports.
- [ ] Requested/resolved model identity is never presented as host-observed identity; unavailable pricing is not reported as measured zero cost. Semantic JSON corrections and the provenance contract are documented.
- [ ] No new ingestion path is added; Codex historical ingestion is ENH-3532.

## Scope Boundaries

- **In scope**: runtime telemetry availability, per-observation provenance columns, `ll-ctx-stats` labeling and `token_provenance` contract, context estimate/staleness labeling, and affected history/dashboard exports.
- **Prerequisite**: BUG-3530 (rebuild must preserve live-only usage rows before this migration ships).
- **Split out**: ENH-3532 (Codex historical rollout ingestion, overlap reconciliation); BUG-3531 (Codex live input normalization); ENH-3534 (Qwen/Gemini/OMP and other hosts).
- **Out of scope**: improving estimator accuracy; deleting the context estimator globally; using consumption as occupancy; new context monitors; changing time-saved/non-token metrics; new model pricing/routing; a universal provenance rewrite of unrelated CLIs.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py`, `cli/verify_host_map.py`, `cli/doctor.py` — typed runtime telemetry and report consistency. `adapters/capabilities.py` stays a build-time emission map.
- `scripts/little_loops/subprocess_utils.py`, `fsm/runners.py`, `fsm/executor.py` — attach provenance/channel/host to live observations; `TokenUsage` compatibility; observed-model handling.
- `scripts/little_loops/session_store/{schema,writers,queries}.py`, `schema_manifest.json` — append-only migration, provenance-aware `record_usage_event`/`_backfill_usage_events`, shareable columns/version.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_codex_cache_usage`, `_render_fallback`, `_print_json`, and provenance rendering for both store and fallback branches.
- `scripts/little_loops/history_reader/{models,usage,context}.py`, `cli/artifact/dashboard.py` and its `dashboard.llat` template — provenance/completeness through readers and export.
- `hooks/scripts/context-monitor.sh`, `context-handoff-sentinel.sh`, `scripts/little_loops/loops/context-health-monitor.yaml` — estimated/stale labels and observation-boundary metadata where needed; preserve existing threshold behavior.

### Dependent Files and Similar Patterns

- `scripts/little_loops/hooks/session_start.py` — version-triggered `--rebuild`; test this path, not only explicit manual rebuild.
- `pricing.py`, `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `init/core.py` — audit assumptions about null values and new columns; update affected consumers without expanding to unrelated metrics.
- `test_cli_ctx_stats.py::TestCacheHitRateInOutput` is an additive-output precedent, but old byte-identical rendering expectations may need explicit updates when estimate/provenance labels change.

### Tests

- `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, context reader tests — mixed/unknown/partial data, unchanged store `source`, numeric locations, JSON Pointer paths, host-independent aggregation, and null-versus-zero behavior.
- `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py` — provenance on live observations, unknown observed models, backward-compatible callbacks.
- `test_session_store_schema.py`, `test_session_store_writers.py`, `test_assistant_messages.py` — migration, manifest, old-schema behavior and version pins; SessionStart-triggered rebuild with live-only rows.
- `test_feat3304_artifact_dashboard.py` — allowlist version/hash, fixture DDL, safe provenance export, and missing/partial totals.
- `test_hooks_integration.py` — context estimates after measured baselines, freshness, compaction, labels, and unchanged threshold behavior.
- `test_host_runner.py`, `test_verify_host_map.py`, `test_cli_doctor.py`, `test_history_store_chokepoint_gate.py` — runtime telemetry parity and history-read boundaries.

### Documentation

Update `docs/reference/{CLI,API,HOST_COMPATIBILITY,CONFIGURATION}.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md`, and relevant context-monitor examples in `BUILTIN_HOOKS_GUIDE.md`, `SESSION_HANDOFF.md`, and `docs/development/TROUBLESHOOTING.md`. Document the JSON Pointer convention, partial/mixed/unknown provenance, JSON compatibility corrections, and shareable fields. Check `docs/observability/{otel-mapping,realized-savings-verification}.md` for affected token semantics.

## Implementation Steps

1. Characterize existing `ll-ctx-stats` text/JSON output and usage rows with fixtures before changing anything.
2. Implement typed runtime telemetry availability and the check against `token_reporting`.
3. Add the provenance/host/channel migration (after BUG-3530) and provenance-aware writers; classify legacy rows `unknown`.
4. Implement aggregation composition and the `token_provenance` JSON Pointer contract; render labels in text and JSON for store and fallback branches; document null/completeness corrections.
5. Label context estimates and staleness in hooks without changing thresholds.
6. Carry provenance through history readers and the shareable export (allowlist version/hash/fixtures together). Update docs. Run focused tests, then the required local suite and applicable lint/type checks.

## Program Design

### Types

- `TokenProvenance = Literal["measured", "estimated", "unknown"]` for observations; aggregate metadata also permits `mixed` and includes source composition/completeness.
- `provenance: str | None` — new nullable `usage_events` column; legacy rows read as `unknown`.
- `channel: str | None` — new nullable `usage_events` column (e.g. `live`, `transcript`, `rollout`).
- A frozen runtime telemetry capability describes availability for a metric/channel. It is not a token value's provenance.
- A persisted observation carries nullable token components, host/channel, metric/scope, observation time, provenance, and observed model separately from requested/resolved selection.

### Signatures

- `record_usage_event(db_path: Path | str, *, run_id: str, ts: str, state: str | None, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int, cache_creation_tokens: int, provenance: str = "measured", host: str | None = None, channel: str | None = None) -> None` — additive keyword-only metadata; existing callers unchanged.
- `_aggregate_usage_events(db_path: Path) -> dict[str, Any] | None` — unchanged signature; the result gains provenance/completeness beside existing numeric fields and never consults the currently configured host.
- `_print_json(...)` and `_render_fallback(state: dict[str, Any], logger: Logger) -> None` — render the same provenance contract, preserving the top-level store `source`.

### Call Path

- `usage_from_event` → `record_usage_event` → `_aggregate_usage_events` → `_print_json`
- `_backfill_usage_events` → `_aggregate_usage_events` → `_render_fallback`

Host event or estimator → attach provenance, host, channel → persist → aggregate values and composition → text / JSON (`token_provenance`) / safe export.

## Impact

- **Priority**: P2 — accuracy/observability enhancement; no current breakage beyond the bugs split out.
- **Effort**: Medium — one migration, a rendering contract, and export plumbing.
- **Risk**: Medium — output-contract changes affect JSON consumers; mitigated by keeping numeric locations and top-level `source`.
- **Breaking Change**: Additive provenance metadata and unchanged store `source`; intentional missing-value corrections must be documented and covered by consumer tests.

## Verification Notes

Review corrections applied on 2026-09-23: separated runtime capability from observed provenance; retained metric-appropriate estimation; specified unavailable/mixed values, model identity, and safe export. Reconciled research and wiring into the directive sections. The review's 30 focused existing tests passed; evidence checks returned no findings.

Review follow-up on 2026-09-23: reprioritized P0 → P2; narrowed to the labeling/provenance slice (former Delivery A) and renamed the file; split Codex historical ingestion to ENH-3532, Codex live input normalization to BUG-3531, other hosts to ENH-3534; made BUG-3530 (rebuild wipes live-only `usage_events`, confirmed in `lifecycle._REBUILD_TABLES`) a blocking prerequisite; fixed the `token_provenance` path convention as RFC 6901 JSON Pointers.

### Verify pass 2026-09-24

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `SCHEMA_VERSION = 52`; `usage_events` is in `lifecycle._REBUILD_TABLES` (BUG-3530 premise holds); `record_usage_event` uses plain `INSERT` with no uniqueness constraint; `token_reporting` is advisory in `doctor.py` (`_ADVISORY_CAPABILITIES`) and `host_runner.py` L648; `_SHAREABLE_ALLOWLIST_VERSION`/`_SHAREABLE_COLUMNS` exist. Dependency note: BUG-3530 is open and has no `blocks:` backlink to ENH-3528 (advisory).

## Status

**Open** | Created: 2026-09-23 | Priority: P2

## Session Log
- `/ll:verify-issues` - 2026-09-24T00:46:08 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:01:43 - `d1e0cad9-5218-4c39-a990-a91f5f18af0d.jsonl`
- `/ll:wire-issue` - 2026-09-23T23:43:26 - `96fe3651-90ba-4862-a958-697a2df577cc.jsonl`
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:59:16 - `f909c28b-1081-4c2f-b215-fc2794a9d5b6.jsonl`

---
id: ENH-3538
type: ENH
title: 'Token observation foundation: nullable usage components and per-observation
  provenance storage'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-23'
captured_at: '2026-09-24T02:48:36Z'
labels:
- observability
- multi-host
blocks:
- BUG-3531
- ENH-3528
- ENH-3532
---

# ENH-3538: Token observation foundation: nullable usage components and per-observation provenance storage

## Summary

Foundation slice extracted from ENH-3528: nullable token observations, per-observation provenance/host/scope/observation-time storage, unknown-default writers, and host-preserving replay. Lands independently, before BUG-3531 (Codex live input normalization) and before ENH-3528's reporting/export/staleness work. Adds no labels to `ll-ctx-stats` output and no new ingestion path.

## Current Behavior

- `TokenUsage` components are `int`; `usage_from_event` coerces missing components to zero, and executor sums and `estimate_cost_usd` assume integers.
- `record_usage_event` (`session_store/writers.py`) takes integer components and writes `ts, model, state, input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens, cost_usd, run_id, channel`. It stores no provenance, host, scope, or observation time, and leaves the existing `invocation_id` / `provider_vendor` columns (v21) NULL.
- `FSMExecutor._finish` assigns one loop-finish timestamp to every collected usage row; that is not their observation time.
- `_iter_events` reads `raw_events.host` but yields only `(raw_line, source_label)`, so `_backfill_usage_events` loses host metadata.
- `SCHEMA_VERSION = 53` (BUG-3530 added `usage_events.channel`; rebuild preserves `channel='live'` rows).

## Expected Behavior

Every usage observation can carry missing components as `None`, a provenance classification that defaults to `unknown`, the runtime host that produced it, its scope kind, and its observation time with an explicit basis. Existing callers and readers keep working unchanged, and no row is certified `measured` by this issue.

## Motivation

BUG-3531 cannot land its Codex normalization safely without a way to tell corrected rows from uncorrected ones, and ENH-3528's reporting cannot label figures it cannot trace. Splitting this storage/writer layer out lets the correctness fix proceed without waiting on the full reporting feature.

## Proposed Solution

See **Design** below.

## Integration Map

### Files to Modify

- `scripts/little_loops/subprocess_utils.py` — `TokenUsage`, `usage_from_event`, callbacks.
- `scripts/little_loops/fsm/runners.py`, `fsm/executor.py` — attach host/observation time at collection; completeness-aware payload sums; `_finish` persistence.
- `scripts/little_loops/session_store/{schema,writers,queries}.py`, `schema_manifest.json` — migration, writer, metadata-aware iterator, `_backfill_usage_events`.
- `scripts/little_loops/pricing.py` — `None`-aware cost.

### Dependent Files and Similar Patterns

- `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `cli/ctx_stats.py`, `hooks/session_start.py` — `None` audit / rebuild path.

### Tests

- `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_session_store_schema.py`, `test_session_store_writers.py`, `test_assistant_messages.py`, `test_pricing.py`.

### Documentation

- `docs/reference/API.md` (`TokenUsage`, `record_usage_event`), `docs/ARCHITECTURE.md` (usage_events columns).

## Program Design

### Types

- `TokenProvenance = Literal["measured", "estimated", "unknown"]`.
- `TokenUsage` — components `int | None`; adds `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis`.
- `scope_kind` values: `request | invocation | session | context | unknown`; `observed_at_basis`: `event | received | None`.

### Signatures

- `record_usage_event(db_path: Path | str, *, run_id: str, ts: str, state: str | None, model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None, cache_creation_tokens: int | None, provenance: TokenProvenance = "unknown", host: str | None = None, provider_vendor: str | None = None, scope_kind: str = "unknown", observed_at: str | None = None, observed_at_basis: str | None = None, invocation_id: str | None = None) -> None` — additive keyword-only metadata; `run_id` keeps its current column; `channel` stays `'live'`.
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False) -> float | None` — already returns `None` for unpriced models; now also `None` when a required component is `None`.

### Call Path

- `usage_from_event` → runner detailed callback → `FSMExecutor` collection → `FSMExecutor._finish` → `record_usage_event`
- raw event + host → metadata-aware iterator → `_backfill_usage_events`

## Implementation Steps

1. Characterize current rows and executor payloads; add partial-event, host/observation-time retention and legacy-compatibility fixtures (failing first).
2. Make `TokenUsage` components nullable with default-compatible metadata; update `usage_from_event`, both callbacks, executor sums and `estimate_cost_usd`; audit listed consumers for `None`.
3. Add the migration, manifest/version pins, the extended `record_usage_event`, and host/vendor/observation-time attachment at collection.
4. Add the metadata-aware iterator and switch `_backfill_usage_events`; test SessionStart-triggered rebuild with live-only rows.
5. Update API/ARCHITECTURE docs; run focused tests, then `python -m pytest scripts/tests/`, ruff and mypy.

## Impact

- **Priority**: P2 — unblocks BUG-3531 and ENH-3528 reporting.
- **Effort**: Medium.
- **Risk**: Medium — nullable components ripple into cost/aggregation consumers; mitigated by no-missing-case parity tests.
- **Breaking Change**: No for existing callers; `None` cost where components are missing is an intentional correction.

## Design

- **Nullable components.** `TokenUsage` token components become `int | None`. `TokenUsage` gains `provenance: TokenProvenance = "unknown"`, `host: str | None = None`, `scope_kind: str = "unknown"`, `observed_at: str | None = None` and `observed_at_basis: str | None = None` (default-compatible, same pattern as `is_batch`). Parsers keep missing components as `None` except where a fixture-backed host contract says omission means zero (Codex's omitted `cache_write_input_tokens`).
- **Provenance values.** `TokenProvenance = Literal["measured", "estimated", "unknown"]`. Writers and parsers default to `unknown`. This issue opts **no** acquisition path into `measured`. BUG-3531 is the first to do so, for normalized Codex rows.
- **Host vs vendor.** New `host` = runtime host that produced the observation (`claude-code`, `codex`, …, from the actual invocation or `raw_events.host`). Existing `provider_vendor` = model vendor (`anthropic`, `openai`, …). The writer fills both when known and never derives either from the currently configured host. `invocation_id` is written when the runner supplies it.
- **Observation time.** Captured when the event arrives: host event timestamp → `observed_at_basis='event'`; otherwise receipt time → `'received'`. `ts` keeps its current meaning; legacy rows keep NULL `observed_at`.
- **Migration.** Append-only migration at the next free schema version (54 unless taken) adds nullable `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis` to `usage_events`. Reuses `channel`, `session_id`, `invocation_id`, `provider_vendor`. Legacy rows read as `provenance='unknown'`. Update `schema_manifest.json` and version pins together.
- **Replay.** Add a metadata-aware usage iterator yielding host alongside the raw line; `_backfill_usage_events` uses it. Existing `_iter_events` tuple consumers are unchanged.
- **Consumers.** `estimate_cost_usd` returns `None` when any required component is missing. Executor payload sums are per-component with known/missing counts, and they don't raise on `None`. The legacy two-int `UsageCallback` fires only when input and output are both known; `DetailedUsageCallback` always receives the partial observation. Audit `pricing.py`, `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/*quality*.py` and `cli/ctx_stats.py` aggregators for `None` safety. Numeric output stays the same in the no-missing case.
- **Codex transition.** Live Codex rows written after this lands carry `host='codex'`, `provenance='unknown'`. Host identity alone does not certify their still-unnormalized input.

## Acceptance Criteria

- [ ] `TokenUsage` components are `int | None`; new metadata fields default to unknown/None; existing construction sites compile and behave identically.
- [ ] A partial-event fixture survives `usage_from_event` → detailed callback → executor payload → `usage_events` row with missing components still NULL and completeness counts preserved. Known zero stays zero; the Codex omitted-cache-write-means-zero rule is fixture-backed.
- [ ] Legacy `UsageCallback` is invoked only for known input/output pairs; callback-consumer tests cover both callbacks.
- [ ] `estimate_cost_usd` returns `None` (not 0) when any required component is missing; audited consumers don't raise on `None`.
- [ ] Migration adds the five columns at the next free version; manifest/version pins updated together; old-schema DBs remain readable; SessionStart-triggered rebuild preserves `channel='live'` rows and their new metadata.
- [ ] `record_usage_event` defaults `provenance='unknown'`; no code path in this issue writes `measured`. A live Codex write persists `host='codex'`, `provenance='unknown'`.
- [ ] `host` and `provider_vendor` are both populated from the actual invocation when known; tests show neither comes from the configured host.
- [ ] Observation time survives delayed loop completion; `event` vs `received` bases are distinguishable; legacy loop-finish `ts` is never copied into `observed_at`.
- [ ] Raw-event host survives backfill/rebuild through the new iterator; existing `_iter_events` consumers are unchanged.

## Scope Boundaries

- **In scope**: nullable observations, migration, unknown-default writer, host/vendor/scope/observation-time plumbing, host-preserving replay, `None`-safe consumers.
- **Out of scope** (ENH-3528 reporting): `token_provenance` JSON contract, `ll-ctx-stats` labels, aggregate `mixed`/composition/coverage metadata, overlap policy, runtime telemetry capability map, context-hook staleness, shareable export allowlist. Codex normalization is BUG-3531.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2

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

Every usage observation can carry missing components as `None`, a provenance classification that defaults to `unknown`, the runtime host that produced it, its scope kind, and its observation time with an explicit basis. Existing callers remain supported; readers preserve complete-data results while representing incomplete totals and costs as unavailable or explicitly partial. No row is certified `measured` by this issue.

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
- `scripts/little_loops/fsm/persistence.py` — `usage.jsonl` writer (`action_complete` → per-state usage row, line ~1100); carries `None` components and the `*_missing` counts through.
- `scripts/little_loops/fsm/cost_graph.py` — `from_usage_jsonl`, `PerStateCost`, `to_dict`, `read_json`, totals and table rendering. Preserve component completeness and unknown cost through serialization, not only the in-memory `has_unknown_model` flag; audit the locked JSON shape and its schema/version consumers.
- `scripts/little_loops/generate_schemas.py` — `action_complete` token fields (lines 174-178) are `_int`; become integer-or-null and gain the `*_missing` count fields; regenerate the generated schemas.
- `scripts/little_loops/session_store/writers.py` `_backfill_usage_events` — currently prices with `int(x or 0)` (line ~3615); switch to `None`-aware cost and write transcript-channel metadata (see Design → Replay).

### Dependent Files and Similar Patterns

- `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `cli/ctx_stats.py`, `hooks/session_start.py` — `None` audit / rebuild path.
- `observability/tracing.py` `_read_token`, `OTelAttributes.from_usage`, `StampUsageEvent.usage_event`, `StreamingParityChecker.diff` / `within_threshold` — omit unknown or partial OTel components; a nullable helper must not cause `float(None)` in the parity checker or certify two unknowns as equal.
- `history_reader/usage.py` (`cost_attribution`, `aggregate_usage`, other usage rollups) — SQL `SUM` ignores NULL contributors, so removing `or 0` is insufficient. Track component/cost completeness before exposing totals or OTel attributes. Audit `history_reader/events.py` and other dependent readers for the same null-to-zero behavior.
- `runner_spec.py` (lines ~276, ~459) via `usage_from_stream_lines` — `RunnerResult` token fields are already `int | None`; verify pass-through only.
- `host_runner.py` `_usage_from_response` (~3100) — Anthropic API / batch path; keeps `provenance='unknown'` in this issue, sets `host`/`scope_kind='request'`.

### Tests

- `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_session_store_schema.py`, `test_session_store_writers.py`, `test_assistant_messages.py`, `test_pricing.py`.
- Also: `fsm/persistence.py` `usage.jsonl` tests, `test_fsm_cost_graph.py` (JSON write/read and rendering round trips), `test_generate_schemas.py`, `test_otel_attributes.py` (partial aggregates and parity checker), `history_reader.usage` SQL/export tests, `runner_spec` usage pass-through. Each aggregate path covers complete, all-missing, and mixed known/missing inputs, including genuine zero.

### Documentation

- `docs/reference/API.md` (`TokenUsage`, `record_usage_event`), `docs/ARCHITECTURE.md` (usage_events columns).

## Program Design

### Types

- `TokenProvenance = Literal["measured", "estimated", "unknown"]`.
- `TokenUsage` — components `int | None`; adds `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis`.
- `TokenScopeKind = Literal["request", "invocation", "session", "context", "unknown"]`.
- `ObservedAtBasis = Literal["event", "received"]` (field type `ObservedAtBasis | None`).
- Cost-report state and totals carry nullable token subtotals, per-component missing counts, and `cost_usd: float | None`. `None` cost is the serialized unknown representation; any in-memory unknown flag must agree with it after a JSON round trip.

### Signatures

- `record_usage_event(db_path: Path | str, *, run_id: str, ts: str, state: str | None, model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None, cache_creation_tokens: int | None, provenance: TokenProvenance = "unknown", host: str | None = None, provider_vendor: str | None = None, scope_kind: TokenScopeKind = "unknown", observed_at: str | None = None, observed_at_basis: ObservedAtBasis | None = None, invocation_id: str | None = None) -> None` — additive keyword-only metadata; `run_id` keeps its current column; `channel` stays `'live'`.
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False) -> float | None` — already returns `None` for unpriced models; now also `None` when a required component is `None`.

### Call Path

- `usage_from_event` → runner detailed callback → `FSMExecutor` collection → `FSMExecutor._finish` → `record_usage_event`
- raw event + host → metadata-aware iterator → `_backfill_usage_events`

## Implementation Steps

1. Characterize current rows and executor payloads; add partial-event, host/observation-time retention and legacy-compatibility fixtures (failing first). Add regressions for mixed SQL/OTel aggregates, cost-report JSON round trips, and incomplete parity comparisons. Treat Codex's omitted-cache-write-as-zero assumption as unproven unless the evidence requirement in BUG-3531 is met.
2. Make `TokenUsage` components nullable with default-compatible metadata; update `usage_from_event`, both callbacks, executor sums and `estimate_cost_usd`; audit listed consumers for completeness as well as `None` safety. Update cost-report serialization/rendering and parity comparisons alongside their shared helpers; update affected schemas/version contracts.
3. Add the migration, manifest/version pins, the extended `record_usage_event`, and host/vendor/observation-time attachment at collection.
4. Add the metadata-aware iterator and switch `_backfill_usage_events`; test SessionStart-triggered rebuild with live-only rows.
5. Update API/ARCHITECTURE docs; run focused tests, then `python -m pytest scripts/tests/`, ruff and mypy.

## Impact

- **Priority**: P2 — unblocks BUG-3531 and ENH-3528 reporting.
- **Effort**: Medium.
- **Risk**: Medium — nullable components ripple into cost/aggregation consumers; mitigated by no-missing-case parity tests.
- **Breaking Change**: Existing call signatures remain compatible. Nullable incomplete totals/costs and additive completeness fields intentionally change affected output contracts; update locked schemas/version pins and readers together. Complete-data numeric results remain unchanged.

## Design

- **Nullable components.** `TokenUsage` token components become `int | None`. `TokenUsage` gains `provenance: TokenProvenance = "unknown"`, `host: str | None = None`, `scope_kind: str = "unknown"`, `observed_at: str | None = None` and `observed_at_basis: str | None = None` (default-compatible, same pattern as `is_batch`). Parsers keep missing components as `None` except where a verified host contract establishes that omission means zero. Codex's omitted `cache_write_input_tokens` is not established by an omission-only fixture or ENH-3464's assertion: use the matched-capture/producer-contract evidence requirement in BUG-3531. Until verified, preserve omission as `None`; the foundation need not wait for BUG-3531 or add a reverse dependency. Explicit `null` is never an omission-based zero.
- **Provenance values.** `TokenProvenance = Literal["measured", "estimated", "unknown"]`. Writers and parsers default to `unknown`. This issue opts **no** acquisition path into `measured`. BUG-3531 is the first to do so, for normalized Codex rows.
- **Host vs vendor.** New `host` = runtime host that produced the observation (`claude-code`, `codex`, …). Existing `provider_vendor` = vendor of the runtime host (`anthropic`, `openai`, …), derived via the existing `observability.tracing.vendor_for_runner(host)` so it matches the OTel `gen_ai.provider.vendor` addendum already emitted; a model-vendor split (e.g. `claude-code` driving a non-Anthropic model) is out of scope. `invocation_id` is written when the runner supplies it.
- **Host stamping precedence.** (1) The runner stamps `host` from the `HostRunner.name` of the specific invocation that produced the event, at collection time in the runner callback — `_finish` never calls `resolve_host()` again, so a config change mid-run or a per-state host override can't relabel rows. (2) A parser may set `host` only for an event type unique to one host (Codex `turn.completed`); Claude's `result` event shape isn't host-unique, so its parser leaves `host=None` for the runner to fill. (3) Replay takes `raw_events.host`. A parser-set host that disagrees with the runner's is a bug: log it and keep the runner's value.
- **Observation time.** Captured when the event arrives: host event timestamp → `observed_at_basis='event'`; otherwise receipt time → `'received'`. Neither Claude's `result` nor Codex's `turn.completed` carries a timestamp, so **every live row in this issue is `received`**; `event` arises only on transcript replay (the record's `timestamp`). `ts` keeps its current meaning; legacy rows keep NULL `observed_at`.
- **Scope kind per path.** Live `result` / `turn.completed` → `invocation`; transcript `assistant` records (backfill) and `_usage_from_response` (one API request) → `request`; everything else → `unknown`.
- **Migration.** Append-only migration at the next free schema version (54 unless taken) adds nullable `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis` to `usage_events`. Reuses `channel`, `session_id`, `invocation_id`, `provider_vendor`. Legacy rows read as `provenance='unknown'`. Update `schema_manifest.json` and version pins together.
- **Replay.** Add a metadata-aware usage iterator yielding host alongside the raw line; `_backfill_usage_events` uses it. Existing `_iter_events` tuple consumers are unchanged. The JSONL `list[Path]` source has no host, so it yields `host=None`. Transcript rows are written with `provenance='unknown'`, `scope_kind='request'`, `observed_at` = record `timestamp` with basis `'event'` (NULL/`None` basis when the record has no timestamp), and `host` from `raw_events.host`. `_backfill_usage_events` stops pricing with `int(x or 0)`: cost is `None` when a required component is missing.
- **`action_complete` payload shape.** For each of `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`: the payload value is the sum of the **known** contributors, or `None` when no event supplies that component (same rule as ENH-3528's aggregation). Add `usage_event_count: int` and, per component, `<component>_missing: int` (count of events missing it), emitted only when `usage_events` is non-empty. A value with `_missing > 0` is a partial subtotal and must never be priced or reported as a total. `fsm/persistence.py` copies the values and counts into `usage.jsonl` unchanged. `fsm/cost_graph.py` treats a `None` component **or** any `_missing > 0` like an unpriced model (sets the bucket's unknown flag, adds no cost) and sums tokens over known values only. `generate_schemas.py` declares the four fields integer-or-null and adds the count fields.
- **Cost-report round trips.** Carry the token subtotals and missing counts through per-state buckets, run totals, `to_dict`, JSON, and `read_json`. A state or run containing any unpriced contribution has `cost_usd=None`; do not expose a known-cost subtotal as the total. Render unavailable cost as `n/a`, all-missing tokens as unavailable, and mixed token subtotals explicitly as partial. Today `PerStateCost.to_dict` drops `has_unknown_model`, and `read_json` restores its default `False`, turning an `n/a` into `$0.0000`; reusing that flag alone is insufficient. Update the locked serialization contract and relevant schema/version consumers. Read legacy numeric reports without inventing missing counts or reclassifying historical zeros whose uncertainty was never stored.
- **SQL and OTel aggregate completeness.** `SUM(component)` ignores NULL, so pair it with contributing/missing counts (for raw usage rows, `COUNT(*) - COUNT(component)` gives the missing count). `[100, NULL]` is a partial subtotal of 100, not a total of 100; `[NULL, NULL]` is unavailable, not zero. Use the same completeness rule for costs. Existing total-only reader fields return `None` for incomplete totals; paths exposing known subtotals must carry explicit completeness. `OTelAttributes.from_usage`, `StampUsageEvent.usage_event`, and `history_reader.usage.cost_attribution` omit a component's `gen_ai.usage.*` attribute when its value is `None` **or** any contributor is missing, even when the subtotal is numeric. Complete components in the same observation/aggregate remain exportable. This minimal correctness work is in scope here; ENH-3528 still owns richer provenance/composition reporting.
- **Parity comparisons.** Audit `StreamingParityChecker` when changing `_read_token`: its current `float(_read_token(...))` cannot accept `None`. Represent an incomplete comparison as unavailable and make `within_threshold` return `False` if any required component is unknown/partial on either side. Do not silently skip missing components (including an empty comparison set) or compare two unknowns as zero. Tests cover one-sided unknown, both sides unknown, partial numeric subtotals, and complete zero counts; complete numeric comparisons retain current behavior.
- **Consumers.** `estimate_cost_usd` returns `None` when any required component is missing. The legacy two-int `UsageCallback` is called with `input_tokens + cache_read_tokens` (`subprocess_utils.py` `result` branch), so it fires only when input, output **and** cache_read are all known; `DetailedUsageCallback` always receives the partial observation. Audit `pricing.py`, `fsm/cost_graph.py`, `fsm/persistence.py`, `observability/tracing.py`, `history_reader/{usage,events}.py`, `issue_history/*quality*.py` and `cli/ctx_stats.py` aggregators for `None` safety and for incomplete values masquerading as totals. Numeric output stays the same in the no-missing case, except an unverified omission must no longer fabricate zero.
- **Codex transition.** Live Codex rows written after this lands carry `host='codex'`, `provenance='unknown'`. Host identity alone does not certify their still-unnormalized input.

## Acceptance Criteria

- [ ] `TokenUsage` components are `int | None`; new metadata fields default to unknown/None; existing construction sites compile and complete-data cases behave identically.
- [ ] A partial-event fixture survives `usage_from_event` → detailed callback → executor payload → `usage_events` row with missing components still NULL and completeness counts preserved in aggregate artifacts. Known zero stays zero; omitted Codex cache-write is `None` unless matched-capture/producer-contract evidence establishes zero, and explicit `null` stays unknown.
- [ ] Legacy `UsageCallback` is invoked only when input, output and cache_read are all known; callback-consumer tests cover both callbacks.
- [ ] `estimate_cost_usd` returns `None` (not 0) when any required component is missing; audited consumers don't raise on `None`.
- [ ] `action_complete` payload: a component sums known contributors (`None` when none is known), with `<component>_missing` and `usage_event_count` set; the generated event schema accepts null and the count fields. That payload flows through `usage.jsonl` into `cost_graph` as an unpriced bucket with no fabricated cost.
- [ ] Cost reports preserve unknown cost and token completeness through `from_usage_jsonl` → `to_dict` / JSON write → `read_json` → table rendering. Mixed priced/unpriced states and runs have `cost_usd=null`, never a partial cost or fabricated zero; all-missing tokens remain unavailable and partial subtotals stay identified. Legacy numeric reports remain readable, and affected serialization schemas/version contracts are updated.
- [ ] SQL reader and OTel tests cover `[100, NULL]`, `[NULL, NULL]`, and `[0, 0]` for tokens and known/unknown costs. Incomplete values cannot appear as complete totals; complete zeros remain zero. `StampUsageEvent` and `cost_attribution` omit a token attribute for numeric subtotals with missing contributors as well as for `None` values, while retaining complete sibling attributes.
- [ ] `StreamingParityChecker.diff` and `within_threshold` handle unknown/partial components on one or both sides without raising or passing an incomplete comparison. Complete zero/equal/different comparisons keep existing behavior.
- [ ] `_backfill_usage_events` returns `None` cost for a transcript record with a missing component and writes `scope_kind='request'`, `observed_at_basis='event'` from the record timestamp.
- [ ] Migration adds the five columns at the next free version; manifest/version pins updated together; old-schema DBs remain readable; SessionStart-triggered rebuild preserves `channel='live'` rows and their new metadata.
- [ ] `record_usage_event` defaults `provenance='unknown'`; no code path in this issue writes `measured`. A live Codex write persists `host='codex'`, `provenance='unknown'`.
- [ ] `host` is stamped from the invocation's `HostRunner.name` at collection time and `provider_vendor = vendor_for_runner(host)`; a test that changes the configured host between collection and `_finish` shows the rows keep the invoking host.
- [ ] Observation time survives delayed loop completion; live rows carry `observed_at_basis='received'`, replayed transcript rows `'event'`; legacy loop-finish `ts` is never copied into `observed_at`.
- [ ] `scope_kind` follows the per-path mapping in Design (live → `invocation`; transcript and `_usage_from_response` → `request`).
- [ ] Raw-event host survives backfill/rebuild through the new iterator; existing `_iter_events` consumers are unchanged.

## Scope Boundaries

- **In scope**: nullable observations, migration, unknown-default writer, host/vendor/scope/observation-time plumbing, host-preserving replay, completeness-safe SQL/OTel consumers, cost-report serialization/rendering, and incomplete parity comparisons. Minimal missing counts and unavailable/partial representations are required for independent delivery.
- **Out of scope** (ENH-3528 reporting): `token_provenance` JSON contract, `ll-ctx-stats` provenance labels, richer aggregate `mixed`/composition/coverage reporting, overlap policy, runtime telemetry capability map, context-hook staleness, shareable export allowlist. Codex normalization and enabling measured provenance are BUG-3531.

## Verification Notes

### Pre-implementation review 2026-09-23

Applied the review findings to the design, integration map, and acceptance criteria: cost-report JSON loses the existing unpriced flag; SQL `SUM` and OTel stamping can expose partial subtotals as totals; and making `_read_token` nullable requires updating `StreamingParityChecker`. Focused probes reproduced the cost round-trip (`n/a` → `$0.0000`) and nullable-helper failure. The omitted Codex cache-write zero assumption now requires evidence; no acquisition path is promoted to measured by this foundation.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-24T03:44:03 - `747bdb3d-c82b-437c-9f00-ae0dbc6a8638.jsonl`

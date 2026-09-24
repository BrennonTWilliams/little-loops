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
- `scripts/little_loops/fsm/persistence.py` — `usage.jsonl` writer (`action_complete` → per-state usage row, line ~1100); carries `None` components and the `*_missing` counts through.
- `scripts/little_loops/fsm/cost_graph.py` — reads `usage.jsonl` with `int(... or 0)` then prices it (line ~223); a missing component must mark the bucket unpriced (same path as `has_unknown_model`), never cost it as 0.
- `scripts/little_loops/generate_schemas.py` — `action_complete` token fields (lines 174-178) are `_int`; become integer-or-null and gain the `*_missing` count fields; regenerate the generated schemas.
- `scripts/little_loops/session_store/writers.py` `_backfill_usage_events` — currently prices with `int(x or 0)` (line ~3615); switch to `None`-aware cost and write transcript-channel metadata (see Design → Replay).

### Dependent Files and Similar Patterns

- `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `cli/ctx_stats.py`, `hooks/session_start.py` — `None` audit / rebuild path.
- `observability/tracing.py` `_read_token` — coerces `None` → 0; unknown components must omit the OTel attribute instead.
- `history_reader/usage.py` (lines ~299, ~468) and `history_reader/events.py` (line ~304) — `row[...] or 0`; OTel export must omit unknown `gen_ai.usage.*` attributes rather than emit 0; totals must not present missing as 0.
- `runner_spec.py` (lines ~276, ~459) via `usage_from_stream_lines` — `RunnerResult` token fields are already `int | None`; verify pass-through only.
- `host_runner.py` `_usage_from_response` (~3100) — Anthropic API / batch path; keeps `provenance='unknown'` in this issue, sets `host`/`scope_kind='request'`.

### Tests

- `test_subprocess_utils.py`, `test_fsm_runners.py`, `test_fsm_executor.py`, `test_session_store_schema.py`, `test_session_store_writers.py`, `test_assistant_messages.py`, `test_pricing.py`.
- Also: `fsm/persistence.py` `usage.jsonl` tests, `cost_graph` tests, `test_generate_schemas.py`, OTel tracing / `history_reader.usage` export tests, `runner_spec` usage pass-through.

### Documentation

- `docs/reference/API.md` (`TokenUsage`, `record_usage_event`), `docs/ARCHITECTURE.md` (usage_events columns).

## Program Design

### Types

- `TokenProvenance = Literal["measured", "estimated", "unknown"]`.
- `TokenUsage` — components `int | None`; adds `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis`.
- `TokenScopeKind = Literal["request", "invocation", "session", "context", "unknown"]`.
- `ObservedAtBasis = Literal["event", "received"]` (field type `ObservedAtBasis | None`).

### Signatures

- `record_usage_event(db_path: Path | str, *, run_id: str, ts: str, state: str | None, model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None, cache_creation_tokens: int | None, provenance: TokenProvenance = "unknown", host: str | None = None, provider_vendor: str | None = None, scope_kind: TokenScopeKind = "unknown", observed_at: str | None = None, observed_at_basis: ObservedAtBasis | None = None, invocation_id: str | None = None) -> None` — additive keyword-only metadata; `run_id` keeps its current column; `channel` stays `'live'`.
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
- **Host vs vendor.** New `host` = runtime host that produced the observation (`claude-code`, `codex`, …). Existing `provider_vendor` = vendor of the runtime host (`anthropic`, `openai`, …), derived via the existing `observability.tracing.vendor_for_runner(host)` so it matches the OTel `gen_ai.provider.vendor` addendum already emitted; a model-vendor split (e.g. `claude-code` driving a non-Anthropic model) is out of scope. `invocation_id` is written when the runner supplies it.
- **Host stamping precedence.** (1) The runner stamps `host` from the `HostRunner.name` of the specific invocation that produced the event, at collection time in the runner callback — `_finish` never calls `resolve_host()` again, so a config change mid-run or a per-state host override can't relabel rows. (2) A parser may set `host` only for an event type unique to one host (Codex `turn.completed`); Claude's `result` event shape isn't host-unique, so its parser leaves `host=None` for the runner to fill. (3) Replay takes `raw_events.host`. A parser-set host that disagrees with the runner's is a bug: log it and keep the runner's value.
- **Observation time.** Captured when the event arrives: host event timestamp → `observed_at_basis='event'`; otherwise receipt time → `'received'`. Neither Claude's `result` nor Codex's `turn.completed` carries a timestamp, so **every live row in this issue is `received`**; `event` arises only on transcript replay (the record's `timestamp`). `ts` keeps its current meaning; legacy rows keep NULL `observed_at`.
- **Scope kind per path.** Live `result` / `turn.completed` → `invocation`; transcript `assistant` records (backfill) and `_usage_from_response` (one API request) → `request`; everything else → `unknown`.
- **Migration.** Append-only migration at the next free schema version (54 unless taken) adds nullable `provenance`, `host`, `scope_kind`, `observed_at`, `observed_at_basis` to `usage_events`. Reuses `channel`, `session_id`, `invocation_id`, `provider_vendor`. Legacy rows read as `provenance='unknown'`. Update `schema_manifest.json` and version pins together.
- **Replay.** Add a metadata-aware usage iterator yielding host alongside the raw line; `_backfill_usage_events` uses it. Existing `_iter_events` tuple consumers are unchanged. The JSONL `list[Path]` source has no host, so it yields `host=None`. Transcript rows are written with `provenance='unknown'`, `scope_kind='request'`, `observed_at` = record `timestamp` with basis `'event'` (NULL/`None` basis when the record has no timestamp), and `host` from `raw_events.host`. `_backfill_usage_events` stops pricing with `int(x or 0)`: cost is `None` when a required component is missing.
- **`action_complete` payload shape.** For each of `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`: the payload value is the sum of the **known** contributors, or `None` when no event supplies that component (same rule as ENH-3528's aggregation). Add `usage_event_count: int` and, per component, `<component>_missing: int` (count of events missing it), emitted only when `usage_events` is non-empty. A value with `_missing > 0` is a partial subtotal and must never be priced or reported as a total. `fsm/persistence.py` copies the values and counts into `usage.jsonl` unchanged. `fsm/cost_graph.py` treats a `None` component **or** any `_missing > 0` like an unpriced model (sets the bucket's unknown flag, adds no cost) and sums tokens over known values only. `generate_schemas.py` declares the four fields integer-or-null and adds the count fields.
- **Consumers.** `estimate_cost_usd` returns `None` when any required component is missing. The legacy two-int `UsageCallback` is called with `input_tokens + cache_read_tokens` (`subprocess_utils.py` `result` branch), so it fires only when input, output **and** cache_read are all known; `DetailedUsageCallback` always receives the partial observation. OTel export (`observability/tracing.py` `_read_token`, `history_reader/usage.py`) omits a `gen_ai.usage.*` attribute whose component is unknown instead of emitting 0. Audit `pricing.py`, `fsm/cost_graph.py`, `fsm/persistence.py`, `observability/tracing.py`, `history_reader/{usage,events}.py`, `issue_history/*quality*.py` and `cli/ctx_stats.py` aggregators for `None` safety. Numeric output stays the same in the no-missing case.
- **Codex transition.** Live Codex rows written after this lands carry `host='codex'`, `provenance='unknown'`. Host identity alone does not certify their still-unnormalized input.

## Acceptance Criteria

- [ ] `TokenUsage` components are `int | None`; new metadata fields default to unknown/None; existing construction sites compile and behave identically.
- [ ] A partial-event fixture survives `usage_from_event` → detailed callback → executor payload → `usage_events` row with missing components still NULL and completeness counts preserved. Known zero stays zero; the Codex omitted-cache-write-means-zero rule is fixture-backed.
- [ ] Legacy `UsageCallback` is invoked only when input, output and cache_read are all known; callback-consumer tests cover both callbacks.
- [ ] `estimate_cost_usd` returns `None` (not 0) when any required component is missing; audited consumers don't raise on `None`.
- [ ] `action_complete` payload: a component sums known contributors (`None` when none is known), with `<component>_missing` and `usage_event_count` set; the generated event schema accepts null and the count fields. That payload flows through `usage.jsonl` into `cost_graph` as an unpriced bucket with no fabricated cost.
- [ ] OTel export omits (does not zero) a `gen_ai.usage.*` attribute whose component is unknown.
- [ ] `_backfill_usage_events` returns `None` cost for a transcript record with a missing component and writes `scope_kind='request'`, `observed_at_basis='event'` from the record timestamp.
- [ ] Migration adds the five columns at the next free version; manifest/version pins updated together; old-schema DBs remain readable; SessionStart-triggered rebuild preserves `channel='live'` rows and their new metadata.
- [ ] `record_usage_event` defaults `provenance='unknown'`; no code path in this issue writes `measured`. A live Codex write persists `host='codex'`, `provenance='unknown'`.
- [ ] `host` is stamped from the invocation's `HostRunner.name` at collection time and `provider_vendor = vendor_for_runner(host)`; a test that changes the configured host between collection and `_finish` shows the rows keep the invoking host.
- [ ] Observation time survives delayed loop completion; live rows carry `observed_at_basis='received'`, replayed transcript rows `'event'`; legacy loop-finish `ts` is never copied into `observed_at`.
- [ ] `scope_kind` follows the per-path mapping in Design (live → `invocation`; transcript and `_usage_from_response` → `request`).
- [ ] Raw-event host survives backfill/rebuild through the new iterator; existing `_iter_events` consumers are unchanged.

## Scope Boundaries

- **In scope**: nullable observations, migration, unknown-default writer, host/vendor/scope/observation-time plumbing, host-preserving replay, `None`-safe consumers.
- **Out of scope** (ENH-3528 reporting): `token_provenance` JSON contract, `ll-ctx-stats` labels, aggregate `mixed`/composition/coverage metadata, overlap policy, runtime telemetry capability map, context-hook staleness, shareable export allowlist. Codex normalization is BUG-3531.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2

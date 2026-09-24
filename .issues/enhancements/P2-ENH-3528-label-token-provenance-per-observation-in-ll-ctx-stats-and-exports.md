---
id: ENH-3528
title: Label token provenance per observation in ll-ctx-stats and exports
type: ENH
priority: P2
status: open
discovered_date: '2026-09-23'
labels:
- observability
- multi-host
relates_to:
- BUG-3531
- ENH-3532
- BUG-3542
- ENH-3543
- ENH-3544
- ENH-3545
- ENH-3546
---

# Label token provenance per observation in ll-ctx-stats and exports

## Summary

Make token provenance explicit per observation and metric. Host capabilities describe which telemetry a host can expose; they cannot determine whether every figure from that host is measured. This issue is the labeling/provenance slice (formerly "Delivery A"): consumption of stored per-observation provenance, and a provenance contract rendered by `ll-ctx-stats` and carried through history readers and shareable exports. New Codex historical rollout ingestion is split out to ENH-3532; other hosts to ENH-3534. Preserve useful context estimates where no measurement of the same quantity and interval is available.

Both prerequisites are done: ENH-3538 (foundation, schema v54) and BUG-3531 (Codex live normalization). Where the Design sections below describe foundation behavior, ENH-3538 is authoritative and this issue consumes it.

**Landing order (decided 2026-09-24):** this issue lands **before** ENH-3532/ENH-3543. Its acceptance criteria cover independent delivery only: conservative unresolved coverage and unknown historical host attribution. The combined behavior (reporting honoring the shared coverage selector and verified host attribution) is tested by ENH-3543 and BUG-3542, which land later.

**Split out 2026-09-24:** typed runtime telemetry map → ENH-3544; context-hook estimate/staleness labeling → ENH-3545; Claude `measured` promotion → ENH-3546. Without ENH-3546, Claude rows (most history) render as `unknown`. That is correct but low-signal, so land ENH-3546 close behind this issue.

## Current Behavior

- `ll-ctx-stats` fallback text already says `Estimated tokens in context`, and fallback JSON uses `estimated_tokens`. The gap is consistent provenance across token figures, context pressure, aggregates, and exports.
- `_print_json` already has a top-level `source` with values `sqlite | fallback | none`, describing the store. This meaning must not change.
- `usage_events` stores live per-invocation usage and historical assistant `message.usage` records. BUG-3530 added `channel` and rebuild preservation of live rows; ENH-3538 (done, schema v54) owns nullable observations, provenance/host/scope/time columns and completeness-safe consumers; there is no additional migration to implement here.
- Codex live `turn.completed` usage reaches `usage_events` normalized to uncached input, with `measured` provenance for producer-verified observations (BUG-3531, done). Claude rows remain `unknown` until ENH-3546.
- `context-monitor.sh` combines measured baselines with estimates and adds heuristic overhead even after the `result_token_count` branch. Its `estimated_tokens` is not automatically measured context occupancy.
- `RUNTIME_HOST_CAPABILITIES` describes runtime operations; the adapter map describes artifact emission. Runtime `token_reporting` is an advisory `ll-doctor` report, not observation provenance.
- `provider_vendor` follows ENH-3538's runtime-host-vendor contract via `vendor_for_runner(host)`; it is not a separate model-vendor field. The foundation's live observations still lack end-to-end session/invocation identity; ENH-3532 owns the additional plumbing for Codex overlap reconciliation.
- ENH-3538 preserves replay host and observation time, but `raw_events.host` can contain the ingesting host rather than the source host. ENH-3532 owns correcting new raw ingestion and establishing durable attribution evidence. Existing non-NULL host values are not automatically trustworthy.
- Existing Claude live invocation totals and transcript assistant usage can cover the same work. Current aggregation sums both channels without resolving overlap; this predates ENH-3532's Codex ingestion.

## Expected Behavior

Each rendered token figure is traceable to its metric, scope, observation source, and provenance. Missing telemetry is unavailable, not zero. Context estimates remain estimates until an applicable context measurement replaces them. Mixed-host and mixed-source history is labeled from stored observations, never from the host currently running the report.

## Design

### Capability and provenance are separate

Typed telemetry availability in the runtime host map is split out to ENH-3544. This issue must not depend on it: provenance comes only from stored observations. Do not add `HostCapabilityEntry.token_source` to the build-time adapter map or infer provenance with `token_source_for(host)`.

Record provenance at the observation boundary:

- `measured`: a host-reported count for the identified quantity and interval, including exact normalization of its cache components.
- `estimated`: any heuristic contribution, including a measured baseline plus estimated tool/turn overhead.
- `unknown`: a value exists but its provenance cannot be established, including unverifiable legacy rows.
- `mixed`: aggregate-only metadata when known measured and estimated observations contribute. Keep component totals/counts so the composition is visible. Unknown contributions make aggregate provenance unknown while preserving the known breakdown.

Unavailable is a value/availability state, not an estimate: use `null` with an explanation in provenance metadata for absent fields. Do not infer zero from missing keys unless the specific host/event contract and a fixture establish that omission means zero. Preserve trustworthy legacy classifications only when the original acquisition path can be demonstrated, not guessed from model names or the currently configured host.

Writer and observation defaults are `unknown`, never `measured`. Verified acquisition paths explicitly opt into `measured` after validating the component semantics. From the foundation release until BUG-3531 lands, live Codex rows carry `host='codex'` and `provenance='unknown'`; host identity alone must not certify their still-unnormalized input. BUG-3531 enables measured provenance only for newly normalized observations with a verified producer contract, consistent input split, and valid known output. Do not retroactively promote intermediate or legacy rows merely because their host is known.

### Missing values through the pipeline

Consume ENH-3538's nullable components and completeness metadata through history readers and exports. BUG-3531 Decision 6 controls Codex omission semantics per acquisition path: an omitted cache-write field remains `None` unless producer evidence establishes zero; explicit null/malformed values never use that exception. A known numeric zero remains zero. This issue does not reimplement parsing, callbacks, executor sums, or the foundation migration.

Aggregate each component independently: sum known contributors, retain known/missing counts, return `null` when no contributor supplies that component, and label a subtotal partial when some contributors are missing. Empty datasets also have unavailable token totals (zero observation count), distinct from observed zero usage. Consume the foundation's executor missing counts without dropping them. Its legacy two-integer callback requires known input, output **and cache_read**, while detailed callbacks retain partial observations; ENH-3538 owns that implementation and its consumer tests.

Preserve ENH-3538's cost/completeness rules: compute cost only when pricing and every required token component are known; otherwise retain `cost_usd=null`. Do not turn a known-cost subtotal into a complete cost or relax completeness-safe OTel exports. A known-price model with missing output is not zero-cost or fully priced. Ratios use a common eligible observation set for numerator and denominator, expose excluded/missing counts, and return `null` for an unavailable or zero denominator.

### Metrics, scope, and freshness

Keep these quantities distinct: per-request/per-invocation consumption, cumulative session consumption, and current context occupancy. Identify session/invocation scope and observation time wherever known. Store the acquisition channel separately from the measured/estimated classification.

Read acquisition metadata from ENH-3538's stored columns; retain event-versus-receipt time and never relabel legacy loop-finish `ts` as observation time. Preserve supplied identities without inventing a host-observed identity from model choice, run ID, or persistence time. ENH-3532 owns additional live identity plumbing and metadata-bearing Codex replay.

Treat historical host attribution separately from numeric token provenance. Legacy `raw_events.host` may name the ingesting host: a populated column alone does not certify the source. Include only verified source hosts in `token_provenance.hosts`; qualify uncertain attribution with a reason and do not derive a certified provider vendor from it. Readers/exports must preserve this distinction. ENH-3532 owns correcting new raw ingestion and persisting trustworthy attribution evidence; that correction is required before certifying those historical host labels. This reporting issue can land independently by exposing uncertain historical host attribution as unknown, using conservative channel/schema evidence and never the configured reporting host. Tests must include a Codex source ingested under a Claude-configured process and legacy rows whose origin cannot be recovered.

Replace an estimate only with an applicable measurement of the same metric, scope, and interval. Never use cumulative usage as current context occupancy or add a cumulative total to its constituent request counts. A context sample becomes stale when relevant context changes or compaction occurs; expose its observation boundary/staleness rather than presenting it as current. Between measurements, an existing supported estimator may continue with `estimated` provenance. Without either a valid measurement or estimator, report unavailable.

Retain the context estimator for its existing use cases. Remove redundant estimation only within a path where equivalent authoritative data is actually supplied. No estimator-wide deletion or new cross-host context monitor is required.

### Labeling and the `token_provenance` contract

Audit `ll-ctx-stats` usage totals/by-model, cache token figures and ratios, fallback total/breakdown, waste token totals, and context-pressure derivations. A measured numerator does not make a heuristic derived figure measured. Do not broaden this issue into time-saved or other non-token metrics.

Keep existing numeric field locations and the top-level `source`. Add a top-level `token_provenance` object whose keys are **RFC 6901 JSON Pointers** to the numeric field they describe, relative to the JSON document root (e.g. `/usage_by_model/totals/input_tokens`). Dynamic keys such as model IDs and tool names are embedded verbatim with standard JSON Pointer escaping (`~` → `~0`, `/` → `~1`); dots need no escaping, so model IDs like `claude-haiku-4.5` stay unambiguous. Each value identifies provenance, metric/scope, channel and observation time where known, availability/completeness, and aggregate composition where relevant. Text rendering uses the same semantic metadata. Do not wrap existing numbers in new objects.

**Entry scope.** Only token-count fields (per-model/per-tool/total input, output, cache-read, cache-write, waste tokens, fallback estimates) and figures derived from tokens (cache-hit ratio, context pressure, token cost) get pointer entries. Event/row counts, timestamps, and non-token metrics do not. When a group of dynamic entries (e.g. every model under `usage_by_model`) shares identical metadata, still emit one entry per numeric field. Keep entries compact: omit null-valued optional keys and do not repeat default-valued ones. The metadata-shape test asserts the required keys: `provenance`, `metric`, `availability`, `known_count`, `missing_count`, `coverage`.

Preserve JSON compatibility where existing values remain valid. Correctly changing an absent measurement previously coerced to zero into `null` is an intentional semantic correction: document the affected fields and update consumer tests. Partial aggregates retain their numeric subtotal but identify missing contributors; all-missing measurements return `null`, never a misleading measured zero.

Each pointer entry has a fixed contract: `provenance`, `metric`, `scope_kind`, nullable `session_id`/`invocation_id`, `hosts`, `channels`, nullable `observed_from`/`observed_to`, `observation_time_basis`, `availability` (`available | partial | unavailable`), `known_count`, `missing_count`, `composition` (component counts and subtotals by provenance), `coverage` (`non_overlapping | overlap_unresolved | unknown`), nullable `stale`, and nullable `reason`. Unknown identities/times remain null or empty collections; do not substitute the reporting host or report-generation time. Observation provenance is conservative at row level; component availability is independent. Derived ratios inherit uncertainty from every required operand. Validate the metadata shape as well as pointer resolution.

### Coverage and existing live/transcript overlap

Add a Claude fixture containing a live invocation total plus its constituent transcript requests. ENH-3532's Codex reconciliation does not resolve this existing case. This issue does not introduce speculative deduplication: unless disjoint coverage can be established from stored identities, a combined live/transcript aggregate has `coverage='overlap_unresolved'`, aggregate `provenance='unknown'`, and a reason explaining that it may count the same work twice. Keep per-channel subtotals and provenance composition visible; label the existing combined numeric field as an unreconciled observation sum, not verified consumption. Waste and cost rollups must propagate this qualification too. Tests include both overlapping and demonstrably disjoint observations. Equal token values, timestamp proximity, or a shared run ID alone are not proof of request identity. Exact reconciliation remains separate work; callers can see the limitation immediately.

ENH-3532 owns shared coverage selection for Codex usage, cost, waste, and exports, including the live identities needed to establish matching intervals. Consume that policy when present: verified equivalent coverage contributes once, demonstrably disjoint coverage can be added, and partial/unmatched/ambiguous coverage remains qualified. Never implement a second host-wide or session-wide channel preference here. Before that selector lands, or when it cannot establish a match, retain the unreconciled observation-sum behavior above. This issue's tests cover independent delivery only (see Landing order); ENH-3543 owns the tests for both issues landed together. No dependency on ENH-3532 is required for conservative reporting.

### Storage, exports, and model identity

Persistence of provenance, host, scope kind, and observation-time metadata is delivered by ENH-3538 (append-only migration at the next free schema version). The new `host` column is the runtime host that produced an observation; the existing `provider_vendor` column is the runtime host's vendor via `vendor_for_runner(host)`, matching the OTel `gen_ai.provider.vendor` addendum (ENH-3538 Design; a separate model-vendor field is out of scope). Both are filled from the actual invocation; neither substitutes for the other in reporting. BUG-3530's rebuild fix has landed. The acquisition channel is **not** added here: reuse its `usage_events.channel` (`'live' | 'transcript'`, legacy rows classified by `session_id` presence). Reuse existing session/invocation identity columns. A new channel value (e.g. ENH-3532's `'rollout'`) must also declare whether rebuild treats it as replayable. Legacy rows with unproven provenance remain `unknown`, with unknown observation times; replay may recover facts only from trustworthy raw-event metadata.

BUG-3531 (Codex live input normalization) depends on ENH-3538, not this issue. It persists inconsistent Codex observations (`cache_read + cache_write > input`) with `input_tokens=None` and `provenance='unknown'`, and only producer-verified observations with a consistent input split and valid known output as `'measured'` with `host='codex'`. Pre-foundation rows and intermediate unnormalized rows stay `unknown`. Existing context-state/pressure data retains `estimated` provenance.

The shareable export must retain non-sensitive provenance needed to interpret its token figures. Add safe provenance columns to `_SHAREABLE_COLUMNS`, bump `_SHAREABLE_ALLOWLIST_VERSION` and update the hash and fixtures together, and omit private transcript paths/raw source identifiers. Carry provenance through `UsageEvent`, history readers, and dashboard token exports affected by the new columns.

Keep requested/resolved model selections separate from observed model identity, following ENH-3527's contract. An unknown observed model remains unknown; it must not become a hint, assumed model ID, or zero-cost claim. Neither issue requires the other to land first.

## Acceptance Criteria

- [ ] Provenance is never selected from the current host, runtime capabilities, or the build-time adapter map (the typed telemetry map itself is ENH-3544).
- [ ] Text and JSON label all token/derived-context figures in `ll-ctx-stats`, including fallback breakdown, usage-by-model, cache, waste, and pressure. Existing top-level `source` and numeric field locations remain intact.
- [ ] `token_provenance` keys are RFC 6901 JSON Pointers; tests cover escaping of `~` and `/` in dynamic model/tool keys, dotted model IDs, and that every pointer resolves to an existing numeric (or `null`) field in the same document.
- [ ] Tests cover measured, estimated, unknown, mixed, unavailable, partial, and legacy data; a missing field is not a measured zero. Aggregation preserves source composition across multiple hosts.
- [ ] Unannotated writers default to `unknown`. A foundation-only Codex write remains unknown; after BUG-3531, only newly normalized observations satisfying its producer-contract, consistent-input, and valid-output gates become measured. No host-based promotion of intermediate/legacy rows.
- [ ] A partial-event fixture survives parsing → detailed callback → executor payload → database → history aggregation → export with missing components still null and completeness preserved. Known zero, all-missing, empty datasets, partial pricing, zero-denominator ratios, and legacy callback behavior are covered.
- [ ] Reporting retains foundation observation times and completeness through delayed persistence and export, distinguishing event/receipt time from legacy loop-finish `ts`. Unverified historical ingest-host labels are not reported as source-host facts; tests cover mixed-host ingestion and legacy unknown attribution (verified attribution is tested in BUG-3542).
- [ ] Existing Claude live/transcript overlap is exposed as unresolved coverage with channel subtotals and unknown aggregate provenance, including waste/cost rollups. Fixtures cover overlapping and demonstrably disjoint coverage; no deduplication by token equality or timestamp proximity.
- [ ] The fixed pointer-metadata schema is tested, including per-component known/missing counts, provenance composition, coverage, observation-time ranges/bases, and stale/unavailable reasons.
- [ ] `ll-ctx-stats` fallback figures derived from context-state estimates render as `estimated` (hook-side staleness labeling is ENH-3545).
- [ ] Reporting reads ENH-3538's columns and handles pre-migration schemas and unknown legacy origins (read as `unknown`) without error.
- [ ] History readers and shareable dashboard exports retain safe provenance, with allowlist version/hash and fixture updates; no private source paths are added to exports.
- [ ] Requested/resolved model identity is never presented as host-observed identity; unavailable pricing is not reported as measured zero cost. Semantic JSON corrections and the provenance contract are documented.
- [ ] No new ingestion path is added; Codex historical ingestion is ENH-3532.
- [ ] Reporting consumes ENH-3538's stored metadata without redefining its migration, writer, callback, or cost contracts; `host` and runtime-host `provider_vendor` remain distinct dimensions. Codex omission rules and measured eligibility exactly follow BUG-3531.
- [ ] Without a coverage selector, combined live/transcript/rollout aggregates expose unknown aggregate provenance and unreconciled channel subtotals rather than claiming verified deduplication. Aggregation goes through one function that ENH-3543 can replace with its selector (no scattered all-row sums).

## Scope Boundaries

- **In scope**: consumption of stored provenance, `ll-ctx-stats` labeling and `token_provenance` contract, and affected history/dashboard exports.
- **Prerequisites**: none open (ENH-3538, BUG-3531 and BUG-3530 are done).
- **Split out**: ENH-3544 (typed runtime telemetry map); ENH-3545 (context-hook estimate/staleness labeling); ENH-3546 (Claude measured provenance); ENH-3532 (Codex historical rollout ingestion); ENH-3543 (live/rollout coverage selector); BUG-3542 (raw-ingest source host); ENH-3534 (Qwen/Gemini/OMP and other hosts).
- **Out of scope**: ENH-3538's storage/writer/callback foundation; ENH-3532's raw-ingest host correction and live identity plumbing; exact reconciliation of existing live/transcript overlap (exposing unresolved coverage is in scope); improving estimator accuracy; deleting the context estimator globally; using consumption as occupancy; new context monitors; changing time-saved/non-token metrics; new model pricing/routing; a universal provenance rewrite of unrelated CLIs.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/queries.py` — safe shareable provenance/coverage columns and allowlist version/hash; conservative legacy attribution and consumption of ENH-3532's shared coverage policy when available. No foundation migration or writer reimplementation.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_codex_cache_usage`, `_render_fallback`, `_print_json`, and provenance rendering for both store and fallback branches.
- `scripts/little_loops/history_reader/{models,usage,context}.py`, `cli/artifact/dashboard.py` and its `dashboard.llat` template — provenance/completeness through readers and export.

### Dependent Files and Similar Patterns

- `subprocess_utils.py`, `fsm/{runners,executor}.py`, `session_store/{schema,writers,lifecycle}.py`, `schema_manifest.json` — ENH-3538 owns nullable observations, migration, callbacks, and persistence; ENH-3532 owns extra live/replay identity and source-host attribution. Consume their final contracts rather than independently changing acquisition semantics.

- `scripts/little_loops/hooks/session_start.py` — version-triggered `--rebuild`; test this path, not only explicit manual rebuild.
- `pricing.py`, `fsm/cost_graph.py`, `observability/tracing.py`, `issue_history/{agent_quality,quality_regressions,workspace_quality}.py`, `init/core.py` — audit assumptions about null values and new columns; update affected consumers without expanding to unrelated metrics.
- `test_cli_ctx_stats.py::TestCacheHitRateInOutput` is an additive-output precedent, but old byte-identical rendering expectations may need explicit updates when estimate/provenance labels change.

### Tests

- `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, context reader tests — mixed/unknown/partial data, unchanged store `source`, numeric locations, JSON Pointer paths, host-independent aggregation, and null-versus-zero behavior.
- Reuse ENH-3538's parser/executor/writer fixtures for end-to-end reporting assertions; do not duplicate foundation migration or callback implementation tests. Add old-schema reader and legacy-attribution cases here. ENH-3532 owns identity/host correction/rebuild regressions; this issue tests their reported meaning.
- `test_feat3304_artifact_dashboard.py` — allowlist version/hash, fixture DDL, safe provenance export, and missing/partial totals.
- `test_history_store_chokepoint_gate.py` — history-read boundaries.
- Usage/history/export fixtures — existing Claude live/transcript overlap and disjoint coverage; channel subtotals; partial known-model pricing; all-missing and observed-zero components; unchanged legacy iterator consumers.

### Documentation

Update `docs/reference/{CLI,API,HOST_COMPATIBILITY,CONFIGURATION}.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md`. Document the JSON Pointer convention, partial/mixed/unknown provenance, JSON compatibility corrections, and shareable fields. Check `docs/observability/{otel-mapping,realized-savings-verification}.md` for affected token semantics.

## Implementation Steps

1. ~~Extract the foundation~~ — done: ENH-3538; BUG-3531 retargeted to it.
2. **Foundation** — ENH-3538 (prerequisite).
3. **Normalization** — BUG-3531 (prerequisite).
4. **Reporting:** implement aggregation completeness/composition and unresolved-overlap policy; fixed `token_provenance` metadata and JSON Pointer validation; text/JSON labels for store and fallback branches. Document null/completeness corrections.
5. ~~Hook estimate/staleness labeling~~ — split to ENH-3545.
6. Carry provenance/completeness/coverage through history readers and shareable exports (allowlist version/hash/fixtures together). Update docs. Run focused tests, then the required local suite and applicable lint/type checks. Complete this issue only after reporting criteria pass.

## Program Design

### Types

- `TokenProvenance = Literal["measured", "estimated", "unknown"]` for observations; aggregate metadata also permits `mixed` and includes source composition/completeness.
- ENH-3538 owns `TokenUsage`, its nullable components, `host`/`scope_kind`/`observed_at`/`observed_at_basis`, and the storage schema. Import/reuse those types and read legacy nullable provenance as `unknown`.
- Existing `session_id`/`invocation_id` storage does not imply those identities travel with every live observation. ENH-3532 owns the extra identity plumbing; report absent identity as null until supplied.
- `channel` is existing storage from BUG-3530; ENH-3532 owns adding replayable rollout observations. Reporting consumes stored channels without reclassifying legacy rows.
- A persisted observation carries nullable token components, host/channel, metric/scope, observation time, provenance, and observed model separately from requested/resolved selection.

### Signatures

- `record_usage_event` and `TokenUsage` — consume ENH-3538's final signatures; do not restate or extend the writer here. ENH-3532 owns any additional live identity parameters.
- `UsageCallback = Callable[[int, int], None]` — the foundation invokes it only when input, output **and cache_read** are known; `DetailedUsageCallback` receives partial observations. Reporting consumes persisted completeness instead of changing either callback.
- `_aggregate_usage_events(db_path: Path) -> dict[str, Any] | None` — unchanged signature; the result gains provenance/completeness beside existing numeric fields and never consults the currently configured host.
- `_print_json(...)` and `_render_fallback(state: dict[str, Any], logger: Logger) -> None` — render the same provenance contract, preserving the top-level store `source`.

### Call Path

- Live event → `usage_from_event` → runner detailed callback/metadata attachment → executor collection → `_finish` → `record_usage_event` → aggregation → text/JSON.
- Stored raw event + host → metadata-aware usage iterator → `_backfill_usage_events` → aggregation → text/JSON.
- Context-state estimator → fallback state → `_render_fallback` / `_print_json`; usage backfill does not feed the fallback renderer.

Host event or estimator → attach provenance, host, channel → persist → aggregate values and composition → text / JSON (`token_provenance`) / safe export.

## Impact

- **Priority**: P2 — accuracy/observability enhancement; no current breakage beyond the bugs split out.
- **Effort**: Multiple separately landable deliveries — nullable observation/storage foundation, normalization handoff, then reporting/export/staleness. Do not estimate this as only a migration plus labels.
- **Risk**: Medium — output-contract changes affect JSON consumers; mitigated by keeping numeric locations and top-level `source`.
- **Breaking Change**: Additive provenance metadata and unchanged store `source`; intentional missing-value corrections must be documented and covered by consumer tests.

## Verification Notes

Review corrections applied on 2026-09-23: separated runtime capability from observed provenance; retained metric-appropriate estimation; specified unavailable/mixed values, model identity, and safe export. Reconciled research and wiring into the directive sections. The review's 30 focused existing tests passed; evidence checks returned no findings.

Review follow-up on 2026-09-23: reprioritized P0 → P2; narrowed to the labeling/provenance slice (former Delivery A) and renamed the file; split Codex historical ingestion to ENH-3532, Codex live input normalization to BUG-3531, other hosts to ENH-3534; made BUG-3530 (rebuild wipes live-only `usage_events`, confirmed in `lifecycle._REBUILD_TABLES`) a blocking prerequisite; fixed the `token_provenance` path convention as RFC 6901 JSON Pointers.

### Verify pass 2026-09-24

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

At that earlier check, `SCHEMA_VERSION = 52` and BUG-3530 was open. This prerequisite assessment is superseded by the implementation-readiness review below. The writer used plain `INSERT` with no uniqueness constraint; `token_reporting` was advisory and the shareable allowlist/version constants existed.

### Implementation-readiness review follow-up

Applied the review findings to the directive sections: unknown-default provenance (including the pre-BUG-3531 transition), end-to-end nullable values and callback/pricing behavior, explicit host/scope/observation-time plumbing, a fixed metadata contract, unresolved existing Claude live/transcript overlap, and a mandatory foundation-first delivery split. Corrected the fallback call path and refreshed the prerequisite: BUG-3530 is done and schema version is 53. The earlier VALID verdict did not resolve these prospective implementation gaps.

This follow-up changed the issue specification only.

### Pre-implementation review 2026-09-23

Extracted the foundation into ENH-3538 and retargeted BUG-3531 to it; `blocked_by` now lists ENH-3538 and BUG-3531 (BUG-3530 removed as satisfied). Added the `host` vs existing `provider_vendor` distinction. Marked hook staleness labeling as separable.

### Applied pre-implementation review 2026-09-24

Reconciled remaining foundation duplication and contradictory cache-write/vendor/callback instructions. Added conservative historical-host qualification and alignment with ENH-3532's shared coverage selection, preserving independent delivery without claiming deduplicated totals for unresolved observations. Updated integration ownership and ACs; the raw-ingest source-host correction and additional live identity plumbing belong to ENH-3532. These are specification changes, not evidence that the prerequisites or producer contracts are complete.

### Pre-implementation review 2026-09-24 (split)

Removed the resolved `blocked_by` (ENH-3538, BUG-3531 done). Decided the landing order: this issue first, and its ACs cover independent delivery only; the combined-behavior ACs moved to ENH-3543/BUG-3542. Split out ENH-3544 (telemetry map), ENH-3545 (hook staleness) and ENH-3546 (Claude measured provenance, the gap that would otherwise leave most figures `unknown`). Scoped `token_provenance` entries to token and token-derived fields.

## Status

**Open** | Created: 2026-09-23 | Priority: P2

## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:57 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:08 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:01:43 - `d1e0cad9-5218-4c39-a990-a91f5f18af0d.jsonl`
- `/ll:wire-issue` - 2026-09-23T23:43:26 - `96fe3651-90ba-4862-a958-697a2df577cc.jsonl`
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:59:16 - `f909c28b-1081-4c2f-b215-fc2794a9d5b6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Shared coverage selection and live identity plumbing are owned by ENH-3543, not ENH-3532; the raw-ingest source-host correction and attribution discriminator (`host_basis`) are owned by BUG-3542, not ENH-3532. ENH-3532 keeps historical rollout ingestion only. Treat older references here to ENH-3532 ownership of those items as pointing at ENH-3543 / BUG-3542.

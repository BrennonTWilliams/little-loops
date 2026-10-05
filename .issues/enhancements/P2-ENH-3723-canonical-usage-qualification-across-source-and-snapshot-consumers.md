---
id: ENH-3723
type: ENH
title: Canonical usage qualification across source and snapshot consumers
priority: P2
status: open
discovered_by: capture-issue
discovered_date: '2026-10-03'
captured_at: '2026-10-04T01:43:57Z'
parent: EPIC-3562
decision_needed: true
testable: true
relates_to:
- ENH-3543
- ENH-3528
- ENH-3580
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
---

# ENH-3723: Canonical usage qualification across source and snapshot consumers

## Summary

Give canonical stored-usage figures one qualification policy across source readers, shareable snapshots, and dashboard consumers. Coverage selection currently resolves overlap but does not consistently enforce the epic's audit-only disposition for explicit unknown/partial observations. Resolve the legacy-NULL and estimated-data policy before changing existing totals. This is a shared cutover prerequisite for ENH-3671–3676, not a blocker on native capture or adapter development.

## Current Behavior

`ObservationGroup.total` gates on coverage and component presence. `aggregate_usage` can return numeric components with unknown provenance. `_snapshot_usage_selection` selects canonical components when coverage is non-overlapping, and `usage_coverage_audit` lacks an equivalent qualification/provenance label. `_compute_cache_rate_from_usage` separately requires measured usage.

A synthetic, representative OpenCode row with verified host/session attribution, transcript channel, unknown provenance, input 10, output 2, cache-read 4, and cache-creation NULL selects non-overlapping coverage. Source aggregation returns the known numeric components; snapshot audit stores canonical input 10, output 2, and cache-read 4 despite the epic requiring this partial row to remain audit-only. This proves a consumer-contract mismatch; it does not claim an observed native OpenCode production incident.

Follow-up temporary-database probe (2026-10-04): the same partial/unknown row with a numeric stored cost of $1 reaches `agent_quality._usage_totals` as `tokens: 16`, `cost: 1`, `priced_rows: 1`, `total_rows: 1`. That reader consumes annotated audit rows but ignores their qualification and coerces missing components to zero; its quality rates and downstream regression verdicts are part of this issue's consumer inventory. A separate captured-Claude probe returns `hit_rate_pct: 77` with `freshness: stale` after an append and `freshness: unknown` after source removal. The CLI already attaches as-of/freshness text and diagnostics: this is retained historical data, not proof of a current rate, and must remain visibly qualified.

## Expected Behavior

Separate overlap coverage from qualification to publish a canonical figure. Explicit unknown observations and partial rows declared audit-only by EPIC-3562 retain raw values and labeled audit subtotals, while their dependent canonical totals/rates are NULL/unavailable. Consumers share the same eligibility policy and visible reason; the cache-rate reader may retain its documented stricter measured-only requirement. Derived totals must not turn missing components into zero.

Choose and document legacy-NULL and estimated/mixed-provenance treatment explicitly. Do not silently apply a global measured-only filter or promote historical unknown rows to measured. Qualification evaluates every coverage-selected contributor in the requested aggregate: if any contributor fails the figure's required contract, that canonical figure is unavailable with a reason. Do not discard ineligible contributors and relabel the remaining audit subtotal as a complete total. Coverage reconciliation still precedes report-window/run filters. The six delivery issues add provider/version-qualified rows to this matrix before stored-reader cutover.

**Production publication gate:** remaining-host capture, discovery, native adapters, and raw-event retention may proceed before this issue lands. Enabling production derivation of their new usage observations requires this shared qualification policy first, because existing source/snapshot/quality readers discover `usage_events` automatically. Gating only `ll-ctx-stats` cutover would leave those earlier readers exposed. This is a delivery-stage gate, not a whole-issue scheduling dependency or a blocker on native evidence work.

**Freshness contract:** qualification of a stored observation and completeness of the current source are separate. Preserve otherwise qualified historical/as-of Claude/Codex figures with their existing freshness, lag reason and committed as-of metadata; stale/unknown values cannot be described as current or up to date. Do not erase historical consumption when originals disappear. Characterize both text and JSON behavior before extending this contract to other hosts. This does not permit a rate over only the complete subset of selected observations: missing required components make the complete session rate unavailable even when that subset has a nonzero denominator.

## Motivation

The remaining hosts will introduce deliberately partial audit observations. A shared policy prevents snapshots or dashboards from presenting those values as canonical consumption while the session reader correctly reports them unavailable.

## Proposed Solution

Factor a small qualification result from the existing `ObservationGroup`/coverage chokepoint, carrying eligibility, provenance, and a reason for each figure. Reuse it in source rollups and `_snapshot_usage_selection`, including their cost and rate prerequisites. A stored numeric `cost_usd` alone cannot qualify an otherwise audit-only observation. Extend the snapshot audit allowlist and schema only as needed to preserve the qualification label/reason without exporting source paths or native request/session identities. Audit totals remain distinct from canonical totals. No selected observations is unavailable/empty; a qualified observed zero remains numeric zero.

Treat `ObservationGroup.subtotal` as an audit subtotal, including when it is used to sort reports. Preserve the in-filter population when constructing grouped snapshot totals: silently dropping audit-only contributors cannot turn the remaining subset into a complete figure. Reconcile overlap on the full identity group before filtering; apply provenance/component qualification to the contributors in the requested figure after filtering. An out-of-window audit-only row alone does not taint a different window's figure, while an overlapping counterpart outside that window still prevents coverage certification. Built-in dashboard queries expose qualification codes/reasons and distinguish unavailable from observed zero. Custom SQL remains an audit tool; document that a bare `SUM` of selected rows or NULLs does not establish completeness, without rewriting arbitrary user SQL or adding a new query engine.

## Integration Map

### Files to Modify

- `scripts/little_loops/token_provenance.py` — `ObservationGroup` qualification and numeric/audit distinction; `row_provenance` currently collapses legacy NULL and explicit unknown, so preserve their distinction only if the chosen compatibility policy needs it.
- `scripts/little_loops/history_reader/usage.py` — selection/rollup qualification metadata.
- `scripts/little_loops/session_store/queries.py` — `_snapshot_usage_selection`, `usage_coverage_audit`, and `_SHAREABLE_COLUMNS`.
- `scripts/little_loops/cli/ctx_stats.py` — `_compute_cache_rate_from_usage`, complete-denominator qualification and as-of/freshness text/JSON parity.
- `scripts/little_loops/issue_history/agent_quality.py` — `_usage_totals`, `_rate_metrics` and their callers; carry unavailable token/cost figures into quality metrics instead of using zero defaults or a priced subset as a complete numerator.
- `scripts/little_loops/issue_history/quality_regressions.py` — consume qualified quality values without manufacturing numeric regression verdicts; retain the existing transcript/legacy-channel population and model-composition rules unless qualification requires an explicitly documented adjustment.
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — the predefined `usage_coverage_audit` query, visible qualification/reasons and custom-SQL accounting guidance; inspect `cli/artifact/dashboard.py` if generated metadata changes require it.

### Dependent Files (Callers/Importers)

- Source usage/cost/waste readers, snapshot readers, dashboard derived sums, and the host/session cache-rate path.

### Similar Patterns

- ENH-3543's coverage selector and ENH-3528's provenance metadata; preserve their existing overlap and host-attribution behavior.

### Tests

- `scripts/tests/test_enh3528_token_provenance.py`, `test_enh3543_usage_coverage.py`, `test_enh3543_snapshot_usage.py`, and `test_enh3656_stored_cache_rate.py`; export allowlist/privacy tests affected by the audit fields.
- `scripts/tests/test_issue_history_agent_quality.py` (also contains quality-regression tests), `test_usage_selection_chokepoint_gate.py`, `test_feat3304_artifact_dashboard.py`, and the existing dashboard runtime tests under `scripts/tests/js/feat3304/`; exercise actual consumers rather than only the shared helper.

### Documentation

- `docs/reference/API.md`, `docs/reference/CLI.md`, and EPIC-3562's qualification/closure contract.

### Configuration

- No user option or provider-wide evidence matrix. No migration assumed; any required schema extension takes the next append-only version at landing.

## Program Design

### Types

- Proposed `UsageQualification`: canonical eligibility, provenance label, reason; component requirements supplied by the consumer. Preserve coverage as a separate result.

### Signatures

- `qualify_usage(group: ObservationGroup, required_components: tuple[str, ...]) -> UsageQualification` — proposed, after resolving the legacy/estimated policy.
- Existing `ObservationGroup.total`, `aggregate_usage`, `_snapshot_usage_selection`, and `_compute_cache_rate_from_usage` consume consistent eligibility or a documented stricter rate rule.

### Call Path

`select_usage_coverage` → `ObservationGroup` → shared qualification → source rollups / snapshot canonical fields and audit labels → dashboard / session reader.

## Implementation Steps

1. Measure the selected-report impact, then record the legacy-NULL and estimated/mixed policy decision and the figure-specific component requirements. Count raw and coverage-selected NULL/explicit-unknown rows separately; do not infer a visibility change from raw counts alone.
2. Add one shared qualification result and apply it to source and snapshot consumers; retain raw/audit data and NULL propagation.
3. Preserve qualification metadata through shareable export with privacy/allowlist checks.
4. Prove the parameterized matrix, measured Claude/Codex and as-of controls, quality/regression consumers and built-in dashboard output; coordinate remaining-host production publication and cutover tests.

## Impact

- **Priority:** P2 — closes a cross-consumer accounting gap before six new host cutovers.
- **Effort:** Medium — reuse existing selectors/metadata; policy and snapshot parity need coordinated tests.
- **Risk:** Medium — legacy visibility may change; resolve and test compatibility before implementation.
- **Breaking Change:** Possible legacy canonical totals becoming unavailable under the chosen policy; no CLI option change.

## Decision Needed

Resolve before implementation changes published figures:

- **Conservative legacy policy:** absent/NULL provenance is audit-only. This preserves a strict qualification boundary but may hide historical numeric aggregates; document that compatibility change and preserve audit subtotals.
- **Explicit historical compatibility policy:** preserve selected legacy numeric figures with a distinct historical/unknown qualification label and narrowly stated eligibility rules. This preserves visibility but cannot label them measured or certify new hosts.

**Recommended default (2026-10-04, Opus critique):** legacy NULL is audit-only for canonical totals/rates, with labeled numeric audit subtotals retained. Keep `decision_needed: true` until report impact and the final choice are recorded. This treats NULL and explicit unknown alike and needs no provenance-presence column. If historical compatibility is selected instead, preserve the raw NULL/absent-versus-explicit-unknown distinction before `row_provenance` collapses it; include source/snapshot parity for that discriminator. Do not guess that a current `unknown` row is legacy from its date, host, or current machine settings.

Read-only local probe on 2026-10-04: 517,012 raw usage rows, including 33 NULL, 512,735 explicit unknown and 4,244 measured provenance values. The unfiltered coverage selector returned zero selected rows because coverage was `overlap_unresolved`. These counts do **not** establish the visibility impact of host/session-scoped reports; record scoped selected-row and affected-figure counts before deciding. No local history was modified.

Also state whether estimated and mixed provenance remain numeric with explicit labels for general consumption reports, while measured-only rates remain stricter. Record the selected policy and its rationale in this issue and the epic; host-specific delivery must not decide it independently.

## Acceptance Criteria

- [ ] Legacy absent/NULL provenance and estimated/mixed treatment have an explicit, reviewed decision; compatibility consequences and measured-only rate differences are documented.
- [ ] Source and snapshot canonical fields agree under that policy. Explicit unknown/audit-only partial rows retain raw values and audit subtotals but have unavailable dependent canonical totals/rates and a visible qualification reason.
- [ ] Matrix covers measured, estimated, mixed, explicit unknown, and legacy NULL provenance × complete/partial cache-creation × non-overlapping/unresolved overlap. Include measured Claude/Codex controls, the representative remaining-host partial row, and aggregates mixing eligible and audit-only contributors; each delivery adds its qualified host case.
- [ ] Every selected contributor satisfies each published figure's prerequisites, or the full canonical figure is unavailable with a reason. Numeric audit subtotals survive with partial/audit labels; silently dropping an in-filter ineligible row cannot make a full total or rate appear qualified. Numeric stored costs cannot bypass token/provenance prerequisites.
- [ ] A complete measured observation plus a coverage-selected observation missing input, cache-read or cache-creation makes the complete session cache rate unavailable; it cannot publish a rate over only the complete subset. Preserve audit subtotals, missing counts and the reason.
- [ ] Quality cost/token numerators obey the same qualification policy, including the reproduced partial/unknown row with numeric stored cost. Ineligible contributors remain in completeness accounting; they cannot become zero tokens, 100% qualified cost coverage or a numeric regression verdict. Preserve existing channel pins and qualified-history controls.
- [ ] Source and snapshot preserve coverage reconciliation before report filters; an excluded overlapping counterpart cannot make the remaining group canonical. An empty selection remains unavailable/empty, while a qualified all-zero observation returns zero; a zero denominator leaves its rate unavailable.
- [ ] Snapshot export carries safe provenance/qualification metadata and passes allowlist/privacy tests; native IDs, source paths, and credentials are not introduced into shareable fields.
- [ ] Built-in snapshot/dashboard aggregates preserve the requested population, show qualification/reasons, and distinguish empty/unavailable from observed zero. Source/snapshot filter tests distinguish an out-of-window audit-only row from an out-of-window overlapping counterpart. Custom-SQL guidance explains that arbitrary subset sums do not certify full totals; no SQL rewriting or new query engine is required.
- [ ] Source readers, built-in snapshots/dashboard, and the stored session reader agree, allowing only documented stricter measured-only rates. Derived sums preserve missingness rather than coercing it to zero.
- [ ] Existing Claude/Codex text and JSON retain qualified as-of values and freshness diagnostics after append/source loss; stale/unknown data is never represented as a current measurement. Missing/failed derive has an unavailable/unknown result rather than a fresh zero. Historical stored qualification is independent of original-source availability.
- [ ] Incremental derive, full rebuild, and repeated refresh preserve the selected policy and cannot promote unknown ingest-time evidence.
- [ ] ENH-3671–3676 cite this shared contract and pass qualification tests before enabling production derivation of newly recognized usage rows and before reader cutover; their capture/adapter/raw-retention work can proceed independently.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope:** shared canonical eligibility, safe snapshot labels, source/snapshot/readers parity, legacy policy and regression matrix.
- **Out of scope:** provider capture, host adapters, new component-level measured exceptions without an epic decision, pricing fallback, context occupancy, and unrelated reader refactors.

## Related Key Documentation

- `docs/reference/API.md` — provenance, coverage, and snapshot contracts.
- `docs/reference/CLI.md` — consumption figures and unavailable-rate semantics.

## Status

**Open** | Created: 2026-10-03 | Priority: P2


## Session Log

- Pre-implementation follow-up review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.72), checked against temporary-database probes: added the production-publication gate, explicit quality/dashboard owners, complete cache-rate denominator, filtered population and as-of compatibility controls. Kept the legacy/estimated decision open; no implementation or historical requalification is claimed.

- Pre-implementation epic review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.76) supported whole-aggregate qualification, cost/rate prerequisites, filter parity and empty-versus-zero controls. Kept the legacy policy decision open with a conservative recommendation and measured raw/global-selection counts; a historical exception must preserve raw provenance presence explicitly. Specification changes only.

- `/ll:capture-issue` - 2026-10-04T01:51:01 - `7ac1ad38-c74f-402b-a14d-5845cde7ff55.jsonl`

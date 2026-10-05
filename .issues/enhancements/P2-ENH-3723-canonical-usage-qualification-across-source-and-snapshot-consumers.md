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
decision_needed: false
testable: true
relates_to:
- BUG-3696
- ENH-3543
- ENH-3528
- ENH-3580
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3723: Canonical usage qualification across source and snapshot consumers

## Summary

Give canonical stored-usage figures one qualification policy across source readers, shareable snapshots, and dashboard consumers. Coverage selection currently resolves overlap but does not consistently enforce the epic's audit-only disposition for explicit unknown/partial observations. Resolve the legacy-NULL and estimated-data policy before changing existing totals. This is a shared cutover prerequisite for ENH-3671–3676, not a blocker on native capture or adapter development.

## Current Behavior

`ObservationGroup.total` gates on coverage and component presence. `aggregate_usage` can return numeric components with unknown provenance. `_snapshot_usage_selection` selects canonical components when coverage is non-overlapping, and `usage_coverage_audit` lacks an equivalent qualification/provenance label. `_compute_cache_rate_from_usage` separately requires measured usage.

A synthetic, representative OpenCode row with verified host/session attribution, transcript channel, unknown provenance, input 10, output 2, cache-read 4, and cache-creation NULL selects non-overlapping coverage. Source aggregation returns the known numeric components; snapshot audit stores canonical input 10, output 2, and cache-read 4 despite the epic requiring this partial row to remain audit-only. This proves a consumer-contract mismatch; it does not claim an observed native OpenCode production incident.

Follow-up temporary-database probe (2026-10-04): the same partial/unknown row with a numeric stored cost of $1 reaches `agent_quality._usage_totals` as `tokens: 16`, `cost: 1`, `priced_rows: 1`, `total_rows: 1`. That reader consumes annotated audit rows but ignores their qualification and coerces missing components to zero; its quality rates and downstream regression verdicts are part of this issue's consumer inventory. A separate captured-Claude probe returns `hit_rate_pct: 77` with `freshness: stale` after an append and `freshness: unknown` after source removal. The CLI already attaches as-of/freshness text and diagnostics: this is retained historical data, not proof of a current rate, and must remain visibly qualified.

Review probes on inspected branch `main` (2026-10-04) also reproduced the boundary with **measured** provenance: input 10, output 2, cache-read 4, cache-creation NULL and stored cost $1 publish canonical input/output/cache-read/cost in both source and snapshot readers. `ctx_stats._aggregate_usage_events` publishes the same values under `usage_by_model.totals`, with cost availability `available`, because it uses `ObservationGroup.subtotal` directly. Separately, `_rate_metrics` makes a five-closed-issue window with no usage numerator a `0.0`, `stable` baseline, then compares later priced windows against it. Unknown-only tests would miss both failures.

## Expected Behavior

Separate overlap coverage from qualification to publish a canonical figure. Explicit unknown observations and partial rows declared audit-only by EPIC-3562 retain raw values and labeled audit subtotals, while their dependent canonical totals/rates are NULL/unavailable. Consumers share the same eligibility policy and visible reason; the cache-rate reader may retain its documented stricter measured-only requirement. Derived totals must not turn missing components into zero.

Choose and document legacy-NULL and estimated/mixed-provenance treatment explicitly. Do not silently apply a global measured-only filter or promote historical unknown rows to measured. Qualification evaluates every coverage-selected contributor in the requested aggregate: if any contributor fails the figure's required contract, that canonical figure is unavailable with a reason. Do not discard ineligible contributors and relabel the remaining audit subtotal as a complete total. Coverage reconciliation still precedes report-window/run filters. The six delivery issues add provider/version-qualified rows to this matrix before stored-reader cutover.

**Production publication gate:** remaining-host capture, discovery, native adapters, and raw-event retention may proceed before this issue lands. Enabling production derivation of their new usage observations requires this shared qualification policy first, because existing source/snapshot/quality readers discover `usage_events` automatically. Gating only `ll-ctx-stats` cutover would leave those earlier readers exposed. This is a delivery-stage gate, not a whole-issue scheduling dependency or a blocker on native evidence work.

**Freshness contract:** qualification of a stored observation and completeness of the current source are separate. Preserve otherwise qualified historical/as-of Claude/Codex figures with their existing freshness, lag reason and committed as-of metadata; stale/unknown values cannot be described as current or up to date. Do not erase historical consumption when originals disappear. Characterize both text and JSON behavior before extending this contract to other hosts. This does not permit a rate over only the complete subset of selected observations: missing required components make the complete session rate unavailable even when that subset has a nonzero denominator.

## Motivation

The remaining hosts will introduce deliberately partial audit observations. A shared policy prevents snapshots or dashboards from presenting those values as canonical consumption while the session reader correctly reports them unavailable.

## Proposed Solution

Factor a small qualification result from the existing `ObservationGroup`/coverage chokepoint, carrying eligibility, provenance, and a reason for each figure. Reuse it in source rollups and `_snapshot_usage_selection`, including their cost and rate prerequisites. A stored numeric `cost_usd` alone cannot qualify an otherwise audit-only observation. Extend the snapshot audit allowlist and schema only as needed to preserve the qualification label/reason without exporting source paths or native request/session identities. Audit totals remain distinct from canonical totals. No selected observations is unavailable/empty; a qualified observed zero remains numeric zero.

**Row admission precedes figure completeness.** Under the epic's current row-level contract, an observation missing any of the four `TOKEN_COLUMNS` is audit-only for every canonical figure, even if its provenance says `measured` and the requested component is present. Missing `cost_usd` alone is a pricing gap, not a partial-token row: an otherwise qualified complete observation may publish tokens while its cost is unavailable. Unknown model pricing cannot suppress qualified tokens. Evidence-backed component exceptions require a separate epic decision; `required_components` is not permission to invent one here.

| Figure | Prerequisites after coverage reconciliation and row admission |
| --- | --- |
| Token component / four-component consumption | Every in-population row is admitted; each requested component is present. |
| Cost / cost per issue | Every contributor is admitted and has a stored numeric cost; do not reprice at read time or sum only priced contributors. Dollars remain API list-price estimates; measured token provenance does not certify a billed amount. |
| Waste tokens / waste percentage | Admit the full joined population; preserve the existing **input + output** metric definition, its wasted-run subset, and nonzero denominator rule. |
| Session cache hit rate | Every contributor is admitted and measured; input, cache-read and cache-creation form the complete denominator; a zero denominator is unavailable. |
| Quality tokens per issue | Admit the full attributed population; require all four token components and the existing closed-issue denominator. Preserve fractional attribution across multi-issue sessions. |

The stored-row provenance reader recognizes `measured`/`estimated`; recognition does not decide admission of estimated rows. `mixed` describes an aggregate of measured and estimated rows, canonical only if both are admitted by the selected policy. Do not add a stored `mixed` value or infer its evidence. An unrecognized stored value fails closed like explicit unknown. The legacy exception, if selected, must be explicit before admission.

Treat `ObservationGroup.subtotal` as an audit subtotal, including when it is used to sort reports. Preserve the in-filter population when constructing grouped snapshot totals: silently dropping audit-only contributors cannot turn the remaining subset into a complete figure. Reconcile overlap on the full identity group before filtering; apply provenance/component qualification to the contributors in the requested figure after filtering. An out-of-window audit-only row alone does not taint a different window's figure, while an overlapping counterpart outside that window still prevents coverage certification. Built-in dashboard queries expose qualification codes/reasons and distinguish unavailable from observed zero. Custom SQL remains an audit tool; document that a bare `SUM` of selected rows or NULLs does not establish completeness, without rewriting arbitrary user SQL or adding a new query engine.

Keep coverage-selected populations and counts intact, including audit-only rows in `selected_usage_events`; selection certifies overlap only. Add qualification labels as needed and correct its dashboard guidance. Canonical fields in `usage_coverage_audit` must carry the scope used for their eligibility (currently model-wide, with channel contributions), so a channel subtotal cannot recertify an incomplete model. Record a safe qualification-policy version in snapshot metadata so retained snapshots do not imply they were evaluated under a later policy. Computed snapshot columns/metadata do not by themselves require a source-history migration. Keep existing public numeric keys for canonical figures and expose audit subtotals distinctly; token-provenance pointers, availability, text suffixes and reason codes must agree with the values in JSON. Export only bounded accounting reason codes, never source-derived diagnostic text containing identities or paths.

For usage-derived quality metrics, propagate `None` through optional numerators and choose the earliest **qualified, sample-sufficient** baseline, rather than the earliest closed-issue window. A metric with no observations or unmet prerequisites is unavailable; a qualified observed zero is still zero. Preserve `sample_size`, fractional attribution and coverage diagnostics. `_rate_metrics` also serves correction counts: absence can still mean zero there, so do not impose usage missingness on correction/fix/retry metrics. Keep the existing regression-window/model-composition rules and label the period of any older eligible result; do not present it as a verdict for an unavailable latest window. Update the quality metric definitions and text/JSON reasons that currently say tokens are always computable or price coverage withholds only the verdict.

## Integration Map

### Files to Modify

- `scripts/little_loops/token_provenance.py` — `ObservationGroup` qualification, `entry`/rendering metadata and numeric/audit distinction; `row_provenance` currently collapses legacy NULL and explicit unknown, so preserve their distinction only if the chosen compatibility policy needs it.
- `scripts/little_loops/history_reader/usage.py` — `aggregate_usage`, `cost_attribution`, `waste_attribution` and rollup qualification metadata; waste has its own coverage-only numeric gate and must use the shared policy too. Preserve selectors as coverage-only, with their audit population intact.
- `scripts/little_loops/session_store/queries.py` — `_snapshot_usage_selection`, `usage_coverage_audit`, and `_SHAREABLE_COLUMNS`.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events` all-history/per-model canonical versus audit fields, `_compute_cache_rate_from_usage`, complete-denominator qualification and as-of/freshness text/JSON parity.
- `scripts/little_loops/issue_history/agent_quality.py` — `_usage_totals`, `_rate_metrics`, their callers, metric definitions and text/JSON diagnostics; carry optional token/cost numerators and qualification into baseline selection instead of using zero defaults or a priced subset as a complete numerator.
- `scripts/little_loops/issue_history/quality_regressions.py` — consume qualified quality values without manufacturing numeric regression verdicts; retain the existing transcript/legacy-channel population and model-composition rules unless qualification requires an explicitly documented adjustment.
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — the predefined `usage_coverage_audit` query, visible qualification/reasons and custom-SQL accounting guidance; inspect `cli/artifact/dashboard.py` if generated metadata changes require it.

### Dependent Files (Callers/Importers)

- Source usage/cost/waste readers, snapshot readers, dashboard derived sums, and the host/session cache-rate path.
- `scripts/little_loops/issue_history/workspace_quality.py` — per-repository and workspace-union quality consumers; test that qualified and audit-only members cannot yield a complete subset total. Keep its repository disambiguation and read-only union design.

### Similar Patterns

- ENH-3543's coverage selector and ENH-3528's provenance metadata; preserve their existing overlap and host-attribution behavior.

### Tests

- `scripts/tests/test_enh3528_token_provenance.py`, `test_enh3543_usage_coverage.py`, `test_enh3543_snapshot_usage.py`, and `test_enh3656_stored_cache_rate.py`; export allowlist/privacy tests affected by the audit fields.
- `scripts/tests/test_issue_history_agent_quality.py` (also contains quality-regression tests), `test_feat3410_workspace_quality.py`, `test_feat3418_workspace_quality.py`, `test_usage_selection_chokepoint_gate.py`, `test_feat3304_artifact_dashboard.py`, and the existing dashboard runtime tests under `scripts/tests/js/feat3304/`; exercise actual consumers rather than only the shared helper.

### Documentation

- `docs/reference/API.md`, `docs/reference/CLI.md`, and EPIC-3562's qualification/closure contract.

### Configuration

- No user option or provider-wide evidence matrix. No migration assumed; any required schema extension takes the next append-only version at landing.

## Program Design

### Types

- Proposed immutable `UsageQualification`: canonical eligibility, provenance label, bounded reason code; audit known/missing and rejected-contributor counts remain available. Apply row admission before consumer-specific component requirements. Preserve coverage and freshness as separate results; token-evidence provenance and estimated dollar semantics are distinct.

### Signatures

- `qualify_usage(group: ObservationGroup, required_components: tuple[str, ...]) -> UsageQualification` — proposed, after resolving the legacy/estimated policy. The shared helper always enforces fixed row admission first; this tuple adds figure requirements and cannot relax the four-token-component or provenance gate. Measured-only cache-rate qualification can only tighten that result. There is no caller-supplied row-admission policy.
- Existing `ObservationGroup.total`/`entry`, source rollups including waste, `_aggregate_usage_events`, `_snapshot_usage_selection`, quality numerators/baselines, and `_compute_cache_rate_from_usage` consume consistent eligibility or the documented stricter measured-only rate rule. `ObservationGroup.subtotal` remains an explicitly labeled audit operation.

### Call Path

`select_usage_coverage` → `ObservationGroup` → shared qualification → source rollups / snapshot canonical fields and audit labels → dashboard / session reader.

## Implementation Steps

1. ~~Measure the selected-report impact, then record the legacy-NULL and estimated/mixed policy decision and the figure-specific component requirements. Count raw and coverage-selected NULL/explicit-unknown rows separately; also count currently numeric figures that would become unavailable by actual grouping/window for all-history/per-model CLI, default quality windows and built-in snapshots. Do not infer a visibility change from raw counts alone. Keep `decision_needed: true` until both choices and their consequences are recorded.~~ **Done 2026-10-04** — see "Step-1 impact measurement" and "Decision" under Decision Needed; `decision_needed` cleared. Human review of the decision remains the first acceptance criterion.
2. Add one shared qualification result and apply it to source, all-history/session CLI, snapshot and quality consumers; retain raw/audit data, metadata parity, optional numerators and qualified baseline selection. Preserve unrelated quality metrics and the existing waste formula.
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

Bounded read-only scoped probe on 2026-10-04: the latest five verified Claude host/session pairs (ordered by `MAX(ts)`) contained 60 audit rows, all 60 coverage-selected and measured with complete tokens. Their 21 currently numeric component/cost figures would all remain numeric under complete-row admission and conservative unknown/NULL treatment. No verified Codex pair matched this sample query. This is a small measured-history control, **not** a legacy-impact census or a producer-capability verdict; the broader decision remains open.

Also state whether estimated and mixed provenance remain numeric with explicit labels for general consumption reports, while measured-only rates remain stricter, and whether estimated/mixed quality values may supply trend baselines/verdicts. A change in provenance composition must not silently masquerade as a measured quality change. Record the selected policy and its rationale in this issue and the epic; host-specific delivery must not decide it independently.

Recommended estimated-data policy for review: admit complete `estimated` observations in general consumption reports with explicit estimated labels; measured + estimated aggregates are `mixed`. Keep unknown/legacy NULL audit-only and cache rates measured-only. This preserves supported estimates without treating them as measurements. It is a recommendation pending the same decision gate, not a silent cutover. BUG-3696 may land independently: adding a rate neither qualifies a usage observation nor backfills its evidence.

Opus second opinion (2026-10-04, confidence 0.74) preferred making estimated rows audit-only initially, based on future tightening risk and possible quality-composition effects; it identified missing producer/volume evidence and explicitly dissented in favor of labeled estimates where useful. Neither recommendation settles the decision. Its suggestions to leave waste outside the cutover or manufacture zero for unsupported components are not adopted: waste is already part of the shared consumer contract, and component zeros require native evidence/an approved epic contract. Existing regression-window selection may remain compatible when older results visibly name their period.

### Step-1 impact measurement (2026-10-04, read-only against `.ll/history.db`)

Ran the real consumers and `select_usage_coverage`; nothing was modified. 517,222 usage rows.

| Provenance | Rows | Notes |
| --- | --- | --- |
| explicit `unknown` | 512,735 | 482,949 Claude transcript rows with no `host_basis`; 29,697 `host_basis='handle'`; 89 live |
| `measured` | 4,454 | 4,311 transcript (`handle`), 143 live; all complete-token |
| legacy NULL | 33 | all `channel='live'`, `host` NULL, pre-2026-09-24, cost present |
| `estimated` | 0 | no local rows |

Incomplete-token rows: 2 (unknown, NULL `cache_creation_input_tokens`; unverified host). Every measured row is complete.

**Unscoped consumers are already canonical-unavailable, independent of policy.** `_classify_coverage` is called with a store-wide `ambiguous_cross_channel` flag (live + non-live channels present, and some row lacks a verified identity). Here it is true, so all 20,045 coverage groups are `overlap_unresolved` / `unverified_cross_channel_identity` and `selected_rows` is empty. `ll-ctx-stats` all-history and per-model (16 models), `aggregate_usage`, `cost_attribution`, `waste_attribution` (17 loops) and the snapshot selection already return no numeric canonical figure. The report-window `since` filter is applied after reconciliation, so it does not change this. Zero figures there change under any legacy/estimated policy.

**Scoped session reader (`_compute_cache_rate_from_usage`).** 1,343 verified host/session pairs, all `non_overlapping` with complete tokens: 366 measured-only, 976 unknown-only, 1 mixed. It already requires measured provenance, so its output is the same under either policy; the 976 unknown-only sessions are already unavailable with `unverified_usage`. Legacy NULL rows have no `host`, so they can never be in a verified pair.

**Quality windows (`agent_quality._usage_totals`) are the only consumer whose numbers move.** It reads audit rows and ignores coverage and provenance. 17 windows, 3,355 closed issues, 353,412 fractional attributed rows unknown vs 741 measured (99.8% unknown). Legacy NULL contributes nothing (live channel is excluded). Today's `tokens_per_issue`:

- 5 windows with no usage publish a numeric `0.0` / `stable` (2026-01..04 and `unknown`).
- 9 windows containing unknown rows publish numbers and verdicts (5 degrading, 2 improving, 2 stable).
- 1 window is all-measured and complete (2026-10 `ll-auto`, 16 closed).

Cost is the same except 2026-09 and 2026-10 `ll-auto` already withhold the verdict (low priced coverage).

### Decision (2026-10-04, `/ll:decide-issue` after step-1 measurement)

1. **Legacy NULL: conservative.** Absent/NULL provenance is treated exactly like explicit `unknown`: audit-only for canonical totals and rates, with labeled numeric audit subtotals kept. No provenance-presence discriminator column and no historical-compatibility label. *Consequence:* none for published figures. The 33 rows reach no report today (unscoped reports are coverage-blocked, scoped reports need a host, quality excludes the live channel). Compatibility mode would add a code path and a source/snapshot parity burden to protect rows nothing displays.
2. **Estimated/mixed: admit complete `estimated` rows in general consumption reports with an explicit `estimated` / `mixed` label; keep cache rate measured-only; quality baselines and verdicts require an all-`measured` composition.** A window containing estimated or mixed contributions shows its labeled value but no verdict and cannot be a baseline, so a provenance-composition change cannot masquerade as a measured quality change. *Consequence:* none today (0 local estimated rows). It follows the epic's "measured vs estimated" distinction and the Opus dissent is addressed by tightening the one place where composition effects bite (quality), while avoiding a future breaking change for consumption reports.
3. **Quality consequence accepted.** Under the shared policy the 5 phantom zero baselines and the 9 unknown-containing windows (all 7 non-stable verdicts) become unavailable with a reason. The one measured window becomes the first qualified, sample-sufficient baseline (`stable`, no verdict against a prior window). This removes unsupported trend verdicts rather than a measured history. **Underived sessions (Opus, verified 2026-10-04):** an issue-attributed session with raw events but no derived `usage_events` rows, or a lagging derive cursor, makes its window **unavailable**, never a zero or "complete" numerator. Example: session `cf766a9e` has 145 `raw_events` and 0 `usage_events` and is a silent zero in the 2026-10 `ll-auto` window today. That window's baseline is therefore provisional until derives catch up.
4. **Gate finding and resolution (Option A, refined).** `ambiguous_cross_channel` is tripped by **two independent populations**: the 482,949 transcript rows with NULL `host_basis`, and all 266 `channel='live'` rows, which have a NULL `session_id`/`identity_basis`. Reconciling either alone would not clear it, and Option C could not certify the live rows without a timestamp join, which this issue forbids. Chosen approach: add a `channel=` scope to `select_usage_coverage` (following the existing `host`/`session_id` scoping precedent) so coverage and the ambiguity gate are computed over the consumer's own transcript-only population. This is **scope-local coverage, not skipped coverage**: quality stays on the shared contract, the store-wide gate and ENH-3543's contract are unchanged, and live/rollout is documented as an excluded population (including Codex/rollout-orchestrated work). Required test: a live counterpart cannot change quality figures. Narrowing the store-wide gate itself (Option C) is a separate issue.
5. **Guardrails.** Do not change `_rate_metrics`' absence-equals-zero default (correction/fix/retry counts depend on it); pass usage qualification in separately.
6. **Re-deriving unknown transcript rows.** Relabeling them, or stamping `measured` during a rebuild, is promotion and is forbidden. Re-ingesting a source that still exists through the usage-refresh path is legitimate fresh evidence, but only if the old rows are deleted in the same transaction (the old unknown rows have no `observation_key`, so quality would otherwise double-count). Yield is small: about 5,410 eligible rows, and the 2026-09 windows contain rows that can never qualify. Not required by this issue.

**Second opinion (2026-10-04, `/ll:advise` Opus, confidence 0.8):** accepts decisions 1-3 (siding with labeled estimated rows over its earlier audit-only preference) and chose Option A, refined as above.

## Acceptance Criteria

- [ ] Legacy absent/NULL provenance and estimated/mixed treatment have an explicit, reviewed decision; compatibility consequences, quality-baseline/verdict eligibility and measured-only rate differences are documented.
- [ ] Source and snapshot canonical fields agree under that policy. Explicit unknown/audit-only partial rows retain raw values and audit subtotals but have unavailable dependent canonical totals/rates and a visible qualification reason.
- [ ] Matrix covers measured/estimated/explicit unknown/legacy NULL rows, mixed measured + estimated aggregates, unrecognized stored provenance, each missing token component and complete tokens × non-overlapping/unknown/unresolved coverage. Include measured Claude/Codex controls, the representative remaining-host partial row, the measured-partial numeric-cost probe, and aggregates mixing eligible and audit-only contributors; each delivery adds its qualified host case.
- [ ] Every selected contributor satisfies each published figure's prerequisites, or the full canonical figure is unavailable with a reason. Numeric audit subtotals survive with partial/audit labels; silently dropping an in-filter ineligible row cannot make a full total or rate appear qualified. Numeric stored costs cannot bypass token/provenance prerequisites.
- [ ] A complete measured observation plus a coverage-selected observation missing input, cache-read or cache-creation makes the complete session cache rate unavailable; it cannot publish a rate over only the complete subset. Preserve audit subtotals, missing counts and the reason.
- [ ] Quality cost/token numerators obey the same qualification policy, including the reproduced partial/unknown row with numeric stored cost. Ineligible contributors remain in completeness accounting; they cannot become zero tokens, 100% qualified cost coverage or a numeric regression verdict. Preserve existing channel pins and qualified-history controls.
- [ ] Quality windows with no usage or any audit-only contributor have unavailable usage-derived values and reasons; they cannot become zero baselines. The next qualified, sample-sufficient window supplies the baseline. Qualified zeros remain zero; partial priced coverage cannot qualify a cost numerator, even above the legacy 50% verdict threshold. Correction/fix/retry metrics, fractional multi-issue attribution and workspace-union populations retain their definitions; an older regression result names its actual period.
- [ ] Source and snapshot preserve coverage reconciliation before report filters; an excluded overlapping counterpart cannot make the remaining group canonical. An empty selection remains unavailable/empty, while a qualified all-zero observation returns zero; a zero denominator leaves its rate unavailable.
- [ ] Snapshot export carries safe provenance/qualification metadata, its qualification-policy version and passes allowlist/privacy tests; native IDs, source paths, and credentials are not introduced into shareable fields. Coverage-selected rows/counts remain intact; qualification is evaluated separately.
- [ ] Built-in snapshot/dashboard aggregates preserve the requested population, show qualification/reasons, and distinguish empty/unavailable from observed zero. Source/snapshot filter tests distinguish an out-of-window audit-only row from an out-of-window overlapping counterpart. Custom-SQL guidance explains that arbitrary subset sums do not certify full totals; no SQL rewriting or new query engine is required.
- [ ] Source readers, built-in snapshots/dashboard, and the stored session reader agree, allowing only documented stricter measured-only rates. Derived sums preserve missingness rather than coercing it to zero.
- [ ] `ll-ctx-stats` all-history/per-model JSON keys and text show canonical values only when qualified, with distinct labeled audit subtotals and valid provenance pointers. Metadata never says `available` for an unavailable canonical field. Cost/token/waste source readers and snapshot model/channel aggregates pass the same cases. Complete qualified tokens with missing model pricing remain canonical while cost is unavailable; a numeric stored cost cannot admit a partial-token row. Dollars are visibly estimates rather than billed measurements.
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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-05_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- Decision 4 (scope-local `channel=` parameter on `select_usage_coverage`) is recorded under Decision but not carried into "Files to Modify", Implementation Steps, Program Design Signatures, or Acceptance Criteria; its required test ("a live counterpart cannot change quality figures") has no AC line.
- Program Design still hedges on the now-settled policy ("after resolving the legacy/estimated policy", "legacy exception, if selected") — stale wording an implementer could read as still open.
- Acceptance Criterion 1 (human review of the recorded policy) is unchecked; implementation should not begin changing published figures before that review.
- Gates clean: Program Design, dependencies (no `blocked_by`), parity, claim/symbol refs, structure, learning tests (none required). All cited files, tests, and related issues resolve; `qualify_usage`/`UsageQualification` do not exist yet (no duplicate).

### Outcome Risk Factors
- Deep per-site complexity: a new shared qualification contract threaded through source rollups, snapshot selection, ctx_stats, quality baselines and the dashboard, plus a new coverage scope parameter (contract changes, not mechanical edits).
- Broad enumeration across 7 modify sites plus workspace_quality and dashboard dependents (~6-10 consumers).
- Quality windows change published verdicts (7 non-stable verdicts and 5 phantom zero baselines become unavailable); accepted in the recorded policy, but a large visible behavior change to regress-test.

## Session Log

- `/ll:decide-issue` - 2026-10-05T01:57:06 - `dd4da702-03cb-4aad-8b85-189a7f98afba.jsonl`
- `/ll:decide-issue` - 2026-10-05T01:46:59 - `b606fd82-aba7-4cff-a1d1-d303a7baa87f.jsonl`
- `/ll:confidence-check` - 2026-10-05T01:40:54 - `c65364f3-0e6e-4339-ad18-d1167792b7ba.jsonl`
- `/ll:confidence-check` - 2026-10-05T01:33:45 - `db7a7cbe-4bdf-470b-adb8-0b1fabd56d3e.jsonl`
- Targeted pre-implementation review - 2026-10-04 - Inspected `main`; temporary-database probes reproduced measured-partial canonical leakage and empty quality baselines. `/ll:advise` with `claude-opus-5-5` (confidence 0.74) supported fixed row admission, explicit metadata/CLI owners and qualified per-metric baselines. Added the figure contract, waste/workspace consumers, snapshot policy version and independent pricing handoff. Retained the legacy/estimated decision gate and documented advisor dissent; five sampled verified Claude sessions remained unaffected, without claiming a full impact census. Specification changes only.

- Pre-implementation follow-up review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.72), checked against temporary-database probes: added the production-publication gate, explicit quality/dashboard owners, complete cache-rate denominator, filtered population and as-of compatibility controls. Kept the legacy/estimated decision open; no implementation or historical requalification is claimed.

- Pre-implementation epic review - 2026-10-04 - `/ll:advise` with Opus (confidence 0.76) supported whole-aggregate qualification, cost/rate prerequisites, filter parity and empty-versus-zero controls. Kept the legacy policy decision open with a conservative recommendation and measured raw/global-selection counts; a historical exception must preserve raw provenance presence explicitly. Specification changes only.

- `/ll:capture-issue` - 2026-10-04T01:51:01 - `7ac1ad38-c74f-402b-a14d-5845cde7ff55.jsonl`

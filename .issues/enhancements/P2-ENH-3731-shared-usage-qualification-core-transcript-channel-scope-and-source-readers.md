---
id: ENH-3731
type: ENH
title: Shared usage qualification core, transcript channel scope, and source readers
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
relates_to:
- ENH-3732
- ENH-3733
- BUG-3696
- ENH-3543
- ENH-3528
- ENH-3730
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
---

# ENH-3731: Shared usage qualification core, transcript channel scope, and source readers

## Summary

Add the shared qualification contract for canonical stored-usage figures and route the source readers through it. This child owns `qualify_usage`/`UsageQualification` with fixed row admission, the logical `channel=` acquisition scope on both coverage selectors, and the source-side consumers (`aggregate_usage`, `cost_attribution`, `waste_attribution`, `ll-ctx-stats` all-history/per-model and the stored cache-rate path). Sibling children ENH-3732 (quality) and ENH-3733 (snapshot/dashboard) consume this contract and are blocked by this issue.

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. The parent's recorded **Decision (2026-10-04, `/ll:decide-issue`, commit `01747bb96`)** is authoritative and is not reopened here:

1. Legacy NULL provenance is conservative: audit-only, exactly like explicit `unknown`; no provenance-presence column or compatibility label.
2. Complete `estimated` rows are admitted in general consumption reports with an explicit `estimated`/`mixed` label; cache rate stays measured-only; quality trends require all-measured composition.
3. Decision 4 (Option A, refined): `channel=` scope on `select_usage_coverage`/`select_usage_observations`; the store-wide ambiguity gate and ENH-3543's contract are unchanged (narrowing it belongs to ENH-3730).

## Current Behavior

`ObservationGroup.total` gates on coverage and component presence; `aggregate_usage` can return numeric components with unknown provenance. `ctx_stats._aggregate_usage_events` publishes `ObservationGroup.subtotal` as canonical `usage_by_model.totals` with cost availability `available`. `waste_attribution` has its own coverage-only numeric gate. A partial row (input 10, output 2, cache-read 4, cache-creation NULL) with unknown **or measured** provenance and stored cost $1 publishes canonical input/output/cache-read/cost from source readers. `_compute_cache_rate_from_usage` separately requires measured usage and a complete denominator.

## Expected Behavior

- Row admission precedes figure completeness: an observation missing any of the four `TOKEN_COLUMNS` is audit-only for every canonical figure, regardless of provenance or requested component. Missing `cost_usd` alone is a pricing gap, not a partial-token row. Unrecognized stored provenance fails closed like explicit unknown.
- Qualification evaluates every coverage-selected contributor in the requested aggregate; if any contributor fails the figure's contract the canonical figure is unavailable with a bounded reason code. Audit subtotals stay numeric and distinctly labeled; derived totals never turn missing components into zero. A stored numeric `cost_usd` alone cannot qualify an audit-only row.
- Figure prerequisites (after coverage reconciliation and row admission):

  | Figure | Prerequisites |
  | --- | --- |
  | Token component / four-component consumption | Every in-population row admitted; each requested component present. |
  | Cost / cost per issue | Every contributor admitted with a stored numeric cost; no read-time repricing; no priced-subset sums. Dollars are API list-price estimates. |
  | Waste tokens / percentage | Admit the full joined population; keep the existing **input + output** definition, wasted-run subset and nonzero-denominator rule. |
  | Session cache hit rate | Every contributor admitted **and measured**; input, cache-read and cache-creation form the complete denominator; zero denominator is unavailable. |

- `select_usage_coverage(..., channel: str | None = None)` and `select_usage_observations` with the same argument: resolve logical channels with `row_channel` (including legacy NULL/absent channel with a session ID) before grouping and before computing `ambiguous_cross_channel`. Default `channel=None` preserves the current store-wide gate; `since`/run filters still apply after coverage reconciliation. Selectors stay coverage-only and keep audit-only rows in `selected_usage_events`.
- **Freshness contract**: qualification of a stored observation and completeness of the current source are separate. Preserve qualified historical/as-of Claude/Codex figures with existing freshness, lag reason and as-of metadata; stale/unknown cannot read as current. A cache rate over only the complete subset of selected observations is not permitted. Characterize text and JSON behavior before extending to other hosts.
- `ll-ctx-stats` all-history/per-model JSON keys keep their existing public numeric keys, show canonical values only when qualified, expose labeled audit subtotals distinctly, and never mark metadata `available` for an unavailable canonical field. Qualified tokens with missing model pricing stay canonical while cost is unavailable.
- Incremental derive, full rebuild and repeated refresh preserve the policy and cannot promote unknown ingest-time evidence.

## Proposed Solution

Factor a small immutable `UsageQualification` (eligibility, provenance label `measured`/`estimated`/`mixed`/`unknown`, bounded reason code, audit known/missing and rejected-contributor counts) from the `ObservationGroup`/coverage chokepoint in `token_provenance.py`:

- `qualify_usage(group: ObservationGroup, required_components: tuple[str, ...]) -> UsageQualification` — always enforces fixed row admission first; `required_components` adds figure requirements and cannot relax the four-component or provenance gate. Cache-rate measured-only qualification can only tighten the result. No caller-supplied admission policy. `mixed` is an aggregate label only; never store it.
- Treat `ObservationGroup.subtotal` as an explicitly labeled audit operation, including when used to sort reports.
- Add `channel` to both selectors in `history_reader/usage.py` and thread it through the coverage/ambiguity computation.
- Apply qualification in `aggregate_usage`, `cost_attribution`, `waste_attribution`, `ctx_stats._aggregate_usage_events` and `_compute_cache_rate_from_usage`.
- Keep snapshot (`queries.py`) and quality (`agent_quality.py`) untouched here; they are ENH-3733 and ENH-3732.

## Integration Map

### Files to Modify

- `scripts/little_loops/token_provenance.py` — `ObservationGroup` qualification, `entry`/rendering metadata, numeric-vs-audit distinction.
- `scripts/little_loops/history_reader/usage.py` — `channel=` scope on both selectors; qualification in `aggregate_usage`, `cost_attribution`, `waste_attribution`.
- `scripts/little_loops/history_reader/__init__.py` — re-export/doc updated selector signatures and `qualify_usage`.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_compute_cache_rate_from_usage`, as-of/freshness text/JSON parity.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/token_provenance.py` — `_META_KEYS` is an explicit allowlist feeding `same_metadata` grouping; add new qualification/audit keys there only if they should split grouping; keep `REQUIRED_KEYS` (`provenance`, `metric`, `availability`, `known_count`, `missing_count`, `coverage`) on every `entry()` in `ObservationGroup.entry` [Agent 2 finding]
- `scripts/little_loops/token_provenance.py` — `channel_subtotals()` is the audit-subtotal surface consumed by `_provenance_fields` and `_compute_cache_rate_from_usage`; keep it numeric and distinctly labeled in `ObservationGroup.channel_subtotals` [Agent 1 finding]
- `scripts/little_loops/history_reader/usage.py` — `_provenance_fields` reads `aggregate_provenance`/`coverage`/`coverage_reason`/`channel_subtotals`; add qualification label + reason here so the `aggregate_usage`/`cost_attribution` dict keys stay stable in `_provenance_fields` [Agent 1 finding]
- `scripts/little_loops/history_reader/usage.py` — `waste_attribution` keeps a hand-rolled `total/total_missing/wasted/wasted_missing` accumulator beside its `ObservationGroup`; admit the full joined population in `waste_attribution` and preserve `tokens_total_missing`/`tokens_wasted_missing`/`waste_pct` keys [Agent 1 finding]
- `scripts/little_loops/history_reader/usage.py` — `select_usage_coverage` builds `audit_group` for `CoverageGroup.channel_subtotals`; resolve `row_channel` before `_classify_coverage` and keep the channel filter Python-side (no new SQL constant naming token/cost columns beside `FROM usage_events`) in `select_usage_coverage` [Agent 2 finding]
- `scripts/little_loops/history_reader/__init__.py` — module docstring signature lines for `select_usage_coverage(conn, *, since, require_run_id, host, session_id)` / `select_usage_observations(...)` need `channel`; the `from little_loops.history_reader.usage import (` re-export block and `__all__` are the re-export site. Note `qualify_usage` lives in `token_provenance`, not `history_reader.usage` — decide the re-export source in `__all__` [Agent 1 + 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `_waste_provenance` reads `channel_subtotals`, `coverage`, `coverage_reason`, `provenance`, `tokens_total_missing`, `tokens_wasted_missing`, `waste_pct` from each waste row; any new reason/label must keep those keys in `_waste_provenance` [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `_print_json` strips only `provenance` from `usage_by_model`; new audit-subtotal keys leak into the public JSON unless stripped/kept deliberately in `_print_json`; `/usage_by_model/totals/<col>` and `/usage_by_model/per_model/<model>/<col>` pointers from `_token_provenance` must keep resolving to numeric-or-null [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `_cache_rate_provenance` composes reason prose from `coverage_reason`/`lag_reason`/`freshness` and `_STORED_USAGE_DIAGNOSTICS` ("ingested without qualified usage observations") carries the stored-absence strings; new `qualification_reason` codes (missing token component, unrecognized provenance, empty selection, unpriced contributor, non-measured) must be defined in `_cache_rate_provenance` / `_compute_cache_rate_from_usage` without changing the existing four diagnostics [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `_render` cache-rate branch ("unavailable (coverage unresolved)" / "unavailable (usage unverified)" / "no usage observed" / `based on … eligible record(s); … excluded (missing usage component)` footer) encodes the eligible-subset behavior being replaced; update in `_render` for text/JSON parity (`usage_by_model` itself has no text rendering) [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `main_ctx_stats` stderr messages key off `cache_rate["qualification_reason"]` and a qualified Codex run must still emit empty stderr in `main_ctx_stats` [Agent 2 finding]

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `writers.py` — read-only; incremental/rebuild/refresh policy tests only.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/agent_quality.py` — calls `select_usage_observations(conn)` (and imports `_connect_readonly`) in `_usage_totals`; must stay identical with `channel=None` (ENH-3732) [Agent 1 finding]
- `scripts/little_loops/session_store/queries.py` — `select_usage_coverage(conn, since=since)` feeding `selected_usage_events` in the snapshot build; must stay identical with `channel=None` (ENH-3733) [Agent 1 finding]
- `scripts/little_loops/issue_history/quality_regressions.py` — hand-written `FROM usage_events ... AND (channel = 'transcript' OR channel IS NULL)` query (line ~205) duplicates the transcript scope outside the selectors; **do not migrate it onto `channel=` here** — `test_usage_selection_chokepoint_gate.py:test_quality_regressions_query_is_not_flagged` asserts that literal; belongs to ENH-3732 [Agent 1 + 2 finding]
- `scripts/little_loops/cli/__init__.py` — re-exports `main_ctx_stats` (`__all__`); no change needed, public CLI entry unchanged [Agent 1 finding]
- `scripts/little_loops/fsm/cost_graph.py` — docstring prose pointer to `history_reader.aggregate_usage()`; not a call, no change [Agent 1 finding]
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — reads `usage_coverage_audit` from the snapshot (`FROM usage_coverage_audit ORDER BY model, channel`); ENH-3733 territory, untouched here [Agent 1 finding]
- Gate-consumer sweep: no loop YAML (`scripts/little_loops/loops/`, `.loops/*.yaml`), hook, skill, command or agent reads `usage_by_model`, `cache_hit_rate_pct`, `token_provenance`, `aggregate_usage`, `cost_attribution` or `waste_attribution` (`.loops/.history`/`.running` hits are run logs only); the `ll-ctx-stats` JSON contract is consumed only by CLI.md prose and the tests below [Agent 2 finding]
- `scripts/little_loops/session_store/usage_refresh.py` — inferred, unconfirmed: produces `usage_events` rows, no traced symbol matched; relevant only to the "repeated refresh cannot promote unknown evidence" tests [Agent 1 finding — Inferred, unconfirmed]

### Tests

- `scripts/tests/test_enh3528_token_provenance.py`, `test_enh3543_usage_coverage.py`, `test_enh3656_stored_cache_rate.py`, `test_usage_selection_chokepoint_gate.py`; parameterized matrix of measured/estimated/explicit unknown/legacy NULL, mixed measured+estimated, unrecognized provenance, each missing token component, complete tokens × non-overlapping/unknown/unresolved coverage; measured Claude/Codex controls; representative remaining-host partial row; measured-partial numeric-cost probe; aggregates mixing eligible and audit-only contributors; transcript-scope controls (live counterpart for same and unrelated session cannot change values; unscoped coverage still blocks).

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests that will break (NULL provenance is the default fixture value, so canonical-value assertions flip to unavailable — update, do not delete):**
- `scripts/tests/test_enh3528_token_provenance.py` — update in `TestUsageAggregation.test_null_components_are_missing_not_zero` (input 15 from a row with `output_tokens=None`) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3528_token_provenance.py` — update in `TestUsageAggregation.test_partial_subtotal_is_labeled` (asserts subtotal 14 / `availability == "partial"` / `partial 2/3`; becomes a labeled audit subtotal) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3528_token_provenance.py` — update in `TestUsageAggregation.test_known_zero_stays_zero` and `test_provenance_composition` (NULL-provenance `available` zero; mixed label with a live row lacking a session ID) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3528_token_provenance.py` — rewrite in `TestHistoryReaderNullContract.test_ctx_stats_partial_vs_reader_none_on_same_fixture` (asserts ctx-stats 10 vs reader `None` — the contrast being removed) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3528_token_provenance.py` — keep keys in `TestHistoryReaderNullContract.test_aggregate_usage_none_on_any_missing`, `test_waste_zero_denominator`, `TestCoverage.test_waste_propagates_overlap_and_none_on_missing`, `TestJsonDocument.test_waste_pointers_resolve` and `test_all_pointers_resolve_and_exclude_byte_fields` (`input_tokens_missing`, `tokens_*_missing`, pointer resolution, `"provenance" not in doc["usage_by_model"]`); `TestUsageAggregation.test_entry_shape` pins `REQUIRED_KEYS`; `TestHostAttribution.test_live_row_null_basis_keeps_invocation_host` pins `reason == "codex_live_scope_unknown"` exactly [Agent 2 + 3 finding]
- `scripts/tests/test_cli_ctx_stats.py` — update in `TestAggregateUsageEvents.test_aggregates_by_model_with_totals` (NULL-provenance rows, `totals.input_tokens == 45`, `cost_usd == 0.40`, one NULL-cost row — also the priced-subset-sum case) [Agent 2 + 3 finding]
- `scripts/tests/test_cli_ctx_stats.py` — re-check in `_populate_waste_run` / `_WASTE_CORE_EXPECTED` (`tokens_total` 120, `waste_pct` 1.0), used by `TestAggregateWaste.test_present_rows_returned` and `TestMainCtxStatsWasteSection.test_json_mode_waste_present`; open question: does the provenance gate apply to waste admission? The issue says "admit the full joined population" without stating — resolve before updating [Agent 3 finding]
- `scripts/tests/test_history_reader_usage.py` — update in `TestCostAttribution.test_group_by_invocation_id_sums_match_raw_totals`, `test_group_by_vendor`, `test_group_by_run_id`, and `TestUsageEventReaders.test_aggregate_usage_by_model` / `test_aggregate_usage_by_session` (NULL provenance; NULL-cost row mixed in); re-check `TestWasteAttribution` tests built on `_seed_run` (`test_success_and_wasted_runs_split_by_loop`, `test_waste_pct_none_when_no_tokens`, `test_unjoined_usage_events_excluded`) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3538_token_observations.py` — update in `TestSqlCompleteness.test_aggregate_usage` (`[(0, 0.0), (0, 0.0)]` case expects `input_tokens == 0` on NULL provenance) and `test_cost_attribution_omits_partial_attribute_keeps_complete_sibling` (expects sibling `gen_ai.usage.output_tokens == 0` beside an input-NULL row — conflicts with row-level admission) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3656_stored_cache_rate.py` — update in `test_missing_native_id_is_unverified_and_partial_or_zero_is_unavailable` (keep `qualification_reason == "unverified_usage"` unless the vocabulary changes) and `test_captured_duplicate_uuids_correct_to_two_native_requests` / `test_pair_filter_excludes_same_id_other_host_and_legacy_attribution` (`hit_rate_pct == {"known": 2, "missing": 0}` count semantics) [Agent 3 finding]

**Controls that must keep passing unchanged (default `channel=None`, measured rows):**
- `scripts/tests/test_enh3543_usage_coverage.py` — controls in `test_live_and_stored_rollout_overlap_stays_audit_only_across_filters`, `test_waste_rates_unavailable_when_run_row_has_rollout_counterpart`, `test_old_rollout_and_live_only_scope_are_unknown` (reasons `live_replay_join_unproven`, `rollout_request_identity_unverified`, `codex_live_scope_unknown`) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` — controls in `test_current_codex_rollout_uses_selected_stored_requests_and_host_pair` (rate 78, measured), `test_live_rollout_overlap_is_audit_only_for_ctx_stats`, `test_old_codex_rollout_is_unknown_but_auditable`, `test_codex_cli_uses_latest_selected_stored_session_and_clean_json` (`output.err == ""`) [Agent 1 + 2 + 3 finding]
- `scripts/tests/test_enh3549_codex_usage_refresh.py` — control in the `coverage == "unknown"` freshness case (imports `_compute_cache_rate_from_usage`) [Agent 1 + 3 finding]
- `scripts/tests/test_enh3543_snapshot_usage.py` and `scripts/tests/test_feat3304_artifact_dashboard.py` — `selected_usage_events` / `usage_coverage_audit` snapshot consumers; unchanged with `channel=None` (ENH-3733) [Agent 1 + 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — `_usage_totals` loop over `("live", "rollout")` channels; unchanged with `channel=None` (ENH-3732) [Agent 1 + 3 finding]
- `scripts/tests/test_usage_selection_chokepoint_gate.py` — `test_no_token_or_cost_reads_outside_the_chokepoint` allowlists by enclosing function name (`select_usage_observations`, `recent_usage_events`); a new SQL helper needs an allowlist entry, and `test_quality_regressions_query_is_not_flagged` pins `channel = 'transcript'` in `quality_regressions.py` [Agent 2 finding]

**Policy tests to extend (cannot promote unknown ingest-time evidence):**
- `scripts/tests/test_enh3534_host_usage_dispatch.py` — extend the pattern of `test_opencode_shape_rebuild_preserves_unknown_provenance` to a measured/unknown pair across rebuild [Agent 3 finding]
- `scripts/tests/test_session_store_incremental_usage.py`, `test_session_store_usage_refresh.py`, `test_session_store_lifecycle.py` (`_backfill_usage_events` tests), `test_enh3678_rebuild_derive_gate.py` — incremental/refresh/rebuild policy-preservation cases [Agent 2 + 3 finding]

**New tests / fixtures to follow:**
- `scripts/tests/test_enh3528_token_provenance.py` — reuse `_insert(db, **row)` (defaults `model="m1"`, `input=10`, `output=2`, cache 0, `cost_usd=None`; any column overridable) for the provenance × missing-column matrix; `TestCoverage._group(rows)` builds an in-memory `ObservationGroup` (provenance defaults `measured`) for DB-free `qualify_usage` unit tests; `estimated`/`mixed` need synthetic inserts (precedent `test_provenance_composition`). Both helpers are file-local — copy or hoist to a shared helper [Agent 3 finding]
- New explicit-NULL-token-column inserts follow the raw `INSERT INTO usage_events(ts, session_id, channel, host, host_basis, input_tokens, cache_read_input_tokens, cache_creation_input_tokens)` pattern in `test_enh3543_usage_coverage.py` / `test_enh3656_stored_cache_rate.py::test_pair_filter_excludes_same_id_other_host_and_legacy_attribution`; transcript-scope controls reuse `_live`, `_stored_rollout`, `_handle` and the `fixtures/codex/rollout-*-v0.158.0*.jsonl` fixtures [Agent 3 finding]
- New vocabulary test for the new reason codes (missing token component, unrecognized provenance, empty selection, unpriced contributor) — no existing test pins them; optionally add `("docs/reference/API.md", "qualify_usage", "ENH-3731")` to `scripts/tests/test_wiring_reference_docs.py` (substring-only gate; no existing gate covers selector signatures or CLI.md figure wording) [Agent 3 finding]
- Failed derive is unavailable/unknown, not a fresh zero — extend `test_enh3656_stored_cache_rate.py::test_stale_append_and_unknown_tail_never_report_fresh` / `test_missing_cursor_after_refresh_is_unknown` [Agent 3 finding]

### Documentation

- `docs/reference/API.md` (selector signatures, `qualify_usage`), `docs/reference/CLI.md` (consumption figures, unavailable-rate semantics, dollars as estimates).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:626` — the "Partial totals" bullet (`usage_by_model` totals "are the sum of the *known* values … labeled `partial k/n`") directly contradicts the audit-subtotal model; rewrite in the `### ll-ctx-stats` section [Agent 2 finding]
- `docs/reference/CLI.md` — also update in `### ll-ctx-stats`: the stored cache-rate paragraph ("verified, stored `usage_events`"; add the all-contributors-admitted-and-measured rule), the provenance-label bullet (`unknown` incl. legacy rows, `mixed`; add `estimated`/`mixed` consumption labels, "dollars are API list-price estimates", numeric cost cannot qualify an audit-only row), the "JSON corrections" bullet, and the `--json` `waste` row shape (may gain `provenance`/`coverage`/`channel_subtotals`); the "Cache figures" bullet is already stale vs the Codex cutover [Agent 2 finding]
- `docs/reference/API.md` — in `### select_usage_coverage / select_usage_observations` (~line 8946): add `channel: str | None = None` to the signature block and a `channel=` paragraph; the mirror note near ~9018 ("mirror `select_usage_observations`' `channel`/`host`/`host_basis`") and the `from little_loops.history_reader import (` block (~8525) are related [Agent 1 + 2 finding]
- `docs/reference/API.md` — in `### cost_attribution` / `### waste_attribution`: "`tokens_total` / `tokens_wasted` are `None` when any contributing row is missing a component" and the unresolved-coverage sentence must absorb row admission + provenance; there is no `aggregate_usage` section and no `token_provenance` module section today — `qualify_usage`/`UsageQualification` need a new section [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — in the `[^tok-claude]` and Codex `**ll-ctx-stats now reads stored Codex rollout requests (ENH-3549).**` footnote blocks: describe cache-rate qualification (measured-only, all contributors admitted) and unresolved-overlap behavior [Agent 2 finding]
- `docs/ARCHITECTURE.md` — schema-table rows `v20 | usage_events` (mentions `aggregate_usage()`), `v29` (`waste_attribution()`), and `v53 | usage_events.channel` (closest home for `channel=` scope semantics) [Agent 2 finding]
- `docs/observability/otel-mapping.md` — in the "Cost attribution query" section: `gen_ai.usage.*` keys from `history_reader.cost_attribution(group_by="gen_ai.invocation.id")` are now conditionally absent when the total is unqualified [Agent 2 finding]
- Docstrings that go stale: `history_reader/__init__.py` module docstring; `history_reader/usage.py` docstrings of `aggregate_usage`, `cost_attribution`, `waste_attribution` ("A row missing `input_tokens` or `output_tokens` has an unavailable token count"), `_provenance_fields`; `cli/ctx_stats.py:_aggregate_usage_events` ("partial subtotal is labeled `availability='partial'`"), `_compute_cache_rate_from_usage` [Agent 2 finding]
- No change needed: `docs/reference/EVENT-SCHEMA.md`, `docs/reference/CONFIGURATION.md`, `config-schema.json` (no usage/provenance keys), `README.md`, `.claude/CLAUDE.md`, `commands/`, `agents/`, `hooks/`; `CHANGELOG.md` lands at release prep, not `[Unreleased]` [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Selector SQL is constrained by `scripts/tests/test_usage_selection_chokepoint_gate.py`: an AST scan allows `FROM usage_events` string constants that also name token/cost columns only inside `history_reader/usage.py:select_usage_observations` and `recent_usage_events` (plus whole-file allowances for `session_store/{queries,writers,lifecycle,schema}.py`). The `select_usage_coverage` SQL is split across implicit-concatenation constants so the `FROM` fragment carries no column names — any `channel=` filtering added to the query must not introduce a new string constant that trips the gate.
- Selector callers today: `history_reader/usage.py::_read_groups` and `waste_attribution` (`select_usage_observations`), `cli/ctx_stats.py::_aggregate_usage_events` (no args) and `_compute_cache_rate_from_usage` (`select_usage_coverage(host=, session_id=)`), plus out-of-scope `issue_history/agent_quality.py::_usage_totals` and `session_store/queries.py` snapshot build. `channel=None` must be behavior-identical for all of them.
- `ObservationGroup.subtotal` call sites: sort keys in `aggregate_usage` (`cost_usd`) and `cost_attribution` (`input_tokens`), and the published `totals`/`per_model` values in `ctx_stats._aggregate_usage_events`. No test calls `.subtotal(` directly.
- Writers emit only `provenance` `measured`/`unknown` today (live default `unknown`; transcript `measured` iff `observation.qualified`; rollout `measured` iff measured); `estimated` is recognized on read but unwritten, so `estimated`/`mixed` paths need synthetic fixtures.
- `ctx_stats` `usage_by_model` has no text rendering (JSON only); text `_render` covers waste and the cache-rate section, so "text and JSON parity" applies to the cache-rate/freshness lines.

## Program Design

### Types

- `UsageQualification` — new immutable (`@dataclass(frozen=True)`) in `scripts/little_loops/token_provenance.py`; carries eligibility, provenance label (`measured`/`estimated`/`mixed`/`unknown`), bounded reason code, audit known/missing counts and rejected-contributor count.
- `ObservationGroup` (`token_provenance.py`, plain class) — today accumulates every row into every `AGGREGATE_COLUMNS` component with no row admission; a row missing one token column still feeds the other three.
- `CoverageGroup` / `CoverageSelection` (`history_reader/usage.py`, both `frozen=True`) — `channel=` scope changes which rows reach them, not their fields.
- Coverage values stay plain `str`: `non_overlapping`, `overlap_unresolved`, `unknown`. Provenance literals `"measured"`/`"estimated"`/`"unknown"` have no module constant (a separate `TokenProvenance` Literal lives in `subprocess_utils.py`).

### Signatures

- `qualify_usage(group: ObservationGroup, required_components: tuple[str, ...]) -> UsageQualification` — new, `token_provenance.py`.
- `select_usage_coverage(conn, *, since=None, require_run_id=False, host=None, session_id=None, channel: str | None = None) -> CoverageSelection` — `history_reader/usage.py`; `channel` is the new argument.
- `select_usage_observations(conn, *, since=None, require_run_id=False, host=None, session_id=None, channel: str | None = None) -> Iterator[Mapping[str, Any]]` — currently `yield from select_usage_coverage(...).audit_rows`.
- `row_channel(row) -> str` (`token_provenance.py:69`) — existing logical-channel resolver (NULL/absent channel with a session ID is `transcript`, without is `live`).
- `row_provenance(row) -> str` (`token_provenance.py:77`) — existing; anything other than `measured`/`estimated` already reads as `unknown`.
- `ObservationGroup.total(column)` (`:222`, `None` unless coverage is `non_overlapping` and no component is missing), `.subtotal(column)` (`:231`, sum of known values, no provenance gate), `.aggregate_provenance(column)` (`:210`), `.entry(column, *, extra_reason=None)` (`:242`).
- `aggregate_usage(group_by="model", *, since=None, db=...)` (`usage.py:766`), `cost_attribution(group_by="gen_ai.invocation.id", *, since=None, db=...)` (`:530`), `waste_attribution(*, since=None, db=...)` (`:612`) — public keys of each returned dict must be preserved.
- `ctx_stats._aggregate_usage_events(db_path) -> dict | None` (`ctx_stats.py:226`, publishes `subtotal` values and `entry` provenance) and `_compute_cache_rate_from_usage(handle, db_path) -> tuple[dict | None, str | None]` (`:445`).

### Call Path

`main_ctx_stats` -> `_aggregate_usage_events` / `_compute_cache_rate_from_usage` / `_aggregate_waste` -> `select_usage_observations` / `select_usage_coverage` -> `_classify_coverage` -> `ObservationGroup.add` -> `qualify_usage` -> published figure and `entry` metadata.

`aggregate_usage` / `cost_attribution` -> `_read_groups` -> `select_usage_observations` -> `group_rows` -> `ObservationGroup`. `waste_attribution` calls `select_usage_observations(require_run_id=True)` directly and keeps its own per-loop accumulator beside the `ObservationGroup`.

Selector call sites outside this issue's scope that must keep working unchanged with `channel=None`: `issue_history/agent_quality.py:_usage_totals` (ENH-3732) and the snapshot `selected_usage_events` build in `session_store/queries.py` (ENH-3733).

### Decision Rules

- **Row admission (fixed, first)**: a row is admitted only if all four `TOKEN_COLUMNS` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) are non-NULL. Missing `cost_usd` alone does not reject a row — it makes cost unavailable. A rejected row stays in `audit_rows` and in audit subtotals.
- **Provenance**: `measured` and `estimated` are recognized; NULL, `unknown` and unrecognized strings all read as `unknown` through `row_provenance`. Aggregate label is `measured` if every contributor is measured, `estimated` if every contributor is estimated, `mixed` if both occur, `unknown` if any contributor is `unknown`. `mixed` is never stored.
- **Cache rate**: requires every contributor admitted and `measured`; denominator is `input + cache_read + cache_creation`; zero denominator is unavailable. It may only tighten the base qualification. Existing eligible-subset behavior in `_compute_cache_rate_from_usage` (a rate over only complete rows, gated on `input_tokens` provenance alone) is what this replaces.
- **Waste**: keep `input_tokens + output_tokens`, the `_WASTED_RUN_PREDICATE` subset and `waste_pct` only when `tokens_total` is nonzero; admit the full joined population instead of the current coverage-only gate.
- **Empty selection** is unavailable; a qualified observed zero is zero.
- **Reason codes**: bounded vocabulary extends the existing coverage reasons (`unverified_cross_channel_identity`, `live_replay_join_unproven`, `cross_channel_join_unproven`, `codex_live_scope_unknown`, `codex_live_identity_unverified`, `rollout_request_identity_unverified`) and `ctx_stats` codes (`unverified_usage`, `no_store`, `unreadable_store`, `session_not_ingested`, `ingested_without_usage`). No code exists yet for missing token component, unrecognized provenance, empty selection or unpriced contributor — the implementation must define them.
- **`channel=` scope**: resolve `row_channel(row)` for every fetched row before grouping and before `ambiguous_cross_channel` is computed (currently store-wide over the `host`/`session_id`-narrowed rows: `live` present, a non-`live` channel present, and some row without verified identity); `channel=None` leaves that gate exactly as is. `since`/`require_run_id` stay post-classification.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/history_reader/usage.py` — add `channel` to `select_usage_coverage`/`select_usage_observations`, resolving `row_channel` in Python before `_classify_coverage`/`ambiguous_cross_channel`; do not add SQL text naming token/cost columns next to `FROM usage_events` (chokepoint gate)
- Update `scripts/little_loops/history_reader/usage.py` — `_provenance_fields`, `aggregate_usage`, `cost_attribution`, `waste_attribution`: route through `qualify_usage`, preserve every public dict key (`<col>_missing`, `tokens_*_missing`, `provenance`, `coverage`, `coverage_reason`, `channel_subtotals`); replace `.subtotal` sort keys with an explicitly labeled audit operation
- Update `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_compute_cache_rate_from_usage`, `_waste_provenance`, `_print_json`, `_token_provenance`, `_cache_rate_provenance`, `_render`: keep pointer resolution, the four stored-absence diagnostics and the `REQUIRED_KEYS` entry shape; decide whether audit-subtotal keys are public in `usage_by_model` JSON
- Update `scripts/little_loops/history_reader/__init__.py` — docstring signatures, import block and `__all__` for `channel` and the `qualify_usage` re-export
- Leave untouched but regression-guard with `channel=None`: `issue_history/agent_quality.py:_usage_totals`, `session_store/queries.py` snapshot build, `issue_history/quality_regressions.py` hand-written transcript query
- Update the existing tests listed under Tests → "will break" (`test_enh3528_token_provenance.py`, `test_cli_ctx_stats.py`, `test_history_reader_usage.py`, `test_enh3538_token_observations.py`, `test_enh3656_stored_cache_rate.py`) and add the new matrix, `channel=` scope, cache-rate-unavailable, reason-vocabulary and rebuild/refresh no-promotion tests
- Update `docs/reference/CLI.md` (rewrite the "Partial totals" bullet), `docs/reference/API.md` (selector signature + new `qualify_usage` section + cost/waste prose), `docs/reference/HOST_COMPATIBILITY.md`, `docs/ARCHITECTURE.md` (`v53` channel row), `docs/observability/otel-mapping.md`
- Run `python -m pytest scripts/tests/test_usage_selection_chokepoint_gate.py scripts/tests/test_enh3528_token_provenance.py scripts/tests/test_enh3543_usage_coverage.py scripts/tests/test_enh3656_stored_cache_rate.py` before the full suite

## Acceptance Criteria

- [ ] Implementation/tests/docs match the recorded policy: legacy absent/NULL audit-only, complete estimates labeled numeric consumption, cache rates measured-only; compatibility consequences documented.
- [ ] Matrix covers measured/estimated/explicit unknown/legacy NULL, mixed aggregates, unrecognized provenance, each missing token component, complete tokens × non-overlapping/unknown/unresolved coverage, measured Claude/Codex controls, the representative remaining-host partial row, the measured-partial numeric-cost probe and eligible+audit-only mixes.
- [ ] Every selected contributor satisfies each figure's prerequisites or the full canonical figure is unavailable with a bounded reason; silently dropping an in-filter ineligible row cannot make a total or rate appear qualified; numeric stored cost cannot bypass token/provenance prerequisites; empty selection is unavailable while a qualified observed zero is zero.
- [ ] A complete measured observation plus a coverage-selected observation missing input, cache-read or cache-creation makes the session cache rate unavailable, with audit subtotals, missing counts and reason preserved.
- [ ] `channel="transcript"` on both selectors reconciles transcript and legacy NULL/absent-channel rows with a session ID before coverage analysis; excluded live/rollout counterparts cannot change values or qualification; default unscoped coverage still blocks unresolved counterparts; `since`/run filters cannot certify coverage; selected populations/counts (including audit-only rows) stay intact.
- [ ] `ll-ctx-stats` all-history/per-model JSON and text show canonical values only when qualified, with distinct labeled audit subtotals and valid provenance pointers; metadata never says `available` for an unavailable field; qualified tokens with missing pricing stay canonical while cost is unavailable; dollars are visibly estimates.
- [ ] Existing Claude/Codex text and JSON retain qualified as-of values and freshness diagnostics after append/source loss; stale/unknown never described as current; failed derive is unavailable/unknown, not a fresh zero.
- [ ] Incremental derive, full rebuild and repeated refresh preserve the policy and cannot promote unknown evidence.
- [ ] Publication gate recorded: ENH-3671–3676 cite this shared contract and pass qualification tests before enabling production derivation of newly recognized usage rows; because source, snapshot and quality readers all discover `usage_events`, that gate requires **ENH-3731, ENH-3732 and ENH-3733 together**. Capture/adapter/raw-retention work can proceed independently.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Out of scope:** snapshot export/dashboard (ENH-3733), quality derive status/baselines/workspace (ENH-3732), ENH-3730's store-wide ambiguity redesign, provider capture and adapters, derive-algorithm or source-freshness changes, component-level measured exceptions, pricing fallback.

## Session Log

- `/ll:wire-issue` - 2026-10-05T03:23:32 - `e79ced76-329a-41b8-acda-11c309df53b4.jsonl`
- `/ll:refine-issue` - 2026-10-05T03:13:46 - `ca3640c2-fc5f-47d0-9305-872e41fc20ff.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2

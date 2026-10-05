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
verify_verdict: VALID
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
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Large
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

- **Terms (used consistently below).** *Admitted* = all four `TOKEN_COLUMNS` non-NULL. *Eligible* = admitted **and** row provenance is `measured` or `estimated` (NULL, explicit `unknown` and unrecognized strings all read as `unknown` through `row_provenance`, so they are never eligible). Missing `cost_usd` alone is a pricing gap, not a partial-token row and does not affect admission.
- Row admission precedes figure completeness: an observation that is not admitted is audit-only for every canonical figure, regardless of provenance. An admitted row with `unknown` provenance is also audit-only.
- Qualification evaluates every coverage-selected contributor in the requested aggregate; if any contributor fails the figure's contract the canonical figure is unavailable with a bounded reason code. Audit subtotals stay numeric and distinctly labeled; derived totals never turn missing components into zero. A stored numeric `cost_usd` alone cannot qualify an audit-only row.
- Figure prerequisites (after coverage reconciliation and row admission):

  | Figure | Prerequisites |
  | --- | --- |
  | Token component / four-component consumption | Every in-population row eligible (admitted ⇒ every component present). |
  | Cost / cost per issue | Every contributor eligible with a stored numeric cost; no read-time repricing; no priced-subset sums. Dollars are API list-price estimates. |
  | Waste tokens / percentage | **One qualification per loop over the full joined population** (reading B: row admission **plus** the provenance gate) governs both `tokens_total` and `tokens_wasted`; keep the existing **input + output** definition, wasted-run subset sum and nonzero-denominator rule. Admission still requires all four token columns, so a row with NULL cache columns now blanks that loop's waste figures (behavior change vs. today's input/output-only check). |
  | Session cache hit rate | Every contributor eligible **and measured** (`estimated` excluded); input, cache-read and cache-creation form the complete denominator; zero denominator is unavailable. Cache operand fields (`cache_read_tokens`, `cache_write_tokens`, `uncached_tokens`) stay measured-only too. |

- **Availability metadata follows qualification.** Every published `token_provenance` entry (`ObservationGroup.entry`, `_waste_provenance`, `_cache_rate_provenance`) derives `availability` from the qualified value, never from known/missing counts alone: a `None` canonical figure is `unavailable`. Canonical stored pointers use only `available`/`unavailable`; `partial` is not emitted for a figure whose canonical value is `None`. Today `counted_entry` would report `available` for `tokens_total=None` when the cause is non-missing (unknown provenance, `tokens_*_missing == 0`) — that must be fixed, and a document-wide invariant test asserts every JSON pointer whose value is `None` has `availability == "unavailable"`.
- **`qualification_reason` on result dicts.** `aggregate_usage` and `cost_attribution` rows (and `waste_attribution` rows) gain an additive `qualification_reason` key (`None` when qualified), because a `None` total with `<col>_missing == 0` will be common. Existing keys are untouched.
- `select_usage_coverage(..., channel: str | None = None)` and `select_usage_observations` with the same argument: resolve logical channels with `row_channel` (including legacy NULL/absent channel with a session ID) before grouping and before computing `ambiguous_cross_channel`. Default `channel=None` preserves the current store-wide gate; `since`/run filters still apply after coverage reconciliation. **Rows outside the requested channel are excluded from `audit_rows`/`selected_rows`/group subtotals entirely; an unrecognized channel value raises `ValueError`** (an empty result is not a silent typo). Selectors stay coverage-only and keep audit-only rows (in-channel) in `selected_usage_events`.
- **Freshness contract**: qualification of a stored observation and completeness of the current source are separate. Preserve qualified historical/as-of Claude/Codex figures with existing freshness, lag reason and as-of metadata; stale/unknown cannot read as current. A cache rate over only the complete subset of selected observations is not permitted. Characterize text and JSON behavior before extending to other hosts.
- `ll-ctx-stats` all-history/per-model JSON keys keep their existing public numeric keys, show canonical values only when qualified, expose labeled audit subtotals distinctly, and never mark metadata `available` for an unavailable canonical field. Qualified tokens with missing model pricing stay canonical while cost is unavailable.
- Incremental derive, full rebuild and repeated refresh preserve the policy and cannot promote unknown ingest-time evidence.

## Proposed Solution

Factor a small immutable `UsageQualification` (eligibility, provenance label `measured`/`estimated`/`mixed`/`unknown`, bounded reason code, audit known/missing and rejected-contributor counts) from the `ObservationGroup`/coverage chokepoint in `token_provenance.py`:

- `qualify_usage(group: ObservationGroup, *, require_cost: bool = False, measured_only: bool = False) -> UsageQualification` — a pure function of group state; always enforces fixed row admission and the provenance gate first. After admission the only figure-specific variation is whether `cost_usd` is also required (`require_cost`) and whether `estimated` is excluded (`measured_only`, cache rate); both flags can only tighten the result, never relax the four-column or provenance gate. No caller-supplied admission policy. `mixed` is an aggregate label only; never store it. The coverage check is delegated to `group.coverage()`; the label matches today's `aggregate_provenance` masking semantics (computed over all coverage-selected contributors, admitted or not).
- `ObservationGroup.add` gains per-row counters (not-admitted rows, unknown-provenance rows, estimated/measured presence, rows missing cost) so `qualify_usage` needs no second pass; leave exact naming to the implementer.
- Treat `ObservationGroup.subtotal` as an explicitly labeled audit operation (recommended: rename to `audit_subtotal` and gate inside `total()`), including when used to sort reports.
- **No new audit surface for dollars.** Per-provenance token and cost subtotals already live in `token_provenance[ptr].composition`; never add `cost_usd` to `ObservationGroup.channel_subtotals()` — it also feeds `CoverageGroup.channel_subtotals` and the ENH-3733 snapshot schema, which must stay byte-identical. State in the docs that dollars have no separate audit-subtotal surface.
- **Reason-code precedence** (first match wins): coverage (existing reasons) > `empty_selection` > `missing_token_component` > `unknown_provenance` > `unpriced_contributor` (cost figure) / `not_measured` (cache rate). `row_provenance` collapses unrecognized strings into `unknown`, so there is **no** separate `unrecognized_provenance` code. The cache rate keeps `unverified_usage` as its public `qualification_reason` for the non-measured case.
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
- `scripts/little_loops/cli/ctx_stats.py` — `_waste_provenance` reads `channel_subtotals`, `coverage`, `coverage_reason`, `provenance`, `tokens_total_missing`, `tokens_wasted_missing`, `waste_pct` from each waste row; any new reason/label must keep those keys in `_waste_provenance`. **Required fix**: the `tokens_total`/`tokens_wasted` entries use `known=events-missing` via `counted_entry`, so a `None` figure caused by unknown provenance (`tokens_*_missing == 0`) reports `available`; set `known=0` whenever the row's value is `None` (as the `waste_pct` entry already does) and surface `qualification_reason` [Agent 2 finding + 2026-10-04 review]
- `scripts/little_loops/cli/ctx_stats.py` — `_print_json` strips only `provenance` from `usage_by_model`; new audit-subtotal keys leak into the public JSON unless stripped/kept deliberately in `_print_json`; `/usage_by_model/totals/<col>` and `/usage_by_model/per_model/<model>/<col>` pointers from `_token_provenance` must keep resolving to numeric-or-null [Agent 2 finding]
- `scripts/little_loops/cli/ctx_stats.py` — `_cache_rate_provenance` composes reason prose from `coverage_reason`/`lag_reason`/`freshness` and `_STORED_USAGE_DIAGNOSTICS` ("ingested without qualified usage observations") carries the stored-absence strings; new `qualification_reason` codes (`empty_selection`, `missing_token_component`, `unknown_provenance`, `unpriced_contributor`, `not_measured`, in that precedence after coverage) must be defined in `_cache_rate_provenance` / `_compute_cache_rate_from_usage` without changing the existing four diagnostics [Agent 2 finding]
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
- `scripts/tests/test_enh3538_token_observations.py` — update in `TestSqlCompleteness.test_aggregate_usage` (`[(0, 0.0), (0, 0.0)]` case expects `input_tokens == 0` on NULL provenance) and `test_cost_attribution_omits_partial_attribute_keeps_complete_sibling` (expects sibling `gen_ai.usage.output_tokens == 0` beside an input-NULL row — conflicts with row-level admission; its intent is **reversed**, so rewrite it to assert every `gen_ai.usage.*` attribute is omitted for the group — do not weaken or delete it) [Agent 2 + 3 finding]
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
- New vocabulary + precedence test for the new reason codes (`empty_selection`, `missing_token_component`, `unknown_provenance`, `unpriced_contributor`, `not_measured`) — no existing test pins them; include an unrecognized-provenance string asserting it yields `unknown_provenance`; a document-wide invariant test (every JSON pointer whose value is `None` has `availability == "unavailable"`, across `usage_by_model`, `waste`, cache-rate pointers); selector tests for `channel=` exclusion from `audit_rows`/subtotals and `ValueError` on an unknown channel; a `qualification_reason` presence test on `aggregate_usage`/`cost_attribution`/`waste_attribution` rows; optionally add `("docs/reference/API.md", "qualify_usage", "ENH-3731")` to `scripts/tests/test_wiring_reference_docs.py` (substring-only gate; no existing gate covers selector signatures or CLI.md figure wording) [Agent 3 finding]
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

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Verified current anchors (2026-10-05 re-check): `token_provenance.py` `row_channel:69`, `row_provenance:77`, `ObservationGroup:114`, `aggregate_provenance:210`, `total:222`, `subtotal:231`, `entry:242`, `_META_KEYS:407`, `group_rows:302`; `usage.py` `select_usage_coverage:375`, `select_usage_observations:480`, `_read_groups:512`, `cost_attribution:530`, `waste_attribution:612`, `aggregate_usage:766`; `ctx_stats.py` `_aggregate_usage_events:226`, `_compute_cache_rate_from_usage:445`, `main_ctx_stats:1175`. No line drift against the issue text. `docs/ARCHITECTURE.md` changed since the last refine only for an unrelated sonnet-alias line (`360f6b373`); the `v20`/`v29`/`v53` `usage_events` rows are still present (lines 696/705/723).
- `REQUIRED_KEYS` is a **test constant** (`scripts/tests/test_enh3528_token_provenance.py:37`, asserted in `TestUsageAggregation.test_entry_shape`), not a symbol in `token_provenance.py`. The constraint on `ObservationGroup.entry` is the set of keys it emits today (`provenance`, `metric`, `scope_kind`, `observation_time_basis`, `availability`, `known_count`, `missing_count`, `composition`, `coverage`, plus conditional `hosts`/`channels`/`session_id`/`invocation_id`/`observed_from`/`observed_to`/`reason`); any new qualification metadata must be additive to that shape.
- Two `row_channel` sites exist in the selector: `usage.py:337` (per-group channel set inside `_classify_coverage`) and `usage.py:433` (store-wide `channels` feeding `ambiguous_cross_channel`, computed over the whole `host`/`session_id`-narrowed `rows`, before `since`/`require_run_id`). A `channel=` filter applied to `rows` after the cursor→dict conversion and before `grouped` is built covers both; `row_channel` is Python-only, so it cannot be a SQL `channel =` predicate (raw column is NULL for legacy rows, which `row_channel` maps to `transcript` when a session ID exists).
- `issue_history/agent_quality.py:_usage_totals` (`:305`, filter at `:314`) already scopes transcript post-selection with the raw-column predicate `session_id is not None and channel in (None, "transcript")`. That predicate is equivalent to `row_channel == "transcript"` for rows with a session ID, but runs **after** the store-wide gate has classified coverage — the exact gap `channel=` closes. It is ENH-3732's call site, not migrated here.
- `session_store/queries.py:_snapshot_usage_selection` (`:354`, calls `select_usage_coverage` at `:363`) is a third selector consumer beyond `ctx_stats`/`usage.py`/`agent_quality`; it must remain identical with `channel=None` (ENH-3733).
- `ctx_stats._compute_cache_rate_from_jsonl` (`:342`, called at `:1223`) is a **separate non-stored cache-rate path** with its own eligible-subset logic: it emits no `source`/`coverage`/`qualification_reason` and always reports provenance `unknown`, yet reaches the shared `_render` footer ("based on N eligible record(s); M excluded (missing usage component)") and `counts["hit_rate_pct"]`. It is not among the issue's named consumers; removing eligible-subset wording from the stored path must not silently change this path's rendering, and the Freshness-contract line ("characterize text and JSON behavior before extending to other hosts") is the governing scope boundary.
- `ObservationGroup.aggregate_provenance(column)` (`:210`) is built from `set(components[column].by_provenance)`; `_Component.add` registers a provenance slot before checking for a NULL value, so a row whose value for that column is NULL still contributes its provenance label (count 0). `entry()` filters zero-count slots out of `composition`, `aggregate_provenance` does not. `qualify_usage` computes its label over **all coverage-selected contributors** (admitted or not), so it cannot treat `aggregate_provenance` as an already-admission-filtered signal.
- Today `aggregate_usage`/`cost_attribution` gate columns individually via `ObservationGroup.total` (a column is `None` only when some contributor lacks *that* column), so a partial row's present components already surface as numbers beside a `None` for its NULL column; only `ctx_stats._aggregate_usage_events` (via `subtotal`, no missing/provenance gate) publishes the partial sum as the canonical figure. Row-level admission changes `aggregate_usage`/`cost_attribution` behavior too (present columns of a partial row become unavailable), which is what `test_enh3538_token_observations.py::test_cost_attribution_omits_partial_attribute_keeps_complete_sibling` pins today.

## Program Design

### Types

- `UsageQualification` — new immutable (`@dataclass(frozen=True)`) in `scripts/little_loops/token_provenance.py`; carries eligibility, provenance label (`measured`/`estimated`/`mixed`/`unknown`), bounded reason code, audit known/missing counts and rejected-contributor count.
- `ObservationGroup` (`token_provenance.py`, plain class) — today accumulates every row into every `AGGREGATE_COLUMNS` component with no row admission; a row missing one token column still feeds the other three.
- `CoverageGroup` / `CoverageSelection` (`history_reader/usage.py`, both `frozen=True`) — `channel=` scope changes which rows reach them, not their fields.
- Coverage values stay plain `str`: `non_overlapping`, `overlap_unresolved`, `unknown`. Provenance literals `"measured"`/`"estimated"`/`"unknown"` have no module constant (a separate `TokenProvenance` Literal lives in `subprocess_utils.py`).

### Signatures

- `qualify_usage(group: ObservationGroup, *, require_cost: bool = False, measured_only: bool = False) -> UsageQualification` — new, `token_provenance.py`; pure over group state.
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

- **Terms**: *admitted* = all four `TOKEN_COLUMNS` non-NULL; *eligible* = admitted and provenance `measured`/`estimated`. Use these two words only in this sense.
- **Row admission (fixed, first)**: a row is admitted only if all four `TOKEN_COLUMNS` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) are non-NULL. Missing `cost_usd` alone does not reject a row — it makes cost unavailable. A rejected row stays in `audit_rows` and in audit subtotals.
- **Provenance**: `measured` and `estimated` are recognized; NULL, `unknown` and unrecognized strings all read as `unknown` through `row_provenance`. Aggregate label is `measured` if every contributor is measured, `estimated` if every contributor is estimated, `mixed` if both occur, `unknown` if any contributor is `unknown`. `mixed` is never stored.
- **Cache rate**: requires every contributor eligible and `measured` (`measured_only=True`); denominator is `input + cache_read + cache_creation`; zero denominator is unavailable. It may only tighten the base qualification. Existing eligible-subset behavior in `_compute_cache_rate_from_usage` (a rate over only complete rows, gated on `input_tokens` provenance alone) is what this replaces. Operand fields stay measured-only; `counts["hit_rate_pct"]` keeps its `{"known", "missing"}` shape with `missing` = rejected-contributor count.
- **Waste (resolved: reading B)**: keep `input_tokens + output_tokens`, the `_WASTED_RUN_PREDICATE` subset and `waste_pct` only when `tokens_total` is nonzero. One per-loop qualification over the full joined population (admission **and** provenance gate) governs `tokens_total` and `tokens_wasted` together; `tokens_wasted` is not qualified on the wasted-run subset alone (the coverage gate, provenance label and `waste_pct` are all per-loop). Fixtures that need canonical waste numbers must set `provenance='measured'` explicitly (`_populate_waste_run` / `_WASTE_CORE_EXPECTED` flip to `None` otherwise) — do not weaken the gate.
- **Availability** is derived from the qualified value (see Expected Behavior); `counted_entry`'s count-only derivation must not be allowed to report `available` for a `None` figure.
- **Empty selection** is unavailable; a qualified observed zero is zero.
- **Reason codes**: bounded vocabulary extends the existing coverage reasons (`unverified_cross_channel_identity`, `live_replay_join_unproven`, `cross_channel_join_unproven`, `codex_live_scope_unknown`, `codex_live_identity_unverified`, `rollout_request_identity_unverified`) and `ctx_stats` codes (`unverified_usage`, `no_store`, `unreadable_store`, `session_not_ingested`, `ingested_without_usage`). New codes (inline literals, no registry): `empty_selection`, `missing_token_component`, `unknown_provenance`, `unpriced_contributor`, `not_measured`. Precedence, first match wins: coverage > `empty_selection` > `missing_token_component` > `unknown_provenance` > `unpriced_contributor` (cost) / `not_measured` (cache rate). There is deliberately no `unrecognized_provenance` code (`row_provenance` collapses it into `unknown`). The cache rate keeps `unverified_usage` as its public `qualification_reason` for the non-measured case. `aggregate_usage`/`cost_attribution`/`waste_attribution` rows expose the code via an additive `qualification_reason` key.
- **`channel=` scope**: resolve `row_channel(row)` for every fetched row before grouping and before `ambiguous_cross_channel` is computed (currently store-wide over the `host`/`session_id`-narrowed rows: `live` present, a non-`live` channel present, and some row without verified identity); `channel=None` leaves that gate exactly as is. `since`/`require_run_id` stay post-classification. Out-of-channel rows are dropped from every output (`audit_rows`, `selected_rows`, group subtotals); an unrecognized channel raises `ValueError`. The filter is Python-side only (`row_channel` has no SQL equivalent for legacy NULL rows). No in-scope caller passes `channel=` (only ENH-3732's `_usage_totals` will), so it is verified by direct selector-level tests and lands as its own first commit.
- **Audit surfaces**: no new audit-dollar surface (see Proposed Solution); `usage_by_model` audit subtotals, if published, go in a **top-level sibling** (e.g. `usage_by_model.audit`), not nested inside `per_model[model]`, so consumers iterating per-model columns are unaffected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Waste admission — resolved reading (the wire pass left this open).** `waste_attribution` today never consults provenance or the cache/cost columns for admission: it requires only `input_tokens` and `output_tokens` non-NULL per row and gates `tokens_total`/`tokens_wasted` on `slot["group"].coverage() == "non_overlapping"`; provenance only feeds the reported `provenance` label. Two readings of "admit the full joined population" are possible: (A) row admission only (four `TOKEN_COLUMNS` non-NULL), or (B) row admission plus the fail-closed provenance gate. The recorded decision (parent Decision 1: NULL/unknown provenance is audit-only for canonical figures; Expected Behavior: "unrecognized stored provenance fails closed like explicit unknown") implies B for waste, and the figure table distinguishes cache rate only by adding *measured-only* (excluding `estimated`), not by being the sole provenance-gated figure. Under B the `_populate_waste_run` fixture (input 100, output 20, cache 0/0, NULL provenance, no session/host) flips `_WASTE_CORE_EXPECTED` `tokens_total`/`tokens_wasted`/`waste_pct` to `None`; under A it is unchanged. Whichever reading lands, the `tokens_total_missing`/`tokens_wasted_missing`/`waste_pct` keys and the `test_enh3543_usage_coverage.py` unresolved-overlap controls (all three figures `None`) must hold, and fixtures that need canonical waste numbers must set `provenance='measured'` explicitly rather than weakening the gate.
- **`unverified_usage` is a `ctx_stats` code, not a coverage reason.** `_compute_cache_rate_from_usage` emits `qualification_reason` of only `"unverified_usage"` (coverage `non_overlapping` but `input_tokens` provenance not `measured`) or `None`; unresolved/unknown coverage is reported via `coverage_reason`, and the four stored-absence diagnostics (`no_store`, `unreadable_store`, `session_not_ingested`, `ingested_without_usage`) travel as the tuple's second element via `_STORED_USAGE_DIAGNOSTICS` (`ctx_stats.py:549`). No shared reason-code constant or enum exists; every code is an inline literal (`usage.py:_classify_coverage`/`select_usage_coverage`, `_provenance_fields` fallback `coverage_unverified`, `ctx_stats.py`). New codes extend that inline-literal convention; there is no registry to add to.
- **Current cache-rate gate vs the replaced behavior.** `reportable = coverage == "non_overlapping" and group.aggregate_provenance("input_tokens") == "measured"`; rows with all of input/cache-read/cache-creation present count as `eligible_events` and the rest as `excluded_events` (`counts["hit_rate_pct"] = {"known": eligible, "missing": excluded}`); `output_tokens` is never read. The `{"known": N, "missing": M}` count shape is asserted by `test_enh3656_stored_cache_rate.py` and must keep resolving, with `missing` now carrying the rejected-contributor count.

## Compatibility Consequences

_Added 2026-10-04 from a pre-implementation review (`/ll:advise`, verified against the local `.ll/history.db`)._

On a real store the new gate makes most consumption figures unavailable, by design of the recorded decision — not a bug to fix here, but it must be documented concretely (CLI.md `### ll-ctx-stats`, API.md, CHANGELOG at release prep):

- Local store snapshot: 517,614 `usage_events` rows; 512,646 (~99%) are `transcript` rows with `provenance='unknown'`; only 2 rows are missing a token column. All-history totals and per-model figures are already `None` today via the store-wide ambiguity gate, and stay `None` after ENH-3730 narrows it, because any `unknown` contributor blanks the aggregate.
- 3,742 of 4,040 `claude-sonnet-5-5` rows have NULL stored `cost_usd` (pre-BUG-3696); with no read-time repricing, cost is unavailable for nearly every aggregate containing them.
- **Open question (unverified)**: whether a full rebuild/refresh re-derives `measured` provenance and stored cost from `raw_events` for these rows. `writers.py` keeps rows with an `observation_key` conflict at `unknown` (retained for audit), so the answer is not obvious. The implementer must check this and state the answer in the docs; if rebuild cannot re-qualify them, historical data stays audit-only permanently. **File a follow-up issue** for a provenance/cost re-qualification backfill (out of scope here — derive-algorithm changes are excluded).
- Docs must state: unavailable figures are expected on stores with legacy/live `unknown` rows; the reason code names the blocker; dollars have no separate audit surface (use `token_provenance[ptr].composition`).

## Implementation Steps

0. **Commit order**: land `channel=` on both selectors first (own commit, selector-level tests only; `channel=None` byte-identical for `agent_quality` and the snapshot build), then the qualification core, then consumers, then docs.

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

- [ ] Implementation/tests/docs match the recorded policy: legacy absent/NULL audit-only, complete estimates labeled numeric consumption, cache rates measured-only; compatibility consequences documented per **Compatibility Consequences** (real-store numbers, rebuild re-qualification answer, follow-up issue filed).
- [ ] Availability metadata is value-derived: no pointer whose value is `None` reports `available`/`partial` (document-wide invariant test), including `_waste_provenance` `tokens_total`/`tokens_wasted`; `aggregate_usage`/`cost_attribution`/`waste_attribution` rows carry an additive `qualification_reason`.
- [ ] Waste is qualified once per loop over the full joined population (admission + provenance) for both `tokens_total` and `tokens_wasted`; reason codes follow the documented precedence with no `unrecognized_provenance` code; `cost_usd` is not added to `channel_subtotals()`.
- [ ] Matrix covers measured/estimated/explicit unknown/legacy NULL, mixed aggregates, unrecognized provenance, each missing token component, complete tokens × non-overlapping/unknown/unresolved coverage, measured Claude/Codex controls, the representative remaining-host partial row, the measured-partial numeric-cost probe and eligible+audit-only mixes.
- [ ] Every selected contributor satisfies each figure's prerequisites or the full canonical figure is unavailable with a bounded reason; silently dropping an in-filter ineligible row cannot make a total or rate appear qualified; numeric stored cost cannot bypass token/provenance prerequisites; empty selection is unavailable while a qualified observed zero is zero.
- [ ] A complete measured observation plus a coverage-selected observation missing input, cache-read or cache-creation makes the session cache rate unavailable, with audit subtotals, missing counts and reason preserved.
- [ ] `channel="transcript"` on both selectors reconciles transcript and legacy NULL/absent-channel rows with a session ID before coverage analysis; excluded live/rollout counterparts cannot change values or qualification and are absent from `audit_rows`/subtotals; an unrecognized channel raises `ValueError`; default unscoped coverage still blocks unresolved counterparts; `since`/run filters cannot certify coverage; selected populations/counts (including audit-only rows) stay intact.
- [ ] `ll-ctx-stats` all-history/per-model JSON and text show canonical values only when qualified, with distinct labeled audit subtotals and valid provenance pointers; metadata never says `available` for an unavailable field; qualified tokens with missing pricing stay canonical while cost is unavailable; dollars are visibly estimates.
- [ ] Existing Claude/Codex text and JSON retain qualified as-of values and freshness diagnostics after append/source loss; stale/unknown never described as current; failed derive is unavailable/unknown, not a fresh zero.
- [ ] Incremental derive, full rebuild and repeated refresh preserve the policy and cannot promote unknown evidence.
- [ ] Publication gate recorded: ENH-3671–3676 cite this shared contract and pass qualification tests before enabling production derivation of newly recognized usage rows; because source, snapshot and quality readers all discover `usage_events`, that gate requires **ENH-3731, ENH-3732 and ENH-3733 together**. Capture/adapter/raw-retention work can proceed independently.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Out of scope:** snapshot export/dashboard (ENH-3733), quality derive status/baselines/workspace (ENH-3732), ENH-3730's store-wide ambiguity redesign, provider capture and adapters, derive-algorithm or source-freshness changes, component-level measured exceptions, pricing fallback, a provenance/cost re-qualification backfill for legacy `unknown`/NULL-cost rows (follow-up to be filed), any audit-dollar surface, adding `cost_usd` to `channel_subtotals()`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-04_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- ~~Waste admission is stated two ways~~ — **resolved 2026-10-04**: reading B, one per-loop qualification (see Decision Rules → Waste).
- ~~Audit-subtotal keys public in `usage_by_model`~~ — **resolved 2026-10-04**: top-level sibling if published; no audit-dollar surface. Still left to the implementer: which module `qualify_usage` is re-exported from in `history_reader.__all__`.
- `ctx_stats._compute_cache_rate_from_jsonl` is a separate non-stored cache-rate path that shares the `_render` eligible-subset footer; removing that wording for the stored path must not change its rendering.

### Outcome Risk Factors
- Moderate per-site complexity: row-level admission is a contract change across `ObservationGroup`, `aggregate_usage`, `cost_attribution`, `waste_attribution` and `ctx_stats` (shared state, cross-module), not a mechanical edit.
- Broad change surface: ~6 selector/subtotal callers plus ~8 existing test files whose NULL-provenance fixtures flip to unavailable; `channel=None` must stay behavior-identical for the out-of-scope `agent_quality` and snapshot consumers.
- New bounded reason-code vocabulary (`empty_selection`, `missing_token_component`, `unknown_provenance`, `unpriced_contributor`, `not_measured`) has no registry or existing test to anchor it (a vocabulary/precedence test is now specified).

## Session Log

- `/ll:confidence-check` - 2026-10-05T03:37:45 - `4504af05-93f3-458d-afca-2878c39c662b.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T03:32:20 - `5b873f1f-917c-4a97-9f4f-58c77a829f91.jsonl`
- `/ll:wire-issue` - 2026-10-05T03:23:32 - `e79ced76-329a-41b8-acda-11c309df53b4.jsonl`
- `/ll:refine-issue` - 2026-10-05T03:13:46 - `ca3640c2-fc5f-47d0-9305-872e41fc20ff.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2

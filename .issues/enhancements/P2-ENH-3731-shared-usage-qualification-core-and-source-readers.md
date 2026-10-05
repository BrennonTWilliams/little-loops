---
id: ENH-3731
type: ENH
title: Shared usage qualification core and source readers
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
verify_verdict: VALID
blocked_by:
- BUG-3735
blocks:
- ENH-3732
- ENH-3733
relates_to:
- ENH-3748
- BUG-3696
- ENH-3543
- ENH-3528
- ENH-3730
- ENH-3746
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
size: Large
---

# ENH-3731: Shared usage qualification core and source readers

## Summary

Add the shared qualification contract for canonical stored-usage figures and route the source readers through it. This child owns `qualify_usage`/`UsageQualification` with fixed row admission and the source-side consumers (`aggregate_usage`, `cost_attribution`, `waste_attribution`, `ll-ctx-stats` all-history/per-model and the stored cache-rate path). Sibling children ENH-3732 (quality) and ENH-3733 (snapshot/dashboard) consume this contract and are blocked by this issue. The logical `channel=` selector scope was split to ENH-3748 on 2026-10-05.

**Program Design → Decision Rules is the single normative contract.** Expected Behavior summarizes outcomes, Proposed Solution describes the implementation shape, and Acceptance Criteria name what to verify; on any apparent conflict, Decision Rules win.

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. The parent's recorded **Decision (2026-10-04, `/ll:decide-issue`, commit `01747bb96`)** is authoritative and is not reopened here:

1. Legacy NULL provenance is conservative: audit-only, exactly like explicit `unknown`; no provenance-presence column or compatibility label.
2. Complete `estimated` rows are admitted in general consumption reports with an explicit `estimated`/`mixed` label; cache rate stays measured-only; quality trends require all-measured composition.
3. Decision 4 (Option A, refined): `channel=` scope on the selectors — now implemented by ENH-3748; the store-wide ambiguity gate and ENH-3543's contract are unchanged (narrowing it belongs to ENH-3730).

## Current Behavior

`ObservationGroup.total` gates on coverage and component presence; `aggregate_usage` can return numeric components with unknown provenance. `ctx_stats._aggregate_usage_events` publishes `ObservationGroup.subtotal` as canonical `usage_by_model.totals` with cost availability `available`. `waste_attribution` has its own coverage-only numeric gate. A partial row (input 10, output 2, cache-read 4, cache-creation NULL) with unknown **or measured** provenance and stored cost $1 publishes canonical input/output/cache-read/cost from source readers. `_compute_cache_rate_from_usage` separately requires measured usage and a complete denominator, computed over a complete subset of selected rows with coercing `_known_int`.

## Expected Behavior

Outcome summary; see Decision Rules for the normative rules.

- A canonical stored-usage figure is published only when every in-population contributor meets that figure's prerequisites; otherwise its value is `None` with a bounded figure reason. Missing components never become zero, a stored numeric `cost_usd` cannot qualify an audit-only row, empty selection is unavailable and a qualified observed zero is zero.
- Tokens and cost qualify independently: a missing/invalid cost never blanks qualified tokens. All four token columns, including the `gen_ai.usage.*` OTel attributes, qualify together.
- Metadata is truthful: availability follows the published value, while audit known/missing/invalid/rejected counts describe the evidence even when the figure is unavailable.
- Labeled audit detail stays in the existing surfaces (`token_provenance[ptr].composition`, `channel_subtotals`). Existing public keys remain; no new keys appear inside `usage_by_model.totals`/`per_model[model]`.
- **Freshness contract**: qualification of a stored observation and completeness of the current source are separate. Preserve qualified historical/as-of Claude/Codex figures with existing freshness, lag reason and as-of metadata, subject to BUG-3735's overlap verdict; stale/unknown cannot read as current. A cache rate over only the complete subset of selected observations is not permitted. Characterize text and JSON behavior before extending to other hosts.
- `ll-ctx-stats` all-history/per-model JSON keeps its existing public numeric keys, shows canonical values only when qualified, and never marks metadata `available` for an unavailable canonical field. Qualified tokens with missing model pricing stay canonical while cost is unavailable.
- Qualification is read-time policy: no history migration, derive-version bump, automatic rebuild or refresh. Incremental replay, full rebuild and unchanged tail refresh cannot infer producer qualification from legacy payload shape or stored numeric cost. Explicit re-ingestion from a verified original source can acquire new producer evidence through the existing `refresh_raw_events` workflow; that is distinct from replay and remains outside this implementation's mutations.

## Proposed Solution

- **Result type.** A small immutable `UsageQualification` (fields in Program Design → Types) factored from the `ObservationGroup`/coverage chokepoint in `token_provenance.py`.
- **`qualify_usage(group, *, require_cost=False, measured_only=False)`** — a pure function of group state. It always enforces row admission and the provenance gate first; `require_cost` and `measured_only` can only tighten the result. No caller-supplied admission policy. Coverage is delegated to `group.coverage()`. It returns no `zero_denominator`; figure builders add that after base qualification succeeds.
- **Accumulation.** `ObservationGroup.add` gains per-row counters sufficient for every `require_cost`/`measured_only` combination, with numeric validation before arithmetic, so `qualify_usage` needs no second pass and counts a multiply rejected row once. The result snapshots counts; a later `group.add()` cannot mutate it. Internal accumulator names are an implementation choice.
- **Canonical vs audit operations.** `ObservationGroup.total(column)` and `entry(column)` call `qualify_usage(group, require_cost=(column == COST_COLUMN))` — general-consumption eligibility, never `measured_only`. Rename `subtotal` → `audit_subtotal(column)`: the sum of valid values, `None` when no valid contributor, with no coverage/provenance gate; all canonical gating lives in `total()`. Its four call sites: sort keys in `aggregate_usage` (`cost_usd`) and `cost_attribution` (`input_tokens`) intentionally sort by audit sum (unresolved-coverage groups therefore sort by their audit sum instead of last — confirm no test pins that order); the published `totals`/`per_model` values in `ctx_stats._aggregate_usage_events` switch to `total()`.
- **Shared constants** beside `qualify_usage` in `token_provenance.py`: `USAGE_QUALIFICATION_POLICY_VERSION = 1` (carried as `UsageQualification.policy_version`; ENH-3733 exports that result's version, not a second literal; intentional changes to admission/provenance/figure prerequisites/reason precedence bump it together with the shared behavioral matrix; coverage-policy and export-allowlist versions stay separate) and `USAGE_QUALIFICATION_REASONS` (`frozenset[str]`, contents in Decision Rules).
- **Source consumers.** Apply qualification in `aggregate_usage`, `cost_attribution`, `waste_attribution`, `ctx_stats._aggregate_usage_events` and `_compute_cache_rate_from_usage`. Tokens qualify with `require_cost=False` and cost separately with `require_cost=True`; snapshot and other consumers follow the same split.
- **Stored cache reader.** Compute one `qualify_usage(group, measured_only=True)` over `selection.audit_rows` and reuse it for the rate, every operand and their metadata; never recertify operands through general-consumption `total`/`entry`. Replace coercing `_known_int` use and the complete-subset accumulator with strict validated arithmetic; keep `_known_int` and the separate direct-JSONL reader (`_compute_cache_rate_from_jsonl`) unchanged.
- **Metadata helpers.** Fix `_waste_provenance` and `_cache_rate_provenance` locally: build truthful count metadata with `counted_entry`, then set `availability` from the published value and attach the figure reason/invalid/rejected counts. Do not change `counted_entry`'s default behavior for unrelated callers.
- Keep snapshot (`queries.py`) and quality (`agent_quality.py`) untouched; they are ENH-3733 and ENH-3732. Selectors are untouched here (`channel=` is ENH-3748; acquisition/output ordering is BUG-3735).

## Integration Map

### Files to Modify

- `scripts/little_loops/token_provenance.py` — `ObservationGroup` qualification, immutable result/count types, shared policy-version/reason constants, `total`/`entry` qualification, `audit_subtotal` rename, strict numeric accumulation.
- `scripts/little_loops/history_reader/usage.py` — qualification in `aggregate_usage`, `cost_attribution`, `waste_attribution`, `_provenance_fields`; no selector changes.
- `scripts/little_loops/history_reader/__init__.py` — re-export `qualify_usage` and `UsageQualification` directly from `token_provenance`, add both to `__all__`, update the module docstring.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_compute_cache_rate_from_usage`, `_waste_provenance`, `_cache_rate_provenance`, `_print_json`, `_token_provenance`, `_render`, `main_ctx_stats`.

_Wiring pass added by `/ll:wire-issue` (file-specific instructions; rules live in Decision Rules):_
- `token_provenance.py` — `_META_KEYS` gains `qualification_reason`, `invalid_count` and `rejected_contributors` so `same_metadata` cannot merge figures with different qualification evidence; keep ignoring free-form `reason`/`metric`; absent new keys compare equally for unrelated callers. Keep every key `ObservationGroup.entry` emits today (the test constant `REQUIRED_KEYS` pins a subset).
- `token_provenance.py` — `channel_subtotals()` stays numeric, valid-value only and token-only (never `cost_usd`); it is consumed by `_provenance_fields` and `_compute_cache_rate_from_usage`.
- `usage.py` — `_provenance_fields` reads `aggregate_provenance`/`coverage`/`coverage_reason`/`channel_subtotals`; add token and cost qualification metadata deliberately at their consumers. `aggregate_usage`/`cost_attribution` gain independent `qualification_reason`/`cost_qualification_reason` and additive `<col>_invalid` counts; a shared helper must not apply the cost requirement to waste.
- `usage.py` — `waste_attribution` keeps its hand-rolled `total/total_missing/wasted/wasted_missing` accumulator beside its per-loop `ObservationGroup`; add the full-joined-population qualification and preserve `tokens_total_missing`/`tokens_wasted_missing`/`waste_pct` keys.
- `ctx_stats.py` — `_waste_provenance`: replace the ratio's count-reset workaround with denominator-pair evidence; attach base `qualification_reason` to total/wasted pointers and `waste_pct_qualification_reason` to the ratio pointer.
- `ctx_stats.py` — `_print_json` strips only `provenance` from `usage_by_model`; keep `/usage_by_model/totals/<col>` and `/usage_by_model/per_model/<model>/<col>` pointers resolving to numeric-or-null and leak no new keys.
- `ctx_stats.py` — `_cache_rate_provenance` passes the actual stored coverage to `counted_entry` for the three operands and the rate (not the `non_overlapping` default), retains coverage/freshness prose and `_STORED_USAGE_DIAGNOSTICS`' four absence diagnostics, and preserves stored audit counts instead of converting known observations into missing ones.
- `ctx_stats.py` — `_render` cache-rate branch ("unavailable (coverage unresolved)" / "unavailable (usage unverified)" / "no usage observed" / `based on … eligible record(s); … excluded (missing usage component)` footer) encodes the eligible-subset behavior being replaced for the stored path only; the direct-JSONL path shares that footer and must render unchanged. `_render` and `main_ctx_stats` distinguish coverage, missing/invalid component, unverified provenance and zero-denominator reasons; stored waste/cache text exposes the figure-specific bounded reason in a footnote, including waste's ratio reason. A qualified zero-denominator record must not emit the "producer usage identity or components are unverified" stderr line; a qualified current Codex run still emits empty stderr.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `writers.py`, `claude_usage.py` (`claude_transcript_contract`), `usage_refresh.py` (`refresh_raw_events`) — read-only; incremental/rebuild/refresh policy tests only. Ordinary replay uses the persisted producer marker; tail refresh ignores already-ingested records; explicit verified-source re-ingestion can acquire a new marker and invalidates old derived usage before rebuild.
- `scripts/little_loops/issue_history/agent_quality.py`, `issue_history/quality_regressions.py` — untouched (ENH-3732; ENH-3748 adds the selector scope it will use).
- `scripts/little_loops/session_store/queries.py`, `templates/dashboard.llat/template.html.j2` — untouched (ENH-3733).
- `scripts/little_loops/cli/__init__.py` (re-exports `main_ctx_stats`), `fsm/cost_graph.py` (docstring pointer to `aggregate_usage()`) — no change.
- Gate-consumer sweep: no loop YAML, hook, skill, command or agent reads `usage_by_model`, `cache_hit_rate_pct`, `token_provenance`, `aggregate_usage`, `cost_attribution` or `waste_attribution`; the `ll-ctx-stats` JSON contract is consumed only by CLI.md prose and tests.

### Tests

**Existing tests that will break (NULL provenance is the default fixture value, so canonical-value assertions flip to unavailable — update, do not delete):**
- `scripts/tests/test_enh3528_token_provenance.py` — `TestUsageAggregation.test_null_components_are_missing_not_zero`, `test_partial_subtotal_is_labeled` (becomes a labeled audit subtotal), `test_known_zero_stays_zero`, `test_provenance_composition`; rewrite `TestHistoryReaderNullContract.test_ctx_stats_partial_vs_reader_none_on_same_fixture` (the contrast is removed). Keep keys in `test_aggregate_usage_none_on_any_missing`, `test_waste_zero_denominator`, `TestCoverage.test_waste_propagates_overlap_and_none_on_missing`, `TestJsonDocument.test_waste_pointers_resolve`, `test_all_pointers_resolve_and_exclude_byte_fields`; `test_entry_shape` pins `REQUIRED_KEYS`; `TestHostAttribution.test_live_row_null_basis_keeps_invocation_host` pins `reason == "codex_live_scope_unknown"`.
- `scripts/tests/test_cli_ctx_stats.py` — `TestAggregateUsageEvents.test_aggregates_by_model_with_totals` (also the priced-subset-sum case); `_populate_waste_run` / `_WASTE_CORE_EXPECTED` used by `TestAggregateWaste.test_present_rows_returned` and `TestMainCtxStatsWasteSection.test_json_mode_waste_present`: canonical-number fixtures set `provenance='measured'` explicitly; unknown-provenance fixtures assert unavailable values with reasons.
- `scripts/tests/test_history_reader_usage.py` — `TestCostAttribution.test_group_by_invocation_id_sums_match_raw_totals`, `test_group_by_vendor`, `test_group_by_run_id`, `TestUsageEventReaders.test_aggregate_usage_by_model` / `test_aggregate_usage_by_session`; re-check `TestWasteAttribution` tests built on `_seed_run`; check sort-order assertions after the `audit_subtotal` rename.
- `scripts/tests/test_enh3538_token_observations.py` — `TestSqlCompleteness.test_aggregate_usage`; `test_cost_attribution_omits_partial_attribute_keeps_complete_sibling` has its intent **reversed**: rewrite it to assert every `gen_ai.usage.*` attribute is omitted for the group (do not weaken or delete it).
- `scripts/tests/test_enh3656_stored_cache_rate.py` — `test_missing_native_id_is_unverified_and_partial_or_zero_is_unavailable` (keep `qualification_reason == "unverified_usage"`), `test_captured_duplicate_uuids_correct_to_two_native_requests` / `test_pair_filter_excludes_same_id_other_host_and_legacy_attribution` (`hit_rate_pct == {"known": 2, "missing": 0}` count semantics).

**Controls that must keep passing unchanged (measured rows):**
- `scripts/tests/test_enh3543_usage_coverage.py` — `test_live_and_stored_rollout_overlap_stays_audit_only_across_filters`, `test_waste_rates_unavailable_when_run_row_has_rollout_counterpart`, `test_old_rollout_and_live_only_scope_are_unknown` (reasons `live_replay_join_unproven`, `rollout_request_identity_unverified`, `codex_live_scope_unknown`).
- `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` — `test_current_codex_rollout_uses_selected_stored_requests_and_host_pair` (rate 78, measured), `test_live_rollout_overlap_is_audit_only_for_ctx_stats`, `test_old_codex_rollout_is_unknown_but_auditable`, `test_codex_cli_uses_latest_selected_stored_session_and_clean_json` (`output.err == ""`).
- `scripts/tests/test_enh3549_codex_usage_refresh.py` — the `coverage == "unknown"` freshness case.
- `scripts/tests/test_usage_selection_chokepoint_gate.py` — no new SQL is added here; a new SQL helper would need an allowlist entry.

**Policy tests to extend (cannot promote unknown ingest-time evidence):**
- `scripts/tests/test_enh3534_host_usage_dispatch.py` — extend `test_opencode_shape_rebuild_preserves_unknown_provenance` to a measured/unknown pair across rebuild.
- `scripts/tests/test_session_store_incremental_usage.py`, `test_session_store_usage_refresh.py`, `test_session_store_lifecycle.py`, `test_enh3678_rebuild_derive_gate.py` — incremental/refresh/rebuild policy-preservation cases.

**New tests:**
- **Fixtures.** Reuse `_insert(db, **row)` in `test_enh3528_token_provenance.py` for the provenance × missing-column matrix and `TestCoverage._group(rows)` for DB-free `qualify_usage` unit tests (both file-local — copy or hoist). Explicit-NULL inserts follow the raw `INSERT INTO usage_events(...)` pattern in `test_enh3543_usage_coverage.py`. `estimated`/`mixed` need synthetic inserts on **transcript or live** channels (a Codex rollout row with non-measured provenance is coverage `unknown` by design; add one such row as a control asserting `coverage_unknown`).
- **Matrix.** Measured/estimated/explicit unknown/legacy NULL, mixed measured+estimated, unrecognized provenance, each missing token component, complete tokens × non-overlapping/unknown/unresolved coverage; measured Claude/Codex controls; a representative remaining-host partial row; the measured-partial numeric-cost probe; aggregates mixing eligible and audit-only contributors; out-of-window unknown provenance alone does not taint a qualified window while out-of-window overlap still does.
- **Shared contract.** Immutable-result snapshots after subsequent `group.add`; per-component known/missing/invalid partition; multiply rejected rows counted once; all flag combinations; insertion-order-independent reasons; coverage diagnostic prose never enters bounded codes; empty tokens and empty cost each give `empty_selection`; `2**53 + 1` token precision; direct-mapping boolean and persisted negative/fractional/non-finite values beside one valid sibling. Cost permutations `[1e16, 1.0, 1.0]`, two `1e308` costs, and `sys.float_info.max` plus three `math.ulp(sys.float_info.max) / 4` costs: stable qualification/overflow, preserved counts, finite audit serialization, the same finalized total in value and composition consumers (independently rounded provenance subtotals need not sum bit-for-bit to the total).
- **Vocabulary/invariant.** `USAGE_QUALIFICATION_REASONS` membership and precedence; unrecognized provenance yields `unknown_provenance` (shared) and `unverified_usage` (stored-cache pointers). A document-wide stored-usage invariant (scope in Decision Rules) checks value/availability/coverage/figure-reason agreement and truthful counts across `usage_by_model`, `waste` and stored-cache pointers. `same_metadata` distinguishes the three new keys while preserving its free-form-reason compatibility test. Optionally add `("docs/reference/API.md", "qualify_usage", "ENH-3731")` to `scripts/tests/test_wiring_reference_docs.py`.
- **Source figures.** Complete measured tokens with NULL/invalid cost keep token values and token reason `None` while cost is unavailable with its own reason; all four OTel token attributes disappear together after any token failure. Cache: missing-output row; valid measured sibling plus unresolved audit sibling; strict direct-mapping values; truthful counts despite unavailable values; compatibility mapping; the same complete estimated fixture yields canonical estimated consumption and unavailable stored-cache operands/rate; all four cache-pointer coverage fields equal the top-level selection status. Waste: observed zero denominator, positive denominator with zero wasted runs, malformed non-wasted pairs, NULL-plus-invalid pairs, missing-cache-only rejection.
- **Freshness.** Failed derive is unavailable/unknown, not a fresh zero — extend `test_enh3656_stored_cache_rate.py::test_stale_append_and_unknown_tail_never_report_fresh` / `test_missing_cursor_after_refresh_is_unknown`.
- **Recovery.** `test_refresh_recovers_stripped_usage_and_rebuild_is_stable` in `test_session_store_usage_refresh.py` keeps passing; add a legacy-NULL-marker replay/unchanged-tail-refresh case that preserves `unknown` despite numeric rebuilt cost. No test enforces permanent unknown after new verified source evidence.
- **Ingestion.** The captured all-zero Claude record still yields `ingested_without_usage`; exercise the observed-zero/zero-denominator contract with synthetic measured observations, not by changing provider admission.

### Documentation

End-user docs (`docs/reference/`, `docs/guides/`) describe behavior only — never this repository's local store counts (audience gate `test_docs_audience_gate.py`).

- `docs/reference/CLI.md` `### ll-ctx-stats` — rewrite the "Partial totals" bullet (contradicts the audit-subtotal model); update the stored cache-rate paragraph (all contributors admitted and measured), the provenance-label bullet (`estimated`/`mixed` consumption labels; dollars are API list-price estimates; numeric cost cannot qualify an audit-only row), the "JSON corrections" bullet and the `--json` `waste` row shape; the "Cache figures" bullet is already stale vs the Codex cutover. State that unavailable figures are expected on stores with legacy/live `unknown` rows, the reason code names the blocker, dollars have no separate audit surface (use `token_provenance[ptr].composition`), and ordinary replay differs from explicit verified-source recovery.
- `docs/reference/API.md` — new section for `qualify_usage`/`UsageQualification` and the two constants (no `token_provenance` or `aggregate_usage` section exists today); `### cost_attribution` / `### waste_attribution` prose ("`tokens_total` / `tokens_wasted` are `None` when any contributing row is missing a component" and the unresolved-coverage sentence) absorbs row admission + provenance; the `from little_loops.history_reader import (` block.
- `docs/reference/HOST_COMPATIBILITY.md` — `[^tok-claude]` and the Codex "ll-ctx-stats now reads stored Codex rollout requests (ENH-3549)" footnotes: cache-rate qualification (measured-only, all contributors admitted) and unresolved-overlap behavior.
- `docs/ARCHITECTURE.md` — schema rows `v20 | usage_events` (`aggregate_usage()`) and `v29` (`waste_attribution()`).
- `docs/observability/otel-mapping.md` — "Cost attribution query": `gen_ai.usage.*` keys are absent when the token figure is unqualified.
- Stale docstrings: `history_reader/__init__.py` module docstring; `history_reader/usage.py` `aggregate_usage`, `cost_attribution`, `waste_attribution` ("A row missing `input_tokens` or `output_tokens` has an unavailable token count"), `_provenance_fields`; `cli/ctx_stats.py` `_aggregate_usage_events` ("partial subtotal is labeled `availability='partial'`"), `_compute_cache_rate_from_usage`.
- No change: `docs/reference/EVENT-SCHEMA.md`, `CONFIGURATION.md`, `config-schema.json`, `README.md`, `.claude/CLAUDE.md`, `commands/`, `agents/`, `hooks/`. `CHANGELOG.md` lands at release prep, not `[Unreleased]`.

### Codebase Research Findings

_Consolidated 2026-10-05 from `/ll:refine-issue`, `/ll:wire-issue` and pre-implementation reviews:_

- **Anchors.** Use symbol names. Line numbers in `history_reader/usage.py` and `cli/ctx_stats.py` predate BUG-3735, which is in flight in the working tree; re-verify after it commits. `token_provenance.py` (unaffected): `row_channel:69`, `row_provenance:77`, `ObservationGroup:114`, `aggregate_provenance:210`, `total:222`, `subtotal:231`, `entry:242`, `group_rows:302`, `counted_entry:363`, `_META_KEYS:407`.
- `REQUIRED_KEYS` is a **test constant** (`scripts/tests/test_enh3528_token_provenance.py:37`), not a module symbol. `ObservationGroup.entry` emits `provenance`, `metric`, `scope_kind`, `observation_time_basis`, `availability`, `known_count`, `missing_count`, `composition`, `coverage`, plus conditional `hosts`/`channels`/`session_id`/`invocation_id`/`observed_from`/`observed_to`/`reason`; new metadata is additive.
- `ObservationGroup.subtotal` call sites: sort keys in `aggregate_usage` (`cost_usd`) and `cost_attribution` (`input_tokens`), and published `totals`/`per_model` values in `ctx_stats._aggregate_usage_events`. No test or doc calls `.subtotal(`.
- `_Component.add` registers a provenance slot before checking for NULL, so `aggregate_provenance` sees labels from rows whose value for that column is NULL; `entry()` filters zero-count slots from `composition`. `aggregate_provenance` is not an admission-filtered signal.
- Today `aggregate_usage`/`cost_attribution` gate each column individually via `total`, so a partial row's present components surface beside a `None`; only `_aggregate_usage_events` publishes partial sums as canonical. Row-level admission therefore changes `aggregate_usage`/`cost_attribution` too, which `test_cost_attribution_omits_partial_attribute_keeps_complete_sibling` pins today.
- Writers emit only `measured`/`unknown` provenance (live default `unknown`; transcript `measured` iff `observation.qualified`; rollout `measured` iff measured). `estimated` is recognized on read but unwritten.
- `_classify_coverage` returns `("unknown", "rollout_request_identity_unverified")` for any Codex rollout row (`host == "codex"`) whose provenance is not `measured`, so an estimated Codex rollout row is never canonical — see Decision Rules → Estimated scope.
- `ctx_stats` `usage_by_model` has no text rendering (JSON only); text parity applies to the waste and cache-rate/freshness lines.
- `_compute_cache_rate_from_jsonl` is a separate non-stored cache-rate path with its own eligible-subset logic; it emits no `source`/`coverage`/`qualification_reason`, always reports provenance `unknown`, and reaches the shared `_render` footer and `counts["hit_rate_pct"]`. It stays unchanged.
- Current stored cache gate: `reportable = coverage == "non_overlapping" and group.aggregate_provenance("input_tokens") == "measured"` over `selected_rows`; rows with input/cache-read/cache-creation all present count as `eligible_events`, the rest `excluded_events`; `output_tokens` is never read. `unverified_usage` is a `ctx_stats` code, not a coverage reason.
- Review probes (2026-10-05, `main`): `_cache_rate_provenance` reports pointer coverage `non_overlapping` for a stored result with `coverage='overlap_unresolved'` and resets two known observations to two missing; `_waste_provenance` reports two missing ratio contributors for two observed zero pairs; direct `ObservationGroup.add` cost permutations return `1e16` vs `1.0000000000000002e16`, and at the finite-float boundary the finite maximum vs Infinity. Earlier probes reproduced invalid-value crashes in source readers.

## Program Design

### Types

- `UsageComponentCounts` — new frozen dataclass in `scripts/little_loops/token_provenance.py`: `column: str`, `known_count: int`, `missing_count: int`, `invalid_count: int`. Counts describe valid numeric/NULL/present-invalid observations, independent of whole-row qualification.
- `UsageQualification` — new frozen dataclass in the same module: `eligible: bool`, `provenance: str` (`measured`/`estimated`/`mixed`/`unknown`), `reason: str | None`, `contributors: int`, `rejected_contributors: int`, `component_counts: tuple[UsageComponentCounts, ...]` in `AGGREGATE_COLUMNS` order, `policy_version: int`. `eligible` iff `reason is None`. Copies counts into immutable values; retains no mutable component mappings.
- `ObservationGroup` (`token_provenance.py`, plain class) — today accumulates every row into every `AGGREGATE_COLUMNS` component with no row admission; a row missing one token column still feeds the other three.
- Coverage values stay plain `str`: `non_overlapping`, `overlap_unresolved`, `unknown`. Provenance literals have no module constant (a separate `TokenProvenance` Literal lives in `subprocess_utils.py`).

### Signatures

- `qualify_usage(group: ObservationGroup, *, require_cost: bool = False, measured_only: bool = False) -> UsageQualification` — new, `token_provenance.py`; pure over group state.
- `ObservationGroup.total(column: str) -> Any` — canonical value; `None` unless `qualify_usage(self, require_cost=(column == COST_COLUMN))` is eligible.
- `ObservationGroup.audit_subtotal(column: str) -> Any` — renamed from `subtotal`; valid-value sum or `None`, no coverage/provenance gate.
- `ObservationGroup.entry(column: str, *, extra_reason: str | None = None) -> dict[str, Any]` — existing; gains qualification metadata.
- `select_usage_coverage(conn, *, since=None, require_run_id=False, host=None, session_id=None) -> CoverageSelection` — existing, unchanged here.
- `aggregate_usage(group_by="model", *, since=None, db=...)`, `cost_attribution(group_by="gen_ai.invocation.id", *, since=None, db=...)`, `waste_attribution(*, since=None, db=...)` — `history_reader/usage.py`; every existing public key of each returned dict is preserved.
- `_aggregate_usage_events(db_path) -> dict | None` and `_compute_cache_rate_from_usage(handle, db_path) -> tuple[dict | None, str | None]` — `cli/ctx_stats.py`.

### Call Path

`main_ctx_stats` -> `_aggregate_usage_events` / `_compute_cache_rate_from_usage` / `_aggregate_waste` -> `select_usage_observations` / `select_usage_coverage` -> `ObservationGroup.add` -> `qualify_usage` -> published figure and `entry` metadata.

`aggregate_usage` / `cost_attribution` -> `_read_groups` -> `select_usage_observations` -> `group_rows` -> `ObservationGroup.total` -> `qualify_usage`. `waste_attribution` calls `select_usage_observations(require_run_id=True)` directly and keeps its own per-loop accumulator beside the `ObservationGroup`.

### Decision Rules

_Normative. Other sections defer to these rules._

- **Terms.** *Admitted* = all four `TOKEN_COLUMNS` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) satisfy `type(value) is int and value >= 0`. *Eligible* = admitted **and** row provenance is `measured` or `estimated`. Use these two words only in this sense.
- **Row admission (fixed, first).** NULL is missing; negative, float (including integral `3.0`), boolean and string values are invalid. SQLite INTEGER affinity may persist booleans/integral floats/numeric strings as integers; validate the actual read value without inferring lost type history. Missing `cost_usd` alone does not reject a token row — it makes cost unavailable. A rejected row stays in `audit_rows`; only its valid components enter audit subtotals/composition. A row that is not admitted is audit-only for every canonical figure regardless of provenance; an admitted `unknown`-provenance row is also audit-only.
- **Population.** Qualification evaluates **all in-filter annotated audit contributors** of the requested aggregate, including coverage-unresolved rows; `selected_rows` certifies coverage only and is never the qualification population. Coverage reconciliation precedes output/report filters; admission/provenance/pricing checks apply to the returned population, so an out-of-window unknown-provenance row alone does not invalidate a qualified window (out-of-window overlap still does, via coverage).
- **Provenance.** `measured` and `estimated` are recognized; NULL, `unknown` and unrecognized strings all read as `unknown` through `row_provenance`. The `UsageQualification.provenance` label is computed from all population contributors, **unmasked by coverage**: `measured` if every contributor is measured, `estimated` if every one is estimated, `mixed` if both occur, `unknown` if any is unknown. Coverage failure is expressed in `reason`, not in the label. Existing public `provenance` fields (`ObservationGroup.aggregate_provenance`, `entry()["provenance"]`, the stored cache result's `provenance`) keep their current computation and coverage masking, so ENH-3543/ENH-3549 controls hold. `mixed` is never stored.
- **Figure prerequisites** (after coverage reconciliation and row admission):

  | Figure | `qualify_usage` call | Prerequisites |
  | --- | --- | --- |
  | Token component / four-component consumption | `require_cost=False` | Every population row eligible. |
  | Cost / cost per issue | `require_cost=True` | Every contributor eligible with a finite stored non-bool `int`/`float` cost ≥ 0 and a finite aggregate; no read-time repricing; no priced-subset sums. Dollars are API list-price estimates. Cost eligibility implies token eligibility. |
  | Waste tokens / percentage | `require_cost=False`, per loop | See Waste. |
  | Session cache hit rate and operands | `measured_only=True` | Every contributor eligible **and measured**. See Cache rate. |

  `ObservationGroup.total`/`entry` use the token or cost row by column; the stored cache reader is the only `measured_only=True` caller.
- **Estimated scope.** The `estimated` general-consumption path is reachable for transcript and live rows. `_classify_coverage` keeps classifying a Codex rollout row with non-measured provenance as coverage `unknown` (`rollout_request_identity_unverified`); that rule is unchanged here (ENH-3730 / host adapters own any change).
- **Cache rate.** Qualify all `selection.audit_rows` with `measured_only=True`, including the output-column admission prerequisite (missing **output** disqualifies the rate even though output is not a denominator operand). Denominator is `input + cache_read + cache_creation` over the full qualified sums (never a complete subset). Base failure blanks the rate and all operands; otherwise zero denominator blanks only the rate with `zero_denominator`, operands stay numeric zeros with reason `None`. Keep the `counts` entries' `{"known", "missing"}` shape: rate known = contributors passing row prerequisites, rate missing = `rejected_contributors`; operand known/missing = valid-component/NULL counts. Coverage/zero-denominator failure does not falsify counts. Expose operand invalid counts in an additive parallel `invalid_counts` mapping and full-population `rejected_contributors`. Cache qualification never requires cost.
- **Waste (reading B, settled).** Keep `input_tokens + output_tokens`, the `_WASTED_RUN_PREDICATE` subset and `waste_pct` only when `tokens_total` is nonzero. One per-loop qualification over the full joined population (admission **and** provenance gate) governs both `tokens_total` and `tokens_wasted`; a row with NULL cache columns therefore blanks that loop's waste figures (behavior change vs today's input/output-only check). Preserve `tokens_total_missing` (joined rows missing input/output) and `tokens_wasted_missing` (wasted-run rows missing those operands); missing cache/provenance is a qualification rejection, not an input/output shortfall. Classify each operand pair once: either NULL operand → missing; otherwise either invalid operand → invalid; otherwise known. Add `tokens_total_invalid`/`tokens_wasted_invalid` and full-loop `rejected_contributors`. Non-wasted rows contribute known zero to the numerator even when their raw pair is missing/invalid. For each token figure, known = joined events minus that figure's missing and invalid pairs. Ratio known/missing/invalid counts equal the denominator-pair counts, independently of full-loop rejection counts (missing cache can blank the figures with zero missing pairs; zero denominator can blank the ratio with all pairs known). Ratio reason = base failure if present, else `zero_denominator` when total is zero, else `None`; a qualified positive total with no wasted runs gives zero wasted tokens and ratio.
- **Availability and counts.** Every published canonical stored-usage `token_provenance` entry (`ObservationGroup.entry`, `_waste_provenance`, `_cache_rate_provenance`) is `available` iff its value is present, otherwise `unavailable`; these pointers never emit `partial`. Locally override `counted_entry`'s count-derived availability for stored cache/waste; unrelated callers keep its behavior. Preserve real known/missing counts even when qualification fails; never reset a valid-component count to force availability. For each component, valid known + NULL missing + present invalid = contributors. A row rejected for several prerequisites counts once in `rejected_contributors`; coverage failure and zero denominator are group/figure failures, not missing or invalid rows. Pointers also carry figure-specific `qualification_reason`, `invalid_count` and `rejected_contributors`. Every stored-cache pointer carries the actual selection coverage (equal to `cache_rate_coverage`), never `counted_entry`'s `non_overlapping` default.
- **Invariant scope.** The value/availability/coverage/reason invariant applies to `usage_by_model`, `waste` and cache pointers whose result has `source == "stored_usage"`. Direct-JSONL cache pointers are out of scope and may still emit `partial`.
- **Figure reasons.** `aggregate_usage`/`cost_attribution` rows gain token `qualification_reason` and `cost_qualification_reason` (matching ENH-3733); waste rows gain base `qualification_reason` plus `waste_pct_qualification_reason`; stored cache results keep public `qualification_reason` for the rate and each operand's pointer carries its own figure reason. A figure's value is `None` iff its figure reason is non-NULL. A missing/invalid cost cannot appear in the token reason or blank qualified tokens.
- **Reason codes and precedence.** First applicable group-wide failure wins, independent of insertion order: `empty_selection` (no contributors) > coverage (`coverage_overlap_unresolved` for `group.coverage() == "overlap_unresolved"`, `coverage_unknown` for `"unknown"`, `unclassified` for any unexpected status) > `missing_token_component` > `invalid_token_component` > `unknown_provenance` > `not_measured` (when `measured_only`) > `invalid_cost` (cost figure) > `unpriced_contributor` (cost figure). The same order applies when `measured_only` and `require_cost` are both true. Figure builders add `zero_denominator` only after base qualification succeeds. Keep existing `coverage_reason` codes/prose untouched as separate diagnostics; never parse their semicolon-joined text or use `CoverageSelection.reason` to choose a code. No `unrecognized_provenance` code.
- **Reason vocabulary.** `USAGE_QUALIFICATION_REASONS` = the codes above plus `zero_denominator`. It is the bounded handoff for ENH-3733, separate from coverage diagnostics and CLI absence/compatibility codes; an arbitrary snake_case string can still disclose an ID, so unknown reasons become `unclassified` (no enum or registry). `usage_by_model` and `waste` pointers carry shared codes. The stored cache path maps `unknown_provenance` and `not_measured` to public `unverified_usage` on both the result's `qualification_reason` and every stored-cache pointer; other codes pass through. The document-wide invariant accepts `USAGE_QUALIFICATION_REASONS | {"unverified_usage"}`, with `unverified_usage` valid only on stored-cache pointers.
- **Numeric validity and arithmetic.** Validate before accumulation and qualification, identically in source and snapshot. Invalid values count as rejected contributors and remain intact in audit rows, but never enter numeric audit subtotals, `channel_subtotals` or provenance composition; never coerce strings/bools, let a string raise during addition, or emit NaN/Infinity. Token sums stay Python integers (exact above `2**53`). Cost totals and each provenance subtotal must be order-independent in both value and overflow verdict — use a stable stdlib approach such as `math.fsum` over buffered validated scalars, handling `OverflowError` and non-finite results; `qualify_usage` never re-reads raw rows and totals/metadata reuse the same finalized sums. Finite contributors whose aggregate overflows make cost unavailable with `invalid_cost`, preserve known counts, report `None` (not Infinity) for that audit subtotal, and — absent row-level failure — have `rejected_contributors == 0` and every `invalid_count == 0`; tokens and any still-finite provenance subtotals stay available on their surfaces.
- **Empty selection** is unavailable; a qualified observed zero is zero.
- **Audit surfaces (settled).** Preserve token `channel_subtotals` on source rows and labeled valid-value `token_provenance[ptr].composition` subtotals/counts in CLI JSON; add invalid/rejected/figure-reason metadata there. No duplicate `usage_by_model.audit` object; no new keys inside canonical `totals`/`per_model[model]`. Dollars appear only in existing composition: never add `cost_usd` to `channel_subtotals()` and add no new audit-dollar surface. Valid finite dollar audit subtotals remain labeled evidence when canonical cost fails; the no-priced-subset rule applies to canonical figures only.

## Compatibility Consequences

_Historical sample recorded 2026-10-04 from the maintainer's local `.ll/history.db` during a pre-implementation review. These numbers motivate the docs wording and the release-prep CHANGELOG entry; they do not go into `docs/reference/` or `docs/guides/`._

- 517,614 `usage_events` rows; 512,646 (~99%) are `transcript` rows with `provenance='unknown'`; only 2 rows miss a token column. All-history totals and per-model figures are already `None` via the store-wide ambiguity gate and stay `None` after ENH-3730, because any `unknown` contributor blanks the aggregate.
- 3,742 of 4,040 `claude-sonnet-5-5` rows have NULL stored `cost_usd` (pre-BUG-3696); with no read-time repricing, cost is unavailable for nearly every aggregate containing them.
- **Recovery (resolved 2026-10-05).** `normalize_host_usage` requires the persisted raw `usage_contract` plus a valid native contract. Full replay with a legacy NULL marker stays unknown; `refresh_usage_source` leaves already-ingested raw rows/markers unchanged; rebuild can recompute stored cost but does not qualify unknown tokens. `refresh_raw_events` re-ingests an available verified original, can persist newly observed producer evidence, invalidates old non-live derivations and requires replay (`test_refresh_recovers_stripped_usage_and_rebuild_is_stable`). Missing/unverified/compacted originals retain diagnostics and cannot be assumed recoverable. Document the distinction; do not invoke recovery from a reader. Conflict/pruned-history recovery is BUG-3736's.
- Canonical partial sums are retired; strict admission also rejects integral floats/numeric strings previously accepted by cache coercion; existing JSON numeric keys stay nullable with audit detail in provenance composition.

## Implementation Steps

0. **Prerequisite**: BUG-3735 committed (`blocked_by`). Re-verify `usage.py`/`ctx_stats.py` anchors against it before editing.
1. **Qualification core (commit 1, TDD).** Write failing DB-free `qualify_usage` tests (shared-contract and vocabulary bullets), then add `UsageComponentCounts`, `UsageQualification`, the constants, strict accumulation, `total`/`entry` qualification, the `audit_subtotal` rename and `_META_KEYS` keys. Re-export from `history_reader/__init__.py`.
2. **Source consumers (commit 2, TDD).** Update the "will break" tests and add source-figure tests, then route `aggregate_usage`, `cost_attribution`, `waste_attribution`, `_aggregate_usage_events`, `_compute_cache_rate_from_usage`, `_waste_provenance`, `_cache_rate_provenance`, `_print_json`, `_render` and `main_ctx_stats` per the wiring list.
3. **Docs (commit 3).** CLI.md, API.md, HOST_COMPATIBILITY.md, ARCHITECTURE.md, otel-mapping.md and stale docstrings.
4. Run `python -m pytest scripts/tests/test_usage_selection_chokepoint_gate.py scripts/tests/test_enh3528_token_provenance.py scripts/tests/test_enh3543_usage_coverage.py scripts/tests/test_enh3656_stored_cache_rate.py scripts/tests/test_enh3549_codex_stored_ctx_stats.py` before the full suite.

## Acceptance Criteria

- [ ] Implementation, tests and docs match the recorded policy: legacy absent/NULL audit-only, complete estimated transcript/live rows labeled numeric consumption, cache rates measured-only. No migration, derive-version bump or automatic rebuild/refresh. End-user docs describe unavailable-figure behavior, ordinary replay vs explicit verified-source recovery, nullable canonical figures and existing audit surfaces without maintainer-store sample counts.
- [ ] `qualify_usage`/`UsageQualification`/`UsageComponentCounts` and the two constants exist as specified in Program Design; results are deeply immutable, count each rejected row once across all flag combinations, partition per-column counts, and give permutation-invariant reasons using status-based coverage codes. `ObservationGroup.subtotal` is renamed `audit_subtotal`; `total`/`entry` qualify with `require_cost` set by column.
- [ ] The result's provenance label is unmasked by coverage, while existing public `provenance` fields keep their masking; ENH-3543/ENH-3549 controls pass unchanged.
- [ ] Within the invariant scope, pointer value, availability, coverage and figure reason agree (`None` iff unavailable with a reason); stored-cache pointers carry the actual selection coverage; counts are truthful with separate invalid/rejected counts; no count-reset workaround or `partial` remains. Direct-JSONL rendering and metadata are unchanged.
- [ ] Source rows carry independent token `qualification_reason` / `cost_qualification_reason` matching ENH-3733; missing/invalid cost never blanks tokens; the four token fields and OTel attributes qualify together. Waste has a separate ratio reason. Stored-cache result and pointers use `unverified_usage` for `unknown_provenance`/`not_measured`.
- [ ] Waste is qualified once per loop over the full joined population for both token figures; ratio counts use denominator-pair evidence; reason precedence starts with `empty_selection`; no `unrecognized_provenance`; `cost_usd` is not in `channel_subtotals()`.
- [ ] The matrix in Tests → New tests passes, including the estimated Codex rollout control (`coverage_unknown`).
- [ ] An in-filter ineligible row can never be silently dropped to make a total or rate qualify; numeric stored cost cannot bypass token/provenance prerequisites; empty selection is unavailable while a qualified observed zero is zero.
- [ ] A complete measured observation plus any in-filter missing/invalid/unknown/estimated or unresolved audit observation (including missing **output**) makes the stored-session rate unavailable; one measured-only result over `selection.audit_rows` governs the rate, operands and metadata; no coercion or complete-subset rate remains; qualified zero operands survive a `zero_denominator` rate.
- [ ] `ll-ctx-stats` JSON keeps existing canonical numeric keys and valid pointers; waste/cache text and JSON agree, with bounded figure reasons in text footnotes; `same_metadata` compares the three new keys while ignoring free-form prose; zero denominator emits no unverified-producer warning; qualified current Claude/Codex controls keep clean stderr; dollars are visibly estimates and finite audit-dollar subtotals survive canonical cost rejection.
- [ ] Claude/Codex text and JSON retain qualified as-of values and freshness diagnostics after append/source loss; stale/unknown is never described as current; failed derive is unavailable/unknown, not a fresh zero.
- [ ] Replay, rebuild and unchanged tail refresh preserve unknown ingest-time evidence; stored numeric cost cannot promote it; explicit verified-source recovery still works and is stable on repeat.
- [ ] Invalid contributors cannot crash accumulation or serialize non-finite values; token sums are exact; cost totals/overflow are order-independent; aggregate overflow affects only cost.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — prerequisite for safe remaining-host publication.
- **Effort**: Large — shared contract and source consumer changes.
- **Risk**: Medium — legacy/invalid figures deliberately become unavailable; labeled audit values and reader diagnostics remain.
- **Publication gate (verified 2026-10-05, no action here):** ENH-3671–3676 already carry `blocked_by` ENH-3731, ENH-3732 and ENH-3733, so production derivation of newly recognized usage rows waits for all three qualification children. Capture/adapter/raw-retention work can proceed independently.

## Scope Boundaries

- **Out of scope:** the `channel=` selector scope (ENH-3748); selector acquisition/output ordering and the stored-cache `channels` metadata normalization to `row_channel` (BUG-3735); snapshot export/dashboard (ENH-3733); quality derive status/baselines/workspace (ENH-3732); ENH-3730's store-wide ambiguity redesign and the Codex rollout non-measured coverage rule; provider capture and adapters; derive-algorithm or source-freshness changes; component-level measured exceptions; pricing fallback; legacy provenance/cost backfill or automated recovery; a new audit-dollar surface; `cost_usd` in `channel_subtotals()`. Existing explicit verified-source recovery is documented and regression-guarded, not changed or invoked.

## Confidence Check Notes

_Historical. The 2026-10-05 re-score (Readiness 95, Outcome 63 — below `outcome_threshold` 65) predates the 2026-10-05 restructure that split `channel=` to ENH-3748, added `blocked_by: BUG-3735` and resolved four contract gaps; its frontmatter scores were removed. Rerun `/ll:confidence-check` before implementation._

### Outcome Risk Factors (from the historical score)
- Moderate per-site complexity: row-level admission is a contract change across `ObservationGroup`, `aggregate_usage`, `cost_attribution`, `waste_attribution` and `ctx_stats`.
- Broad change surface: ~6 subtotal/selector callers plus ~5 test files whose NULL-provenance fixtures flip to unavailable.
- New bounded reason vocabulary and independent token/cost/rate metadata require the specified precedence, population, count and permutation controls.

## Session Log

- Pre-implementation review - 2026-10-05 - `/ll:advise` with `claude-fable-5-1` (confidence 0.85) plus code checks. Split the `channel=` selector scope to ENH-3748; added `blocked_by: BUG-3735` (in flight in the working tree, same selector) and removed the either-landing-order clauses; moved maintainer-store sample counts out of the end-user docs requirement; decided the `subtotal` → `audit_subtotal` rename and the per-column `require_cost` mapping; resolved the provenance-label masking contradiction (result unmasked, public fields masked), the stored-cache pointer reason vocabulary, the estimated Codex rollout coverage rule and the invariant scope vs direct-JSONL `partial`; put `empty_selection` first in precedence; converted the publication-gate AC to a verified note; consolidated normative rules into Decision Rules. Stale scores removed; rerun the confidence gate.
- `/ll:confidence-check` - 2026-10-05T20:20:41 - `ae6dd8ed-dfaf-4c44-8d2a-2461e60f636e.jsonl`
- Pre-implementation review - 2026-10-05 - Inspected `main`; `/ll:advise` with `claude-opus-5-5` (confidence 0.80) and direct helper probes identified incorrect stored-cache pointer coverage, ambiguous waste-ratio evidence counts and order-dependent float totals/overflow. Tightened measured-only result reuse, actual coverage propagation, pair/count semantics, metadata grouping, visible figure-reason footnotes and stable cost finalization. The 64 focused provenance/coverage/cache/chokepoint baseline tests and issue format/design/whitespace checks passed.
- `/ll:ready-issue` - 2026-10-05T19:24:26 - `f4e99cab-51d3-4bd1-81f2-929d6e6d61e8.jsonl`
- Pre-implementation review - 2026-10-05 - Inspected `main`; `/ll:advise` with `claude-opus-5-5` (confidence 0.78). Added independent token/cost and ratio reasons, full annotated-audit cache population, truthful missing/invalid/rejected counts, immutable result fields, bounded order-independent coverage codes, exact cache compatibility mapping, channel validation, zero/overflow controls and explicit recovery semantics. Focused baseline: 81 tests passed.
- Pre-implementation epic review - 2026-10-05 - Clarified invalid-value audit accumulation, empty-selection precedence and direct re-exports. Opus confidence 0.72. BUG-3736 owns the separately reproduced pruning/replay loss.
- Pre-implementation epic review - 2026-10-05 - Opus critique (confidence 0.74) and direct-mapping probes confirmed source/snapshot disagreement on negative/fractional/boolean token values. Added shared numeric validity, deterministic reasons, policy-version/result and safe-reason handoffs.
- `/ll:confidence-check` - 2026-10-05T03:37:45 - `4504af05-93f3-458d-afca-2878c39c662b.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T03:32:20 - `5b873f1f-917c-4a97-9f4f-58c77a829f91.jsonl`
- `/ll:wire-issue` - 2026-10-05T03:23:32 - `e79ced76-329a-41b8-acda-11c309df53b4.jsonl`
- `/ll:refine-issue` - 2026-10-05T03:13:46 - `ca3640c2-fc5f-47d0-9305-872e41fc20ff.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2

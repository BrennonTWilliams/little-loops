---
id: ENH-3733
type: ENH
title: Snapshot export and dashboard usage qualification
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
blocked_by:
- ENH-3731
relates_to:
- ENH-3732
- ENH-3543
- ENH-3730
- BUG-3735
- ENH-3748
verify_verdict: VALID
confidence_score: 70
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-3733: Snapshot export and dashboard usage qualification

## Summary

Make shareable snapshots and the built-in dashboard honor the shared usage qualification policy. This child routes `_snapshot_usage_selection` and `usage_coverage_audit` through `qualify_usage`, preserves qualification label/reason and a policy version in the export under the privacy allowlist, and updates the built-in dashboard query, visible reasons and custom-SQL guidance. Blocked by ENH-3731.

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. Recorded parent Decision (commit `01747bb96`) applies: legacy NULL/unknown is audit-only; complete estimated rows are labeled numeric consumption; cache rates measured-only.

## Current Behavior

`_snapshot_usage_selection` selects canonical components whenever coverage is non-overlapping, and `usage_coverage_audit` has no qualification/provenance label. A partial/unknown OpenCode-shaped row (input 10, output 2, cache-read 4, cache-creation NULL) is stored as canonical input 10, output 2, cache-read 4; the same holds for a measured partial row with stored cost $1. The dashboard's predefined query and guidance don't distinguish unavailable from observed zero.

## Expected Behavior

- Source and snapshot canonical fields agree under the shared policy. Explicit unknown/partial audit-only rows retain raw values and labeled audit subtotals, but dependent canonical totals/rates are NULL/unavailable with a visible reason; numeric stored cost cannot bypass token/provenance prerequisites.
- Reconcile overlap on the full identity group before filtering; apply provenance/component qualification to the contributors in the requested figure after filtering. An out-of-window audit-only row alone does not taint a different window's figure, while an overlapping counterpart outside the window still prevents coverage certification. Preserve the in-filter population when building grouped totals (model/channel); silently dropping audit-only contributors cannot make the remaining subset a complete figure. A channel subtotal cannot recertify an incomplete model: canonical fields carry the scope (currently model-wide with channel contributions) used for eligibility.
- Coverage-selected rows/counts (including audit-only rows in `selected_usage_events`) stay intact; selection certifies overlap only. No selected observations is unavailable/empty; a qualified observed zero stays numeric zero; a zero rate denominator is unavailable.
- Extend `_SHAREABLE_COLUMNS` and schema only as needed to preserve the qualification label/reason; export only bounded accounting reason codes — never source paths, native request/session identities, credentials or source-derived diagnostic text. Record a safe qualification-policy version in snapshot metadata so retained snapshots don't imply a later policy. Computed columns/metadata don't require a source-history migration (any needed schema extension takes the next append-only version). Keep existing public numeric keys; expose audit subtotals distinctly; provenance pointers, availability, text suffixes and reason codes agree with the JSON values.
- Built-in dashboard queries expose qualification codes/reasons and distinguish unavailable from observed zero. Custom SQL stays an audit tool: document that a bare `SUM` of selected rows or NULLs does not establish completeness, without rewriting user SQL or adding a query engine. Correct the existing dashboard guidance.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

Policy-version home — three candidates; the codebase constrains each differently:

**Option A**: Page stamp only — add a key to `build_dashboard_html`'s `data` dict beside `allowlist_version`, declare it in `manifest.yaml` (`data_schema.properties` and `required`), render with `[[= key =]]`. Matches the existing convention (`schema_version_warning` reasoning: versions ride the page); a retained `.db` and `HistoryPayload.to_dict` / `refreshHistory` (five-key payload pinned by `test_feat3323_sse_bridge.py`) do not carry it.

**Option B**: In-snapshot table (e.g. a one-row policy table created only on the `usage_event` path). The only form a retained `.db` carries on its own, but there is no in-snapshot meta table precedent, and it breaks the four-table-set, no-indexes and loop-only-export tests.

**Option C**: Policy-version column on the generated `usage_coverage_audit` table (a bounded literal, constant per snapshot). Travels with any retained snapshot, adds no table, needs no manifest/payload/`HistoryPayload` change, and rides the same three-place schema edit and allowlist bump already required for the label/reason columns. Caveat: a snapshot with zero audit rows carries no version (it also carries no figures).

> **Selected:** Option C — rides the three-place schema edit and allowlist bump already required for the label/reason columns, and is the only form a standalone `build_snapshot_db` output carries.

**Recommended**: Option C — it is the only candidate that satisfies "retained snapshots don't imply a later policy" without a new table or a pinned-payload change; a display-only page stamp (Option A) can be added later without conflict.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-10-04.

**Selected**: Option C — policy-version column on `usage_coverage_audit`

**Reasoning**: The label/reason columns already force a `_SHAREABLE_COLUMNS` + `CREATE TABLE` DDL + `audit_rows.append` tuple edit and a `PINNED_VERSION`/`PINNED_HASH` bump (`queries.py:212-236`, `:392-404`, `:460-495`; `TestAllowlistVersionLockstep`), so the version column adds one name to an edit that is happening anyway, with no manifest, `dashboard.py`, template-stamp, `HistoryPayload` or table-set test change. Option A needs five edit sites across four files and leaves `build_snapshot_db` output (what the tests and the "snapshot export carries a policy version" criterion inspect) without a version; Option B needs a new table and a table-set assertion change with no in-snapshot meta precedent.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (page stamp) | 3/3 | 2/3 | 2/3 | 1/3 | 8/12 |
| Option B (in-snapshot table) | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| Option C (audit-table column) | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:

Evidence on A (page stamp): exact `allowlist_version` stamp precedent (`dashboard.py:333`, `manifest.yaml:16,33`, `template.html.j2:83`), but the version is absent from the `.db` and from `HistoryPayload` (five-key payload pinned at `test_feat3323_sse_bridge.py:1028`). The `.db` is a temp artifact in production (only the HTML persists), which is why it is not scored lower.

Evidence on B (in-snapshot table): only the four-table-set assertion (`test_feat3304_artifact_dashboard.py:302-307`) must change if the DDL is plain and `usage_event`-guarded (`queries.py:553`), so the "breaks three tests" claim in the option text is overstated; still no meta-table precedent in any snapshot.

Evidence on C (audit-table column): no precedent for a constant-per-row column, and zero-audit-row snapshots carry no version; ENH-3731 owns the policy version beside `qualify_usage` and exposes it on the result. Sanitise-and-truncate idiom at `queries.py:424-432` applies to the literal.

### Resolved consumer contract (2026-10-05)

These choices resolve the research questions below; retain the recorded Option C policy-version home.

1. Build one `ObservationGroup` per logical model from **all in-filter annotated audit contributors**, retaining unresolved siblings. This preserves model-wide coverage taint and provenance/admission completeness. Run `qualify_usage` separately for tokens and cost (`require_cost=True`). Emit each channel's canonical component sums only if the full model passes that figure's qualification; never qualify only `selected_rows` or a complete channel subset. Audit and coverage-selected counts remain unchanged.

2. Use `row_channel` for logical channels. Group missing models using `UNKNOWN_MODEL_BUCKET` from `token_provenance.py`, matching `ll-ctx-stats`; preserve raw model/channel values on the observation export. The model-grouping API that historically returns NULL may keep its public key; parity tests compare the explicit NULL-to-bucket mapping. Document the changed audit-table bucket values rather than silently relabel raw observations.

3. Export model-scoped qualification provenance (`measured`/`estimated`/`mixed`/`unknown`), token `qualification_reason`, separate `cost_qualification_reason`, and `qualification_policy_version` from the shared result. Derived `mixed` is valid metadata in a computed artifact; the ban on storing `mixed` applies to producer observations. Preserve raw stored provenance on `selected_usage_events` and explain why its value is distinct from the aggregate qualification label. A missing/invalid price can leave tokens available while cost is unavailable.

4. Follow ENH-3731's common numeric validity rule; neither snapshot nor source may certify a sum that skipped an invalid contributor. Export only allowlisted bounded reason codes; syntactically valid arbitrary source text becomes `unclassified`. Add reason/ID-leak and invalid-value parity controls.

5. The snapshot has no rate column: do not add one. Empty/zero and token/cost qualification criteria bind its existing figures; rate/zero-denominator and measured-only checks are parity controls on the stored session reader. Remove any implication that this issue creates snapshot rates, JSON provenance-pointer surfaces or a new dashboard payload.

6. Old snapshots without the qualification columns/version remain audit artifacts; consumers must not infer certification under the new policy from old numeric columns. No legacy-snapshot migration is required. Empty new snapshots carry no audit rows/figures, so Option C carries no version there; test that case explicitly. The qualification policy version is separate from the export allowlist version and coverage policy.

7. Unscoped dashboards may remain unavailable under the global coverage policy, unknown historical provenance or missing stored prices even after this issue lands. That is expected, explained behavior; ENH-3730 is optional availability work, not permission to relabel a selected subset as complete.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/queries.py` — `_snapshot_usage_selection`, `usage_coverage_audit`, `_SHAREABLE_COLUMNS`, policy-version metadata.
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — predefined `usage_coverage_audit` query, qualification/reason display, custom-SQL guidance; inspect `cli/artifact/dashboard.py` if generated metadata changes require it.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/queries.py:393` — the schema is written three times, not once: new qualification columns must land in the `_SHAREABLE_COLUMNS` list, the literal `CREATE TABLE snap.usage_coverage_audit (...)` DDL, and the positional `audit_rows.append((...))` tuple (and `CREATE TABLE snap.selected_usage_events` at `:365` only if row-level qualification is exported); `PRAGMA table_info` order is test-enforced, in `_snapshot_usage_selection` [Agent 2 finding]
- _Page-stamp edit in `dashboard.py` struck — not needed under the selected Option C; only relevant if a display-only page stamp is added later_ [Agent 1 + 2 finding]
- _Template-manifest schema entries struck — not needed under the selected Option C; only relevant if a display-only page stamp is added later_ [Agent 2 finding]
- `scripts/little_loops/templates/dashboard.llat/template.html.j2:216` — `renderTable` renders NULL as an empty cell (`td.textContent = value === null || value === undefined ? "" : String(value)`), so unavailable vs observed zero is only distinguishable if the `PREDEFINED` SQL emits an explicit text label (`CASE`/`COALESCE`) or `renderTable` changes (it is shared with all custom SQL results) [Agent 2 finding]

### Dependent Files

- `scripts/little_loops/token_provenance.py`, `history_reader/usage.py` — consumed from ENH-3731; no changes here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/dashboard.py:333` — imports `_SHAREABLE_COLUMNS`, `_SHAREABLE_ALLOWLIST_VERSION`, `build_snapshot_db`; the only production caller of `build_snapshot_db`, in `build_history_payload` [Agent 1 finding]
- `scripts/little_loops/cli/artifact/dashboard.py` — `HistoryPayload.to_dict` returns exactly five keys; a page-stamp-only policy version is not re-read by the client `refreshHistory` poll, so a retained `.db` or live refresh does not carry it unless it is also in-snapshot, in `HistoryPayload.to_dict` [Agent 2 finding]
- `scripts/little_loops/cli/artifact/serve.py` — live `/history` route calls `build_history_payload` and the page-render path calls `build_dashboard_html`, in `make_history_route` [Agent 1 + 2 finding]
- `scripts/little_loops/cli/loop/run.py` — in-loop `--serve` branch calls `build_dashboard_html` with `serve_context`, in the dashboard branch of `cmd_run` [Agent 1 finding]
- `scripts/little_loops/session_store/__init__.py` — re-exports `build_snapshot_db` in the import block and `__all__` (signature must stay stable) [Agent 1 finding]
- `scripts/little_loops/cli/ctx_stats.py` — source-side consumer of `select_usage_coverage` and `audit_group.channel_subtotals()`, emitting `coverage_reason` / `cache_rate_channel_subtotals`; the "source and snapshot agree" AC compares against this reader, in `ctx_stats` output assembly [Agent 1 finding]
- `scripts/little_loops/artifact_templates.py` — comment near `:306` names `build_dashboard_html` as the template-data producer; stays accurate if the stamp is added there [Agent 1 finding]
- `scripts/little_loops/package_data.py` — `PACKAGE_DATA_ASSETS` lists the dashboard template files; affected only if a new template file is added [Agent 2 finding]
- `scripts/little_loops/config/features.py` and `scripts/little_loops/config-schema.json` — `ArtifactsExportConfig` docstring and `artifacts.export.mode` description restate the allowlist-version text; descriptive only, edit only if the policy version is described beside it. `artifacts.export` is pinned to `{mode, max_artifact_bytes}` (`additionalProperties: false`), so do not put the policy version in config, in `ArtifactsExportConfig` [Agent 1 + 2 finding]
- No loop YAML, skill, command, hook or agent references `usage_coverage_audit`, `selected_usage_events`, `build_snapshot_db` or `build_history_payload` — the only in-repo reader of the generated tables is the `PREDEFINED` "Usage cost by model and channel" query in `template.html.j2` [Agent 1 + 2 finding]

### Tests

- `scripts/tests/test_enh3543_snapshot_usage.py`, export allowlist/privacy tests, `test_feat3304_artifact_dashboard.py`, runtime tests under `scripts/tests/js/feat3304/`. Source/snapshot filter tests distinguish an out-of-window audit-only row from an out-of-window overlapping counterpart; model/channel aggregates pass the same matrix as ENH-3731; exercise actual consumers.

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests that will break or need coordinated edits**
- `scripts/tests/test_feat3304_artifact_dashboard.py` — column additions change the pinned hash: bump `_SHAREABLE_ALLOWLIST_VERSION`, `PINNED_VERSION` and `PINNED_HASH` together, in `TestAllowlistVersionLockstep` [Agent 2 + 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — a new in-snapshot policy/meta table breaks the exact four-table set, in `TestSnapshotRoundTrip::test_default_tables_are_the_shareable_set_not_export_defaults`; the table must also satisfy `TestSnapshotRoundTrip::test_snapshot_carries_no_indexes` (no indexes, `freelist_count == 0`) [Agent 2 + 3 finding]
- `scripts/tests/test_enh3543_snapshot_usage.py` — loop-only export must stay `{"loop_runs"}`, so any policy table is created only on the `"usage_event" in tables` path, in `test_loop_only_snapshot_does_not_create_usage_surfaces` [Agent 2 + 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — pins the substrings `FROM usage_coverage_audit ORDER BY model, channel`, `raw observations for audit` and the absence of `FROM usage_events GROUP BY model`; rewording the `PREDEFINED` tail or the "Snapshot SQL" paragraph breaks it, in `TestSnapshotRoundTrip::test_predefined_usage_view_uses_qualified_audit` [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — a new `[[= key =]]` must be in the manifest and no new `[[% %]]` block is allowed (pinned set: `if schema_version_warning`, `if serve_enabled`, `if serve_history_enabled`, `if serve_interaction_enabled`, `endif`), in `TestTemplatePipeline::test_template_body_avoids_jinja_delimiters_in_inline_js` [Agent 2 + 3 finding]
- `scripts/tests/test_feat3323_sse_bridge.py` — `/history` payload key set is pinned to five keys; adding a `HistoryPayload` field breaks it, in the `/history` route test asserting `set(payload) == {...}` [Agent 2 finding]
- `scripts/tests/test_enh3543_snapshot_usage.py` — canonical expectations for seeded rows (`canonical_input_tokens` 7/8, `canonical_cost_usd == 0.12`) move if qualification changes them; `partial-model` / `unknown-model` assertions are likely stable, in `test_shareable_snapshot_keeps_known_rows_and_audit_without_claiming_overlap`; also re-check `test_since_window_keeps_full_source_coverage_classification` (`rollout["raw_observation_count"] == 1`, `canonical_input_tokens is None`) [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — export must stay byte-reproducible (no timestamps or unordered set joins in exported columns/metadata), in `test_gzip_snapshot_is_reproducible_across_renders`; qualification code must also tolerate stores with every provenance column absent or NULL, in `test_pre_v55_db_exports_without_error` and the hand-DDL `_build_history_db` fixtures here and in `test_feat3323_sse_bridge.py` [Agent 2 + 3 finding]
- `scripts/tests/test_feat3323_sse_bridge.py` and `scripts/tests/test_remote_operation_matrix.py` — wrap/call `build_snapshot_db`; only break if its signature or return value changes (`TestBuildSnapshotDb::test_returns_the_recorded_schema_version` pins the source schema version string) [Agent 1 + 3 finding]

**Source-side suites that define the agreement baseline (reuse their matrices, do not duplicate)**
- `scripts/tests/test_enh3543_usage_coverage.py` — `select_usage_coverage` matrix incl. `test_live_and_stored_rollout_overlap_stays_audit_only_across_filters`, `test_pair_filter_admits_verified_live_but_not_other_or_unverified_hosts`; real `ensure_db()` fixtures [Agent 1 + 3 finding]
- `scripts/tests/test_enh3528_token_provenance.py` — `TestUsageAggregation::test_null_components_are_missing_not_zero`, `test_partial_subtotal_is_labeled`, `test_known_zero_stays_zero`; `TestHistoryReaderNullContract::test_ctx_stats_partial_vs_reader_none_on_same_fixture` is the nearest source-vs-reader agreement pattern [Agent 3 finding]
- `scripts/tests/test_usage_selection_chokepoint_gate.py` — `queries.py` is whole-file allowlisted, so new SQL there is not flagged; any new `.py` module with `FROM usage_events` beside token/cost columns trips `test_no_token_or_cost_reads_outside_the_chokepoint` (the `.j2` SQL is not scanned) [Agent 1 + 3 finding]

**New tests to write**
- `scripts/tests/test_enh3543_snapshot_usage.py` — extend the `insert` closure in `_source_db` (it hard-codes `output=2`, `cache_read=1`, `cache_creation=0`, `provenance="measured"`) with `cache_creation`/`provenance`/cost parameters, then add: partial OpenCode-shaped row (input 10, output 2, cache-read 4, cache-creation NULL, `estimated`/NULL provenance, with and without stored cost $1) → raw/known subtotals kept, `canonical_*` NULL, label/reason present, in a new `test_partial_unknown_rows_are_audit_only_with_visible_reason` [Agent 3 finding]
- `scripts/tests/test_enh3543_snapshot_usage.py` — out-of-window audit-only row vs out-of-window overlapping counterpart under `since`; empty selection unavailable vs qualified all-zero numeric `0`; zero-denominator rate NULL; channel subtotal cannot recertify an incomplete model, in new tests beside `test_since_window_keeps_full_source_coverage_classification` [Agent 3 finding]
- `scripts/tests/test_enh3543_snapshot_usage.py` — no test covers the `"unclassified"` / 64-char reason sanitization in `_snapshot_usage_selection`, and the sentinel byte-scan covers only `source_path`/`turn_id`/`request_id`; add a source-derived diagnostic-text sentinel so exported reason codes are leak-tested, in a new `test_exported_reason_codes_are_bounded_and_leak_free` [Agent 2 + 3 finding]
- `scripts/tests/test_enh3543_snapshot_usage.py` — no test compares source `aggregate_usage`/`cost_attribution` canonical fields with snapshot `canonical_*` on the same DB; add a per-model parity test (allowing only documented stricter measured-only rates) plus a `selected_usage_events` rows/counts-intact assertion, in a new `test_snapshot_canonical_fields_match_source_readers` [Agent 3 finding]
- `scripts/tests/test_feat3304_artifact_dashboard.py` — assert the policy version in `usage_coverage_audit`, the generated-table schema/allowlist lockstep, and that `PREDEFINED` selects token/cost qualification reasons and an explicit unavailable-vs-zero label. Under recorded Option C, do not add a page-stamp or manifest assertion; the existing page stamps and five-key payload stay unchanged.
- `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — no JS test runs `PREDEFINED` SQL or touches the usage tables (it queries `loop_runs` only; gated behind `LL_REQUIRE_NODE=1` via `TestDashboardNodeRuntimeGate`); add a case that runs the extracted usage query against the embedded snapshot, copying the `db.prepare(sql)` / `stmt.getColumnNames()` pattern, in the runtime test [Agent 3 finding]

### Documentation

- `docs/reference/API.md` (snapshot contract, policy version, custom-SQL guidance), `docs/reference/CLI.md` where snapshot figures are described.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — no section exists for `build_snapshot_db`, `_SHAREABLE_COLUMNS` or the generated tables; add the snapshot contract next to the `select_usage_coverage / select_usage_observations` section (its `selected_rows contains canonical-eligible rows only` paragraph is the statement this extends); ENH-3731 edits the same region, so expect an adjacent-edit collision, in `### select_usage_coverage / select_usage_observations` [Agent 2 finding]
- `docs/reference/CLI.md` — the `usage_events provenance columns (ENH-3580, allowlist version 2)` paragraph is already stale (code is at version 3; neither generated table is documented): update it and add the new version, in `#### ll-artifact dashboard` [Agent 2 finding]
- `docs/reference/CLI.md` — describe the policy version on `usage_coverage_audit` and the qualification columns under export scope. The `Stamped into the page` list stays unchanged under Option C.
- `docs/reference/CLI.md` — the intro says users "run arbitrary read-only SQL … plus predefined views" with no completeness guidance; add the "bare `SUM` of selected rows or NULLs does not establish completeness" note, in `#### ll-artifact dashboard` [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `artifacts.export` paragraph on `_SHAREABLE_COLUMNS` / `_SHAREABLE_ALLOWLIST_VERSION` (lines ~987–997); descriptive only, edit only if the policy version is mentioned alongside, in `#### artifacts.export` [Agent 1 + 2 finding]
- Audience rule: `docs/reference/` edits use end-user wording — no `scripts/tests/` or `scripts/little_loops/` paths (cite `little_loops.<module>`); gated by `scripts/tests/test_docs_audience_gate.py` [Agent 2 finding]
- `CHANGELOG.md` — no `[Unreleased]` entry; promoted at release prep (no edit here) [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/schema_manifest.json` / `SCHEMA_VERSION` (58) — no change: the generated tables are computed snapshot columns, not source-DB tables, and `session_store/schema.py` does not reference them [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Today `_snapshot_usage_selection` (`session_store/queries.py`) qualifies only on model-wide coverage (`non_overlapping`) plus per-column NULLs via `_SnapshotTotals.value(col, strict=True)`; it never consults provenance (`row_provenance`) or token-component admission, so partial/unknown rows reach `canonical_*`. `usage_coverage_audit` has 23 columns, none carrying a qualification label/reason/policy version (`coverage_reason` holds coverage reasons only).
- The snapshot DB has no `meta` table (CTAS does not copy it; see `cli/artifact/dashboard.py:schema_version_warning`). A policy version therefore has two possible homes — a stamp in dashboard template data (`build_dashboard_html`; must be declared in `templates/dashboard.llat/manifest.yaml` `data_schema`, and `TestTemplatePipeline::test_template_body_avoids_jinja_delimiters_in_inline_js` pins manifest keys vs `[[= x =]]`) or a table written inside the snapshot — the second is what lets a retained `.db` carry its own policy. Neither exists.
- `_SHAREABLE_COLUMNS` edits are pinned: `TestAllowlistVersionLockstep` (`test_feat3304_artifact_dashboard.py`) holds `PINNED_VERSION = 3` and a sha256 `PINNED_HASH` of `repr(sorted(_SHAREABLE_COLUMNS.items()))`; the generated-table keys `selected_usage_events` / `usage_coverage_audit` are inside that hash. Column additions bump `_SHAREABLE_ALLOWLIST_VERSION`, `PINNED_VERSION`, and `PINNED_HASH` together, plus fixture DDL.
- `test_enh3543_snapshot_usage.py` asserts `PRAGMA table_info` of both generated tables equals `_SHAREABLE_COLUMNS[...]` and that `{"source_path","turn_id","request_id","source_raw_event_id"}` are absent; its fixture seeds sentinels and byte-scans the snapshot. Reason text exported by this issue is not covered by any existing leak test, and the `"unclassified"` / 64-char sanitization in `_snapshot_usage_selection` has no test.
- Dashboard: the `PREDEFINED` "Usage cost by model and channel" query (`template.html.j2`) selects neither `coverage_reason` nor any qualification column; `test_predefined_usage_view_uses_qualified_audit` pins the substring `FROM usage_coverage_audit ORDER BY model, channel` and the absence of `FROM usage_events GROUP BY model`. The "Snapshot SQL" paragraph (`Custom SQL reads snapshot tables directly…`) currently tells users `selected_usage_events` is for "qualified accounting" — the guidance this issue corrects. `cli/artifact/dashboard.py` carries no usage-table logic; it changes only if a new template-data key is stamped.
- No JS runtime test touches the usage tables: `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` queries `loop_runs` only and never runs `PREDEFINED` SQL. `TestDashboardNodeRuntimeGate` skips unless `LL_REQUIRE_NODE=1`.
- Docs gap: `docs/reference/API.md` has no section for the snapshot tables, `build_snapshot_db`, or `_SHAREABLE_COLUMNS` (nearest is the `select_usage_coverage / select_usage_observations` section); `docs/reference/CLI.md` `ll-artifact dashboard` documents allowlist versions 1–2 only and no custom-SQL guidance. `selected_usage_events` / `usage_coverage_audit` appear nowhere in `docs/`.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Scope mismatch the implementer must resolve knowingly: `usage_coverage_audit.coverage` is the model-wide worst coverage (`model_coverage` in `_snapshot_usage_selection`), while `selected_usage_events.coverage` is the row's own identity-group coverage (`_coverage` annotation from `select_usage_coverage`, `history_reader/usage.py:375`). Any exported qualification label/reason on either table must state which scope it carries; the two scopes already differ today.
- `_snapshot_usage_selection` keys rows with its own `_key()` (NULL channel → `"unknown"`, NULL model stays `None`), whereas source readers use `row_channel` (NULL channel → `transcript` when a session id exists, else `live`) and `UNKNOWN_MODEL_BUCKET` (`cli/ctx_stats.py`). The "source and snapshot agree" criterion is only checkable if the key mapping is aligned or the divergence is documented.
- Known-value definitions differ: `_SnapshotTotals.add` treats a token as known only when it is a non-bool `int` ≥ 0 (cost: any non-bool number, negatives allowed); `ObservationGroup`/`_Component.add` (`token_provenance.py`) treats any non-None as known. Parity tests need a fixture row where the two disagree (negative or non-int token) or an explicit statement that it is out of scope.
- `session_store/queries.py` never reads `CoverageGroup.channel_subtotals` or `ObservationGroup.channel_subtotals()`; ENH-3731's "must not gain `cost_usd` — it feeds the ENH-3733 snapshot schema" constraint therefore guards a coupling with no consumer in the snapshot builder today. The snapshot's per-channel figures come solely from its own `_SnapshotTotals`.
- `selected_usage_events` exports `provenance` as the raw stored string (not via `row_provenance`), so NULL/unrecognized provenance is exported un-normalized beside any new normalized qualification label; the two must not contradict in the same row.
- Test-fixture constraint: only `test_enh3543_snapshot_usage.py::_source_db` (real `ensure_db()` migrations, native-id sentinels) can exercise the leak and `identity_basis` cases; `test_feat3304_artifact_dashboard.py::_build_history_db` uses hand-written DDL and tolerates absent provenance columns via `select_usage_coverage`'s `NULL AS col` substitution (`history_reader/usage.py:397`), whereas `_snapshot_select` intersects the allowlist with `PRAGMA table_info` — the generated-table builders do not use that intersection.

## Program Design

### Types

- `UsageQualification` — frozen dataclass planned in `little_loops.token_provenance` by ENH-3731 (eligibility, provenance label, bounded reason code, audit known/missing counts); not yet in source, so field names are consumed as ENH-3731 lands them.
- `_SnapshotTotals` — existing dataclass in `little_loops.session_store.queries` (`count: int`, `sums: dict[str, int | float]`, `missing: dict[str, int]`); today's only eligibility input for `canonical_*` columns.
- `_SHAREABLE_COLUMNS: dict[str, list[str]]` — gains qualification label/reason column names on `usage_coverage_audit` (and `selected_usage_events` only if row-level qualification is exported).
- `_SHAREABLE_ALLOWLIST_VERSION: int` — currently `3`; any `_SHAREABLE_COLUMNS` edit bumps it in the same commit.

### Signatures

- `_snapshot_usage_selection(conn: sqlite3.Connection, since: str | None) -> None` — only caller is `build_snapshot_db`; keeps its call to `select_usage_coverage(conn, since=since)` store-wide (no `channel=`).
- `build_snapshot_db(db: Path, dest: Path, *, tables: list[str], since: str | None = None, local_mode: bool = False) -> str | None` — return value stays the source schema version string.
- `select_usage_coverage(conn: sqlite3.Connection, *, since: str | None = None, require_run_id: bool = False, host: str | None = None, session_id: str | None = None) -> CoverageSelection` — supplies `CoverageGroup.audit_rows` / `selected_rows` that qualification is evaluated over.
- `qualify_usage(group: ObservationGroup, *, require_cost: bool = False, measured_only: bool = False) -> UsageQualification` — ENH-3731 API; the snapshot builds an `ObservationGroup` per in-filter contributor set and consumes its result.
- `ObservationGroup.channel_subtotals() -> dict[str, dict[str, Any]]` — must not gain `cost_usd`; it also feeds `CoverageGroup.channel_subtotals`.

### Call Path

`build_snapshot_db` -> `_snapshot_usage_selection` -> `select_usage_coverage` (overlap reconciled on the full identity group, then `since` applied) -> `ObservationGroup` / `qualify_usage` per model (channel contributions folded in, never certified alone) -> `usage_coverage_audit` insert via `_SHAREABLE_COLUMNS["usage_coverage_audit"]`.

Dashboard side: `build_history_payload` -> `build_snapshot_db`; the browser runs `PREDEFINED` SQL in `template.html.j2` against the snapshot, selecting the new qualification label/reason/policy-version columns. No new page-stamp key (policy version rides the `usage_coverage_audit` column — Option C).

### Decision Rules

N/A — no new decision logic; the qualification policy (eligibility, reason precedence, measured-only rates) is defined by ENH-3731 and consumed unchanged here. This issue adds only the mapping of that result into snapshot columns/metadata.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- Contract mismatches between this issue and ENH-3731's planned `qualify_usage` (reconcile before coding; field names stay provisional until ENH-3731 lands):
  - **Admission granularity**: ENH-3731 admission is row-level (all four `TOKEN_COLUMNS` non-NULL) and cost is a separate `require_cost` call; the snapshot gates each `canonical_*` column independently today (`canonical and not model_known.missing.get(col)`), so input can be non-NULL while cache_creation is NULL. Under the shared policy the four token `canonical_*` columns become NULL together — an intended behavior change that existing expectations (`canonical_input_tokens` 7/8 in `test_shareable_snapshot_keeps_known_rows_and_audit_without_claiming_overlap`) must be re-derived against.
  - **Input group**: `qualify_usage` takes coverage from `group.coverage()`, i.e. from the `_coverage` labels on rows added. A group built from `selected_rows` is always `non_overlapping` and loses the unresolved sibling groups that taint a model today; a group built from `audit_rows` keeps them but also folds non-selected rows into admission/provenance. The group the snapshot builds per model must preserve model-wide coverage taint while qualifying only in-filter contributors.
  - **Rates**: `usage_coverage_audit` has no rate or cache-rate column, so the "zero denominator → unavailable" and "stricter measured-only rates" criteria have no snapshot figure to attach to unless one is added (which is an allowlist change) — decide whether those criteria bind the snapshot or only the source readers.
  - **`mixed` label**: ENH-3731 says `mixed` is an aggregate label that is never stored; the exported label column is a derived value in a retained artifact. State which label vocabulary (`measured`/`estimated`/`unknown`, with or without `mixed`) is allowed in the column.
  - **Reason text**: the snapshot reads `CoverageGroup.reason` (a single snake_case token), not `ObservationGroup.coverage_reason()` (joined with `"; "`, can be prose). Exported reasons pass through the inline sanitizer in `_snapshot_usage_selection` (ASCII, `[A-Za-z0-9_]`, `[:64]`, else `"unclassified"`, joined `","` sorted); a `"; "`-joined or prose reason would silently collapse to `"unclassified"`. ENH-3731's planned codes (`empty_selection`, `missing_token_component`, `unknown_provenance`, `unpriced_contributor`, `not_measured`) pass the sanitizer. The sanitizer is the only copy in the repo and has no test.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/session_store/queries.py` — add each new qualification column to the `_SHAREABLE_COLUMNS` list, the `CREATE TABLE snap.usage_coverage_audit` DDL and the positional `audit_rows.append` tuple in `_snapshot_usage_selection`, keeping column order identical across all three
- Policy-version home is decided (Option C): a policy-version column on `usage_coverage_audit`, added in the same three-place edit as the label/reason columns; no page-stamp, template-data or `HistoryPayload` change, no new table (the page-stamp and in-snapshot-table alternatives were rejected — see `### Decision Rationale`)
- Bump `_SHAREABLE_ALLOWLIST_VERSION`, `PINNED_VERSION` and `PINNED_HASH` together in one commit (`test_feat3304_artifact_dashboard.py::TestAllowlistVersionLockstep`)
- Update `scripts/little_loops/templates/dashboard.llat/template.html.j2` — `PREDEFINED` usage query emits qualification label/reason and an explicit unavailable-vs-zero text label (NULL renders as an empty cell in `renderTable`); keep the pinned `FROM usage_coverage_audit ORDER BY model, channel` and `raw observations for audit` substrings or update `test_predefined_usage_view_uses_qualified_audit` in the same change; correct the "Snapshot SQL" paragraph; add no new `[[% %]]` block
- Update `scripts/tests/test_enh3543_snapshot_usage.py` — extend the `_source_db` `insert` closure with `cache_creation`/`provenance`/cost parameters; add partial-row, window, empty/zero, channel-recertification, reason-leak and source-vs-snapshot parity tests
- Update `scripts/tests/test_feat3304_artifact_dashboard.py` and `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — audit-table policy-version/allowlist assertions and a runtime case that runs the usage `PREDEFINED` query; no new page stamp, manifest field or history payload key
- Update `docs/reference/API.md` (snapshot contract section) and `docs/reference/CLI.md` (`ll-artifact dashboard`: stale allowlist-version-2 paragraph, audit-table policy version, custom-SQL completeness note), using end-user wording per the docs-audience gate

## Acceptance Criteria

- [ ] Source and snapshot canonical fields agree under the shared policy; audit-only partial rows keep raw values and audit subtotals with unavailable canonical token/cost figures and a visible reason.
- [ ] Source and snapshot preserve coverage reconciliation before report filters; an excluded overlapping counterpart cannot make the remaining group canonical; empty selection is unavailable/empty while a qualified all-zero returns zero. Stored-session rate/zero-denominator parity is tested without adding a snapshot rate column.
- [ ] Snapshot export carries safe model-scoped qualification label, token/cost reasons and the shared result’s policy version, passes allowlist/privacy tests, and introduces no native IDs, source paths or credentials; coverage-selected rows/counts remain intact with qualification evaluated separately; dashboard unavailable/zero display and bounded reason codes agree with the snapshot values; no new JSON payload/provenance-pointer surface is required.
- [ ] Built-in snapshot/dashboard aggregates preserve the requested population, show qualification/reasons and distinguish empty/unavailable from observed zero; model/channel aggregates cannot recertify an incomplete model; custom-SQL guidance documents that arbitrary subset sums don't certify totals, with no SQL rewriting or new query engine.
- [ ] Source readers, built-in snapshots/dashboard and the stored session reader agree, allowing only documented stricter measured-only rates; derived sums preserve missingness.
- [ ] NULL model/channel parity uses the documented logical mapping; derived mixed labels are permitted, raw row provenance remains intact, invalid values cannot create a canonical subset, tokens can qualify independently of cost, and legacy/empty snapshot policy-version behavior is explicit.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — required before remaining-host observations reach snapshots/dashboard.
- **Effort**: Medium to large — generated-table metadata, shared qualification and dashboard/documentation changes.
- **Risk**: Medium — bucket labels and allowlist version change; retain raw evidence and explain expected unavailable figures.

## Scope Boundaries

- **Out of scope:** qualification core and source readers (ENH-3731), selector `channel=` scope (ENH-3748), quality (ENH-3732), a source-history migration, rewriting custom SQL, ENH-3730's gate redesign.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- ENH-3731 is open and `qualify_usage` / `UsageQualification` are absent from `scripts/`. It leaves `queries.py` edits to this issue; ENH-3748's default `channel=None` preserves the immediate baseline's coverage policy/population, allowing BUG-3735's intentional scoped-filter correction. The shared `ObservationGroup.channel_subtotals()` shape gains no `cost_usd`; snapshot costs use their own totals and qualification, so there is no shared-subtotal schema dependency to invent. This issue intentionally adds the chosen qualification columns and audit-table policy version. `test_usage_selection_chokepoint_gate.py` constrains SQL string constants naming token/cost columns beside `FROM usage_events`.
- Conventions in force (evidence, not templates): reason codes are plain lowercase snake_case literals with no shared enum or prefix (`history_reader/usage.py:_classify_coverage`, `token_provenance.py`); a retained export carries versions only as page stamps, never as an in-DB `meta` row (`cli/artifact/dashboard.py:schema_version_warning`); source-DB schema changes are append-only `_MIGRATIONS` entries paired with `SCHEMA_VERSION` (currently 58) and `schema_manifest.json`, guarded by `TestSchemaManifest` — computed snapshot columns need none of this. Two fixtures disagree: `test_enh3543_snapshot_usage.py::_source_db` uses real `ensure_db()` migrations and seeds native-ID sentinels; `test_feat3304_artifact_dashboard.py::_build_history_db` uses hand-written DDL without `source_path`/`identity_basis` — only the former can exercise the leak case.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-04 (re-scored 2026-10-04)_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies hard override)
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Criterion 4 (15/20): consumed API (`qualify_usage` / `UsageQualification`) does not exist in `scripts/little_loops` yet, so the Program Design field names are provisional.
- Resolved by **Resolved consumer contract**: derived `mixed` labels are allowed, rate checks apply only to session-reader parity, and computed buckets use `row_channel`/`UNKNOWN_MODEL_BUCKET`. Earlier research questions are historical findings, not choices left to the implementer. No new readiness score is claimed.

### Gaps to Address
- **Unresolved dependency (hard override):** `blocked_by: ENH-3731` is `open` — `qualify_usage` / `UsageQualification` are still absent from source. Land ENH-3731 first (or remove the dependency if it no longer applies), then re-run.

### Outcome Risk Factors
- Broad enumeration across ~6 source/template/doc sites plus a coordinated test sweep (hash/version lockstep, pinned dashboard substrings, `PRAGMA table_info` order).
- Moderate per-site complexity: qualification is evaluated on in-filter contributors after full-identity-group overlap reconciliation, with model/channel scope rules that cannot recertify an incomplete model.

## Session Log

- Pre-implementation epic review - 2026-10-05 - Removed active page-stamp/manifest directives that contradicted recorded Option C, aligned tests/docs with the audit-table policy version, and marked the already resolved vocabulary/rate/bucket concerns as resolved. Source numeric audit safety remains ENH-3731's handoff; no new readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Resolved model-wide audit contributor scope, logical bucketing, derived labels, independent token/cost reasons, numeric validity and shared policy version. Kept Option C and scoped rate criteria to session-reader parity, without new snapshot rates or payload fields. Opus confidence 0.74; its empty-snapshot stamping dissent was not adopted because the recorded decision needs no new table/payload and an empty snapshot carries no figures. Added Impact; fresh confidence required after ENH-3731.

- `/ll:confidence-check` - 2026-10-05T04:41:52 - `a3a2850e-1859-4131-baf9-41bae51155b8.jsonl`
- `/ll:verify-issues` - 2026-10-05T04:40:12 - `faddfe34-ee99-446f-9e12-f81bfea56f96.jsonl`
- `/ll:decide-issue` - 2026-10-05T04:38:16 - `727b64ff-a77b-4d8b-9c8c-afabeceeda4b.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T04:33:31 - `6d396473-5fc6-4381-8b30-58b5f06aa040.jsonl`
- `/ll:confidence-check` - 2026-10-05T04:27:46 - `a146c9c4-1b4b-4d4f-9052-ad3e3745a066.jsonl`
- `/ll:wire-issue` - 2026-10-05T04:23:20 - `1b404432-b825-49eb-bd3d-99651e25e458.jsonl`
- `/ll:refine-issue` - 2026-10-05T04:16:01 - `688a8bf8-c000-4ab4-a82d-b83b98aa3a6a.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2

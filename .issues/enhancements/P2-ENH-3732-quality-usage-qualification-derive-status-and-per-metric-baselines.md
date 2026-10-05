---
id: ENH-3732
type: ENH
title: Quality usage qualification, session derive status, and per-metric baselines
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
blocked_by:
- ENH-3731
- BUG-3736
relates_to:
- ENH-3733
- ENH-3730
- BUG-3735
- ENH-3543
verify_verdict: VALID
confidence_score: 70
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Large
---

# ENH-3732: Quality usage qualification, session derive status, and per-metric baselines

## Summary

Make the agent-quality report obey the shared usage qualification policy. This child scopes quality acquisition to the transcript channel, adds a member-local read-only per-session derive-status helper (with workspace map injection), carries nullable token/cost numerators with per-metric qualification, and replaces the zero-as-unmeasured baseline proxy in `quality_regressions` with explicit all-measured trend eligibility. Blocked by ENH-3731 (`qualify_usage` and the `channel=` selector scope) and BUG-3736 (preserve retained usage and prevent pruning underived candidates).

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. Parent Decision (commit `01747bb96`) items 2, 3, 4 and 5 apply: quality baselines/verdicts require an all-`measured` composition; the 5 phantom zero baselines and 9 unknown-containing windows (all 7 non-stable verdicts) become unavailable with a reason; underived in-scope sessions make their window unavailable; do not change `_rate_metrics`' absence-equals-zero default (correction/fix/retry counts depend on it) — pass usage qualification in separately.

## Current Behavior

`agent_quality._usage_totals` reads annotated audit rows, ignores qualification and coerces missing components to zero: a partial/unknown row with stored cost $1 yields `tokens: 16`, `cost: 1`, `priced_rows: 1`, `total_rows: 1`. `_rate_metrics` makes a five-closed-issue window with no usage numerator a `0.0`, `stable` baseline that later priced windows are compared against. `_metric_eligible_as_baseline` rejects observed zeros, so `[10, 0, 10]` with two prior baselines produces no regression (complete mean would be `5`). A verified complete measured transcript row is coverage-selected only until an unrelated unidentified live row trips the store-wide ambiguity gate; quality's later channel filter cannot undo that annotation. Workspace quality exposes raw/usage union views but no member-local derive proof, so a bare `meta` read on the union resolves to an attached member.

## Expected Behavior

- **Transcript scope:** quality requests `channel="transcript"` from the selectors (added in ENH-3731). Excluded live/rollout counterparts cannot change values, qualification or model-composition inputs. Within scope, unknown/partial/unresolved contributors stay as completeness contributors and the same coverage/qualification rules apply. Text/JSON and metric definitions state the transcript-only numerator, that Codex rollout/live work is excluded, and that the closed-issue denominator is unchanged.
- **Derive completeness:** `select_session_derive_status(conn, session_ids) -> dict[str, SessionDeriveStatus]` in `history_reader/usage.py`, read-only over committed `raw_events` and the member's `meta.usage_derive_version`/`usage_derive_raw_id`. It never stats source files, calls `usage_source_freshness`, requires source cursors or re-derives; it reuses the deriver's version constant. Every requested session gets a status (missing proof cannot omit a key). Dispositions:

  | Attributed-session evidence | Disposition |
  | --- | --- |
  | No in-scope observations/candidates and evidence positively proves only excluded channels | `out_of_scope`; ignored for this numerator, denominator unchanged |
  | In-scope raw evidence, missing/invalid checkpoint or absent/mismatched derive version | Unavailable: `derive_pending` |
  | In-scope raw evidence with session-local max raw ID above the member checkpoint | Unavailable: `derive_lagging` (unrelated sessions' later IDs do not taint it) |
  | Retained raw may contain in-scope usage, but its contract/channel/candidate rule or logical key is unproved | Unavailable: `derive_status_unavailable`; an unregistered host/version is not proved non-usage |
  | Any proved logical usage candidate lacks a corresponding in-scope observation | Unavailable: `derive_gap`, even when other observations exist in that session |
  | In-scope usage observations and all preceding checks pass | Apply shared row qualification and coverage (legacy/as-of usage stays qualified even without retained raw/cursors) |
  | Fully covered, recognized raw proves only non-usage records, with no in-scope observations | `derived_no_usage` (contributes nothing, not an observed zero) |
  | Neither raw nor usage evidence, or unreadable evidence for an in-population session | Unavailable: `no_evidence` / `derive_status_unavailable` |

  Any unavailable session blocks the usage-derived figures of every window it is fractionally attributed to. A window with zero in-scope observations stays `no_observations`. Keep these codes namespaced apart from the source-freshness `derive_pending` in `session_store/lifecycle.py`.
- **Per-metric qualification:** propagate `None` through optional numerators; a qualified observed zero is zero; no observations or unmet prerequisites are unavailable. Cost cannot qualify on a partial priced subset, even above the legacy 50% verdict threshold. Preserve `sample_size`, fractional attribution and coverage diagnostics. Qualification, sample insufficiency and trend eligibility are separate metadata; `insufficient_history` keeps meaning only the sample gate failed. Estimated/mixed numeric values carry labels and a reason explaining why they have no verdict. `_format_metric_line` must render sample-sufficient unavailable metrics without asserting a number.
- **Baselines/verdicts:** select the earliest qualified, sample-sufficient, all-measured baseline independently for tokens and cost (not the earliest closed-issue window). Replace `_ZERO_INELIGIBLE_BASELINE_METRICS` for usage metrics with explicit eligibility; a measured `[10, 0, 10]` series with two prior baselines includes the zero (mean `5`, relative increase `1.0`) while the zero-**mean** division guard stays. Keep `_rate_metrics`/`classify_verdict` zero-baseline behavior and regression-window/model-composition rules otherwise. Label the period of any older eligible result; never present it as a verdict for an unavailable latest window.
- **Workspace:** compute derive status per member on the already-open read-only connections, merge conservatively across members in which a session participates (retain any unavailable member's reason; excluded-channel-only members contribute nothing; a member with no association does not invent a missing status), and inject the map via `analyze_agent_quality(..., derive_status: Mapping[str, SessionDeriveStatus] | None = None)`. `None` computes locally; a supplied map is authoritative, missing keys fail closed, and there is no fallback to unqualified `meta` on the union. Never compare raw IDs/checkpoints across members. Keep repository/issue discriminators, TEMP union views and `_UNION_RELATIONS`.

## Proposed Solution

Introduce immutable `SessionDeriveStatus` (bounded status/reason, in-population disposition; no raw IDs or paths in serialization), extend `QualityMetric` with defaulted qualification/provenance/reason/trend-eligibility fields preserving existing keys and non-usage callers, and assemble quality windows in order: declared scope → coverage → session derive status → complete per-window population → per-metric qualification/value → baseline/verdict.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` and `history_reader/__init__.py` — `select_session_derive_status`, `SessionDeriveStatus` (re-export).
- `scripts/little_loops/issue_history/agent_quality.py` — `_usage_totals`, `_rate_metrics`, `QualityMetric`, callers, metric definitions, text/JSON diagnostics, `_format_metric_line`, `derive_status` parameter.
- `scripts/little_loops/issue_history/quality_regressions.py` — all-measured target/baseline eligibility, replace the usage zero-as-missing exclusion, keep the zero-mean guard and model-composition inputs on the transcript/legacy population.
- `scripts/little_loops/issue_history/workspace_quality.py` — member-local status and merged map injection.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/agent_quality.py` — module docstring "Resolved attribution decisions" item 3 ("tokens per issue has no such gate because it needs no pricing-table lookup") must be reworded in the module docstring [Agent 2 finding]
- `scripts/little_loops/issue_history/agent_quality.py` — `_STANDARD_NOTES` ("Cost verdicts are suppressed below 50% priced coverage; tokens per issue is unaffected by pricing-table gaps.") renders on every report and in the JSON `notes` array; add the transcript-only numerator / unchanged-denominator statement in `_STANDARD_NOTES` [Agent 2 finding]
- `scripts/little_loops/issue_history/agent_quality.py` — `_definitions` `cost_per_issue` `verdict_band` plus first caveat ("withholds the verdict, not the number") and `tokens_per_issue` caveat ("Always computable -- no pricing-table dependency") must change in `_definitions`; fit wording into the existing 8 `MetricDefinition` fields — a new field would also reach `rework.py`'s payload path [Agent 2 finding]
- `scripts/little_loops/issue_history/agent_quality.py` — `format_agent_quality_json` / `format_agent_quality_yaml` dump `QualityAnalysis.to_dict()` unfiltered, so new `QualityMetric` keys reach `ll-history quality --format json|yaml` and the workspace `per_repo[*]`/`totals` payloads automatically; conditionally add usage-only keys when set (new contract for `issue_history`; the precedent is `history_reader.usage._provenance_fields`) in `QualityMetric.to_dict()` [Agent 2 finding]
- `scripts/little_loops/issue_history/agent_quality.py` — `_quality_text_body` iterates `_METRIC_LABELS` into `_format_metric_line` and renders `_STANDARD_NOTES`/`_REGRESSION_NOTES` verbatim; the text and markdown regression lines print `skipped_zero_baseline=` literally, in `_quality_text_body` [Agent 2 finding]
- `scripts/little_loops/issue_history/quality_regressions.py` — `_metric_eligible` (`not insufficient_history and verdict is not None`) gates **targets** as well as baselines; the all-measured eligibility must cover the target side too, in `_metric_eligible` [Agent 2 finding]
- `scripts/little_loops/issue_history/quality_regressions.py` — `load_window_compositions` host dimension (`SELECT session_id, host, COUNT(*) FROM raw_events ... GROUP BY session_id, host`) has no channel/transcript filter, unlike the model dimension just above it; retain and label the broader all-raw host diagnostic, keeping it outside usage qualification, in `load_window_compositions` [Agent 2 finding]
- `scripts/little_loops/issue_history/quality_regressions.py` — `detect_quality_regressions` retry-inflation branch (`RetryWindow`) shares the `skipped_zero_baseline` counter with the usage branch; keep the retry branch's zero-baseline behavior unchanged while replacing the usage exclusion, in `detect_quality_regressions` [Agent 2 finding]
- `scripts/little_loops/issue_history/quality_regressions.py` — module docstring and the comment above `_ZERO_INELIGIBLE_BASELINE_METRICS` ("not 'free', just unmeasured") describe the proxy being replaced; update in the module docstring [Agent 2 finding]
- `scripts/little_loops/history_reader/usage.py` — resolve `_USAGE_DERIVE_VERSION` through the `lifecycle` module attribute at call time (not `from ... import` at import time) so `monkeypatch.setattr(lifecycle, "_USAGE_DERIVE_VERSION", ...)` in tests is seen, and import it lazily inside `select_session_derive_status`: `session_store/queries.py` already imports `history_reader.usage` lazily in the opposite direction, to avoid binding the private version at import time [Agent 2 finding]
- `scripts/little_loops/issue_history/workspace_quality.py` — new member-status code placed after `_open_member_readonly` must not contain `ensure_db(`, `_connect_readonly(` or `immutable=1` and must keep `mode=ro` (source-text check `test_never_uses_migrating_opener`), and must not add a raw `sqlite3.connect(` (`test_history_store_chokepoint_gate.py` allowlists only the `:memory:` scratch connections), in `aggregate_history_dbs` [Agent 3 finding]

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `writers.py`, `claude_usage.py` — read the derive-version/checkpoint and producer-contract definitions; factor/re-export a constant only if needed. No derive-algorithm, source-freshness, producer-contract or migration change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/history.py` — `quality` branch of `main_history`: workspace path calls `aggregate_history_dbs(...)` (status map built inside it, no CLI change); single-repo path calls `analyze_agent_quality(all_issues, db=db_path, ...)` with no `conn`/`derive_status`, so `None` → local compute; it opens the DB via `_connect_readonly`, which migrates, so the local-compute path reads `meta` on a migrated connection, in `main_history` [Agent 1/2 finding]
- `scripts/little_loops/issue_history/__init__.py` — re-exports `QualityMetric`/`QualityAnalysis`/`QualityWindow`/`analyze_agent_quality`/`aggregate_history_dbs`; no new export needed unless `SessionDeriveStatus` is surfaced at this level (it lives in `history_reader`), in `__all__` [Agent 1 finding]
- `scripts/little_loops/issue_history/rework.py` — shares `MetricDefinition`, `LOW_COVERAGE_THRESHOLD` and the windowing/verdict helpers in `_utils.py` with `agent_quality.py`; shared-helper edits must not change rework output, in `LOW_COVERAGE_THRESHOLD` [Agent 1/2 finding]
- `scripts/little_loops/session_store/usage_refresh.py` — deletes `meta.usage_derive_version`/`usage_derive_raw_id` during a per-source refresh, so those keys are absent until the next derive: the real-world source of the `derive_pending` (missing checkpoint) disposition, in `refresh_usage_source` [Agent 2 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `prune` deletes `raw_events` rows with `compacted = 1` older than a cutoff while `usage_events` survive; a session with pruned raw rows must still resolve as qualified legacy/as-of usage (not `no_evidence`), in `prune` [Agent 2 finding]
- `scripts/little_loops/issue_history/workspace_activity.py` — imports `_gate_member`/`_label` from `workspace_quality`; no `analyze_agent_quality` call, so untouched unless those helpers' signatures change, in `_gate_member` [Agent 1 finding]

### Tests

- `scripts/tests/test_issue_history_agent_quality.py` (also holds quality-regression tests), `test_feat3410_workspace_quality.py`, `test_feat3418_workspace_quality.py`. Query-only status cases: missing/version-mismatched checkpoint, session-local lag, recognized positive contract without derived usage, fully derived non-usage raw, no evidence, source loss. Workspace tests use overlapping raw IDs and different member checkpoints, proving neither an eligible member nor the first attached `meta` can certify an underived member. Drive actual consumers, not just helpers.

_Wiring pass added by `/ll:wire-issue`:_

Tests that will break or change (update deliberately):
- `scripts/tests/test_issue_history_agent_quality.py` — `_usage_event` fixture writes NULL provenance (reads as `unknown`); add a provenance parameter/measured variant, in `_usage_event` [Agent 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — asserts numeric values/coverage from `unknown` rows and will change under all-measured qualification, in `TestCostAndTokensPerIssue::test_live_codex_thread_identity_does_not_change_transcript_cost` (`2.0/5`, `150/5`), `TestCostAndTokensPerIssue::test_cost_and_tokens_split_evenly_across_multi_issue_session` and `TestCostAndTokensPerIssue::test_fully_priced_window_reports_full_coverage` (`coverage == 1.0`, `stable`) [Agent 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — composition tests built on `_usage_event`; survive if composition stays on the transcript/legacy population, in `TestAttribution::test_model_mix_shift_coincides_with_drop_attributes_model` and `TestAttribution::test_unchanged_model_mix_attributes_none`; `TestAttribution::test_model_share_weighted_by_row_count` is the existing transcript-scope control (live/rollout NULL-token rows) [Agent 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — `assert metric.value is not None` replacement must keep the empty-analysis render passing, in `TestFormatting::test_text_and_markdown_render_without_error_on_empty` [Agent 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — `len(analysis.definitions) == 4` breaks if a metric definition is added/removed, in `TestEmptyAndMissingDb::test_empty_db_returns_empty_analysis`; same count assertion in `scripts/tests/test_cli_history.py::TestHistoryQualitySubcommand::test_quality_json_format_routes_to_json_formatter` (`len(payload["definitions"]) == 4`) [Agent 2/3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — asserts a `"correlational"` note survives in the JSON `notes` array (also in `test_issue_history_rework.py`); keep that wording when editing `_STANDARD_NOTES`, in `TestFormatting::test_json_round_trips_window_fields` [Agent 2 finding]
- `scripts/tests/test_feat3418_workspace_quality.py` — compares `totals.to_dict()` with `per_repo[...].to_dict()`; breaks if the injected map makes union output differ from a single member's, in `TestTotalsEdgeCounts::test_one_member_totals_equals_its_per_repo_entry` [Agent 3 finding]
- `scripts/tests/test_feat3418_workspace_quality.py` — asserts temp-view names equal `set(_UNION_RELATIONS)`; breaks only if `meta` were added to `_UNION_RELATIONS` (the issue says keep it), in `TestUnionViewCoverage::test_nine_temp_views_and_summed_counts` [Agent 2/3 finding]
- `scripts/tests/test_feat3410_workspace_quality.py` — source-text check on code after `_open_member_readonly`, in `TestSourceDbUntouched::test_never_uses_migrating_opener` [Agent 2/3 finding]
- `scripts/tests/test_usage_selection_chokepoint_gate.py` — AST scan flags `FROM usage_events` strings naming a token/cost column outside the allowlist; `select_session_derive_status` must read `raw_events`/`meta` or `usage_events` without those columns, in `test_no_token_or_cost_reads_outside_the_chokepoint` [Agent 2/3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — flags any new raw `sqlite3.connect(` outside its allowlist, in `test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist` [Agent 3 finding]

Existing coverage to keep green (derive-checkpoint and freshness code paths this issue reads but must not change):
- `scripts/tests/test_session_store_incremental_usage.py` — `test_normalizer_version_change_replays_historical_rows` (monkeypatches `lifecycle._USAGE_DERIVE_VERSION`), `test_claude_slices_keep_last_valid_message_snapshot_and_match_rebuild` (reads `meta.usage_derive_raw_id`), `test_catchup_failure_rolls_back_rows_and_checkpoint` [Agent 3 finding]
- `scripts/tests/test_session_store_usage_refresh.py` — `test_refresh_recovers_stripped_usage_and_rebuild_is_stable` (hand-inserts `meta.usage_derive_version='old'`) [Agent 3 finding]
- `scripts/tests/test_enh3549_codex_usage_refresh.py` and `test_backfill_worker_usage_trigger.py` — source-freshness `derive_pending`; the new reason codes must stay namespaced apart from it [Agent 3 finding]

New tests to write:
- `scripts/tests/test_enh3732_session_derive_status.py` (new) — `select_session_derive_status` cases, templated on `test_enh3678_rebuild_derive_gate.py::TestRebuildNeeded` (frozen-dataclass `AttributeError`, fail-safe on missing `meta`, byte-identical read, `_set_meta`/`_drop_meta`/`_meta` helpers) and `connect_readonly` for a real `query_only` connection. Fixture sources: `backfill_raw_events`/`backfill_usage_incremental`/`rebuild` with `scripts/tests/fixtures/claude/transcript-v2.1.284.jsonl` (positive `usage_contract`); `derive_gap` by `DELETE FROM usage_events WHERE channel = 'transcript'` after ingest; `test_enh3528_token_provenance.py::_insert(db, **row)` for measured/partial/unknown/live rows. Also assert `usage_source_freshness` is never called (monkeypatch to raise), every requested session gets a key, and an unrelated later raw ID does not taint a session [Agent 3 finding]
- `scripts/tests/test_enh3732_session_derive_status.py` (new) — `history_reader` export check (`select_session_derive_status`, `SessionDeriveStatus` in `__all__` and `hasattr`), copying `test_enh3678_rebuild_derive_gate.py::TestFrozenLegacyPins::test_package_exports`; no `history_reader` `__all__` test exists today [Agent 3 finding]
- `scripts/tests/test_feat3418_workspace_quality.py` — workspace derive-status cases (colliding raw IDs, differing member checkpoints, shared-session merge, out-of-scope-only member, no-association member, member file hash unchanged); reuse `_member_with_closed_issue` (shared bare `issue_id`), `_bare_member`, `<name>-history.db` naming (dodges the autouse `_isolate_history_db` fixture); neither workspace test file has `raw_events`/`meta`/usage fixtures yet [Agent 3 finding]
- `scripts/tests/test_cli_history.py` — `quality` CLI text/markdown/JSON output with usage data (existing `TestHistoryQualitySubcommand` covers only argv routing on an empty DB); patch `sys.argv`/`Path.cwd`, call `main_history()`, parse `capsys`, per `test_quality_json_format_routes_to_json_formatter` [Agent 3 finding]
- `scripts/tests/test_issue_history_agent_quality.py` — new classes: partial/unknown stored-cost row; `[10, 0, 10]` → mean 5 / relative increase 1.0 and all-zero mean → `skipped_zero_baseline`; independent per-metric baseline selection; older-result period label; estimated/mixed label+reason; sample-sufficient `value=None` rendered in text/markdown/JSON; `to_dict()` keeps its 7 keys; transcript scope with live/rollout counterparts incl. `load_window_compositions`; injected `derive_status` authoritative with missing key failing closed; `_rate_metrics` absence-equals-zero retained. No test currently drives `backfill_raw_events`/`rebuild` into `analyze_agent_quality` — one end-to-end production-writer test is a gap [Agent 3 finding]

### Documentation

- `docs/reference/API.md`, `docs/reference/CLI.md` — update metric definitions that currently say tokens are always computable or price coverage withholds only the verdict.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-history quality` "Metric definitions" bullets (cost per issue: "suppresses the verdict (not the number) when coverage < 0.5"; tokens per issue: "Always computable ... no coverage gate") in `ll-history quality` [Agent 2 finding]
- `docs/reference/CLI.md` — "Regression detection and attribution (FEAT-3405)" bullet 2 (`value == 0.0` window "never usable *as* a baseline", ~line 3799) states the zero-as-missing rule being replaced, in `Regression detection and attribution (FEAT-3405)` [Agent 2 finding]
- `docs/reference/CLI.md` — "Cross-repo workspace aggregation" bullets describe `#r{i}` discriminators and skip conditions only; add the member-local derive-status / conservative merge note, in `Cross-repo workspace aggregation` [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — "Quality Metric Definitions" table, Cost per issue row (~528, "suppresses the verdict, not the number") and Tokens per issue row (~529, "Always computable"), in `Quality Metric Definitions` [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — "Why cost coverage matters" paragraph and the "Rework and agent-quality trends" workspace paragraph ("the same per-window analysis once per member"), in `Why cost coverage matters` [Agent 2 finding]
- `docs/reference/API.md` — issue-history table rows `analyze_agent_quality(...)` (signature lacks `derive_status`) and `aggregate_history_dbs(...)` (no mention of per-member derive status), in `little_loops.issue_history` [Agent 2 finding]
- `docs/reference/API.md` — `## little_loops.history_reader` hand-maintained import block and `### select_usage_coverage / select_usage_observations` section (~8946) are the home for `select_session_derive_status` / `SessionDeriveStatus`; keep the `## little_loops.history_reader` heading (pinned by `test_wiring_reference_docs.py`), in `little_loops.history_reader` [Agent 2/3 finding]
- `scripts/little_loops/history_reader/__init__.py` — module docstring (~lines 82–83 list `select_usage_coverage`/`select_usage_observations`), the re-export block (~271) and `__all__` (~363) must all add the new names; `usage.py` also carries its own `__all__` (~44), in `__all__` [Agent 1 finding]
- `scripts/little_loops/issue_history/__init__.py` — module docstring one-line summaries for `analyze_agent_quality`/`detect_quality_regressions`/`aggregate_history_dbs`, in the module docstring [Agent 2 finding]
- `scripts/little_loops/pricing.py` — docstring says `ll-history quality`'s cost-coverage gate remains required; reword if the gate semantics change, in the module docstring [Agent 2 finding]
- `docs/ARCHITECTURE.md` — ~756 ("History DB: Producer→Consumer Flow") has no "always computable"/"withholds the verdict" wording (full-file grep found none); the doc edit this issue calls for there is likely a no-op beyond mentioning quality's derive-status read [Agent 2 finding]
- All doc edits must follow the end-user audience rule (`test_docs_audience_gate.py`): use `ll-history quality` and reader-shaped paths, no `scripts/tests/` or `scripts/little_loops/` paths in `docs/guides/` or `docs/reference/` [CLAUDE.md]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Prerequisite surfaces are absent from source.** `qualify_usage`, `UsageQualification`, `channel=` on the selectors, and every ENH-3732 name (`SessionDeriveStatus`, `select_session_derive_status`, `derive_lagging`, `derive_gap`, `derived_no_usage`, `derive_status_unavailable`, `no_observations`) are absent from source (searched repo-wide excluding `.issues/**`). Existing vocabulary to build on: `token_provenance.py` `row_provenance`/`row_channel`/`ObservationGroup` (`.coverage()`, `.aggregate_provenance()`, `.total()` → `None` on missing components) and the `_coverage`/`_coverage_reason` annotations `select_usage_coverage` (`history_reader/usage.py:375`) attaches to audit rows. Quality consumes none of them today.
- **`_usage_totals`** (`agent_quality.py:305`) calls `select_usage_observations(conn)` with no arguments, filters `channel in (None, "transcript")` in Python afterwards, ignores `provenance`/`_coverage`, and coerces NULL components to `0` (`(input or 0) + ...`). Bucket shape `{"cost","tokens","priced_rows","total_rows"}` is asserted verbatim by `test_enh3532_codex_rollout_usage.py::test_cost_per_issue_remains_transcript_only`, which imports it directly.
- **`_rate_metrics`** (`agent_quality.py:385`) is called only from `analyze_agent_quality` (three sites: `correction_rate`, `cost_per_issue`, `tokens_per_issue`). Per orchestrator, `baseline_key` is the first window with `closed >= min_sample` (earliest closed-issue window, not earliest qualified). `numerator.get(key, 0.0)` makes absence a zero; that default is load-bearing for correction/fix/retry and must not change. Coverage < `LOW_COVERAGE_THRESHOLD` (0.5, from `rework.py`) nulls the verdict but keeps the value.
- **`QualityMetric`** (`agent_quality.py:80`) is a mutable dataclass with 7 positional fields (`name, value, sample_size, verdict, baseline_period, insufficient_history, coverage`) built positionally at five call sites (`_fix_rate_metrics` ×3, `_rate_metrics` ×2); `to_dict()` emits exactly those 7 keys. New fields must be trailing and defaulted, and existing keys must keep their names.
- **`_format_metric_line`** (`agent_quality.py:610`) and the markdown `cell()` in `_quality_markdown_body` both `assert metric.value is not None` outside the `insufficient_history` branch — a sample-sufficient `value=None` metric currently raises `AssertionError` in text/markdown output.
- **`quality_regressions.py`**: `_ZERO_INELIGIBLE_BASELINE_METRICS` (`:53`), `_metric_eligible` (`:322`), `_metric_eligible_as_baseline` (`:327`, rejects `value == 0.0` for the two usage metrics), `detect_quality_regressions` (`:337`; baseline = mean of the prior `baseline_windows` eligible windows; `baseline_value == 0` → `skipped_zero_baseline`, `:384`/`:436`). Two distinct baseline stages exist: the per-window verdict baseline in `_rate_metrics` (earliest) and the prior-K mean in `detect_quality_regressions`. The issue's "earliest qualified, sample-sufficient, all-measured baseline" text applies to the first; the `[10, 0, 10]` mean-5 criterion applies to the second.
- **`load_window_compositions`** (`quality_regressions.py`) runs its own `usage_events` query (model dimension) with a literal `channel = 'transcript' OR channel IS NULL` clause, guarded by `PRAGMA table_info`. `test_usage_selection_chokepoint_gate.py::test_quality_regressions_query_is_not_flagged` asserts that literal and exempts the file only because the query reads no token/cost column.
- **`workspace_quality.py`**: `aggregate_history_dbs` (`:249`) calls `analyze_agent_quality` per member inside the open member connection (`:280`, connection closed in a `finally`; `gated` retains only paths and issues) and once on the union (`:317`). `_UNION_RELATIONS` has 9 entries including `raw_events`/`usage_events` but **not `meta`**; `session_id` and `raw_events.id` pass through undiscriminated (overlapping raw IDs across members), while `issue_num` is offset by `i * 1_000_000_000` and `issue_id` suffixed `#r{i}`. A bare `meta` read on the union resolves temp → main (empty) → first attached member. The union call carries no member identity on `session_id`; the member-to-issue mapping is recoverable only from the stride on `issue_sessions`/`issue_events`, so the injected map must be built in the per-member loop and merged before the union call.
- **Derive plumbing**: `_USAGE_DERIVE_VERSION = "enh3651-v1"` is private in `session_store/lifecycle.py:1047` (distinct from the public `REBUILD_DERIVE_VERSION`); `_set_usage_derive_checkpoint` (`:1272`) writes `meta.usage_derive_version` and `usage_derive_raw_id = str(MAX(raw_events.id))`. The source-freshness `derive_pending` literal lives only in `usage_source_freshness` (`:1702`). `raw_events.usage_contract` is written at ingest (`claude_usage.claude_transcript_contract`: host `claude-code`, `host_basis == "handle"`, version exactly `2.1.284`, four non-negative int components not all zero); `writers.normalize_host_usage` returns `[]` for a malformed current-version Claude record and for Codex/Kimi hosts. `raw_events` has no `channel` column — in-scope vs excluded raw evidence must be decided from `host`/`host_basis`/`usage_contract`/`source_path`.
- **Missed docs/tests**: `docs/guides/HISTORY_SESSION_GUIDE.md` (~lines 534–536, "Quality Metric Definitions") repeats the "tokens always computable"/"cost withholds the verdict, not the number" language; `agent_quality.py` `_definitions` caveats, `_STANDARD_NOTES` and the module docstring (resolved-attribution item 3) carry it too. The later wiring check found no such claim in `docs/ARCHITECTURE.md`; inspect it only for applicable lifecycle wording.
- **Existing tests that encode the old contract** (will need to change deliberately, not by accident): `TestRegressionZeroBaseline` (`test_zero_value_cost_window_ineligible_as_baseline`, `test_coverage_suppressed_cost_window_ineligible_as_baseline`, `test_zero_baseline_correction_rate_skipped_not_flagged`), `TestCostCoverageGate::test_majority_null_cost_suppresses_verdict_but_not_tokens` (asserts the number survives with `verdict is None`), and the `_usage_event` fixture in `test_issue_history_agent_quality.py` (NULL provenance → `unknown`, which any measured-only rule disqualifies). Note the issue text locates these under `test_issue_history_agent_quality.py`; `test_enh3532_codex_rollout_usage.py` and `test_usage_selection_chokepoint_gate.py` are additional consumers.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Conventions in force.**
  - Reason codes are plain lowercase snake_case string literals, not prefixed and not held in a shared enum; the closed vocabulary is enumerated in the owning class docstring — evidence: `session_store/lifecycle.py` `RebuildState`, `history_reader/usage.py` `_classify_coverage`. Namespacing apart from the source-freshness `derive_pending` therefore has to be done by a distinct field/type, since the codebase has no prefix convention.
  - Frozen result types pair a bounded status (`Literal[...]` or `Enum`) with a `reason`; only `RepoActivity` (`issue_history/workspace_activity.py`) pairs that with an explicit `to_dict()`. `QualityMetric`/`QualityWindow`/`QualityAnalysis` are mutable with hand-written `to_dict()` — the two families disagree, and `SessionDeriveStatus` straddles them (frozen per the issue, serialized in quality output).
  - Readers take an already-open read-only connection; `try/except sqlite3.Error` returns a fail-safe value; the `query_only` connection comes from `SqliteBackend.connect_readonly` (`session_store/backend.py`). Read-only is tested by hashing the DB file before/after (`test_feat3410_workspace_quality.py::_sha256`) and by source-inspection asserts.
  - New dataclass fields are trailing and defaulted; `to_dict()` is hand-written, existing keys never renamed, conditional keys added under an `if` (`QualityAnalysis.regressions`, `usage._provenance_fields` adds `coverage_reason` only when not `non_overlapping`).
  - `history_reader` submodules define their own `__all__`, and `__init__.py` re-exports per submodule and lists names in its own `__all__`; the package is a DAG (submodules import only `_base.py`/`models.py`, never siblings). Dataclasses used by one domain live in that submodule (`CoverageGroup` in `usage.py`), so `SessionDeriveStatus` belongs in `usage.py`.
  - Optional injected parameters follow `x is None` → compute locally (`analyze_agent_quality(conn=None)`, `triage_research_axes(index=None)`). No precedent exists for a `Mapping[...] | None` injected map in `history_reader/`, `issue_history/` or `session_store/` (scoped search), and none for a supplied value being treated as authoritative with fail-closed missing keys — that contract is new.
  - Chokepoint gate: `test_usage_selection_chokepoint_gate.py` AST-scans for SQL naming token/cost columns `FROM usage_events` outside an allowlist. A helper reading only `raw_events`/`meta` does not match; any quality-side change that reads token/cost columns directly would need to route through `select_usage_observations`/`select_usage_coverage`.
  - Test fixtures write through production writers where they exist (`backfill_raw_events`, `rebuild`, `record_usage_event`), otherwise raw `INSERT` helpers; checkpoint drift is simulated with `INSERT INTO meta` or `monkeypatch.setattr(lifecycle, "_USAGE_DERIVE_VERSION", ...)`. Workspace tests share a bare `issue_id` across members to force collisions (`test_feat3418_workspace_quality.py::test_totals_not_conflated_across_id_collision`); neither workspace test file has usage/`raw_events`/`meta` fixtures yet.

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Derive checkpoint is store-global and its readers are unguarded.** `lifecycle._set_usage_derive_checkpoint` (`lifecycle.py:1276`) stamps `usage_derive_raw_id = MAX(raw_events.id)` over the whole store, both meta values are TEXT, and `_derive_usage_incremental_conn` (`:1293`) does `int(rows.get("usage_derive_raw_id", "0"))` with no guard — a missing id defaults to `"0"`, a non-numeric one raises `ValueError`. A status reader must treat a missing, non-numeric or version-mismatched checkpoint as `derive_pending` itself rather than copy that parse.
- **`usage_refresh.refresh_usage_source` strips the checkpoint store-wide, not per source** (`usage_refresh.py:222`, `DELETE FROM meta WHERE key IN ('usage_derive_version', 'usage_derive_raw_id')`). After any single-source refresh every session reads as checkpoint-missing until the next derive.
- **`prune` can move the store's `MAX(raw_events.id)` below the checkpoint** — the deriver treats `max_id < checkpoint` as invalid and replays (`lifecycle.py:1295`). A session-local `MAX(id) > checkpoint` lag test cannot see that case, and it also must not reclassify pruned-raw sessions that still have qualified `usage_events`.
- **`derive_gap` cannot be decided by joining `raw_events.id` to `usage_events.source_raw_event_id`.** `observation_key` is `[host, session_id, message_id]`; multiple raw snapshot rows for one message collapse into one usage row whose `source_raw_event_id` moves to the newest raw id, so contract-bearing raw rows routinely have no 1:1 match. The positive-contract case that does produce no row is `normalize_host_usage` returning `[]` for a malformed 2.1.284 Claude record that carries a message id.
- **Rollout/live evidence does not key on `raw_events.session_id`.** Codex rollout usage rows take `session_id` from the `session_meta` payload id (thread id), which can differ from `raw_events.session_id`; the dependable raw-to-usage join is `source_path`. `raw_events.host_basis` (`'handle'` at ingest) is a fifth in-scope-evidence input alongside `host`/`usage_contract`/`source_path`. `kimi-code` currently has no registered usage producer; that absence does not prove its raw channel is excluded or contains no usage. Until its native evidence and pure candidate/key/non-usage rules are registered, status remains unavailable rather than `derived_no_usage`; ENH-3665/3676 own that handoff.
- **`analyze_agent_quality` has an early-return branch with no session map.** When `rework.windows` is empty (`agent_quality.py:521`) it returns after `load_window_compositions(conn, {}, {}, {})` and `detect_quality_regressions`, before `_session_issue_map`/`_usage_totals`; a supplied `derive_status` must be a no-op there. In the main path the status check sits between `session_issues = _session_issue_map(conn)` and `_usage_totals(...)`. A session taints every window of every issue in `session_issues[sid]` — including issues that are not closed — and the fractional share is `1 / len(session_issues[sid])` over all issues the session touched.
- **Union-specific hazards beyond raw-id collisions** (`workspace_quality.py`): `session_id` is passed through the union verbatim, so a session shared by two members appears once with issue nums from both strides and a different `n` than either member computes (docstring: double-counting in `totals` is accepted, `per_repo` unaffected). `select_usage_coverage` also runs over the union, where `ambiguous_cross_channel` is store-wide across all members and `("unidentified", row["id"])` groups can collide across members — an injected status map does not repair coverage-side contamination.
- **Retry-inflation shares `skipped_zero_baseline`** with the usage branch in `detect_quality_regressions` (`quality_regressions.py`, lines ~435–437); `latest_only` selects the latest *eligible* window, so a verdict-less latest window silently yields an event for an older period with nothing marking it as not-the-latest — the "label the period of any older eligible result" criterion is a new rendering, not an existing one.


_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Conditional-key rule lives in the usage readers, not `issue_history`.** Every `issue_history/*` `to_dict()` (45 definitions, incl. `QualityAnalysis.to_dict` which always emits `"regressions": ... or None`, `agent_quality.py:161`) emits a fixed key set; keys omitted when unset appear only in `history_reader/usage.py:_provenance_fields` (`coverage_reason` only when coverage is not `non_overlapping`) and `token_provenance.ObservationGroup.entry`/`estimated_entry`. The "byte-for-byte for non-usage metrics" constraint on `QualityMetric.to_dict()` therefore introduces a conditional-key shape new to `issue_history`.
- **Vocabulary already in force for label/reason fields:** `provenance` ∈ `measured|estimated|unknown|mixed`; `availability` ∈ `available|partial|unavailable`; `coverage` ∈ `non_overlapping|overlap_unresolved|unknown`; reasons are snake_case literals with `reason` / `coverage_reason` / `qualification_reason` as separate string fields (`token_provenance.py`, `history_reader/usage.py`, `cli/ctx_stats.py`). New `QualityMetric` fields reusing these names keep one vocabulary across quality, `ctx-stats` and snapshot output.
- **Unavailable-metric rendering — two conventions disagree.** `cli/ctx_stats.py` (`_fmt_count`: "unavailable renders `—`, never `0`"; `unavailable (coverage unresolved)`), `token_provenance.format_figure` (`— [unavailable]`) and `workspace_activity` (`counts: unavailable (...)`) render an em-dash/"unavailable" with a separate reason clause and `null` in JSON. `rework.py` and `agent_quality._format_metric_line` instead use `insufficient history` for any missing value and have no unavailable-with-reason form. ENH-3732's "false insufficiency labels" criterion sides with the first group; the quality renderer is the outlier.
- **No precedent for per-metric independent baseline selection.** Every series picks the earliest window passing one series-wide gate (`_rate_metrics` `valid_keys[0]`, `_fix_rate_metrics`, `_compute_retry_windows`, `rework._assign_verdicts`); coverage gates only the *current* window's verdict, never baseline choice. `detect_quality_regressions` is the second stage and takes the last `baseline_windows` eligible priors. Independent token/cost baselines are a new shape, and `_metric_eligible` (`not insufficient_history and verdict is not None`) already makes a coverage-nulled cost window ineligible as both target and baseline.
- **`history_reader` → `session_store` is not a new module-level edge.** `history_reader/_base.py:30` imports `little_loops.session_store` at module level (and `runs.py`/`formatting.py` import `session_store.backend`), so `usage.py` already loads `session_store.lifecycle` transitively; only `session_store/queries.py` → `history_reader.usage` is lazy (opposite direction). No production module outside `session_store` imports a *private* `session_store` name, so reading `_USAGE_DERIVE_VERSION` from `history_reader` has no precedent; a function-local import and a `lifecycle`-module attribute lookup both see `monkeypatch.setattr(lifecycle, "_USAGE_DERIVE_VERSION", ...)` because both read the attribute at call time.
- **Existing read-only test idioms assert bytes, not connection mode:** `_sha256`/`read_bytes()` before/after (`test_feat3410_workspace_quality.py`, `test_feat3418_workspace_quality.py::TestSourceUntouchedDuringTotals`, `test_enh3678_rebuild_derive_gate.py::TestRebuildNeeded::test_read_leaves_store_byte_identical`) plus source-text checks; no Python test asserts `PRAGMA query_only` or a rejected write. `rebuild_needed` opens from a path, so its open/lock-timeout cases do not transfer to a helper taking an open connection. The only quality-side `raw_events` fixture is `_raw_event(db, session_id, host, *, line_no)` in `test_issue_history_agent_quality.py`.
- **No precedent for an authoritative injected `Mapping | None`** (searched `scripts/little_loops/`): the closest, `artifact_templates.py` `contexts: Mapping[DataPath, RegionContext] | None`, defaults absent keys to `text` (non-authoritative). The fail-closed-on-missing-key contract is new and needs its own test.

## Resolved review handoffs (2026-10-05)

- **Logical derive gaps:** recognize positive retained contracts at the same canonical observation grain used by `writers.normalize_host_usage`: for the existing qualified Claude producer, host + session + message ID. Several raw snapshots can coalesce into one observation; a missing `source_raw_event_id` join is not a gap. A represented logical observation satisfies those snapshots even when its raw pointer moves. A proved positive logical candidate with no derived observation is `derive_gap`; a missing/unproved key or inadequate retained evidence is `derive_status_unavailable`. Reuse/factor only the pure existing key construction as needed; do not call the normalizer or change derivation. Test two snapshots → one observation, genuine missing candidate, and unprovable identity.
- **Complete candidate population:** check every proved logical key before the usage-present branch. A session with two candidates and only one stored observation is `derive_gap`; malformed later snapshots do not create another candidate or invalidate the producer's last-valid-snapshot contract. Only a recognized contract can prove that a raw kind is non-usage or excluded. Unregistered/mismatched contracts and unproved source/channel rules stay unavailable, never `derived_no_usage`. The six evidence/delivery pairs declare and extend this pure retained-raw rule before their publication gate; do not encode today's missing Kimi producer as permanent proof that Kimi raw is excluded.
- **Consistent read proof:** read raw population, checkpoint/version and corresponding observations in one committed read snapshot. Reuse a caller-owned transaction; if none is active, manage only the helper/analysis's own read transaction without committing a caller's transaction. No writer/checkpoint redesign is required: the production deriver already holds `BEGIN IMMEDIATE` across usage and checkpoint writes. Test an append/derive between reads cannot make an uncovered candidate appear complete. Workspace injected status and union contributors must describe the same member revisions; detect intervening member commits and fail affected figures closed, or obtain both from a shared read snapshot. A per-member map followed by an unchecked later union read is insufficient.
- **Retention boundary:** BUG-3736 owns replay preservation and guarding underived candidates against pruning. A store-wide `MAX(raw_events.id) < checkpoint` alone does not invalidate a qualified as-of observation whose raw evidence was legitimately pruned; it is not proof of fresh source completeness either. Preserve that historical verdict while applying the recognized-candidate checks to surviving raw evidence. Test safe prune, underived-candidate retention, and new append after prune; do not treat a checkpoint above current MAX as permission to skip those checks.
- **Host composition:** keep `load_window_compositions`' existing all-raw-event host diagnostic and label that broader population in text/JSON/definitions. It must not supply the transcript token/cost numerator, denominator, qualification or trend eligibility. The model dimension remains transcript scoped. This resolves the repeated “decide whether” wiring note below without a new query or metric.
- **Workspace population:** preserve the documented member-additive `UNION ALL` quality population, including the accepted counting of a session present in multiple stores. A workspace total is not a distinct-session or counted-once host-consumption total. State that scope with the output; do not silently deduplicate or blanket-quarantine shared sessions. Member-local unavailable derive proof still taints every attributed window, so a good member cannot hide an underived one.
- **Coverage isolation:** in the transcript-only workspace acquisition, numeric IDs from different members cannot merge otherwise unrelated audit groups or use one member's checkpoint. Add a two-member case with colliding IDs and different session/provenance/derive states plus an excluded live counterpart. Keep `_UNION_RELATIONS`, issue discriminators and accepted attribution unchanged. BUG-3735 handles cross-channel wildcard correctness; this is not ENH-3730's availability redesign.
- **Workspace identity and reason selection:** keep any local row/raw-link identity used by coverage or candidate correspondence member-qualified in scratch views/mappings. Never join bare raw IDs across members or deduplicate a shared `observation_key`; the existing member-additive rows and shared session attribution remain intact. Prefer a query-local member tag or collision-free key; no source schema migration or arbitrary billion-row assumption is required. Merge unavailable statuses in fixed order `derive_status_unavailable` > `no_evidence` > `derive_pending` > `derive_lagging` > `derive_gap`, retaining the bounded contributing reasons in stable order. This is diagnostic precedence only; every unavailable status blocks the figure. Test member-order permutations as well as collisions.

## Program Design

### Types

- `SessionDeriveStatus` (new, frozen dataclass in `history_reader/usage.py`) — bounded `status` and `reason` strings plus an in-population disposition; serializes no raw IDs or paths.
- `QualityMetric` (`agent_quality.py`) — gains trailing defaulted fields for qualification, provenance label, reason and trend eligibility; the existing 7 positional fields and `to_dict()` keys are unchanged.
- `derive_status: Mapping[str, SessionDeriveStatus] | None` — session-ID keyed; `None` computes locally, a supplied map is authoritative and a missing key fails closed.

### Signatures

- `select_session_derive_status(conn: sqlite3.Connection, session_ids: Iterable[str]) -> dict[str, SessionDeriveStatus]` — new, read-only over `raw_events`/`meta`; returns a key for every requested session.
- `analyze_agent_quality(issues, *, db, conn, min_sample, sensitivity, baseline_windows, latest_only, derive_status=None) -> QualityAnalysis` — existing function gains one keyword-only parameter.
- `_usage_totals(conn, session_issues, issue_window) -> dict[tuple[str, str], dict[str, float]]` — existing; its bucket shape is asserted by `test_enh3532_codex_rollout_usage.py`, so qualification metadata is carried alongside rather than by reshaping existing keys.
- `_rate_metrics(name, numerator_by_key, window_closed, min_sample, coverage_by_key=None) -> dict[tuple[str, str], QualityMetric]` — existing; absence-equals-zero stays the default for correction/fix/retry.
- `_metric_eligible_as_baseline(window: QualityWindow, metric_name: str) -> bool` — existing; the usage-metric zero exclusion is replaced by explicit all-measured eligibility.
- `aggregate_history_dbs(members, *, min_sample, sensitivity, baseline_windows, latest_only) -> AggregationResult` — existing; builds the per-member status maps and merges them before the union call.

### Call Path

`aggregate_history_dbs` -> `select_session_derive_status` (per member, on the open read-only connection) -> merged map -> `analyze_agent_quality(derive_status=...)` -> `_usage_totals` -> `_rate_metrics` -> `detect_quality_regressions` -> `_metric_eligible_as_baseline`

### Decision Rules

- **Inputs per session:** in-scope raw evidence (host/`host_basis`/`usage_contract`/`source_path`-derived, since `raw_events` has no `channel` column), the session-local `MAX(raw_events.id)`, the member's `meta.usage_derive_version` and `meta.usage_derive_raw_id`, and in-scope `usage_events` observations.
- **Precedence:** the disposition table in Expected Behavior is evaluated top-down; positively proved excluded-only evidence precedes pending/lagging checks, then unproved candidate evidence and per-logical-key gaps precede qualification. Existing observations do not bypass a gap. Workspace reason precedence is specified in **Resolved review handoffs** and is independent of per-session disposition order.
- **Version comparison:** reuses the deriver's `_USAGE_DERIVE_VERSION` (`lifecycle.py`); never a literal copy.
- **Merge across members:** any unavailable member status wins and its reason is retained; excluded-channel-only members contribute nothing; a member with no association contributes no key.
- **Baseline eligibility:** a window is a baseline/target only when qualified, sample-sufficient and all-measured, independently for tokens and cost; a qualified observed zero is eligible; the zero-**mean** guard (`skipped_zero_baseline`) is unchanged.
- **Escape hatch:** none — an unavailable status cannot be dismissed per session. A window with zero in-scope observations stays `no_observations`.

## Acceptance Criteria

- [ ] Quality cost/token numerators obey shared qualification, including the partial/unknown row with numeric stored cost; ineligible contributors stay in completeness accounting and cannot become zero tokens, 100% priced coverage or a numeric verdict; channel pins and qualified-history controls preserved.
- [ ] Windows with no usage or any audit-only contributor have unavailable usage-derived values with reasons and cannot become zero baselines; the next qualified, sample-sufficient window supplies the baseline; qualified zeros remain zero; correction/fix/retry metrics, fractional multi-issue attribution and workspace-union populations keep their definitions; an older regression result names its actual period.
- [ ] Transcript-scoped quality: adding excluded live/rollout counterparts (same and unrelated session) cannot change values, qualification or model composition; in-scope unknown/partial/unresolved rows remain completeness contributors; text/JSON state the transcript-only numerator and unchanged denominator.
- [ ] Baselines/verdicts require qualified sample-sufficient all-measured values independently for tokens and cost; estimated/mixed windows show labels/reasons but cannot be targets or baselines; measured `[10, 0, 10]` with two prior baselines yields mean `5` and relative increase `1.0`; no-observation windows stay unavailable; an all-zero mean keeps the division guard; text/JSON render sample-sufficient unavailable metrics without exceptions or false insufficiency labels.
- [ ] Attributed sessions with in-scope raw evidence and absent/invalid/version-mismatched proof or session-local lag make each touched window unavailable with bounded reasons; recognized positive contract without a derived observation is `derive_gap`; fully derived non-usage raw needs no usage row; no evidence or zero in-scope observations never becomes zero; proved rollout/live-only sessions stay excluded; source deletion and unrelated later raw appends cannot invalidate qualified stored sessions; helpers run on `query_only` connections with no writes, re-derivation or source reads.
- [ ] Workspace analysis uses member-local proof and a conservatively merged injected map; colliding raw IDs with different checkpoints on a shared window cannot publish a complete subset total; bare first-attached `meta` cannot certify another member; shared-session merging and absent/out-of-scope members tested; attribution/discriminators and union relations preserved.
- [ ] Coalesced raw snapshots do not create false derive gaps; missing logical candidates and unprovable keys fail closed with distinct reasons. Workspace ID-collision and shared-session tests preserve member-additive counting while unavailable member proof blocks affected windows. The broader raw-host diagnostic is labeled and never certifies transcript usage.
- [ ] Two logical candidates with one observed request remain `derive_gap`; unregistered/mismatched raw contracts cannot become proved non-usage/excluded evidence. Safe pruning retains qualified as-of observations, underived candidates cannot be pruned under BUG-3736, and later appends still require proof. Status/usage reads are snapshot-consistent, including injected workspace maps versus union rows; member-order permutations preserve figures and bounded reasons.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — prevents audit-only/underived data from becoming quality numbers or baselines.
- **Effort**: Large — read-only session proof, metric semantics and member-local integration.
- **Risk**: Medium — published trends become unavailable when evidence is incomplete; preserve the documented member-additive population.

## Scope Boundaries

- **Out of scope:** qualification core and selectors (ENH-3731), snapshot/dashboard (ENH-3733), source-to-raw freshness, derive-algorithm changes and pruning/replay preservation (BUG-3736), re-deriving unknown transcript rows (promotion is forbidden), ENH-3730's gate redesign.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

1. Quality's usage numerators come from the transcript channel only and obey the shared qualification (the shared qualification surfaces are a prerequisite recorded in `blocked_by`). Verified by driving `analyze_agent_quality` end to end with a partial/unknown row carrying stored cost, and by `test_enh3532_codex_rollout_usage.py` still passing.
2. `select_session_derive_status` exists in `history_reader/usage.py`, is re-exported from `history_reader/__init__.py`, and returns a status for every requested session on a `query_only` connection with no writes or source reads. Verified with the missing-checkpoint, version-mismatch, session-local-lag, recognized-contract-without-observation, fully-derived non-usage, no-evidence and source-loss cases, plus a DB-hash-unchanged assertion in the style of `test_feat3410_workspace_quality.py`.
3. `QualityMetric` carries qualification/provenance/reason/trend-eligibility without altering its existing 7 keys, and `_format_metric_line` plus the markdown `cell()` render a sample-sufficient unavailable metric without the current `assert metric.value is not None`. Verified with text, markdown and JSON output for an unavailable-but-sample-sufficient window.
4. Usage-metric baselines/verdicts are chosen per metric from qualified, sample-sufficient, all-measured windows; `_ZERO_INELIGIBLE_BASELINE_METRICS` no longer governs usage metrics while the zero-mean guard remains. Verified by `[10, 0, 10]` → mean 5 / relative increase 1.0, an all-zero mean still skipped, and an older eligible result naming its actual period.
5. Workspace analysis computes status on each member's open connection and injects a conservatively merged map; the union call never reads bare `meta`. Verified with overlapping raw IDs and differing member checkpoints on a shared window.
6. `_definitions`, `_STANDARD_NOTES`, the module docstring, `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md` and `docs/ARCHITECTURE.md` no longer claim tokens are always computable or that coverage withholds only the verdict. Inspect `docs/ARCHITECTURE.md` only for applicable lifecycle wording; it has no such claim to remove.
7. `python -m pytest scripts/tests/` exits 0, including the old-contract tests listed under Integration Map, which are updated deliberately.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/issue_history/agent_quality.py` — `_STANDARD_NOTES`, `_definitions` (`cost_per_issue`/`tokens_per_issue` caveats and `verdict_band`) and the module docstring item 3; keep the `"correlational"` note and the 4-definition count (`test_cli_history.py` and `TestEmptyAndMissingDb` assert it)
- Update `scripts/little_loops/issue_history/agent_quality.py` — `QualityMetric.to_dict()` adds the new keys conditionally so JSON/YAML (`format_agent_quality_json`/`format_agent_quality_yaml`, workspace `per_repo`/`totals`) keep the existing 7 keys byte-for-byte for non-usage metrics
- Update `scripts/little_loops/issue_history/quality_regressions.py` — apply all-measured eligibility to `_metric_eligible` (targets) as well as `_metric_eligible_as_baseline`; leave the `RetryWindow` zero-baseline branch of `detect_quality_regressions` unchanged; test that the all-raw host diagnostic is labeled and cannot gate the transcript usage metrics
- Update `scripts/little_loops/history_reader/usage.py` — look up `_USAGE_DERIVE_VERSION` through the `lifecycle` module at call time via a lazy import inside `select_session_derive_status` (monkeypatch-visible; keeps the private version lookup local without copying it); read only `raw_events`/`meta` (or `usage_events` without token/cost columns) so the chokepoint AST gate stays green; no raw `sqlite3.connect(`
- Update `scripts/little_loops/history_reader/__init__.py` — docstring, re-export block and `__all__`; add a `history_reader` export test
- Update `scripts/little_loops/issue_history/workspace_quality.py` — keep new code after `_open_member_readonly` free of `ensure_db(`/`_connect_readonly(`/`immutable=1`; build the per-member map inside the open-connection loop (connections close in a `finally`; `gated` keeps only paths/issues) and merge before the union call; do not add `meta` to `_UNION_RELATIONS`
- Treat `ll-history quality` single-repo path (`main_history` in `scripts/little_loops/cli/history.py`) as a verified-unchanged caller: `derive_status=None` → local compute on its migrated read-only connection; add a CLI test with usage data
- Update `scripts/tests/test_issue_history_agent_quality.py` — `_usage_event` provenance parameter; adjust `TestCostAndTokensPerIssue` (three tests), `TestRegressionZeroBaseline`, `TestCostCoverageGate`; add the new quality classes
- Update `scripts/tests/test_cli_history.py` — `len(payload["definitions"]) == 4` and a usage-data `quality` output test
- Add `scripts/tests/test_enh3732_session_derive_status.py` and workspace derive-status cases in `scripts/tests/test_feat3418_workspace_quality.py`; keep `test_usage_selection_chokepoint_gate.py` and `test_history_store_chokepoint_gate.py` passing
- Update `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/reference/API.md`, `scripts/little_loops/issue_history/__init__.py` docstring and `scripts/little_loops/pricing.py` docstring per the Documentation list; re-run `test_docs_audience_gate.py` and `test_doc_counts.py`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-04 (re-verified 2026-10-04: ENH-3731 still `open`; `qualify_usage`/`UsageQualification` still absent from source)_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Architecture: `derive_status: Mapping[...] | None` as an authoritative, fail-closed injected map has no precedent in `history_reader/`, `issue_history/` or `session_store/`; `SessionDeriveStatus` straddles the frozen/mutable result-type conventions.
- Host diagnostic scope is resolved: retain and label the all-raw population per **Resolved review handoffs**; it cannot certify transcript usage. Earlier “decide whether” wording is historical, not an outstanding decision.
- ENH-3731 is a required implementation prerequisite for `qualify_usage`/`channel=`. Keep the hard edge; the earlier wording about nullable numerators has been clarified so it cannot be mistaken for a scheduling exception.

### Gaps to Address
- `blocked_by` ENH-3731 is `open`: `qualify_usage`, `UsageQualification` and the `channel=` selector scope do not exist in source (verified by grep of `history_reader/usage.py` and `issue_history/`). BUG-3736 additionally owns the reproduced prune/replay loss and pending-candidate retention. Complete both prerequisites before this reader's retained-history/derive-status integration; no new score is claimed.

### Outcome Risk Factors
- Deep per-site complexity: rewires `_usage_totals`/`_rate_metrics`/baseline eligibility plus a new derive-status read path with a conservative cross-member merge.
- Broad enumeration across ~15+ sites (4 source modules, ~8 test files, ~6 docs); several existing tests encode the old contract and must change deliberately.
- Wide blast radius on `QualityMetric`/`analyze_agent_quality` (CLI, workspace union, regressions, rework shared helpers).


## Session Log

- Pre-implementation epic review - 2026-10-05 - Opus critique (confidence 0.72) confirmed gap-before-usage ordering and unregistered-contract failure. Added coherent read-snapshot, stable workspace-reason and member-qualified local-identity controls, while retaining the accepted member-additive population. BUG-3736 owns the independently reproduced pruning/usage-loss repair and is a hard integration prerequisite. Reconciled superseded wiring concerns; no new confidence pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Resolved logical-observation derive gaps, raw-host diagnostic scope and workspace coverage/proof controls. Kept the explicitly documented member-additive totals instead of adopting Opus’s proposed cross-member quarantine (confidence 0.74); that would change the existing accepted population. Added Impact and required regression cases; no new score or implementation pass is claimed.

- `/ll:confidence-check` - 2026-10-05T04:09:15 - `ddd0ba49-7247-411f-a7ef-57bd1c042115.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T04:06:20 - `097f9bb1-c676-46ac-b043-c8b9570fd790.jsonl`
- `/ll:confidence-check` - 2026-10-05T03:58:51 - `34b28804-d521-4695-861e-b3e56e525c2d.jsonl`
- `/ll:verify-issues` - 2026-10-05T03:57:29 - `e36568ce-5b7b-43e2-a419-0854752c451b.jsonl`
- `/ll:wire-issue` - 2026-10-05T03:55:31 - `442ab9b5-db9b-449c-b459-e80826708c51.jsonl`
- `/ll:refine-issue` - 2026-10-05T03:44:38 - `18d2ef05-82f6-4fff-9353-148e58d582a1.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2

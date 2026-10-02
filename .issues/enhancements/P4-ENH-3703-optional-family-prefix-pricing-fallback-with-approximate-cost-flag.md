---
id: ENH-3703
type: ENH
title: Optional family-prefix pricing fallback with approximate cost flag
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:16Z'
parent: EPIC-3562
---

# ENH-3703: Optional family-prefix pricing fallback with approximate cost flag

## Summary

Optional follow-up to BUG-3696: when a model ID is absent from `MODEL_PRICING`, estimate cost from the nearest known family (segment-boundary longest-prefix match) and mark the figure approximate, instead of showing `n/a`.

## Current Behavior

`estimate_cost_usd` is exact-key only; any unknown model yields `None` and `n/a` in the `ll-loop` usage table. BUG-3696 adds an unpriced-model footer so the gap is visible but supplies no number.

## Expected Behavior

An unknown ID with a known family prefix is priced at the family's rate, flagged approximate (`~$X.XXXX`), with the following constraints from the advisor review:

- **Segment-boundary matching only** (`model == key` or `model.startswith(key + "-")`); never `claude-fable-5-1` pricing `claude-fable-5-10`; longest key wins; never crosses a major version.
- **Accuracy caveat:** minor versions are priced differently (`claude-opus-5-5` input $4 vs `claude-opus-5` $5; `claude-fable-5-1` cache read $0.25 vs `claude-fable-5` $1.00); loop runs are cache-heavy, so a fallback figure can be 20–75% off. Decide whether that is acceptable before implementing; the BUG-3696 footer may be enough.
- Apply only in `fsm/cost_graph.py`; keep `session_store/writers.py` exact-only (`usage_events.cost_usd` has no provenance column).
- `executor._check_cost_ceiling` must treat approximate cost as unknown and emit `cost_ceiling_unknown` (reason "approximate price"), so ceilings never abort on an invented figure.
- `PerStateCost.approximate` emitted in `to_dict` only when True and read back in `CostReport.read_json`; `_compute_totals` aggregates it.
- Deferred wiring/research notes were moved here from BUG-3696 on 2026-10-02; see § Deferred Wiring Notes.

## Motivation

Models ship every few weeks, and each release blanks cost until the table is edited; a flagged estimate beats `n/a` for most users — provided it is not misleading. Split out of BUG-3696 as optional work; close as won't-do if the footer proves sufficient.

## Impact

- **Priority**: P4 - optional; BUG-3696's unpriced-model footer already makes the gap visible
- **Effort**: Medium - new prefix matcher, `PerStateCost.approximate` through `to_dict`/`read_json`/`_compute_totals`, cost-ceiling handling, docs
- **Risk**: Medium - a fallback figure can be 20–75% off for cache-heavy runs and could mislead cost decisions
- **Breaking Change**: No - additive JSON field emitted only when true

## Acceptance Criteria

- [ ] Decision recorded: implement the fallback or close as won't-do (given the 20–75% accuracy caveat)
- [ ] If implemented: segment-boundary longest-prefix matcher with tests (`claude-fable-5-10` does not match `claude-fable-5-1`; exact keys and dated IDs are not shadowed)
- [ ] If implemented: `_check_cost_ceiling` treats approximate costs as unknown, with a `test_cost_ceiling_enforcement.py` case
- [ ] If implemented: `approximate` round-trips through `write_json` / `read_json`; `to_dict` stays byte-identical for exact-only data
- [ ] `python -m pytest scripts/tests/` exits 0

## Deferred Wiring Notes

_Moved verbatim from BUG-3696 § Integration Map on 2026-10-02 (pre-implementation review). Written while the fallback was in BUG-3696's scope; items about the `claude-sonnet-5-5` price entry, the unpriced-model footer and doc fixes are owned by BUG-3696. Line numbers are as of 2026-10-02._

> **Scope revision (2026-10-02):** the prefix fallback / `approximate` flag was dropped from this issue. Every wiring and research note below that mentions `approximate`, `estimate_cost_usd_approx`, `~$`, `read_json` round-tripping the flag, the `_check_cost_ceiling` decision, `session_store/writers.py` call sites, `to_dict` conditional emission, or `ll-history quality` distinguishing rows is **deferred to the follow-up fallback enhancement** and is NOT in scope here. Still in scope: the `claude-sonnet-5-5` price entry (`pricing.py`, `LIVE_RATES`, identity test, docstring), the unpriced-model footer in `cost_graph.py`, the price-coverage test, `test_usage_reporter.py` end-to-end table test, and the stale `docs/reference/CLI.md` fixes. `_check_cost_ceiling` is unaffected (an unpriced model stays `cost_ceiling_unknown`).

#### Files to Modify
- `scripts/little_loops/pricing.py` - `MODEL_PRICING` (shared `_SONNET_5` dict), module docstring
- `scripts/little_loops/fsm/cost_graph.py` - `CostReport.from_usage_jsonl` (track unpriced model IDs), `CostReport.table` (footer)
- `docs/reference/CLI.md` - stale `est_cost` / `cost_usd` text (~L1022, ~L1057), unpriced-model footer note
- `docs/reference/API.md` - `MODEL_PRICING` description (~L12627) if it enumerates models

#### Tests

- `scripts/tests/` pricing and `cost_graph` tests; new price-coverage test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_pricing.py:20` — add `claude-sonnet-5-5` to `LIVE_RATES` in `TestLiveRates` (certain break otherwise: `test_every_model_pinned`); `test_rates_match_live_table` / `test_batch_halves_each_rate` then cover it automatically; optionally add it to `TestModelPricing.test_known_models_present`, and `test_output_more_expensive_than_input` iterates all of `MODEL_PRICING` so the new rate must satisfy output > input [Agent 3 finding]
- `scripts/tests/test_pricing.py` — new `TestEstimateCostUsdApprox` class: exact hit → `approximate=False`; `claude-sonnet-5-5-<suffix>`/dated ID → longest prefix, `approximate=True`; longest prefix beats shorter (use `monkeypatch.setitem(MODEL_PRICING, ...)`); `"unknown-model-xyz"`, `"unknown"`, `""` → `None`; a `None` token component → `None`; `is_batch`/`as_of` pass-through [Agent 3 finding]
- `scripts/tests/test_pricing.py:106` — price-coverage test shaped like `test_every_model_pinned` and `test_host_runner_dispatch.py::TestModelAliasResolution::test_every_alias_target_is_ranked_and_priced`; pin an explicit set (`MODEL_ALIASES` values / `MODEL_RANKS["claude-code"]` / `MODEL_CONTEXT_WINDOW`), since "every ID the harness can emit" is unbounded [Agent 3 finding]
- `scripts/tests/test_fsm_cost_graph.py:103` — `TestPerStateCost.test_to_dict_exact_keys` (exact 8-key equality) breaks only if `approximate` is always emitted; emit it only when True. Also add `test_table_row_approximate_marker` (`~$`, no `n/a`), a `test_defaults` assertion `approximate is False`, and `TestCostReport` cases: family-fallback row sets `approximate` with `has_unknown_model` False; exact + approximate mix; approximate + unknown mix → unknown wins, `cost_usd` None; `_compute_totals` aggregation; `write_json` → `read_json` round trip [Agent 3 finding]
- `scripts/tests/test_fsm_cost_graph.py` — shared `fixture_jsonl` uses `claude-sonnet-4-5` (no `MODEL_PRICING` entry, no `claude-sonnet-4` family key); assertions check tokens/keys only so no break expected, but a truly unrecognised-family case needs its own fixture; same for `test_cli_cost_table.py` `fixture_jsonl` [Agent 3 finding]
- `scripts/tests/test_usage_reporter.py:91` — `TestPrintUsageSummary.test_na_shown_for_unknown_model` (model `"unknown"`, no prefix match, `n/a` persists) and `test_cost_estimate_shown_for_known_model` (`"$" in out`, still true for `~$`); add a `claude-sonnet-5-5` row asserting `~$` and no `n/a` — the closest end-to-end table test [Agent 3 finding]
- `scripts/tests/test_enh3538_token_observations.py:407` — `TestCostGraphRoundTrip.test_complete_json_has_no_missing_keys_and_legacy_numeric_reads` is the absence-when-default template for `approximate`; `test_incomplete_state_is_unpriced_and_survives_json_round_trip` requires the approx function to still return `None` for a `None` token component [Agent 3 finding]
- `scripts/tests/test_cost_ceiling_enforcement.py:226` — `TestCostCeilingUnknownCases.test_unpriceable_model_does_not_abort` uses `"totally-unpriced-model-xyz"` (no `claude-` prefix, safe); add a ceiling-with-approximate-model case under `TestCostCeilingBreachAborts` once the executor decision is made [Agent 3 finding]
- `scripts/tests/test_tier0_traces.py:140` — asserts locked per-state keys and `has_unknown_model is False` against static fixtures; unaffected by conditional emission [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py:218` — pins the `## little_loops.pricing` heading in `docs/reference/API.md` (ENH-3067); optionally add a `("docs/reference/API.md", "estimate_cost_usd_approx", "BUG-3696")` tuple [Agent 1 finding]
- `scripts/tests/test_pricing.py:364` — `TestEventDatePricingCallSites.test_cost_graph_prices_by_row_timestamp` drives `from_usage_jsonl` and asserts costs only; verify it still passes after the call-site swap [Agent 3 finding]

#### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-02 — based on codebase analysis:_

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/fsm/executor.py:4452` — the cost-ceiling check treats `has_unknown_model` / `cost_usd is None` as "unpriced" and skips enforcement (emits `cost_ceiling_unknown`). An approximate-priced state would read as priced, so the ceiling would start enforcing against a fallback figure; the fix must decide that knowingly.
- `scripts/little_loops/session_store/writers.py` (three `estimate_cost_usd` call sites, each passing `as_of=_event_date(...)`) — writes the result to `usage_events.cost_usd` (REAL, nullable). The schema (`session_store/schema.py`, `usage_events` DDL) has no column recording how a cost was derived.
- `scripts/little_loops/cli/loop/summary.py:_print_usage_summary` — only calls `CostReport.from_usage_jsonl(...).table()` / `write_json`; no per-row logic to change.
- `scripts/little_loops/fsm/persistence.py:_handle_event` — emits `usage.jsonl` rows; `model` comes from the host-reported event, not from `MODEL_ALIASES`.

**Conventions in Force**
- A model price is one exact-key entry in `MODEL_PRICING` carrying the four rate keys; `pricing.py`'s module docstring is the changelog for additions and cites the issue ID. A table fix does not back-fill already-written null `cost_usd` rows. Evidence: `pricing.py` (FEAT-3183, ENH-2745, BUG-3564 notes).
- `estimate_cost_usd` is exact-key only and its signature grows append-only with defaults (`is_batch` FEAT-2710, `as_of` BUG-3579), so positional callers in `cost_graph.py` and `session_store/writers.py` stay valid. No longest-prefix/family matching helper exists anywhere in `scripts/little_loops` — `context_window.context_window_for` and `host_runner.resolve_model_alias` are exact-lookup precedents, so the family fallback is a new primitive.
- Additive stable-JSON fields are emitted only when non-default, keeping complete-data output byte-identical to the prior shape (`PerStateCost.to_dict` and `_compute_totals` for the `*_missing` keys, ENH-3538; `persistence.py` for `is_batch`, FEAT-2716). New `PerStateCost` fields carry defaults, like `has_unknown_model`.
- A flag may legitimately live only in the Python API: `has_unknown_model` is deliberately absent from `PerStateCost.to_dict` (folded into `cost_usd: null`), while `_compute_totals` does expose it under `totals`. Whether `approximate` goes into `to_dict` is a choice the existing code supports either way.
- Contested/stale docs: `docs/reference/CLI.md` (~L1022, ~L1057) describes a `~$X.XXX (model unknown)` table form and `cost_usd` of `0.0` for unknown models, but `table_row` prints `n/a` and `to_dict` emits `null`. Reconcile the doc with the final behavior, not the other way round.

**Tests**
- `scripts/tests/test_pricing.py::TestLiveRates::test_every_model_pinned` asserts `set(MODEL_PRICING) == set(LIVE_RATES)`; adding `claude-sonnet-5-5` without a matching `LIVE_RATES` entry fails it. `test_rates_match_live_table` and `test_batch_halves_each_rate` are parametrized over `LIVE_RATES`, so the new entry is covered automatically once pinned. `test_pricing.py` also asserts `estimate_cost_usd("unknown-model-xyz", ...)` is `None` — that contract (genuinely unknown → `None`) must keep passing for `estimate_cost_usd` itself.
- `scripts/tests/test_fsm_cost_graph.py::TestPerStateCost::test_to_dict_exact_keys` locks the exact `to_dict` key set; `test_table_row_unknown_model_marker` asserts `n/a` for an unknown model. `test_cli_cost_table.py::TestCostOutputJsonShape::test_state_entry_locked_keys` is a subset check. `test_enh3538_token_observations.py` asserts complete data emits no extra keys.
- The shared `fixture_jsonl` in `test_fsm_cost_graph.py` and `test_cli_cost_table.py` uses `claude-sonnet-4-5`, which has no `MODEL_PRICING` entry; whether it still renders `n/a` after a family-prefix fallback depends on whether a `claude-sonnet-4` family key exists — those tests must be re-checked, and a truly unrecognized-family case needs its own fixture.
- Closest existing completeness gate: `test_host_runner_dispatch.py::TestModelAliasResolution::test_every_alias_target_is_ranked_and_priced` (covers only `MODEL_ALIASES` targets). It would not have caught this bug.

**Harness-emittable model IDs (constraint on AC 4)**
- The model recorded in `usage.jsonl` is whatever the host reports (`subprocess_utils.py` stream-json `system/init`; `executor.py` usage payload), not an entry of `host_runner.MODEL_ALIASES`. `MODEL_ALIASES` still resolves `sonnet` to `claude-sonnet-5`, yet the observed run reported `claude-sonnet-5-5`. The set of IDs the harness can emit is therefore unbounded from the codebase's side; a test enumerating `MODEL_ALIASES` / `MODEL_RANKS` targets is checkable, a test over "every ID the harness can emit" is not. State which set the test pins.
- Nothing else in the repo prices `claude-sonnet-5-5` (it appears only as a literal in `test_adapters_model_hint.py` and in issue files). The published rate cannot be derived from the repository and must be confirmed externally.

**`ll-history quality` cost-coverage (constraint on Proposed Solution step 4)**
- `issue_history/agent_quality.py:_usage_totals` computes coverage as the non-null share of `usage_events.cost_usd` rows (`priced_rows / total_rows`), gated by `LOW_COVERAGE_THRESHOLD = 0.5`. It has no signal for exact vs approximate: ingest writers store a bare `float | None`. As written, approximate rows would count as fully priced. Distinguishing them requires a new column or a decision to leave history unflagged; "verify it distinguishes" cannot be satisfied by verification alone.

_Added by `/ll:refine-issue` — 2026-10-02 — based on codebase analysis:_

- `PerStateCost` is constructed on three paths, and any new field must survive all of them: `from_usage_jsonl` (the `buckets` dict, `cost_graph.py:277`–`342`), `read_json` (`cost_graph.py:208`, which derives `has_unknown_model=cost_raw is None` at `:237`), and the `_compute_totals` aggregate (`cost_graph.py:360`–`375`). Constraint: if `approximate` is omitted from `to_dict`, a table re-rendered from a saved cost JSON via `read_json` silently loses the `~` marker, so "Python-API-only" and "round-trips through the saved report" are different outcomes the fix must choose between knowingly.
- `docs/reference/API.md:12627` carries the `MODEL_PRICING` description ("Covers the current Claude 5.x / 4.x model registry…"); it is the doc anchor for a new price entry, separate from the cost-report JSON-shape notes.
- `estimate_cost_usd` has 5 call sites outside tests: `cost_graph.py:321` and four in `session_store/writers.py` (`:2011`, `:3941`, `:4074`, `:4276`). A sibling approximate helper leaves the writers on exact-only pricing unless they are switched, in which case `usage_events.cost_usd` would start holding fallback figures with no marker (see the `_usage_totals` coverage constraint below).

_Added by `/ll:refine-issue` — 2026-10-02 — based on codebase analysis:_

**Additional conventions (pattern-finder pass)**
- Two model keys that share a rate share one module-level dict, and a test asserts identity — evidence: `_HAIKU_4_5` in `pricing.py` and `test_pricing.py::test_haiku_ids_share_one_rate_dict`. If `claude-sonnet-5-5` turns out to carry the same rate as an existing entry, the identity convention applies; if it differs, a literal dict is the norm.
- Model-ID tables are exact-match per-purpose dicts with no shared normalizer — evidence: `host_runner.MODEL_ALIASES`/`resolve_model_alias`, `advisor.MODEL_RANKS`/`rank_model`, `context_window.MODEL_CONTEXT_WINDOW`/`context_window_for`. `pricing.py` has no date-suffix stripping; the one dated ID is a literal key (`claude-haiku-4-5-20251001`). A longest-prefix matcher must therefore not shadow exact dated keys, and must not treat `claude-sonnet-5-5-<suffix>` and `claude-sonnet-5` as the same family by accident (`claude-sonnet-5` is a string prefix of `claude-sonnet-5-5`, which is exactly why the proposed fallback maps them).
- Searched `scripts/**/*.py` for `approximate|family.prefix|longest.prefix`, `removesuffix`, `normalize_model`, `model_family`: no existing family-matching or normalization primitive (capability search, not name search).
- `_STATE_KEYS` in `cost_graph.py` is commented "Locked JSON keys (do not reorder / rename without a schema version bump)"; optional keys join `to_dict` only when truthy (`<component>_missing`, ENH-3538).

_Wiring pass added by `/ll:wire-issue`:_

**Additional sites inside known files to Modify**
- `scripts/little_loops/fsm/cost_graph.py:26` — `from little_loops.pricing import _event_date, estimate_cost_usd` at module top must also import `estimate_cost_usd_approx`; the `estimate_cost_usd(` call in `CostReport.from_usage_jsonl` (~L321) is the swap site [Agent 1 finding]
- `scripts/little_loops/fsm/cost_graph.py` — `CostReport.read_json` rebuilds `PerStateCost` from JSON and sets `has_unknown_model=cost_raw is None`; if `approximate` is emitted by `to_dict`, `read_json` must read it (default False) or a `write_json` → `read_json` → `table()` round trip loses the `~$` marker [Agent 2 finding]
- `scripts/little_loops/pricing.py:1` — module docstring is the de facto changelog (cites issue IDs); add a BUG-3696 note for the `claude-sonnet-5-5` entry and the new fallback helper in the module docstring [Agent 2 finding]
- `docs/reference/API.md:12618` — `## little_loops.pricing` import line listing public symbols and `### estimate_cost_usd` (L12647); add `estimate_cost_usd_approx` in `little_loops.pricing`; do **not** rename the `## little_loops.pricing` heading (pinned by `test_wiring_reference_docs.py:218`) [Agent 2 finding]

#### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:4452` — `_check_cost_ceiling`: with the fallback an approximate state has `has_unknown_model=False` and `cost_usd` not None, so `cost_warn_at` / `cost_ceiling_per_state` would enforce (and can abort with `cost_ceiling_exceeded`) against a fallback figure; `cost_ceiling_unknown` then fires only for unmatched families or a missing `usage.jsonl`. Decide knowingly — e.g. read `bucket.approximate` here [Agent 2 finding]
- `scripts/little_loops/fsm/__init__.py:86` — re-exports `CostReport`, `PerStateCost` (and `__all__` L181–182); no change needed unless a new public symbol is added [Agent 1 finding]
- `scripts/little_loops/cli/loop/runner.py:556` — `_print_usage_summary` call is wrapped in `try/except Exception: pass`, so a `table_row` regression is silent; cover with a direct `_print_usage_summary` test [Agent 2 finding]
- `scripts/little_loops/cli/loop/__init__.py:376` — `--cost-output-json` help text points at `test_cli_cost_table.py` for the locked shape; update if the shape gains `approximate` [Agent 2 finding]
- `scripts/little_loops/issue_history/agent_quality.py:208` — comment "cost_usd is null for any model absent from pricing.MODEL_PRICING" in `_usage_totals`; stays accurate only if the ingest path (`session_store/writers.py`) remains exact-only [Agent 1 finding]
- `scripts/little_loops/host_runner.py:109` — `MODEL_ALIASES` still maps `sonnet` → `claude-sonnet-5`; `scripts/little_loops/advisor.py:54` `MODEL_RANKS` has no `claude-sonnet-5-5`. Neither is in scope, but a price-coverage test over alias/rank targets would not cover this bug (state which set the test pins) [Agent 1 finding]
- `scripts/little_loops/session_store/schema.py:510` — `usage_events.cost_usd REAL` has no provenance column; adding the exact `claude-sonnet-5-5` entry changes `cost_usd` for new transcript/replay rows only (live-channel rows already written stay NULL) — see `docs/reference/API.md` `### INTRO_PRICING` "Stored rows after a rate correction" [Agent 2 finding]

#### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1022` — `est_cost` row ("`~$X.XXX (model unknown)`") and L1057 ("`cost_usd` is `0.0` ... `has_unknown_model` surfaced only in the Python API, not the JSON") in `Per-State Token/Cost Summary (ENH-1797)`; also the example block (L1005–1011) shows a `TOTAL` row and thousands separators that `CostReport.table()` does not emit, and `_compute_totals` does expose `totals["has_unknown_model"]` [Agent 2 finding]
- `docs/reference/CLI.md:3722` — `ll-history quality` coverage note ("`cost_usd` is null for any model absent from `pricing.MODEL_PRICING`") and `docs/guides/HISTORY_SESSION_GUIDE.md:505` in `Why cost coverage matters` [Agent 2 finding]
- `docs/observability/tier0-traces.md:147` — describes `has_unknown_model` as "bucket-poisoned" and the `n/a` rendering, and cites `cost_graph.py` / `pricing.py` by line number (L228–231); `docs/observability/realized-savings-verification.md:39` carries the `cost_usd: 0.0` / `has_unknown_model: true` description [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md:1008` — `### cost_ceiling_unknown` reasons (L1010–1019), relevant if the approximate-cost ceiling decision changes event semantics [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:228` — "unknown cost is never treated as under budget" in `Per-State Cost Ceiling` [Agent 2 finding]
- `CHANGELOG.md` — entry belongs in a concrete release section at release prep, not `[Unreleased]` [Agent 1 finding]

## Status

**Open** | Created: 2026-10-02 | Priority: P4

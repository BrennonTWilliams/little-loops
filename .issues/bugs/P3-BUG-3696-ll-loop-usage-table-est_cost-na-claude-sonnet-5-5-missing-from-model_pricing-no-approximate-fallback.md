---
id: BUG-3696
type: BUG
title: 'll-loop usage table est_cost n/a: claude-sonnet-5-5 missing from MODEL_PRICING,
  no approximate fallback'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:30Z'
parent: EPIC-3562
---

# BUG-3696: ll-loop usage table est_cost n/a: claude-sonnet-5-5 missing from MODEL_PRICING, no approximate fallback

## Summary

The `ll-loop run` usage table shows `est_cost` as `n/a` for every state because the run's model, `claude-sonnet-5-5`, has no entry in `MODEL_PRICING`. The tool should estimate at API list prices regardless of how the user is billed (subscription or API key), and an unrecognized model ID should degrade to a flagged estimate rather than blanking the column.

## Current Behavior

Run `refine-to-ready-issue-20261002T111524` (model `claude-sonnet-5-5`, as recorded in `usage.jsonl`) printed `est_cost` = `n/a` for all five states. Cause chain:

1. `scripts/little_loops/pricing.py` `MODEL_PRICING` has `claude-sonnet-5` but no `claude-sonnet-5-5` (it does have `claude-opus-5-5` and `claude-fable-5-1`). Verified: `estimate_cost_usd("claude-sonnet-5-5", ...)` returns `None`, while `claude-sonnet-5`, `claude-opus-5-5` and `claude-fable-5-1` all price.
2. `estimate_cost_usd` returns `None` on any unknown model; `fsm/cost_graph.py` (`from_usage_jsonl`) then sets `has_unknown_model`, and `PerStateCost.table_row` renders `n/a`.
3. Because cost is `None` whenever any contributor is unpriced, one unknown model blanks the per-state cost and the run-wide total (`_compute_totals`). The same gap leaves null `cost_usd` rows in `usage_events` (see the FEAT-3183 note in `pricing.py`).

## Steps to Reproduce

1. Run `python -c "from little_loops.pricing import estimate_cost_usd as e; print(e('claude-sonnet-5-5', 1000, 1000), e('claude-sonnet-5', 1000, 1000))"`.
2. Observe `None` for `claude-sonnet-5-5` and a float for `claude-sonnet-5`.
3. Run any `ll-loop run <loop>` whose host model is `claude-sonnet-5-5` (e.g. `refine-to-ready-issue`).
4. Observe the end-of-run usage table print `n/a` in `est_cost` for every state.

## Expected Behavior

- `claude-sonnet-5-5` is priced at its published API rate.
- Cost is shown even when the host is on a subscription: this is an API-price estimate, not a billed amount.
- A model ID absent from the table falls back to the closest known family (longest-prefix match, e.g. `claude-sonnet-5-5` -> `claude-sonnet-5`) and the table marks the figure as approximate (e.g. `~$0.1234`), rather than `n/a`.

## Motivation

Every run on a newly released model silently loses cost visibility: the usage table shows `n/a` per state, the run-wide total is blanked, and `usage_events` accumulates null `cost_usd` rows that degrade history-based cost analysis. A single unpriced model ID blanks the whole column, so a missing table entry should degrade to a flagged estimate and a test should catch the gap before a release ships it.

## Proposed Solution

1. Add `claude-sonnet-5-5` to `MODEL_PRICING` using the current published rate (confirm against the Anthropic pricing page; do not copy `claude-sonnet-5`'s rate by assumption, since `claude-opus-5-5` and `claude-fable-5-1` differ from their predecessors).
2. Add a family-prefix fallback in `estimate_cost_usd` (or a sibling helper) that returns an estimate plus an `approximate` flag; thread the flag through `PerStateCost` / `CostReport.to_dict` and render a `~` prefix in `table_row`. Keep the stable-JSON shape change additive.
3. Add a test that fails when a model ID the harness can emit (`claude-<family>-<major>[-<minor>]` from the host runner's model map) has no price entry, so a new model cannot silently regress to `n/a`.
4. Verify `ll-history quality`'s cost-coverage gate treats approximate rows distinctly from exact ones.

## Integration Map

### Files to Modify
- `scripts/little_loops/pricing.py` - `MODEL_PRICING`, `estimate_cost_usd`
- `scripts/little_loops/fsm/cost_graph.py` - `PerStateCost`, `table_row`, `from_usage_jsonl`, `_compute_totals`
- `docs/reference/API.md` - pricing / cost-report notes if the JSON shape gains a field

### Tests
- `scripts/tests/` pricing and `cost_graph` tests; new price-coverage test

### Codebase Research Findings

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

## Program Design

### Types

- `PerStateCost.approximate: bool = False` — new additive field; True when any contributing row was priced via family-prefix fallback

### Signatures

- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> float | None` — existing; exact-match behavior unchanged
- `estimate_cost_usd_approx(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> tuple[float, bool] | None` — new sibling; exact match first, then longest-prefix family match against `MODEL_PRICING`; the bool is the `approximate` flag
- `PerStateCost.table_row(self) -> str` — existing; renders `~$X.XXXX` when `approximate`, `n/a` only for an unrecognized family

### Call Path

`CostReport.from_usage_jsonl` -> `estimate_cost_usd_approx` -> `estimate_cost_usd` — per-row pricing, flag aggregated per state.

`CostReport.from_usage_jsonl` -> `PerStateCost.table_row` — rendering of the approximate marker.

## Implementation Steps

1. Add `claude-sonnet-5-5` to `MODEL_PRICING` at the confirmed published rate.
2. Add the family-prefix fallback with an `approximate` flag; thread it through `PerStateCost` and `CostReport.to_dict` additively, and render the `~` prefix in `table_row`.
3. Add a test that fails when a harness-emittable model ID has no price entry.
4. Verify `ll-history quality`'s cost-coverage gate distinguishes approximate from exact rows; update `docs/reference/API.md` if the JSON shape gains a field.
5. Run `python -m pytest scripts/tests/` and re-render the ENH-3678 `usage.jsonl` table to confirm no `n/a`.

## Impact

- **Priority**: P3 - cosmetic for the user, but also leaves null `cost_usd` rows in history
- **Effort**: Small
- **Risk**: Low

## Acceptance Criteria

- [ ] `estimate_cost_usd("claude-sonnet-5-5", ...)` returns a float at the published rate
- [ ] A model ID with no table entry but a known family prefix yields an approximate estimate, not `None`
- [ ] `ll-loop run` usage table shows `$X.XXXX` (or `~$X.XXXX` when approximate) for the ENH-3678 `usage.jsonl`; no `n/a` for a known family
- [ ] A test fails if a model ID emitted by the harness lacks a price entry
- [ ] `python -m pytest scripts/tests/` exits 0

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-10-02T18:00:09 - `211b3968-8e30-4656-bda0-11230a163531.jsonl`
- `/ll:format-issue` - 2026-10-02T17:52:15 - `dc7de560-ace3-44cc-8c42-afca4eb429ff.jsonl`
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`

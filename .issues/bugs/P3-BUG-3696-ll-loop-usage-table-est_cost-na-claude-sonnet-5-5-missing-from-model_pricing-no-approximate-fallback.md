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
blocks:
- BUG-3701
---

# BUG-3696: ll-loop usage table est_cost n/a: claude-sonnet-5-5 missing from MODEL_PRICING, no approximate fallback

> **Re-run `/ll:confidence-check`** (2026-10-02 review): the earlier scores (90/67) predated the scope revision and were cleared.

## Summary

The `ll-loop run` usage table shows `est_cost` as `n/a` for every state because the run's model, `claude-sonnet-5-5`, has no entry in `MODEL_PRICING`. The tool should estimate at API list prices regardless of how the user is billed (subscription or API key), and an unpriced model ID should be named in the table output instead of silently blanking the column.

> **Scope revision (advisor review, 2026-10-02):** the originally proposed family-prefix fallback (`approximate` flag, `~$` rendering) was dropped. Minor versions within a family are priced differently (`claude-opus-5-5` input $4 vs `claude-opus-5` $5; `claude-fable-5-1` cache read $0.25 vs `claude-fable-5` $1.00), and loop runs are mostly cache tokens, so an "approximate" figure can be 20–75% off. The fix is the exact price entry plus an unpriced-model footer. The fallback is tracked separately as an optional enhancement (see Related below).

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
- When a state's cost is `n/a` because a model ID is absent from `MODEL_PRICING`, the usage table ends with a footer naming each unpriced model ID and where to add it (e.g. `unpriced: claude-sonnet-5-5 — add to little_loops.pricing.MODEL_PRICING`). No cost figure is invented for an unknown model.

## Motivation

Every run on a newly released model silently loses cost visibility: the usage table shows `n/a` per state, the run-wide total is blanked, and `usage_events` accumulates null `cost_usd` rows that degrade history-based cost analysis. A single unpriced model ID blanks the whole column, so the table should say which model is missing and a test should catch gaps in the model tables the repo controls.

## Proposed Solution

1. Add `claude-sonnet-5-5` to `MODEL_PRICING`. Advisor review read the rate from the `claude-api` skill's pricing table (cached 2026-09-25) as **$2 input / $10 output / $0.20 cache read — identical to `claude-sonnet-5`**; cache creation follows the repo's 1.25× convention ($2.50), which that table does not list. **Confirm against the live Anthropic pricing page before merging** — the rate cannot be derived from the repo. Since the rate is identical, follow the `_HAIKU_4_5` pattern: a shared `_SONNET_5` dict used by both `claude-sonnet-5` and `claude-sonnet-5-5`, plus an identity test (like `test_haiku_ids_share_one_rate_dict`). If the confirmed rate differs, use a literal dict instead.
2. Make `n/a` explain itself: track the model IDs whose pricing lookup returned `None` (only lookup failures — not rows that are `None` because a token component was incomplete) in `CostReport.from_usage_jsonl`, and have `CostReport.table()` append the unpriced-model footer when any exist. Keep the stable-JSON shape unchanged (the footer data is Python-API-only, like `has_unknown_model`); `table()` output is unchanged when every model is priced.
3. Add a price-coverage test pinning an explicit, checkable set: `MODEL_ALIASES` values ∪ `MODEL_RANKS["claude-code"]` keys ⊆ `MODEL_PRICING`. Do **not** include `MODEL_CONTEXT_WINDOW`: on current `main` it holds `claude-opus-3-7` and `claude-sonnet-4-5`, neither priced, so the test would fail on landing (BUG-3701 cleans that table). State plainly in the test docstring that this set would not have caught this bug, because `claude-sonnet-5-5` appears in none of those tables (it is reported only by the host in `usage.jsonl`).
4. Note in `pricing.py`'s docstring (and `docs/reference/CLI.md`) that already-written null `cost_usd` rows in `usage_events` are not back-filled; `ll-history quality` semantics are unchanged because the fallback is not introduced.
5. Fix the stale `docs/reference/CLI.md` text (~L1022 `~$X.XXX (model unknown)`, ~L1057 `cost_usd` of `0.0`) to match the real `n/a` / `null` behavior.

## Integration Map

> **Pruned 2026-10-02 (pre-implementation review).** Wiring and research notes written for the dropped prefix fallback (`approximate` flag, `estimate_cost_usd_approx`, `read_json` round-trip, `_check_cost_ceiling`, `session_store/writers.py` call sites, `ll-history quality` row distinction) were moved verbatim to ENH-3703 § Deferred Wiring Notes. Everything below is in scope.

### Files to Modify
- `scripts/little_loops/pricing.py` - `MODEL_PRICING` (shared `_SONNET_5` dict for `claude-sonnet-5` / `claude-sonnet-5-5`), module docstring BUG-3696 note (the docstring is the de facto changelog and cites issue IDs; state that already-written null `usage_events.cost_usd` rows are not back-filled)
- `scripts/little_loops/fsm/cost_graph.py` - `CostReport.from_usage_jsonl` (track unpriced model IDs), `CostReport.table` (footer); `to_dict` / `read_json` / `_compute_totals` unchanged
- `docs/reference/CLI.md` - `est_cost` row (~L1022, "`~$X.XXX (model unknown)`") and ~L1057 ("`cost_usd` is `0.0`") to match the real `n/a` / `null` behavior; the example block (~L1005–1011) shows a `TOTAL` row and thousands separators that `table()` does not emit; document the unpriced-model footer
- `docs/reference/API.md` - `## little_loops.pricing` (~L12618) / `MODEL_PRICING` description (~L12627); do **not** rename the `## little_loops.pricing` heading (pinned by `test_wiring_reference_docs.py:218`)
- `docs/observability/realized-savings-verification.md:39` - stale `cost_usd: 0.0` description (same error as CLI.md ~L1057)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/summary.py:_print_usage_summary` - only caller of `CostReport.table()` in production; no change
- `scripts/little_loops/cli/loop/runner.py:556` - wraps `_print_usage_summary` in `try/except Exception: pass`, so a footer regression is silent; covered by the direct `test_usage_reporter.py` test below
- `scripts/little_loops/fsm/executor.py:4452` (`_check_cost_ceiling`) - unaffected: an unpriced model still yields `cost_usd is None` -> `cost_ceiling_unknown`
- `scripts/little_loops/issue_history/agent_quality.py:208` - comment "cost_usd is null for any model absent from pricing.MODEL_PRICING" stays accurate (ingest stays exact-only)
- `scripts/little_loops/fsm/__init__.py:86` - re-exports `CostReport`; no change (no new public symbol)

### Tests
- `scripts/tests/test_pricing.py:20` - add `claude-sonnet-5-5` to `LIVE_RATES` in the same change as the `MODEL_PRICING` entry (`TestLiveRates::test_every_model_pinned` asserts set equality); `test_rates_match_live_table` / `test_batch_halves_each_rate` then cover it; `test_output_more_expensive_than_input` iterates all of `MODEL_PRICING`
- `scripts/tests/test_pricing.py` - `_SONNET_5` identity test modeled on `test_haiku_ids_share_one_rate_dict`
- `scripts/tests/test_pricing.py:106` - new price-coverage test shaped like `test_every_model_pinned` and `test_host_runner_dispatch.py::TestModelAliasResolution::test_every_alias_target_is_ranked_and_priced`. Pinned set: `MODEL_ALIASES` values ∪ `MODEL_RANKS["claude-code"]` keys ⊆ `MODEL_PRICING`. **`MODEL_CONTEXT_WINDOW` is deliberately excluded:** on current `main` it contains `claude-opus-3-7` (not a real model) and `claude-sonnet-4-5`, neither priced, so including it fails on landing; BUG-3701 owns cleaning that table
- `scripts/tests/test_fsm_cost_graph.py` - footer present for an unpriced model; absent when all models are priced; absent when `None` cost comes only from an incomplete token component; `TestPerStateCost::test_to_dict_exact_keys` keeps passing; `table()` byte-identical for all-priced data. The shared `fixture_jsonl` here and in `test_cli_cost_table.py` uses `claude-sonnet-4-5` (unpriced), so their `table()` output gains the footer; existing assertions there are substring checks (`test_table_matches_existing_layout`, `TestTableOutput`) and should still pass
- `scripts/tests/test_usage_reporter.py:91` - a `claude-sonnet-5-5` row renders `$` and no `n/a`; `test_na_shown_for_unknown_model` still passes and also asserts the footer
- `scripts/tests/test_enh3538_token_observations.py:~400` - `loaded = CostReport.read_json(...)`; `loaded.table()` must still contain `n/a`. A report rebuilt via `read_json` has no `unpriced_models` (Python-API-only, not in the JSON), so it renders **no footer**; assert that explicitly so the behavior is intentional
- `scripts/tests/test_wiring_reference_docs.py:218` - pins the `## little_loops.pricing` heading; keep it

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-02; pruned to in-scope items:_

- A model price is one exact-key entry in `MODEL_PRICING` carrying the four rate keys; two keys sharing a rate share one module-level dict with an identity test (`_HAIKU_4_5`). `estimate_cost_usd` is exact-key only; its signature is unchanged here.
- Additive output stays byte-identical when there is nothing to report (ENH-3538 `*_missing` keys, FEAT-2716 `is_batch`); the footer follows the same rule. `has_unknown_model` is already Python-API-only on `PerStateCost`, so `unpriced_models` being API-only has precedent.
- The model in `usage.jsonl` is whatever the host reports (`subprocess_utils.py` stream-json `system/init`), not an entry of `MODEL_ALIASES`. The set of IDs the harness can emit is unbounded from the codebase's side, so the coverage test pins an explicit, checkable set and its docstring says it would not have caught this bug on its own (it would after BUG-3701 adds `claude-sonnet-5-5` to `MODEL_RANKS`).
- Nothing in the repo prices `claude-sonnet-5-5`; the published rate must be confirmed externally.

### Documentation
- `docs/reference/CLI.md` - see Files to Modify; the `ll-history quality` coverage note (~L3722) stays accurate
- `docs/observability/tier0-traces.md:147` - describes the `n/a` rendering; add one line about the footer if it enumerates table output
- `CHANGELOG.md` - entry belongs in a concrete release section at release prep, not `[Unreleased]`

## Program Design

### Types

- `CostReport.unpriced_models: list[str]` — new Python-API-only field (default empty, sorted, de-duplicated); model IDs whose `estimate_cost_usd` lookup returned `None` while every token component was present. Not emitted by `to_dict`, so the stable-JSON shape is unchanged.
- `_SONNET_5: dict[str, float]` — shared rate dict for `claude-sonnet-5` and `claude-sonnet-5-5` (module-level in `pricing.py`, like `_HAIKU_4_5`).

### Signatures

- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> float | None` — existing; unchanged (exact-key lookup; unknown model → `None`)
- `CostReport.table(self) -> str` — existing; appends a final `unpriced: <ids> — add to little_loops.pricing.MODEL_PRICING` line only when `unpriced_models` is non-empty; otherwise byte-identical to today
- `CostReport.from_usage_jsonl(cls, path: Path) -> CostReport` — existing; additionally records unpriced model IDs

### Call Path

`CostReport.from_usage_jsonl` -> `estimate_cost_usd` — per-row pricing; a `None` result with complete tokens records the model in `unpriced_models`.

`CostReport.table` -> `CostReport.from_usage_jsonl` result's `unpriced_models` — footer rendering (via `_print_usage_summary` in `cli/loop/summary.py`).

## Implementation Steps

1. Confirm the `claude-sonnet-5-5` rate against the live Anthropic pricing page; add it to `MODEL_PRICING` via a shared `_SONNET_5` dict (literal dict if the rate differs), add it to `LIVE_RATES` in the same change, and add the identity test and a BUG-3696 `pricing.py` docstring note.
2. In `cost_graph.py`, track unpriced model IDs in `from_usage_jsonl` (lookup failures only, not incomplete-token rows) and render the footer in `CostReport.table()`; leave `to_dict`/`read_json`/`_compute_totals` unchanged.
3. Add the pinned-set price-coverage test (`MODEL_ALIASES` values ∪ `MODEL_RANKS["claude-code"]` keys ⊆ `MODEL_PRICING`; `MODEL_CONTEXT_WINDOW` excluded) with a docstring stating it would not have caught this bug.
4. Fix the stale `docs/reference/CLI.md` `est_cost` / `cost_usd` text and document the footer; note that already-written null `usage_events.cost_usd` rows are not back-filled.
5. Run `python -m pytest scripts/tests/`. Optionally (non-gating) re-render `.loops/runs/refine-to-ready-issue-20261002T111524/usage.jsonl` (7 rows, all `claude-sonnet-5-5`) if it still exists; run dirs are transient.

### Wiring Phase (added by `/ll:wire-issue`, narrowed by scope revision)

_Touchpoints that remain in scope:_

- Update `scripts/tests/test_pricing.py` — add `claude-sonnet-5-5` to `LIVE_RATES` (same change as the `MODEL_PRICING` entry), the `_SONNET_5` identity test, and the pinned-set price-coverage test
- Update `scripts/little_loops/fsm/cost_graph.py` — `unpriced_models` tracking in `from_usage_jsonl` and the footer in `table()`
- Update `scripts/tests/test_fsm_cost_graph.py` — footer present for an unpriced model, absent when all priced, absent when `None` cost comes only from an incomplete token component, `to_dict` keys unchanged (`test_to_dict_exact_keys` keeps passing), `table()` byte-identical for all-priced data
- Update `scripts/tests/test_usage_reporter.py` — a `claude-sonnet-5-5` row renders `$` and no `n/a`; `test_na_shown_for_unknown_model` still passes and now also asserts the footer
- Update `docs/reference/CLI.md` (L1022, L1057, example block, L3722 null-row note) and `docs/reference/API.md` (`## little_loops.pricing` — keep the heading, pinned by `test_wiring_reference_docs.py:218`)
- Confirm the `claude-sonnet-5-5` rate externally (not derivable from the repo)

_Deferred to the follow-up fallback enhancement:_ `estimate_cost_usd_approx`, `PerStateCost.approximate`, `read_json` round-trip, `_check_cost_ceiling` decision, `session_store/writers.py` switch, `ll-history quality` row distinction.

## Impact

- **Priority**: P3 - cosmetic for the user, but also leaves null `cost_usd` rows in history
- **Effort**: Small
- **Risk**: Low

## Acceptance Criteria

- [ ] `estimate_cost_usd("claude-sonnet-5-5", ...)` returns a float at the live-confirmed published rate, and `claude-sonnet-5` / `claude-sonnet-5-5` share one rate dict when the rates are identical (identity test)
- [ ] A `usage.jsonl` fixture whose rows are all `claude-sonnet-5-5` (shape of run `refine-to-ready-issue-20261002T111524`) renders `$X.XXXX` with no `n/a` and no footer through `_print_usage_summary`
- [ ] A state whose cost is `n/a` because a model is absent from `MODEL_PRICING` produces a table footer naming each unpriced model ID; the footer is absent when all models are priced or when `None` cost comes only from incomplete token components; `CostReport.to_dict` keys are unchanged
- [ ] A test fails if any `MODEL_ALIASES` target or `MODEL_RANKS["claude-code"]` entry lacks a `MODEL_PRICING` entry (docstring states this set would not have caught BUG-3696; `MODEL_CONTEXT_WINDOW` is excluded until BUG-3701 cleans it)
- [ ] `docs/reference/CLI.md` `est_cost` / `cost_usd` text (and `docs/observability/realized-savings-verification.md:39`) matches actual `n/a` / `null` behavior
- [ ] A report rebuilt via `CostReport.read_json` renders no footer (asserted, so the API-only scope is intentional)
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- ENH-3703 — optional family-prefix pricing fallback with an `approximate` flag (deferred from this issue)
- BUG-3701 — stale `MODEL_ALIASES['sonnet']` / `MODEL_RANKS` missing `claude-sonnet-5-5` (split out; not a pricing concern)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-10-02T19:45:19 - `9a15ba2c-4c77-475b-8d6d-2e5aa8b1186f.jsonl`
- `/ll:wire-issue` - 2026-10-02T19:42:58 - `4830feb2-90ba-4747-9939-6d60a5df22df.jsonl`
- `/ll:refine-issue` - 2026-10-02T19:40:25 - `3112767e-a69b-4d0d-ad44-28f11d927193.jsonl`
- `/ll:refine-issue` - 2026-10-02T18:00:09 - `211b3968-8e30-4656-bda0-11230a163531.jsonl`
- `/ll:format-issue` - 2026-10-02T17:52:15 - `dc7de560-ace3-44cc-8c42-afca4eb429ff.jsonl`
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`

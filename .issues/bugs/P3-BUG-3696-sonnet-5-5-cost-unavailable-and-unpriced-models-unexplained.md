---
id: BUG-3696
type: BUG
title: Sonnet 5.5 cost unavailable and unpriced models unexplained
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:30Z'
parent: EPIC-3562
blocks:
- BUG-3701
---

# BUG-3696: Sonnet 5.5 cost unavailable and unpriced models unexplained

> **Re-run `/ll:confidence-check`**: the earlier scores (90/67) predated the scope revision and were cleared. This review does not replace that gate.

## Summary

The `ll-loop run` usage table shows `est_cost` as `n/a` for `claude-sonnet-5-5` because its exact ID is absent from `MODEL_PRICING`. Add the verified price and a footer naming unknown model IDs, including IDs on rows that also have incomplete tokens. The estimate uses published API list prices regardless of subscription/API billing; it is not the user's billed amount.

**Scope:** exact pricing and human-readable diagnostics only. No family-prefix fallback, invented rate, stable-JSON change, cost-ceiling change, or history backfill. ENH-3703 owns the optional approximate fallback; BUG-3701 owns the alias/rank correction; BUG-3704 owns effective context windows.

## Current Behavior

Run `refine-to-ready-issue-20261002T111524` recorded `claude-sonnet-5-5` on all seven `usage.jsonl` rows and printed `n/a` for all five states.

1. `scripts/little_loops/pricing.py:MODEL_PRICING` contains `claude-sonnet-5` but lacks `claude-sonnet-5-5`. `estimate_cost_usd('claude-sonnet-5-5', 1000, 1000)` returns `None`.
2. `CostReport.from_usage_jsonl` sets a state's cost to `None` if any row is unpriced. It also skips the estimator entirely for a row with a null token component or a positive `*_missing` count. The existing `has_unknown_model` flag therefore covers both absent prices and incomplete observations; it cannot identify why a row is unpriced.
3. `PerStateCost.table_row()` renders `n/a`, and `_compute_totals` leaves the run's total cost null. Known-cost subtotals are not presented as complete totals.
4. New history `usage_events` rows for the absent model also receive null `cost_usd`; already-written null rows are not recomputed when a rate is added.

## Steps to Reproduce

1. Run `python -c "from little_loops.pricing import estimate_cost_usd as e; print(e('claude-sonnet-5-5', 1000, 1000), e('claude-sonnet-5', 1000, 1000))"`.
2. Observe `None` and `0.012` respectively.
3. Build a usage report with `model: claude-sonnet-5-5`; the cost is `n/a` with no explanation of the missing model price.

## Expected Behavior

- Complete Sonnet 5.5 observations are priced at their published standard API rates, including cache tokens and the existing batch discount.
- A report built from `usage.jsonl` lists each ID absent from `MODEL_PRICING` once in a sorted footer, even when the same row also has incomplete tokens.
- A known model with incomplete tokens remains unpriced and does not create an unpriced-model footer entry. The footer explains missing prices, not every possible reason for `n/a`.
- Reports containing only priced models retain their existing table output. The stable JSON remains unchanged and cannot carry the model-specific footer through `read_json`.

## Motivation

New host-reported model IDs can silently erase state/run cost visibility and leave gaps in history cost coverage. Alias/rank coverage can catch drift in tables controlled by the repo, while the footer diagnoses models that arrive from the host outside those tables.

## Proposed Solution

1. Add `claude-sonnet-5-5` at **$2 input / $10 output / $0.20 cache read / $2.50 five-minute cache creation per million tokens**. All four values were confirmed on the live [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing) and [Sonnet 5.5 specifications](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) on 2026-10-02. The pricing page also confirms identical Sonnet 5 rates, so share a `_SONNET_5` dict following the existing `_HAIKU_4_5` pattern. The rates are standard; `INTRO_PRICING` is currently empty and this fix adds no introductory entry. Keep the repo's aggregate cache-creation convention; one-hour TTL pricing is outside scope.
2. Add `CostReport.unpriced_models: list[str] = field(default_factory=list)`, populated as sorted, de-duplicated IDs. Check exact membership in the same imported `MODEL_PRICING` table used by the estimator, independently of the token-completeness branch. Do not infer missing prices from `cost is None` or `has_unknown_model`, and do not change token normalization or cost aggregation.
3. Append `unpriced: <comma-separated IDs> — add to little_loops.pricing.MODEL_PRICING` in `table()` only when the list is non-empty. Do not serialize the list. `read_json` defaults it to empty because the locked JSON contains no model IDs; test that limitation with a genuinely unknown-model report.
4. Add coverage for `set(MODEL_ALIASES.values()) | set(MODEL_RANKS['claude-code']) <= set(MODEL_PRICING)`. All current alias/rank IDs, including Opus 5 and Fable 5, already have prices, so it passes before BUG-3701 lands. Explain in the test that this alone would not have caught BUG-3696: Sonnet 5.5 is currently absent from both selection tables. Do not include context-window keys: real legacy models can need context sizing without pricing support.
5. Correct stale CLI/observability documentation about `~$` fallback, `0.0` unknown costs, a printed `TOTAL` row, and thousands separators. State that costs remain exact-ID estimates, state/run costs become null if any contributor is unpriced, and stored null history costs are not back-filled.

## Integration Map

### Files to Modify

- `scripts/little_loops/pricing.py` — shared `_SONNET_5` rates, Sonnet 5.5 entry, source/date and no-backfill note
- `scripts/little_loops/fsm/cost_graph.py` — import the shared pricing table, collect diagnostic IDs in `from_usage_jsonl`, add the report field and table footer; keep `to_dict`, `read_json` parsing, and `_compute_totals` semantics
- `scripts/tests/test_pricing.py` — Sonnet 5.5 in `LIVE_RATES` (the existing set-equality test requires it), shared-dict identity, explicit standard-price/date and batch coverage, alias/rank coverage
- `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_usage_reporter.py`, `scripts/tests/test_cli_cost_table.py` — diagnostics and output compatibility
- `docs/reference/CLI.md` — per-state summary (~L1005–1057), correct examples and state-vs-total JSON flags, footer and no-backfill limitation
- `docs/reference/API.md` — pricing description (~L12615); keep the `## little_loops.pricing` heading pinned by `test_wiring_reference_docs.py`
- `docs/observability/realized-savings-verification.md:39` — replace stale `cost_usd: 0.0` with null
- `docs/observability/tier0-traces.md:147` — document the footer alongside existing table output

### Dependent Files

- `cli/loop/summary.py:_print_usage_summary` — production table caller; no change
- `cli/loop/runner.py` — summary exceptions are swallowed, so direct reporter regression coverage is required
- `fsm/executor.py:_check_cost_ceiling` — unchanged; an unpriced cost still follows `cost_ceiling_unknown`
- `session_store/writers.py` — gains the new exact rate through its current estimator import; no new lookup or ingestion path
- `issue_history/agent_quality.py` — null-cost coverage semantics remain accurate
- `fsm/__init__.py` — existing `CostReport` export; no new symbol

### Tests

- Exercise **known/unknown model × complete/incomplete tokens**. Include explicit null components and positive `*_missing` counts. Unknown+incomplete must still name the ID; known+incomplete must not. Legacy absent-token keys retain their current zero defaults.
- Multiple unpriced IDs across states, repeated IDs, and mixed priced/unpriced contributors: one sorted footer; affected state and run costs stay null; complete known-only states retain their numeric costs.
- Sonnet 5.5 reporter fixture using all four token components: assert the numeric estimate, no `n/a`, no footer. One million of each component costs $14.70 synchronously and $7.35 with the existing batch discount.
- Complete, already-priced data: compare full table bytes, preserving header, separator, row sorting, formatting, and trailing newline. `fixture_jsonl` in `test_fsm_cost_graph.py` and `test_cli_cost_table.py` uses unpriced Sonnet 4.5, so its table deliberately gains the footer; do not relabel it as priced.
- Unknown-model JSON round-trip: `loaded.to_dict() == report.to_dict()`, null costs preserved, no `unpriced_models` key, loaded list empty, and loaded table has no footer. Do not assert dataclass equality: diagnostic metadata is intentionally lost. The existing `test_enh3538_token_observations.py` incomplete-known-model round-trip remains valid but cannot alone prove unknown-model metadata loss.
- Keep the locked per-state/top-level JSON key tests and the existing alias-target-ranked-and-priced test.

## Program Design

### Types

- `_SONNET_5: dict[str, float]` — shared standard rate dict for the two exact Sonnet IDs, following the existing shared Haiku pattern
- `CostReport.unpriced_models: list[str]` — diagnostic-only, default empty; sorted and de-duplicated by `from_usage_jsonl`; absent from stable JSON

### Signatures

- `estimate_cost_usd(...) -> float | None` — existing signature and exact-ID/complete-token semantics unchanged
- `CostReport.from_usage_jsonl(path)` — adds independent model-price membership tracking before the incomplete-token pricing shortcut
- `CostReport.table()` — optional footer, otherwise identical output

### Call Path

`cli/loop/summary.py:_print_usage_summary` -> `CostReport.from_usage_jsonl` -> membership in `pricing.MODEL_PRICING` for diagnostics and `estimate_cost_usd` for complete observations -> `CostReport.table` for the footer. `CostReport.write_json` -> `to_dict` retains the locked JSON; `CostReport.read_json` constructs a report with the diagnostic list's empty default.

## Implementation Steps

1. Add the verified exact rates and corresponding `LIVE_RATES`, identity, standard-date and batch tests.
2. Add the independent unpriced-ID collection and conditional footer; implement the four-way completeness test matrix and mixed-model cases.
3. Add alias/rank coverage and the explicit JSON diagnostic-loss regression test.
4. Correct the listed reference/observability docs and examples; retain current cost-ceiling and history-coverage behavior.
5. Run `python -m pytest scripts/tests/`. Optionally re-render the original seven-row run if its transient directory still exists; use a committed fixture for the gate.

## Impact

- **Priority**: P3 — cost visibility and history coverage are missing for a current model; this also reaches consumers of run costs
- **Effort**: Small
- **Risk**: Low — exact rate addition and diagnostics, no fallback or aggregation change

## Acceptance Criteria

- [ ] Sonnet 5.5 is priced at the four source-confirmed standard rates; Sonnet 5 and 5.5 share the rate dict with identity and batch tests, and no Sonnet 5.5 introductory rate is added
- [ ] A complete Sonnet 5.5 fixture renders its expected dollar cost through `_print_usage_summary`, with no `n/a` or footer
- [ ] Unknown model IDs are sorted and de-duplicated in the footer with complete or incomplete tokens; incomplete known models do not appear there
- [ ] Mixed known/unknown contributors preserve null state/run cost semantics; all-priced tables remain byte-identical
- [ ] Alias targets and all `MODEL_RANKS['claude-code']` keys have prices; the test states the host-emitted-ID limitation and excludes independent context-window coverage
- [ ] Stable JSON keys are unchanged; an unknown-model report round-trips with null costs and intentionally loses its footer metadata
- [ ] CLI/API/observability docs match actual `n/a`/null behavior, distinguish per-state flags from `totals.has_unknown_model`, describe the footer, and state the no-backfill limitation
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3701 — alias/rank correction; implement after this issue so its new alias target is priced
- BUG-3704 — effective native-1M context windows, independent scope
- ENH-3703 — optional family-prefix approximate pricing; deferred wiring notes from the original proposal live there

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Pricing API and stable cost semantics |
| `docs/ARCHITECTURE.md` | History usage ingestion and null cost coverage |

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log

- Pre-implementation review - 2026-10-02 - `/ll:advise` with Opus (confidence 0.80): confirmed live prices, fixed unknown+incomplete diagnostic scope, expanded regression cases, and moved context-window work to BUG-3704. Existing shared rate-dict precedent retained; no speculative equality contract or new price-lookup API added.
- `/ll:confidence-check` - 2026-10-02T19:45:19 - `9a15ba2c-4c77-475b-8d6d-2e5aa8b1186f.jsonl`
- `/ll:wire-issue` - 2026-10-02T19:42:58 - `4830feb2-90ba-4747-9939-6d60a5df22df.jsonl`
- `/ll:refine-issue` - 2026-10-02T19:40:25 - `3112767e-a69b-4d0d-ad44-28f11d927193.jsonl`
- `/ll:refine-issue` - 2026-10-02T18:00:09 - `211b3968-8e30-4656-bda0-11230a163531.jsonl`
- `/ll:format-issue` - 2026-10-02T17:52:15 - `dc7de560-ace3-44cc-8c42-afca4eb429ff.jsonl`
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`

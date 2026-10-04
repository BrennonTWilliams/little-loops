---
id: BUG-3696
type: BUG
title: 'Sonnet 5.5 cost unavailable: claude-sonnet-5-5 absent from MODEL_PRICING'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:30Z'
parent: EPIC-3562
blocks:
- BUG-3701
- ENH-3719
---

# BUG-3696: Sonnet 5.5 cost unavailable: claude-sonnet-5-5 absent from MODEL_PRICING

> **Re-run `/ll:confidence-check`**: earlier scores (90/67) predated two scope revisions (2026-10-02 and the 2026-10-04 split) and were cleared. This review does not replace that gate.

## Summary

The `ll-loop run` usage table shows `est_cost` as `n/a` for `claude-sonnet-5-5` because its exact ID is absent from `MODEL_PRICING`. Add the verified price, pin it with tests, and add alias/rank/price coverage. **This issue is pricing only.** The unpriced-model footer, the missing-ID sentinel matrix, the reporter/JSON tests and the cost-table doc sweep were split into ENH-3719 (2026-10-04) so this one-line fix can land and unblock BUG-3701 on its own. Closing this issue (`done`) resolves BUG-3701's dependency edge. The estimate uses published API list prices regardless of subscription/API billing; it is not the user's billed amount.

**Scope:** the exact `claude-sonnet-5-5` rate, its tests, `pricing.py` header notes and rank/alias/price coverage. No family-prefix fallback (ENH-3703), invented rate, stable-JSON change, cost-ceiling change, history backfill, footer or doc sweep (ENH-3719), alias/rank correction (BUG-3701), or effective context windows (BUG-3704).

## Current Behavior

Run `refine-to-ready-issue-20261002T111524` recorded `claude-sonnet-5-5` on all seven `usage.jsonl` rows and printed `n/a` for all five states. Re-read on 2026-10-03: every row still has that exact ID, without a provider prefix, date or `[1m]` suffix. The first row has 14 input, 5748 output, 433686 cache-read and 70335 cache-creation tokens; at the verified standard rates its estimate is $0.3200827, rendered `$0.3201`.

1. `scripts/little_loops/pricing.py:MODEL_PRICING` contains `claude-sonnet-5` but lacks `claude-sonnet-5-5`. `estimate_cost_usd('claude-sonnet-5-5', 1000, 1000)` returns `None`.
2. `CostReport.from_usage_jsonl` therefore sets the state cost to `None`, `PerStateCost.table_row()` renders `n/a`, and `_compute_totals` leaves the run total null.
3. New history `usage_events` rows for the absent model also receive null `cost_usd`; already-written null rows are not recomputed when a rate is added.

## Steps to Reproduce

1. Run `python -c "from little_loops.pricing import estimate_cost_usd as e; print(e('claude-sonnet-5-5', 1000, 1000), e('claude-sonnet-5', 1000, 1000))"`.
2. Observe `None` and `0.012` respectively.

## Expected Behavior

- Complete Sonnet 5.5 observations are priced at their published standard API rates, including cache tokens and the existing batch discount.
- `estimate_cost_usd` semantics are otherwise unchanged (exact-ID lookup, complete tokens only).
- Every alias target and every `MODEL_RANKS['claude-code']` key is priced.

## Motivation

New host-reported model IDs silently erase state/run cost visibility and leave gaps in history cost coverage. Sonnet 5.5 is the model the host's own `sonnet` alias already resolves to, so most local runs are affected today. BUG-3701 cannot land its alias/rank change until the new alias target is priced.

## Proposed Solution

1. Add `claude-sonnet-5-5` at **$2 input / $10 output / $0.20 cache read / $2.50 five-minute cache creation per million tokens**. All four values were confirmed on the live [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing) and [Sonnet 5.5 specifications](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) on 2026-10-02 and re-confirmed 2026-10-03. The pricing page also confirms identical Sonnet 5 rates, so reuse a `_SONNET_5` dict following the existing `_HAIKU_4_5` pattern. Pin each model's literal rates and batch behavior; object identity is not an acceptance contract and future independent repricing remains possible. The rates are standard; `INTRO_PRICING` is currently empty and this fix adds no introductory entry. Keep the repo's aggregate cache-creation convention; one-hour TTL pricing is out of scope.
2. **Extend the existing test** `test_every_alias_target_is_ranked_and_priced` (`scripts/tests/test_host_runner_dispatch.py:444`) rather than adding a duplicate in `test_pricing.py`: assert `set(MODEL_ALIASES.values()) | set(MODEL_RANKS['claude-code']) <= set(MODEL_PRICING)`. All six current IDs (Haiku 4.5, Sonnet 5, Opus 5/5.5, Fable 5/5.1) already have prices (re-probed 2026-10-03), so it passes before BUG-3701 lands and needs no unrelated price additions. Add a docstring noting that this alone would not have caught this bug: Sonnet 5.5 is currently absent from both selection tables, and the test cannot see host-emitted IDs. Do not include context-window keys: real legacy models can need context sizing without pricing support.
3. Update the `pricing.py` module header: the "as of" date, `claude-sonnet-5-5` in the source note, and the known gap that lookup is exact-match so dated, `anthropic.`-prefixed or `[1m]` model IDs stay unpriced. Do **not** guess a `claude-sonnet-4-5` rate; add it only if real history shows it (ENH-3719's footer will surface it).
4. Update the `docs/reference/API.md` `## little_loops.pricing` description (~L12630) only where it enumerates covered models or states pricing semantics that change. Keep the heading pinned by `test_wiring_reference_docs.py`. The broader cost-table doc sweep belongs to ENH-3719.

## Integration Map

### Files to Modify

- `scripts/little_loops/pricing.py` — shared `_SONNET_5` rates, Sonnet 5.5 entry, source/date and exact-match/no-backfill header notes
- `scripts/tests/test_pricing.py` — Sonnet 5.5 in `LIVE_RATES` (the existing set-equality test requires it), literal standard-rate/date and batch coverage for both Sonnet IDs, observed-row projection
- `scripts/tests/test_host_runner_dispatch.py` — extend `test_every_alias_target_is_ranked_and_priced` to include all `MODEL_RANKS['claude-code']` keys
- `docs/reference/API.md` — pricing description (~L12630), only if affected

### Dependent Files

- `fsm/cost_graph.py` — gains the rate through the existing `estimate_cost_usd` import; no change here (footer is ENH-3719)
- `session_store/writers.py` — gains the new exact rate through its current estimator import; no new lookup or ingestion path
- `fsm/executor.py:_check_cost_ceiling` — unchanged
- `issue_history/agent_quality.py` — null-cost coverage semantics remain accurate

### Tests

- `LIVE_RATES` includes `claude-sonnet-5-5` with the four literal rates; both Sonnet IDs have literal-rate and batch tests. One million of each token component costs $14.70 synchronously and $7.35 with the existing batch discount for both IDs.
- Observed-run regression at pricing level: `estimate_cost_usd('claude-sonnet-5-5', 14, 5748, 433686, 70335)` ≈ 0.3200827 (committed fixture, independent of the transient run directory). ENH-3719 adds the through-the-reporter version.
- No `INTRO_PRICING` entry exists for Sonnet 5.5.
- Dated, `anthropic.`-prefixed and `[1m]`-suffixed Sonnet 5.5 IDs return `None` from `estimate_cost_usd` (documents the exact-match gap).
- Extended alias/rank/price coverage test; keep the existing locked JSON key tests untouched.

## Program Design

### Types

- `_SONNET_5: dict[str, float]` — shared standard rate dict for the two exact Sonnet IDs, following the shared Haiku pattern

### Signatures

- `estimate_cost_usd(...) -> float | None` — existing signature and exact-ID/complete-token semantics unchanged

### Call Path

`pricing.MODEL_PRICING` -> `pricing.estimate_cost_usd` -> `fsm/cost_graph.py:CostReport.from_usage_jsonl` (CLI usage table) and `session_store/writers.py` (history `usage_events.cost_usd`).

## Implementation Steps

1. Add the verified exact rate (`_SONNET_5`), the `pricing.py` header date/source/exact-match notes, and the `LIVE_RATES`, literal-rate, batch and observed-row tests; run `python -m pytest scripts/tests/test_pricing.py`.
2. Extend `test_every_alias_target_is_ranked_and_priced` with the rank-key subset assertion and docstring.
3. Update the API.md pricing description if affected.
4. Run `python -m pytest scripts/tests/`; set `status: done` to resolve BUG-3701 and ENH-3719 dependency edges.

## Impact

- **Priority**: P3 — cost visibility and history coverage are missing for the model the host `sonnet` alias already resolves to
- **Effort**: Small — one rate entry, header note and focused tests
- **Risk**: Low — exact rate addition, no fallback or aggregation change

## Acceptance Criteria

- [ ] Sonnet 5.5 is priced at the four source-confirmed standard rates; both Sonnet IDs have literal-rate/date and batch tests ($14.70 sync / $7.35 batch per 1M of each component); no Sonnet 5.5 introductory rate is added
- [ ] The observed run's first-row token projection prices to ≈ $0.3200827 via `estimate_cost_usd`
- [ ] Dated, `anthropic.`-prefixed and `[1m]` Sonnet 5.5 IDs remain unpriced (exact-match gap documented in the `pricing.py` header)
- [ ] `test_every_alias_target_is_ranked_and_priced` also asserts all `MODEL_RANKS['claude-code']` keys are priced, states the host-emitted-ID limitation, and excludes context-window coverage; no duplicate test is added
- [ ] `pricing.py` header "as of" date and source note are updated; no `claude-sonnet-4-5` rate is invented
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3701 — alias/rank correction; implement after this issue is `done` so its new alias target is priced
- ENH-3719 — unpriced-model footer, sentinel handling, reporter/JSON tests and cost-table doc sweep (split from this issue)
- BUG-3704 — effective native-1M context windows, independent scope
- ENH-3703 — optional family-prefix approximate pricing

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/API.md` | Pricing API and stable cost semantics |
| `docs/ARCHITECTURE.md` | History usage ingestion and null cost coverage |

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log

- Split into BUG-3696 (price) + ENH-3719 (footer/docs) - 2026-10-04 - `/ll:advise` with Opus (confidence 0.78): pricing lands alone so BUG-3701 unblocks cheaply; duplicate coverage test replaced by extending the existing one; footer/sentinel/reporter/doc work moved to ENH-3719 with its test matrix cut to four.
- Pre-implementation review 3 - 2026-10-03 - `/ll:advise` with Opus (confidence 0.80): deliver as one issue; clarify unavailable costs and missing IDs; pin footer bytes and reporter/JSON output; correct input/cache docs; confirm the original seven exact host IDs and current alias/rank price coverage. (Superseded by the 2026-10-04 split.)
- Pre-implementation review 2 - 2026-10-03 - `/ll:advise` with Opus (confidence 0.82): rates re-confirmed; phased delivery (price first), end-user footer wording, header date, no guessed `claude-sonnet-4-5` rate, exact-match known gap.
- Pre-implementation review - 2026-10-02 - `/ll:advise` with Opus (confidence 0.80): confirmed live prices, fixed unknown+incomplete diagnostic scope, expanded regression cases, and moved context-window work to BUG-3704. Existing shared rate-dict precedent retained; no speculative equality contract or new price-lookup API added.
- `/ll:confidence-check` - 2026-10-02T19:45:19 - `9a15ba2c-4c77-475b-8d6d-2e5aa8b1186f.jsonl`
- `/ll:wire-issue` - 2026-10-02T19:42:58 - `4830feb2-90ba-4747-9939-6d60a5df22df.jsonl`
- `/ll:refine-issue` - 2026-10-02T19:40:25 - `3112767e-a69b-4d0d-ad44-28f11d927193.jsonl`
- `/ll:refine-issue` - 2026-10-02T18:00:09 - `211b3968-8e30-4656-bda0-11230a163531.jsonl`
- `/ll:format-issue` - 2026-10-02T17:52:15 - `dc7de560-ace3-44cc-8c42-afca4eb429ff.jsonl`
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`

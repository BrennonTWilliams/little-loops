---
id: BUG-3564
type: BUG
title: MODEL_PRICING has stale rates for Sonnet 5, Opus 4.5-4.7 and Haiku 4.5
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:03:48Z'
labels:
- models
- pricing
- observability
relates_to:
- BUG-3541
- BUG-3579
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3564: MODEL_PRICING has stale rates for Sonnet 5, Opus 4.5-4.7 and Haiku 4.5

## Summary

`little_loops.pricing.MODEL_PRICING` has the wrong rates for several models that are still in use, and the Sonnet 5 introductory-rate override has expired. So `estimate_cost_usd` has been overstating Sonnet 5 costs by 1.5x since 2026-09-01. It overstates Opus 4.5 through 4.7 costs by 3x and understates Haiku 4.5 costs by 20%. These numbers feed `usage_events.cost_usd` at ingest (`session_store/writers.py:1965`, `:3657`), the FSM cost graph (`fsm/cost_graph.py:321`) and cost-ceiling enforcement.

## Current Behavior

Rates below are USD per million tokens, as input / output / cache read / 5-minute cache write. The "live" column comes from the Anthropic pricing page (platform.claude.com/docs/en/about-claude/pricing), checked 2026-09-24.

| Key | `pricing.py` | Live | Error |
|---|---|---|---|
| `claude-sonnet-5` | 3 / 15 / 0.30 / 3.75 (intro 2 / 10 expired 2026-08-31) | 2 / 10 / 0.20 / 2.50 | 1.5x over since 2026-09-01. The page says the $2/$10 intro rate "is now the standard price"; the planned rise to $3/$15 was cancelled. |
| `claude-opus-4-7` | 15 / 75 / 1.50 / 18.75 | 5 / 25 / 0.50 / 6.25 | 3x over |
| `claude-opus-4-6` | 15 / 75 / 1.50 / 18.75 | 5 / 25 / 0.50 / 6.25 | 3x over |
| `claude-opus-4-5` | 15 / 75 / 1.50 / 18.75 | 5 / 25 / 0.50 / 6.25 | 3x over; also sits under the wrong "Claude 3.x (legacy)" comment |
| `claude-haiku-4-5-20251001` | 0.80 / 4 / 0.08 / 1.00 | 1 / 5 / 0.10 / 1.25 | 20% under (these are the Haiku 3.5 rates) |

These entries are correct: `claude-fable-5`, `claude-opus-5`, `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-sonnet-3-7` and `claude-haiku-3-5`. Keys missing for new model IDs (`claude-opus-5-5`, `claude-fable-5-1`, undated `claude-haiku-4-5`) belong to BUG-3541, not this issue.

## Expected Behavior

- `MODEL_PRICING` matches the live pricing table for every key it holds.
- Sonnet 5 is priced at $2/$10 standard from `MODEL_PRICING` itself. Its `INTRO_PRICING` entry is removed, since the intro rate became the permanent rate. Keep the `INTRO_PRICING` mechanism itself for future launches.
- The module docstring's "Source … as of" date is updated, and its sentence saying Sonnet 5's intro rate is "modeled via `INTRO_PRICING`" is rewritten (the rate is now standard in `MODEL_PRICING`; the mechanism stays for future launches).
- `claude-opus-4-5` moves out from under the "Claude 3.x (legacy)" comment into the "Claude 4.x" group.

## Proposed Solution

- Correct the five rows above; delete the `claude-sonnet-5` `INTRO_PRICING` entry.
- `scripts/tests/test_pricing.py` currently locks in a wrong value: `test_post_expiry_uses_standard_rate` asserts Sonnet 5 at `3.0 + 15.0`. (`test_unaffected_model_regression` also asserts `3.0 + 15.0`, but for `claude-sonnet-4-6`, which is correct; keep it.) Add explicit per-model rate assertions against the live table, one row per key, so a future drift fails loudly. `test_all_four_fields_contribute` uses `claude-opus-4-7` but only compares relative costs, so it survives the change.
- `test_pre_expiry_uses_intro_rate`, `test_boundary_2026_08_31_uses_intro_rate` and `test_intro_sub_dict_has_all_rate_keys` need a synthetic `INTRO_PRICING` fixture, via monkeypatch, once the Sonnet 5 entry is gone. That keeps the mechanism covered.

## Integration Map

- `scripts/little_loops/pricing.py` (`MODEL_PRICING`, `INTRO_PRICING`, docstring).
- Consumers, which need no code change but whose behavior shifts: `session_store/writers.py` (ingest and replay `cost_usd`), `fsm/cost_graph.py`, cost-ceiling enforcement (`test_cost_ceiling_enforcement.py`), `ll-history quality` cost coverage (`issue_history/agent_quality.py:214`).
- Tests: `test_pricing.py`, `test_fsm_cost_graph.py`, `test_cli_cost_table.py` (check for hard-coded dollar expectations).

## Program Design

### Types
- No new types. `MODEL_PRICING: dict[str, dict[str, float]]` and `INTRO_PRICING: dict[str, dict[str, float | str]]` keep their shapes; only data changes.

### Signatures
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False) -> float | None` — unchanged; reads the corrected rows (`pricing.py:113`).

### Call Path
`estimate_cost_usd` -> `MODEL_PRICING` lookup (the `INTRO_PRICING` override no longer matches `claude-sonnet-5`)

### Decision Rules
- A model whose intro rate became permanent is priced from `MODEL_PRICING` directly; its `INTRO_PRICING` entry is deleted, not left expired.
- Every rate is a data change only; no consumer code changes.

## Impact

- **Priority**: P2. Sonnet 5 and Opus 4.x are high-volume models here, so reported spend and cost-ceiling trips are wrong by 1.5 to 3x.
- **Effort**: Small.
- **Risk**: Low. The change is data only, but cost ceilings will trip later than they do today.

## Steps to Reproduce

1. `python -c "from little_loops.pricing import estimate_cost_usd as e; print(e('claude-sonnet-5', 1_000_000, 1_000_000))"` on any date after 2026-08-31.
2. Observe `18.0`; expected `12.0`.
3. Same call with `claude-opus-4-7`: observe `90.0`, expected `30.0`.

## Scope Boundaries

- **In scope**: correcting existing rates; removing the expired Sonnet 5 intro entry; rate-assertion tests.
- **Out of scope**: adding keys for new aliases/IDs (BUG-3541); 1-hour cache-write pricing (`cache_creation` models the 5-minute rate only); inference-geo / fast-mode multipliers; recomputing `cost_usd` already stored in `usage_events`. Stored rows keep the wrong cost until replayed through `_backfill_usage_events`. Document that, or capture a follow-up if a reprice command is wanted.

## Acceptance Criteria

- [ ] Each `MODEL_PRICING` row matches the live pricing table. A test asserts all four rates for every key.
- [ ] `estimate_cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == 12.0` on any date.
- [ ] `claude-opus-4-5/6/7` price at $5/$25; `claude-haiku-4-5-20251001` at $1/$5.
- [ ] The `INTRO_PRICING` mechanism stays covered by a synthetic-entry test.
- [ ] The `is_batch` discount still halves each corrected rate.
- [ ] The module docstring no longer describes Sonnet 5 as intro-priced, and `claude-opus-4-5` sits under the "Claude 4.x" comment.
- [ ] The synthetic `INTRO_PRICING` fixture is reusable (a module-level pytest fixture or helper), since BUG-3579 builds on it.

## Follow-up (captured as BUG-3579)

`estimate_cost_usd` decides whether an `INTRO_PRICING` entry applies with `date.today()` (`pricing.py:143`), not the usage event's timestamp. Replay and backfill (`_backfill_usage_events`) therefore price historical events at the rate in force on the day of the replay. This is moot for Sonnet 5 once its entry is removed (intro and standard rates are now identical), but the `INTRO_PRICING` mechanism kept for future launches carries the flaw. Fixing it means threading the event date into `estimate_cost_usd`; out of scope here.

## Related

- BUG-3541: adds the missing keys for `claude-opus-5-5`, `claude-fable-5-1` and undated `claude-haiku-4-5`. Either can land first. If BUG-3541 lands first, its haiku alias must share the dated entry's dict so this fix corrects both.

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-24T22:09:36 - `6c1833f1-29b8-4569-8cd1-c7e84a3f7e66.jsonl`

---
id: BUG-3541
title: MODEL_ALIASES maps opus and fable to superseded model IDs
type: BUG
priority: P2
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_date: '2026-09-23'
labels:
- multi-host
- models
relates_to:
- BUG-3564
---

# MODEL_ALIASES maps opus and fable to superseded model IDs

## Summary

`host_runner.MODEL_ALIASES` (`scripts/little_loops/host_runner.py:97-102`)
resolves `opus → claude-opus-5` and `fable → claude-fable-5`. The current
lineup is Opus 5.5 (`claude-opus-5-5`) and Fable 5.1 (`claude-fable-5-1`).
The CLI path is unaffected (the host binary resolves aliases itself), but every
SDK/batch request (`orchestration.request_path: sdk|batch`) that uses `opus` or
`fable` is sent to the older model. ENH-3527 derives its `anthropic-api`
`reasoning` hint target from this table, so the staleness would carry into
hints too.

## Current Behavior

- `resolve_model_alias("opus")` → `claude-opus-5`; `resolve_model_alias("fable")`
  → `claude-fable-5`. `sonnet → claude-sonnet-5` and `haiku → claude-haiku-4-5`
  are current.
- `advisor.py:56-58` ranks `claude-fable-5-1` but has no `claude-opus-5-5`
  entry, so ranking a resolved `claude-opus-5-5` would fall to the unknown-model
  default.
- `pricing.py` has no entry for `claude-opus-5-5` or `claude-fable-5-1`, so
  `estimate_cost_usd` returns `None` for either (null `cost_usd` rows).
- `pricing.py` also has no entry for the undated `claude-haiku-4-5`, which is
  what `haiku` resolves to. It only keys `claude-haiku-4-5-20251001`, and
  `MODEL_PRICING.get()` is an exact lookup. Every SDK/batch `haiku` request is
  therefore unpriced today. This also means a guard test over all alias targets
  would fail on `haiku` before this fix.

## Steps to Reproduce

1. `python -c "from little_loops.host_runner import resolve_model_alias as r; print(r('opus'), r('fable'))"`
2. Observe `claude-opus-5 claude-fable-5`; expected `claude-opus-5-5 claude-fable-5-1`.
3. `python -c "from little_loops.pricing import estimate_cost_usd as e; print(e('claude-haiku-4-5', 1, 1))"` prints `None` (the `haiku` alias target is unpriced).

## Impact

- **Priority**: P3 — only SDK/batch request paths are affected; the CLI path resolves aliases itself.
- **Effort**: Small — table entries plus tests.
- **Risk**: Low. It changes which model `opus` / `fable` hit on SDK/batch paths, but explicitly named old IDs still pass through unchanged.

## Expected Behavior

Aliases resolve to the current model IDs; the advisor rank table and pricing
table recognize both the new and the superseded IDs (history rows keep old IDs).

## Scope

1. Update `MODEL_ALIASES` `opus`/`fable` targets.
2. Add `claude-opus-5-5` to `advisor.py` rank table (same rank as `claude-opus-5`).
3. Add `pricing.py` entries using the live pricing-page rates. Do **not** copy
   the predecessors' rates; the cache-read multipliers differ.
   - `claude-opus-5-5`: input 4.0, output 20.0, cache_read 0.20, cache_creation 5.0.
   - `claude-fable-5-1`: input 10.0, output 50.0, cache_read 0.25 (0.025x input,
     not Fable 5's 0.1x), cache_creation 12.50.
   - `claude-haiku-4-5`: point it at the **same dict object** as
     `claude-haiku-4-5-20251001`, for example a module-level `_HAIKU_4_5`
     referenced by both keys. The two IDs cannot then drift, and BUG-3564's
     rate correction fixes both.
   - Keep the `claude-opus-5` / `claude-fable-5` entries for historical rows.
4. Update `scripts/tests/test_host_runner_dispatch.py:383-387` (`opus`/`fable`
   expectations) and `test_advisor.py`.
5. Extend `test_dispatch_sends_resolved_model_to_sdk` and
   `test_batch_submission_sends_resolved_model_to_sdk`
   (`test_host_runner_dispatch.py`, which cover `sonnet` only today) to
   parametrize over `opus` and `fable`. Assert the new IDs reach
   `messages.create` and `messages.batches.create`.
6. Add `claude-opus-5` and `claude-fable-5` to
   `test_non_aliases_pass_through_unchanged`, so an explicit old ID still
   reaches the API unchanged.
7. Add a guard test asserting every `MODEL_ALIASES` target has an advisor rank
   and a `MODEL_PRICING` entry, so the three tables cannot drift again.

## Program Design

### Types

- `MODEL_ALIASES: dict[str, str]`
- `MODEL_PRICING: dict[str, dict[str, float]]`
- `MODEL_RANKS: dict[str, dict[str, int]]`

### Signatures

- `resolve_model_alias(model: str) -> str` — unchanged; reads the updated table.
- `rank_model(host: str, model: str) -> int | None` — unchanged; gains a `claude-opus-5-5` row.
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> float | None` — unchanged; gains the three new keys.
- `test_every_alias_target_is_ranked_and_priced() -> None` — new guard test.

### Call Path

`resolve_model_alias` -> `rank_model` and `estimate_cost_usd`; the guard test iterates `MODEL_ALIASES` and asserts both resolve for every target.

## Acceptance Criteria

- [ ] `resolve_model_alias("opus") == "claude-opus-5-5"` and
      `resolve_model_alias("fable") == "claude-fable-5-1"`.
- [ ] `rank_model("claude-code", "opus") == rank_model("claude-code", "claude-opus-5-5")`.
- [ ] Explicit price assertions:
      `estimate_cost_usd("claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000) == 4.0 + 20.0 + 0.20 + 5.0`,
      and `estimate_cost_usd("claude-fable-5-1", 0, 0, 1_000_000, 0) == 0.25`.
- [ ] `MODEL_PRICING["claude-haiku-4-5"] is MODEL_PRICING["claude-haiku-4-5-20251001"]`.
- [ ] Every `MODEL_ALIASES` target has a rank and a price (guard test, passing for all four aliases).
- [ ] SDK and batch dispatch send `claude-opus-5-5` / `claude-fable-5-1` for the `opus` / `fable` aliases.
- [ ] Superseded IDs remain ranked, priced and passed through unchanged when named explicitly.

## Related

- ENH-3527 — `anthropic-api` hint targets derive from `MODEL_ALIASES`; ENH-3527 is `blocked_by` this bug so its SDK hint tests assert current IDs. Raised P3 → P2 to match (avoids a P3 blocking a P2).
- BUG-3564 corrects stale rates on existing `MODEL_PRICING` rows (Sonnet 5,
  Opus 4.5-4.7, Haiku 4.5). This issue only adds keys. Either can land first.
- Pricing source: platform.claude.com/docs/en/about-claude/pricing (checked 2026-09-24).

## Status

**Open** | Created: 2026-09-23 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`

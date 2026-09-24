---
id: BUG-3579
type: BUG
title: estimate_cost_usd applies intro pricing by today's date, not the event date
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T21:22:50Z'
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3579: estimate_cost_usd applies intro pricing by today's date, not the event date

## Summary

`little_loops.pricing.estimate_cost_usd` decides whether an `INTRO_PRICING` entry applies by comparing `date.today()` against the entry's `expires` date (`scripts/little_loops/pricing.py:143`). It never sees when the usage actually happened. A replay or backfill therefore prices historical events at whatever rate is in force on the day of the replay, not the rate that applied when the tokens were spent.

This is latent today. BUG-3564 removes the only live entry (`claude-sonnet-5`), whose intro and standard rates are now identical. The `INTRO_PRICING` mechanism is deliberately kept for future launches, though, and the next time it is used every replay after expiry will reprice intro-window events at the standard rate.

## Current Behavior

- `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens=0, cache_creation_tokens=0, is_batch=False)` has no date parameter; the intro override check reads `date.today()`.
- The transcript replay path in `_backfill_usage_events` (`scripts/little_loops/session_store/writers.py:3603`) has each record's `timestamp` in hand (`ts`, read just before the call at `:3657`) but does not pass it.
- The live writer (`writers.py:1965`) takes an `observed_at` argument but prices without it. For live rows today's date is usually right, but a delayed flush at loop-run finish can straddle an expiry boundary.
- `fsm/cost_graph.py:321` recomputes cost from aggregated token rows at report time, which is also "today".

## Expected Behavior

- `estimate_cost_usd` accepts an optional `as_of: date | None = None`. `None` means today, so every existing caller keeps its current behavior.
- The intro override applies when `as_of <= expires`.
- Replay passes the record's timestamp (parsed to a date, falling back to today when absent or unparseable). The live writer passes `observed_at` when present.
- `cost_graph` passes a per-row date if the rows carry one; if they only carry aggregates, document that its costs are priced at report time.

## Motivation

`usage_events.cost_usd` is the source for reported spend and cost-ceiling enforcement, and replay is the documented way to rebuild it. A replay that silently reprices past events makes historical spend depend on the day it was recomputed. Fixing this before the next `INTRO_PRICING` entry lands is cheap; finding it afterwards means an unexplained jump in historical costs.

## Proposed Solution

1. Add `as_of: date | None = None` to `estimate_cost_usd`; replace `date.today()` with `as_of or date.today()`.
2. `_backfill_usage_events`: parse `ts` (ISO-8601) to a date and pass it.
3. Live writer: pass the date of `observed_at` when given.
4. `cost_graph`: pass a row date if available; otherwise leave it and note the limitation.

## Integration Map

### Files to Modify
- `scripts/little_loops/pricing.py` — `estimate_cost_usd`.
- `scripts/little_loops/session_store/writers.py` — the live writer call (`:1965`) and `_backfill_usage_events` (`:3657`).
- `scripts/little_loops/fsm/cost_graph.py` — `:321`, if rows carry a date.

### Tests
- `scripts/tests/test_pricing.py` — synthetic `INTRO_PRICING` fixture via monkeypatch: an event inside the intro window is priced at the intro rate when today is past expiry, an event after expiry at the standard rate when today is inside the window, and `as_of=None` matches the current behavior.
- A replay test showing `_backfill_usage_events` prices by record timestamp.

### Documentation
- `docs/reference/API.md` — `estimate_cost_usd`'s new parameter.

## Program Design

### Types
- No new types.

### Signatures
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> float | None` — the intro window is checked against `as_of`, defaulting to today (`pricing.py:113`).

### Call Path
`_backfill_usage_events` -> `estimate_cost_usd(..., as_of=<record date>)`
live `usage_events` writer -> `estimate_cost_usd(..., as_of=<observed_at date>)`

### Decision Rules
- `as_of=None` means today (backward compatible).
- An intro entry applies when `as_of <= expires` (the expiry date is inclusive, as today).
- An unparseable or missing timestamp falls back to today, never raises.

## Implementation Steps

1. Write failing tests with the synthetic intro fixture.
2. Add `as_of` to `estimate_cost_usd`.
3. Thread event dates through the replay and live call sites; decide on `cost_graph`.
4. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P4 — latent; no live `INTRO_PRICING` entries after BUG-3564.
- **Effort**: Small.
- **Risk**: Low — an optional keyword argument with a backward-compatible default.
- **Breaking Change**: No.

## Steps to Reproduce

1. Monkeypatch `INTRO_PRICING` with a synthetic entry, `{"claude-test": {"expires": "2026-08-31", "input": 1.0, ...}}`, and a matching `MODEL_PRICING` row at a different rate.
2. Patch `date.today()` to 2026-09-15.
3. Price an event that occurred on 2026-08-15: the result uses the standard rate, not the intro rate that applied on the event date.

## Root Cause

- **File**: `scripts/little_loops/pricing.py`
- **Anchor**: `estimate_cost_usd`
- **Cause**: the intro-window check is evaluated against the wall clock at call time rather than the usage event's own date, and no caller can supply one.

## Scope Boundaries

- **In scope**: the `as_of` parameter and passing event dates from existing call sites.
- **Out of scope**: repricing rows already stored in `usage_events`; rate corrections (BUG-3564); new model keys (BUG-3541).

## Acceptance Criteria

- [ ] `estimate_cost_usd` accepts `as_of`; omitting it gives today's behavior.
- [ ] With a synthetic intro entry, an event dated inside the window is priced at the intro rate even when today is after expiry, and vice versa.
- [ ] `_backfill_usage_events` prices each record by its own timestamp; a missing or malformed timestamp falls back to today without raising.
- [ ] The live writer prices by `observed_at` when it is given.

## Related

- BUG-3564 — its Follow-up section records this flaw; removing the Sonnet 5 intro entry makes it latent.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P4


## Session Log
- `/ll:confidence-check` - 2026-09-24T22:10:05 - `b03f0e56-e701-4b6d-bb94-8f4cb425b852.jsonl`
- `/ll:capture-issue` - 2026-09-24T21:22:59 - `9791f4b4-37b2-4bef-91d5-0ac00eeb812a.jsonl`

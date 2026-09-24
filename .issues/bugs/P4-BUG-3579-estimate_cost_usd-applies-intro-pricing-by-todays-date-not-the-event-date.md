---
id: BUG-3579
type: BUG
title: estimate_cost_usd applies intro pricing by today's date, not the event date
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T21:22:50Z'
relates_to:
- BUG-3564
blocked_by:
- BUG-3564
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3579: estimate_cost_usd applies intro pricing by today's date, not the event date

## Summary

`little_loops.pricing.estimate_cost_usd` decides whether an `INTRO_PRICING` entry applies by comparing `date.today()` against the entry's `expires` date (`scripts/little_loops/pricing.py:137`). It never sees when the usage actually happened. A replay or backfill therefore prices historical events at whatever rate is in force on the day of the replay, not the rate that applied when the tokens were spent.

This is latent today. BUG-3564 removed the only live entry (`claude-sonnet-5`), whose intro and standard rates are now identical. The `INTRO_PRICING` mechanism is deliberately kept for future launches, though, and the next time it is used every replay after expiry will reprice intro-window events at the standard rate.

## Current Behavior

- `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens=0, cache_creation_tokens=0, is_batch=False)` has no date parameter; the intro override check reads `date.today()`.
- The transcript replay path in `_backfill_usage_events` (`scripts/little_loops/session_store/writers.py:3607`) has each record's `timestamp` in hand (`ts`, read just before the call at `:3661`) but does not pass it.
- The live writer `record_usage_event` (`writers.py:1965`) takes a required `ts: str` and an optional `observed_at`, but prices with neither. Its only caller, the loop-run-finish flush in `fsm/executor.py:4413`, sets `ts = _iso_now()` (flush time, one value for the whole batch) and passes each usage's own `observed_at` (stamped at collection, `subprocess_utils.py:157`, `...Z` format). For live rows today's date is usually right, but a delayed flush at loop-run finish can straddle an expiry boundary.
- `fsm/cost_graph.py:321` (`CostReport.from_usage_jsonl`) recomputes cost at report time ("today"), even though every `usage.jsonl` row it reads carries its own `"timestamp"` (written at `fsm/persistence.py:1105`).

## Expected Behavior

- `estimate_cost_usd` accepts an optional `as_of: date | None = None`. `None` means today, so every existing caller keeps its current behavior.
- The intro override applies when `as_of <= expires`.
- **Event dates are UTC dates.** A timestamp is parsed as ISO-8601 (`Z` accepted), converted to UTC, and only then truncated to a date. A naive timestamp (no offset) is treated as UTC. Without a canonical zone, the same instant written as `2026-08-31T23:30:00-05:00` and `2026-09-01T04:30:00Z` would get different rates. `expires` is likewise an inclusive UTC date.
- Replay passes the record's timestamp (parsed to a UTC date, falling back to today when absent or unparseable).
- The live writer passes the date of the **first parseable** of `observed_at`, then `ts`, then today. A present but malformed `observed_at` falls through to `ts`; it does not short-circuit to today.
- `cost_graph` passes each `usage.jsonl` row's `"timestamp"` (same parse-and-fallback rule; legacy rows with `""` price at today).

## Motivation

`usage_events.cost_usd` is the source for reported spend, and replay is the documented way to rebuild it. Per-state cost-ceiling enforcement (`fsm/executor.py:4138`) reads `CostReport.from_usage_jsonl`, the `cost_graph` call site below, not `usage_events`. A replay that silently reprices past events makes historical spend depend on the day it was recomputed. Fixing this before the next `INTRO_PRICING` entry lands is cheap; finding it afterwards means an unexplained jump in historical costs.

## Proposed Solution

1. Add `as_of: date | None = None` to `estimate_cost_usd`; replace `date.today()` with `as_of or date.today()`.
2. `_backfill_usage_events`: parse `ts` (ISO-8601) to a date and pass it.
3. Live writer: pass `_event_date(observed_at) or _event_date(ts)` (first parseable wins; `None` falls back to today).
4. `cost_graph`: pass the date of each row's `"timestamp"`.
5. Put the ISO-8601 → UTC `date` parse in one small helper (e.g. `pricing._event_date(ts: str | None) -> date | None`: `datetime.fromisoformat`, naive → UTC, `astimezone(UTC).date()`; returns `None` on missing/unparseable input so `estimate_cost_usd` falls back to today) and use it at all three call sites.

**Ordering:** blocked by BUG-3564 (`blocked_by` in frontmatter). It replaces the Sonnet 5 intro tests with a synthetic, monkeypatched `INTRO_PRICING` fixture in `test_pricing.py`; this issue reuses that fixture instead of adding a second one.

## Integration Map

### Files to Modify
- `scripts/little_loops/pricing.py` — `estimate_cost_usd`.
- `scripts/little_loops/session_store/writers.py` — the live writer call in `record_usage_event` (`:1965`) and `_backfill_usage_events` (call at `:3661`).
- `scripts/little_loops/fsm/cost_graph.py` — `CostReport.from_usage_jsonl` (`:321`), per-row `"timestamp"`.

### Tests
- `scripts/tests/test_pricing.py` — reuse BUG-3564's synthetic `INTRO_PRICING` fixture (monkeypatch): an event inside the intro window is priced at the intro rate when today is past expiry, an event after expiry at the standard rate when today is inside the window, and `as_of=None` matches the current behavior.
- `_event_date` unit tests: offset boundary (`2026-08-31T23:30:00-05:00` and `2026-09-01T04:30:00Z` both → 2026-09-01), `Z` suffix, naive timestamp (treated as UTC), and malformed / empty / `None` input (→ `None`, never raises).
- A replay test showing `_backfill_usage_events` prices by record timestamp.
- A live-writer integration test for `record_usage_event` precedence: valid `observed_at` wins over `ts`; malformed `observed_at` falls through to `ts`; both malformed price at today.
- `scripts/tests/test_fsm_cost_graph.py` — a `usage.jsonl` row dated inside the intro window is priced at the intro rate after expiry.

### Documentation
- `docs/reference/API.md` — `estimate_cost_usd`'s new parameter (`### estimate_cost_usd`, `:12392`), plus the two `little_loops.pricing` summaries (`:84`, `:12360`) that say it "checks `date.today()`".

## Program Design

### Types
- No new types.

### Signatures
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> float | None` — the intro window is checked against `as_of`, defaulting to today (`pricing.py:107`).

### Call Path
`_backfill_usage_events` -> `estimate_cost_usd(..., as_of=<record date>)`
`record_usage_event` -> `estimate_cost_usd(..., as_of=<observed_at or ts date>)`
`CostReport.from_usage_jsonl` -> `estimate_cost_usd(..., as_of=<row timestamp date>)`

### Decision Rules
- `as_of=None` means today (backward compatible).
- An intro entry applies when `as_of <= expires` (the expiry date is inclusive, as today).
- An unparseable or missing timestamp falls back to today, never raises.
- Event dates are UTC: convert to UTC before truncating; naive timestamps are UTC.
- Live writer precedence: first parseable of `observed_at`, `ts`, today.

## Implementation Steps

1. Write failing tests with the synthetic intro fixture.
2. Add `as_of` to `estimate_cost_usd`.
3. Thread event dates through the replay, live and `cost_graph` call sites.
4. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P4 — latent; no live `INTRO_PRICING` entries after BUG-3564.
- **Effort**: Small.
- **Risk**: Low — a new keyword argument with a backward-compatible default.
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
- [ ] The live writer prices by the first parseable of `observed_at`, `ts`, then today; a malformed `observed_at` falls through to `ts` (integration test through `record_usage_event`).
- [ ] The same instant in different offsets (`2026-08-31T23:30:00-05:00`, `2026-09-01T04:30:00Z`) gets the same rate; a naive timestamp is priced as UTC.
- [ ] `cost_graph` prices each `usage.jsonl` row by its own `"timestamp"`; a row with an empty or malformed timestamp falls back to today.
- [ ] `docs/reference/API.md` documents `as_of`, and its `little_loops.pricing` summaries no longer say pricing always checks `date.today()`.

## Related

- BUG-3564 (blocker) — its Follow-up section records this flaw; removing the Sonnet 5 intro entry makes it latent. Land it first: this issue reuses its synthetic `INTRO_PRICING` test fixture.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Checked 2026-09-24 against the working tree. That tree holds BUG-3564's uncommitted `pricing.py` / `test_pricing.py` / `API.md` edits.

- **Line drift (fixed):** the `date.today()` check is at `pricing.py:137` and `def estimate_cost_usd` at `:107` in the working tree. The old `:143` / `:113` anchors match HEAD only, because BUG-3564 shortened the module docstring and emptied `INTRO_PRICING`.
- **Motivation (fixed):** cost-ceiling enforcement does not read `usage_events.cost_usd`. `_check_cost_ceiling` (`fsm/executor.py:4138`) uses `CostReport.from_usage_jsonl`, which is already in scope.
- **Live writer (clarified):** `record_usage_event` has one caller, `fsm/executor.py:4413`. That caller passes `ts=_iso_now()`, the flush time, so `ts` is a flush-time fallback and not an event date.
- **Docs (fixed):** added the `API.md` summaries at `:84` and `:12360`, which describe `date.today()`, and added an Acceptance Criterion for the Documentation point, which had none.
- **Confirmed:** there are exactly three production callers: `writers.py:1965`, `writers.py:3661` (`ts` read at `:3659`) and `cost_graph.py:321`. `persistence.py:1105` writes `"timestamp"` from `event.get("ts", "")`. The `synthetic_intro_pricing` fixture exists (`test_pricing.py:33`). BUG-3564 is `done`, and `INTRO_PRICING` is `{}` in the working tree but still holds the Sonnet 5 entry at HEAD.
- **Implementer caution:** the existing intro tests patch `little_loops.pricing.date` with a mock that defines only `today` and `fromisoformat`. `as_of or date.today()` works with that mock. Build `_event_date` on `datetime` rather than `date`, or keep it out of the code path those tests patch.

Remaining: BUG-3564 has no `blocks: [BUG-3579]` backlink (it lists BUG-3579 under `relates_to` only). It is advisory, since the blocker is done.

## Status

**Open** | Created: 2026-09-24 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-09-24T23:39:13 - `ce8bec5b-7632-4ff9-a3da-7cdd35c70217.jsonl`
- `/ll:verify-issues` - 2026-09-24T22:56:17 - `4279401a-9acc-474c-b872-fd398cd78a8e.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:35:17 - `193eb57f-e9f6-4072-bd61-43000a1d97b1.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:10:05 - `b03f0e56-e701-4b6d-bb94-8f4cb425b852.jsonl`
- `/ll:capture-issue` - 2026-09-24T21:22:59 - `9791f4b4-37b2-4bef-91d5-0ac00eeb812a.jsonl`

---
id: BUG-3531
type: BUG
title: Codex live usage stores cache-inclusive input_tokens in the uncached-input
  column
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:32Z'
labels:
- observability
- multi-host
confidence_score: 95
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
---

# BUG-3531: Codex live usage stores cache-inclusive input_tokens in the uncached-input column

## Summary

Codex's `turn.completed` usage reports `input_tokens` **inclusive** of cached and cache-write tokens, but `usage_from_event` (`scripts/little_loops/subprocess_utils.py`) stores it unchanged in the `input_tokens` field, whose meaning everywhere else (Claude's disjoint three-way split, `estimate_cost_usd`, `usage_events`) is **uncached** input. Cached Codex tokens are therefore counted twice in any input + cache total, and mixed-host aggregates add two different quantities in one column.

## Steps to Reproduce

1. `python -c "from little_loops.subprocess_utils import usage_from_event as u; print(u({'type':'turn.completed','usage':{'input_tokens':1000,'cached_input_tokens':600,'output_tokens':10}}, default_model='x'))"`
2. Observe `input_tokens=1000, cache_read_tokens=600`; any input + cache total counts the 600 cached tokens twice (expected `input_tokens=400`).

## Current Behavior

- `usage_from_event` for `turn.completed`: `input_tokens=usage["input_tokens"]`, `cache_read_tokens=usage["cached_input_tokens"]`, `cache_creation_tokens=usage["cache_write_input_tokens"]` — no subtraction.
- `ctx_stats._codex_cache_usage` already treats Codex input as inclusive and derives `uncached = max(0, input - cached - cache_write)`, so the two Codex paths disagree.
- `ctx_stats._aggregate_usage_events` sums `input_tokens` and the cache columns across all rows regardless of host.
- USD cost is not currently affected: `MODEL_PRICING` has no OpenAI models, so Codex rows get `cost_usd = NULL`. It becomes a cost bug the moment Codex pricing is added.

## Expected Behavior

Live Codex usage is normalized to the canonical disjoint contract before it leaves `usage_from_event`: `input_tokens` = uncached input, with cache-read/cache-write as separate components. When the components are inconsistent (cache components exceed inclusive input), the row remains identifiable as inconsistent rather than silently clamped into a plausible measured split.

## Integration Map

- `scripts/little_loops/subprocess_utils.py` `usage_from_event`, `scripts/little_loops/cli/ctx_stats.py` `_codex_cache_usage`.
- Tests: `test_subprocess_utils.py`, `test_cli_ctx_stats.py`, `test_fsm_runners.py`; fixture `scripts/tests/fixtures/codex/`.

## Impact

- **Priority**: P2 — overstated token totals for Codex runs; latent cost bug.
- **Effort**: Small.
- **Risk**: Low to medium — changes stored values for new Codex rows.
- **Related**: ENH-3532 (historical rollout ingestion) must use the same normalizer.

## Acceptance Criteria

- [ ] Fixture-backed test: a Codex `turn.completed` with `input_tokens=1000, cached_input_tokens=600` yields `input_tokens=400, cache_read_tokens=600`.
- [ ] Missing `cache_write_input_tokens` stays a real zero (ENH-3464 Decision 3); inconsistent components have a defined, tested outcome.
- [ ] `_codex_cache_usage` and `usage_from_event` share one normalization helper so the semantics cannot drift again.
- [ ] Output/reasoning inclusion is checked against a fixture and documented (no double-add of reasoning tokens).
- [ ] Already-written Codex rows: decide and document (leave as-is and exclude/flag, or a one-shot correction). Do not silently mix corrected and uncorrected rows in totals.

## Program Design

### Types

- `TokenUsage` unchanged; its `input_tokens` field is documented as uncached input for every host.

### Signatures

- `usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None` — signature unchanged; the `turn.completed` branch subtracts cache components via the shared helper.
- `normalize_codex_input(usage: dict[str, Any]) -> tuple[int, int, int]` — new shared helper returning `(uncached_input, cache_read, cache_write)`; also used by `_codex_cache_usage`.

### Call Path

- `usage_from_event` → `record_usage_event` (live FSM path)
- `_codex_cache_usage` → `normalize_codex_input` (ctx-stats cache rate)

## Verification Notes

Verdict: **VALID** (2026-09-23). `usage_from_event` `turn.completed` branch stores `input_tokens` unchanged (`subprocess_utils.py:105-110`); `_codex_cache_usage` documents inclusive input and subtracts. Inclusive-input claim read directly from `scripts/tests/fixtures/codex/rollout-exec.jsonl` (`input_tokens` 13001 ⊇ `cache_write_input_tokens` 12998; `total_tokens` 13006 = input + output, so reasoning is not double-added). `ll-verify-evidence` clean.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Two Acceptance Criteria defer decisions to implementation time: outcome for inconsistent components (cache > input) and policy for already-written Codex rows. Resolve both before coding.
- `usage_from_event` has 5 call sites (`subprocess_utils.py` 143/169/706/730) feeding live usage rows; stored values change for new Codex rows.

### Outcome Risk Factors
- Minor open design decisions (inconsistent-component representation; existing-row handling) — resolvable during implementation but affect stored data.
- Shared normalizer touches two modules (`subprocess_utils`, `ctx_stats`) plus ENH-3532 coupling.

## Session Log
- `/ll:confidence-check` - 2026-09-24T00:45:01 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`

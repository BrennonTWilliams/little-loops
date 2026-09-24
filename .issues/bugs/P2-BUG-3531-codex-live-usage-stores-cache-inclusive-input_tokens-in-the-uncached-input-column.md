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
blocked_by:
- ENH-3538
blocks:
- ENH-3528
- ENH-3532
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
- `_codex_cache_usage` sums `input_tokens`, `cached_input_tokens` and `cache_write_input_tokens` across all turns first and only then clamps with `max(0, …)` (`ctx_stats.py:388`). One inconsistent turn is therefore hidden by another turn's positive uncached balance, and `test_codex_clamps_negative_uncached_to_zero` (`test_cli_ctx_stats.py:1043`) enshrines the silent clamp.
- `ctx_stats._aggregate_usage_events` sums `input_tokens` and the cache columns across all rows regardless of host.
- `FSMExecutor` sums `TokenUsage` fields across a state's usage events into the `action_complete` payload (`executor.py:2697`). Any status carried outside `TokenUsage` is lost there.
- Existing live Codex rows are not identifiable: `turn.completed` has no `model` field (rows store `"unknown"`), and `record_usage_event` stores no host.
- USD cost is not currently affected: `MODEL_PRICING` has no OpenAI models, so Codex rows get `cost_usd = NULL`. It becomes a cost bug the moment Codex pricing is added.

## Expected Behavior

Live Codex usage is normalized to the canonical disjoint contract before it leaves `usage_from_event`: `input_tokens` = uncached input, with cache-read/cache-write as separate components. When the components are inconsistent (cache components exceed inclusive input), the row remains identifiable as inconsistent rather than silently clamped into a plausible measured split.

## Integration Map

- `scripts/little_loops/subprocess_utils.py` `usage_from_event`, `TokenUsage`; `scripts/little_loops/cli/ctx_stats.py` `_codex_cache_usage`.
- `scripts/little_loops/fsm/executor.py` — `action_complete` usage aggregation; relies on ENH-3538's completeness-aware sums (no new flag).
- `scripts/little_loops/session_store/writers.py` `record_usage_event` — persist inconsistent observations as `provenance='unknown'` using ENH-3538's columns.
- Tests: `test_subprocess_utils.py`, `test_cli_ctx_stats.py` (replace `test_codex_clamps_negative_uncached_to_zero`), `test_fsm_runners.py`, `test_fsm_executor.py`; fixtures `scripts/tests/fixtures/codex/` (`rollout-interactive.jsonl` for reasoning; a new captured `turn.completed` fixture for the live path).

## Design Decisions

_Resolved 2026-09-23 (review of BUG-3529/3530/3531)._

1. **Representation.** `normalize_codex_input(usage) -> CodexInputSplit`, a frozen dataclass `(uncached_input: int | None, cache_read: int, cache_write: int, consistent: bool)`. A consistent observation gives `uncached_input = input - cache_read - cache_write`. When `cache_read + cache_write > input`, the result is `consistent=False`, with `uncached_input=None` (unavailable, per ENH-3538's null-not-zero rule) and the cache components kept exactly as reported. `consistent` is local to the split; it is not added to `TokenUsage`.
2. **Survives aggregation.** No new `TokenUsage` flag. `usage_from_event` maps the split onto ENH-3538's fields: consistent → `input_tokens=uncached_input`, `provenance='measured'`, `host='codex'`; inconsistent → `input_tokens=None`, `provenance='unknown'`, `host='codex'`. ENH-3538's completeness-aware executor sums carry the missing input count into the `action_complete` payload, and each `TokenUsage` is still collected individually for per-row persistence. (Revised 2026-09-23: replaces the earlier `input_consistent: bool` field, which duplicated provenance and would have been dropped by payload summing.)
3. **Survives persistence.** Rows are written through ENH-3538's writer with the provenance above and `channel='live'`. Because this relies on ENH-3538's migration and nullable components, BUG-3531 is blocked by ENH-3538 (not by all of ENH-3528). Landing the normalization first would mix corrected and uncorrected rows with nothing to tell them apart.
4. **Per-observation, before summing.** `_codex_cache_usage` normalizes each turn and then sums the consistent ones. Inconsistent turns are excluded from the hit-rate numerator and denominator, and the result reports their count (`inconsistent_events`). It never clamps an aggregate.
5. **Legacy rows.** No correction. Pre-fix live Codex rows can't be told apart from other hosts' rows (model `"unknown"`, no host), so they are not selected by model name and cached tokens are not subtracted wholesale. They keep ENH-3538's legacy `provenance='unknown'`, and ENH-3528's aggregation reports that composition rather than presenting a clean total.

## Impact

- **Priority**: P2 — overstated token totals for Codex runs; latent cost bug.
- **Effort**: Small.
- **Risk**: Low to medium — changes stored values for new Codex rows.
- **Related**: ENH-3532 (historical rollout ingestion) must use the same normalizer.

## Acceptance Criteria

- [ ] Fixture-backed test: a Codex `turn.completed` with `input_tokens=1000, cached_input_tokens=600` yields `input_tokens=400, cache_read_tokens=600, provenance='measured', host='codex'`.
- [ ] Missing `cache_write_input_tokens` stays a real zero (ENH-3464 Decision 3).
- [ ] Inconsistent components (`cache_read + cache_write > input`) yield `input_tokens=None`, keep the reported cache components, and persist as `provenance='unknown'`. Covered at the `usage_from_event`, executor-payload (missing-input count) and `usage_events` row levels.
- [ ] `_codex_cache_usage` and `usage_from_event` share `normalize_codex_input`. `_codex_cache_usage` normalizes per turn before summing: a test with one inconsistent turn and one consistent turn shows the inconsistent turn excluded and counted, not absorbed.
- [ ] `test_codex_clamps_negative_uncached_to_zero` is replaced by a test asserting the inconsistent-turn outcome. No test requires a silent clamp.
- [ ] Output/reasoning inclusion is verified against `rollout-interactive.jsonl`, whose turns have nonzero `reasoning_output_tokens` (9, 158) and `total_tokens == input_tokens + output_tokens` (so reasoning is included in output and must not be added again). `rollout-exec.jsonl` can't establish this because its reasoning count is 0.
- [ ] A captured `codex exec --json` `turn.completed` event is added under `scripts/tests/fixtures/codex/` and drives the live-path test (the rollout fixtures come from a different event stream).
- [ ] Legacy rows follow Design Decision 5: no correction, and a test shows a mixed legacy + new aggregate is reported with `unknown` composition rather than a single measured total.

## Program Design

### Types

- `TokenUsage` — no new fields (uses ENH-3538's nullable components and `provenance`/`host`); its `input_tokens` field is documented as uncached input for every host.
- `CodexInputSplit` — new frozen dataclass `(uncached_input: int | None, cache_read: int, cache_write: int, consistent: bool)`.

### Signatures

- `usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None` — signature unchanged; the `turn.completed` branch builds its fields from `normalize_codex_input` and sets `provenance`/`host`.
- `normalize_codex_input(usage: dict[str, Any]) -> CodexInputSplit` — new shared helper for one observation; also used per turn by `_codex_cache_usage`.

### Call Path

- `usage_from_event` → `FSMExecutor` (payload aggregation, per-event collection) → `record_usage_event` (live FSM path)
- `_codex_cache_usage` → `normalize_codex_input` (ctx-stats cache rate)

## Verification Notes

Verdict: **VALID** (2026-09-23). `usage_from_event` `turn.completed` branch stores `input_tokens` unchanged (`subprocess_utils.py:105-110`); `_codex_cache_usage` documents inclusive input and subtracts. Inclusive-input claim read directly from `scripts/tests/fixtures/codex/rollout-exec.jsonl` (`input_tokens` 13001 ⊇ `cache_write_input_tokens` 12998). `ll-verify-evidence` clean.

**Correction (2026-09-23)**: the exec fixture's `reasoning_output_tokens` is 0, so `total_tokens = input + output` there cannot show whether reasoning is included in output. `rollout-interactive.jsonl` can: for example `output_tokens=237, reasoning_output_tokens=158, total_tokens=26316 = 26079 + 237`, so reasoning is a subset of output.

### Pre-implementation review 2026-09-23

Retargeted `blocked_by` from BUG-3530 (done) + ENH-3528 to ENH-3538 (extracted foundation). Replaced the `input_consistent` flag with `input_tokens=None` + `provenance='unknown'` so inconsistent input is unavailable rather than a fabricated 0 and survives payload summing.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- ~~Two Acceptance Criteria defer decisions to implementation time~~ — resolved 2026-09-23; see Design Decisions.
- `usage_from_event` has 4 call sites (`subprocess_utils.py` 143/169/706/730) feeding live usage rows; stored values change for new Codex rows.

### Outcome Risk Factors
- Minor open design decisions (inconsistent-component representation; existing-row handling) — resolvable during implementation but affect stored data.
- Shared normalizer touches two modules (`subprocess_utils`, `ctx_stats`) plus ENH-3532 coupling.

## Session Log
- `/ll:confidence-check` - 2026-09-24T00:45:01 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`

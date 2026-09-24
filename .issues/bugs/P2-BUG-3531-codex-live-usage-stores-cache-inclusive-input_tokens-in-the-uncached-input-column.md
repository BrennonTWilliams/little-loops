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
---

# BUG-3531: Codex live usage stores cache-inclusive input_tokens in the uncached-input column

## Summary

Codex's `turn.completed` usage reports `input_tokens` **inclusive** of cached and cache-write tokens, but `usage_from_event` (`scripts/little_loops/subprocess_utils.py`) stores it unchanged in the `input_tokens` field, whose meaning everywhere else (Claude's disjoint three-way split, `estimate_cost_usd`, `usage_events`) is **uncached** input. Cached Codex tokens are therefore counted twice in any input + cache total, and mixed-host aggregates add two different quantities in one column.

## Steps to Reproduce

1. `python -c "from little_loops.subprocess_utils import usage_from_event as u; print(u({'type':'turn.completed','usage':{'input_tokens':1000,'cached_input_tokens':600,'output_tokens':10}}, default_model='x'))"`
2. Observe `input_tokens=1000, cache_read_tokens=600`; any input + cache total counts the 600 cached tokens twice. Expected uncached input is `400` when cache-write is explicitly zero or verified to be zero on omission; otherwise the disjoint uncached component is unavailable (`None`).

## Current Behavior

- `usage_from_event` for `turn.completed`: `input_tokens=usage["input_tokens"]`, `cache_read_tokens=usage["cached_input_tokens"]`, `cache_creation_tokens=usage["cache_write_input_tokens"]` — no subtraction.
- `ctx_stats._codex_cache_usage` already treats Codex input as inclusive and derives `uncached = max(0, input - cached - cache_write)`, so the two Codex paths disagree.
- `_codex_cache_usage` sums `input_tokens`, `cached_input_tokens` and `cache_write_input_tokens` across all turns first and only then clamps with `max(0, …)` (`ctx_stats.py:388`). One inconsistent turn is therefore hidden by another turn's positive uncached balance, and `test_codex_clamps_negative_uncached_to_zero` (`test_cli_ctx_stats.py:1043`) enshrines the silent clamp.
- `ctx_stats._aggregate_usage_events` sums `input_tokens` and the cache columns across all rows regardless of host.
- `FSMExecutor` sums `TokenUsage` fields across a state's usage events into the `action_complete` payload (`executor.py:2697`). Any status carried outside `TokenUsage` is lost there.
- Existing live Codex rows are not identifiable: `turn.completed` has no `model` field (rows store `"unknown"`), and `record_usage_event` stores no host.
- USD cost is not currently affected: `MODEL_PRICING` has no OpenAI models, so Codex rows get `cost_usd = NULL`. It becomes a cost bug the moment Codex pricing is added.

## Expected Behavior

Live Codex usage is normalized to the canonical disjoint contract before it leaves `usage_from_event`: `input_tokens` = uncached input, with cache-read/cache-write as separate components. Inconsistent, missing, or malformed components must not be silently clamped or coerced into a plausible measured split. Cache-rate text and JSON output expose excluded observations, including when no valid observation remains.

## Integration Map

- `scripts/little_loops/subprocess_utils.py` `usage_from_event`, `TokenUsage`; `scripts/little_loops/cli/ctx_stats.py` `_codex_cache_usage`, `_render`, `_print_json` — propagate excluded-event counts and unavailable rates into public text/JSON output, not only the helper's dict.
- `scripts/little_loops/fsm/executor.py` — `action_complete` usage aggregation; relies on ENH-3538's completeness-aware sums (no new flag).
- `scripts/little_loops/session_store/writers.py` `record_usage_event` — persist inconsistent observations as `provenance='unknown'` using ENH-3538's columns.
- `scripts/little_loops/runner_spec.py` (`_run_skill` / `_run_prompt`, lines ~276, ~459) — `RunnerResult` efficiency fields (ENH-3464) come from `usage_from_stream_lines` → `usage_from_event`, so Codex `input_tokens` there also becomes uncached input (or `None` when inconsistent). Codex efficiency figures captured before this fix aren't comparable; note this in the CHANGELOG entry.
- Tests: `test_subprocess_utils.py`, `test_cli_ctx_stats.py` (replace `test_codex_clamps_negative_uncached_to_zero`; test public JSON/text output), `test_fsm_runners.py`, `test_fsm_executor.py`, `runner_spec` usage tests; fixtures `scripts/tests/fixtures/codex/` (`rollout-interactive.jsonl` for reasoning; matched stdout/rollout captures for the live path). Add null/negative/boolean/nonnumeric component cases and mixed, all-excluded, valid-zero, and no-observation cache-rate cases.
- Documentation: fixture README records CLI version, capture procedure, observation scope, and cache-write evidence; CHANGELOG documents new Codex input semantics and public cache-rate exclusion fields. Audit schemas pinning the affected JSON fields.

## Design Decisions

_Revised 2026-09-23. Representation and legacy handling are decided; the live producer contract must satisfy Decision 6 before measured provenance is enabled._

1. **Representation.** `normalize_codex_input(usage) -> CodexInputSplit`, a frozen dataclass `(uncached_input: int | None, cache_read: int | None, cache_write: int | None, consistent: bool)`. A consistent observation gives `uncached_input = input - cache_read - cache_write` only when all three inputs are known nonnegative integers. When valid cache components exceed inclusive input, the result is `consistent=False`, with `uncached_input=None` (unavailable, per ENH-3538's null-not-zero rule) and the valid cache components kept exactly as reported. `consistent` is local to the split; it is not added to `TokenUsage`.
   - **Missing keys.** Missing `input_tokens` or `cached_input_tokens` makes the split unavailable/inconsistent (`cache_read=None` for the latter). Omitted `cache_write_input_tokens` becomes `0` only when Decision 6 establishes that meaning for the acquisition path; otherwise `cache_write=None`, `uncached_input=None`, `consistent=False`. An omission-only fixture and ENH-3464 Decision 3 are not sufficient proof. The shared helper defaults conservatively; any path-specific omission rule must be explicit at its call sites rather than inferred from an ambiguous usage dict.
   - **Malformed components.** Explicit `null`, negative integers, booleans, floats, strings (including numeric strings), and other noninteger values are unavailable (`None`), never coerced via `int(...)` or `or 0`. Validate input, cache-read, cache-write, and output independently. Preserve other valid reported components; an invalid/missing input-split component makes `uncached_input=None` and `consistent=False`. Invalid/missing output becomes `output_tokens=None` and prevents measured row provenance, but does not invalidate an otherwise valid input split used solely for cache-rate calculation. Explicit cache-write `null` never uses the omitted-key zero rule.
2. **Survives aggregation.** No new `TokenUsage` flag. `usage_from_event` maps a consistent input split onto ENH-3538's fields and sets `host='codex'`; `provenance='measured'` requires the producer-contract gate in Decision 6, a consistent split, and a valid known output count. Otherwise provenance is `unknown`; an inconsistent input split specifically gives `input_tokens=None`, retaining other valid components. ENH-3538's completeness-aware executor sums carry missing-component counts into the `action_complete` payload, and each `TokenUsage` is still collected individually for per-row persistence. A valid input split can remain numeric when only output is missing, without certifying the row as measured.
3. **Survives persistence.** Rows are written through ENH-3538's writer with the provenance above and `channel='live'`. Because this relies on ENH-3538's migration and nullable components, BUG-3531 is blocked by ENH-3538 (not by all of ENH-3528). Landing the normalization first would mix corrected and uncorrected rows with nothing to tell them apart.
4. **Per-observation, before summing.** `_codex_cache_usage` normalizes each usage observation and then sums only consistent input splits. Missing/malformed input splits and cache components exceeding inclusive input are excluded from the hit-rate numerator and denominator, and counted as `inconsistent_events`; valid splits count as `consistent_events`. `info: null` rate-limit-only records are not usage observations and affect neither count. A present but incomplete usage observation counts as excluded. It never clamps an aggregate.
   - **Public result.** The helper returns both counts plus its existing fields. `_print_json` exposes `cache_rate_inconsistent_events` and `cache_rate_consistent_events` beside the existing `cache_hit_rate_pct`/token/host fields. Text reports exclusions whenever nonzero and identifies mixed results as based only on accepted observations; the extra fields must not disappear at the renderer boundary.
   - **All excluded.** Return a result with `hit_rate_pct=None`, token totals `None`, `consistent_events=0`, and the retained exclusion count. JSON emits nulls and the counts; text reports an unavailable rate and the exclusions, never `None%`, `0%`, or zero token totals.
   - **Valid zero usage.** A consistent all-zero observation remains accepted: token totals are zero and `hit_rate_pct=None` because the denominator is zero. Text identifies zero usage; both counts distinguish this case from all-excluded. Return `None` only when no usage observation exists; JSON uses zero observation counts and null rate/token fields in that case.
5. **Legacy rows.** No correction. Pre-fix live Codex rows can't be told apart from other hosts' rows (model `"unknown"`, no host), so they are not selected by model name and cached tokens are not subtracted wholesale. They keep ENH-3538's legacy `provenance='unknown'`, and ENH-3528's aggregation reports that composition rather than presenting a clean total.
6. **Producer-contract prerequisite.** Before enabling measured provenance or fixing the omission rule, capture matched `codex exec --json` stdout and rollout observations for the same run, including multiple turns/resume. Record CLI version and establish inclusive-input semantics, whether terminal usage is per-turn or thread-cumulative, and what an omitted cache-write field means. Align observation intervals before comparing; a capture that only lacks the field proves omission, not zero. Alternatively, cite a version-matched authoritative producer contract that establishes the omitted-field semantics. The committed rollout fixtures contain nonzero cache-write counts, so do not infer token counts from a claim about billing. If omission does not establish zero, retain nullable cache-write and uncached values for affected live events, with unknown provenance; revise any expected measured examples accordingly. If live counts are cumulative, specify and test baseline/difference handling before normalization, including resume/reset behavior, and update the call path/signature as necessary. Scope and omission semantics must be resolved from evidence before this issue is marked implementation-ready.

## Implementation Steps

1. Complete Decision 6's producer-contract investigation and document the evidence in the fixture README and this issue. Establish path-specific omission behavior and any cumulative-count handling before enabling measured rows.
2. Add shared normalization and per-component validation with focused malformed/partial/zero tests; wire the live parser and per-observation rollout cache-rate reader.
3. Carry accepted/excluded counts and unavailable rates through both public renderers; test mixed, all-excluded, valid-zero, and no-observation outputs.
4. Verify executor missing counts, per-row persistence, legacy-row preservation, and runner efficiency pass-through against ENH-3538. Update affected output contracts and CHANGELOG; run focused tests and required project checks.

## Impact

- **Priority**: P2 — overstated token totals for Codex runs; latent cost bug.
- **Effort**: Small.
- **Risk**: Low to medium — changes stored values for new Codex rows.
- **Related**: ENH-3532 (historical rollout ingestion) must use the same normalizer.

## Acceptance Criteria

- [ ] After the producer-contract gate passes, a complete Codex `turn.completed` with `input_tokens=1000, cached_input_tokens=600, cache_write_input_tokens=0, output_tokens=10` yields `input_tokens=400, cache_read_tokens=600, provenance='measured', host='codex'`. The captured live shape drives an additional fixture-backed case; omission is not substituted for an explicit zero without evidence.
- [ ] Matched stdout/rollout captures or a version-matched authoritative producer contract establish the omitted-cache-write semantics for each relevant acquisition path. The fixture README records the evidence and CLI version. An omission-only fixture does not pass this criterion; unestablished omission remains `None` with unknown provenance.
- [ ] Inconsistent components (`cache_read + cache_write > input`) yield `input_tokens=None`, keep the reported cache components, and persist as `provenance='unknown'`. Covered at the `usage_from_event`, executor-payload (missing-input count) and `usage_events` row levels.
- [ ] `_codex_cache_usage` and `usage_from_event` share `normalize_codex_input`. `_codex_cache_usage` normalizes per turn before summing: a test with one inconsistent turn and one consistent turn shows the inconsistent turn excluded and counted, not absorbed.
- [ ] Public text and JSON tests verify accepted/excluded counts for mixed observations and all-excluded observations. All-excluded results retain the count with null rate/token totals and an unavailable text message. Consistent zero usage preserves zero token totals and a null rate with an accepted count; no-observation results have zero counts and null totals. Rate-limit-only events do not inflate either count.
- [ ] `test_codex_clamps_negative_uncached_to_zero` is replaced by a test asserting the inconsistent-turn outcome. No test requires a silent clamp.
- [ ] Output/reasoning inclusion is verified against `rollout-interactive.jsonl`, whose turns have nonzero `reasoning_output_tokens` (9, 158) and `total_tokens == input_tokens + output_tokens` (so reasoning is included in output and must not be added again). `rollout-exec.jsonl` can't establish this because its reasoning count is 0.
- [ ] A captured `codex exec --json` `turn.completed` event is added under `scripts/tests/fixtures/codex/` and drives the live-path test (the rollout fixtures come from a different event stream).
- [ ] Missing `input_tokens` or `cached_input_tokens` yields `uncached_input=None`, `consistent=False` (and `cache_read=None` for the latter); cache-write omission follows the verified path contract or remains unknown.
- [ ] Parameterized boundary tests cover explicit `null`, negative counts, booleans, floats, numeric strings, and nonnumeric values in input/cache/output components. No case raises or fabricates zero; valid sibling components survive, missing counts reach executor/persistence, and malformed observations never receive measured provenance. A valid input split with missing/invalid output remains usable for cache rate but has `output_tokens=None` and unknown row provenance.
- [ ] Before the live-path test is written, the captured fixture set includes a multi-turn run (`codex exec resume` or a second turn) and records whether `turn.completed.usage` is per-turn or thread-cumulative (the `last_token_usage` vs `total_token_usage` trap `_codex_cache_usage` already guards against). If it's cumulative, the live path must take the per-turn difference before normalizing, and this issue is updated to say so.
- [ ] Legacy rows follow Design Decision 5: no correction. A test shows existing pre-fix `usage_events` rows are unchanged by the migration and the new code, and still read as `provenance='unknown'`. (The mixed legacy + new **aggregate** composition report belongs to ENH-3528.)

## Program Design

### Types

- `TokenUsage` — no new fields (uses ENH-3538's nullable components and `provenance`/`host`); its `input_tokens` field is documented as uncached input for every host.
- `CodexInputSplit` — new frozen dataclass `(uncached_input: int | None, cache_read: int | None, cache_write: int | None, consistent: bool)`; nullable cache-write supports explicit null/malformed values and omissions without a verified zero contract.
- Cache-rate result — existing token/rate fields become nullable for unavailable data; adds integer `consistent_events` and `inconsistent_events`. Public JSON uses the `cache_rate_` prefix for both counts.

### Signatures

- `usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None` — signature unchanged; the `turn.completed` branch builds its fields from `normalize_codex_input` and sets `provenance`/`host`.
- `normalize_codex_input(usage: dict[str, Any], *, omitted_cache_write_is_zero: bool = False) -> CodexInputSplit` — new shared helper for one observation; also used per observation by `_codex_cache_usage`. Only a call site with Decision 6's verified path contract may opt into zero-on-omission. The option never converts explicit null/malformed values to zero.

### Call Path

- `usage_from_event` → `FSMExecutor` (payload aggregation, per-event collection) → `record_usage_event` (live FSM path)
- `_codex_cache_usage` → `normalize_codex_input` → accepted/excluded cache-rate result → `_render` / `_print_json`

## Verification Notes

Historical verdict: **VALID** (2026-09-23, before the reviews below). `usage_from_event` `turn.completed` branch stores `input_tokens` unchanged (`subprocess_utils.py:105-110`); `_codex_cache_usage` documents inclusive input and subtracts. Inclusive-input evidence came from `scripts/tests/fixtures/codex/rollout-exec.jsonl` (`input_tokens` 13001, `cache_write_input_tokens` 12998). That rollout evidence does not by itself establish the omitted-field or cumulative-count contract of the separate live stream. `ll-verify-evidence` was clean.

**Correction (2026-09-23)**: the exec fixture's `reasoning_output_tokens` is 0, so `total_tokens = input + output` there cannot show whether reasoning is included in output. `rollout-interactive.jsonl` can: for example `output_tokens=237, reasoning_output_tokens=158, total_tokens=26316 = 26079 + 237`, so reasoning is a subset of output.

### Pre-implementation review 2026-09-23

Retargeted `blocked_by` from BUG-3530 (done) + ENH-3528 to ENH-3538 (extracted foundation). Replaced the `input_consistent` flag with `input_tokens=None` + `provenance='unknown'` so inconsistent input is unavailable rather than a fabricated 0 and survives payload summing.

### Pre-implementation review 2026-09-23 (2)

`cache_read` became `int | None` with explicit missing-key rules. This review still assumed omitted cache-write meant zero; review (3) below supersedes that assumption. Added `runner_spec` `RunnerResult` as an affected consumer, a cumulative-vs-per-turn capture check, and a row-level legacy criterion; the aggregate composition report belongs to ENH-3528.

### Pre-implementation review 2026-09-23 (3)

Applied public text/JSON exclusion reporting and all-excluded/valid-zero behavior; added strict component validation and nullable cache-write; strengthened the producer-contract prerequisite to require evidence for zero-on-omission as well as usage scope. Removed stale frontmatter confidence scores rather than presenting the earlier 95/100 as current readiness. The double-counting bug still reproduces; the producer-contract investigation remains outstanding. Re-run `/ll:confidence-check` after that evidence resolves the contract.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-23_

**Historical only — superseded by pre-implementation review (3).** These scores are not a current proceed recommendation; producer-contract evidence is still required and no replacement score has been computed.

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- ~~Two Acceptance Criteria defer decisions to implementation time~~ — resolved 2026-09-23; see Design Decisions.
- `usage_from_event` has 4 call sites (`subprocess_utils.py` 143/169/706/730) feeding live usage rows; stored values change for new Codex rows.

### Outcome Risk Factors
- Minor open design decisions (inconsistent-component representation; existing-row handling) — resolvable during implementation but affect stored data.
- Shared normalizer touches two modules (`subprocess_utils`, `ctx_stats`) plus ENH-3532 coupling.

## Session Log
- `/ll:verify-issues` - 2026-09-24T03:44:03 - `747bdb3d-c82b-437c-9f00-ae0dbc6a8638.jsonl`
- `/ll:confidence-check` - 2026-09-24T00:45:01 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:37:52 - `97f40d76-766f-412a-a4ef-794728276e4c.jsonl`

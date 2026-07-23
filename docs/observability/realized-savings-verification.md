# EPIC-2456 Realized-Savings Verification Report

> **ENH-2719 — EPIC-2456 closure gate**

This report is the closure gate for EPIC-2456 (token-cost reduction). Per
shipped child, it records the Success Metrics gate, the measurement method,
the measured value (or the reason no value could be produced), and a
pass/fail/blocked verdict. Closure is conditioned on this report existing —
not on every gate passing (ENH-2719 Expected Behavior).

Measured 2026-07-22. Read-only: no production code was changed to produce
these numbers (ENH-2719 Scope Boundaries).

## Gate Catalog

| Gate | Feature | Method | Measured value | Verdict |
|---|---|---|---|---|
| Tier 0 before/after cost delta | FEAT-2470 | `CostReport.from_usage_jsonl` diffed against the ENH-2518 locked baseline (`scripts/tests/fixtures/tier0_traces/`) | **Not computable against the locked baseline** — see below (ENH-2745 fixed the pricing half of the block; a same-model relock is still needed) | **BLOCKED** |
| F4 heuristic compressor 3–6× | FEAT-2675/2599 | Existing test: `test_heuristic_compression.py::TestReductionBand` | Every locked trace + the mean fall inside 3.0–6.0× (test asserts this on every run) | **PASS (test-enforced, cited)** |
| F3 compaction shrink ratio 50–70% | FEAT-2598 | Ad-hoc script calling `evict_sink_and_window()` on 3 representative on-disk session transcripts, token count via the LCM `len//4` estimate | 89.6%, 73.8%, 61.3% (mean 74.9%) — see below | **FAIL (2 of 3 over-shrink)** |
| F1 cache_read populated on >50% of FSM iterations | FEAT-2478/ENH-2724 | Ad-hoc read-only query (`_connect_readonly`-style) over `.ll/history.db` `usage_events` grouped by `state IS NOT NULL` | 6/6 rows with `state` populated also have `cache_read_input_tokens > 0` (100%) | **PASS on paper, sample negligible** — see below |
| F10 warmed cache-hit rate >80% | FEAT-2673/2710 | Same `usage_events` query, filtered to a repeated `run_id`/`state` pair | No data — see below | **BLOCKED (structurally dormant)** |
| F5 DES accepts 100% of events | FEAT-2478 | Existing test: `test_otel_attributes.py` | Passing | **PASS (test-enforced, cited)** |
| F6 stable per-state cost JSON schema | ENH-2477 | Existing tests: `test_fsm_cost_graph.py`, `test_tier0_traces.py` | Passing | **PASS (test-enforced, cited)** |

Full run: `python -m pytest scripts/tests/test_heuristic_compression.py
scripts/tests/test_tier0_traces.py scripts/tests/test_otel_attributes.py
scripts/tests/test_compaction.py scripts/tests/test_streaming_cache_parity.py`
— 90 passed, 1 skipped.

## Tier 0 (FEAT-2470) — BLOCKED

The locked baseline (`tier0-traces.md`) is pinned to `single_model_only:
claude-sonnet-4-6`. No `general-task` trace on disk postdates FEAT-2470's
completion (2026-07-06) with that same model:

- `.loops/runs/general-task-20260707T133447/usage.jsonl` (2026-07-07, the
  only post-ship `general-task` run) uses `MiniMax-M3[1m]` — not in
  `MODEL_PRICING`, `CostReport.from_usage_jsonl` returns `cost_usd: 0.0` /
  `has_unknown_model: true` for every state (still true; `MiniMax-M3` is
  unrelated to ENH-2745's fix and remains unpriced).
- Every loop run from 2026-07-20 onward uses `claude-sonnet-5` or
  `claude-opus-4-8` — **ENH-2745 added both to `MODEL_PRICING`**
  (`scripts/little_loops/pricing.py`), along with `claude-fable-5`, so these
  traces now price successfully. (The `[1m]` suffix in the original grep
  evidence above was inaccurate — live `usage_events.model` rows store the
  bare `claude-opus-4-8` string; see ENH-2745's Codebase Research Findings.)

The fleet's default model moved twice since the baseline was locked
(`claude-sonnet-4-6` → `MiniMax-M3` → `claude-sonnet-5`/`claude-opus-4-8`).
Pricing is no longer the blocker, but a **same-model** diff against the
ENH-2518 baseline still requires either (a) a new `claude-sonnet-4-6` trace
postdating FEAT-2470 (none exists), or (b) relocking a new Tier 0 baseline
against `claude-sonnet-5`/`claude-opus-4-8` following the ENH-2518 precedent.
ENH-2745 deliberately did not relock — it kept the ENH-2518 `claude-sonnet-4-6`
set as the historical reference and left relocking as a follow-up, since a
relock is a separate, larger effort (new trace capture + manifest/test-fixture
updates) than the pricing-table fix this issue scoped. See Follow-ups.

## F3 — Compaction Shrink Ratio (FEAT-2598)

`evict_sink_and_window(messages, sink_n=4, window_n=20)` was run against
three real on-disk session transcripts (message-count capped read, `role`
+ `content` extracted, tokens estimated via the `len(text)//4` LCM
convention `session_store._estimate_tokens` uses):

| Session (truncated id) | Messages before → after | Tokens before → after | Shrink |
|---|---|---|---|
| `84cbedd9` | 136 → 24 | 91,917 → 9,583 | 89.6% |
| `a2a457a7` | 55 → 24 | 47,253 → 18,301 | 61.3% |
| `8c12fca6` | 58 → 24 | 62,093 → 16,264 | 73.8% |

Mean 74.9%, range 61.3–89.6%. One of three sessions lands inside the
50–70% gate; two exceed it (over-shrink relative to the gate, in the
direction of *more* reduction, not less). Caveat: this measures only the
always-on structural eviction pass (`evict_sink_and_window`) at its default
`sink_n=4`/`window_n=20`, not the combined effect with the soft-threshold-gated
`summarize_6_section` LLM pass, since that pass requires a live model call and
is out of scope for a read-only measurement. The gate is written against
whichever pass(es) actually fire in production, so this is a lower-bound
proxy, not the full picture — see Follow-ups.

## F1 — Cache Read Populated on FSM Iterations (FEAT-2478/ENH-2724)

```sql
SELECT COUNT(*) FROM usage_events WHERE state IS NOT NULL;
-- 6
SELECT COUNT(*) FROM usage_events
  WHERE state IS NOT NULL AND cache_read_input_tokens IS NOT NULL
    AND cache_read_input_tokens > 0;
-- 6
```

100% of the 6 rows with `state` populated also have `cache_read_input_tokens
> 0`, clearing the ">50% of FSM iterations" bar. But the denominator is 6
against 183,524 total `usage_events` rows — nearly every row still has
`state IS NULL` (the historical backfill path, which never populates
`state`; only the live `record_usage_event()` writer, ENH-2724, does). The
6 populated rows are themselves from `confidence_check`/`refine_issue`/
`wire_issue` states captured during this same ENH-2719 session, not a
production sample. The gate passes technically but the population mechanism
is barely exercised — see Follow-ups.

## F10 — Warmed Cache-Hit Rate (FEAT-2673/2710) — BLOCKED

`OrchestrationConfig.request_path` defaults to `"cli"`
(`scripts/little_loops/config/orchestration.py:91`); the 0.1×-read/1.25×-write
cache discount this gate measures is unreachable over the CLI shell path per
that file's own docstring. No opt-in `sdk`/`batch` run set exists to measure
against. This gate is structurally dormant until ENH-2738 (or a temporary
opt-in run set) produces `sdk`/`batch` traffic — out of scope for this
read-only pass per ENH-2719 Scope Boundaries (temporary opt-in runs were
step 4 of the Proposed Solution; none were executed in this pass).

## F5 / F6 — Already Test-Enforced

Cited, not re-measured, per ENH-2719 Scope Boundaries:

- F5 (DES accepts 100% of events): `scripts/tests/test_otel_attributes.py`
- F6 (stable per-state cost JSON schema): `scripts/tests/test_fsm_cost_graph.py`,
  `scripts/tests/test_tier0_traces.py`

Both suites pass as of this report (see Full run above).

## Follow-ups Filed

- Tier 0 before/after was blocked on model-pricing drift (`MODEL_PRICING` had
  no `claude-sonnet-5`/`claude-opus-4-8` entries) — fixed by ENH-2745. The gate
  remains BLOCKED pending a same-model relock (ENH-2518 precedent) against the
  current default model; tracked as a follow-up parented to EPIC-2456.
- F3's 61–90% spread (vs. the 50–70% gate) on structural eviction alone
  warrants either a combined-pass measurement (requires a live summarization
  call) or a gate-band reconciliation — filed as a follow-up parented to
  EPIC-2456.
- F1/F10 remain dormant under the `cli` default; ENH-2738 already tracks the
  default flip and is blocked on this issue closing — no separate follow-up
  needed beyond noting F1's tiny sample size in ENH-2738's own gate.

See EPIC-2456's Session Log for the filed issue IDs.

## Coordination

Siblings in `docs/observability/`: [`tier0-traces.md`](tier0-traces.md)
(locked Tier 0 fixture format), [`streaming-parity-traces.md`](streaming-parity-traces.md)
(F5 streaming/blocking parity), [`otel-mapping.md`](otel-mapping.md) (F1's
`cache_read_input_tokens` → `gen_ai.usage.cache_read.input_tokens` field
mapping), [`docs/reference/CONFIGURATION.md`](../reference/CONFIGURATION.md#request_path)
(the `request_path` opt-in condition F1/F10 need to leave dormancy).

## Decision History

- 2026-07-22 — ENH-2719 measurement pass produced this report. Tier 0 and
  F10 are blocked (model drift, structural dormancy respectively); F3
  measured outside its gate band on the structural-eviction-only proxy; F1,
  F4, F5, F6 pass (F1 on a negligible sample). Per ENH-2719 Expected
  Behavior, EPIC-2456 closure is gated on this report's existence, not on
  100% gate pass — closure may proceed once follow-ups are filed for the
  BLOCKED/FAIL rows above.

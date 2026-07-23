---
id: ENH-2719
type: ENH
title: EPIC-2456 realized-savings verification and closure gate
priority: P2
status: done
captured_at: '2026-07-21T17:22:20Z'
completed_at: '2026-07-23T01:42:46Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- observability
- verification
relates_to:
- EPIC-2456
- ENH-2471
- ENH-2479
- ENH-2477
- FEAT-2478
- ENH-2712
- ENH-2723
- ENH-2724
- ENH-2725
- ENH-2737
- ENH-2738
confidence_score: 98
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 25
---

# ENH-2719: EPIC-2456 realized-savings verification and closure gate

## Summary

EPIC-2456's Success Metrics are full of measured gates — F1 `cache_read_input_tokens` populated on >50% of FSM iterations, F3 compaction shrink in the 50–70% range, F4 heuristic compressor at 3–6× on the locked trace set, F10 warmed cache-hit rate >80%, Tier 0 before/after cost delta — but no child owns actually *running* those measurements now that the features have shipped. Everything is instrumented (FEAT-2478 OTel `gen_ai.usage.*` emission, ENH-2477 per-state cost attribution, `ll-ctx-stats`) but unverified against real runs. Add a verification pass that executes each shipped feature's success gate, records before/after $/run in the epic, and flags any gate that fails. The epic cannot honestly close without this — it is the closure gate.

## Motivation

The whole epic's justification rests on a measurable reduction in $/run, and the plans (`thoughts/plans/2026-07-02-token-cost-optimal-techniques.md`) insist even "free" wins get a measured gate: "'Free' code paths have a long history of becoming unmeasured assumptions." As of 2026-07-21, Tiers 0–3 plus the transport tranche are `done` on paper with zero realized-savings numbers recorded anywhere. Without this pass, (a) the epic closes on claimed rather than measured savings, and (b) ENH-2738 (the `request_path` default flip, successor to the now-decomposed ENH-2720) has no parity/savings evidence to gate on.

## Current Behavior

- Shipped features carry per-feature success gates in EPIC-2456 § Success Metrics, but no measurement has been run or recorded against them.
- The telemetry to answer them exists: `usage_events` in `.ll/history.db` (FEAT-2478), per-state cost attribution (ENH-2477), `ll-ctx-stats`.
- Locked trace sets exist only partially: Tier 0 set (ENH-2471, relaxed to ≥2 confirmed-stable traces), streaming-parity 3-fixture set (ENH-2479). The F4 10-trace `general-task` set and the F8 5-trace handoff set were never locked (F8 itself is unfiled).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction — Tier 0 is already locked, done**: `ENH-2518` ("lock-tier-0-verification-trace-set", `status: done`) already produced the locked set — `scripts/tests/fixtures/tier0_traces/manifest.json` (`_meta.owner: "ENH-2518"`, `lock_date: 2026-07-08`) plus two trace files and `docs/observability/tier0-traces.md`. Only the *before/after cost-delta measurement run* against these locked traces (Proposed Solution step 1) remains open — not the lock itself.
- **Correction — F4's 10-trace set is already locked AND already gated by a passing test**: `scripts/tests/fixtures/heuristic_traces/manifest.json` (`_meta.owner: "FEAT-2675"`) holds 10 `general-task` traces, and `scripts/tests/test_heuristic_compression.py::TestReductionBand.test_trace_in_band` / `test_mean_in_band` already asserts each trace and the mean fall in the 3.0–6.0× band via `CompressedResult.reduction_ratio` (`scripts/little_loops/compression/heuristic.py:75-80`). This gate is effectively already satisfied and should move to the F5/F6 "cite existing tests" bucket (Proposed Solution step 5), not step 2's "lock + measure."
- **F3 (compaction) has no shrink-ratio measurement at all** — confirmed genuinely open. `CompactResult` (`scripts/little_loops/compaction/result.py:15-31`) carries no `original_tokens`/ratio field, and `evict_sink_and_window()` (`scripts/little_loops/compaction/instant.py:34`) returns only the trimmed message list with no before/after accounting. `test_compaction.py` is correctness-only (no shrink-band assertion). New measurement code is required here.
- **F1/F10 gates are structurally dormant**, confirmed: `OrchestrationConfig.request_path` defaults to `"cli"` (`scripts/little_loops/config/orchestration.py:91`), and the 0.1×-read/1.25×-write cache discount is "unreachable over the CLI shell path" per that file's docstring. `fsm/executor.py:_resolve_request_path()` (line 2007) confirms per-state override else config default. No existing query computes "cache_read_input_tokens populated on >50% of FSM iterations" (F1) or warmed-vs-unwarmed cache hit rate (F10) — `ll-ctx-stats`'s `_aggregate_usage_events()` (`scripts/little_loops/cli/ctx_stats.py:183`) rolls up by model only, not by state/iteration.
- **`usage_events` can now answer F1's question structurally**: the live writer `record_usage_event()` (`session_store.py:2065-2109`, ENH-2724) populates both `state` and `cache_read_input_tokens` per FSM iteration (unlike the historical backfill path, which always leaves `state` NULL). A new query — not yet written — grouping by `run_id`/`state` would answer the F1 gate once `sdk`/`batch` opt-in runs are captured.

## Expected Behavior

A single verification report (checked into the epic's Session Log, with the artifact under `thoughts/` or `docs/observability/`) that, per shipped feature, states: the gate, the measurement method, the measured value, and pass/fail. Failed gates each get a follow-up issue filed. The epic's closure is conditioned on this report existing — not on every gate passing (a failed gate with a filed follow-up is an acceptable closure state; a missing measurement is not).

## Proposed Solution

Run the cheapest sufficient measurement per gate, in dependency order:

1. **Tier 0 (FEAT-2470)** — before/after cost delta on the ENH-2471 locked traces via the host CLI `usage` block, as specified in that issue's remaining scope (trace-set lock + baseline capture were left open there; either finish them here or mark this line blocked on ENH-2471's residue).
2. **F4 heuristic compressor (FEAT-2675/2599)** — lock the 10-trace `general-task` set (Open Question #3 in the epic) and measure the compression ratio against the 3–6× gate. Note: compression is already default-on (trigger-gated at `trigger_pct=0.4` of context window), so this measures live behavior.
3. **F3 compaction (FEAT-2598)** — eviction+schema shrink on representative sessions vs the 50–70% gate; the system/CLAUDE.md-preservation regression test already exists, so only the shrink range needs a measured number.
4. **F1/F10/Batches (FEAT-2673/2674/2710/2716)** — these are dormant under the default `orchestration.request_path: "cli"`. Measure on opt-in runs: N `ll-loop run` invocations with `request_path: "sdk"` (then `"batch"` where latency-insensitive), reading `cache_read_input_tokens` share and $/run from `usage_events`. These same runs double as ENH-2738's parity evidence — coordinate the run set so it serves both issues.
5. **F5/F6 (FEAT-2478/ENH-2477)** — their gates (DES accepts 100% of events; stable JSON schema) are already test-enforced; cite the tests rather than re-measuring.
6. Record everything in one report; file follow-ups for failed gates; append the epic Session Log entry that closes EPIC-2456's measurement obligation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reusable aggregator for step 1 (Tier 0)**: `CostReport.from_usage_jsonl()` (`scripts/little_loops/fsm/cost_graph.py:184-256`) is the canonical per-run cost aggregator ENH-2471/ENH-2518 already used and documented in `docs/observability/tier0-traces.md`'s "Aggregation Order" section — reuse it for the before/after delta rather than re-deriving cost math. Pricing constants live in `scripts/little_loops/pricing.py:10-55` (`MODEL_PRICING`, `estimate_cost_usd()`).
- **Step 2 is already done** (see Current Behavior findings above) — F4's 3–6× gate is satisfied by the existing `test_heuristic_compression.py` pass; this step reduces to citation, moving it under step 5's "already test-enforced" umbrella.
- **Step 3 (F3 shrink ratio) needs new measurement code**, since neither `CompactResult` nor `evict_sink_and_window()` currently compute or return a before/after token ratio (see Current Behavior findings).
- **Step 4 (F1/F10 opt-in runs) has a reusable query layer to build on**: `history_reader.py:862` `cost_attribution()` and `history_reader.py:1558` `aggregate_loop_runs()` are the established `usage_events`-querying patterns (whitelist-guarded `GROUP BY`, `_connect_readonly()` never-raise contract) that a new F1/F10 query function should follow — see `scripts/tests/test_history_reader.py:92-181` (`TestCostAttribution`) for the test pattern to model after.
- **Report artifact shape**: prior EPIC-2456 children (`docs/observability/tier0-traces.md`, `docs/observability/streaming-parity-traces.md`) establish the convention for a report under `docs/observability/`: sections for Overview/Trace-or-Gate Catalog (table), Fixture/Measurement Format, Test Strategy, Coordination (cross-links to sibling docs), Forward-Compat, and (per `streaming-parity-traces.md`) a "Decision History" section pointing back at issue-file line ranges. Following this convention keeps the new report consistent with siblings.
- **EPIC closure entry pattern**: `EPIC-1707`'s closure used a `## Verification Notes` section (dated, `**Verdict: CLOSED**` prose citing evidence) rather than annotating each Success Metrics bullet inline — the closest existing precedent for how EPIC-2456's own annotation should look. EPIC-2456's own Session Log entries (lines 365-377) use bare labels like `epic-review` for non-slash-command entries — follow that convention rather than inventing a new one.
- **Follow-up filing mechanism**: use `capture-issue "description" --parent EPIC-2456` (see `skills/capture-issue/SKILL.md`) to file a gate-failure follow-up — it sets `parent:` frontmatter and updates the epic's `relates_to:`/`## Children` automatically, the same mechanism used to file ENH-2719 itself and its siblings (ENH-2723/2724/2725).

## Implementation Steps

1. Inventory each shipped child's success gate from EPIC-2456 § Success Metrics; classify as test-enforced (cite) vs run-measured (measure).
2. Close the trace-set gaps (Tier 0 baseline capture; F4 10-trace lock).
3. Execute the opt-in `sdk`/`batch` run set and the compaction/compression measurements.
4. Write the verification report; file follow-ups for failed gates; update the epic.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Correct the stale `ENH-2720` references in Motivation and Proposed Solution step 4 to point at `ENH-2738` (the live blocked successor) — `ENH-2720` is closed/decomposed.
6. When annotating EPIC-2456 in step 4, also strike/update its "Open Questions for Refinement" line about the F4 10-trace set (already locked per this issue's own Codebase Research Findings), not just the Success Metrics bullets.
7. Cross-link the new report from `docs/observability/otel-mapping.md` (F1 field mapping) and `docs/reference/CONFIGURATION.md:1517` (request_path opt-in condition) where relevant.

## Integration Map

### Files to Modify
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` (Session Log + Success Metrics annotations)
- New report artifact under `thoughts/` or `docs/observability/`

### Dependent Files (Callers/Importers)
- N/A — read-only over `.ll/history.db` and run artifacts; no production code changes expected.

### Similar Patterns
- ENH-2471's before/after protocol (host CLI `usage` block measurement, Tier 0)
- ENH-2712's `waste` view (complementary: it ranks wasted spend; this verifies realized savings)

### Tests
- Cite existing: `test_streaming_cache_parity.py`, `test_compaction.py`, `test_heuristic_compression.py`, `test_otel_attributes.py`. New tests only if a gate measurement becomes a reusable CLI.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_history_reader.py:92-201` (`TestCostAttribution`) — cite as the test pattern to follow if a new F1/F10 query function is added to `history_reader.py`: per-`tmp_path` seeded db, whitelist-injection `pytest.raises(ValueError)` test, missing-db/empty-table zero-result tests [Agent 1/3 finding]
- `scripts/tests/test_fsm_cost_graph.py` — unit tests for `CostReport`/`cost_graph.py`, the Tier 0 aggregator this issue reuses [Agent 1 finding]
- `scripts/tests/test_tier0_traces.py` — validates the locked Tier 0 trace set (ENH-2518) this issue's step 1 measures against [Agent 1 finding]
- `scripts/tests/test_cli_cost_table.py` — cost table aggregation tests, same `cost_graph.py` surface [Agent 1 finding]
- `scripts/tests/test_pricing.py` — unit tests for `pricing.py` (`MODEL_PRICING`, `estimate_cost_usd()`) [Agent 1 finding]
- `scripts/tests/test_cli_ctx_stats.py` — tests for `ctx_stats.py`'s `_aggregate_usage_events()`, the model-keyed rollup this issue's F1 measurement extends conceptually [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Measurement/query surfaces to read from (no modification, per Scope Boundaries):**
- `scripts/little_loops/fsm/cost_graph.py` — `CostReport.from_usage_jsonl()` (Tier 0 before/after aggregator)
- `scripts/little_loops/pricing.py` — `MODEL_PRICING` / `estimate_cost_usd()`
- `scripts/little_loops/session_store.py` — `usage_events` schema (`_MIGRATIONS` v20/v21/v29, lines 740-775, 916-923), `record_usage_event()` (line 2065, ENH-2724 live writer)
- `scripts/little_loops/history_reader.py` — `cost_attribution()` (line 854), `aggregate_loop_runs()` (line 1550) — patterns for a new F1/F10 query
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events()` (line 183); currently model-keyed only, no per-state/iteration or warmed-hit-rate view
- `scripts/little_loops/compaction/result.py` / `compaction/instant.py` — confirms F3 has no existing ratio computation. Computing it from existing `CompactResult`/`evict_sink_and_window()` outputs at the measurement-script level (not modifying those modules) keeps this within the "no production code changes" Scope Boundary
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.request_path` default (`"cli"`, line 91) confirming F1/F10 dormancy

**Locked trace-set fixtures already on disk (reuse, do not re-lock):**
- `scripts/tests/fixtures/tier0_traces/manifest.json` (owner ENH-2518, done)
- `scripts/tests/fixtures/heuristic_traces/manifest.json` (owner FEAT-2675, F4 gate already passing)
- `scripts/tests/fixtures/streaming_parity/` (owner ENH-2479)

**Report artifact precedent to model the new doc after:**
- `docs/observability/tier0-traces.md`, `docs/observability/streaming-parity-traces.md` (section shape: Overview, Catalog table, Format, Coordination, Forward-Compat, Decision History)

**Follow-up-issue mechanism:**
- `skills/capture-issue/SKILL.md` — `--parent EPIC-2456` flag files a gate-failure follow-up parented to the epic

### Documentation
- EPIC-2456 Success Metrics section annotated with measured values.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/observability/otel-mapping.md:15` — documents the `cache_read_input_tokens` → `gen_ai.usage.cache_read.input_tokens` OTel field mapping the F1 gate measures against; cross-link from the new report [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:1517` — documents when `orchestration.request_path` must be `"sdk"`/`"batch"` for cache discounts to apply, the same condition step 4's temporary opt-in exercises; cross-link so readers can reproduce the measurement config [Agent 2 finding]
- `docs/ARCHITECTURE.md` (F1 section ~line 8486/8519-8520, F4 section ~line 7738, F5 sections ~lines 763-765/4073/4682) — describes these gates as shipped but does not link to any measurement artifact; the new report is the natural cross-link target once it exists [Agent 2 finding]
- `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` "Open Questions for Refinement" (line 342) still asks to "lock a 10-trace `general-task` set" — stale text contradicting this issue's own Codebase Research Finding that the set (FEAT-2675, `heuristic_traces/manifest.json`) is already locked and gated. The epic-annotation step (Implementation Step 4) should strike/update this Open Question, not just the Success Metrics bullets [Agent 2 finding]
- Motivation and Proposed Solution step 4 cite **ENH-2720** as the open issue awaiting this issue's parity evidence. ENH-2720 is `status: done` (decomposed 2026-07-22 into ENH-2737 and ENH-2738 — its `relates_to` already lists both). The actual live blocked dependent is **ENH-2738** (`P2-ENH-2738-flip-request-path-default-to-sdk-plus-batch-tranche.md`), which states verbatim: "Blocking Gate unmet: ENH-2719 ... Do not start until ENH-2719 closes." Update the prose references from ENH-2720 to ENH-2738 for accuracy [Agent 2 finding]

### Configuration
- Temporary opt-in `orchestration.request_path: "sdk"`/`"batch"` for the measurement run set (not a default change — that is ENH-2720).

## Success Metrics

- Every shipped child's success gate from EPIC-2456 § Success Metrics is classified (test-enforced or run-measured) and, for run-measured gates, has a recorded measured value and pass/fail verdict.
- The verification report exists as a checked-in artifact (Session Log entry + file under `thoughts/` or `docs/observability/`).
- Every failed gate has a filed follow-up issue — closure is conditioned on report existence, not on 100% gate pass rate.

## Scope Boundaries

- No production code changes — this issue is read-only measurement and reporting over `.ll/history.db` and run artifacts.
- Does not flip `orchestration.request_path`'s default (`sdk`/`batch` are temporary opt-in for the measurement run set only) — that default-flip decision belongs to ENH-2720.
- Does not file or scope F8 (5-trace handoff set) itself, since F8 is unfiled — measuring it is out of scope until it exists as an issue.
- Does not re-measure gates already test-enforced (F5/F6) — those are cited, not re-run.

## Impact

- **Priority**: P2 — gates epic closure and supplies the evidence ENH-2720 needs; no production behavior change.
- **Effort**: Medium — mostly running instrumented workloads and writing the report; the trace-set locks are the only net-new scope.
- **Risk**: Low — read-only measurement plus temporary opt-in config.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Relevance | Notes |
|---|---|---|
| [thoughts/plans/2026-07-02-token-cost-optimal-techniques.md](../../thoughts/plans/2026-07-02-token-cost-optimal-techniques.md) | **High** | Source of the per-tier success gates and the "measure, don't claim" posture. |
| [docs/reference/API.md](../../docs/reference/API.md) | Medium | Documents the shipped telemetry surfaces (`observability/tracing.py`, `usage_events`) this issue reads. |

## Labels

`token-cost`, `observability`, `verification`, `captured`

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-23T01:42:25Z - `1b068faa-9da8-4bec-af30-feafda6b3309.jsonl`
- `/ll:ready-issue` - 2026-07-23T01:29:44 - `9e10ca08-bf89-4378-a3c1-b4d4fefafbf2.jsonl`
- `/ll:confidence-check` - 2026-07-23T01:25:14Z - `908b0104-1612-42ee-85e6-ff4a32c7ed4f.jsonl`
- `/ll:wire-issue` - 2026-07-23T01:23:08 - `055d042e-137b-4246-ab63-b4d0b2962a74.jsonl`
- `/ll:refine-issue` - 2026-07-23T01:17:31 - `4c513c9a-ad0e-4ba6-8bb2-b15c00f0558c.jsonl`
- `/ll:format-issue` - 2026-07-23T01:11:38 - `4947a177-2cdd-4fa8-9397-409b7a6a5e4b.jsonl`
- `/ll:capture-issue` - 2026-07-21T17:22:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9384c3a9-e5cf-4f15-a503-33c5d34b10c7.jsonl`

---
id: ENH-2719
type: ENH
title: EPIC-2456 realized-savings verification and closure gate
priority: P2
status: open
captured_at: '2026-07-21T17:22:20Z'
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
- ENH-2720
- ENH-2723
- ENH-2724
- ENH-2725
---

# ENH-2719: EPIC-2456 realized-savings verification and closure gate

## Summary

EPIC-2456's Success Metrics are full of measured gates — F1 `cache_read_input_tokens` populated on >50% of FSM iterations, F3 compaction shrink in the 50–70% range, F4 heuristic compressor at 3–6× on the locked trace set, F10 warmed cache-hit rate >80%, Tier 0 before/after cost delta — but no child owns actually *running* those measurements now that the features have shipped. Everything is instrumented (FEAT-2478 OTel `gen_ai.usage.*` emission, ENH-2477 per-state cost attribution, `ll-ctx-stats`) but unverified against real runs. Add a verification pass that executes each shipped feature's success gate, records before/after $/run in the epic, and flags any gate that fails. The epic cannot honestly close without this — it is the closure gate.

## Motivation

The whole epic's justification rests on a measurable reduction in $/run, and the plans (`thoughts/plans/2026-07-02-token-cost-optimal-techniques.md`) insist even "free" wins get a measured gate: "'Free' code paths have a long history of becoming unmeasured assumptions." As of 2026-07-21, Tiers 0–3 plus the transport tranche are `done` on paper with zero realized-savings numbers recorded anywhere. Without this pass, (a) the epic closes on claimed rather than measured savings, and (b) ENH-2720 (the `request_path` default flip) has no parity/savings evidence to gate on.

## Current Behavior

- Shipped features carry per-feature success gates in EPIC-2456 § Success Metrics, but no measurement has been run or recorded against them.
- The telemetry to answer them exists: `usage_events` in `.ll/history.db` (FEAT-2478), per-state cost attribution (ENH-2477), `ll-ctx-stats`.
- Locked trace sets exist only partially: Tier 0 set (ENH-2471, relaxed to ≥2 confirmed-stable traces), streaming-parity 3-fixture set (ENH-2479). The F4 10-trace `general-task` set and the F8 5-trace handoff set were never locked (F8 itself is unfiled).

## Expected Behavior

A single verification report (checked into the epic's Session Log, with the artifact under `thoughts/` or `docs/observability/`) that, per shipped feature, states: the gate, the measurement method, the measured value, and pass/fail. Failed gates each get a follow-up issue filed. The epic's closure is conditioned on this report existing — not on every gate passing (a failed gate with a filed follow-up is an acceptable closure state; a missing measurement is not).

## Proposed Solution

Run the cheapest sufficient measurement per gate, in dependency order:

1. **Tier 0 (FEAT-2470)** — before/after cost delta on the ENH-2471 locked traces via the host CLI `usage` block, as specified in that issue's remaining scope (trace-set lock + baseline capture were left open there; either finish them here or mark this line blocked on ENH-2471's residue).
2. **F4 heuristic compressor (FEAT-2675/2599)** — lock the 10-trace `general-task` set (Open Question #3 in the epic) and measure the compression ratio against the 3–6× gate. Note: compression is already default-on (trigger-gated at `trigger_pct=0.4` of context window), so this measures live behavior.
3. **F3 compaction (FEAT-2598)** — eviction+schema shrink on representative sessions vs the 50–70% gate; the system/CLAUDE.md-preservation regression test already exists, so only the shrink range needs a measured number.
4. **F1/F10/Batches (FEAT-2673/2674/2710/2716)** — these are dormant under the default `orchestration.request_path: "cli"`. Measure on opt-in runs: N `ll-loop run` invocations with `request_path: "sdk"` (then `"batch"` where latency-insensitive), reading `cache_read_input_tokens` share and $/run from `usage_events`. These same runs double as ENH-2720's parity evidence — coordinate the run set so it serves both issues.
5. **F5/F6 (FEAT-2478/ENH-2477)** — their gates (DES accepts 100% of events; stable JSON schema) are already test-enforced; cite the tests rather than re-measuring.
6. Record everything in one report; file follow-ups for failed gates; append the epic Session Log entry that closes EPIC-2456's measurement obligation.

## Implementation Steps

1. Inventory each shipped child's success gate from EPIC-2456 § Success Metrics; classify as test-enforced (cite) vs run-measured (measure).
2. Close the trace-set gaps (Tier 0 baseline capture; F4 10-trace lock).
3. Execute the opt-in `sdk`/`batch` run set and the compaction/compression measurements.
4. Write the verification report; file follow-ups for failed gates; update the epic.

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

### Documentation
- EPIC-2456 Success Metrics section annotated with measured values.

### Configuration
- Temporary opt-in `orchestration.request_path: "sdk"`/`"batch"` for the measurement run set (not a default change — that is ENH-2720).

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
- `/ll:capture-issue` - 2026-07-21T17:22:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9384c3a9-e5cf-4f15-a503-33c5d34b10c7.jsonl`

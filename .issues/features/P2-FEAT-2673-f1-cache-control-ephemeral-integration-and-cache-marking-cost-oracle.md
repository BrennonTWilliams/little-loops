---
id: FEAT-2673
title: "F1 — cache_control: ephemeral integration + cache-marking cost oracle"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T15:15:21Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2671
- FEAT-2672
- FEAT-2674
- FEAT-2599
- FEAT-2679
depends_on:
- FEAT-2671
- FEAT-2679
blocks:
- FEAT-2672
- FEAT-2674
decision_needed: true
labels:
- token-cost
- caching
- tier-2
- sdk-integration
---

# FEAT-2673: F1 — `cache_control: ephemeral` integration + cache-marking cost oracle

## Summary

Introduce the `anthropic` SDK (the EPIC's single pip dep and first
network-side change) and add `build_anthropic_request()` to
`scripts/little_loops/host_runner.py`: emit `CacheControlEphemeralParam`
`{"type": "ephemeral", "ttl": "5m" | "1h"}` on system, tool, and
stable-skill blocks. A cache-marking cost oracle (~50 LOC; SGLang
prefix-hash + Li 2025 cost model) decides which blocks to mark and
**refuses to mark any block below the provider's cacheable-prefix minimum**
(Anthropic: 1024 tokens Sonnet, 4096 Opus — confirm current values at
implementation time). This is EPIC-2456 § Children [TBD-10] — Goal #3.
F1 is non-replicable: the 0.1x-read / 1.25x-write discount only exists
when the request body carries the parameter, so this must integrate via
the SDK rather than the CLI shell path.

## Motivation

Caching is the single largest vendor-measured lever in the EPIC (12.5x
cost differential: writes 1.25x, reads 0.1x). Tier 1 telemetry (F5/F6,
all done) is now in place to verify hit rates, and both cache-stability
prerequisites are filed (FEAT-2671, FEAT-2672). The oracle exists to keep
F1 from being a net loss: an unmarked block costs 1.0x; a marked-but-never-
reused block costs 1.25x.

## Decision Needed (EPIC-2456 Open Questions #1, #2, #5)

1. **SDK version pin + CI install verification** (OQ #1): pick the
   `anthropic` pin and add a baseline CI test proving install +
   `cache_control` acceptance before enabling.
2. **Request-path opt-in** (OQ #2): decision recorded in the EPIC — add
   the SDK code path as opt-in via `orchestration.request_path == "sdk"`;
   default remains the CLI shell path. Implement exactly that.
3. **Oracle reuse threshold** (OQ #5): what reuse frequency justifies the
   1.25x write premium? Derive from the Li 2025 cost model against real
   `history.db` reuse distributions before defaulting; the
   below-cacheable-minimum refusal is the fixed base layer.

## Implementation Steps

1. Add `anthropic` to `scripts/pyproject.toml` (pinned per OQ #1).
2. `host_runner.py`: new `build_anthropic_request()` (~80 LOC) behind
   `orchestration.request_path == "sdk"`.
3. New cache-marking oracle (~50 LOC): consumes FEAT-2671 fragment hashes
   for stability, token counts for the cacheable-prefix minimum, and the
   reuse-frequency threshold from OQ #5.
4. Config: add `cache.*` namespace + `orchestration.request_path` to
   `config-schema.json` and `.ll/ll-config.json`.
5. Verify hit rates via the F5 telemetry (`gen_ai.usage.*`,
   `cache_read_input_tokens`) that FEAT-2478/ENH-2479 shipped.

## Files to Modify

- `scripts/little_loops/host_runner.py` (+~130 LOC incl. oracle)
- `scripts/pyproject.toml` (add `anthropic`)
- `config-schema.json`, `.ll/ll-config.json`
- new `scripts/tests/test_cache_control.py`

## Acceptance Criteria

- [ ] `cache_read_input_tokens` populated for >50% of FSM iterations in
      `general-task` runs (EPIC-2456 Success Metrics, F1 row).
- [ ] Oracle never logs a 1.25x write on a block that wasn't reused within
      K subsequent calls (regression test).
- [ ] Oracle marks nothing below the provider cacheable-prefix minimum.
- [ ] Default behavior unchanged: CLI shell path remains the default;
      SDK path is opt-in.
- [ ] Note: the joint cache x router 2x2 ablation set (EPIC-2456 [TBD-19],
      OQ #7) should be decided before this ships — file/link that issue.

## Session Log
- `/ll:decide-issue` - 2026-07-18T19:14:18 - `4fd1c868-e4bb-4ba3-ab7e-80d1d257cbcd.jsonl`
- `/ll:capture-issue` - 2026-07-18T15:15:21Z - captured from EPIC-2456 § Children [TBD-10] (source: thoughts/plans/2026-07-02-token-cost-reduction-architecture.md, Tier 2; report lines 53ff)

## Status

**Open** | Created: 2026-07-18 | Priority: P2

---
id: ENH-2479
title: "F5 — Streaming-vs-blocking cache-accounting parity trace set"
type: ENH
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [FEAT-2478]
labels:
  - token-cost
  - testing
  - streaming
  - parity
  - measurement
  - tier-1
---

# ENH-2479: F5 — Streaming-vs-blocking cache-accounting parity trace set

## Summary

Lock a 3-trace set that proves `cache_read_input_tokens` matches between
`client.messages.create()` and `client.messages.stream()` within 0.1%
across three canonical patterns: static-prefix-stable turn 2+, cache-
write-then-read across tool result, tool-result-only cache hit. This is
EPIC-2456 § Children [TBD-7] and partially resolves the EPIC's Open
Question #6 (locked trace sets need owners — this issue owns the
streaming-parity trace set).

## Motivation

When FEAT-2478 emits `gen_ai.usage.*` rows, it has to decide which
client path (`create()` vs `stream()`) is the source of truth. Today
these paths can return `cache_read_input_tokens` with small fractional
drift. Without a locked parity gate, drift accumulates silently until
cost attribution graphs under-report.

This child locks the trace set + fixtures that gate the 0.1% threshold
in `scripts/tests/test_streaming_cache_parity.py`. The traces must be
representative of the patterns hit by production loops so the gate
recovers regressions, not just textbook cases.

## Current Behavior

No locked trace set exists for streaming-vs-blocking parity; any
"match" is measured against moving targets. Future drift in either
client path will silently degrade cost attribution accuracy.

## Expected Behavior

A locked 3-trace set with:
- Stable, reproducible token counts (fixtures checked in or
  deterministically rebuildable from recorded host invocations)
- `scripts/tests/test_streaming_cache_parity.py` asserts 0.1%
  parity on each trace
- README/notes describing what each trace covers and how to rebuild

## Proposed Solution

1. **Trace selection** (3 traces):
   - **`trace_a_static_prefix_stable_turn_2`**: Same system + skill
     blocks across 2+ turns; cache_read jumps on turn 2. Verifies the
     prefix-stable case path.
   - **`trace_b_write_then_read_across_tool_result`**: First turn
     writes cache; tool result lands; second turn reads it. Verifies
     the cache hits *across* a tool result, which is the hardest case.
   - **`trace_c_tool_result_only_cache_hit`**: Pure tool-result-only
     cache hit with no system-prefix change.

2. **Fixture format**: recorded host invocations stored under
   `scripts/tests/fixtures/streaming_parity/{trace_a,b,c}/` with
   expected `usage` block per turn in JSON. Fixture loader rebuilds
   the parity assertion from the recorded block.

3. **Test wiring** (`scripts/tests/test_streaming_cache_parity.py`):
   - Parametrize over the 3 fixtures
   - For each, run *both* `messages.create()` and `messages.stream()`;
     diff the `cache_read_input_tokens`; assert diff ≤ 0.1%
   - Skip gracefully when the SDK isn't installed (the `anthropic`
     package install arrives with FEAT-2478's F1 prerequisite; this
     test is gated on `importlib.util.find_spec("anthropic")`)

4. **Recovery**: each trace ships a `rebuild.sh` that re-records from
   scratch if Anthropic ships a meaningfully new SDK version.

## Integration Map

### Files to Modify

- `scripts/tests/test_streaming_cache_parity.py` (new)
- `scripts/tests/fixtures/streaming_parity/trace_a_*/...json` (new
  fixtures)
- `scripts/tests/fixtures/streaming_parity/trace_b_*/...json`
- `scripts/tests/fixtures/streaming_parity/trace_c_*/...json`
- `scripts/tests/fixtures/streaming_parity/{trace,rebuild}.sh` (helpers)

### Dependent Files (Callers/Importers)

- `FEAT-2478` (`observability/tracing.py:StreamingParityChecker`) —
  the production parity check references these fixtures for behavior
  matching

### Similar Patterns

- Existing pytest `parametrize` over fixtures pattern is well-
  established in `scripts/tests/test_fsm_*` — follow it
- The `importlib.util.find_spec("anthropic")` skip pattern is used in
  other SDK-gated tests — confirm before adding

### Tests

- The test file itself is the deliverable; verifies 3 traces pass
  0.1% parity

### Documentation

- `docs/observability/streaming-parity-traces.md` (new) — describes
  trace A/B/C, what each covers, how to rebuild
- Brief mention in `docs/reference/API.md` `observability/tracing.py`
  docs

### Configuration

- N/A — fixture-driven; no config schema change

## Implementation Steps

1. Pick initial 3 traces (owner's pick; mine from any
   `claude -p` runs against `general-task` or `deep-research` that hit
   the 3 patterns)
2. Record host invocations + token counts into fixtures
3. Author `test_streaming_cache_parity.py` parametrized over the 3
   fixtures
4. Skip gracefully when `anthropic` is not installed
5. Document trace A/B/C in
   `docs/observability/streaming-parity-traces.md`
6. Verify `python -m pytest scripts/tests/test_streaming_cache_parity.py
   -v` passes
7. Coordinate with FEAT-2478: same fixtures used by production
   `StreamingParityChecker` for runtime verification

## Acceptance Criteria

- 3 fixtures in `scripts/tests/fixtures/streaming_parity/`
- `test_streaming_cache_parity.py` parametrize-over-fixtures, asserts
  0.1% diff per trace
- Skip when `anthropic` SDK is not installed (no hard-fail for
  contributors without the SDK)
- Each fixture has a `rebuild.sh` that records fresh tokens after SDK
  upgrade
- Trace docs in `docs/observability/streaming-parity-traces.md`
- `python -m pytest scripts/tests/` exits 0

## Scope Boundaries

- **In**: 3 locked fixtures + parity test
- **Out**: Production parity check itself (FEAT-2478); OTel emission
  (FEAT-2478); `anthropic` SDK install (lands with F1)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Tier 1 [TBD-7], Open Question #6 |
| `FEAT-2478` | Consumer of these fixtures in production `StreamingParityChecker` |
| `scripts/tests/test_fsm_*.py` | Established parametrize-over-fixture pattern |

## Impact

- **Priority**: P2 — gates the credibility of F5's streaming-vs-blocking
  parity metric
- **Effort**: Small — 3 fixture recordings + 1 parametrized test
- **Risk**: Low — test-only; production parity check is FEAT-2478
- **Breaking Change**: No — tests are additive; no runtime behavior
  changes

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`

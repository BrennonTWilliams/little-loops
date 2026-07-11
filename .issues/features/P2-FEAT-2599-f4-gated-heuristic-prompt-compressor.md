---
id: FEAT-2599
title: "F4-gated — Heuristic prompt compressor (LLMLingua-gated fallback)"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-11T00:00:00Z"
discovered_date: 2026-07-11
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [ENH-2486]
labels:
  - token-cost
  - fsm
  - compression
  - tier-3
decision_needed: false
---

# FEAT-2599: F4-gated — Heuristic prompt compressor

## Summary

Add an in-house, zero-dependency heuristic prompt compressor invoked from
`fsm/runners.py` for prompts ≥8K tokens: drop repeated tool results older
than 5 turns, dedupe stable system blocks (flagging them as
`cache_control` candidates for the separate, not-yet-filed F1 caching
child — no coupling to F1's implementation, just a flag), and
tail-truncate assistant turns beyond N. The real LLMLingua ML compressor
(GPT2-small, ~700MB weights, pulls in `transformers`) stays **out of
scope and disabled by default** — it is gated behind
`compression.heuristic_underperforms == true`, set only after a benchmark
proves the heuristic underperforms. This is EPIC-2456 § Children
[TBD-13] — directly serves Goal #9 in the EPIC.

## Motivation

The algorithmic compression LLMLingua achieves is real (up to ~20× per
upstream benchmarks), but reproducing the model from scratch is out of
scope, and shipping the pip dependency by default pulls in `transformers`
+ 700MB of weights for every install. The heuristic approach (adapted
from LLMLingua's extractive strategy and Jha's tool-result trimming)
replicates most of the *outcome* — dropping stale tool output, deduping
repeated system blocks, truncating verbose tails — without the dependency
tree. Gating the real LLMLingua behind a measured benchmark, rather than
defaulting to it, keeps the epic's "0 sidecars, minimal deps" posture
intact while leaving a documented escape hatch if the heuristic proves
insufficient.

## Current Behavior

- No prompt-compression step exists at the `fsm/runners.py`
  prompt-assembly boundary. Prompts grow unboundedly with tool-result
  history until other mechanisms (compaction, session boundaries) kick
  in.
- ENH-2486 (done 2026-07-06) added a prompt-size guard + artifact
  bounding at the same `fsm/runners.py` insertion point, but that is a
  guard/cap, not a compressor — it does not reduce token count via
  content-aware trimming.

## Expected Behavior

- For any FSM prompt ≥8K tokens, `compression/heuristic.py` runs before
  the request is sent:
  - Repeated tool results older than 5 turns are dropped.
  - Stable system blocks are deduped (and flagged as `cache_control`
    candidates in metadata, for the separate F1 child to consume later —
    no `cache_control` marking happens in this issue).
  - Assistant turns beyond N are tail-truncated.
- The heuristic compressor hits a **3–6× prompt-token reduction range**
  on a locked 10-trace `general-task` set (this issue owns locking that
  trace set — no other issue currently does).
- If the heuristic's measured ratio on that set falls below **0.5× of
  LLMLingua's measured ratio** (LLMLingua run once, offline, purely as a
  benchmark comparator — not as a shipped runtime dependency), the config
  gate `compression.heuristic_underperforms` is available to flip
  compression over to the real LLMLingua pip dependency. Shipping the
  LLMLingua integration itself is **out of scope** for this issue; only
  the benchmark run and the gate wiring are in scope.
- `.ll/ll-config.json` gains a `compression.*` namespace including
  `compression.heuristic_underperforms` (default `false`).

## Proposed Solution

1. **`scripts/little_loops/compression/heuristic.py`** (new, ~150 LOC):
   - `drop_stale_tool_results(messages, max_age_turns=5)`
   - `dedupe_stable_system_blocks(messages)` — returns deduped blocks +
     a `cache_control_candidate` flag list in metadata (consumed later
     by the separate F1 child, not wired here)
   - `tail_truncate_assistant_turns(messages, max_n)`
   - `compress(messages, token_threshold=8000) -> CompressedResult`
2. **`scripts/little_loops/fsm/runners.py`**: hook `compress()` into the
   prompt-assembly path for prompts ≥8K tokens. Confirm during
   implementation whether ENH-2486's existing size-guard call site is the
   right integration point (see Related Key Documentation) rather than
   adding a second, parallel threshold check.
3. **Benchmark harness**: lock a 10-trace `general-task` trace set (this
   issue documents and commits the set); run both the heuristic and a
   one-time offline LLMLingua comparator over it; record the ratio.
4. **Config gate**: add `compression.heuristic_underperforms` (default
   `false`) to `.ll/ll-config.json` + a matching `compression.*` block in
   `config-schema.json`. When `true`, the (out-of-scope) LLMLingua
   integration is expected to take over — this issue only wires the
   toggle and its default, not the LLMLingua consumer.

## Integration Map

### Files to Modify

- `scripts/little_loops/compression/heuristic.py` (new)
- `scripts/little_loops/fsm/runners.py` — ≥8K-token compression hook

### Dependent Files (Callers/Importers)

- ENH-2486's prompt-size guard occupies the same `fsm/runners.py`
  leverage point (per-invocation prompt-size guard + artifact bounding).
  This issue's threshold hook should build on ENH-2486's existing
  guard/threshold surface rather than duplicating a second, independent
  size check — confirm the exact hook point during implementation.

### Similar Patterns

- N/A — no existing compression pass in the codebase; this is the first.

### Tests

- `scripts/tests/test_heuristic_compression.py` (new) — unit tests for
  each of the three heuristic passes, plus the 3–6× reduction-range
  assertion on the locked 10-trace set.

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section (shared across
  EPIC-2456 children).
- `docs/reference/API.md` — document `compression/heuristic.py`.

### Configuration

- `.ll/ll-config.json` — new `compression.*` namespace:
  `compression.heuristic_underperforms` (default `false`), plus whatever
  tuning knobs the implementation needs (e.g. `max_tool_result_age_turns`,
  `max_assistant_tail_turns`).
- `config-schema.json` — matching `compression` object with an explicit
  property list (mirror the `additionalProperties: false` convention used
  elsewhere in this schema, e.g. `events.otel`).

## Acceptance Criteria

- Heuristic compressor hits the **3–6× range** on the locked 10-trace
  `general-task` set.
- Gate (`compression.heuristic_underperforms`) flips correctly when the
  heuristic falls below 0.5× of LLMLingua's measured ratio on the same
  set (verified via the one-time offline benchmark comparator, not a
  runtime dependency).
- `compression.heuristic_underperforms` defaults to `false` and
  round-trips through `.ll/ll-config.json` / `config-schema.json`.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: heuristic compressor (3 passes), ≥8K-token hook in
  `fsm/runners.py`, locked 10-trace benchmark set, config gate wiring,
  one-time offline LLMLingua comparator run for calibration.
- **Out**: shipping the real LLMLingua pip dependency as a runtime
  consumer (only the gate/toggle is in scope — file a follow-on if the
  benchmark shows the gate needs to flip); any `cache_control` marking
  (tracked under the separate, not-yet-filed F1 child — this issue only
  flags candidates).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Children Tier 3 [TBD-13], Goal #9 |
| `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` | EPIC-CHILD-8 spec detail, LLMLingua gating rationale |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier 3 prioritization, F4 benchmark open question (#3) |
| ENH-2486 | Existing `fsm/runners.py` prompt-size guard — confirm exact hook point before duplicating |

## Impact

- **Priority**: P2 — high-leverage, compounds on every large-prompt FSM
  iteration, but not blocking (no production user currently blocked).
- **Effort**: Medium — ~150 LOC + benchmark harness + trace-set curation.
- **Risk**: Low — zero pip deps for the shipped path; well-trodden
  extractive-compression pattern; LLMLingua itself stays opt-in.
- **Breaking Change**: No — additive; default behavior for prompts <8K
  tokens unchanged.

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-11T00:00:00Z - filed from EPIC-2456 § Children [TBD-13] per `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` (EPIC-CHILD-8) and `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` (Tier 3).

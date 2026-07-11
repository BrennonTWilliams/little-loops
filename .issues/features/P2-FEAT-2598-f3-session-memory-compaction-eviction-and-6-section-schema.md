---
id: FEAT-2598
title: "F3 — Session-memory compaction: StreamingLLM eviction + 6-section schema"
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
  - compaction
  - tier-3
decision_needed: false
---

# FEAT-2598: F3 — Session-memory compaction

## Summary

Add a session-memory compaction module combining two complementary passes:
(a) a **StreamingLLM sink-and-window eviction** pass — instant, structural,
keep the first-N sink *messages* + the recent window, drop the middle
(~80 LOC) — and (b) the cookbook's **6-section semantic summarization
schema** (User Intent / Completed Work / Errors & Corrections / Active Work
/ Pending Tasks / Key References), which fires in a background thread once
the soft threshold (7,500 tokens) is crossed. This is EPIC-2456 § Children
[TBD-12] — directly serves Goal #4 in the EPIC.

This is **not** a greenfield build: it extends the existing LCM compaction
surface already in the tree (`session_store._compact_session_conn` +
the `summary_nodes` SQL schema, `session_store.py:1747+`), reuses
ENH-1954's cross-session condensation, and reuses the existing
`history.compaction` config (4096-token budget) — no new config keys are
needed for the base mechanism.

## Motivation

Long-running FSM loops and `ll-parallel` sessions accumulate context that
gets re-embedded into every subsequent prompt. Eviction handles the
hard-limit swap-in instantly (lossless-enough structural pass); semantic
summarization catches up in the background at the soft threshold so the
two together keep long sessions cheap without stalling on synchronous
summarization. Vendor-measured cookbook anchors (`session_memory_compaction.ipynb`,
`automatic-context-compaction.ipynb`) show **88% reduction (12,847 → 1,526
tokens)** as the semantic-summarization upper bound and **58.6% (122,392
tokens saved)** on a 5-ticket workflow — those are cited as context for how
large the lever is, not as this issue's bar; see Acceptance Criteria for
the actual target.

## Current Behavior

- `session_store._compact_session_conn` and the `summary_nodes` SQL schema
  (`session_store.py:1747+`) already implement cross-session condensation
  (ENH-1954) at the existing 4096-token `history.compaction` budget
  boundary.
- No instant structural eviction pass exists — compaction is
  summarization-only today, which means a hard-limit hit has no fast
  fallback while summarization catches up.
- No 6-section schema (User Intent / Completed Work / Errors & Corrections
  / Active Work / Pending Tasks / Key References) — existing summaries use
  whatever shape ENH-1954 produces.

## Expected Behavior

- A new `compaction/instant.py` module exposes both passes:
  - **Eviction**: keeps the first-N sink *messages* (not tokens — this
    project operates at message granularity, not KV-cache granularity)
    plus the most recent window; drops the middle. Must preserve
    system/CLAUDE.md blocks unconditionally.
  - **Semantic summarization**: fires in a background thread once the
    soft threshold (7,500 tokens) is crossed; produces a summary in the
    6-section schema.
- A new `compaction/result.py` module exposes `CompactResult` — a thin
  Python dataclass wrapper (`summary_message`, `compacted_messages`,
  `summary_text`, `context_token_estimate`) over the *existing*
  `summary_nodes` SQL rows. No schema change.
- A new skill `skills/ll-compact-session/SKILL.md` lets a user manually
  trigger compaction on the current session.
- Eviction+summarization together land in the 50–70% context-size
  reduction range on a locked trace set (see Acceptance Criteria) without
  measurable quality regression on a held-out eval set.

## Proposed Solution

1. **`scripts/little_loops/compaction/instant.py`** (new, ~270 LOC):
   - `evict_sink_and_window(messages, sink_n, window_n)` — the
     StreamingLLM-style structural pass (~80 LOC); message-granularity,
     preserves system/CLAUDE.md blocks by construction (never evicted).
   - Letta-style sliding-window selection for the semantic pass (~150
     LOC): `goal_tokens = (1 - sliding_window_percentage) × context_window`,
     an `is_valid_cutoff` predicate adapted to this project's
     chunk-grouping boundaries, `APPROX_TOKEN_SAFETY_MARGIN = 1.3`
     byte/4 heuristic, monotonic-update path that reuses ENH-1954's
     cross-session condensation.
   - `summarize_6_section(messages) -> str` — background-thread
     summarizer producing the cookbook schema.
2. **`scripts/little_loops/compaction/result.py`** (new, ~50 LOC):
   - `CompactResult(summary_message, compacted_messages, summary_text,
     context_token_estimate)` dataclass, populated from existing
     `summary_nodes` rows via `session_store._compact_session_conn`.
3. **`skills/ll-compact-session/SKILL.md`** (new): manual-trigger skill
   invoking the same compaction path used automatically at the soft
   threshold.
4. Wire the soft-threshold trigger (7,500 tokens) into whichever call
   site currently invokes `session_store._compact_session_conn` at the
   4096-token cross-session boundary — confirm during implementation
   whether that's a shared entry point or needs a new one.

## Integration Map

### Files to Modify

- `scripts/little_loops/compaction/instant.py` (new)
- `scripts/little_loops/compaction/result.py` (new)
- `scripts/little_loops/session_store.py` — verify/extend
  `_compact_session_conn` call sites to invoke the new eviction pass
  ahead of (or alongside) existing summarization

### Dependent Files (Callers/Importers)

- The not-yet-filed F8 child (EPIC-2456 § Children Tier 3, subagent
  handoff compaction) will import `compaction/instant.py` from a new
  `subagents/handoff.py` — this issue's module is a hard dependency for
  that future work; no action needed here beyond keeping the module's
  public surface stable.

### Similar Patterns

- `session_store._compact_session_conn` + `summary_nodes` schema
  (`session_store.py:1747+`) — the existing LCM compaction surface this
  issue extends, not replaces.
- ENH-1954 — cross-session condensation; the monotonic-update path in
  the sliding-window selector should reuse this rather than duplicate it.

### Tests

- `scripts/tests/test_compaction.py` (new) — eviction preserves
  system/CLAUDE.md blocks (regression test); soft/hard threshold
  triggers; 6-section schema shape; 50–70% reduction range on the
  locked trace set.

### Documentation

- `docs/ARCHITECTURE.md` — "Token cost layer" section (shared across
  EPIC-2456 children).
- `docs/reference/API.md` — document `compaction/instant.py` +
  `compaction/result.py`.

### Configuration

- N/A — reuses existing `history.compaction` config (4096-token budget);
  no new config keys required for the base mechanism.

## Acceptance Criteria

- Compaction triggers at the configured soft threshold (default 7,500
  tokens).
- Eviction preserves system/CLAUDE.md blocks — covered by a regression
  test.
- The eviction+summarization combo reduces context size to the **50–70%
  range** on a locked trace set, without measurable quality regression on
  a held-out eval set. (The cookbook's 88% figure is the
  semantic-summarization upper bound, reserved for a possible future
  upgrade — not this issue's bar.)
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: instant eviction pass, 6-section semantic summarization,
  `CompactResult` wrapper, manual-trigger skill.
- **Out**: subagent handoff compaction (future F8 child — will import
  this module but is filed separately); parent-prefix cache hoisting
  (also future F8 scope); any change to `cache_control` (Claude-only
  primitive, tracked under the separate not-yet-filed F1 child).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Children Tier 3 [TBD-12], Goal #4 |
| `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` | EPIC-CHILD-6 spec detail (sliding-window algorithm, module layout) |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier 3 prioritization rationale, vendor-measured anchors |
| ENH-2486 | Adjacent `fsm/runners.py` prompt-assembly leverage point (not a blocking dependency) |

## Impact

- **Priority**: P2 — high-leverage, compounds across every long-running
  loop/session, but no current production user is blocked on its absence.
- **Effort**: Medium — ~320 LOC (270 instant.py + 50 result.py), builds on
  existing LCM surface rather than net-new infrastructure.
- **Risk**: Low — well-trodden pattern (eviction + summarization); no new
  pip deps; no schema change.
- **Breaking Change**: No — additive; existing compaction behavior
  unchanged unless the new soft-threshold trigger is wired in as a strict
  addition ahead of the existing summarization-only path.

## Status

**Open** | Created: 2026-07-11 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-11T00:00:00Z - filed from EPIC-2456 § Children [TBD-12] per `thoughts/plans/2026-07-02-token-cost-reduction-architecture.md` (EPIC-CHILD-6) and `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` (Tier 3).

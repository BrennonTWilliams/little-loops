---
id: FEAT-2747
type: FEAT
title: Assistant-inclusive session compaction (message_events + assistant_messages)
priority: P3
status: open
parent: FEAT-2711
discovered_by: confidence-check
discovered_date: '2026-07-22'
labels:
- token-cost
- fsm
- session-store
relates_to:
- FEAT-2711
- FEAT-2598
size: Small
---

# FEAT-2747: Assistant-inclusive session compaction (message_events + assistant_messages)

## Summary

A new assistant-inclusive compaction function (joins `message_events` and
`assistant_messages`, extending `session_store.py`'s `compact_session()`/
`compact_result_for_session()` at line 3444 / `compaction/result.py:34`).
Carved out of FEAT-2711 so the new mechanism can be built and proven in
isolation before FEAT-2711 wires it into the FSM state chain.

## Motivation

FEAT-2711's spike (`scripts/tests/spike/fsm_continuity_compaction/`,
`/ll:spike` 2026-07-21) found that `compact_session()` reads only
`message_events` — populated exclusively from `type == "user"` JSONL records
by `_backfill_messages`. The assistant's derived understanding (file reads,
analysis, decisions) lives in a separate `assistant_messages` table that
`_compact_session_conn()` never queries. For a single FSM prompt-state
invocation, the "user" turn is just the already-known interpolated prompt —
the state's *new* information is entirely in the assistant turn.

**Used unmodified, `compact_session()`/`compact_result_for_session()` would
summarize the prompt already sent, not the reasoning a caller wants carried
forward.** This issue closes that gap independently of any FSM-side caller,
so FEAT-2711 can consume a proven primitive instead of building a novel
mechanism inline.

## Current Behavior

`compact_session()`/`compact_result_for_session()`
(`scripts/little_loops/session_store.py:3444`,
`scripts/little_loops/compaction/result.py:34`) summarize only user turns
(`message_events`), never `assistant_messages`.

## Expected Behavior

A new function — exact name/signature TBD by the implementer (e.g.
`compact_session_with_reasoning()`) — joins `message_events` and
`assistant_messages` and produces a summary that includes the assistant's
derived reasoning from the session, not just the prompt that was sent. The
function is callable standalone, with no dependency on FSM-layer wiring.

## Proposed Solution

Extend `scripts/little_loops/session_store.py` (near `compact_session()` at
line 3444) and/or `scripts/little_loops/compaction/result.py` (near
`compact_result_for_session()` at line 34) with the new function. Reuse the
existing LCM 3-level escalation machinery already in place rather than
reimplementing summarization from scratch — only the source query (which
tables it joins) needs to change.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` (near `compact_session()`,
  line 3444) — add the new query joining `message_events` and
  `assistant_messages` for a given session ID.
- `scripts/little_loops/compaction/result.py` (near
  `compact_result_for_session()`, line 34) — add the assistant-inclusive
  counterpart that calls the new query and produces a `summary_text` result
  via the existing LCM escalation path.

### Dependent Files (Callers/Importers)
- None today — this is new, standalone functionality. FEAT-2711 will become
  the first caller once it lands (`blocked_by: [FEAT-2747]` on FEAT-2711).

### Similar Patterns
- The existing `compact_session()`/`compact_result_for_session()`
  implementations — same file, same module, same tested LCM escalation path.
  This issue is a sibling function, not a new subsystem.

### Tests
- Promote the spike's
  `TestSummaryOmitsAssistantContent::test_compact_summary_omits_assistant_derived_content`
  (currently in `scripts/tests/spike/fsm_continuity_compaction/`) as the
  regression baseline proving the *old* gap.
- Add a new `test_compact_includes_assistant_derived_content`-style test
  proving the *new* function closes it.
- Reuse the existing regression fixture set referenced in FEAT-2711's Spike
  Results (`test_compaction.py`: 18 passed; `test_session_store.py -k
  "backfill or compact"`: 66 passed) to confirm no regression in the
  unmodified `compact_session()`/`compact_result_for_session()` callers.

### Documentation
- None required at this scope — this is an internal `session_store.py`/
  `compaction/` addition with no external-facing behavior change until
  FEAT-2711 wires a caller.

## Implementation Steps

1. Design the join query: `message_events` + `assistant_messages` keyed by
   session ID, in chronological order.
2. Implement the new compaction function, reusing the existing LCM
   escalation path from `compact_session()`/`compact_result_for_session()`.
3. Promote the spike's
   `test_compact_summary_omits_assistant_derived_content` test as the
   regression baseline for the old gap.
4. Add a new test proving the new function includes assistant-derived
   content.
5. Run the full `test_compaction.py` and `test_session_store.py -k
   "backfill or compact"` suites to verify no regression in existing
   `compact_session()` callers.

## Acceptance Criteria

- [ ] New function joins `message_events` and `assistant_messages` and the
      resulting summary includes assistant-derived content (proven by a
      test, not just manual inspection).
- [ ] Existing `compact_session()`/`compact_result_for_session()` callers
      and tests are unaffected (no signature break).
- [ ] Function is usable standalone (no FSM-layer dependency) so FEAT-2711
      can call it once unblocked.

## Impact

- **Priority**: P3 — matches parent FEAT-2711's priority; blocks it.
- **Effort**: Small — isolated to `session_store.py`/`compaction/result.py`,
  well-scoped by the FEAT-2711 spike (mechanics already proven: synchronous
  backfill-then-compact has no race, `session_id` capture works).
- **Risk**: Low — new query + summarization path, no existing callers to
  break, spike already retired the feasibility risks.

## Session Log
- Decomposed from FEAT-2711 on 2026-07-22 by `/ll:confidence-check` follow-up
  (outcome-confidence mitigation for FEAT-2711's Complexity risk).

---

## Status

**Open** | Created: 2026-07-22 | Priority: P3

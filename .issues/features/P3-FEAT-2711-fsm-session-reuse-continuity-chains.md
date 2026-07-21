---
id: FEAT-2711
type: FEAT
title: FSM session reuse for continuity-of-reasoning state chains
priority: P3
status: open
captured_at: "2026-07-21T02:03:13Z"
discovered_date: "2026-07-21"
discovered_by: capture-issue
parent: EPIC-2456
labels: [token-cost, fsm, orchestration]
relates_to: [EPIC-2456, FEAT-2598, ENH-2486, ENH-2714]
---

# FEAT-2711: FSM session reuse for continuity-of-reasoning state chains

## Summary

Every `HostRunner` adapter already implements a `resume` parameter
(`claude --continue`, `codex exec resume --last`, `gemini --resume latest`),
but `fsm/runners.py` never uses it — every FSM state spawns a fresh host
invocation. Add an opt-in per-state-chain `session_mode: continue` that threads
`resume=True` through the runner **for sequential reasoning chains where state
N+1 genuinely benefits from state N's working context** (e.g. plan → implement
on the same issue), saving the cost of re-deriving understanding, not just the
static prefix.

**Re-scoped 2026-07-20**: prefix-cost reduction is no longer this issue's
justification — that lever moved to ENH-2714 (static-prefix pruning), which
achieves it without breaking state isolation. This issue is now narrowly about
continuity of *reasoning*: chains where a fresh state would have to re-read the
codebase/plan to rebuild context the previous state already holds. If no builtin
loop has a chain where that re-derivation cost is demonstrably significant,
close this instead of implementing it.

## Motivation

For a plan → implement → self-review chain on one issue, a fresh session per
state re-reads the same files and re-derives the same understanding each time.
Resume keeps that working context (and the warm cache prefix) alive, sending
only the new state prompt as the next turn. This is a different saving from
ENH-2714's: it scales with task complexity, not catalog size.

Counterweights (why this is opt-in and narrow):
- Continued sessions re-read a growing transcript each turn — per-state input
  cost rises over the chain; savings decay as the chain lengthens.
- State isolation is the FSM's design point. Evaluator states
  (`check_semantic`/`llm_structured`) seeing prior conversation breaks
  MR-1-style independence; they must default to `fresh`.

## Current Behavior

`fsm/runners.py` calls `build_streaming(...)` with no `resume`; each state is an
independent conversation.

## Expected Behavior

With `session_mode: continue` set on a state chain, state N+1 resumes the
session started by state N. Default `fresh` everywhere, preserving current
behavior exactly.

## Proposed Solution

- Loop-YAML key `session_mode: fresh | continue` (default `fresh`); per-state
  override so evaluator/judge states in a continued chain force `fresh`.
- `fsm/runners.py` passes `resume=True` on non-first invocations when
  `continue` is active; reset to fresh on handoff/spawn boundaries and on
  host-CLI 429 retry (see `reference_fsm_rate_limit_exit_code` — don't mask
  exit codes).
- Guard: wire ENH-2486's per-invocation prompt-size guard to force a fresh
  session (or trigger compaction) when the continued session's context exceeds
  threshold.
- Validation: warn when an evaluator (`check_semantic`/`llm_structured`) state
  inherits `continue`.

## Implementation Steps

0. **Gate**: identify a concrete builtin-loop chain (e.g. rn-implement's
   plan → implement states) and estimate the re-derivation cost a continued
   session would avoid, from a locked trace. If not significant, close as
   superseded by ENH-2714.
1. Schema: `session_mode` in `fsm/schema.py` + evaluator-inheritance warning.
2. Wiring in `fsm/runners.py` / `fsm/executor.py`; reset on handoff, error, and
   retry paths.
3. ENH-2486 guard integration (size threshold → fresh/compact).
4. Tests: state-sequence resume flag assertions; reset-on-retry regression;
   before/after total-token measurement on the locked chain trace.

## Acceptance Criteria

- [ ] Gate (step 0) documented in this issue: named chain + estimated
      re-derivation saving, or issue closed as superseded.
- [ ] `session_mode: continue` threads `resume=True` from state 2 onward on the
      Claude host; default behavior unchanged.
- [ ] Session resets on handoff/spawn, on hard errors, and per-state
      `session_mode: fresh` override.
- [ ] Validation warns when an evaluator state runs in continued mode.
- [ ] Measured total-token (not just prefix) delta on the locked chain trace
      recorded before close.

## Impact

- **Priority**: P3 — demoted from P2; ENH-2714 took the default savings lever.
  Value now contingent on the step-0 gate.
- **Effort**: Small-Medium (~80–120 LOC + tests) after the gate.
- **Risk**: Medium — changes state-isolation semantics; mitigated by opt-in
  default, evaluator warnings, and the narrowed scope.

## Session Log
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`
- Re-scoped 2026-07-20: narrowed to continuity-of-reasoning chains; prefix-cost
  justification moved to ENH-2714; added step-0 viability gate; demoted P2→P3.

---

## Status

**Open** | Created: 2026-07-21 | Priority: P3

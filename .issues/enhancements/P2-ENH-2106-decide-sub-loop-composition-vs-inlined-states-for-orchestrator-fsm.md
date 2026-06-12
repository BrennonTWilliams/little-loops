---
id: ENH-2106
title: "Decide: reusable sub-loop composition vs inlined per-issue states for orchestrator FSM Layers 1+2"
type: ENH
priority: P2
status: open
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1867
relates_to: [FEAT-2000, FEAT-1899]
blocks: [FEAT-2000, FEAT-1899]
labels:
  - fsm
  - orchestration
  - decision
  - spike
---

# ENH-2106: Decide: reusable sub-loop composition vs inlined per-issue states for orchestrator FSM Layers 1+2

## Summary

Resolve Open Question 1 of the orchestrator decomposition plan
(`docs/research/ll-orchestrator-decomposition-plan-v0.2.md`): should the
per-issue processing states (claim → implement → verify → complete/fail) be
extracted into a reusable sub-loop that both Layer 1 (`loops/ll-auto.yaml`,
FEAT-2000) and Layer 2 (the ll-sprint FSM, FEAT-1899) compose, or should each
layer inline its own copy of those states?

## Motivation

This design decision directly shapes how FEAT-2000 and FEAT-1899 are
authored. If it is unresolved when authoring begins, FEAT-1899 will likely
duplicate FEAT-2000's states, and converging later means rewriting one or
both loops. Deciding first is a small spike; deciding later is a refactor.

## Acceptance Criteria

- [ ] Evidence gathered: current sub-loop/fragment composition support in the
  FSM runner (`loops/lib/` fragments, any `sub_loop`/include mechanism) and
  its limitations
- [ ] Decision recorded in `.ll/decisions.yaml` via `ll-issues decisions add`
  (type=decision, category=architecture, issue=EPIC-1867) with rationale and
  rejected alternative
- [ ] FEAT-2000 and FEAT-1899 issue bodies annotated with the decision so
  authoring follows it
- [ ] If composition is chosen: the shared state fragment's home
  (`loops/lib/...`) is named in the decision

## Integration Map

### Files to Read
- `docs/research/ll-orchestrator-decomposition-plan-v0.2.md` — Open Question 1
  and the reference FSM YAML
- `scripts/little_loops/fsm/` — existing composition/fragment mechanics
- `loops/lib/` — fragment conventions

### Files to Modify
- `.ll/decisions.yaml` (via CLI)
- `.issues/features/*FEAT-2000*.md`, `.issues/features/*FEAT-1899*.md` —
  decision annotations

## Impact

- **Priority**: P2 — gates authoring of FEAT-2000 and FEAT-1899
- **Effort**: Small — research + decision record, no implementation
- **Risk**: Low — decision-only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-12 | Priority: P2

---
id: FEAT-1899
title: Implement ll-sprint FSM wave driver and shim
type: FEAT
priority: P3
status: open
captured_at: 2026-06-03T19:12:39Z
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to: [FEAT-1901, FEAT-1902]
---

# FEAT-1899: Implement ll-sprint FSM wave driver and shim

## Summary

Convert `ll-sprint` into an FSM wave driver that reuses the Layer-1 per-issue
states for sequential orchestration and delegates to `ParallelOrchestrator` for
parallel waves. Deliverables:

- `ll-sprint plan --json` subcommand emitting an ordered wave definition (list of
  waves, each with issue IDs and execution mode: `sequential` or `parallel`).
- An FSM wave driver (`loops/ll-sprint.yaml` or equivalent) that iterates over
  wave definitions, dispatches single/contention sub-waves to the Layer-1 per-issue
  states, and shells out to `ParallelOrchestrator` for multi-issue waves.
- Convert `ll-sprint` CLI to a thin shim over the FSM driver.
- Pass `ll-loop validate ll-sprint` (MR-1/MR-3).

Depends on FEAT-1897 (Layer 0 CLI subcommands) and FEAT-1898 (Layer-1 per-issue states to reuse).

## Impact

- **Priority**: P3 — builds on Layer 1; delivers wave-level orchestration
- **Effort**: Medium — wave driver logic + plan subcommand + shim
- **Risk**: Medium — wave dispatch logic is new; parallel delegation to ParallelOrchestrator is well-understood
- **Breaking Change**: No (shim preserves CLI interface)

## Status

**Open** | Created: 2026-06-03 | Priority: P3

## Session Log
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`

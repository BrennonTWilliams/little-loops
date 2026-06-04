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
blocked_by: [FEAT-1901, FEAT-1902]
labels: [feature, orchestration, fsm, sprint]
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

Depends on FEAT-1901 (Layer 0 CLI subcommands) and FEAT-1902 (Layer-1 per-issue states to reuse).

## Use Case

**Who**: Developer running `ll-sprint` to execute a curated set of issues with dependency-aware ordering.

**Context**: After Layer-1 per-issue states (FEAT-1902) are available, the sprint orchestrator needs a structured wave driver — dispatching sequential single-issue sub-waves and delegating parallel batches to `ParallelOrchestrator` — rather than embedding orchestration logic directly in the CLI.

**Goal**: Run `ll-sprint execute` and have dependency-ordered waves driven by a validated FSM loop that reuses Layer-1 states, with parallel batches automatically delegated to `ParallelOrchestrator`.

**Outcome**: `ll-sprint` becomes a thin shim over `loops/ll-sprint.yaml`; the FSM wave driver passes `ll-loop validate` (MR-1/MR-3).

## Current Behavior

`ll-sprint` is a standalone CLI that executes curated issue sets sequentially with dependency-aware ordering. It does not emit structured wave definitions, does not use an FSM wave driver, and does not delegate parallel waves to `ParallelOrchestrator`. All orchestration logic lives directly in the CLI rather than in a validated loop.

## Expected Behavior

- `ll-sprint plan --json` emits an ordered list of waves: `[{"wave": N, "issues": [...], "mode": "sequential|parallel"}, ...]`.
- An FSM wave driver (`loops/ll-sprint.yaml`) iterates over wave definitions, dispatches single/contention sub-waves to Layer-1 per-issue states, and delegates multi-issue parallel waves to `ParallelOrchestrator`.
- `ll-sprint execute` becomes a thin shim that invokes `ll-loop run ll-sprint`.
- `ll-loop validate ll-sprint` passes (MR-1 and MR-3 compliant).

## Motivation

This feature completes the EPIC-1867 FSM decomposition at the sprint/wave level:
- Reuses Layer-1 per-issue states (FEAT-1902) rather than duplicating per-issue orchestration logic in `ll-sprint`.
- Enables `ll-loop validate` enforcement of meta-loop rules (MR-1/MR-3) on sprint execution.
- Reduces `ll-sprint` to a thin shim, concentrating wave dispatch logic in a structured, testable FSM.
- Unlocks parallel wave delegation to `ParallelOrchestrator` in a validated, observable way.

## Acceptance Criteria

- [ ] `ll-sprint plan --json` emits a valid ordered wave definition (list of waves with `issue_ids` and `mode: sequential|parallel`).
- [ ] `loops/ll-sprint.yaml` FSM wave driver iterates over wave definitions and routes correctly to sequential vs. parallel dispatch states.
- [ ] Sequential/contention sub-waves delegate to Layer-1 per-issue states from FEAT-1902.
- [ ] Parallel waves shell out to `ParallelOrchestrator`.
- [ ] `ll-sprint execute` is a thin shim — no duplicated orchestration logic in the CLI.
- [ ] `ll-loop validate ll-sprint` passes (MR-1 and MR-3).
- [ ] Existing `ll-sprint` CLI interface is preserved (no breaking changes to argument surface).

## Proposed Solution

**Step 1 — Add `ll-sprint plan --json`**: Extend `scripts/little_loops/sprint.py` with a `plan` subcommand that reads the sprint definition, resolves dependency order, and emits a JSON wave list.

**Step 2 — Author `loops/ll-sprint.yaml`** following the meta-loop diagnosis-first shape (CLAUDE.md § Loop Authoring):
- States: `load_plan` → `dispatch_wave` → `run_sequential` / `delegate_parallel` → `check_wave_complete` → `done`.
- `dispatch_wave` routes on `mode` field from the wave definition.
- `run_sequential` invokes Layer-1 per-issue FSM states from FEAT-1902.
- `delegate_parallel` shells out to `ParallelOrchestrator`.
- Every LLM-structured state paired with a non-LLM evaluator (`exit_code` or `convergence`) — MR-1.
- All intermediate artifacts written under `${context.run_dir}/` — MR-3.

**Step 3 — Shim `ll-sprint execute`**: Replace orchestration logic with `ll-loop run ll-sprint --args <wave-plan-path>`.

**Step 4 — Validate**: `ll-loop validate ll-sprint`; fix any MR-1/MR-3 violations.

## API/Interface

```
# New subcommand
ll-sprint plan --json [--sprint <name>]

# Output schema
[
  {"wave": 1, "issues": ["FEAT-001"], "mode": "sequential"},
  {"wave": 2, "issues": ["FEAT-002", "FEAT-003"], "mode": "parallel"},
  ...
]

# Thin shim (internal)
ll-sprint execute → ll-loop run ll-sprint --args <wave-plan>
```

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint.py` — add `plan --json` subcommand; refactor `execute` to thin shim
- `loops/ll-sprint.yaml` — new FSM wave driver (create)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel_orchestrator.py` — invoked by `delegate_parallel` state
- FEAT-1902 Layer-1 per-issue loop YAML — referenced by `run_sequential` state
- `ll-sprint` CLI entry point (`scripts/little_loops/__main__.py` or equivalent)

### Similar Patterns
- Existing loop YAMLs in `loops/` — structural reference for FSM state design
- CLAUDE.md § Loop Authoring — meta-loop rules (diagnosis-first, MR-1, MR-3)
- `scripts/little_loops/parallel_orchestrator.py` — delegation interface to understand

### Tests
- `scripts/tests/test_sprint.py` (or equivalent) — add tests for `plan --json` subcommand output schema
- Integration test: verify `ll-sprint plan --json` emits valid wave list; verify shim invokes FSM driver

### Documentation
- `docs/guides/` — update sprint usage guide to reflect FSM-backed execution
- `docs/reference/API.md` — document `plan --json` subcommand

### Configuration
- N/A — uses existing sprint config in `.ll/ll-config.json`; no new keys required

## Implementation Steps

1. Add `ll-sprint plan --json` subcommand to emit ordered wave definitions.
2. Author `loops/ll-sprint.yaml` FSM wave driver with `load_plan`, `dispatch_wave`, `run_sequential`, `delegate_parallel`, `check_wave_complete`, `done` states.
3. Wire Layer-1 per-issue states (FEAT-1902) into `run_sequential` state.
4. Wire `ParallelOrchestrator` into `delegate_parallel` state.
5. Refactor `ll-sprint execute` to thin shim invoking `ll-loop run ll-sprint`.
6. Run `ll-loop validate ll-sprint`; resolve any MR-1/MR-3 violations.
7. Run existing `ll-sprint` tests; verify CLI interface is preserved.

## Impact

- **Priority**: P3 — builds on Layer 1; delivers wave-level orchestration
- **Effort**: Medium — wave driver logic + plan subcommand + shim
- **Risk**: Medium — wave dispatch logic is new; parallel delegation to ParallelOrchestrator is well-understood
- **Breaking Change**: No (shim preserves CLI interface)

## Status

**Open** | Created: 2026-06-03 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `ll-sprint execute` shim follows the canonical thin-shim pattern established by FEAT-1902 (`<cli> → ll-loop run <loop>`). Coordinate shim implementation approach with FEAT-1902 to avoid divergent patterns.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-04T19:54:00 - `2f12f6ef-94a2-4725-933e-626b1ef4cdff.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:47:17 - `6dbe3977-0d8f-47aa-b338-9f0b66da4be5.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:45 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T19:23:35 - `1f79d2d5-df37-42dc-a0f8-73e20acc795b.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`

---
id: EPIC-1962
type: EPIC
priority: P2
status: open
captured_at: "2026-06-05T18:20:28Z"
discovered_date: 2026-06-05
discovered_by: scope-epic
relates_to: [ENH-1958, ENH-1959, BUG-1960, ENH-1961]
---

# EPIC-1962: Hardening FSM Loop Checkpoint & Capture Safety

## Summary

Prevent FSM loops from silently corrupting state and crashing when capture states are bypassed, through a layered defense: structural fix for cross-run state corruption (BUG-1960), task fingerprinting primitive (ENH-1959), runtime safety net for missing captures (ENH-1958), and validation-time detection of capture gaps (ENH-1961). All four issues were discovered from a single 2026-06-05 incident where `general-task.yaml` terminated after 6 iterations with zero productive work due to a stale checkpoint from an unrelated prior task.

## Motivation

The `general-task.yaml` loop — the most-copied loop template in the project — is vulnerable to a class of failures where checkpoints from prior runs silently corrupt current runs, leading to terminal crashes. The root cause spans four compounding gaps:

1. **No per-run isolation** (BUG-1960): All artifacts written to shared `.loops/tmp/`
2. **No task identity** (ENH-1959): No way to tell which task a checkpoint belongs to
3. **No safe degradation** (ENH-1958): Missing captures cause unrecoverable `InterpolationError` crashes
4. **No authoring-time detection** (ENH-1961): Validator can't flag unreachable capture references

Fixing all four layers transforms the failure mode from "silent corruption → terminal crash" to "detected mismatch → clean restart → graceful degradation."

## Goal

FSM loops survive checkpoint corruption, missing captures, and routing edge cases without terminating. Loop authors can opt into safe interpolation, the runner provides task fingerprinting, built-in loops use per-run directories, and the validator catches capture gaps at authoring time.

## Scope

### In Scope
- Injecting `${context.input_hash}` into every loop run (ENH-1959)
- Migrating `general-task.yaml` from `.loops/tmp/` to `${context.run_dir}/` (BUG-1960)
- Adding `:default=` and `?` fallback syntax to `${...}` interpolation (ENH-1958)
- Adding capture reachability analysis to `ll-loop validate` (ENH-1961)
- Regression tests for each layer

### Out of Scope
- Broader `.loops/tmp/` audit beyond `general-task.yaml` — other loops using `.loops/tmp/` are separate bugs
- Changes to `$${...}` escape sequences — untouched by ENH-1958
- Sub-loop capture reachability — ENH-1961 is scoped to same-loop references only
- Backfilling `input_hash` into historical loop runs or session logs

## Children

- **ENH-1959** — Auto-inject `input_hash` into FSM loop context for checkpoint fingerprinting
- **BUG-1960** — `general-task.yaml` uses shared `.loops/tmp/` paths causing cross-run state corruption
- **ENH-1958** — Add safe/fallback interpolation syntax for missing captured variables
- **ENH-1961** — Static validation of captured variable reachability in FSM validator

## Success Metrics

- **Zero cross-run contamination**: `general-task.yaml` survives a prior-run stale checkpoint without false `RESUME_SKIP`
- **Zero silent crashes**: Missing captures with `:default=` or `?` suffix resolve to fallback instead of `InterpolationError`
- **Validation catch**: `ll-loop validate` warns on the `check_done → selected_step.output` pattern that caused BUG-1960
- **Adoption**: `general-task.yaml` uses `${context.input_hash}` and `${context.run_dir}/` for all artifacts
- **No regressions**: All existing FSM tests pass without modification

## Integration Map

### Files to Modify (across all children)
- `scripts/little_loops/cli/loop/run.py` — ENH-1959 (inject `input_hash`)
- `scripts/little_loops/fsm/schema.py` — ENH-1959 (add to `RUNNER_INJECTED`)
- `scripts/little_loops/fsm/interpolation.py` — ENH-1958 (add `:default=` and `?` syntax)
- `scripts/little_loops/fsm/validation.py` — ENH-1961 (add capture reachability analysis)
- `scripts/little_loops/loops/general-task.yaml` — BUG-1960 (migrate to `run_dir`)

### Tests
- `scripts/tests/test_fsm_interpolation.py` — ENH-1958
- `scripts/tests/test_ll_loop_execution.py` — ENH-1959
- `scripts/tests/test_fsm_executor.py` — ENH-1959
- `scripts/tests/test_general_task_loop.py` — BUG-1960
- `scripts/tests/test_fsm_validation.py` — ENH-1961
- `scripts/tests/test_builtin_loops.py` — BUG-1960 (validate still parses)

### Documentation
- `docs/generalized-fsm-loop.md` — ENH-1958 (safe syntax), ENH-1959 (`input_hash`)
- `docs/guides/LOOPS_GUIDE.md` — ENH-1958 (safe interpolation examples), ENH-1959 (fingerprinting example)
- `docs/reference/API.md` — ENH-1958 (interpolation code samples)

## Impact

- **Priority**: P2 — Causes silent cross-run state corruption and unrecoverable loop termination; fixes span the most-copied loop template
- **Effort**: Medium — ~100-150 lines of code + tests + docs across 4 issues; ENH-1959 is trivial (~5 lines), others are ~30-50 lines each
- **Risk**: Low — all changes are additive or opt-in; no breaking changes to existing loop YAMLs or APIs
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`epic`, `fsm`, `loops`, `checkpoint`, `interpolation`, `validation`, `safety`

## Status

**Open** | Created: 2026-06-05 | Priority: P2

## Session Log
- `/ll:scope-epic` - 2026-06-05T18:20:28Z - `2338d4d4-9de8-4056-a8d3-959258c258b7.jsonl`

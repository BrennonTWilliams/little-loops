---
id: ENH-1726
type: ENH
priority: P3
status: open
discovered_date: 2026-05-26
discovered_by: capture-issue
captured_at: '2026-05-26T20:24:33Z'
decision_needed: false
relates_to: [ENH-1684]
---

# ENH-1726: Unify FSM loop run artifacts into a per-run directory under `.loops/runs/`

## Summary

Domain artifacts produced by FSM loops (research files, plans, generated content) are currently scattered across loop-specific subdirectories (`.loops/research/`, `.loops/plans/`, etc.) with no consistent naming or isolation across runs. Standardize all loop run artifact output into a unified per-run subdirectory — `.loops/runs/{loop-name}-{timestamp}/` — so every run's artifacts are co-located, comparable, and independently cleanable.

## Current Behavior

Each loop hardcodes its own `output_dir` in `context` (e.g., `context.output_dir: .loops/research`). Re-running the same loop deposits artifacts into the same directory, potentially overwriting prior runs (the immediate data-loss bug addressed by ENH-1684). There is no standard path or variable a loop author can use to get a fresh, isolated directory per invocation.

The FSM does already provide per-run isolation for its own internal state (`.loops/.running/` for live state and `.loops/.history/<run_id>-<loop_name>/` after archival), but domain artifacts are not co-located with that FSM state.

## Expected Behavior

- The `ll-loop` runner injects a `run_dir` template variable into every loop's context at startup, set to `.loops/runs/{loop-name}-{YYYYMMDDTHHMMSS}/`.
- Loop YAML authors use `${context.run_dir}` instead of a hardcoded `output_dir` to write their domain artifacts.
- Each invocation creates a new, isolated directory:
  ```
  .loops/runs/deep-research-20260526T143022/
    report.md
    knowledge-base.md
    coverage.md
    query-log.md
  .loops/runs/deep-research-20260526T150811/
    report.md
    ...
  ```
- Cleaning up one run is a single `rm -rf .loops/runs/deep-research-20260526T143022/`.
- Comparing two runs of the same loop is straightforward (`diff` or side-by-side).

## Motivation

- **Eliminates the ENH-1684 class of data-loss bugs** at the structural level: no loop can silently overwrite a prior run because every run lands in its own timestamped directory. ENH-1684 and `deep-research-arxiv.yaml` both require individual patches under the current model; the unified `run_dir` approach fixes all loops at once.
- **Discoverability**: all artifacts for a run are in one place — FSM `.history/` archives can optionally symlink or reference the corresponding `runs/` entry.
- **Cleanup ergonomics**: `ll-loop clean` can target a single run directory rather than hunting across multiple type-specific dirs.
- **Consistency**: loop authors no longer need to invent per-loop output path conventions.

## Proposed Solution

1. **Runner injects `run_dir`**: In `scripts/little_loops/fsm/` (likely `persistence.py` or the loop executor), generate a `run_dir` value of the form `.loops/runs/{loop_name}-{timestamp}` at run startup and inject it into the loop's template context as `context.run_dir`. Create the directory before the `init` state executes.

2. **Convention for loop YAML authors**: Document `${context.run_dir}` as the canonical way to reference the run's artifact directory. Loops that currently use `context.output_dir` migrate to `context.run_dir`.

3. **Migrate existing built-in loops**: Update `deep-research.yaml`, `deep-research-arxiv.yaml`, and any other built-in loops that use a custom `output_dir` to use `${context.run_dir}` instead.

4. **Scope exclusions**:
   - `.loops/tmp/` remains a shared, cross-run scratch space (rate-limit circuit breaker, session scratch files). Not per-run.
   - `.loops/.running/` and `.loops/.history/` (FSM internal state) are unaffected — this change is about domain artifacts only.
   - `context.output_dir` stays valid for loops that intentionally want a stable, non-timestamped output path (e.g., loops that accumulate data over time).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` or loop executor — inject `run_dir` into context at startup
- `scripts/little_loops/loops/deep-research.yaml` — replace `output_dir`/`DIR` construction with `${context.run_dir}`
- `scripts/little_loops/loops/deep-research-arxiv.yaml` — same migration
- Any other built-in loops using custom output directories

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — entrypoint that kicks off loop execution; likely where `run_dir` generation belongs
- `scripts/little_loops/cli/loop/next_loop.py` — may need access to `run_dir`

### Similar Patterns
- ENH-1684 is the narrow per-loop patch this replaces at the structural level
- `.loops/.history/<run_id>-<loop_name>/` — existing per-run isolation model for FSM state; `runs/` mirrors this pattern for domain artifacts

### Tests
- `scripts/tests/test_deep_research.py` — update path assertions to match new `runs/` layout
- `scripts/tests/test_builtin_loops.py` — check for hardcoded path assertions

### Documentation
- `docs/ARCHITECTURE.md` — update `.loops/` directory structure diagram
- Loop authoring section of CLAUDE.md — document `${context.run_dir}` convention

### Configuration
- N/A — no config file changes needed; `run_dir` is runtime-injected

## Implementation Steps

1. Add `run_dir` generation to the loop executor (compute `{loop_name}-{timestamp}`, mkdir, inject into context).
2. Update `deep-research.yaml` and `deep-research-arxiv.yaml` to use `${context.run_dir}`.
3. Audit remaining built-in loops for custom `output_dir` usage and migrate.
4. Update tests that assert on `.loops/research/` or other old artifact paths.
5. Document the `${context.run_dir}` convention in loop authoring docs.

## Impact

- **Priority**: P3 — Meaningful quality-of-life and data-safety improvement; not blocking
- **Effort**: Medium — Runner change + migration of existing loops + test updates
- **Risk**: Low — Additive (new dirs under `runs/`); loops that don't use `run_dir` are unaffected; no breaking changes to the FSM state layer
- **Breaking Change**: No — `context.output_dir` remains valid; migration is opt-in for custom loops

## Labels

`loops`, `fsm`, `artifact-management`, `data-safety`

## Status

**Open** | Created: 2026-05-26 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-26T20:24:33Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a02e39e-0327-4fde-996c-a64d954c3e35.jsonl`

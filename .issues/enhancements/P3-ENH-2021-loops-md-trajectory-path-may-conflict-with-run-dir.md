---
id: ENH-2021
title: loops.md trajectory artifact path may conflict with runner-injected run_dir
status: done
priority: P3
type: ENH
created: 2026-06-08
completed_at: 2026-06-08 16:40:35+00:00
---

## Summary

`docs/reference/loops.md` documents `harness-optimize` trajectory artifacts being written to `.ll/runs/harness-optimize/<run-id>/...`. However, `CLAUDE.md`'s MR-3 rule states that loops must write intermediate artifacts to `${context.run_dir}/`, which the runner injects as `.loops/runs/<loop>-<timestamp>/`.

The documented path (`.ll/runs/`) conflicts with the runner-injected path (`.loops/runs/`). Investigation of the actual loop YAML (`scripts/little_loops/loops/harness-optimize.yaml`) confirms it hard-codes `.ll/runs/harness-optimize/$${RUN_ID}/` for trajectory files while correctly using `${context.run_dir}/` for intermediate state files — so the loop itself violates MR-3 for trajectory writes.

## Current Behavior

`scripts/little_loops/loops/harness-optimize.yaml` writes trajectory files to a hard-coded `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl` path (see `init_run` and `write_trajectory` states). The `docs/reference/loops.md` documents this same hard-coded path. Intermediate state queue files correctly use `${context.run_dir}/` but trajectory output does not.

## Expected Behavior

Trajectory files should be written to `${context.run_dir}/states/<state>/trajectory.jsonl` (expanding to `.loops/runs/harness-optimize-<timestamp>/states/<state>/trajectory.jsonl`), consistent with MR-3. The `docs/reference/loops.md` State Graph section and artifact table should be updated to reflect this corrected path.

## Proposed Solution

1. In `scripts/little_loops/loops/harness-optimize.yaml`, update the `init_run` state to capture `${context.run_dir}` as the trajectory base instead of constructing `.ll/runs/harness-optimize/$${RUN_ID}/`.
2. Update all subsequent states that reference `.ll/runs/harness-optimize` to use `${context.run_dir}` instead.
3. Update `docs/reference/loops.md` lines documenting `.ll/runs/harness-optimize/<run-id>/` to show `.loops/runs/harness-optimize-<timestamp>/` (the runner-injected path pattern).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/harness-optimize.yaml` — `init_run`, `load_directive`, `write_trajectory`, `evaluate` states that hard-code `.ll/runs/harness-optimize`
- `docs/reference/loops.md` — State Graph section (~line 59, 85, 113) and artifact table

### Dependent Files (Callers/Importers)
- Any scripts or CI that reads from `.ll/runs/harness-optimize/` after a run would need to use the new runner-injected path

### Tests
- N/A — loop YAML changes are integration-tested via `ll-loop validate`

### Documentation
- `docs/reference/loops.md` — primary documentation file for this loop

### Configuration
- N/A

## Impact

- **Priority**: P3 — Low; documentation and correctness gap, no functional regression observed
- **Effort**: Small — targeted find-and-replace in YAML states and one docs section
- **Risk**: Low — trajectory path change only affects where output files land, not logic
- **Breaking Change**: Yes, for any tooling that reads `.ll/runs/harness-optimize/` post-run; runner-injected path is printed to stdout on `ll-loop run`

## Scope Boundaries

- Only update trajectory artifact paths in `harness-optimize.yaml` — do not restructure other states or change loop logic
- Do not change `${context.run_dir}/` usage for intermediate state files (already correct)
- Do not update other loops; this fix is scoped to `harness-optimize`

## Labels

`documentation`, `loops`, `maint`, `mr3-compliance`

## Status

**Open** | Created: 2026-06-08 | Priority: P3


## Resolution

Updated `harness-optimize.yaml` to use `${context.run_dir}` for all trajectory artifact paths (MR-3 compliance):
- `init_run`: replaced hard-coded `.ll/runs/harness-optimize/$RUN_ID/...` with `${context.run_dir}/states/whole-file/trajectory.jsonl`
- `load_directive`: replaced `find .ll/runs/harness-optimize` with `find ${context.run_dir}`
- `write_trajectory_accepted` / `write_trajectory_rejected`: removed `RUN_ID` extraction hack; state-mode branch now uses `${context.run_dir}/states/$STATE_NAME/trajectory.jsonl`

Updated `docs/reference/loops.md` State Graph, Trajectory, and Output Artifacts sections to reflect the corrected `.loops/runs/harness-optimize-<timestamp>/` path pattern.

## Session Log
- `/ll:ready-issue` - 2026-06-08T16:37:25 - `a6f8e47c-076c-470b-96e5-316fafdf46fb.jsonl`
- `/ll:manage-issue improve` - 2026-06-08T16:40:35Z

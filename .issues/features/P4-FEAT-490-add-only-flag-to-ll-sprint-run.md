---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# FEAT-490: Add `--only` flag to `ll-sprint run`

## Summary

The `--only` flag exists in `cli_args.py` and is used by `ll-auto` and `ll-parallel`, but `ll-sprint run` does not include it. Users can `--skip` issues and filter by `--type`, but cannot specify a subset of sprint issues to process by ID.

## Current Behavior

`ll-sprint run` accepts `--skip` (exclude issues) and `--type` (filter by type) but has no `--only` flag. The `add_only_arg` function in `cli_args.py:44-51` exists but is not called in the sprint run parser setup at `cli/sprint/__init__.py:111-126`.

## Expected Behavior

`ll-sprint run <name> --only ENH-123,BUG-456` processes only the specified issues from the sprint definition.

## Motivation

`ll-auto` and `ll-parallel` both support `--only` for targeted issue reprocessing, but `ll-sprint run` lacks this flag. This inconsistency forces sprint users to use `--skip` with a long list of IDs when they only want to reprocess a few. Adding `--only` to `ll-sprint run` makes the flag available consistently across all execution modes and simplifies recovery from partial sprint failures.

## Use Case

A developer has a sprint with 10 issues but wants to reprocess only 2 specific ones after fixing a configuration issue. Instead of skipping the other 8 with `--skip`, they use `--only ENH-123,BUG-456`.

## Acceptance Criteria

- [ ] `ll-sprint run <name> --only ID1,ID2` processes only specified issues
- [ ] The `--only` flag is documented in `--help`
- [ ] Specified IDs must be present in the sprint definition (error if not)
- [ ] Compatible with `--resume` and other existing flags

## Proposed Solution

Add `add_only_arg(run_parser)` to `cli/sprint.py` and wire `args.only` into the `create_parallel_config()` call. The underlying `ParallelOrchestrator` already accepts `only_ids` via `ParallelConfig`.

## Implementation Steps

1. Add `add_only_arg(run_parser)` to sprint run parser setup
2. Wire `args.only` into the parallel config creation
3. Validate that specified IDs exist in the sprint definition

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint/__init__.py` — add `add_only_arg(run_parser)` to run parser setup (lines ~111-126) and wire to config

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- `cli/parallel.py:119` — already uses `add_only_arg(parser)`
- `cli_args.py:218-230` — `add_common_auto_args` includes `add_only_arg`

### Tests
- `scripts/tests/` — add test for `--only` flag with sprint run

### Documentation
- N/A — `--help` auto-generated

### Configuration
- N/A

## Impact

- **Priority**: P4 — Consistency improvement across CLI tools
- **Effort**: Small — One-line addition plus config wiring
- **Risk**: Low — Uses existing infrastructure
- **Breaking Change**: No

## Labels

`feature`, `cli`, `sprint`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`
- `/ll:verify-issues` - 2026-02-25 - Updated file reference from `cli/sprint.py:106-121` to `cli/sprint/__init__.py:111-126` (sprint CLI was refactored into a package)
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified; add_only_arg(parser) at cli/parallel.py:119 confirmed as the model; ParallelConfig.only_ids confirmed as the wiring target; no knowledge gaps identified

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

## Blocked By

- FEAT-441

## Blocks

- FEAT-488

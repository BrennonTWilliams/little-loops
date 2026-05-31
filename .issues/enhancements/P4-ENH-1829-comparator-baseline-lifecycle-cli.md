---
id: ENH-1829
title: Comparator Evaluator — Baseline Lifecycle CLI
type: ENH
priority: P4
status: open
parent: ENH-1793
depends_on:
- ENH-1828
labels:
- enhancement
- loops
- evaluator
- regression-detection
size: Small
---

# ENH-1829: Comparator Evaluator — Baseline Lifecycle CLI

## Summary

Add the `ll-loop promote-baseline <loop>` subcommand for manual baseline management, register it in the known-subcommands guard, add a display label to `info.py`, and update related documentation. Builds on ENH-1828 (core evaluator).

## Parent Issue

Decomposed from ENH-1793: Blind Cross-Iteration Comparator

## Proposed Solution

The `promote-baseline` CLI subcommand finds the latest run's harness output and copies it to `.loops/baselines/<loop>/output.txt`. This complements the `auto_promote` config field added in ENH-1828 for cases where a user wants to manually set the baseline after inspecting a run.

## Implementation Steps

### `scripts/little_loops/cli/loop/__init__.py`

1. Add `"promote-baseline"` to the `known_subcommands` set (lines 47–75). Without this guard, `ll-loop promote-baseline` is misinterpreted as a loop name and prepended with `"run"`.

2. Add `promote-baseline` subcommand handler:
   - Takes `<loop>` argument
   - Finds latest run in `.loops/runs/<loop>-*/` (sort by timestamp suffix)
   - Reads harness output from the run directory
   - Copies to `.loops/baselines/<loop>/output.txt` (create dirs as needed)
   - Prints confirmation or informative error if no runs found

### `scripts/little_loops/cli/loop/info.py`

Add `"comparator": "blind comparator"` (or similar label) to `_EVALUATE_TYPE_DISPLAY` dict so `ll-loop show --verbose` renders a human-readable label instead of the raw string.

## Tests

### `scripts/tests/test_ll_loop_execution.py`

Add `test_promote_baseline_subcommand_registered` to `TestCmdSimulate`, following pattern of `test_diagnose_evaluators_subcommand_registered` at line 1453.

### `scripts/tests/test_ll_loop_integration.py`

Add `test_promote_baseline_no_runs` (no runs dir → informative message / non-zero exit), following pattern of `test_diagnose_evaluators_no_history` at line 543.

## Documentation

- `.claude/CLAUDE.md` — `## CLI Tools` section: add `ll-loop promote-baseline` entry alongside `ll-loop run`

## Acceptance Criteria

- [ ] `ll-loop promote-baseline <loop>` copies latest run output to `.loops/baselines/<loop>/output.txt`
- [ ] `ll-loop promote-baseline` with no runs exits with informative message and non-zero exit
- [ ] `ll-loop show --verbose` displays `"blind comparator"` for comparator evaluator states
- [ ] `known_subcommands` guard prevents `promote-baseline` from being treated as a loop name
- [ ] `CLAUDE.md` CLI tools section documents the new subcommand

## Session Log
- `/ll:issue-size-review` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/328bc3bf-da89-4021-981a-e4291a0ad2e5.jsonl`

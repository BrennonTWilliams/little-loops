# BUG-327: ll-auto continuation bypasses skill completion logic - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-327-ll-auto-continuation-bypasses-skill-completion-logic.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Problem

When `run_with_continuation()` detects CONTEXT_HANDOFF, it uses the raw continuation prompt content as the next command (line 189). This bypasses the manage_issue skill lifecycle, so completion logic (moving issue to completed/) never runs.

## Solution

Replace raw prompt usage with `--resume` flag on the original command. The manage_issue skill already supports `--resume` and reads `.claude/ll-continue-prompt.md`.

## Changes

### File: `scripts/little_loops/issue_manager.py` (line 187-189)
Replace raw prompt as command with `initial_command + " --resume"`.

### File: `scripts/little_loops/parallel/worker_pool.py` (line 744-745)
Same fix: use `command + " --resume"` instead of raw prompt content.

### File: `scripts/tests/test_issue_manager.py`
Add test verifying continuation command uses `--resume` flag.

## Verification
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

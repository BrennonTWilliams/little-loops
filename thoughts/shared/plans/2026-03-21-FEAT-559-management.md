# FEAT-559 Implementation Plan: Add default `--input` path for ll-messages pipeline integration

**Date**: 2026-03-21
**Issue**: FEAT-559
**Status**: Completed

## Problem

`ll-workflows analyze` required `--input` as a mandatory argument with no default, forcing users to
specify the full JSONL path on every invocation. This broke the ergonomic two-command pipeline with
`ll-messages`.

## Solution: Option A (fixed default path)

Added module-level constant `_DEFAULT_INPUT_PATH = Path(".claude/workflow-analysis/step1-patterns.jsonl")`
and changed `--input` from `required=True` to `default=_DEFAULT_INPUT_PATH`. When the default path
is missing, the error message adds a hint to run `ll-messages` first.

## Changes

### `scripts/little_loops/workflow_sequence_analyzer.py`
1. Added `_DEFAULT_INPUT_PATH` constant after imports
2. Changed `--input` argument: removed `required=True`, added `default=_DEFAULT_INPUT_PATH`, updated help text
3. Updated input-missing error message to append an `ll-messages` hint when using the default path
4. Updated `epilog` examples to show pipeline invocation and the conventional path

### `scripts/little_loops/cli/messages.py`
1. Added pipeline example to `ll-messages` epilog showing the conventional `--output` path

### `scripts/tests/test_workflow_sequence_analyzer.py`
1. Added imports: `sys`, `patch`; added `main` to the module imports
2. Added `TestMainDefaultInput` class with 3 tests

## Acceptance Criteria Verification

- [x] `--input` no longer `required=True` — defaults to `.claude/workflow-analysis/step1-patterns.jsonl`
- [x] Missing default path produces clear error naming the path + hint to run `ll-messages`
- [x] Explicit `--input` overrides the default (existing behavior unchanged)
- [x] `ll-messages` help text mentions the default path convention (epilog updated)

## Test Results

- All 3 new tests pass (Green phase)
- Full test suite: 3819 passed, 4 skipped
- Lint: clean
- Type check: clean

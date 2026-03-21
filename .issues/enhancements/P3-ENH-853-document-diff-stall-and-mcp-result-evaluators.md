---
id: ENH-853
type: ENH
priority: P3
status: open
title: "Document diff_stall and mcp_result evaluators in generalized-fsm-loop.md"
created: 2026-03-21
---

## Summary

Two FSM evaluator types are implemented but undocumented in `docs/generalized-fsm-loop.md`.

## Missing Documentation

### `diff_stall` evaluator
- **File**: `scripts/little_loops/fsm/evaluators.py:373`
- **Verdicts**: `yes` (progress — diff changed), `no` (stalled — diff unchanged for `max_stall` iterations), `error`
- **Config fields**: `scope` (list of paths), `max_stall` (int, default 1)
- **Use case**: Detect when a fix loop is spinning without making filesystem changes

### `mcp_result` evaluator
- **File**: `scripts/little_loops/fsm/evaluators.py:468`
- **Verdicts**: `success` (isError: false), `tool_error` (isError: true), `not_found` (exit 127), `timeout` (exit 124)
- **Use case**: Evaluate results from `action_type: mcp_tool` states
- **Note**: This is the only built-in evaluator that returns `success` as a verdict (not `yes`)

## Fix

Add a new subsection under "Tier 1: Deterministic Evaluators" for `diff_stall`, and a new subsection (possibly under a "Tier 1.5: MCP Evaluator" or after convergence) for `mcp_result`. Also update the schema type comment at line ~361 — already done in a previous fix.

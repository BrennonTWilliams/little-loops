---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# ENH-829: Add test coverage for `_extract_messages_with_context`

## Summary

The `_extract_messages_with_context` function and `_aggregate_response_metadata` in `user_messages.py` have no direct test coverage. The `include_response_context=True` code path in `extract_user_messages` is not exercised by any test in `test_user_messages.py`.

## Location

- **File**: `scripts/little_loops/user_messages.py`
- **Line(s)**: 382-398 (at scan commit: 8c6cf90)
- **Anchor**: `in function extract_user_messages`, `_extract_messages_with_context`

## Current Behavior

No test passes `include_response_context=True` to `extract_user_messages`. The context pairing logic, tool usage aggregation, and `since` filtering within `_extract_messages_with_context` are untested.

## Expected Behavior

At least one test class verifies:
1. User messages get `response_metadata` populated when `include_response_context=True`
2. Tool usage is correctly aggregated across multiple assistant records
3. Context collection stops at the next user message boundary
4. `since` filtering works within the context path

## Motivation

This is a non-trivial code path with aggregation logic and the O(n²) pattern identified in ENH-827. Tests are needed both to validate current behavior and to safely refactor the algorithm.

## Proposed Solution

Add a `TestExtractMessagesWithContext` class in `test_user_messages.py` using in-memory JSONL records constructed as dicts. Write to a temp JSONL file and exercise the `include_response_context=True` code path.

## Scope Boundaries

- Out of scope: Refactoring the O(n²) algorithm (that's ENH-827)
- Out of scope: Testing the non-context path (already covered)

## Impact

- **Priority**: P4 - Test gap for non-trivial logic; blocks safe refactoring of ENH-827
- **Effort**: Small - Standard test writing against existing function
- **Risk**: Low - Test-only change
- **Breaking Change**: No

## Labels

`enhancement`, `testing`, `user-messages`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`

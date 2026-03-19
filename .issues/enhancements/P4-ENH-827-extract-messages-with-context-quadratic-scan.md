---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# ENH-827: `_extract_messages_with_context` O(n²) inner scan

## Summary

`_extract_messages_with_context` in `user_messages.py` uses a nested loop where for every user message at index `i`, it scans forward from `i+1` to find subsequent assistant records until the next user message. For session files with many records, this is O(n²).

## Location

- **File**: `scripts/little_loops/user_messages.py`
- **Line(s)**: 663-682 (at scan commit: 8c6cf90)
- **Anchor**: `in function _extract_messages_with_context`
- **Code**:
```python
i = 0
while i < len(records):
    record = records[i]
    msg = _parse_user_record(record, jsonl_file, since)
    if msg is not None:
        assistant_responses: list[dict] = []
        for j in range(i + 1, len(records)):   # O(n) inner scan per user message
            next_record = records[j]
            if next_record.get("type") == "assistant":
                assistant_responses.append(next_record)
            elif next_record.get("type") == "user":
                break
    i += 1
```

## Current Behavior

For a session file with `n` records, this is O(n²) in the worst case (many user messages, long assistant responses between them).

## Expected Behavior

A single O(n) pass that groups records by user-message boundaries.

## Motivation

`ll-messages` and `ll-workflows` process large session files. Quadratic behavior becomes noticeable with sessions containing 500+ records.

## Proposed Solution

Replace with a single-pass grouping approach: iterate records once, tracking the current user message and accumulating assistant records until the next user record is seen:

```python
current_user_msg = None
current_responses = []
for record in records:
    if record.get("type") == "user":
        if current_user_msg is not None:
            # Emit previous group
            ...
        current_user_msg = _parse_user_record(record, jsonl_file, since)
        current_responses = []
    elif record.get("type") == "assistant" and current_user_msg is not None:
        current_responses.append(record)
```

## Scope Boundaries

- Out of scope: Changing the public API of `extract_user_messages`
- Out of scope: Streaming from file (records are already loaded into memory)

## Impact

- **Priority**: P4 - Performance improvement for large sessions; not a correctness issue
- **Effort**: Small - Replace loop structure, same logic
- **Risk**: Low - Pure refactor, same output
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `user-messages`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

- **Verified**: 2026-03-19 — VALID
- File `scripts/little_loops/user_messages.py` exists ✓
- Function `_extract_messages_with_context` at line 643, O(n²) inner loop at lines 663–682 matches exactly ✓
- Code snippet in issue matches current code verbatim ✓
- No fix has been applied; issue remains open and accurate

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:44:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`

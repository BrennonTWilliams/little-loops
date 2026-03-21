# ENH-827: `_extract_messages_with_context` O(n²) → O(n) Fix

**Date**: 2026-03-21
**Issue**: P4-ENH-827-extract-messages-with-context-quadratic-scan.md
**Action**: improve

---

## Problem

`_extract_messages_with_context` in `scripts/little_loops/user_messages.py` (lines 699–720) uses a nested loop:
- Outer while loop iterates all `n` records
- For each user record that parses successfully, an inner `for j in range(i+1, n)` scan collects assistant responses

This is O(n²) worst case for sessions with many user messages.

## Solution

Single-pass grouping: iterate records once, emit a group whenever we encounter the next user record boundary.

**Key behavioral equivalences verified:**
1. Filtered user records (`_parse_user_record → None`): set `current_msg = None`, reset `current_responses = []`. Subsequent assistant records are not collected (same as original inner loop not starting for None msg).
2. Filtered user record between two valid ones: emit previous group at the filtered boundary (original inner scan breaks on ANY user record, filtered or not).
3. Final group: emitted after the loop (original handled via `while i < len(records)` natural termination).

## Changes

**File**: `scripts/little_loops/user_messages.py` — `_extract_messages_with_context` function (lines 699–720)

**Before:**
```python
i = 0
while i < len(records):
    record = records[i]
    msg = _parse_user_record(record, jsonl_file, since)

    if msg is not None:
        assistant_responses: list[dict] = []
        for j in range(i + 1, len(records)):
            next_record = records[j]
            if next_record.get("type") == "assistant":
                assistant_responses.append(next_record)
            elif next_record.get("type") == "user":
                break

        msg.response_metadata = _aggregate_response_metadata(assistant_responses)
        messages.append(msg)

    i += 1
```

**After:**
```python
current_msg: UserMessage | None = None
current_responses: list[dict] = []

for record in records:
    if record.get("type") == "user":
        if current_msg is not None:
            current_msg.response_metadata = _aggregate_response_metadata(current_responses)
            messages.append(current_msg)
        current_msg = _parse_user_record(record, jsonl_file, since)
        current_responses = []
    elif record.get("type") == "assistant" and current_msg is not None:
        current_responses.append(record)

# Emit the final group
if current_msg is not None:
    current_msg.response_metadata = _aggregate_response_metadata(current_responses)
    messages.append(current_msg)
```

## TDD Note

Red phase is N/A — this is a pure performance refactor with identical outputs. All existing behavioral tests serve as the Green verification suite.

## Verification

1. `python -m pytest scripts/tests/test_user_messages.py -v` — all existing tests pass
2. `ruff check scripts/` — no lint errors
3. `python -m mypy scripts/little_loops/` — no type errors

## Success Criteria

- [x] Single-pass O(n) algorithm replaces nested loop
- [ ] All existing `test_user_messages.py` tests pass
- [ ] Lint and type checks clean

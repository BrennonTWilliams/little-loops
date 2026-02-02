---
discovered_date: 2026-02-02
discovered_by: capture_issue
---

# BUG-220: ll-messages --include-response-context only captures first assistant turn

## Summary

The `--include-response-context` flag in `ll-messages` only captures metadata from the immediately following assistant response, missing tool usage from subsequent turns within the same user request.

## Context

Identified during code review. In `scripts/little_loops/user_messages.py:401-442`, the `_extract_messages_with_context` function breaks after finding the first assistant response:

```python
for j in range(i + 1, len(records)):
    next_record = records[j]
    if next_record.get("type") == "assistant":
        response_metadata = _extract_response_metadata(next_record)
        break  # <-- stops at first assistant response
```

A single user message typically triggers multiple assistant turns (tool use → result → more tool use → final response). The current implementation only captures tools from the first turn, missing all subsequent tool usage.

## Current Behavior

Given a user request that triggers 3 assistant turns:
- Turn 1: Read file A
- Turn 2: Edit file A
- Turn 3: Read file B, confirm completion

Current output:
```json
{
  "response_metadata": {
    "tools_used": [{"tool": "Read", "count": 1}],
    "files_read": ["file_A"],
    "files_modified": [],
    "completion_status": "success"
  }
}
```

## Expected Behavior

Should aggregate all assistant responses until the next user message:

```json
{
  "response_metadata": {
    "tools_used": [
      {"tool": "Read", "count": 2},
      {"tool": "Edit", "count": 1}
    ],
    "files_read": ["file_A", "file_B"],
    "files_modified": ["file_A"],
    "completion_status": "success"
  }
}
```

## Proposed Solution

Modify `_extract_messages_with_context` to:
1. Collect all assistant responses until the next user message
2. Aggregate `tools_used` counts across all turns
3. Combine `files_read` and `files_modified` lists (deduplicated)
4. Take `completion_status` from the final assistant response

```python
def _extract_messages_with_context(...):
    # ...
    if msg is not None:
        # Collect ALL assistant responses until next user message
        assistant_responses = []
        for j in range(i + 1, len(records)):
            next_record = records[j]
            if next_record.get("type") == "assistant":
                assistant_responses.append(next_record)
            elif next_record.get("type") == "user":
                break  # Hit next user message, stop

        if assistant_responses:
            msg.response_metadata = _aggregate_response_metadata(assistant_responses)
```

## Impact

- **Priority**: P3 - Feature works but produces incomplete data
- **Effort**: Low - Straightforward fix
- **Risk**: Low - Read-only extraction

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | CLI tool structure |

---

**Priority**: P3 | **Created**: 2026-02-02

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-02
- **Status**: Completed

### Changes Made
- `scripts/little_loops/user_messages.py`: Added `_aggregate_response_metadata()` function to combine metadata from multiple assistant responses
- `scripts/little_loops/user_messages.py`: Modified `_extract_messages_with_context()` to collect ALL assistant responses until next user message
- `scripts/tests/test_user_messages.py`: Added `test_aggregates_multiple_assistant_turns` test

### Verification Results
- Tests: PASS (55/55)
- Lint: PASS
- Types: PASS

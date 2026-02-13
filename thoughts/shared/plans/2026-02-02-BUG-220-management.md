# BUG-220: ll-messages --include-response-context only captures first assistant turn - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-220-ll-messages-response-context-only-captures-first-turn.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `_extract_messages_with_context` function at `scripts/little_loops/user_messages.py:401-442` processes JSONL records to pair user messages with assistant responses. Currently, it stops at the first assistant response encountered due to an early `break` statement.

### Key Discoveries
- **Bug location**: `user_messages.py:428-432` - the inner for loop breaks after first assistant response
- **Extraction function**: `_extract_response_metadata()` at `user_messages.py:105-158` extracts from a single response
- **Data structure**: `ResponseMetadata` dataclass at `user_messages.py:76-102` needs no changes
- **Aggregation pattern**: Codebase uses `dict.get(key, 0) + 1` and `sorted(set())` for dedup (see `git_operations.py:150-155`)

## Desired End State

When `--include-response-context` is used, metadata should aggregate ALL assistant responses until the next user message:
- Tool counts summed across all turns
- File lists deduplicated and combined
- Completion status taken from final assistant response

### How to Verify
- Unit test with multi-turn assistant responses shows aggregated counts
- Existing tests continue to pass
- Manual test with real Claude Code session shows full tool usage

## What We're NOT Doing

- Not changing the `ResponseMetadata` dataclass structure
- Not changing CLI arguments or output format
- Not modifying non-response-context code paths

## Problem Analysis

The bug is in `_extract_messages_with_context()`:

```python
for j in range(i + 1, len(records)):
    next_record = records[j]
    if next_record.get("type") == "assistant":
        response_metadata = _extract_response_metadata(next_record)
        break  # <-- Bug: stops at first assistant response
    elif next_record.get("type") == "user":
        break
```

A single user message can trigger multiple assistant turns (tool use → tool result → more tool use → final response). The current implementation only captures the first turn.

## Solution Approach

1. Create new `_aggregate_response_metadata()` function to merge multiple ResponseMetadata objects
2. Modify `_extract_messages_with_context()` to collect ALL assistant responses until next user message
3. Add unit test for multi-turn aggregation behavior

## Implementation Phases

### Phase 1: Add Aggregation Function

#### Overview
Add `_aggregate_response_metadata()` function that combines multiple ResponseMetadata objects.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Location**: After `_extract_response_metadata()` (~line 159)
**Changes**: Add new aggregation function

```python
def _aggregate_response_metadata(responses: list[dict]) -> ResponseMetadata | None:
    """Aggregate metadata from multiple assistant response records.

    Combines tool counts, file lists, and uses completion status from final response.

    Args:
        responses: List of assistant records from JSONL

    Returns:
        Aggregated ResponseMetadata, or None if no valid responses
    """
    if not responses:
        return None

    tools_used: dict[str, int] = {}
    files_read: set[str] = set()
    files_modified: set[str] = set()
    completion_status = "success"
    error_message: str | None = None

    for response_record in responses:
        message_data = response_record.get("message", {})
        content = message_data.get("content", [])

        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            tools_used[tool_name] = tools_used.get(tool_name, 0) + 1

            tool_input = block.get("input", {})
            if tool_name == "Read":
                file_path = tool_input.get("file_path")
                if file_path:
                    files_read.add(file_path)
            elif tool_name in ("Edit", "Write"):
                file_path = tool_input.get("file_path")
                if file_path:
                    files_modified.add(file_path)

    # Use completion status from the final response
    final_content = responses[-1].get("message", {}).get("content", [])
    if isinstance(final_content, list):
        completion_status = _detect_completion_status(final_content)
        if completion_status == "failure":
            error_message = _detect_error_message(final_content)

    # Convert to output format
    tools_list: list[dict[str, str | int]] = [
        {"tool": name, "count": count} for name, count in tools_used.items()
    ]

    return ResponseMetadata(
        tools_used=tools_list,
        files_read=sorted(files_read),
        files_modified=sorted(files_modified),
        completion_status=completion_status,
        error_message=error_message,
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Modify Extraction to Aggregate

#### Overview
Update `_extract_messages_with_context()` to collect all assistant responses and call aggregation function.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Location**: Lines 401-442
**Changes**: Modify to collect all assistant responses, then aggregate

Replace current implementation with:

```python
def _extract_messages_with_context(
    records: list[dict],
    jsonl_file: Path,
    since: datetime | None,
) -> list[UserMessage]:
    """Extract user messages with response context from a list of records.

    Pairs each user message with ALL following assistant responses until the
    next user message, aggregating tool usage and file changes.

    Args:
        records: List of all records from a JSONL file
        jsonl_file: Source file (for fallback timestamp)
        since: Filter for messages after this datetime

    Returns:
        List of UserMessages with response_metadata populated
    """
    messages: list[UserMessage] = []

    i = 0
    while i < len(records):
        record = records[i]
        msg = _parse_user_record(record, jsonl_file, since)

        if msg is not None:
            # Collect ALL assistant responses until next user message
            assistant_responses: list[dict] = []
            for j in range(i + 1, len(records)):
                next_record = records[j]
                if next_record.get("type") == "assistant":
                    assistant_responses.append(next_record)
                elif next_record.get("type") == "user":
                    # Hit another user message, stop collecting
                    break

            msg.response_metadata = _aggregate_response_metadata(assistant_responses)
            messages.append(msg)

        i += 1

    return messages
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`

---

### Phase 3: Add Unit Test for Multi-Turn Aggregation

#### Overview
Add test case that verifies tool counts and file lists are aggregated across multiple assistant turns.

#### Changes Required

**File**: `scripts/tests/test_user_messages.py`
**Location**: Add to `TestExtractUserMessagesWithResponseContext` class
**Changes**: Add new test method

```python
def test_aggregates_multiple_assistant_turns(
    self, temp_project_folder: Path
) -> None:
    """Aggregates metadata from all assistant turns until next user message."""
    records = [
        {
            "type": "user",
            "message": {"content": "Make changes to multiple files"},
            "timestamp": "2026-01-10T12:00:00Z",
            "sessionId": "sess-1",
            "uuid": "uuid-1",
        },
        # First assistant turn - reads file
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/file_a.py"}},
                ]
            },
            "timestamp": "2026-01-10T12:00:01Z",
            "sessionId": "sess-1",
            "uuid": "uuid-2",
        },
        # Second assistant turn - edits file
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/file_a.py"}},
                ]
            },
            "timestamp": "2026-01-10T12:00:02Z",
            "sessionId": "sess-1",
            "uuid": "uuid-3",
        },
        # Third assistant turn - reads another file and completes
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/file_b.py"}},
                    {"type": "text", "text": "Done!"},
                ]
            },
            "timestamp": "2026-01-10T12:00:03Z",
            "sessionId": "sess-1",
            "uuid": "uuid-4",
        },
    ]
    self._write_jsonl(temp_project_folder / "session.jsonl", records)

    messages = extract_user_messages(
        temp_project_folder, include_response_context=True
    )

    assert len(messages) == 1
    assert messages[0].response_metadata is not None
    # Should aggregate Read count = 2 (file_a + file_b)
    tools = {t["tool"]: t["count"] for t in messages[0].response_metadata.tools_used}
    assert tools.get("Read") == 2
    assert tools.get("Edit") == 1
    # Should include both files read (deduplicated and sorted)
    assert "/file_a.py" in messages[0].response_metadata.files_read
    assert "/file_b.py" in messages[0].response_metadata.files_read
    # Should include edited file
    assert "/file_a.py" in messages[0].response_metadata.files_modified
    # Completion status from final response
    assert messages[0].response_metadata.completion_status == "success"
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] New test passes: `python -m pytest scripts/tests/test_user_messages.py::TestExtractUserMessagesWithResponseContext::test_aggregates_multiple_assistant_turns -v`
- [ ] All tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`

---

## Testing Strategy

### Unit Tests
- New test: `test_aggregates_multiple_assistant_turns` - verifies multi-turn aggregation
- Existing tests verify single-turn behavior continues to work

### Integration Tests
- Run full test suite to ensure no regressions

## References

- Original issue: `.issues/bugs/P3-BUG-220-ll-messages-response-context-only-captures-first-turn.md`
- Aggregation pattern: `scripts/little_loops/git_operations.py:150-155` (sorted set for dedup)
- Count aggregation: `scripts/little_loops/user_messages.py:120-131` (dict.get pattern)
- Test patterns: `scripts/tests/test_user_messages.py:752-892`

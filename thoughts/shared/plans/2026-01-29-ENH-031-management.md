# ENH-031: Response Context Capture - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-031-response-context-capture.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-messages` CLI tool extracts user messages from Claude Code session logs (JSONL files in `~/.claude/projects/`). Currently:

- `user_messages.py:99-216` extracts only user messages (type == "user")
- `user_messages.py:145-146` explicitly skips non-user records
- No parsing of assistant responses or tool usage exists
- `UserMessage` dataclass has 7 fields: content, timestamp, session_id, uuid, cwd, git_branch, is_sidechain

### Key Discoveries
- JSONL records for assistant messages have `type: "assistant"` at `user_messages.py:145`
- Tool use blocks in assistant content have `type: "tool_use"` structure (similar parsing in `fsm/evaluators.py:467-478`)
- Existing pattern for dataclass serialization at `user_messages.py:57-67` (`to_dict()` method)
- CLI argument pattern at `cli.py:374-382` for boolean flags with `action="store_true"`

## Desired End State

When `--include-response-context` flag is passed to `ll-messages extract`, each extracted user message will include a `response_metadata` field containing:
- Tools used in the assistant's response
- Files read via Read tool
- Files modified via Edit/Write tools
- Completion status (success/failure/partial)
- Any error message detected

### How to Verify
- `ll-messages --include-response-context -n 5 --stdout` outputs JSONL with `response_metadata` field
- Tests pass for new response context extraction functionality
- Existing tests continue to pass (backward compatibility)

## What We're NOT Doing

- Not adding `--redact-paths` option (deferred - mentioned in issue as future consideration)
- Not detecting `follow_up_suggested` field (complex NLP, low priority)
- Not changing default behavior (response context is opt-in)
- Not adding file deduplication across sessions

## Problem Analysis

Workflow analysis tools need more context than just user messages. By capturing what the assistant actually did (files modified, tools used), we enable:
1. File-based workflow clustering
2. Completion detection
3. Tool usage pattern analysis

## Solution Approach

1. Add `ResponseMetadata` dataclass to hold response context
2. Add optional `response_metadata` field to `UserMessage`
3. Create helper functions to parse assistant responses and extract metadata
4. Modify `extract_user_messages()` to optionally capture response context
5. Add `--include-response-context` CLI flag
6. Add comprehensive tests

## Implementation Phases

### Phase 1: Add ResponseMetadata Dataclass

#### Overview
Add a new dataclass to represent response metadata, following the existing `UserMessage` pattern.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Changes**: Add `ResponseMetadata` dataclass after `UserMessage` (around line 68)

```python
@dataclass
class ResponseMetadata:
    """Metadata extracted from assistant response.

    Attributes:
        tools_used: List of tools and their usage counts
        files_read: Files accessed via Read tool
        files_modified: Files changed via Edit/Write tools
        completion_status: "success", "failure", or "partial"
        error_message: Error text if failure detected
    """

    tools_used: list[dict[str, int | str]]
    files_read: list[str]
    files_modified: list[str]
    completion_status: str
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "tools_used": self.tools_used,
            "files_read": self.files_read,
            "files_modified": self.files_modified,
            "completion_status": self.completion_status,
            "error_message": self.error_message,
        }
```

Also add optional `response_metadata` field to `UserMessage`:
```python
response_metadata: ResponseMetadata | None = None
```

Update `UserMessage.to_dict()` to include response_metadata when present.

Update `__all__` to export `ResponseMetadata`.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Response Parsing Functions

#### Overview
Create helper functions to extract metadata from assistant response records.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Changes**: Add helper functions after the dataclass definitions

```python
def _extract_response_metadata(response_record: dict) -> ResponseMetadata | None:
    """Extract metadata from an assistant response record.

    Args:
        response_record: The assistant record from JSONL

    Returns:
        ResponseMetadata if parseable, None otherwise
    """
    message_data = response_record.get("message", {})
    content = message_data.get("content", [])

    if not isinstance(content, list):
        return None

    tools_used: dict[str, int] = {}
    files_read: list[str] = []
    files_modified: list[str] = []

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
                files_read.append(file_path)
        elif tool_name in ("Edit", "Write"):
            file_path = tool_input.get("file_path")
            if file_path:
                files_modified.append(file_path)

    # Detect completion status from text content
    completion_status = _detect_completion_status(content)
    error_message = _detect_error_message(content) if completion_status == "failure" else None

    # Convert tools_used dict to list format
    tools_list = [{"tool": name, "count": count} for name, count in tools_used.items()]

    return ResponseMetadata(
        tools_used=tools_list,
        files_read=files_read,
        files_modified=files_modified,
        completion_status=completion_status,
        error_message=error_message,
    )


def _detect_completion_status(content: list) -> str:
    """Detect completion status from response content.

    Args:
        content: List of content blocks from assistant response

    Returns:
        "success", "failure", or "partial"
    """
    text_parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    text = " ".join(text_parts).lower()

    # Check for error indicators
    error_patterns = ["error", "failed", "couldn't", "unable to", "cannot"]
    if any(pattern in text for pattern in error_patterns):
        return "failure"

    # Check for partial completion
    partial_patterns = ["partially", "some of", "not all", "incomplete"]
    if any(pattern in text for pattern in partial_patterns):
        return "partial"

    return "success"


def _detect_error_message(content: list) -> str | None:
    """Extract error message from response content.

    Args:
        content: List of content blocks from assistant response

    Returns:
        Error message if found, None otherwise
    """
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            # Look for common error message patterns
            lower_text = text.lower()
            if "error:" in lower_text or "failed:" in lower_text:
                # Extract the line containing the error
                for line in text.split("\n"):
                    if "error" in line.lower() or "failed" in line.lower():
                        return line.strip()[:200]  # Limit length
    return None
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Modify extract_user_messages Function

#### Overview
Add `include_response_context` parameter and logic to pair user messages with their assistant responses.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Changes**: Modify `extract_user_messages()` function

1. Add new parameter:
```python
def extract_user_messages(
    project_folder: Path,
    limit: int | None = None,
    since: datetime | None = None,
    include_agent_sessions: bool = True,
    include_response_context: bool = False,  # NEW
) -> list[UserMessage]:
```

2. When `include_response_context=True`, build a lookup of assistant responses by their parent user message UUID, then attach response metadata to user messages.

The key insight: In Claude Code JSONL, assistant responses follow user messages sequentially. We need to pair each user message with the next assistant message in the same session.

Implementation approach:
- First pass: collect all records for the file
- Build user messages as before
- If include_response_context: find the assistant response that follows each user message
- Attach the parsed ResponseMetadata

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 4: Add CLI Flag

#### Overview
Add `--include-response-context` flag to `main_messages()` in cli.py.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add argument in `main_messages()` function (around line 388, after --verbose)

```python
parser.add_argument(
    "--include-response-context",
    action="store_true",
    help="Include metadata from assistant responses (tools used, files modified)",
)
```

Update the `extract_user_messages()` call (around line 425):
```python
messages = extract_user_messages(
    project_folder=project_folder,
    limit=args.limit,
    since=since,
    include_agent_sessions=not args.exclude_agents,
    include_response_context=args.include_response_context,  # NEW
)
```

Update CLI examples in epilog:
```python
epilog="""
Examples:
  %(prog)s                              # Last 100 messages to file
  %(prog)s -n 50                        # Last 50 messages
  %(prog)s --since 2026-01-01           # Messages since date
  %(prog)s -o output.jsonl              # Custom output path
  %(prog)s --stdout                     # Print to terminal
  %(prog)s --include-response-context   # Include response metadata
""",
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] CLI help shows new flag: `ll-messages --help`

---

### Phase 5: Add Tests

#### Overview
Add comprehensive tests for the new response context functionality.

#### Changes Required

**File**: `scripts/tests/test_user_messages.py`
**Changes**: Add new test classes

```python
class TestResponseMetadata:
    """Tests for ResponseMetadata dataclass."""

    def test_to_dict_basic(self) -> None:
        """to_dict() returns correct dictionary structure."""
        metadata = ResponseMetadata(
            tools_used=[{"tool": "Edit", "count": 2}],
            files_read=["README.md"],
            files_modified=["src/main.py"],
            completion_status="success",
        )
        result = metadata.to_dict()

        assert result["tools_used"] == [{"tool": "Edit", "count": 2}]
        assert result["files_read"] == ["README.md"]
        assert result["files_modified"] == ["src/main.py"]
        assert result["completion_status"] == "success"
        assert result["error_message"] is None

    def test_to_dict_with_error(self) -> None:
        """to_dict() includes error message when present."""
        metadata = ResponseMetadata(
            tools_used=[],
            files_read=[],
            files_modified=[],
            completion_status="failure",
            error_message="File not found",
        )
        result = metadata.to_dict()

        assert result["completion_status"] == "failure"
        assert result["error_message"] == "File not found"


class TestExtractResponseMetadata:
    """Tests for _extract_response_metadata helper."""

    def test_extracts_tool_usage(self) -> None:
        """Extracts tool names and counts from response."""
        response = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/b.py"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/c.py"}},
                ]
            },
        }
        from little_loops.user_messages import _extract_response_metadata

        result = _extract_response_metadata(response)

        assert result is not None
        # Check tools_used contains Read:1 and Edit:2
        tools = {t["tool"]: t["count"] for t in result.tools_used}
        assert tools["Read"] == 1
        assert tools["Edit"] == 2

    def test_extracts_file_paths(self) -> None:
        """Extracts file paths from Read/Edit/Write tools."""
        response = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/read.py"}},
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/edit.py"}},
                    {"type": "tool_use", "name": "Write", "input": {"file_path": "/write.py"}},
                ]
            },
        }
        from little_loops.user_messages import _extract_response_metadata

        result = _extract_response_metadata(response)

        assert result is not None
        assert "/read.py" in result.files_read
        assert "/edit.py" in result.files_modified
        assert "/write.py" in result.files_modified

    def test_detects_failure_status(self) -> None:
        """Detects failure status from error text."""
        response = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Error: Could not find the file"},
                ]
            },
        }
        from little_loops.user_messages import _extract_response_metadata

        result = _extract_response_metadata(response)

        assert result is not None
        assert result.completion_status == "failure"


class TestExtractUserMessagesWithResponseContext:
    """Tests for extract_user_messages with include_response_context=True."""

    @pytest.fixture
    def temp_project_folder(self) -> Generator[Path, None, None]:
        """Create a temporary project folder with test JSONL files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _write_jsonl(self, path: Path, records: list[dict]) -> None:
        """Helper to write JSONL file."""
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    def test_includes_response_metadata_when_enabled(
        self, temp_project_folder: Path
    ) -> None:
        """Response metadata is included when flag is True."""
        records = [
            {
                "type": "user",
                "message": {"content": "Edit the file"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/main.py"}},
                        {"type": "text", "text": "Done!"},
                    ]
                },
                "timestamp": "2026-01-10T12:00:01Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(
            temp_project_folder, include_response_context=True
        )

        assert len(messages) == 1
        assert messages[0].response_metadata is not None
        assert "/main.py" in messages[0].response_metadata.files_modified

    def test_excludes_response_metadata_by_default(
        self, temp_project_folder: Path
    ) -> None:
        """Response metadata is not included by default."""
        records = [
            {
                "type": "user",
                "message": {"content": "Edit the file"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/main.py"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:01Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(temp_project_folder)

        assert len(messages) == 1
        assert messages[0].response_metadata is None
```

Also add CLI argument test:
```python
def test_include_response_context(self) -> None:
    """--include-response-context flag."""
    args = self._parse_messages_args(["--include-response-context"])
    assert args.include_response_context is True
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] New tests cover: ResponseMetadata, _extract_response_metadata, include_response_context flag

---

## Testing Strategy

### Unit Tests
- `TestResponseMetadata`: Dataclass creation and serialization
- `TestExtractResponseMetadata`: Helper function parsing logic
- `TestExtractUserMessagesWithResponseContext`: End-to-end extraction with response context
- `TestMessagesArgumentParsing`: New CLI flag parsing

### Integration Tests
- End-to-end CLI invocation with `--include-response-context`
- Verify JSONL output includes `response_metadata` field

## References

- Original issue: `.issues/enhancements/P3-ENH-031-response-context-capture.md`
- Existing UserMessage pattern: `scripts/little_loops/user_messages.py:35-67`
- Tool use parsing reference: `scripts/little_loops/fsm/evaluators.py:467-478`
- CLI argument pattern: `scripts/little_loops/cli.py:374-382`
- Test fixture pattern: `scripts/tests/test_user_messages.py:92-106`

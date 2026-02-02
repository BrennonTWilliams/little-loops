# FEAT-221: Extend ll-messages to include CLI command history - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-221-ll-messages-cli-command-history-extraction.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `ll-messages` CLI tool extracts user messages from Claude Code session logs stored in `~/.claude/projects/`. The module at `scripts/little_loops/user_messages.py` currently:

- Extracts `type == "user"` messages from JSONL logs
- Supports `--include-response-context` flag to capture assistant response metadata
- Uses `UserMessage` dataclass with `to_dict()` serialization
- Uses `ResponseMetadata` dataclass for aggregated response data

### Key Discoveries
- Existing tool_use parsing in `_aggregate_response_metadata()` at user_messages.py:188-205
- CLI argument parsing in `main_messages()` at cli.py:283-413
- Test patterns established in test_user_messages.py with temp fixtures and JSONL helpers
- The `--include-response-context` flag pattern can be followed for new flags

## Desired End State

Add three new CLI flags to `ll-messages`:
1. `--include-commands` - Include Bash commands alongside user messages
2. `--commands-only` - Extract only commands, no user messages
3. `--tools TOOL,...` - Filter command extraction to specific tools (default: Bash)

Output when commands included:
```json
{"type": "user", "content": "Run the tests", "timestamp": "...", ...}
{"type": "command", "content": "python -m pytest scripts/tests/ -v", "timestamp": "...", "tool": "Bash", ...}
```

### How to Verify
- `ll-messages --include-commands --stdout` outputs both user messages and commands interleaved by timestamp
- `ll-messages --commands-only --stdout` outputs only command records
- Tests pass for new functionality
- Existing behavior unchanged when flags not used

## What We're NOT Doing

- Not adding support for tools other than Bash initially (--tools flag is for future extensibility)
- Not changing the existing UserMessage dataclass or its serialization
- Not modifying how response_metadata works
- Not adding command result/output capture (just the command string)

## Problem Analysis

The `/ll:loop-suggester` skill currently only sees user prompts when analyzing workflows. Including the actual CLI commands Claude executed would significantly improve workflow detection accuracy - it would show what commands are repeatedly used for common tasks like testing, linting, git operations, etc.

## Solution Approach

1. Create new `CommandRecord` dataclass for CLI commands
2. Add `extract_commands()` function to parse Bash tool_use from assistant messages
3. Add CLI flags and merge/sort logic in `main_messages()`
4. Add comprehensive tests following existing patterns

## Implementation Phases

### Phase 1: Add CommandRecord Dataclass

#### Overview
Create the data structure for representing extracted CLI commands.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Changes**: Add `CommandRecord` dataclass after `ResponseMetadata` class (around line 103)

```python
@dataclass
class CommandRecord:
    """Extracted CLI command from assistant tool_use.

    Attributes:
        content: The command string that was executed
        timestamp: When the command was issued
        session_id: Claude Code session identifier
        uuid: Unique record identifier
        tool: Tool name (e.g., "Bash")
        cwd: Working directory when command was issued
        git_branch: Git branch active when command was issued
    """

    content: str
    timestamp: datetime
    session_id: str
    uuid: str
    tool: str
    cwd: str | None = None
    git_branch: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": "command",
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "uuid": self.uuid,
            "tool": self.tool,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
        }
```

Also update `__all__` to export `CommandRecord`.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/user_messages.py`

---

### Phase 2: Add extract_commands Function

#### Overview
Create the extraction function for CLI commands from assistant tool_use blocks.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py`
**Changes**: Add `extract_commands()` function after `extract_user_messages()` (around line 390)

```python
def extract_commands(
    project_folder: Path,
    limit: int | None = None,
    since: datetime | None = None,
    include_agent_sessions: bool = True,
    tools: list[str] | None = None,
) -> list[CommandRecord]:
    """Extract CLI commands from assistant tool_use messages.

    Parses assistant messages for tool_use blocks and extracts command strings.

    Args:
        project_folder: Path to Claude project folder
        limit: Maximum number of commands to return
        since: Only include commands after this datetime
        include_agent_sessions: Whether to include agent-*.jsonl files
        tools: Filter to specific tools (default: ["Bash"])

    Returns:
        Commands sorted by timestamp, most recent first.
    """
    if tools is None:
        tools = ["Bash"]

    commands: list[CommandRecord] = []

    # Find all JSONL files
    pattern = "*.jsonl"
    jsonl_files = list(project_folder.glob(pattern))

    for jsonl_file in jsonl_files:
        # Skip agent sessions if requested
        if not include_agent_sessions and jsonl_file.name.startswith("agent-"):
            continue

        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    cmds = _parse_command_record(record, jsonl_file, since, tools)
                    commands.extend(cmds)

        except OSError:
            # Skip files that can't be read
            continue

    # Sort by timestamp, most recent first
    commands.sort(key=lambda c: c.timestamp, reverse=True)

    # Apply limit
    if limit is not None:
        commands = commands[:limit]

    return commands


def _parse_command_record(
    record: dict,
    jsonl_file: Path,
    since: datetime | None,
    tools: list[str],
) -> list[CommandRecord]:
    """Parse CLI commands from an assistant record.

    Args:
        record: The JSON record from JSONL
        jsonl_file: Source file (for fallback timestamp)
        since: Filter for commands after this datetime
        tools: Tool names to extract (e.g., ["Bash"])

    Returns:
        List of CommandRecord for each matching tool_use block
    """
    # Filter for assistant messages only
    if record.get("type") != "assistant":
        return []

    message_data = record.get("message", {})
    content = message_data.get("content", [])

    if not isinstance(content, list):
        return []

    # Parse timestamp
    timestamp_str = record.get("timestamp", "")
    try:
        timestamp_str = timestamp_str.replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
    except (ValueError, AttributeError):
        timestamp = datetime.fromtimestamp(jsonl_file.stat().st_mtime)

    # Apply since filter
    if since and timestamp < since:
        return []

    commands: list[CommandRecord] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue

        tool_name = block.get("name", "")
        if tool_name not in tools:
            continue

        tool_input = block.get("input", {})
        command_str = tool_input.get("command", "")
        if not command_str:
            continue

        commands.append(
            CommandRecord(
                content=command_str,
                timestamp=timestamp,
                session_id=record.get("sessionId", ""),
                uuid=record.get("uuid", ""),
                tool=tool_name,
                cwd=record.get("cwd"),
                git_branch=record.get("gitBranch"),
            )
        )

    return commands
```

Also update `__all__` to export `extract_commands`.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/user_messages.py`

---

### Phase 3: Add CLI Flags and Merge Logic

#### Overview
Add the new CLI arguments and implement merging/output logic.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Update `main_messages()` function

1. Add import for `extract_commands` and `CommandRecord` (around line 293-298):
```python
from little_loops.user_messages import (
    CommandRecord,
    extract_commands,
    extract_user_messages,
    get_project_folder,
    print_messages_to_stdout,
    save_messages,
)
```

2. Add new CLI arguments after `--include-response-context` (around line 356):
```python
    parser.add_argument(
        "--include-commands",
        action="store_true",
        help="Include CLI commands (Bash) alongside user messages",
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Extract only CLI commands, no user messages",
    )
    parser.add_argument(
        "--tools",
        type=str,
        default="Bash",
        help="Comma-separated list of tools to extract commands from (default: Bash)",
    )
```

3. Update extraction and output logic (around line 391-411):
```python
    # Parse tools list
    tools_list = [t.strip() for t in args.tools.split(",")]

    # Extract data based on flags
    messages: list[UserMessage] = []
    commands: list[CommandRecord] = []

    if not args.commands_only:
        messages = extract_user_messages(
            project_folder=project_folder,
            limit=None,  # Apply limit after merging
            since=since,
            include_agent_sessions=not args.exclude_agents,
            include_response_context=args.include_response_context,
        )

    if args.include_commands or args.commands_only:
        commands = extract_commands(
            project_folder=project_folder,
            limit=None,  # Apply limit after merging
            since=since,
            include_agent_sessions=not args.exclude_agents,
            tools=tools_list,
        )

    if not messages and not commands:
        logger.warning("No user messages or commands found")
        return 0

    # Merge and sort by timestamp
    combined: list[UserMessage | CommandRecord] = []
    combined.extend(messages)
    combined.extend(commands)
    combined.sort(key=lambda x: x.timestamp, reverse=True)

    # Apply limit
    if args.limit is not None:
        combined = combined[: args.limit]

    logger.info(f"Found {len([x for x in combined if isinstance(x, UserMessage)])} messages")
    logger.info(f"Found {len([x for x in combined if isinstance(x, CommandRecord)])} commands")

    # Output
    if args.stdout:
        for item in combined:
            print(json.dumps(item.to_dict()))
    else:
        # Save to file
        output_path = _save_combined(combined, args.output)
        logger.success(f"Saved {len(combined)} records to: {output_path}")

    return 0
```

4. Add helper function for saving combined output (at end of file or after main_messages):
```python
def _save_combined(
    items: list[UserMessage | CommandRecord],
    output_path: Path | None = None,
) -> Path:
    """Save combined messages and commands to JSONL file."""
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.cwd() / ".claude"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"user-messages-{timestamp}.jsonl"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.to_dict()) + "\n")

    return output_path
```

Also add necessary imports at top of cli.py:
```python
from datetime import datetime
import json
```

Note: Need to import `UserMessage` and `CommandRecord` types for the union type annotation.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `ll-messages --include-commands --stdout -n 10` shows both types interleaved
- [ ] `ll-messages --commands-only --stdout -n 10` shows only commands

---

### Phase 4: Add Tests

#### Overview
Add comprehensive tests for the new functionality.

#### Changes Required

**File**: `scripts/tests/test_user_messages.py`
**Changes**: Add new test classes

```python
class TestCommandRecord:
    """Tests for CommandRecord dataclass."""

    def test_to_dict_basic(self) -> None:
        """to_dict() returns correct dictionary structure with type field."""
        cmd = CommandRecord(
            content="python -m pytest",
            timestamp=datetime(2026, 1, 10, 12, 0, 0),
            session_id="session-123",
            uuid="uuid-456",
            tool="Bash",
        )
        result = cmd.to_dict()

        assert result["type"] == "command"
        assert result["content"] == "python -m pytest"
        assert result["timestamp"] == "2026-01-10T12:00:00"
        assert result["session_id"] == "session-123"
        assert result["uuid"] == "uuid-456"
        assert result["tool"] == "Bash"
        assert result["cwd"] is None
        assert result["git_branch"] is None

    def test_to_dict_with_optional_fields(self) -> None:
        """to_dict() includes optional fields when set."""
        cmd = CommandRecord(
            content="git status",
            timestamp=datetime(2026, 1, 10, 12, 0, 0),
            session_id="session-123",
            uuid="uuid-456",
            tool="Bash",
            cwd="/path/to/project",
            git_branch="main",
        )
        result = cmd.to_dict()

        assert result["cwd"] == "/path/to/project"
        assert result["git_branch"] == "main"


class TestExtractCommands:
    """Tests for extract_commands function."""

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

    def test_extracts_bash_commands(self, temp_project_folder: Path) -> None:
        """Extracts Bash commands from assistant tool_use."""
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "python -m pytest"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        commands = extract_commands(temp_project_folder)

        assert len(commands) == 1
        assert commands[0].content == "python -m pytest"
        assert commands[0].tool == "Bash"

    def test_filters_non_assistant_messages(self, temp_project_folder: Path) -> None:
        """Ignores user messages."""
        records = [
            {
                "type": "user",
                "message": {"content": "Run tests"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:01Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        commands = extract_commands(temp_project_folder)

        assert len(commands) == 1
        assert commands[0].content == "pytest"

    def test_extracts_multiple_commands_from_one_message(self, temp_project_folder: Path) -> None:
        """Extracts multiple Bash commands from single assistant message."""
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "git status"}},
                        {"type": "text", "text": "Checking status..."},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "git diff"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        commands = extract_commands(temp_project_folder)

        assert len(commands) == 2

    def test_filters_by_tool_name(self, temp_project_folder: Path) -> None:
        """Only extracts commands from specified tools."""
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/foo.py"}},
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/bar.py"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        commands = extract_commands(temp_project_folder, tools=["Bash"])

        assert len(commands) == 1
        assert commands[0].tool == "Bash"

    def test_respects_limit(self, temp_project_folder: Path) -> None:
        """Respects the limit parameter."""
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": f"cmd{i}"}},
                    ]
                },
                "timestamp": f"2026-01-10T12:{i:02d}:00Z",
                "sessionId": "sess-1",
                "uuid": f"uuid-{i}",
            }
            for i in range(10)
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        commands = extract_commands(temp_project_folder, limit=3)

        assert len(commands) == 3

    def test_respects_since_filter(self, temp_project_folder: Path) -> None:
        """Filters commands by since datetime."""
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "old_cmd"}},
                    ]
                },
                "timestamp": "2026-01-01T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "new_cmd"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        since = datetime(2026, 1, 5, 0, 0, 0)
        commands = extract_commands(temp_project_folder, since=since)

        assert len(commands) == 1
        assert commands[0].content == "new_cmd"

    def test_skips_empty_commands(self, temp_project_folder: Path) -> None:
        """Skips tool_use blocks without command input."""
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": ""}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "valid"}},
                    ]
                },
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        commands = extract_commands(temp_project_folder)

        assert len(commands) == 1
        assert commands[0].content == "valid"
```

Also add import for `extract_commands` and `CommandRecord` at top of test file.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] All new tests pass

---

### Phase 5: Update CLI Argument Parsing Tests

#### Overview
Add tests for the new CLI arguments.

#### Changes Required

**File**: `scripts/tests/test_user_messages.py`
**Changes**: Update `TestMessagesArgumentParsing` class

Add new arguments to `_parse_messages_args` helper and add tests:

```python
    def _parse_messages_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_messages."""
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--limit", type=int, default=100)
        parser.add_argument("--since", type=str)
        parser.add_argument("-o", "--output", type=Path)
        parser.add_argument("--cwd", type=Path)
        parser.add_argument("--exclude-agents", action="store_true")
        parser.add_argument("--stdout", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")
        parser.add_argument("--include-response-context", action="store_true")
        parser.add_argument("--include-commands", action="store_true")
        parser.add_argument("--commands-only", action="store_true")
        parser.add_argument("--tools", type=str, default="Bash")
        return parser.parse_args(args)

    def test_include_commands(self) -> None:
        """--include-commands flag."""
        args = self._parse_messages_args(["--include-commands"])
        assert args.include_commands is True

    def test_commands_only(self) -> None:
        """--commands-only flag."""
        args = self._parse_messages_args(["--commands-only"])
        assert args.commands_only is True

    def test_tools_default(self) -> None:
        """--tools defaults to Bash."""
        args = self._parse_messages_args([])
        assert args.tools == "Bash"

    def test_tools_custom(self) -> None:
        """--tools accepts custom value."""
        args = self._parse_messages_args(["--tools", "Bash,Read"])
        assert args.tools == "Bash,Read"
```

Also update `test_default_args` to include new flags.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py::TestMessagesArgumentParsing -v`

---

## Testing Strategy

### Unit Tests
- `CommandRecord.to_dict()` returns correct structure with "type": "command"
- `extract_commands()` filters correctly by tool, since, limit
- `extract_commands()` handles multiple commands in single message
- CLI argument parsing for new flags

### Integration Tests
- End-to-end test with mixed user/assistant messages
- Verify timestamp-based merge ordering

## References

- Original issue: `.issues/features/P3-FEAT-221-ll-messages-cli-command-history-extraction.md`
- UserMessage dataclass: `scripts/little_loops/user_messages.py:36-73`
- ResponseMetadata pattern: `scripts/little_loops/user_messages.py:76-102`
- CLI parsing: `scripts/little_loops/cli.py:283-413`
- Test patterns: `scripts/tests/test_user_messages.py:96-161`

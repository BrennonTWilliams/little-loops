"""Extract and analyze user messages from Claude Code logs.

Provides functionality to extract user messages from Claude Code session
logs stored in ~/.claude/projects/.

Usage as CLI:
    ll-messages                    # Last 100 messages to file
    ll-messages -n 50              # Last 50 messages
    ll-messages --since 2026-01-01 # Since date
    ll-messages -o output.jsonl    # Custom output path
    ll-messages --stdout           # Print to terminal instead of file

Usage as library:
    from little_loops.user_messages import extract_user_messages, get_project_folder

    project_folder = get_project_folder()
    messages = extract_user_messages(project_folder, limit=50)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

__all__ = [
    "UserMessage",
    "ResponseMetadata",
    "get_project_folder",
    "extract_user_messages",
    "save_messages",
]


@dataclass
class UserMessage:
    """Extracted user message with metadata.

    Attributes:
        content: The text content of the user message
        timestamp: When the message was sent
        session_id: Claude Code session identifier
        uuid: Unique message identifier
        cwd: Working directory when message was sent
        git_branch: Git branch active when message was sent
        is_sidechain: Whether this was a sidechain message
    """

    content: str
    timestamp: datetime
    session_id: str
    uuid: str
    cwd: str | None = None
    git_branch: str | None = None
    is_sidechain: bool = False

    response_metadata: ResponseMetadata | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, object] = {
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "uuid": self.uuid,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "is_sidechain": self.is_sidechain,
        }
        if self.response_metadata is not None:
            result["response_metadata"] = self.response_metadata.to_dict()
        return result


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

    tools_used: list[dict[str, str | int]]
    files_read: list[str]
    files_modified: list[str]
    completion_status: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tools_used": self.tools_used,
            "files_read": self.files_read,
            "files_modified": self.files_modified,
            "completion_status": self.completion_status,
            "error_message": self.error_message,
        }


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
    tools_list: list[dict[str, str | int]] = [
        {"tool": name, "count": count} for name, count in tools_used.items()
    ]

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


def get_project_folder(cwd: Path | None = None) -> Path | None:
    """Map current directory to Claude Code project folder.

    Converts: /Users/brennon/foo/bar -> ~/.claude/projects/-Users-brennon-foo-bar

    Args:
        cwd: Working directory to map. If None, uses current directory.

    Returns:
        Path to Claude project folder, or None if it doesn't exist.
    """
    if cwd is None:
        cwd = Path.cwd()

    # Convert path to dash-separated format
    # /Users/brennon/foo/bar -> -Users-brennon-foo-bar
    path_str = str(cwd.resolve())
    encoded_path = path_str.replace("/", "-")

    # Build project folder path
    claude_projects = Path.home() / ".claude" / "projects"
    project_folder = claude_projects / encoded_path

    if project_folder.exists():
        return project_folder

    return None


def extract_user_messages(
    project_folder: Path,
    limit: int | None = None,
    since: datetime | None = None,
    include_agent_sessions: bool = True,
    include_response_context: bool = False,
) -> list[UserMessage]:
    """Extract user messages from all JSONL session files.

    Filters:
    - type == "user"
    - message.content is string (real user input)
    - message.content is array but [0].type != "tool_result"

    Args:
        project_folder: Path to Claude project folder
        limit: Maximum number of messages to return
        since: Only include messages after this datetime
        include_agent_sessions: Whether to include agent-*.jsonl files
        include_response_context: Whether to include metadata from assistant responses

    Returns:
        Messages sorted by timestamp, most recent first.
    """
    messages: list[UserMessage] = []

    # Find all JSONL files
    pattern = "*.jsonl"
    jsonl_files = list(project_folder.glob(pattern))

    for jsonl_file in jsonl_files:
        # Skip agent sessions if requested
        if not include_agent_sessions and jsonl_file.name.startswith("agent-"):
            continue

        try:
            # If we need response context, read all records first to pair user/assistant
            if include_response_context:
                all_records: list[dict] = []
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            all_records.append(record)
                        except json.JSONDecodeError:
                            continue

                # Process records, pairing user messages with their responses
                messages.extend(
                    _extract_messages_with_context(
                        all_records, jsonl_file, since
                    )
                )
            else:
                # Original behavior: stream through file
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg = _parse_user_record(record, jsonl_file, since)
                        if msg is not None:
                            messages.append(msg)

        except OSError:
            # Skip files that can't be read
            continue

    # Sort by timestamp, most recent first
    messages.sort(key=lambda m: m.timestamp, reverse=True)

    # Apply limit
    if limit is not None:
        messages = messages[:limit]

    return messages


def _parse_user_record(
    record: dict,
    jsonl_file: Path,
    since: datetime | None,
) -> UserMessage | None:
    """Parse a single user record into a UserMessage.

    Args:
        record: The JSON record from JSONL
        jsonl_file: Source file (for fallback timestamp)
        since: Filter for messages after this datetime

    Returns:
        UserMessage if valid user message, None otherwise
    """
    # Filter for user messages only
    if record.get("type") != "user":
        return None

    message_data = record.get("message", {})
    content = message_data.get("content")

    # Skip if no content
    if content is None:
        return None

    # Check if this is a real user message or tool_result
    if isinstance(content, str):
        # String content = real user message
        message_content = content
    elif isinstance(content, list):
        # Array content - check first element
        if len(content) > 0 and content[0].get("type") == "tool_result":
            # This is a tool result, skip it
            return None
        # Extract text from array (could be text blocks)
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif "content" in block:
                    text_parts.append(str(block.get("content", "")))
        message_content = "\n".join(text_parts) if text_parts else str(content)
    else:
        return None

    # Parse timestamp
    timestamp_str = record.get("timestamp", "")
    try:
        # Handle ISO 8601 format with Z suffix
        timestamp_str = timestamp_str.replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Convert to naive datetime for consistent comparison
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
    except (ValueError, AttributeError):
        # Use file modification time as fallback
        timestamp = datetime.fromtimestamp(jsonl_file.stat().st_mtime)

    # Apply since filter
    if since and timestamp < since:
        return None

    # Create message object
    return UserMessage(
        content=message_content,
        timestamp=timestamp,
        session_id=record.get("sessionId", ""),
        uuid=record.get("uuid", ""),
        cwd=record.get("cwd"),
        git_branch=record.get("gitBranch"),
        is_sidechain=record.get("isSidechain", False),
    )


def _extract_messages_with_context(
    records: list[dict],
    jsonl_file: Path,
    since: datetime | None,
) -> list[UserMessage]:
    """Extract user messages with response context from a list of records.

    Pairs each user message with the immediately following assistant response.

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
            # Look for the next assistant response
            response_metadata = None
            for j in range(i + 1, len(records)):
                next_record = records[j]
                if next_record.get("type") == "assistant":
                    response_metadata = _extract_response_metadata(next_record)
                    break
                elif next_record.get("type") == "user":
                    # Hit another user message, no response found
                    break

            msg.response_metadata = response_metadata
            messages.append(msg)

        i += 1

    return messages


def save_messages(
    messages: list[UserMessage],
    output_path: Path | None = None,
) -> Path:
    """Save messages to timestamped JSONL file.

    Args:
        messages: List of UserMessage objects to save
        output_path: Output file path. If None, uses default location.

    Returns:
        Path to the saved file.
    """
    if output_path is None:
        # Default: ./.claude/user-messages-{timestamp}.jsonl
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.cwd() / ".claude"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"user-messages-{timestamp}.jsonl"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg.to_dict()) + "\n")

    return output_path


def print_messages_to_stdout(messages: list[UserMessage]) -> None:
    """Print messages to stdout in JSONL format.

    Args:
        messages: List of UserMessage objects to print
    """
    import sys

    for msg in messages:
        print(json.dumps(msg.to_dict()), file=sys.stdout)

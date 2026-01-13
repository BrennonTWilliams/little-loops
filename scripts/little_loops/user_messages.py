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

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "uuid": self.uuid,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "is_sidechain": self.is_sidechain,
        }


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
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Filter for user messages only
                    if record.get("type") != "user":
                        continue

                    message_data = record.get("message", {})
                    content = message_data.get("content")

                    # Skip if no content
                    if content is None:
                        continue

                    # Check if this is a real user message or tool_result
                    if isinstance(content, str):
                        # String content = real user message
                        message_content = content
                    elif isinstance(content, list):
                        # Array content - check first element
                        if len(content) > 0 and content[0].get("type") == "tool_result":
                            # This is a tool result, skip it
                            continue
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
                        continue

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
                        continue

                    # Create message object
                    msg = UserMessage(
                        content=message_content,
                        timestamp=timestamp,
                        session_id=record.get("sessionId", ""),
                        uuid=record.get("uuid", ""),
                        cwd=record.get("cwd"),
                        git_branch=record.get("gitBranch"),
                        is_sidechain=record.get("isSidechain", False),
                    )
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

"""Session log linking for issue files.

Links Claude Code JSONL session files to issue files by appending
session log entries with command name, timestamp, and file path.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from little_loops.user_messages import get_project_folder

# Regex to isolate the ## Session Log section content
_SESSION_LOG_SECTION_RE = re.compile(
    r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)", re.MULTILINE | re.DOTALL
)
# Regex to extract backtick-quoted /ll:* command names from session log entries
_COMMAND_RE = re.compile(r"`(/[\w:-]+)`")


def parse_session_log(content: str) -> list[str]:
    """Extract distinct /ll:* command names from the ## Session Log section.

    Returns commands in first-seen order, deduplicated (preserves insertion order).

    Args:
        content: Full text of an issue markdown file.

    Returns:
        List of distinct command names (e.g. ["/ll:refine-issue", "/ll:ready-issue"]).
    """
    log_match = _SESSION_LOG_SECTION_RE.search(content)
    if not log_match:
        return []
    cmds = _COMMAND_RE.findall(log_match.group(1))
    # Deduplicate while preserving insertion order
    return list(dict.fromkeys(cmds))


def count_session_commands(content: str) -> dict[str, int]:
    """Count occurrences of each /ll:* command in the ## Session Log section.

    Unlike parse_session_log(), this does NOT deduplicate — each entry is counted.

    Args:
        content: Full text of an issue markdown file.

    Returns:
        Mapping of command name to occurrence count (e.g. {"/ll:refine-issue": 3}).
    """
    log_match = _SESSION_LOG_SECTION_RE.search(content)
    if not log_match:
        return {}
    counts: dict[str, int] = {}
    for cmd in _COMMAND_RE.findall(log_match.group(1)):
        counts[cmd] = counts.get(cmd, 0) + 1
    return counts


def get_current_session_jsonl(cwd: Path | None = None) -> Path | None:
    """Resolve the active Claude Code session's JSONL file path.

    Finds the most recently modified .jsonl file in the project's
    Claude Code session directory, excluding agent session files.

    Args:
        cwd: Working directory to map. If None, uses current directory.

    Returns:
        Path to the most recent JSONL file, or None if not found.
    """
    project_folder = get_project_folder(cwd)
    if project_folder is None:
        return None

    jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]
    if not jsonl_files:
        return None

    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


def append_session_log_entry(
    issue_path: Path,
    command: str,
    session_jsonl: Path | None = None,
) -> bool:
    """Append a session log entry to an issue file.

    Creates or appends to the ``## Session Log`` section with command name,
    ISO timestamp, and absolute path to the session JSONL file.

    Args:
        issue_path: Path to the issue markdown file.
        command: Command name (e.g., ``/ll:manage-issue``).
        session_jsonl: Path to session JSONL file. If None, auto-detected.

    Returns:
        True if entry was appended, False if session could not be resolved.
    """
    if session_jsonl is None:
        session_jsonl = get_current_session_jsonl()
    if session_jsonl is None:
        return False

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    entry = f"- `{command}` - {timestamp} - `{session_jsonl}`"

    content = issue_path.read_text()

    if "## Session Log" in content:
        # Append entry after existing section header (count=1 to only replace first occurrence)
        content = content.replace(
            "## Session Log\n",
            f"## Session Log\n{entry}\n",
            1,
        )
    else:
        # Add new section before --- Status footer if present, else at end
        if "\n---\n\n## Status" in content:
            content = content.replace(
                "\n---\n\n## Status",
                f"\n## Session Log\n{entry}\n\n---\n\n## Status",
            )
        else:
            content += f"\n\n## Session Log\n{entry}\n"

    issue_path.write_text(content)
    return True

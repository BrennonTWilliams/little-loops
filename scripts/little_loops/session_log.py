"""Session log linking for issue files.

Links Claude Code JSONL session files to issue files by appending
session log entries with command name, timestamp, and file path.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from little_loops.file_utils import atomic_write
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
    matches = list(_SESSION_LOG_SECTION_RE.finditer(content))
    if not matches:
        return []
    cmds = _COMMAND_RE.findall(matches[-1].group(1))
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
    matches = list(_SESSION_LOG_SECTION_RE.finditer(content))
    if not matches:
        return {}
    counts: dict[str, int] = {}
    for cmd in _COMMAND_RE.findall(matches[-1].group(1)):
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


def get_current_session_id(cwd: Path | None = None) -> str | None:
    """Resolve the active session's ID (the JSONL filename stem), or None.

    Used by issue-lifecycle EventBus producers (ENH-2462) to stamp
    ``issue_events.session_id`` at transition time. Prefers an explicit
    ``CLAUDE_SESSION_ID`` environment variable when a host sets one, falling
    back to the most recently modified session JSONL for the project.
    """
    import os

    env_val = os.environ.get("CLAUDE_SESSION_ID")
    if env_val:
        return env_val
    jsonl = get_current_session_jsonl(cwd)
    return jsonl.stem if jsonl is not None else None


def append_session_log_entry(
    issue_path: Path,
    command: str,
    session_jsonl: Path | None = None,
) -> bool:
    """Append a session log entry to an issue file.

    Creates or appends to the ``## Session Log`` section with command name,
    ISO timestamp, and the session JSONL filename (the session id; not the
    absolute path, which is machine-specific).

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
    # Record only the session JSONL filename (the session id), not the absolute
    # path: the home-directory prefix is machine-specific and leaks the user's
    # local layout into committed issue files. The session id maps back to a
    # full path via .ll/history.db when needed.
    entry = f"- `{command}` - {timestamp} - `{session_jsonl.name}`"

    content = issue_path.read_text()

    if "## Session Log" in content:
        # Insert entry after the last ## Session Log header (real section, not a fake in code block)
        idx = content.rfind("## Session Log\n")
        insert_pos = idx + len("## Session Log\n")
        content = content[:insert_pos] + entry + "\n" + content[insert_pos:]
    else:
        # Add new section before --- Status footer if present, else at end
        if "\n---\n\n## Status" in content:
            content = content.replace(
                "\n---\n\n## Status",
                f"\n## Session Log\n{entry}\n\n---\n\n## Status",
            )
        else:
            content += f"\n\n## Session Log\n{entry}\n"

    atomic_write(issue_path, content)
    return True

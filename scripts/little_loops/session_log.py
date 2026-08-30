"""Session log linking for issue files.

Links Claude Code JSONL session files to issue files by appending
session log entries with command name, timestamp, and file path.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from little_loops.file_utils import acquire_lock, atomic_write, issue_lock_path
from little_loops.text_utils import fence_spans, in_fence
from little_loops.user_messages import get_sessions_folder

# Line-anchored ``## Session Log`` heading (BUG-3202): requires the literal
# two-hash-space prefix at line start, so an ``### Session Log`` H3 no longer
# substring-matches (the old ``str.rfind("## Session Log\n")`` scan did).
_SESSION_LOG_HEADING_RE = re.compile(r"^## Session Log\s*$", re.MULTILINE)
# Fence-blind terminator shape reused by _session_log_body's fence-aware scan
# below: either the next H2 heading or the next frontmatter-style '---' rule.
_SESSION_LOG_TERMINATOR_RE = re.compile(r"\n(?:##|---)")
# Regex to extract backtick-quoted /ll:* command names from session log entries
_COMMAND_RE = re.compile(r"`(/[\w:-]+)`")
# Discriminated Session Log command string for a --gap-analysis refine pass
# (BUG-3356): exempt from commands.max_refine_count, unlike the bare
# "/ll:refine-issue" full-rewrite entry. Single source of truth — readers
# (program_design.py's _REFINE_ENTRY, research_triage.py's staleness check)
# import this rather than hardcoding the literal.
GAP_REFINE_COMMAND = "/ll:refine-issue:gap-analysis"
# Same, but capturing the entry's ISO timestamp (ENH-2971). The time portion is
# optional: the oldest entries carry a bare date.
_TIMESTAMPED_ENTRY_RE = re.compile(
    r"`(/[\w:-]+)`\s*-\s*(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)?)"
)


def session_log_body(content: str) -> str | None:
    """Return the last (fence-excluded) ``## Session Log`` section's raw body.

    Shared read-side extraction for :func:`parse_session_log`,
    :func:`count_session_commands`, and :func:`last_command_timestamp`
    (BUG-3202) — and exported so other modules (e.g. ``cli/issues/search.py``'s
    last-activity-date sort) reuse it instead of a fifth fence-blind local
    regex.

    A ``## Session Log``-shaped line inside a fenced code block is excluded
    from heading resolution via :func:`~little_loops.text_utils.fence_spans`/
    :func:`~little_loops.text_utils.in_fence`, and the end-boundary scan (the
    next ``\\n##`` or ``\\n---``) is fence-aware too, so a fenced example
    containing either shape no longer truncates the real section early.

    Args:
        content: Full text of an issue markdown file.

    Returns:
        The section body, or None when no (non-fenced) ``## Session Log``
        heading exists.
    """
    spans = fence_spans(content)
    headings = [
        m
        for m in _SESSION_LOG_HEADING_RE.finditer(content)
        if not in_fence(m.start(), m.end(), spans)
    ]
    if not headings:
        return None

    start = headings[-1].end()
    leading_blank = re.compile(r"\n+").match(content, start)
    if leading_blank:
        start = leading_blank.end()

    end = len(content)
    for term in _SESSION_LOG_TERMINATOR_RE.finditer(content, start):
        if not in_fence(term.start(), term.end(), spans):
            end = term.start()
            break
    return content[start:end]


def parse_session_log(content: str) -> list[str]:
    """Extract distinct /ll:* command names from the ## Session Log section.

    Returns commands in first-seen order, deduplicated (preserves insertion order).

    Args:
        content: Full text of an issue markdown file.

    Returns:
        List of distinct command names (e.g. ["/ll:refine-issue", "/ll:ready-issue"]).
    """
    body = session_log_body(content)
    if body is None:
        return []
    cmds = _COMMAND_RE.findall(body)
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
    body = session_log_body(content)
    if body is None:
        return {}
    counts: dict[str, int] = {}
    for cmd in _COMMAND_RE.findall(body):
        counts[cmd] = counts.get(cmd, 0) + 1
    return counts


def last_command_timestamp(content: str, command: str) -> datetime | None:
    """Return the most recent ``## Session Log`` timestamp for *command*.

    The read side of :func:`append_session_log_entry`. Entries look like
    ``- `/ll:refine-issue` - 2026-08-01T12:34:56 - `session.jsonl` ``; the
    older date-only form (``- `/ll:capture-issue` - 2026-08-01``) is also
    accepted and read as midnight.

    Returns a **UTC-aware** datetime, deliberately unlike
    ``issue_history.parsing._parse_iso_datetime``'s naive-local convention:
    :func:`append_session_log_entry` writes ``datetime.now(UTC)`` without a
    ``Z`` suffix, so reading those stamps as local time would skew every
    comparison by the local UTC offset.

    Args:
        content: Full text of an issue markdown file.
        command: Command name to match, e.g. ``"/ll:refine-issue"``.

    Returns:
        The newest matching timestamp, or None when the command has no dated
        entry (or no Session Log section exists).
    """
    body = session_log_body(content)
    if body is None:
        return None
    stamps: list[datetime] = []
    for entry in _TIMESTAMPED_ENTRY_RE.finditer(body):
        if entry.group(1) != command:
            continue
        try:
            parsed = datetime.fromisoformat(entry.group(2).rstrip("Z"))
        except ValueError:
            continue
        stamps.append(parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed)
    return max(stamps) if stamps else None


def get_current_session_jsonl(cwd: Path | None = None) -> Path | None:
    """Resolve the active host session's JSONL file path.

    Finds the most recently modified .jsonl file in the project's session
    directory (host auto-detected via ``LL_HOOK_HOST``), excluding agent
    session files. Resolves through ``get_sessions_folder`` so hosts whose
    session JSONL nests one level deeper — qwen's ``chats/`` (ENH-3165) —
    are reached too.

    Args:
        cwd: Working directory to map. If None, uses current directory.

    Returns:
        Path to the most recent JSONL file, or None if not found.
    """
    project_folder = get_sessions_folder(cwd)
    if project_folder is None:
        return None

    jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]
    if not jsonl_files:
        return None

    # Guard the stat() against a TOCTOU race (BUG-2489): the live host process can
    # rotate or delete a .jsonl between the glob() above and the stat() below. Skip
    # files that vanish rather than propagating FileNotFoundError, which would poison
    # callers such as complete_issue_lifecycle, get_current_session_id, and the FSM
    # prompt-mode payload builder.
    dated: list[tuple[float, Path]] = []
    for f in jsonl_files:
        try:
            dated.append((f.stat().st_mtime, f))
        except OSError:
            continue
    if not dated:
        return None
    return max(dated, key=lambda pair: pair[0])[1]


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


def read_latest_effort_from_session_jsonl(session_jsonl: Path) -> str | None:
    """Read the most recent ``"effort"`` field from a session JSONL's assistant lines.

    ENH-2885: the host CLI reports the actual reasoning-effort level it applied
    as a top-level ``"effort"`` field on every ``type: "assistant"`` line. Scans
    all lines (last-write-wins, mirroring how callers take ``usage_events[-1]``
    for the observed ``model`` value) so the most recent assistant turn's effort
    wins over earlier ones in the same file.

    Args:
        session_jsonl: Path to a session JSONL file.

    Returns:
        The most recent assistant-line effort value, or None if the file is
        missing, unreadable, or no assistant line carries an ``"effort"`` field.
    """
    import json

    latest: str | None = None
    try:
        with session_jsonl.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "assistant":
                    continue
                effort = record.get("effort")
                if effort:
                    latest = effort
    except OSError:
        return None
    return latest


def format_session_log_entry(command: str, session_jsonl: Path | None = None) -> str | None:
    """Render the session-log bullet for ``command``, or None if no session resolves.

    Extracted from :func:`append_session_log_entry` (FEAT-3149) so the MCP
    ``issue_append_log`` tool's dry-run can show the exact line it would insert
    without duplicating — and therefore drifting from — this format.

    Args:
        command: Command name (e.g., ``/ll:manage-issue``).
        session_jsonl: Path to session JSONL file. If None, auto-detected.

    Returns:
        The formatted bullet, or None when the current session cannot be resolved.
    """
    if session_jsonl is None:
        session_jsonl = get_current_session_jsonl()
    if session_jsonl is None:
        return None

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    # Record only the session JSONL filename (the session id), not the absolute
    # path: the home-directory prefix is machine-specific and leaks the user's
    # local layout into committed issue files. The session id maps back to a
    # full path via .ll/history.db when needed.
    return f"- `{command}` - {timestamp} - `{session_jsonl.name}`"


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
    entry = format_session_log_entry(command, session_jsonl)
    if entry is None:
        return False

    # BUG-3150: the read and the write are one read-modify-write and must be
    # atomic against a concurrent `ll-issues set-status`/`link` or another
    # append. The write was already atomic (no torn file), but two concurrent
    # appends could each read the pre-entry content and one entry would be lost.
    # Locking here rather than in `cmd_append_log` covers the ll-auto
    # (issue_lifecycle.py) and ll-parallel (parallel/orchestrator.py) callers
    # too, which is where concurrent appends actually happen.
    #
    # flock contends within a single process as well as across processes, so no
    # caller may hold this same lock when calling in. `set-status` and `link`
    # (the other holders) do not call this function.
    with acquire_lock(issue_lock_path(issue_path)):
        content = issue_path.read_text()

        spans = fence_spans(content)
        headings = [
            m
            for m in _SESSION_LOG_HEADING_RE.finditer(content)
            if not in_fence(m.start(), m.end(), spans)
        ]

        if headings:
            # Insert entry after the last real (fence-excluded, line-anchored
            # H2) ## Session Log heading — never one quoted inside a fence,
            # and never an ### Session Log H3 (BUG-3202).
            match = headings[-1]
            newline_pos = content.find("\n", match.end())
            insert_pos = newline_pos + 1 if newline_pos != -1 else len(content)
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

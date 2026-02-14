# FEAT-323: Link Session JSONL Logs to Issue Files - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-323-link-session-jsonl-logs-to-issue-files.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

- No session log linking exists in issue files
- JSONL discovery logic lives in `scripts/little_loops/user_messages.py` (`get_project_folder()` at line 318)
- Issue file modification patterns exist in `issue_lifecycle.py` (`_prepare_issue_content` at line 222)
- `issue-sections.json` lacks a `Session Log` section definition

### Key Discoveries
- `user_messages.py:318-344` - `get_project_folder()` maps cwd to `~/.claude/projects/-path-encoded/`
- `user_messages.py:373-375` - JSONL files discovered via `project_folder.glob("*.jsonl")`
- `issue_lifecycle.py:222-235` - Pattern for appending sections to issue files with idempotency check
- Commands are markdown files in `commands/` — they instruct Claude, not Python code

## Desired End State

Issue files contain a `## Session Log` section with timestamped entries linking to JSONL session files. A Python utility module provides `get_current_session_jsonl()` and `append_session_log_entry()`. Commands reference calling this utility.

### How to Verify
- Unit tests for utility functions pass
- Manual: run `/ll:capture-issue` and check that the created issue has a Session Log entry

## What We're NOT Doing

- Not building the SQLite history DB (FEAT-324) — that depends on this
- Not modifying `ll-messages` CLI behavior
- Not adding session log entries to already-completed issues retroactively
- Not implementing the command-side integration in this PR (commands are markdown instruction files — they need manual text additions, which we'll do, but the actual runtime behavior depends on Claude following those instructions)

## Solution Approach

1. Create `scripts/little_loops/session_log.py` with two functions:
   - `get_current_session_jsonl()` — reuses `get_project_folder()`, finds most recently modified `.jsonl`
   - `append_session_log_entry()` — appends/creates `## Session Log` section in an issue file
2. Add `Session Log` to `issue-sections.json`
3. Update command markdown files to instruct appending session log entries
4. Add tests

## Code Reuse & Integration

- **Reuse**: `user_messages.get_project_folder()` for JSONL path discovery
- **Pattern**: `issue_lifecycle._prepare_issue_content()` for section append pattern
- **New**: `session_log.py` module (small, justified — new capability)

## Implementation Phases

### Phase 1: Create session_log.py utility module

#### Changes Required

**File**: `scripts/little_loops/session_log.py` (NEW)

```python
"""Session log linking for issue files.

Links Claude Code JSONL session files to issue files by appending
session log entries with command name, timestamp, and file path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from little_loops.user_messages import get_project_folder


def get_current_session_jsonl(cwd: Path | None = None) -> Path | None:
    """Resolve the active Claude Code session's JSONL file path.

    Finds the most recently modified .jsonl file in the project's
    Claude Code session directory.

    Args:
        cwd: Working directory to map. If None, uses current directory.

    Returns:
        Path to the most recent JSONL file, or None if not found.
    """
    project_folder = get_project_folder(cwd)
    if project_folder is None:
        return None

    jsonl_files = list(project_folder.glob("*.jsonl"))
    if not jsonl_files:
        return None

    # Return most recently modified file (likely the active session)
    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


def append_session_log_entry(
    issue_path: Path,
    command: str,
    session_jsonl: Path | None = None,
) -> bool:
    """Append a session log entry to an issue file.

    Creates or appends to the '## Session Log' section.

    Args:
        issue_path: Path to the issue markdown file.
        command: Command name (e.g., '/ll:manage-issue').
        session_jsonl: Path to session JSONL file. If None, auto-detected.

    Returns:
        True if entry was appended, False if session could not be resolved.
    """
    if session_jsonl is None:
        session_jsonl = get_current_session_jsonl()
    if session_jsonl is None:
        return False

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    entry = f"- `{command}` - {timestamp} - `{session_jsonl}`"

    content = issue_path.read_text()

    if "## Session Log" in content:
        # Append entry after existing section header
        content = content.replace(
            "## Session Log\n",
            f"## Session Log\n{entry}\n",
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
```

#### Success Criteria
- [ ] Module created with type hints
- [ ] `python -c "from little_loops.session_log import get_current_session_jsonl, append_session_log_entry"`

### Phase 2: Add Session Log to issue-sections.json

**File**: `templates/issue-sections.json`
Add to `common_sections`:
```json
"Session Log": {
    "required": false,
    "description": "Links to Claude Code JSONL session files involved in this issue's lifecycle",
    "ai_usage": "LOW",
    "human_value": "MEDIUM",
    "creation_template": ""
}
```

### Phase 3: Update command markdown files

Add instruction text to each command's completion/creation section:

**Files**: `commands/manage_issue.md`, `commands/capture_issue.md`, `commands/scan_codebase.md`, `commands/refine_issue.md`

Each gets a brief instruction paragraph telling Claude to call `append_session_log_entry()` or manually append a `## Session Log` entry after the relevant action.

### Phase 4: Add tests

**File**: `scripts/tests/test_session_log.py` (NEW)

Test:
- `get_current_session_jsonl()` with mock project folder
- `append_session_log_entry()` — new section creation
- `append_session_log_entry()` — append to existing section
- `append_session_log_entry()` — returns False when no session found
- Idempotency: multiple calls append multiple entries

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/test_session_log.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Mock `get_project_folder()` to return temp dirs with fake .jsonl files
- Test file content manipulation with `tmp_path` fixture
- Test edge cases: no project folder, no jsonl files, missing section

### Integration
- Manual: run a command and verify session log appears in issue file

---
discovered_commit: 64342c8
discovered_branch: main
discovered_date: 2026-01-09T22:40:00Z
---

# FEAT-011: User Message History Extraction

## Summary

Create a Python CLI tool (`ll-messages`) that extracts user-sent messages and metadata from Claude Code's JSONL logs for the current project, outputting them to a timestamped JSONL file. This enables downstream analysis including command suggestions, workflow pattern detection, and personalized recommendations.

## Motivation

User message history is valuable data that's currently locked in Claude Code's session logs:

- **Command suggestions**: Analyze past requests to suggest relevant `/ll:*` commands
- **Workflow patterns**: Identify repeated multi-step sequences that could be automated
- **Hook generation**: Spot frustrations ("don't do X") to create preventive hooks
- **Project onboarding**: "Here's what people commonly ask about this codebase"
- **Usage analytics**: Understand how the plugin is being used

Claude Code stores conversation history in `~/.claude/projects/{dash-format-path}/*.jsonl` but there's no easy way to query this data across sessions.

## Proposed Implementation

### 1. Core Module: `scripts/little_loops/messages.py`

```python
"""Extract and analyze user messages from Claude Code logs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

@dataclass
class UserMessage:
    """Extracted user message with metadata."""
    content: str
    timestamp: datetime
    session_id: str
    uuid: str
    cwd: str | None = None
    git_branch: str | None = None
    is_sidechain: bool = False
    entities: list[str] | None = None  # Extracted file paths, commands, concepts

def get_project_folder(cwd: Path | None = None) -> Path | None:
    """Map current directory to Claude Code project folder.

    Converts: /Users/brennon/foo/bar → ~/.claude/projects/-Users-brennon-foo-bar
    """
    ...

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

    Returns messages sorted by timestamp, most recent first.
    """
    ...

def save_messages(
    messages: list[UserMessage],
    output_path: Path | None = None,
) -> Path:
    """Save messages to timestamped JSONL file.

    Default output: .claude/user-messages-{timestamp}.jsonl
    """
    ...
```

### 2. CLI Entry Point: `ll-messages`

Add to `scripts/pyproject.toml`:

```toml
[project.scripts]
ll-messages = "little_loops.messages_cli:main"
```

CLI interface:

```
ll-messages extract [OPTIONS]

Options:
  --limit N          Maximum messages to extract
  --since DATE       Only messages after this date (ISO 8601)
  --output PATH      Output file path (default: .claude/user-messages-{timestamp}.jsonl)
  --include-agents   Include messages from agent sessions (default: true)
  --format FORMAT    Output format: jsonl, json, yaml, csv (default: jsonl)
  --extract-entities Extract file paths, commands, concepts from messages (default: true)

ll-messages suggest [OPTIONS]   # Quick pattern-based command suggestions
ll-messages stats [OPTIONS]     # Usage analytics
```

### 3. Output JSONL Schema

Simplified format optimized for downstream analysis:

```json
{"content": "Help me implement feature X", "timestamp": "2026-01-09T22:29:32.603Z", "session_id": "686d1cb9-...", "cwd": "/Users/brennon/project", "git_branch": "main", "entities": ["feature X"]}
{"content": "Fix the bug in checkout.py", "timestamp": "2026-01-09T21:15:00.000Z", "session_id": "abc123-...", "cwd": "/Users/brennon/project", "git_branch": "feature/checkout", "entities": ["checkout.py"]}
```

### 3.1 Entity Extraction

Entities are automatically extracted from message content:

| Entity Type | Pattern Examples | Extraction Method |
|-------------|------------------|-------------------|
| File paths | `checkout.py`, `README.md` | Regex: `[\w/-]+\.(md\|py\|json\|yaml\|js\|ts)` |
| Directory refs | `phase-1-module-1`, `src/` | Regex: `phase-\d+`, path patterns |
| Slash commands | `/ll:commit`, `/help` | Regex: `^/[\w:-]+` |
| Concepts | quoted terms, capitalized phrases | Heuristic extraction |

### 4. Log Structure Reference

**Location**: `~/.claude/projects/{dash-format-path}/`

**Files**:
- `{uuid}.jsonl` - Regular session files
- `agent-{id}.jsonl` - Subagent session files

**User Message Structure**:
```json
{
  "type": "user",
  "timestamp": "2026-01-09T22:29:32.603Z",
  "uuid": "...",
  "sessionId": "...",
  "parentUuid": "...",
  "cwd": "...",
  "gitBranch": "main",
  "userType": "...",
  "isSidechain": false,
  "message": {
    "role": "user",
    "content": "..." | [...]
  }
}
```

**Filtering Logic**:
- Include: `type == "user"` AND `message.content` is string
- Include: `type == "user"` AND `message.content` is array AND `[0].type != "tool_result"`
- Exclude: Tool result responses (these are system-generated)

### 5. Future: Command Suggestion (`ll-messages suggest`)

Quick pattern-based command suggestions:

```python
def suggest_commands(messages: list[UserMessage]) -> list[CommandSuggestion]:
    """Analyze message patterns and suggest relevant ll commands.

    Patterns to detect:
    - "run tests" / "check tests" → /ll:run_tests
    - "commit" / "create commit" → /ll:commit
    - "fix lint" / "format code" → /ll:check_code fix
    - "create issue" / "bug report" → /ll:scan_codebase
    """
    ...
```

For comprehensive workflow analysis and automation proposals, see:
- **FEAT-026**: Workflow Pattern Analyzer Agent
- **FEAT-027**: Workflow Sequence Analyzer Agent
- **FEAT-028**: Workflow Automation Proposer Agent
- **FEAT-029**: `/ll:analyze-workflows` Command

### 6. Integration with Existing Commands

Add `/ll:messages` slash command as wrapper:

```markdown
---
description: Extract and analyze user message history
allowed_tools: ["Bash", "Read", "Write"]
---

# /ll:messages

Run `ll-messages` CLI tool with provided arguments.

Arguments: $ARGUMENTS
```

## Location

- **New Module**: `scripts/little_loops/messages.py`
- **New Module**: `scripts/little_loops/messages_cli.py`
- **New Command**: `commands/messages.md`
- **Modified**: `scripts/pyproject.toml` (add entry point)

## Current Behavior

No mechanism exists to extract or analyze user message history. Claude Code logs are stored but not queryable.

## Expected Behavior

```bash
# Extract last 50 messages to JSONL
$ ll-messages extract --limit 50
Extracted 50 messages to .claude/user-messages-2026-01-09T22-45-00.jsonl

# Extract messages from last week
$ ll-messages extract --since 2026-01-02

# Future: Get command suggestions
$ ll-messages suggest
Based on your recent messages, you might find these commands useful:
  /ll:run_tests - You frequently ask to "run tests" (12 times this week)
  /ll:commit - You often request commits manually (8 times)
```

## Impact

- **Severity**: Medium - Enables new analysis capabilities
- **Effort**: Medium - Core extraction is straightforward, suggestion engine is more complex
- **Risk**: Low - Read-only access to existing logs, no modification

## Privacy Considerations

- User messages may contain sensitive information
- Output files should be created in `.claude/` (typically gitignored)
- Consider adding `--redact` option to mask file paths, secrets patterns

## Dependencies

None - standalone feature

## Blocked By

None

## Blocks

- FEAT-026: Workflow Pattern Analyzer Agent
- FEAT-027: Workflow Sequence Analyzer Agent
- FEAT-028: Workflow Automation Proposer Agent
- FEAT-029: `/ll:analyze-workflows` Command
- ENH-031: Response Context Capture

## Labels

`feature`, `cli-tool`, `analytics`, `user-experience`

---

## Status

**Open** | Created: 2026-01-09 | Priority: P2

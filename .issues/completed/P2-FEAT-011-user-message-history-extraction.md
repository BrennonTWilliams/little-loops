---
discovered_commit: 64342c8
discovered_branch: main
discovered_date: 2026-01-09T22:40:00Z
---

# FEAT-011: User Message History Extraction

## Summary

~~Create a Python CLI tool (`ll-messages`) that extracts user-sent messages and metadata from Claude Code's JSONL logs for the current project, outputting them to a timestamped JSONL file.~~

**Update (2026-01-12)**: Core extraction functionality is implemented. This issue now tracks **remaining enhancements**: entity extraction, additional output formats, slash command wrapper, and future analysis subcommands.

## Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| `UserMessage` dataclass | Implemented | `scripts/little_loops/user_messages.py` |
| `get_project_folder()` | Implemented | `scripts/little_loops/user_messages.py` |
| `extract_user_messages()` | Implemented | `scripts/little_loops/user_messages.py` |
| `save_messages()` | Implemented | `scripts/little_loops/user_messages.py` |
| `print_messages_to_stdout()` | Implemented | `scripts/little_loops/user_messages.py` |
| CLI entry point (`ll-messages`) | Implemented | `scripts/little_loops/cli.py:main_messages` |
| `-n/--limit` option | Implemented | Default: 100 |
| `--since` option | Implemented | ISO date filter |
| `-o/--output` option | Implemented | Custom output path |
| `--cwd` option | Implemented | Override working directory |
| `--exclude-agents` option | Implemented | Exclude agent sessions |
| `--stdout` option | Implemented | Print to terminal |
| `-v/--verbose` option | Implemented | Progress output |
| **Entity extraction** | **Not implemented** | `entities` field in UserMessage |
| **`--format` option** | **Not implemented** | json, yaml, csv formats |
| **`--extract-entities` flag** | **Not implemented** | Toggle entity extraction |
| **`/ll:messages` command** | **Not implemented** | `commands/messages.md` |
| **`ll-messages suggest`** | **Not implemented** | Future subcommand |
| **`ll-messages stats`** | **Not implemented** | Future subcommand |

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

    Converts: /home/user/foo/bar → ~/.claude/projects/-home-user-foo-bar
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
{"content": "Help me implement feature X", "timestamp": "2026-01-09T22:29:32.603Z", "session_id": "686d1cb9-...", "cwd": "/path/to/project", "git_branch": "main", "entities": ["feature X"]}
{"content": "Fix the bug in checkout.py", "timestamp": "2026-01-09T21:15:00.000Z", "session_id": "abc123-...", "cwd": "/path/to/project", "git_branch": "feature/checkout", "entities": ["checkout.py"]}
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

- **Existing Module**: `scripts/little_loops/user_messages.py` (core extraction logic)
- **Existing CLI**: `scripts/little_loops/cli.py` (`main_messages` entry point)
- **New Command**: `commands/messages.md` (not yet created)

## Current Behavior

The `ll-messages` CLI tool is fully functional for basic extraction:

```bash
ll-messages                          # Last 100 messages to file
ll-messages -n 50                    # Last 50 messages
ll-messages --since 2026-01-01       # Messages since date
ll-messages -o output.jsonl          # Custom output path
ll-messages --stdout                 # Print to terminal
ll-messages --exclude-agents         # Exclude agent sessions
ll-messages --cwd /path/to/project   # Specify project directory
ll-messages -v                       # Verbose progress output
```

Output is JSONL with: `content`, `timestamp`, `session_id`, `uuid`, `cwd`, `git_branch`, `is_sidechain`.

## Expected Behavior (Remaining Enhancements)

```bash
# Entity extraction (adds file paths, commands, concepts to output)
$ ll-messages --extract-entities
{"content": "Fix checkout.py", ..., "entities": ["checkout.py"]}

# Alternative output formats
$ ll-messages --format json    # Pretty JSON array
$ ll-messages --format csv     # CSV with headers
$ ll-messages --format yaml    # YAML list

# Future: Command suggestions
$ ll-messages suggest
Based on your recent messages, you might find these commands useful:
  /ll:run_tests - You frequently ask to "run tests" (12 times this week)
  /ll:commit - You often request commits manually (8 times)

# Future: Usage statistics
$ ll-messages stats
Sessions: 47 | Messages: 312 | Most active: Mon-Wed
Top topics: testing (23%), refactoring (18%), debugging (15%)
```

## Impact

- **Severity**: Low - Core functionality complete, enhancements are nice-to-have
- **Effort**: Low - Entity extraction is regex-based; formats are straightforward
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

`feature`, `cli-tool`, `analytics`, `user-experience`, `partially-complete`

---

## Design Decisions

### Project Folder Matching: Exact Match Only

**Decision**: Do NOT implement `--include-related` / `--include-outside-directories` feature.

**Context**: The Bash prototype (`get_recent_user_messages.sh`) included a `--include-outside-directories` flag that searched for related project folders (e.g., `myproject` and `myproject-history`). The question was whether to port this to the Python implementation.

**Options Considered**:

| Option | Description |
|--------|-------------|
| 1. Keep it | Port wildcard/related folder matching from Bash script |
| 2. Exact match only | Only search the exact current directory's project folder |

**Recommendation: Option 2 - Exact match only**

**Rationale**:

1. **Claude Code uses exact path mapping** - The `~/.claude/projects/` structure is deterministic. Each working directory maps to exactly one project folder (`/Users/foo/bar` → `-Users-foo-bar`). There's no official "related projects" concept in Claude Code.

2. **False positive risk** - Wildcard matching (`*$search_term*`) could match unrelated projects. E.g., searching for `api` might match `api`, `api-v2`, `rapid-tools`, `company-api-client`.

3. **Complexity reduction** - The Bash script is 711 lines vs 319 for Python. ~180 lines (25%) of the Bash script is related-folder logic.

4. **Composable alternative** - Users needing messages from multiple projects can run the tool multiple times with different `--cwd` values and combine outputs:
   ```bash
   python extract_user_messages.py --cwd /path/to/project1 -o p1.jsonl
   python extract_user_messages.py --cwd /path/to/project2 -o p2.jsonl
   cat p1.jsonl p2.jsonl | sort -k2 > combined.jsonl
   ```

5. **YAGNI** - Feature can be added later if real demand emerges.

**Date**: 2026-01-12

---

## Status

**Complete** | Created: 2026-01-09 | Closed: 2026-01-12 | Priority: P2

Core extraction functionality fully implemented via `ll-messages` CLI tool.

### Closure Notes

Remaining items were evaluated and deemed unnecessary:
- `/ll:messages` slash command - Redundant wrapper around functional CLI
- Entity extraction - Handled by FEAT-026 (workflow-pattern-analyzer)
- Output formats - Low value; JSONL sufficient for programmatic use
- `suggest` subcommand - Superseded by FEAT-029 (`/ll:analyze-workflows`)
- `stats` subcommand - Can be added as separate enhancement if needed

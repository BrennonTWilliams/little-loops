---
discovered_date: 2026-02-02
discovered_by: capture_issue
---

# FEAT-221: Extend ll-messages to optionally include CLI command history

## Summary

Add a `--include-commands` flag to `ll-messages` that extracts CLI/Bash commands executed by Claude alongside user messages, enabling `/ll:loop-suggester` to include tool invocations in workflow analysis and proposed loop configurations.

## Context

**Direct mode**: User description: "Extend `ll-messages` to optionally included CLI command history, for usage by `/ll:loop-suggestions` to include CLI commands in workflow analysis and proposed loops"

The `/ll:loop-suggester` skill analyzes user message patterns to suggest FSM loop configurations. However, it currently only sees what users *asked* for, not what commands Claude *executed*. Including the actual CLI commands (git, npm, pytest, etc.) would significantly improve workflow detection accuracy.

## Current Behavior

- `ll-messages` extracts only `type == "user"` messages from JSONL logs
- Output contains: `content`, `timestamp`, `session_id`, `uuid`, `cwd`, `git_branch`, `is_sidechain`
- No visibility into tool calls or Bash commands executed by Claude
- `/ll:loop-suggester` must infer workflows purely from user prompts

## Expected Behavior

```bash
# New flag to include CLI commands
$ ll-messages --include-commands
{"type": "user", "content": "Run the tests", "timestamp": "...", ...}
{"type": "command", "content": "python -m pytest scripts/tests/ -v", "timestamp": "...", "tool": "Bash", ...}
{"type": "user", "content": "Fix the lint errors", "timestamp": "...", ...}
{"type": "command", "content": "ruff check scripts/ --fix", "timestamp": "...", "tool": "Bash", ...}

# Combined with existing options
$ ll-messages --include-commands --stdout -n 50
$ ll-messages --include-commands --since 2026-01-01
```

### Output Schema Extension

```json
{
  "type": "command",
  "content": "python -m pytest scripts/tests/",
  "timestamp": "2026-02-02T10:30:00.000Z",
  "session_id": "abc123-...",
  "uuid": "...",
  "tool": "Bash",
  "cwd": "/Users/brennon/project",
  "git_branch": "main"
}
```

### Log Structure Reference

Claude Code logs contain assistant messages with tool use blocks:

```json
{
  "type": "assistant",
  "timestamp": "...",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "name": "Bash",
        "input": {
          "command": "python -m pytest scripts/tests/"
        }
      }
    ]
  }
}
```

The extraction should:
1. Find `type == "assistant"` messages
2. Look for `message.content[].type == "tool_use"`
3. Filter for `name == "Bash"` (or optionally other tools)
4. Extract `input.command` as the content

## Proposed Solution

### Implementation in `scripts/little_loops/user_messages.py`

1. Add new `CommandRecord` dataclass:
   ```python
   @dataclass
   class CommandRecord:
       content: str          # The command string
       timestamp: datetime
       session_id: str
       uuid: str
       tool: str             # "Bash", etc.
       cwd: str | None = None
       git_branch: str | None = None
   ```

2. Add `extract_commands()` function:
   ```python
   def extract_commands(
       project_folder: Path,
       limit: int | None = None,
       since: datetime | None = None,
       tools: list[str] | None = None,  # Default: ["Bash"]
   ) -> list[CommandRecord]:
       """Extract CLI commands from assistant tool_use messages."""
   ```

3. Add `--include-commands` CLI flag in `cli.py`

4. Merge and sort user messages + commands by timestamp in output

### CLI Options

| Flag | Description |
|------|-------------|
| `--include-commands` | Include Bash commands alongside user messages |
| `--commands-only` | Extract only commands, no user messages |
| `--tools TOOL,...` | Filter command extraction to specific tools (default: Bash) |

## Impact

- **Priority**: P3
- **Effort**: Low - Similar extraction logic to existing user messages
- **Risk**: Low - Additive feature, no changes to existing behavior

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | scripts/little_loops/user_messages.py | Core extraction module to extend |
| skills | skills/loop-suggester/SKILL.md | Consumer of ll-messages output |

## Labels

`feature`, `cli-tool`, `ll-messages`, `loop-suggester`, `workflow-analysis`

---

**Priority**: P3 | **Created**: 2026-02-02

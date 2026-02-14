# Claude CLI Integration Mechanics - Research Report

## Executive Summary

This report documents how the little-loops plugin integrates with the Claude Code CLI for automated issue processing. The research confirms the CLI patterns used are current and correct, with sophisticated mechanisms for multi-turn interactions and output capture.

---

## 1. Claude Code CLI API

### Current Invocation Pattern

**Confirmed correct** - The pattern `claude --dangerously-skip-permissions -p "..."` is the authoritative API:

```bash
claude --dangerously-skip-permissions -p "/ll:manage-issue bug fix"
```

**Source**: `scripts/little_loops/subprocess_utils.py:82`
```python
cmd_args = ["claude", "--dangerously-skip-permissions", "-p", command]
```

### CLI Flags Reference

| Flag | Purpose | Required |
|------|---------|----------|
| `--dangerously-skip-permissions` | Skip interactive permission prompts for autonomous execution | Yes (for automation) |
| `-p` / `--print` | Print mode - executes command and prints response without interactive session | Yes |
| `--output-format json` | Return structured JSON output | Optional |
| `--output-format stream-json` | Streaming NDJSON for real-time processing | Optional |
| `--output-format text` | Plain text output (default) | Optional |
| `--version` | Display CLI version | Diagnostic |
| `--auth-status` | Check authentication status | Diagnostic |

### Environment Configuration

```python
env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"
```
Prevents Claude from changing directories during execution (BUG-007 fix for worktree isolation).

---

## 2. Slash Commands and Multi-Turn Interactions

### Command Definition

Commands are markdown files with YAML frontmatter in `commands/`:

```yaml
---
description: [command description]
arguments:
  - name: [arg_name]
    description: [arg_description]
    required: [true/false]
---
# Command content (instructions for Claude)
```

**Auto-discovery**: `plugin.json:23-24` declares `"commands": { "directory": "commands" }`

### Multi-Turn Interaction Patterns

The codebase implements several strategies for handling multi-turn interactions:

#### A. Phase Gates (Manual Checkpoints)
**Source**: `commands/manage_issue.md:381-415`

- Enable with `--gates` flag
- After each phase completes, execution pauses
- User reviews verification criteria
- User replies "continue" to proceed
- Designed for supervised automation

#### B. Resume Capability
**Source**: `commands/manage_issue.md:296-316`

- `--resume` flag locates existing plan from previous session
- Scans for `[x]` checkmarks in success criteria
- Verifies previous work still valid before continuing
- Enables long-running tasks across session boundaries

#### C. Context Handoff Protocol
**Source**: `scripts/little_loops/subprocess_utils.py:23-37`

```python
CONTEXT_HANDOFF_PATTERN = re.compile(r"CONTEXT_HANDOFF:\s*Ready for fresh session")
CONTINUATION_PROMPT_PATH = Path(".claude/ll-continue-prompt.md")
```

When context limits approach:
1. `/ll:handoff` generates continuation prompt
2. Outputs signal: `CONTEXT_HANDOFF: Ready for fresh session`
3. Outer loop detects signal and spawns fresh Claude session
4. New session reads continuation prompt and resumes work

#### D. State Persistence
**Source**: `scripts/little_loops/state.py:39-46`

```python
@dataclass
class ProcessingState:
    current_issue: str | None
    phase: str | None
    timestamp: str | None
    completed_issues: list[str]
    failed_issues: dict[str, str]
    attempted_issues: set[str]
    timing: dict[str, dict[str, float]]
    corrections: dict[str, str]
```

State is persisted to JSON files, enabling:
- Recovery from crashes
- Progress tracking across sessions
- Audit trails for debugging

---

## 3. Output Capture Mechanisms

### Real-Time Streaming

**Source**: `scripts/little_loops/subprocess_utils.py:55-148`

```python
process = subprocess.Popen(
    cmd_args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,  # Line buffered
    cwd=working_dir,
    env=env,
)
```

Features:
- Separate stdout/stderr pipes
- Line-buffered mode for immediate output
- Non-blocking I/O using `selectors.DefaultSelector()`
- Optional streaming callback: `OutputCallback = Callable[[str, bool], None]`

### JSON Output Format

**Source**: `scripts/little_loops/parallel/worker_pool.py:459-472`

```python
result = subprocess.run(
    ["claude", "-p", "reply with just 'ok'", "--output-format", "json"],
    cwd=worktree_path,
    capture_output=True,
    text=True,
    timeout=30,
)
response = json.loads(result.stdout)
model_usage = response.get("modelUsage", {})
```

Used for:
- Model usage detection in worktrees
- Structured response parsing when deterministic output needed

### Structured Output Parsing

**Source**: `scripts/little_loops/parallel/output_parsing.py:1-463`

Parses Claude's natural language output into structured data:

| Function | Purpose |
|----------|---------|
| `parse_ready_issue_output()` | Extract verdict, concerns, validations |
| `parse_manage_issue_output()` | Extract status, files changed, commits |
| `parse_sections()` | Parse `## SECTION_NAME` headers |
| `parse_validation_table()` | Parse markdown tables |
| `parse_status_lines()` | Parse `- key: value` lists |

Verdict extraction uses multiple fallback strategies (lines 231-285) to handle formatting variations.

### Context Monitoring Hook

**Source**: `hooks/scripts/context-monitor.sh:1-305`

PostToolUse hook that:
- Reads tool call JSON from stdin
- Estimates token consumption per tool type
- Stores state in `.claude/ll-context-state.json`
- Triggers warning at 80% context threshold

Token weight estimates:
```bash
# Read: lines × 10
# Bash: output_chars × 0.3
# Glob: file_count × 20
# Task: 2000 tokens
# WebFetch: 1500 tokens
```

---

## 4. Key Architectural Patterns

### Command Flow

```
User/Automation → claude CLI → Slash Command → Claude Execution → Output
                    ↓                               ↓
             -p "/ll:cmd"                    State Updates
                    ↓                               ↓
         --dangerously-skip-permissions      Log Capture
```

### Session Lifecycle Hooks

**Source**: `hooks/hooks.json:1-61`

| Event | Purpose |
|-------|---------|
| `SessionStart` | Clear state, load config |
| `SessionEnd` | Session termination cleanup |
| `UserPromptSubmit` | Validate setup, warn if no config |
| `PreToolUse` | Validate before edits (e.g., duplicate IDs) |
| `PostToolUse` | Monitor context usage |
| `Stop` | Clean up locks, worktrees |
| `SubagentStop` | Handle subagent completion |
| `PreCompact` | Prepare for context compaction |
| `Notification` | Handle system notifications |

### Continuation Prompt Template

**Source**: `hooks/prompts/continuation-prompt-template.md:1-74`

```markdown
# Session Continuation: [ISSUE-ID]
## Context - 2-3 sentence summary
## Completed Work - [x] Phase N: Name
## Current State - Working on, Last action, Next action
## Key File References - Plan, Modified files, Tests
## Resume Command - /ll:manage-issue [type] [action] [ISSUE-ID] --resume
## Critical Context - Decisions, Gotchas, Patterns
```

---

## 5. Critical File References

| File | Purpose |
|------|---------|
| `scripts/little_loops/subprocess_utils.py` | Core CLI invocation and output handling |
| `scripts/little_loops/parallel/worker_pool.py` | Parallel execution with worktrees |
| `scripts/little_loops/parallel/output_parsing.py` | Structured output extraction |
| `scripts/little_loops/state.py` | State persistence layer |
| `scripts/little_loops/issue_manager.py` | Sequential issue processing |
| `commands/manage_issue.md` | Full issue lifecycle with phases |
| `commands/handoff.md` | Session handoff generation |
| `commands/resume.md` | Session continuation |
| `hooks/hooks.json` | Lifecycle event handlers |
| `hooks/scripts/context-monitor.sh` | Real-time context tracking |
| `docs/generalized-fsm-loop.md` | FSM-based processing paradigms |
| `docs/SESSION_HANDOFF.md` | Multi-turn session management |

---

## 6. Answers to Original Questions

### Q1: Is `claude --dangerously-skip-permissions -p "..."` the current/correct Claude Code CLI API?

**Yes.** This is the correct and current API for automated/autonomous Claude Code execution. The `--dangerously-skip-permissions` flag is required to bypass interactive permission prompts, and `-p` (print mode) executes the command and prints the response without starting an interactive session.

### Q2: How do we handle slash commands that may trigger multi-turn interactions?

**Multiple complementary strategies:**

1. **Phase gates** - Manual checkpoints with `--gates` flag
2. **Resume capability** - `--resume` flag continues from checkmarks in plan files
3. **Context handoff** - Automatic detection of context limits triggers session continuation
4. **State persistence** - JSON files maintain progress across sessions

### Q3: How is output captured from Claude sessions?

**Three-tier approach:**

1. **Real-time streaming** - Line-buffered subprocess with callbacks for immediate output
2. **Structured parsing** - Regex-based extraction of verdicts, sections, tables from natural language
3. **JSON format** - `--output-format json` for deterministic structured output when needed
4. **Context monitoring** - PostToolUse hook estimates token usage and persists to state files

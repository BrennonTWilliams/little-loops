# Session Handoff

Automatic context management and session continuation for long-running tasks.

## Overview

Claude Code sessions have a context window limit. When working on complex tasks, context can fill up, potentially losing progress. Session handoff solves this by:

1. **Monitoring** context usage in real-time
2. **Warning** when approaching the limit (80% by default)
3. **Preserving** session state to a continuation prompt
4. **Resuming** seamlessly in a fresh session

## Quick Start

### Enable Context Monitoring

Add to `.claude/ll-config.json`:

```json
{
  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80
  }
}
```

### Manual Handoff

When you want to preserve your work:

```bash
/ll:handoff                           # Auto-detect context
/ll:handoff "Working on auth module"  # With explicit description
```

### Resume in New Session

```bash
/ll:resume
```

## How It Works

### Interactive Sessions

```
┌─────────────────────────────────────────────────────────────────┐
│ Session starts                                                  │
│     ↓                                                           │
│ PostToolUse hook monitors each tool call                        │
│     ↓                                                           │
│ Estimates tokens: Read (10/line), Bash (0.3/char), etc.         │
│     ↓                                                           │
│ When usage >= 80%:                                              │
│     "[ll] Context ~82% used. Run /ll:handoff..."                │
│     ↓                                                           │
│ Reminder repeats on every tool call until handoff executed      │
│     ↓                                                           │
│ /ll:handoff writes .claude/ll-continue-prompt.md                │
│     ↓                                                           │
│ Start new session → /ll:resume → Continue working               │
└─────────────────────────────────────────────────────────────────┘
```

### Automation Tools (ll-auto, ll-parallel)

Automation tools handle handoff automatically:

```
┌─────────────────────────────────────────────────────────────────┐
│ Worker processes issue                                          │
│     ↓                                                           │
│ Context threshold reached                                       │
│     ↓                                                           │
│ PostToolUse hook outputs to stderr (exit 2)                     │
│ "[ll] Context ~82% used. Run /ll:handoff..."                    │
│     ↓                                                           │
│ Claude receives feedback, autonomously runs /ll:handoff         │
│     ↓                                                           │
│ /ll:handoff outputs: "CONTEXT_HANDOFF: Ready for fresh session" │
│     ↓                                                           │
│ CLI detects signal, reads .claude/ll-continue-prompt.md         │
│     ↓                                                           │
│ Spawns fresh Claude session with continuation prompt            │
│     ↓                                                           │
│ Work continues (up to 3 continuations per issue)                │
└─────────────────────────────────────────────────────────────────┘
```

## Commands

### `/ll:handoff`

Generates a continuation prompt capturing current session state. Uses a **conversation-first approach** by default - summarizing the conversation history already in context without running external commands.

**Usage:**

```bash
/ll:handoff                              # Conversation summary (default, fast)
/ll:handoff "Refactoring auth module"    # With explicit context hint
/ll:handoff --deep                       # With artifact validation
/ll:handoff "Working on BUG-042" --deep  # Context + artifact validation
```

**Modes:**

| Mode | Command | What's Captured | Speed |
|------|---------|----------------|-------|
| Default | `/ll:handoff` | Conversation summary, decisions, errors, code changes | Fast (no disk I/O) |
| Deep | `/ll:handoff --deep` | Default + git status, todos, discrepancy detection | Slower (runs git) |

**Default Output:** Writes to `.claude/ll-continue-prompt.md`:

```markdown
# Session Continuation: Refactoring auth module

## Conversation Summary

### Primary Intent
Refactoring the authentication module to support OAuth2 providers.

### What Happened
1. Analyzed existing auth middleware
2. Discussed JWT vs session-based approach - chose JWT for statelessness
3. Implemented token validation utility
4. Encountered CORS issue with refresh endpoint - fixed with credentials flag

### User Feedback
- User clarified that refresh tokens should use HTTP-only cookies for security

### Errors and Resolutions
| Error | How Fixed | User Feedback |
|-------|-----------|---------------|
| CORS error on /refresh | Added credentials: 'include' | None |
| Token expiry too short | Increased to 15 minutes | User confirmed 15min is acceptable |

### Code Changes
| File | Changes Made | Discussion Context |
|------|--------------|-------------------|
| `src/middleware/auth.ts:45` | Added token validation | Core auth flow |
| `src/utils/tokens.ts:12` | New token utility | Extracted for reuse |

## Resume Point

### What Was Being Worked On
Implementing the refresh token endpoint callback handler

### Direct Quote
> "Now let's implement the callback handler for the refresh flow"

### Next Step
Add the /auth/refresh endpoint with cookie handling

## Important Context

### Decisions Made
- **JWT over sessions**: Chosen for statelessness and microservice compatibility
- **HTTP-only cookies**: For refresh tokens to prevent XSS

### Gotchas Discovered
- **CORS with credentials**: Must set credentials: 'include' on fetch requests

### User-Specified Constraints
- Refresh tokens must use HTTP-only cookies (security requirement)
- Token expiry: 15 minutes

### Patterns Being Followed
- Following pattern from `src/middleware/rate-limit.ts` for middleware structure
```

**Deep Mode Output:** Includes all sections above, plus:

```markdown
## Artifact Validation

### Current Git Status
```
M  src/middleware/auth.ts
M  src/utils/tokens.ts
?? src/utils/cookies.ts
```

### Discrepancies
No discrepancies detected between conversation and artifacts

### Todo List State
| Status | Task |
|--------|------|
| in_progress | Implement refresh token endpoint |
| pending | Add token rotation on refresh |
| completed | Create token validation utility |

### Plan Files
- Active plan: `thoughts/shared/plans/2024-01-15-auth-refactor.md`
```

### `/ll:resume`

Loads a continuation prompt and restores session context.

**Usage:**

```bash
/ll:resume                              # From default location
/ll:resume path/to/custom-prompt.md     # From custom location
```

**Output:**

```
Resuming from previous session
─────────────────────────────────────────────────────────────────
[Continuation prompt content displayed]
─────────────────────────────────────────────────────────────────

Ready to continue. What would you like to do next?
```

## Configuration

### Full Configuration Options

```json
{
  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80,
    "context_limit_estimate": 150000,
    "estimate_weights": {
      "read_per_line": 10,
      "tool_call_base": 100,
      "bash_output_per_char": 0.3
    },
    "state_file": ".claude/ll-context-state.json"
  },
  "continuation": {
    "enabled": true,
    "auto_detect_on_session_start": true,
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true,
    "max_continuations": 3,
    "prompt_expiry_hours": 24
  }
}
```

### Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `context_monitor.enabled` | `false` | Enable automatic context monitoring |
| `context_monitor.auto_handoff_threshold` | `80` | Percentage (50-95) to trigger warnings |
| `context_monitor.context_limit_estimate` | `150000` | Conservative token limit estimate |
| `continuation.max_continuations` | `3` | Max auto-continuations per issue (automation) |
| `continuation.prompt_expiry_hours` | `24` | Hours before prompt marked stale |

### Token Estimation Weights

The context monitor estimates token usage based on tool activity:

| Tool | Estimation | Rationale |
|------|------------|-----------|
| Read | `lines × 10` | File content is verbose |
| Grep | `matches × 5` | Summarized search results |
| Bash | `chars × 0.3` | Command output varies |
| Glob | `files × 20` | File lists are compact |
| Write/Edit | `300` | Base cost × 3 for edits |
| Task | `2000` | Agent responses are summarized |
| WebFetch | `1500` | Web content is processed |
| WebSearch | `1000` | Search results summary |
| Other | `100` | Base overhead per call |

## Files

| File | Purpose |
|------|---------|
| `.claude/ll-continue-prompt.md` | Generated continuation prompt |
| `.claude/ll-context-state.json` | Running context usage state |
| `.claude/ll-session-state.json` | Session metadata (fallback) |

### State File Format

`.claude/ll-context-state.json`:

```json
{
  "session_start": "2024-01-15T10:30:00Z",
  "estimated_tokens": 125000,
  "tool_calls": 63,
  "threshold_crossed_at": "2024-01-15T11:45:00Z",
  "handoff_complete": false,
  "breakdown": {
    "read": 60000,
    "bash": 30000,
    "grep": 15000,
    "glob": 5000,
    "task": 15000
  }
}
```

## Troubleshooting

### Context monitor not triggering

1. **Check if enabled:**
   ```bash
   cat .claude/ll-config.json | jq '.context_monitor.enabled'
   ```

2. **Verify jq is installed** (required for the hook):
   ```bash
   which jq
   ```

3. **Check state file:**
   ```bash
   cat .claude/ll-context-state.json
   ```

### Reminders keep appearing after handoff

The monitor checks if `.claude/ll-continue-prompt.md` was modified *after* the threshold was crossed. Ensure:

1. `/ll:handoff` was run (not just manually creating the file)
2. The file modification time is recent
3. Check `handoff_complete` in state file

### Resume shows stale prompt

Prompts older than `prompt_expiry_hours` (default: 24) are marked stale. The content is still shown, but a warning appears. You can:

1. Run `/ll:handoff` to generate a fresh prompt
2. Increase `prompt_expiry_hours` in config

### Automation not detecting handoff

Ensure the handoff command outputs the signal:

```
CONTEXT_HANDOFF: Ready for fresh session
```

Check `subprocess_utils.py` detection pattern:

```python
CONTEXT_HANDOFF_PATTERN = re.compile(r"CONTEXT_HANDOFF:\s*Ready for fresh session")
```

### Max continuations reached

If you see "Reached max continuations", the issue required more than 3 session restarts. Options:

1. Increase `continuation.max_continuations` in config
2. Break the issue into smaller tasks
3. Run remaining work manually

## Best Practices

### When to Use Manual Handoff

- Before taking a break on a long task
- When you notice context filling up
- Before switching to a different task
- When the hook starts warning you

### Writing Good Continuation Prompts

The `/ll:handoff` command auto-generates prompts from conversation history. You can improve them:

1. **Provide explicit context hints** when running handoff:
   ```bash
   /ll:handoff "Implementing OAuth2 flow - finished provider setup, starting callback handler"
   ```

2. **Use `--deep` for complex situations** when you need to verify disk state:
   ```bash
   /ll:handoff --deep
   ```

3. **Keep todos updated** - they're included in deep mode validation

4. **Discuss decisions in conversation** - the conversation summary captures reasoning and trade-offs

### For Automation

1. **Set appropriate thresholds** - Lower threshold (70%) for complex issues
2. **Monitor logs** - Check for `CONTEXT_HANDOFF` signals
3. **Review continuation count** - High counts may indicate issues that need splitting

## Integration

### With Other Hooks

- **PostToolUse hook**: Monitors context usage and triggers handoff reminders
- **Stop hook**: Cleans up context state file when session ends

### With Automation Tools

Both `ll-auto` and `ll-parallel` support automatic continuation:

```python
# In issue_manager.py and worker_pool.py
if detect_context_handoff(result.stdout):
    prompt_content = read_continuation_prompt(working_dir)
    # Spawn fresh session with prompt
```

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md#context-monitor-and-session-continuation) - Technical details
- [commands/handoff.md](../../commands/handoff.md) - Command reference
- [commands/resume.md](../../commands/resume.md) - Command reference

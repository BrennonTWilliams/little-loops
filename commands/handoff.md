---
description: Generate continuation prompt for session handoff
argument-hint: "[context]"
allowed-tools:
  - Read
  - Write
  - Bash(git:*)
arguments:
  - name: context
    description: Brief description of current work context (optional)
    required: false
  - name: flags
    description: "Optional flags: --deep (validate and enrich with git status, todos, recent files)"
    required: false
---

# Session Handoff

Generate a continuation prompt capturing current session state for handoff to a fresh session.

This command uses a **conversation-first approach**: by default, it summarizes the conversation history (which is already in context) without running external commands. Use `--deep` for artifact validation when you need to cross-check conversation against actual disk state.

## Configuration

Read settings from `.claude/ll-config.json` under `continuation`:
- `include_todos`: Include todo list state in deep mode (default: true)
- `include_git_status`: Include git status in deep mode (default: true)
- `include_recent_files`: Include recently modified files in deep mode (default: true)

## Edge Cases

### Compacted Conversations
If the conversation was recently compacted (look for "Conversation was compacted" message):
- Note that summary is based on post-compaction context
- Consider using `--deep` to enrich with artifacts
- Output includes: "Note: Conversation was compacted; summary based on available context"

### Empty or New Sessions
If no meaningful conversation history exists:
- Fall back to artifact-based approach (like `--deep` behavior)
- Output includes: "Note: Fresh session with no prior context"

### Discrepancies (--deep only)
When conversation says one thing but artifacts show another:
- Flag explicitly in Artifact Validation section
- Do not override conversation summary (user may have discussed planned changes)
- Recommend user verify intended changes

## Process

### 1. Summarize the Conversation (Default - Always)

Review the entire conversation history above and extract:

#### User Requests
- **Primary intent**: What was the user trying to accomplish?
- **Explicit requests**: All specific requests made by the user
- **Scope changes**: Did the user shift focus or refine requirements?

#### Chronological Flow
- **Key phases**: What major phases of work were undertaken?
- **Decisions made**: What choices were made and why?
- **Pivot points**: Where did the approach change based on discoveries?

#### Errors and Fixes
- **Errors encountered**: What went wrong?
- **How fixed**: What was done to resolve each error?
- **User feedback**: Did the user provide corrections or guidance?

#### Code Changes
- **Files modified**: What files were actually changed?
- **Code snippets**: Key code that was written or discussed
- **Architectural decisions**: What patterns or approaches were chosen?

### 2. Validate with Artifacts (Only with --deep flag)

**Skip this section if `--deep` flag was NOT provided.**

Parse flags:
```bash
FLAGS="${flags:-}"
DEEP_MODE=false
if [[ "$FLAGS" == *"--deep"* ]]; then DEEP_MODE=true; fi
```

If `DEEP_MODE` is true, run these commands to validate conversation against disk state:

#### Git Status
```bash
git status --short
```
- **Purpose**: Verify actual file state vs what was discussed
- **Check**: Are all mentioned files actually modified?
- **Flag**: Any discrepancies between conversation and disk

#### Todo List
- **Purpose**: Cross-check pending work
- **Verify**: In-progress items match current conversation
- **Include**: All pending items for continuity

#### Recent Modifications
```bash
git diff --name-only HEAD~1 2>/dev/null || git diff --name-only --cached
```
- **Purpose**: Catch files modified outside the conversation flow
- **Include**: Files that may not have been explicitly discussed

#### Plan Files
Check `thoughts/shared/plans/` for:
- Any plan files referenced in conversation
- Most recently modified plan file

#### Discrepancy Detection
Compare conversation claims to artifact reality:
| Conversation Claim | Artifact Reality | Status |
|-------------------|------------------|--------|
| Modified auth.ts | git shows M auth.ts | MATCH |
| Updated tests | No test changes in git | MISMATCH |

### 3. Generate Continuation Prompt

Write to `.claude/ll-continue-prompt.md`.

**If `--deep` flag was NOT passed** (default mode):

```markdown
# Session Continuation: [Primary Intent from Conversation]

## Conversation Summary

### Primary Intent
[From conversation: what the user was trying to accomplish]

### What Happened
[Chronological summary of key phases, decisions, and discoveries]

### User Feedback
[Specific corrections or guidance the user provided, if any]

### Errors and Resolutions
| Error | How Fixed | User Feedback |
|-------|-----------|---------------|
| [Error encountered] | [Resolution applied] | [Any user input] |

### Code Changes
| File | Changes Made | Discussion Context |
|------|--------------|-------------------|
| `path/to/file.ts:45` | [What changed] | [Why it was discussed] |

## Resume Point

### What Was Being Worked On
[Precise description from conversation end]

### Direct Quote
> [Verbatim quote from most recent work or user request]

### Next Step
[Immediate next action based on conversation]

## Important Context

### Decisions Made
- **[Decision]**: [Reasoning from conversation]

### Gotchas Discovered
- **[Gotcha]**: [How discovered, what to watch for]

### User-Specified Constraints
[Any specific requirements or constraints the user gave]

### Patterns Being Followed
- Following pattern from `[file:line]` - [why this pattern was chosen]
```

**If `--deep` flag WAS passed** (deep mode):

Include all sections from default mode above, PLUS add this section after "Important Context":

```markdown
## Artifact Validation

### Current Git Status
```
[Output of git status --short]
```

### Discrepancies
[Any differences between conversation and disk state]
- **[File or claim]**: [Conversation said X, disk shows Y]
(If none: "No discrepancies detected between conversation and artifacts")

### Todo List State
| Status | Task |
|--------|------|
| in_progress | [Current task] |
| pending | [Next tasks] |
| completed | [Done tasks] |

### Plan Files
- Active plan: `[path to plan file]`
- Related plans: `[other relevant plan files]`
```

### 4. Output Handoff Signal

After writing the continuation prompt, output:

```
CONTEXT_HANDOFF: Ready for fresh session
Continuation prompt written to: .claude/ll-continue-prompt.md

Source: Conversation summary [+ artifact validation with --deep]

To continue in a new session:
  1. Start a new Claude Code session
  2. Run /ll:resume

Or copy the prompt content above to paste into a new session.
```

---

## Arguments

$ARGUMENTS

- **context** (optional): Brief description of current work context
  - Provides a hint for the conversation summary
  - Example: `"Refactoring authentication module"`

- **flags** (optional): Command behavior flags
  - `--deep` - Validate and enrich with git status, todos, recent files

---

## Examples

```bash
# Generate handoff from conversation summary (default - fast)
/ll:handoff

# Generate handoff with explicit context hint
/ll:handoff "Refactoring authentication module"

# Generate handoff with artifact validation (slower but comprehensive)
/ll:handoff --deep

# Combine context and deep mode
/ll:handoff "Working on BUG-042" --deep
```

---

## Integration

- Complements `/ll:resume` for reading the prompt
- Uses same file format as automation tools (`ll-auto`, `ll-parallel`)
- Outputs `CONTEXT_HANDOFF` signal for automation detection
- Works with PostToolUse context monitor hook for automatic reminders

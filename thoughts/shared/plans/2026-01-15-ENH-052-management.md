# ENH-052: Conversation-Aware Handoff - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-052-conversation-aware-handoff.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `/ll:handoff` command (commands/handoff.md) currently reconstructs session state by reading external artifacts:
- Git status via `git status --short` (line 31)
- Recent modifications via `git diff --name-only` (line 37)
- Plan files from `thoughts/shared/plans/` (lines 42-44)
- Todo list state
- Optional user-provided context argument

### Key Discoveries
- **commands/handoff.md:22-48** - Current artifact-only approach misses conversation context
- **commands/handoff.md:52-76** - Output writes to `.claude/ll-continue-prompt.md`
- **hooks/scripts/context-monitor.sh:221** - PostToolUse hook checks for continuation file to detect handoff completion
- **commands/init.md:24-35** - Flag parsing pattern: `[[ "$FLAGS" == *"--flag"* ]]`

## Desired End State

The `/ll:handoff` command should:
1. **Default mode**: Summarize the conversation history (user requests, decisions, errors, code changes) - fast, no disk I/O
2. **Deep mode (`--deep`)**: Add artifact validation to cross-check conversation against disk state

### How to Verify
- Running `/ll:handoff` produces a continuation prompt based on conversation summary
- Running `/ll:handoff --deep` includes additional artifact validation section
- Automation tools (`ll-auto`, `ll-parallel`) continue to work with the signal
- `/ll:resume` can read the new prompt format

## What We're NOT Doing

- Not changing the output file location (`.claude/ll-continue-prompt.md`)
- Not changing the `CONTEXT_HANDOFF` signal format
- Not modifying Python automation tools (they read the signal, not parse prompt content)
- Not adding new configuration options (existing `continuation` config still applies)
- Not modifying `commands/resume.md` (it reads raw file content)

## Problem Analysis

When `/ll:handoff` is invoked, the LLM has full conversation history but doesn't use it. The current approach:
- Misses user feedback and corrections
- Loses reasoning behind decisions
- Doesn't capture error resolution flow
- Requires more manual context provision

## Solution Approach

1. Update command frontmatter to add optional `flags` argument for `--deep`
2. Replace artifact-first process with conversation-first process
3. Add conditional deep mode for artifact validation
4. Update output template with new sections
5. Maintain backward compatibility (file location, signal, automation)

## Implementation Phases

### Phase 1: Update Command Frontmatter

#### Overview
Add the `--deep` flag argument to enable optional artifact validation.

#### Changes Required

**File**: `commands/handoff.md`
**Changes**: Add flags argument to YAML frontmatter

```yaml
---
description: Generate continuation prompt for session handoff
arguments:
  - name: context
    description: Brief description of current work context (optional)
    required: false
  - name: flags
    description: "Optional flags: --deep (validate and enrich with git status, todos, recent files)"
    required: false
---
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`
- [ ] Command file is valid YAML frontmatter

**Manual Verification**:
- [ ] Running `/ll:handoff --deep` is recognized by Claude

---

### Phase 2: Rewrite Process Section

#### Overview
Replace the current artifact-based process with conversation-first approach.

#### Changes Required

**File**: `commands/handoff.md`
**Changes**: Complete rewrite of ## Process section

The new process will be structured as:

```markdown
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

#### Discrepancy Detection
Compare conversation claims to artifact reality:
| Conversation Claim | Artifact Reality | Status |
|-------------------|------------------|--------|
| Modified auth.ts | git shows M auth.ts | MATCH |
| Updated tests | No test changes in git | MISMATCH |

### 3. Generate Continuation Prompt

Write to `.claude/ll-continue-prompt.md`.

**Structure varies by mode:**
- **Default mode**: Conversation Summary + Resume Point + Important Context
- **Deep mode (--deep)**: All default sections + Artifact Validation section
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Running `/ll:handoff` uses conversation summary (no git commands)
- [ ] Running `/ll:handoff --deep` runs git status and includes validation

---

### Phase 3: Update Output Template

#### Overview
Create new continuation prompt templates for default and deep modes.

#### Changes Required

**File**: `commands/handoff.md`
**Changes**: Replace the template in "Generate Continuation Prompt" section

New template structure:

```markdown
### 3. Generate Continuation Prompt

Write to `.claude/ll-continue-prompt.md`:

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
> [Verbatim quote from most recent work]

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

Include all sections from default mode above, plus:

```markdown
## Artifact Validation

### Current Git Status
```
[Output of git status --short]
```

### Discrepancies
[Any differences between conversation and disk state]
- **[File or claim]**: [Conversation said X, disk shows Y]

### Todo List State
| Status | Task |
|--------|------|
| in_progress | [Current task] |
| pending | [Next tasks] |
| completed | [Done tasks] |
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Command file has valid markdown structure

**Manual Verification**:
- [ ] Default mode output includes conversation summary sections
- [ ] Deep mode output includes artifact validation section
- [ ] Output is written to `.claude/ll-continue-prompt.md`

---

### Phase 4: Update Signal and Examples

#### Overview
Update the output signal and examples section.

#### Changes Required

**File**: `commands/handoff.md`
**Changes**: Update signal section and examples

Signal section (minimal changes - add source indicator):

```markdown
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
```

Examples section:

```markdown
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
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Signal output indicates source (conversation vs artifact)
- [ ] Examples cover all usage modes

---

### Phase 5: Handle Edge Cases

#### Overview
Add handling for compacted conversations and empty sessions.

#### Changes Required

**File**: `commands/handoff.md`
**Changes**: Add edge case handling section before Process section

```markdown
## Edge Cases

### Compacted Conversations
If the conversation was recently compacted (look for "Conversation was compacted" message):
- Note that summary is based on post-compaction context
- Consider using `--deep` to enrich with artifacts
- Output includes: "Note: Conversation was compacted; summary based on available context"

### Empty or New Sessions
If no meaningful conversation history exists:
- Fall back to artifact-based approach (like current behavior)
- Output includes: "Note: Fresh session with no prior context"

### Discrepancies (--deep only)
When conversation says one thing but artifacts show another:
- Flag explicitly in Artifact Validation section
- Do not override conversation summary (user may have discussed planned changes)
- Recommend user verify intended changes
```

#### Success Criteria

**Automated Verification**:
- [ ] Command file has valid markdown structure

**Manual Verification**:
- [ ] Running `/ll:handoff` in a fresh session produces reasonable output
- [ ] Output notes when conversation was compacted

---

## Testing Strategy

### Manual Testing Scenarios

1. **Simple conversation**: Basic feature implementation, run `/ll:handoff`
   - Verify conversation flow is captured
   - Verify user feedback is included
   - Verify no git commands are run

2. **Deep mode**: Run `/ll:handoff --deep`
   - Verify git status is included
   - Verify todo list is included
   - Verify discrepancies are flagged

3. **Error recovery session**: Session with multiple errors and fixes
   - Verify errors and resolutions are in table format
   - Verify user feedback is captured

4. **Context argument**: Run `/ll:handoff "Working on feature X"`
   - Verify context is used in title

5. **Automation compatibility**: Verify `CONTEXT_HANDOFF` signal format unchanged
   - Output contains `CONTEXT_HANDOFF: Ready for fresh session`
   - File written to `.claude/ll-continue-prompt.md`

## References

- Original issue: `.issues/enhancements/P3-ENH-052-conversation-aware-handoff.md`
- Current implementation: `commands/handoff.md`
- Flag parsing pattern: `commands/init.md:24-35`
- Resume command: `commands/resume.md`
- Context monitor hook: `hooks/scripts/context-monitor.sh`

---
discovered_date: 2026-01-15T12:00:00Z
---

# ENH-052: Conversation-Aware Handoff

## Summary

Enhance `/ll:handoff` to leverage the actual conversation context in the active session, rather than inferring context solely from external artifacts (git status, todos, files).

## Motivation

Currently, `/ll:handoff` reconstructs session state by reading external artifacts:
- Git status (`git status --short`)
- Todo list state
- Recent modifications (`git diff`)
- Plan files in `thoughts/`
- User-provided context argument

However, when `/ll:handoff` is invoked, the LLM has access to the **full conversation history** in its context window. This includes:
- User's explicit requests and intents
- Chronological flow of the conversation
- Errors encountered and how they were fixed
- User feedback (especially corrections)
- Decisions made and their reasoning
- Code snippets that were discussed
- Architectural choices

By not leveraging this rich context, the current `/ll:handoff`:
- Misses user feedback and corrections
- Loses reasoning behind decisions
- Doesn't capture the conversational flow
- May miss important context that wasn't captured in artifacts
- Requires more manual context provision via arguments

## Proposed Implementation

### 1. New Process Flow

Update `/ll:handoff` to use a **conversation-first approach** with optional deep validation:

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Summarize the conversation (primary source)                   │
│    - Review entire conversation history above                     │
│    - Extract user requests, decisions, errors, feedback           │
│    - Capture chronological flow and reasoning                     │
│    - Generate continuation prompt from conversation alone         │
│     ↓                                                             │
│ 2. [Optional --deep] Validate and enrich with artifacts          │
│    - Git status (verify actual file state)                        │
│    - Todo list (cross-check pending items)                        │
│    - Recent files (ensure nothing was missed)                     │
│    - Flag any discrepancies between conversation and disk state   │
│     ↓                                                             │
│ 3. [Optional --deep] Enhance prompt with artifact validation     │
│    - Add artifact validation section to continuation prompt       │
│    - Include discrepancies, git status, todo state                │
└─────────────────────────────────────────────────────────────────┘
```

**Default behavior** (no flag): Step 1 only - conversation summary is sufficient for most handoffs.

**With `--deep` flag**: Steps 1, 2, 3 - full validation and artifact enrichment for complex situations.

### 2. Updated Command Structure

**File**: `commands/handoff.md`

Replace the current "Gather Current State" section with:

```markdown
## Process

### 1. Summarize the Conversation (Always)

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

### 2. [With --deep] Validate and Enrich with Artifacts

**Only if `--deep` flag was passed**: Run these commands to validate and enrich the conversation summary:

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

### 3. Generate Continuation Prompt

Write to `.claude/ll-continue-prompt.md`:

**If `--deep` flag was passed**: Include all sections below.

**If `--deep` flag was NOT passed**: Only include "Conversation Summary Section" and "Next Steps Section".

#### Conversation Summary Section
- Narrative flow of what happened
- User's explicit requests and feedback
- Errors encountered and resolutions
- Decisions and their reasoning

#### Artifact Validation Section
- Current git status
- Discrepancies noted (if any)
- Todo list state

#### Next Steps Section
- Immediate next action (from conversation context)
- Verbatim quote showing what was being worked on
- Any pending tasks identified

#### Critical Context Section
- Decisions made with reasoning
- Gotchas discovered
- User feedback to remember
- Patterns being followed

### 4. Output Handoff Signal

After writing the continuation prompt, output:

```
CONTEXT_HANDOFF: Ready for fresh session
Continuation prompt written to: .claude/ll-continue-prompt.md

Source: Conversation summary enriched with artifact validation

To continue in a new session:
  1. Start a new Claude Code session
  2. Run /ll:resume

Or copy the prompt content above to paste into a new session.
```

## Enhanced Output Format

### Default Mode (no --deep flag)

```markdown
# Session Continuation: [Context from conversation]

## Conversation Summary

### Primary Intent
[From conversation: what the user was trying to accomplish]

### What Was Discussed
[Chronological summary of key phases, decisions, and discoveries]

### User Feedback
[Specific corrections or guidance the user provided]

### Errors and Resolutions
| Error | How Fixed | User Feedback |
|-------|-----------|--------------|
| ... | ... | ... |

### Code Changes
| File | Changes Made | Discussion Context |
|------|--------------|-------------------|
| `path/to/file.ts:45` | Added error handling | Discussed in phase 2, user requested retry logic |
| ... | ... | ... |

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

### Deep Mode (--deep flag)

Includes everything from Default Mode, plus:

```markdown
## Artifact Validation

### Current Git Status
[Actual git status output]

### Discrepancies
[Any differences between conversation and disk state]

### Todo List State
[Current todo items]
```

## Benefits

| Aspect | Current (Artifacts Only) | Enhanced Default (Conversation Only) | Enhanced Deep (--deep flag) |
|--------|-------------------------|--------------------------------------|-----------------------------|
| User feedback | ❌ Not captured | ✅ Included verbatim | ✅ Included verbatim |
| Reasoning | ❌ Inferred or missing | ✅ Captured from discussion | ✅ Captured from discussion |
| Errors | ⚠️ Inferred from git | ✅ Described with resolution | ✅ Described with resolution |
| Flow | ❌ No narrative | ✅ Chronological story | ✅ Chronological story |
| Code snippets | ❌ Only file:line refs | ✅ Full snippets included | ✅ Full snippets included |
| Speed | ⚠️ Multiple git reads | ✅ Fast - no disk I/O | ⚠️ Slower - validation |
| Validation | ❌ None | ⚠️ Conversation only | ✅ Cross-checked with git |
| Discrepancies | ❌ Not detected | ❌ Not detected | ✅ Flagged explicitly |

## Edge Cases to Handle

### 1. Compacted Conversations
If the conversation was recently compacted:
- **Fallback**: Use artifact-based approach
- **Detection**: Check for "Conversation was compacted" in recent messages
- **Output**: Note that summary is artifact-based due to compaction

### 2. Empty or New Sessions
If no conversation history exists:
- **Fallback**: Pure artifact-based approach
- **Output**: Note that this is a fresh session with no prior context

### 3. Discrepancies
When conversation says one thing but git shows another:
- **Flag**: Explicitly note the discrepancy
- **Example**: "Conversation discussed modifying auth.ts but git shows no changes"
- **Recommendation**: Suggest user verify intended changes

## Configuration

No new configuration needed. Existing `continuation` config applies:

```json
{
  "continuation": {
    "enabled": true,
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true
  }
}
```

## Backward Compatibility

- **File format**: Same output file (`.claude/ll-continue-prompt.md`)
- **Resume command**: `/ll:resume` works with both formats
- **Automation**: `ll-auto` and `ll-parallel` continue to work
- **Signal**: Same `CONTEXT_HANDOFF` signal output

## Testing

### Manual Testing Scenarios

1. **Simple conversation**: Basic feature implementation
2. **Error recovery**: Session with multiple errors and fixes
3. **User corrections**: User provided feedback that changed direction
4. **Compacted session**: After `/compact` was run
5. **Discrepancy**: Conversation discussed changes that weren't saved

### Expected Outputs

For each scenario, verify:
- ✅ Conversation flow is captured
- ✅ User feedback is included
- ✅ Errors with resolutions are listed
- ✅ Discrepancies are flagged
- ✅ Next step is clear and quoted

## Location

| Component | File Path |
|-----------|-----------|
| Command | `commands/handoff.md` |
| Documentation | `docs/SESSION_HANDOFF.md` (update) |
| Tests | Create manual test cases |

## Current Behavior

`/ll:handoff` generates continuation prompts based solely on external artifacts (git status, todos, plan files). Does not leverage the conversation history available in the LLM's context window.

## Expected Behavior

```bash
# Default mode - conversation summary only (fast, most common)
/ll:handoff

# Output includes:
# - Conversation summary with user requests and feedback
# - Errors encountered and how they were fixed
# - Decisions and their reasoning
# - Code snippets with discussion context
# - Next steps and resume point

# Deep mode - includes artifact validation (for complex situations)
/ll:handoff --deep

# Output includes everything from default mode, plus:
# - Artifact validation (git status, todos)
# - Discrepancy detection between conversation and disk
```

## Impact

- **Severity**: Low - Quality of life improvement
- **Effort**: Low - Command rewrite, no new infrastructure
- **Risk**: Low - Backward compatible, additive feature

## Dependencies

None. This is a standalone command enhancement.

## Blocked By

None.

## Blocks

None currently identified. May enhance:
- Session handoff quality
- Automation success rates (ll-auto, ll-parallel)
- User satisfaction with continuity

## Labels

`enhancement`, `handoff`, `continuation`, `conversation`, `ux`, `quality-of-life`

---

## Status

**Open** | Created: 2026-01-15 | Priority: P3

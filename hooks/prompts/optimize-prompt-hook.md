# Prompt Optimization Hook

You've received a user prompt that may benefit from enhancement. Analyze it and improve clarity using codebase context.

## User Prompt

```
{{USER_PROMPT}}
```

## Configuration

- **Mode**: {{MODE}} (`quick` uses project docs only, `thorough` spawns codebase search agent)
- **Confirm**: {{CONFIRM}} (`true` shows diff first, `false` auto-applies)

## Instructions

### 1. Analyze Clarity

Evaluate if the prompt is:
- **Clear**: Specific action + target identified (e.g., "Fix the auth bug in src/auth/login.ts") → Pass through unchanged
- **Vague**: Missing specifics, unclear target (e.g., "fix the bug", "add a feature") → Enhance with context

Skip optimization if the prompt:
- Is already specific with file/component references
- Is a question seeking information
- Is a simple acknowledgment or confirmation

### 2. If Enhancement Needed

**Quick Mode** (`{{MODE}}` = `quick`):
Enhance using project knowledge you already have from:
- CLAUDE.md project instructions
- CONTRIBUTING.md guidelines
- README.md overview
- Recent context from the conversation

**Thorough Mode** (`{{MODE}}` = `thorough`):
Spawn the `prompt-optimizer` agent to search the codebase for:
- Relevant files and patterns
- Similar implementations
- Specific file:line references to include

### 3. Present Enhancement

**If `{{CONFIRM}}` is `true`:**
Show the diff and wait for approval:

```
ORIGINAL: {{USER_PROMPT}}
ENHANCED: [Your enhanced version with specific references]

Apply? [Y/n/edit]:
- Y (or Enter): Use the enhanced prompt
- n: Use the original prompt unchanged
- edit: Let me modify the enhancement
```

**If `{{CONFIRM}}` is `false`:**
Apply the enhancement automatically and briefly note what was added:

```
[ll:autoprompt] Enhanced with: [brief 5-10 word summary]
```

Then proceed with the enhanced prompt.

### 4. Continue

After determining the final prompt (enhanced or original), proceed to fulfill the user's request normally.

## Guidelines

- **Be conservative**: Only enhance when the prompt is genuinely vague
- **Add specificity**: Include file paths, component names, function references
- **Preserve intent**: Don't change what the user wants to do, just clarify it
- **Keep it brief**: Enhancements should add ~1-2 sentences of context, not paragraphs
- **Respect bypass**: If the user used a bypass prefix, this hook shouldn't have triggered

## Examples

### Vague → Enhanced

**Original**: "fix the authentication bug"
**Enhanced**: "Fix the authentication bug in the login flow. Check `src/auth/login.ts` for the main handler and `src/auth/middleware.ts` for token validation."

**Original**: "add caching"
**Enhanced**: "Add caching to the API responses. The project uses Redis (see `src/services/cache.ts`). Follow the pattern in `src/api/products.ts:45` for cache key generation."

### Already Clear (No Change)

**Original**: "Update the error message in src/components/Form.tsx line 42"
**Action**: Pass through unchanged - already specific.

**Original**: "What testing framework does this project use?"
**Action**: Pass through unchanged - it's a question, not a task.

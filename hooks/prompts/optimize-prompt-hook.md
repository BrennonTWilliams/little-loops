---
event: UserPromptSubmit
---

# Prompt Optimization Hook

This hook evaluates user prompts for clarity and automatically optimizes vague prompts with codebase-aware enhancements.

## Configuration

Read settings from `.claude/ll-config.json` under `prompt_optimization`:
- `enabled`: Whether to analyze prompts (default: true)
- `mode`: "quick" or "thorough" (default: quick)
- `confirm`: Show diff before applying (default: true)
- `bypass_prefix`: Character to skip optimization (default: "*")
- `clarity_threshold`: Minimum score to pass through (default: 6)

## Skip Conditions

**Immediately pass through without analysis if ANY of these are true:**

1. `enabled` is false in config
2. Prompt starts with bypass prefix (default: `*`)
3. Prompt starts with `/` (slash command)
4. Prompt starts with `#` (memorization/note mode)
5. Prompt is empty or whitespace only
6. Prompt is very short (<10 characters)
7. Prompt is a question (starts with who/what/where/when/why/how and ends with `?`)

If any skip condition matches, **do nothing** - let the prompt pass through unchanged.

## Clarity Analysis

For prompts that don't match skip conditions, perform a rapid clarity assessment:

### Score These Dimensions (1-10)

| Dimension | Low Score (1-3) | High Score (8-10) |
|-----------|-----------------|-------------------|
| **Specificity** | "fix it", "make better" | Specific component, file, behavior |
| **Context** | No file/code references | Mentions files, functions, patterns |
| **Actionability** | Vague goal, unclear deliverable | Clear steps or expected result |
| **Completeness** | Missing key details | All necessary info provided |

### Calculate Overall Score

Average the dimensions. If score >= threshold (default: 6), pass through unchanged.

## Optimization Process

If clarity score is below threshold, optimize the prompt:

### Quick Mode (default)

Gather context from:
- `.claude/ll-config.json` for project settings (src_dir, test_cmd, lint_cmd)
- CLAUDE.md, CONTRIBUTING.md, README.md if they exist

### Thorough Mode

All quick mode context PLUS spawn `prompt-optimizer` agent:

```
Analyze the codebase for context relevant to this prompt:
"[ORIGINAL_PROMPT]"

Search for:
1. Files related to the prompt topic
2. Existing patterns that should be followed
3. Conventions established in the codebase

Return: Relevant files, patterns, specific file:line references
```

### Apply Enhancement Patterns

Transform the prompt by applying these patterns in order:

**1. Clarity**
- Replace vague language with specifics
- "fix the bug" → "Fix the [specific] bug in [component]"
- "improve performance" → "Optimize [specific metric] in [component]"

**2. Codebase Context**
- Add relevant file paths from project config
- Reference test command: `{{config.project.test_cmd}}`
- Include lint command: `{{config.project.lint_cmd}}`

**3. Structure**
- Add numbered steps for multi-part tasks
- Include success criteria as checkboxes
- Add verification commands

**4. Claude-Specific**
- Add "think carefully" or "think hard" for complex tasks
- Include anti-patterns (what NOT to do) when helpful

## Output Behavior

### If confirm: ON (default)

Show interactive diff and ask for confirmation:

```
Prompt Optimization
-------------------
Your prompt could be more specific. Here's an enhanced version:

ORIGINAL:
  > fix the login bug

OPTIMIZED:
  > Fix the authentication bug in the login flow.
  >
  > 1. Locate the login handler in {{config.project.src_dir}}
  > 2. Identify the specific failure condition
  > 3. Fix the logic error
  > 4. Add test case for the fixed behavior
  >
  > Success criteria:
  > - [ ] Login works correctly
  > - [ ] `{{config.project.test_cmd}}` passes

```

Use the AskUserQuestion tool with single-select:
- Question: "Apply this optimized prompt?"
- Options:
  - "Apply" - Use the optimized version
  - "Keep original" - Use original prompt as-is
  - "Edit" - Modify the optimized prompt

### If confirm: OFF

Auto-apply the optimized prompt with brief notification:

```
[Autoprompt] Enhanced: "fix the login bug" → "Fix the authentication bug..."
```

Then proceed with the optimized prompt.

## Examples

### Example 1: Clear Prompt (Pass Through)

**User Prompt:**
> Fix the JWT token expiration bug in src/auth/token.ts where tokens are incorrectly marked as expired

**Analysis:** Specificity 9, Context 9, Actionability 8, Completeness 8 = **8.5/10**

**Action:** Score >= 6, pass through unchanged. Say nothing.

### Example 2: Vague Prompt (Optimize)

**User Prompt:**
> fix the login bug

**Analysis:** Specificity 2, Context 1, Actionability 3, Completeness 2 = **2/10**

**Action:** Score < 6, optimize and show diff (if confirm: ON).

### Example 3: Bypass Prefix (Skip)

**User Prompt:**
> * just quickly add a console.log

**Action:** Starts with `*`, skip entirely. Pass through unchanged.

### Example 4: Question (Skip)

**User Prompt:**
> How does the authentication flow work?

**Action:** Is a question, skip. Pass through unchanged.

## Important Guidelines

1. **Speed is critical** - This runs on every prompt. Be fast.
2. **Err on side of passing through** - When score is borderline (5-6), let it through.
3. **Never block** - Always let prompts through after showing diff.
4. **Be concise** - Short diffs, not essays.
5. **Respect the bypass** - `*` prefix means user knows what they want.
6. **Don't over-trigger** - Annoying users defeats the purpose.

## What NOT to Do

- Don't analyze every word in detail (be fast)
- Don't lecture about prompt engineering
- Don't block the user from proceeding
- Don't suggest optimization for clear prompts
- Don't force optimization on unwilling users
- Don't significantly slow down the user experience

## Remember

The goal is to **help**, not to gatekeep. Most prompts should pass through unchanged. Only optimize when a prompt is so vague that Claude would need to ask clarifying questions anyway.

If you're unsure, let it through. Users can toggle settings with `/ll:toggle_autoprompt`.

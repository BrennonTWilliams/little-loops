# BUG-181: Auto-prompt feature documented but not implemented - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-181-auto-prompt-feature-documented-not-implemented.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The auto-prompt optimization feature is extensively documented but completely non-functional:

### Key Discoveries
- `config-schema.json:334-368` - Complete `prompt_optimization` config schema exists
- `commands/toggle_autoprompt.md` - Full 157-line command documentation exists
- `agents/prompt-optimizer.md` - 213-line agent definition for thorough mode exists
- `hooks/hooks.json:15-25` - `UserPromptSubmit` hook exists but only runs `user-prompt-check.sh`
- `hooks/scripts/user-prompt-check.sh` - Only checks for config file existence (15 lines)

### What's Missing
- `hooks/prompts/optimize-prompt-hook.md` - The hook prompt that would intercept and optimize prompts
- No integration of `user-prompt-check.sh` with prompt optimization config
- No clarity scoring logic
- No bypass pattern detection
- No prompt enhancement logic

## Desired End State

When `prompt_optimization.enabled` is `true` in config:
1. `UserPromptSubmit` hook reads the user prompt
2. Checks bypass patterns (`*`, `/`, `#`, `?`, short prompts <10 chars)
3. If not bypassed, outputs a hook prompt to Claude for optimization
4. Hook prompt instructs Claude to enhance vague prompts with codebase context

### How to Verify
- Toggle autoprompt enabled: prompt triggers optimization guidance
- Use bypass prefix (`*`): prompt passes unchanged
- Use slash command (`/ll:help`): prompt passes unchanged
- Short prompts (<10 chars): prompt passes unchanged

## What We're NOT Doing

- Not implementing "quick" vs "thorough" mode switching in the hook (deferred - the hook prompt handles mode selection)
- Not implementing the confirmation dialog flow (Claude handles this via normal tool interaction)
- Not implementing clarity scoring algorithm (Claude judges clarity naturally)
- Not adding Python backend code (hooks are bash scripts + prompt files)
- Not modifying the `toggle_autoprompt.md` command (already correct)
- Not modifying the `prompt-optimizer.md` agent (already correct)

## Problem Analysis

The feature was designed with documentation and schema, but the critical implementation piece - the hook prompt file and bash script integration - was never created. The `UserPromptSubmit` hook exists but only checks for config presence, not prompt optimization.

## Solution Approach

Create the missing `optimize-prompt-hook.md` file and modify `user-prompt-check.sh` to:
1. Read `prompt_optimization` config settings
2. Check bypass patterns
3. Output the hook prompt when optimization is enabled and not bypassed

The hook prompt will instruct Claude to:
- Analyze the prompt for clarity
- Enhance vague prompts using project context
- Use the `prompt-optimizer` agent in thorough mode

## Implementation Phases

### Phase 1: Create optimize-prompt-hook.md

#### Overview
Create the hook prompt file that tells Claude how to optimize user prompts.

#### Changes Required

**File**: `hooks/prompts/optimize-prompt-hook.md`
**Changes**: Create new file

```markdown
# Prompt Optimization Hook

You've received a user prompt that may benefit from enhancement. Analyze it and improve clarity using codebase context.

## User Prompt
{user_prompt}

## Configuration
- Mode: {mode} (quick|thorough)
- Confirm: {confirm} (true|false)

## Instructions

### 1. Analyze Clarity
Evaluate if the prompt is:
- **Clear**: Specific action + target identified → Pass through unchanged
- **Vague**: Missing specifics, unclear target → Enhance with context

### 2. If Enhancement Needed

**Quick Mode**: Enhance using project knowledge from CLAUDE.md, CONTRIBUTING.md, README.md
**Thorough Mode**: Spawn the `prompt-optimizer` agent to search the codebase

### 3. Present Enhancement

If `confirm` is true:
```
ORIGINAL: {original prompt}
ENHANCED: {enhanced prompt}

Apply? [Y/n/edit]:
```

If `confirm` is false:
Apply the enhancement automatically and show:
```
[ll:autoprompt] Applied: {brief summary of enhancement}
```

### 4. Output
Proceed with the enhanced prompt (or original if already clear).
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `hooks/prompts/optimize-prompt-hook.md`
- [ ] File is valid markdown

**Manual Verification**:
- [ ] Review hook prompt structure makes sense for Claude interaction

---

### Phase 2: Modify user-prompt-check.sh

#### Overview
Update the existing hook script to read prompt optimization config and output the hook prompt when appropriate.

#### Changes Required

**File**: `hooks/scripts/user-prompt-check.sh`
**Changes**: Add config reading and hook prompt output logic

The updated script will:
1. Keep existing config existence check
2. Add jq-based config reading for `prompt_optimization` settings
3. Read user prompt from stdin JSON
4. Check bypass patterns
5. If optimization enabled and not bypassed, cat the hook prompt file with variable substitution

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `shellcheck hooks/scripts/user-prompt-check.sh`
- [ ] Script is executable

**Manual Verification**:
- [ ] Test with bypass prefix `*` - no optimization output
- [ ] Test with slash command `/ll:help` - no optimization output
- [ ] Test with enabled config - optimization prompt appears

---

### Phase 3: Test Integration

#### Overview
Verify the complete flow works end-to-end.

#### Changes Required

No code changes - validation only.

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Enable autoprompt in config, submit vague prompt → sees optimization guidance
- [ ] Disable autoprompt in config, submit vague prompt → no optimization
- [ ] Use `*` bypass prefix → prompt passes through unchanged

---

## Testing Strategy

### Unit Tests
- Shell script logic can be tested with mock JSON input
- Bypass pattern matching for various prefixes

### Integration Tests
- End-to-end with Claude Code (manual)
- Config toggle affects behavior

## References

- Original issue: `.issues/bugs/P3-BUG-181-auto-prompt-feature-documented-not-implemented.md`
- Config schema pattern: `config-schema.json:334-368`
- Similar hook implementation: `hooks/scripts/context-monitor.sh:16-35`
- Existing UserPromptSubmit hook: `hooks/scripts/user-prompt-check.sh:1-15`
- Hook prompt template pattern: `hooks/prompts/continuation-prompt-template.md`

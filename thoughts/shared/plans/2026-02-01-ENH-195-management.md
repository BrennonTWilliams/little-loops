# ENH-195: Tool Evaluator Defaults Table is Documentation-Only Guidance - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-195-tool-evaluator-defaults-is-docs-only.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `/ll:create_loop` command documentation includes a comprehensive "Tool Evaluator Defaults" table (lines 268-289) that shows recommended evaluator types for various tools (pytest, mypy, ruff, eslint, tsc, cargo test, go test).

However, **there is no code** that implements automatic tool pattern detection. This table is purely human guidance for Claude during the wizard flow.

### Key Discoveries
- `commands/create_loop.md:272-293` - Contains "Tool Evaluator Defaults" table and "Detection Instructions" section that implies automatic tool detection
- `scripts/little_loops/fsm/evaluators.py` - No tool pattern detection logic (only has `output_contains` pattern matching for evaluation results)
- `scripts/little_loops/fsm/compilers.py` - No tool pattern detection logic (references "tools" only as goal paradigm step commands)

### Evidence from Code Review
The evaluators.py file contains:
- `output_contains` evaluator with pattern matching - but this matches evaluation OUTPUT, not tool COMMANDS
- LLM-based evaluator using tools - but this is for evaluation, not detection
- No tool command pattern matching or auto-detection of appropriate evaluators

The compilers.py file contains:
- References to "tools" in the goal paradigm - but these are check/fix step COMMANDS to execute, not tool detection
- pattern field only used in output_contains evaluator configuration
- No automatic tool pattern detection logic

**Conclusion**: The documentation correctly describes what SHOULD happen during the wizard (AI matches tool patterns and customizes questions), but there is NO separate code implementation - the AI running the wizard uses the table as guidance when generating questions. The "Detection Instructions" are instructions FOR THE AI, not description of implemented code.

## Desired End State

The documentation should clearly indicate that:
1. The "Tool Evaluator Defaults" table provides guidance for the AI during interactive wizard creation
2. The "Detection Instructions" are instructions for the AI to follow when customizing questions
3. There is NO separate code-based automatic tool detection - it's part of the AI's wizard flow

### How to Verify
- Read the create_loop.md command documentation
- The table and instructions should be clearly marked as AI guidance
- No implication of separate code implementation

## What We're NOT Doing

- Not implementing actual code-based tool pattern detection (deferred to separate enhancement)
- Not removing the helpful table (it provides useful guidance)
- Not changing the wizard flow behavior
- Not modifying any Python code

## Problem Analysis

The issue is that the "Detection Instructions" section (lines 288-293) uses imperative language that could be interpreted as describing implemented code:

```
**Detection Instructions:**
1. After the check command is determined, match against the tool patterns above
2. If a match is found, customize the evaluator question...
```

This sounds like it's describing an algorithm that runs automatically. In reality, these are instructions FOR THE AI that reads and follows this skill definition during the wizard flow.

The table itself is fine - it's clearly guidance. The problem is the framing of the "Detection Instructions" section.

## Solution Approach

Add a clear disclaimer note before the "Tool Evaluator Defaults" table that clarifies:
1. This table guides the AI during the interactive wizard flow
2. There is no separate code-based automatic tool detection
3. Users should select appropriate evaluators based on their tools

Additionally, add a clarifying note to the "Detection Instructions" section to make it clear these are instructions for the AI executing the wizard.

## Implementation Phases

### Phase 1: Add Disclaimer to Tool Evaluator Defaults Section

#### Overview
Add a clear disclaimer before the Tool Evaluator Defaults table explaining that this is AI guidance for the wizard flow, not implemented code.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add disclaimer note after line 272 (before the table)

Add this note:
```markdown
> **Note**: This table provides guidance for the AI during the interactive wizard flow. There is no separate code-based automatic tool detection - the AI uses this table to customize question wording based on the check command you provide. You should select the appropriate evaluator type for your specific tools.
```

#### Success Criteria

**Automated Verification**:
- [ ] Documentation is valid markdown with no syntax errors
- [ ] No Python code changes required (no tests needed)

**Manual Verification**:
- [ ] Read the modified section in create_loop.md
- [ ] Verify the disclaimer clearly distinguishes between AI guidance and implemented code
- [ ] Verify the tone is helpful and not defensive

---

### Phase 2: Clarify Detection Instructions Section

#### Overview
Add a clarifying note to the "Detection Instructions" section to make it explicit these are instructions for the AI.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add clarifying sentence after the "Detection Instructions:" heading

Add this clarification:
```markdown
**Detection Instructions** (for the AI executing this wizard):
```

Or keep the heading as-is and add a note after it:
```markdown
**Detection Instructions:**

> These instructions guide the AI's behavior during the wizard flow to customize questions based on the detected tool pattern.

1. After the check command is determined...
```

#### Success Criteria

**Automated Verification**:
- [ ] Documentation is valid markdown with no syntax errors

**Manual Verification**:
- [ ] Read the modified section
- [ ] Verify it's clear these are instructions for the AI, not description of implemented code
- [ ] Verify the flow remains logical

## Testing Strategy

### Manual Testing
- Read the full create_loop.md command file
- Verify the new disclaimers provide clarity without being verbose
- Verify a new user would understand that the AI (not code) handles tool pattern detection during the wizard

## References

- Original issue: `.issues/enhancements/P4-ENH-195-tool-evaluator-defaults-is-docs-only.md`
- Documentation: `commands/create_loop.md:272-293`
- Evaluators code: `scripts/little_loops/fsm/evaluators.py`
- Compilers code: `scripts/little_loops/fsm/compilers.py`

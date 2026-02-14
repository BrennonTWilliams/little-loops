# ENH-124: Smart Defaults Per Tool for Loop Evaluators - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-124-smart-defaults-per-tool-for-loop-evaluators.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

After ENH-122 was completed, the `/ll:create-loop` wizard asks users to select an evaluator type after check commands are determined. However, the default is always "Exit code (Recommended)" regardless of which tool is selected.

### Key Discoveries
- Evaluator selection flow exists at `commands/create_loop.md:268-344`
- The wizard already knows about common tools: mypy, pytest, ruff, npm test, etc. (`create_loop.md:238-263`)
- Pattern matching for tools already exists in `scripts/little_loops/issue_history.py:2011-2057` using regex patterns
- Gitignore pattern database with metadata at `scripts/little_loops/git_operations.py:28-90` provides a model for pattern databases
- The `_build_evaluate_config()` helper at `compilers.py:51-78` handles evaluator spec processing

### Current Flow
1. User selects check target (mypy, ruff, pytest, custom)
2. User selects evaluator type (exit_code always recommended)
3. If output_contains/output_numeric, user specifies pattern/condition

### Problem
All tools default to "Exit code (Recommended)" even though some tools (like mypy with specific output formats) might benefit from output parsing evaluation.

## Desired End State

When a user selects or enters a common tool in the wizard:
1. The wizard detects the tool from the check command string
2. It looks up a recommended evaluator from a tool defaults database
3. It pre-selects or prominently displays the recommended evaluator with an explanation

Example:
```
Detected tool: mypy
Recommended evaluator: Exit code (mypy returns non-zero on type errors)
```

### How to Verify
- Run `/ll:create-loop`, select "Build from paradigm" → "Fix errors until clean"
- Select "Type errors (mypy)" as check target
- Evaluator question should show "Exit code (Recommended for mypy)"
- For custom commands matching known patterns, appropriate defaults should be suggested

## What We're NOT Doing

- Not implementing JSON output parsing for tools (that's a separate evaluator type)
- Not changing compiler behavior - only wizard UX
- Not making the defaults mandatory - user can always override
- Not adding new evaluator types

## Problem Analysis

The wizard has predefined tool options but doesn't leverage this knowledge for evaluator recommendations. The issue is purely in the wizard instructions at `commands/create_loop.md`.

## Solution Approach

Add a "Tool Evaluator Defaults" reference section to `create_loop.md` that provides:
1. A mapping of tool patterns to recommended evaluators
2. Instructions for Claude to detect the tool and adjust the evaluator question dynamically

This is a documentation-only change since the wizard is a markdown instruction file that Claude follows.

## Implementation Phases

### Phase 1: Add Tool Evaluator Defaults Reference

#### Overview
Add a new reference section to `commands/create_loop.md` with tool patterns and recommended evaluators.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add a new "Tool Evaluator Defaults" section before the evaluator selection questions

Insert after line 267 (before "Evaluator Selection"):

```markdown
**Tool Evaluator Defaults:**

When a check command is determined (from presets or custom input), use this table to recommend the appropriate evaluator:

| Tool Pattern | Recommended Evaluator | Rationale |
|--------------|----------------------|-----------|
| `pytest` | exit_code | Well-behaved: 0=all pass, 1=failures, 2+=errors |
| `mypy` | exit_code | Well-behaved: 0=no errors, 1=type errors |
| `ruff check` | exit_code | Well-behaved: 0=clean, 1=violations |
| `ruff format --check` | exit_code | Well-behaved: 0=formatted, 1=needs formatting |
| `npm test` | exit_code | Standard npm behavior |
| `npx tsc --noEmit` | exit_code | Well-behaved: 0=no errors |
| `npx eslint` | exit_code | Well-behaved: 0=clean, 1=violations |

**Detection Instructions:**
1. After the check command is determined, match against the tool patterns above
2. If a match is found, update the evaluator question to show the matched tool's recommendation
3. Modify the first option label to include the tool name: "Exit code (Recommended for {tool})"
4. Add the rationale to the option description

**Example with mypy detected:**
```yaml
questions:
  - question: "How should success be determined for the mypy check?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for mypy)"
        description: "Well-behaved: 0=no errors, 1=type errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      ...
```

**For custom commands:** If no known tool pattern matches, use the generic "Exit code (Recommended)" default.
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run `/ll:create-loop`, select goal paradigm with mypy - evaluator shows "Recommended for mypy"
- [ ] Run `/ll:create-loop`, select goal paradigm with ruff - evaluator shows "Recommended for ruff"
- [ ] Run `/ll:create-loop` with custom command matching pytest - evaluator shows "Recommended for pytest"
- [ ] Run `/ll:create-loop` with unknown custom command - evaluator shows generic "Recommended"

---

### Phase 2: Update Invariants and Imperative Paradigm Sections

#### Overview
Apply the same tool detection pattern to the invariants and imperative paradigm evaluator questions.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Update the invariants evaluator question (lines 402-418) and imperative evaluator question (lines 578-594) to reference the tool defaults table

For Invariants (around line 402), add before the evaluator question:
```markdown
Use the Tool Evaluator Defaults table above to customize the evaluator recommendation based on the constraint's check command.
```

For Imperative (around line 578), add before the evaluator question:
```markdown
Use the Tool Evaluator Defaults table above to customize the evaluator recommendation based on the exit condition check command.
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run `/ll:create-loop` with invariants paradigm - each constraint shows tool-specific evaluator recommendation
- [ ] Run `/ll:create-loop` with imperative paradigm - exit condition shows tool-specific evaluator recommendation

---

## Testing Strategy

### Manual Tests
Since this is a documentation change affecting Claude's behavior, testing is manual:
1. Test each paradigm with known tools (pytest, mypy, ruff)
2. Test with custom commands matching known patterns
3. Test with unknown commands to verify fallback behavior

### No Unit Tests Required
This change is purely to the wizard instructions in `create_loop.md` - no Python code is modified.

## References

- Original issue: `.issues/enhancements/P3-ENH-124-smart-defaults-per-tool-for-loop-evaluators.md`
- Related completed issue: `.issues/completed/P2-ENH-122-add-evaluator-selection-to-loop-wizard.md`
- Wizard implementation: `commands/create_loop.md:268-344`
- Pattern database example: `scripts/little_loops/issue_history.py:2011-2057`

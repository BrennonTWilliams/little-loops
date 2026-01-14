# FEAT-048: /ll:create-loop Command - Implementation Plan

## Issue Reference
- **File**: .issues/features/P3-FEAT-048-create-loop-command.md
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- **Existing skill pattern**: `skills/issue-workflow.md:1-7` shows frontmatter with `name` and `description` fields containing trigger keywords
- **AskUserQuestion patterns**: `commands/init.md:194-425` demonstrates multi-step wizard with grouped questions (up to 4 per call)
- **Paradigm compilers**: `scripts/little_loops/fsm/compilers.py:51-90` provides `compile_paradigm()` for all paradigm types
- **Validation**: `scripts/little_loops/fsm/validation.py:301-353` provides `load_and_validate()` function
- **ll-loop CLI**: `scripts/little_loops/cli.py:762-777` provides `ll-loop validate` command
- **No .loops directory** yet - needs to be created

### Dependencies (All Completed)
- FEAT-040: FSM Schema Definition and Validation ✅
- FEAT-041: Paradigm Compilers ✅
- FEAT-047: ll-loop CLI Tool ✅

## Desired End State

A skill file at `skills/create-loop.md` that:
1. Guides users through interactive paradigm selection via AskUserQuestion
2. Gathers paradigm-specific parameters through follow-up questions
3. Generates valid paradigm YAML based on user selections
4. Shows preview and gets confirmation before saving
5. Saves to `.loops/<name>.yaml`
6. Validates with `ll-loop validate`

### How to Verify
- Skill file exists with proper frontmatter
- Skill appears in `/ll:help` output
- Interactive workflow functions when invoked
- Generated YAML validates successfully with `ll-loop validate`

## What We're NOT Doing

- Not implementing custom Python generation code - skill uses Claude to generate YAML
- Not creating templates in a separate template directory
- Not adding new CLI commands - using existing `ll-loop validate`
- Not handling advanced FSM paradigm (direct state machine editing) - only the 4 high-level paradigms

## Problem Analysis

The issue requires creating an interactive skill that:
1. Uses AskUserQuestion to determine user intent
2. Maps user selections to paradigm-specific YAML structures
3. Generates valid YAML that passes validation
4. Saves to the correct location

The challenge is crafting the skill instructions so Claude can:
- Ask the right follow-up questions for each paradigm
- Generate valid YAML matching the compiler input schemas
- Handle edge cases and custom commands via "Other" option

## Solution Approach

Create a comprehensive skill document that:
1. Defines trigger conditions and allowed tools in frontmatter
2. Provides step-by-step workflow instructions
3. Documents the AskUserQuestion patterns for each paradigm
4. Includes YAML templates for each paradigm type
5. Specifies validation and save procedures

## Implementation Phases

### Phase 1: Create Directory Structure

#### Overview
Ensure the `.loops/` directory exists for storing loop configurations.

#### Changes Required

Create directory via Bash:
```bash
mkdir -p .loops
```

#### Success Criteria

**Automated Verification**:
- [ ] Directory exists: `test -d .loops && echo "OK" || echo "MISSING"`

---

### Phase 2: Create Skill File

#### Overview
Create the `skills/create-loop.md` skill file with comprehensive instructions.

#### Changes Required

**File**: `skills/create-loop.md`
**Changes**: Create new skill file

The skill file must include:

1. **Frontmatter** with:
   - `name: create-loop`
   - `description` with trigger keywords: "create loop", "new loop", "make automation loop", "create-loop"

2. **Workflow Section** explaining:
   - Step 1: Paradigm selection via AskUserQuestion
   - Step 2: Paradigm-specific parameter gathering
   - Step 3: Loop name selection
   - Step 4: YAML generation and preview
   - Step 5: Confirmation and save
   - Step 6: Validation with `ll-loop validate`

3. **Paradigm-Specific Question Templates**:
   - Goal: checks to run, fix tool, max iterations
   - Invariants: constraint definitions, maintain mode
   - Convergence: metric command, target, fix action
   - Imperative: step list, until condition

4. **YAML Templates** showing the exact structure for each paradigm matching the compiler input schemas from `compilers.py`

5. **Validation and Save Instructions**:
   - Write to `.loops/<name>.yaml`
   - Run `ll-loop validate <name>`
   - Show "Run now with: ll-loop <name>" on success

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f skills/create-loop.md && echo "OK" || echo "MISSING"`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Skill appears in `/ll:help` output
- [ ] Frontmatter is valid YAML
- [ ] Instructions are clear and actionable

---

### Phase 3: Verify Integration

#### Overview
Test that the skill integrates correctly with the plugin.

#### Changes Required

No code changes - verification only.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] `ll-loop --help` works: `ll-loop --help`

**Manual Verification**:
- [ ] Invoking `/ll:create-loop` triggers the skill
- [ ] AskUserQuestion displays properly for paradigm selection
- [ ] Follow-up questions are paradigm-appropriate
- [ ] Generated YAML validates with `ll-loop validate`

---

## Testing Strategy

### Unit Tests
- No new Python code, so no new unit tests required
- Existing tests remain passing

### Integration Tests
Manual testing with various paradigm selections:

1. **Goal paradigm flow**
   - Select "Fix errors until clean"
   - Choose type errors + lint errors
   - Verify generated YAML has correct structure

2. **Invariants paradigm flow**
   - Select "Maintain code quality continuously"
   - Add multiple constraints
   - Verify constraint chain in FSM

3. **Convergence paradigm flow**
   - Select "Drive a metric toward a target"
   - Enter custom metric command
   - Verify convergence FSM structure

4. **Imperative paradigm flow**
   - Select "Run a sequence of steps"
   - Enter step list
   - Verify sequential FSM structure

## References

- Original issue: `.issues/features/P3-FEAT-048-create-loop-command.md`
- Design doc: `docs/generalized-fsm-loop.md:1750-1834`
- Existing skill pattern: `skills/issue-workflow.md:1-7`
- AskUserQuestion patterns: `commands/init.md:194-425`
- Compiler schemas: `scripts/little_loops/fsm/compilers.py:105-429`
- Validation: `scripts/little_loops/fsm/validation.py:301-353`

# FEAT-028: Workflow Automation Proposer Skill - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-028-workflow-automation-proposer-skill.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

This is Step 3 of the 3-step workflow analysis pipeline:
- **Step 1** (completed): `workflow-pattern-analyzer` agent produces `step1-patterns.yaml`
- **Step 2** (completed): `workflow_sequence_analyzer.py` module produces `step2-workflows.yaml`
- **Step 3** (this issue): Create skill that synthesizes patterns into automation proposals

### Key Discoveries
- Skills use folder structure: `skills/<skill-name>/SKILL.md` (`skills/capture-issue/SKILL.md:1-63`)
- Skill frontmatter uses `description` field with multi-line YAML and trigger keywords
- `workflow-pattern-analyzer` agent defines output schema at `agents/workflow-pattern-analyzer.md:142-190`
- `workflow_sequence_analyzer.py` defines data structures at lines 82-202
- No `skills/workflow-automation-proposer/` directory exists yet

### Patterns to Follow
- **Skill frontmatter**: From `skills/capture-issue/SKILL.md:1-6` - use `description` with trigger keywords
- **Content structure**: Clear sections with headers, tables, and examples
- **Output directory**: `.claude/workflow-analysis/` (same as Steps 1 and 2)

## Desired End State

A skill file at `skills/workflow-automation-proposer/SKILL.md` that:
1. Reads `step1-patterns.yaml` and `step2-workflows.yaml` from the workflow analysis directory
2. Synthesizes patterns and workflows into concrete automation proposals
3. Outputs `step3-proposals.yaml` with prioritized recommendations
4. Handles both explicit file path arguments and default file locations

### How to Verify
- Skill file exists at correct location
- YAML frontmatter is valid with description and trigger keywords
- Content provides clear instructions for proposal synthesis
- Output schema matches the specification in the issue

## What We're NOT Doing

- Not implementing actual automation (proposals are suggestions only)
- Not creating a Python module (this is a skill, not code)
- Not modifying the `/ll:analyze-workflows` command (that's FEAT-029)
- Not adding tests (skills are markdown files, not code)

## Problem Analysis

The workflow analysis pipeline needs a final step to synthesize patterns and workflows into actionable automation proposals. The issue provides detailed specifications including:
- Input/output file resolution
- Proposal type taxonomy
- Priority and effort calculation criteria
- Output YAML schema

## Solution Approach

Create a skill markdown file that instructs Claude to:
1. Read input files (step1-patterns.yaml and step2-workflows.yaml)
2. Analyze patterns and workflows for automation opportunities
3. Match patterns to appropriate automation types
4. Calculate priority and effort estimates
5. Generate implementation sketches
6. Write structured YAML output

## Implementation Phases

### Phase 1: Create Skill Directory and File

#### Overview
Create the skill directory and SKILL.md file with proper frontmatter and comprehensive instructions.

#### Changes Required

**File**: `skills/workflow-automation-proposer/SKILL.md`
**Changes**: Create new file with YAML frontmatter and skill instructions

The skill will include:
1. YAML frontmatter with description and trigger keywords
2. Overview of the skill's role in the pipeline
3. Input resolution instructions
4. Proposal type taxonomy
5. Priority and effort calculation guidance
6. Output schema specification
7. Important guidelines

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `skills/workflow-automation-proposer/SKILL.md`
- [ ] YAML frontmatter parses correctly (no syntax errors)
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] Skill description is clear and actionable
- [ ] Trigger keywords are appropriate
- [ ] Output schema matches issue specification
- [ ] Instructions cover all proposal types

---

### Phase 2: Verify Plugin Recognition

#### Overview
Ensure the skill is properly recognized by the plugin system.

#### Changes Required

No code changes needed - skills in the `skills/` directory should be auto-discovered.

#### Success Criteria

**Automated Verification**:
- [ ] Skill directory structure follows convention: `skills/workflow-automation-proposer/SKILL.md`

**Manual Verification**:
- [ ] Review skill file for completeness
- [ ] Compare against existing skills for consistency

## Testing Strategy

### Validation
- Verify YAML frontmatter syntax
- Ensure all sections from the issue specification are included
- Check output schema matches expected format

## References

- Original issue: `.issues/features/P2-FEAT-028-workflow-automation-proposer-skill.md`
- Step 1 agent: `agents/workflow-pattern-analyzer.md`
- Step 2 module: `scripts/little_loops/workflow_sequence_analyzer.py`
- Example skill: `skills/capture-issue/SKILL.md`

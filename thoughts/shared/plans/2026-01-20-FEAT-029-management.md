# FEAT-029: /ll:analyze-workflows Command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-029-analyze-workflows-command.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The project has a 3-step workflow analysis pipeline with all components implemented:

### Key Discoveries
- **Step 1 Agent**: `agents/workflow-pattern-analyzer.md` exists and defines the pattern categorization agent invoked via Task tool
- **Step 2 CLI**: `scripts/little_loops/workflow_sequence_analyzer.py` exists with `ll-workflows` CLI entry point at `pyproject.toml:53`
- **Step 3 Skill**: `skills/workflow-automation-proposer/SKILL.md` exists and defines the proposal generation skill

### Patterns to Follow
- Command frontmatter pattern from `commands/check_code.md:1-9`
- Task tool invocation pattern from `commands/manage_issue.md:95-135`
- TodoWrite progress tracking from `commands/scan_codebase.md:23-36`
- Summary report generation from `commands/check_code.md:133-155`
- Error handling with clear output from `commands/manage_issue.md:415-454`

## Desired End State

A `/ll:analyze-workflows` command that:
1. Auto-detects the most recent user-messages JSONL file
2. Orchestrates the 3-step pipeline sequentially
3. Generates a human-readable summary report
4. Tracks progress via TodoWrite

### How to Verify
- Run `/ll:analyze-workflows` with an existing user-messages file
- Verify step1-patterns.yaml, step2-workflows.yaml, step3-proposals.yaml are created
- Verify summary-{timestamp}.md is generated
- Check error handling by providing non-existent file path

## What We're NOT Doing

- Not modifying the existing agent, CLI, or skill implementations
- Not adding new Python code - this is purely a command orchestration file
- Not implementing verbose mode beyond basic progress output (kept simple)

## Problem Analysis

Users need a single command to run the entire workflow analysis pipeline. Currently they would need to:
1. Manually find the user-messages file
2. Spawn the pattern analyzer agent
3. Run the ll-workflows CLI
4. Invoke the automation proposer skill
5. Manually compile results

## Solution Approach

Create a single command file `commands/analyze-workflows.md` that:
1. Uses Glob to auto-detect input files
2. Uses Task tool to spawn the pattern analyzer agent (Step 1)
3. Uses Bash tool to run the ll-workflows CLI (Step 2)
4. Uses Skill tool to invoke the automation proposer (Step 3)
5. Uses Read/Write to generate a summary report (Step 4)
6. Uses TodoWrite to track progress throughout

## Implementation Phases

### Phase 1: Create Command File

#### Overview
Create `commands/analyze-workflows.md` with the complete orchestration logic.

#### Changes Required

**File**: `commands/analyze-workflows.md`
**Changes**: Create new file with full command definition

The command will follow this structure:

1. **Frontmatter** - Define description, allowed-tools, and arguments
2. **Input Detection** - Logic to find the most recent user-messages file
3. **Step 1** - Task tool invocation for workflow-pattern-analyzer
4. **Step 2** - Bash tool invocation for ll-workflows CLI (note: CLI uses `analyze` subcommand, not `--step2` flag per actual implementation)
5. **Step 3** - Skill tool invocation for workflow-automation-proposer
6. **Step 4** - Summary generation with Read/Write
7. **Error Handling** - Clear error messages per step
8. **Final Report** - Machine-parseable output format

#### Key Implementation Details

**CLI Invocation Correction**: The issue file shows `ll-workflows analyze --step2` but the actual CLI implementation at `workflow_sequence_analyzer.py:816-862` uses:
```bash
ll-workflows analyze --input {file} --patterns {file} --output {file}
```
There is no `--step2` flag - the command will use the correct syntax.

**Output Directory**: Create `.claude/workflow-analysis/` if it doesn't exist.

#### Success Criteria

**Automated Verification**:
- [ ] File `commands/analyze-workflows.md` exists
- [ ] Lint passes: `ruff check scripts/`
- [ ] No syntax errors in markdown frontmatter (valid YAML)

**Manual Verification**:
- [ ] Command appears in `/ll:help` output
- [ ] Frontmatter has correct structure (description, allowed-tools, arguments)

---

### Phase 2: Verify End-to-End Pipeline (if test data exists)

#### Overview
Test the command with existing user-messages data if available.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] If `.claude/user-messages-*.jsonl` exists, run `/ll:analyze-workflows`
- [ ] Verify all output files are created in `.claude/workflow-analysis/`

## Testing Strategy

### Unit Tests
- Existing tests in `scripts/tests/test_workflow_sequence_analyzer.py` cover Step 2
- Existing tests in `scripts/tests/test_workflow_integration.py` cover integration

### Integration Tests
- End-to-end test requires a user-messages JSONL file
- Can be manually verified with real or synthetic data

## References

- Original issue: `.issues/features/P2-FEAT-029-analyze-workflows-command.md`
- Step 1 agent: `agents/workflow-pattern-analyzer.md`
- Step 2 CLI: `scripts/little_loops/workflow_sequence_analyzer.py:805-913`
- Step 3 skill: `skills/workflow-automation-proposer/SKILL.md`
- CLI entry point: `scripts/pyproject.toml:53`
- Similar command patterns: `commands/check_code.md`, `commands/manage_issue.md`

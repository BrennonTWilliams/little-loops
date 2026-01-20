---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T12:00:00Z
---

# FEAT-029: /ll:analyze-workflows Command

## Summary

Create `/ll:analyze-workflows` command that orchestrates the 3-step workflow analysis pipeline and generates a summary report with automation proposals.

## Motivation

The workflow analysis pipeline consists of three components (FEAT-026 agent, FEAT-027 Python module, FEAT-028 skill) that must run in sequence. Users need a single command to:

- Auto-detect the most recent user messages file
- Run all three analysis steps in order
- Generate a human-readable summary report
- Store all outputs in a consistent location

This command serves as the entry point for workflow analysis.

## Proposed Implementation

### 1. Command Definition: `commands/analyze-workflows.md`

```yaml
---
description: Analyze user message history to identify patterns, workflows, and automation opportunities
allowed_tools:
  - Read
  - Write
  - Glob
  - Task      # Step 1 (agent)
  - Bash      # Step 2 (Python CLI)
  - Skill     # Step 3 (skill)
  - TodoWrite
---
```

### 2. Command Logic

```markdown
# /ll:analyze-workflows

Analyze user messages to identify patterns, workflows, and automation opportunities.

## Arguments

$ARGUMENTS

## Usage

```bash
# Analyze most recent user-messages file (auto-detected)
/ll:analyze-workflows

# Analyze specific file
/ll:analyze-workflows .claude/user-messages-20260112.jsonl

# Analyze with verbose output
/ll:analyze-workflows --verbose
```

## Execution Flow

### Step 0: Input Detection

1. If file path provided, use it
2. Otherwise, find most recent `user-messages-*.jsonl` in `.claude/`
3. Validate file exists and contains messages
4. Create output directory: `.claude/workflow-analysis/`

### Step 1: Pattern Analysis (via Task tool → Agent)

Spawn `workflow-pattern-analyzer` agent using the **Task tool**:
- Input: user-messages JSONL file
- Output: `.claude/workflow-analysis/step1-patterns.yaml`

```
Task tool invocation:
  subagent_type: workflow-pattern-analyzer
  prompt: "Analyze {messages_file} and write results to .claude/workflow-analysis/step1-patterns.yaml"
```

Wait for completion. If failed, report error and stop.

### Step 2: Sequence Analysis (via Bash → Python CLI)

Invoke `workflow-sequence-analyzer` Python module using the **Bash tool**:
- Input: user-messages file + step1-patterns.yaml
- Output: `.claude/workflow-analysis/step2-workflows.yaml`

```bash
ll-workflows analyze --step2 \
  --input {messages_file} \
  --patterns .claude/workflow-analysis/step1-patterns.yaml \
  --output .claude/workflow-analysis/step2-workflows.yaml
```

Wait for completion. Check exit code:
- Exit 0: Success, proceed to Step 3
- Exit 1: Failure, report error from stderr and stop

### Step 3: Automation Proposals (via Skill tool → Skill)

Invoke `workflow-automation-proposer` skill using the **Skill tool**:
- Input: step1-patterns.yaml + step2-workflows.yaml
- Output: `.claude/workflow-analysis/step3-proposals.yaml`

```
Skill tool invocation:
  skill: "workflow-automation-proposer"
  args: ".claude/workflow-analysis/step1-patterns.yaml .claude/workflow-analysis/step2-workflows.yaml"
```

Wait for completion. If failed, report error and stop.

### Step 4: Generate Summary

Read all three output files and generate `summary-{timestamp}.md`:

```markdown
# Workflow Analysis Summary

**Generated**: {timestamp}
**Source**: {input_file} ({message_count} messages)

## Overview

| Metric | Value |
|--------|-------|
| Messages analyzed | {count} |
| Categories identified | {count} |
| Patterns detected | {count} |
| Workflows detected | {count} |
| Proposals generated | {count} |

## Top Patterns

| Pattern | Frequency | Category |
|---------|-----------|----------|
| {pattern} | {freq} | {cat} |
...

## Detected Workflows

| Workflow | Pattern | Sessions | Duration |
|----------|---------|----------|----------|
| {name} | {pattern} | {count} | {mins}m |
...

## Automation Proposals

### High Priority

| ID | Type | Name | Effort |
|----|------|------|--------|
| {id} | {type} | {name} | {effort} |
...

### Medium Priority
...

### Low Priority
...

## Existing Command Suggestions

Based on your usage patterns, consider these existing commands:

| Your Pattern | Suggested Command | Frequency |
|--------------|-------------------|-----------|
| "commit changes" | /ll:commit | 50 |
| "run tests" | /ll:run_tests | 12 |
...

## Next Steps

1. Review high-priority proposals in `step3-proposals.yaml`
2. Implement proposals that match your needs
3. Start using suggested existing commands
4. Re-run analysis after implementing to measure impact

---

*Analysis completed in {duration}*
*Output files: .claude/workflow-analysis/*
```

### Step 5: Report Results

Display summary to user:
- Total messages analyzed
- Key findings (top patterns, workflows)
- High-priority proposals
- Path to full summary file

## Result Normalization

Each step uses a different invocation method, but the orchestrator normalizes results to a common contract:

| Field | Description |
|-------|-------------|
| `success` | Boolean indicating step completed successfully |
| `output_file` | Path to the step's output YAML file |
| `summary` | Brief description of what was produced |
| `error` | Error message if `success` is false |

**Extracting normalized results by invocation type:**

| Invocation | Success Check | Output File | Summary Extraction |
|------------|---------------|-------------|-------------------|
| Task (Agent) | Agent returns without error | Specified in prompt | Check output file exists and read summary from file |
| Bash (CLI) | Exit code == 0 | `--output` parameter | First line of stdout |
| Skill | Skill completes without error | Read from skill output | Parse from skill response |

This allows the orchestrator to use consistent logic for progress reporting and error handling regardless of how each step was invoked.

## Error Handling

If any step fails:
1. Log the error with step number and invocation type
2. Preserve partial outputs (completed steps remain available)
3. Report the specific error from the failed invocation:
   - Task: Agent error message
   - Bash: stderr output and exit code
   - Skill: Skill error response
4. Suggest actionable retry steps:
   - For Step 1 failures: Check input file format
   - For Step 2 failures: Run `ll-workflows analyze --step2 --verbose` for debugging
   - For Step 3 failures: Check that step1 and step2 outputs exist
5. Allow resuming from last successful step (partial outputs preserved)
```

### 3. Output Directory Structure

```
.claude/workflow-analysis/
├── step1-patterns.yaml       # Pattern analysis results
├── step2-workflows.yaml      # Workflow detection results
├── step3-proposals.yaml      # Automation proposals
└── summary-20260112-103000.md # Human-readable summary
```

### 4. Todo List Integration

The command uses TodoWrite to track progress:

```yaml
todos:
  - content: "Detect input file"
    status: in_progress
    activeForm: "Detecting input file"
  - content: "Run Step 1: Pattern Analysis"
    status: pending
    activeForm: "Running pattern analysis"
  - content: "Run Step 2: Sequence Analysis"
    status: pending
    activeForm: "Running sequence analysis"
  - content: "Run Step 3: Automation Proposals"
    status: pending
    activeForm: "Generating automation proposals"
  - content: "Generate summary report"
    status: pending
    activeForm: "Generating summary report"
```

### 5. Example Session

```bash
$ /ll:analyze-workflows

Detecting input file...
Found: .claude/user-messages-20260112-111551.jsonl (200 messages)

Running Step 1: Pattern Analysis...
✓ Identified 15 categories, 23 repeated patterns

Running Step 2: Sequence Analysis...
✓ Detected 8 workflows, 3 cross-session links

Running Step 3: Automation Proposals...
✓ Generated 8 proposals (2 HIGH, 4 MEDIUM, 2 LOW)

Summary
═══════

Top Patterns:
  • "run tests" (12 occurrences) - testing
  • "fix the" (8 occurrences) - debugging
  • "commit" (50 occurrences) - git_operation

Detected Workflows:
  • Checkout Bug Fix (debug → fix → test)
  • Authentication Feature (plan → implement → verify)
  • Reference Cleanup (explore → modify → verify)

High-Priority Proposals:
  1. /ll:cleanup-refs - Automate reference cleanup (MEDIUM effort)
  2. Use /ll:commit - You request commits 50 times manually

Full analysis: .claude/workflow-analysis/summary-20260112-103000.md
```

## Location

| Component | Path |
|-----------|------|
| Command | `commands/analyze-workflows.md` |
| Output Directory | `.claude/workflow-analysis/` |

## Current Behavior

No workflow analysis command exists. Users must manually analyze their message history.

## Expected Behavior

```bash
# Run full analysis pipeline
$ /ll:analyze-workflows
# Generates 4 output files in .claude/workflow-analysis/

# Analyze specific file
$ /ll:analyze-workflows .claude/user-messages-20260101.jsonl

# View results
$ cat .claude/workflow-analysis/summary-*.md
```

## Impact

- **Severity**: High - Entry point for entire workflow analysis system
- **Effort**: Medium - Orchestration logic, summary generation
- **Risk**: Low - Read-only analysis, no modifications to codebase

## Dependencies

- **Task tool**: Spawning `workflow-pattern-analyzer` agent (Step 1)
- **Bash tool**: Invoking `ll-workflows` CLI for sequence analysis (Step 2)
- **Skill tool**: Invoking `workflow-automation-proposer` skill (Step 3)
- **TodoWrite**: Progress tracking
- **Read/Write**: File operations for summary generation
- **Glob**: Input file detection

## Blocked By

- FEAT-011: User Message History Extraction (provides input data)
- FEAT-026: Workflow Pattern Analyzer Agent (Step 1 - invoked via Task tool)
- FEAT-027: Workflow Sequence Analyzer Module (Step 2 - invoked via Bash/CLI)
- FEAT-028: Workflow Automation Proposer Skill (Step 3 - invoked via Skill tool)

## Blocks

None. This is the end of the pipeline.

## Labels

`feature`, `command`, `workflow-analysis`, `orchestration`

---

## Verification Notes

**Verified: 2026-01-17**

- Blocker FEAT-011 (User Message History Extraction) is now **completed** (in `.issues/completed/`)
- Blocker FEAT-026 (Workflow Pattern Analyzer Agent) is now **completed** (in `.issues/completed/`)
- `agents/workflow-pattern-analyzer.md` exists
- Still blocked by FEAT-027 (Python module) and FEAT-028 (skill) which are open
- Partially unblocked - can begin once remaining blockers are implemented

**Updated: 2026-01-20**

- Revised to use heterogeneous invocation:
  - Step 1: Task tool → workflow-pattern-analyzer agent
  - Step 2: Bash tool → `ll-workflows` CLI (Python module)
  - Step 3: Skill tool → workflow-automation-proposer skill
- Added result normalization contract for unified handling
- Updated error handling with invocation-specific guidance

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2

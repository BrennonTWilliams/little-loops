---
description: Analyze user message history to identify patterns, workflows, and automation opportunities
allowed-tools:
  - Read
  - Write
  - Glob
  - Task
  - Bash
  - Skill
  - TodoWrite
arguments:
  - name: file
    description: Path to user-messages JSONL file (auto-detected if omitted)
    required: false
---

# Analyze Workflows

You are tasked with orchestrating the 3-step workflow analysis pipeline to identify patterns and automation opportunities from user message history.

## Configuration

This command creates output in `.claude/workflow-analysis/`:
- `step1-patterns.yaml` - Pattern analysis results (from agent)
- `step2-workflows.yaml` - Workflow detection results (from CLI)
- `step3-proposals.yaml` - Automation proposals (from skill)
- `summary-{timestamp}.md` - Human-readable summary report

## Arguments

$ARGUMENTS

- **file** (optional): Path to user-messages JSONL file
  - If provided, use that file
  - If omitted, auto-detect most recent `user-messages-*.jsonl` in `.claude/`

## Process

### Step 0: Initialize Progress Tracking

Create a todo list to track analysis progress:

```
Use TodoWrite to create:
- Detect input file
- Run Step 1: Pattern Analysis (agent)
- Run Step 2: Sequence Analysis (CLI)
- Run Step 3: Automation Proposals (skill)
- Generate summary report
```

Update todos as each step completes.

### Step 1: Detect Input File

Mark "Detect input file" as in_progress.

**If file argument provided:**
1. Validate the file exists using Read tool
2. Verify it contains JSONL data
3. Count total messages

**If file argument not provided:**
1. Use Glob to find `user-messages-*.jsonl` files in `.claude/`
2. Select the most recent file (by filename timestamp)
3. Validate and count messages

```
Pattern: .claude/user-messages-*.jsonl
```

**On error:**
```
ERROR: Input file detection failed

Reason: [No user-messages files found in .claude/ | File not found: {path}]

To fix:
1. Extract messages first: ll-messages
2. Then run: /ll:analyze-workflows
```

Mark "Detect input file" as completed after success.

**Output:**
```
Input file: {path}
Messages: {count}
```

### Step 2: Ensure Output Directory

Create the output directory if it doesn't exist:
```
.claude/workflow-analysis/
```

### Step 3: Run Pattern Analysis (Agent via Task Tool)

Mark "Run Step 1: Pattern Analysis (agent)" as in_progress.

Spawn the workflow-pattern-analyzer agent using the Task tool:

```
Use Task tool with:
  subagent_type: "ll:workflow-pattern-analyzer"
  prompt: |
    Analyze the user messages file and write pattern analysis results.

    Input file: {messages_file}
    Output file: .claude/workflow-analysis/step1-patterns.yaml

    Process all messages in the file. Categorize each message, detect repeated patterns,
    extract common phrases, inventory tool references, and build entity inventory.

    Write results to the output file using the exact schema defined in your instructions.
```

**Wait for agent to complete.**

**Verify success:**
1. Check that `.claude/workflow-analysis/step1-patterns.yaml` exists
2. Read the file to extract summary metrics

**On error:**
```
ERROR: Step 1 (Pattern Analysis) failed

Agent error: [error message from agent]

Partial outputs preserved in: .claude/workflow-analysis/

To debug:
1. Check input file format (should be JSONL with 'content' field)
2. Manually run: spawn workflow-pattern-analyzer agent
```

Mark "Run Step 1: Pattern Analysis (agent)" as completed after success.

**Output:**
```
Step 1 Complete: Pattern Analysis
- Categories identified: {count}
- Patterns detected: {count}
- Output: .claude/workflow-analysis/step1-patterns.yaml
```

### Step 4: Run Sequence Analysis (CLI via Bash Tool)

Mark "Run Step 2: Sequence Analysis (CLI)" as in_progress.

Run the ll-workflows CLI using the Bash tool:

```bash
ll-workflows analyze \
  --input {messages_file} \
  --patterns .claude/workflow-analysis/step1-patterns.yaml \
  --output .claude/workflow-analysis/step2-workflows.yaml
```

**Check exit code:**
- Exit 0: Success, proceed to Step 5
- Exit non-zero: Failure, report error

**Verify success:**
1. Check that `.claude/workflow-analysis/step2-workflows.yaml` exists
2. Read the file to extract summary metrics

**On error:**
```
ERROR: Step 2 (Sequence Analysis) failed

Exit code: {code}
Error: {stderr}

Partial outputs preserved in: .claude/workflow-analysis/

To debug:
1. Verify step1-patterns.yaml exists and is valid YAML
2. Run manually: ll-workflows analyze --input {file} --patterns {file} --output {file} --verbose
```

Mark "Run Step 2: Sequence Analysis (CLI)" as completed after success.

**Output:**
```
Step 2 Complete: Sequence Analysis
- Workflows detected: {count}
- Session links: {count}
- Output: .claude/workflow-analysis/step2-workflows.yaml
```

### Step 5: Run Automation Proposals (Skill via Skill Tool)

Mark "Run Step 3: Automation Proposals (skill)" as in_progress.

Invoke the workflow-automation-proposer skill using the Skill tool:

```
Use Skill tool with:
  skill: "ll:workflow-automation-proposer"
  args: ".claude/workflow-analysis/step1-patterns.yaml .claude/workflow-analysis/step2-workflows.yaml"
```

**Wait for skill to complete.**

**Verify success:**
1. Check that `.claude/workflow-analysis/step3-proposals.yaml` exists
2. Read the file to extract summary metrics

**On error:**
```
ERROR: Step 3 (Automation Proposals) failed

Skill error: [error from skill]

Partial outputs preserved in: .claude/workflow-analysis/

To debug:
1. Verify step1-patterns.yaml and step2-workflows.yaml exist
2. Manually invoke: /ll:workflow-automation-proposer {paths}
```

Mark "Run Step 3: Automation Proposals (skill)" as completed after success.

**Output:**
```
Step 3 Complete: Automation Proposals
- Proposals generated: {count}
- High priority: {count}
- Medium priority: {count}
- Low priority: {count}
- Output: .claude/workflow-analysis/step3-proposals.yaml
```

### Step 6: Generate Summary Report

Mark "Generate summary report" as in_progress.

Read all three output files and generate a human-readable summary.

**Generate timestamp:**
```bash
date -u +"%Y%m%d-%H%M%S"
```

**Write summary to:** `.claude/workflow-analysis/summary-{timestamp}.md`

**Summary template:**

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
| ... | ... | ... |

## Detected Workflows

| Workflow | Pattern | Sessions | Duration |
|----------|---------|----------|----------|
| {name} | {pattern} | {count} | {mins}m |
| ... | ... | ... | ... |

## Automation Proposals

### High Priority

| ID | Type | Name | Effort |
|----|------|------|--------|
| {id} | {type} | {name} | {effort} |
| ... | ... | ... | ... |

### Medium Priority

| ID | Type | Name | Effort |
|----|------|------|--------|
| {id} | {type} | {name} | {effort} |
| ... | ... | ... | ... |

### Low Priority

| ID | Type | Name | Effort |
|----|------|------|--------|
| {id} | {type} | {name} | {effort} |
| ... | ... | ... | ... |

## Existing Command Suggestions

Based on your usage patterns, consider using these existing commands:

| Your Pattern | Suggested Command | Frequency |
|--------------|-------------------|-----------|
| {pattern} | {command} | {count} |
| ... | ... | ... |

## Next Steps

1. Review high-priority proposals in `step3-proposals.yaml`
2. Implement proposals that match your workflow needs
3. Start using suggested existing commands
4. Re-run analysis after implementing to measure impact

---

*Analysis pipeline: Pattern Analysis → Sequence Analysis → Automation Proposals*
*Output files: .claude/workflow-analysis/*
```

Mark "Generate summary report" as completed after success.

### Step 7: Display Results

Display a concise summary to the user:

```
================================================================================
WORKFLOW ANALYSIS COMPLETE
================================================================================

Input: {file} ({count} messages)

Step 1: Pattern Analysis
  - Categories: {count}
  - Patterns: {count}

Step 2: Sequence Analysis
  - Workflows: {count}
  - Session links: {count}

Step 3: Automation Proposals
  - Total: {count}
  - High priority: {count}
  - Medium priority: {count}
  - Low priority: {count}

## Top Patterns
{top 3 patterns with frequencies}

## Detected Workflows
{top 3 workflows}

## High-Priority Proposals
{list high-priority proposals}

## Existing Command Suggestions
{list suggestions}

Full report: .claude/workflow-analysis/summary-{timestamp}.md

================================================================================
```

## Error Handling Summary

| Step | Error Check | Recovery Action |
|------|-------------|-----------------|
| Input detection | File not found | Suggest running ll-messages extract first |
| Step 1 (Agent) | Agent error or output missing | Preserve partial outputs, suggest manual run |
| Step 2 (CLI) | Non-zero exit code | Preserve partial outputs, show stderr |
| Step 3 (Skill) | Skill error or output missing | Preserve partial outputs, suggest manual run |
| Summary | Read/write error | Report error, output files remain available |

**Partial outputs are always preserved** - if a step fails, previous step outputs remain in `.claude/workflow-analysis/` for debugging or manual continuation.

## Examples

```bash
# Analyze most recent user-messages file (auto-detected)
/ll:analyze-workflows

# Analyze specific file
/ll:analyze-workflows .claude/user-messages-20260112-111551.jsonl

# View results after analysis
cat .claude/workflow-analysis/summary-*.md
```

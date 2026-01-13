# FEAT-026: Workflow Pattern Analysis Agent - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-026-workflow-pattern-analyzer-agent.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

No workflow pattern analysis agent exists. The codebase has:

- **FEAT-011 implemented**: User message extraction via `scripts/little_loops/user_messages.py` provides JSONL input files with `UserMessage` objects containing: content, timestamp, session_id, uuid, cwd, git_branch, is_sidechain
- **7 existing agents** in `agents/` directory following consistent structure with YAML frontmatter
- **Agent conventions**: name, description (with examples and trigger keywords), allowed_tools, model fields
- **Output directory**: `.claude/workflow-analysis/` for analysis outputs

### Key Discoveries
- Agent structure: `agents/codebase-pattern-finder.md:1-28` - frontmatter with examples and trigger keywords
- Output pattern: `commands/scan_codebase.md:172-230` - YAML frontmatter with structured sections
- Input format: `scripts/little_loops/user_messages.py:36-67` - UserMessage dataclass with to_dict() method

## Desired End State

A `workflow-pattern-analyzer` agent that:
1. Reads JSONL files containing extracted user messages
2. Categorizes each message into 15 action types
3. Detects repeated patterns (2-4 word n-grams with frequency >= 3)
4. Extracts common phrases and tool references
5. Builds entity inventory (files, commands, concepts)
6. Outputs structured YAML to `.claude/workflow-analysis/step1-patterns.yaml`

### How to Verify
- Agent file exists at `agents/workflow-pattern-analyzer.md`
- Agent has correct frontmatter (name, description, allowed_tools, model)
- System prompt includes category taxonomy and output schema
- Can be invoked via Task tool with `subagent_type="workflow-pattern-analyzer"`

## What We're NOT Doing

- Not implementing the orchestrating command `/ll:analyze-workflows` (FEAT-029)
- Not implementing the sequence analyzer agent (FEAT-027)
- Not implementing the automation proposer agent (FEAT-028)
- Not creating Python code for pattern detection (agent uses LLM reasoning)
- Not creating the `.claude/workflow-analysis/` directory structure (will be created on first use)

## Solution Approach

Create a single agent file following established conventions from `codebase-pattern-finder.md` and `codebase-analyzer.md`. The agent will:

1. Use Read tool to load JSONL input file
2. Apply LLM reasoning for categorization and pattern detection
3. Use Write tool to output structured YAML

## Implementation Phases

### Phase 1: Create Agent File

#### Overview
Create `agents/workflow-pattern-analyzer.md` with proper frontmatter and comprehensive system prompt.

#### Changes Required

**File**: `agents/workflow-pattern-analyzer.md` (NEW)
**Purpose**: First-step analysis agent for workflow analysis pipeline

The agent file will include:

1. **YAML Frontmatter** with:
   - `name: workflow-pattern-analyzer`
   - `description` with pipeline context, examples, and trigger keywords
   - `allowed_tools: [Read, Write, Grep, Glob]`
   - `model: sonnet` (complex pattern detection requires reasoning)

2. **System Prompt** sections:
   - Role statement and pipeline position
   - Core responsibilities (categorize, detect patterns, extract phrases, inventory entities)
   - Category taxonomy table (15 categories with indicators)
   - Analysis strategy (step-by-step process)
   - Output format (YAML schema matching issue specification)
   - Important guidelines
   - What NOT to do section
   - Purpose reminder

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f agents/workflow-pattern-analyzer.md`
- [ ] YAML frontmatter is valid: Check with grep for required fields
- [ ] All required sections present in system prompt

**Manual Verification**:
- [ ] Agent description is clear and includes usage examples
- [ ] Category taxonomy matches issue specification
- [ ] Output schema matches issue specification

---

## Testing Strategy

### Unit Tests
- No unit tests needed (agent is a markdown file, not code)

### Integration Tests
- Agent can be loaded by Claude Code plugin system
- Agent produces valid YAML output when given sample input

## References

- Original issue: `.issues/features/P2-FEAT-026-workflow-pattern-analyzer-agent.md`
- Similar agent: `agents/codebase-pattern-finder.md:1-202`
- Input format: `scripts/little_loops/user_messages.py:36-67`
- FEAT-011 implementation: `scripts/little_loops/user_messages.py`

# FEAT-219: Agent Skill to Suggest Loops Using ll-messages - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-219-ll-messages-loop-suggestion-skill.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- Skills are located in `skills/<name>/SKILL.md` with YAML frontmatter containing `description` and trigger keywords
- The `ll-messages` CLI outputs JSONL with `UserMessage` containing `content`, `timestamp`, `session_id`, and optional `response_metadata` (tools_used, files_modified)
- FSM loops use paradigms: `goal`, `invariants`, `convergence`, `imperative` - compiled via `scripts/little_loops/fsm/compilers.py`
- The `/ll:create_loop` wizard requires interactive paradigm selection, multi-step questions, and confirmation prompts
- Existing `workflow-automation-proposer` skill provides a template for structured YAML output generation

### Patterns to Follow
- Skill frontmatter format from `skills/workflow-automation-proposer/SKILL.md:1-10`
- Arguments handling with `$ARGUMENTS` placeholder and fallback behavior
- Multi-phase workflow structure from `skills/issue-size-review/SKILL.md`
- YAML output schema pattern from `skills/workflow-automation-proposer/SKILL.md:139-201`
- Paradigm compilation patterns from `scripts/little_loops/fsm/compilers.py:134-475`

## Desired End State

A new skill at `skills/loop-suggester/SKILL.md` that:
1. Takes `ll-messages` JSONL output as input (via argument or runs extraction)
2. Analyzes user message history for repeated multi-step patterns (3-15 steps)
3. Maps detected patterns to appropriate FSM paradigms
4. Generates valid loop YAML configurations with confidence scores
5. Outputs suggestions ready for user review and direct use

### How to Verify
- Skill file exists at `skills/loop-suggester/SKILL.md`
- Skill appears in `/ll:help` output
- Skill can be invoked with `/ll:loop-suggester` or trigger keywords
- Generated YAML passes `ll-loop validate` when saved to `.loops/`
- Output follows structured YAML schema with metadata, summary, and proposals

## What We're NOT Doing

- Not modifying `/ll:create_loop` - this is a parallel path, not a replacement
- Not creating Python code - this is a skill (prompt-based), not a CLI tool
- Not implementing complex ML pattern detection - using heuristic rules
- Not auto-executing suggested loops - output is for user review
- Deferring integration with `ll-loop` execution to future enhancement

## Problem Analysis

Users with established workflows captured in their message history must manually:
1. Notice repetitive patterns in their work
2. Navigate the `/ll:create_loop` interactive wizard
3. Translate observed patterns into paradigm parameters

This skill automates steps 1-3 by analyzing message history directly.

## Solution Approach

Create a skill that:
1. Loads messages from `ll-messages` output (JSONL with response context)
2. Extracts tool usage sequences from `response_metadata.tools_used`
3. Identifies repeated patterns using heuristics:
   - Check-fix-verify cycles → goal paradigm
   - Multiple sequential constraints → invariants paradigm
   - Metric tracking patterns → convergence paradigm
   - Ordered step sequences → imperative paradigm
4. Generates paradigm-specific YAML using the schema from `fsm-loop-schema.json`
5. Outputs structured proposals with confidence scores

## Implementation Phases

### Phase 1: Create Skill File Structure

#### Overview
Create the skill file with proper frontmatter, description, and trigger keywords.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Create new skill file

```markdown
---
description: |
  Analyze user message history to suggest FSM loop configurations.
  Uses ll-messages output to identify repeated workflows and generate
  ready-to-use loop YAML files.

  Trigger keywords: "suggest loops", "loop from history", "automate workflow",
  "create loop from messages", "analyze messages for loops", "ll-messages loop"
---

# Loop Suggester

[Full content in implementation]
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f skills/loop-suggester/SKILL.md`
- [ ] Has valid YAML frontmatter with description

**Manual Verification**:
- [ ] Skill appears in available skills list

---

### Phase 2: Define Input Resolution

#### Overview
Define how the skill resolves its input data - either from provided argument or by running `ll-messages`.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Add Arguments and Input Resolution sections

The skill should:
1. Accept `$ARGUMENTS` as path to existing JSONL file
2. If empty, run `ll-messages --include-response-context -n 200 --stdout` to get recent messages
3. Parse JSONL into message objects for analysis

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check skills/`

**Manual Verification**:
- [ ] Input resolution logic is clearly documented

---

### Phase 3: Define Pattern Detection Logic

#### Overview
Define the heuristics for detecting loop-worthy patterns in message history.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Add Pattern Detection section with detection rules

Pattern detection rules:
1. **Tool sequence analysis**: Group consecutive messages by tool usage
2. **Check-fix cycles**: Detect `Bash(test/lint/type)` followed by `Edit` followed by same check
3. **Multi-constraint patterns**: Multiple different checks in sequence (lint + types + tests)
4. **Repetition threshold**: Pattern must appear 3+ times to suggest automation

Paradigm mapping:
| Pattern Type | Paradigm | Indicators |
|--------------|----------|------------|
| Single check-fix-verify | goal | Same check tool appears before and after Edit |
| Multiple sequential checks | invariants | Different check tools in sequence, all must pass |
| Metric improvement | convergence | Numeric output comparison (coverage, error count) |
| Ordered steps | imperative | Consistent tool sequence without branching |

#### Success Criteria

**Automated Verification**:
- [ ] File syntax is valid markdown

**Manual Verification**:
- [ ] Detection rules cover the four paradigms
- [ ] Rules are specific enough to be actionable

---

### Phase 4: Define Output Schema

#### Overview
Define the YAML output schema for loop suggestions.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Add Output Schema section

Schema structure:
```yaml
analysis_metadata:
  source_file: [path to JSONL or "live extraction"]
  messages_analyzed: [count]
  analysis_timestamp: [ISO 8601]
  skill: loop-suggester
  version: "1.0"

summary:
  total_suggestions: [count]
  by_paradigm:
    goal: [count]
    invariants: [count]
    convergence: [count]
    imperative: [count]
  message_time_range:
    start: [ISO 8601]
    end: [ISO 8601]

suggestions:
  - id: "loop-001"
    name: "[suggested loop name]"
    paradigm: [goal|invariants|convergence|imperative]
    confidence: [0.0-1.0]
    rationale: |
      [Why this pattern was detected, with message references]
    source_patterns:
      - messages: [list of message UUIDs]
        tool_sequence: [list of tools used]
        frequency: [count]
    yaml_config: |
      [Complete, valid paradigm YAML ready for ll-loop]
    validation_notes: |
      [Any caveats or customization suggestions]
```

#### Success Criteria

**Automated Verification**:
- [ ] Schema example is valid YAML

**Manual Verification**:
- [ ] Schema provides enough detail for user to evaluate suggestion
- [ ] yaml_config field contains ready-to-use loop configuration

---

### Phase 5: Define Analysis Process

#### Overview
Define the step-by-step process the skill follows to analyze messages and generate suggestions.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Add Analysis Process section with numbered steps

Process:
1. **Load messages**: Parse JSONL, extract content and response_metadata
2. **Build tool sequences**: For each message with response_metadata, extract tools_used
3. **Identify sessions**: Group messages by session_id
4. **Detect cycles**: Find repeated tool sequences within and across sessions
5. **Map to paradigms**: Apply paradigm mapping rules from Phase 3
6. **Generate YAML**: For each detected pattern, generate paradigm-specific YAML
7. **Calculate confidence**: Based on frequency, consistency, and pattern clarity
8. **Output suggestions**: Write structured YAML to output location

#### Success Criteria

**Automated Verification**:
- [ ] File exists and is readable

**Manual Verification**:
- [ ] Process steps are clear and actionable
- [ ] Each step has defined inputs and outputs

---

### Phase 6: Add Example Suggestions

#### Overview
Add concrete examples showing what generated suggestions look like.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Add Examples section with sample outputs

Example 1: Goal paradigm (type error fix loop)
```yaml
- id: "loop-001"
  name: "type-error-fixer"
  paradigm: goal
  confidence: 0.85
  rationale: |
    Detected 7 occurrences of: Bash(mypy) → Edit → Bash(mypy) cycle.
    User repeatedly checks for type errors, fixes them, and re-checks.
  yaml_config: |
    paradigm: goal
    name: "type-error-fixer"
    goal: "No type errors in source"
    tools:
      - "mypy scripts/"
      - "/ll:manage_issue bug fix"
    max_iterations: 20
    evaluator:
      type: exit_code
```

Example 2: Invariants paradigm (quality gate)
```yaml
- id: "loop-002"
  name: "quality-gate"
  paradigm: invariants
  confidence: 0.72
  rationale: |
    Detected sequential pattern: Bash(ruff) → Bash(mypy) → Bash(pytest)
    appearing in 4 sessions. User maintains multiple quality constraints.
  yaml_config: |
    paradigm: invariants
    name: "quality-gate"
    constraints:
      - name: "lint"
        check: "ruff check scripts/"
        fix: "ruff check --fix scripts/"
      - name: "types"
        check: "mypy scripts/"
        fix: "/ll:manage_issue bug fix"
      - name: "tests"
        check: "pytest scripts/tests/"
        fix: "/ll:manage_issue bug fix"
    max_iterations: 30
```

#### Success Criteria

**Automated Verification**:
- [ ] Example YAML is valid

**Manual Verification**:
- [ ] Examples demonstrate realistic suggestions
- [ ] yaml_config would pass `ll-loop validate`

---

### Phase 7: Add Guidelines and Limitations

#### Overview
Document what the skill should and should not do, plus limitations.

#### Changes Required

**File**: `skills/loop-suggester/SKILL.md`
**Changes**: Add Guidelines and Limitations sections

Guidelines:
- Only suggest loops for patterns appearing 3+ times
- Prefer simpler paradigms (goal > invariants > imperative)
- Include customization notes when tool paths may vary
- Warn about patterns that may be project-specific

Limitations:
- Cannot detect semantic intent, only tool patterns
- May suggest loops for one-time complex tasks
- Confidence scores are heuristic, not probabilistic
- Requires `--include-response-context` for best results

#### Success Criteria

**Automated Verification**:
- [ ] File is complete markdown

**Manual Verification**:
- [ ] Guidelines prevent low-value suggestions
- [ ] Limitations set appropriate expectations

---

## Testing Strategy

### Manual Testing
1. Run `ll-messages --include-response-context -n 200 -o test-messages.jsonl`
2. Invoke `/ll:loop-suggester test-messages.jsonl`
3. Verify output contains structured YAML with suggestions
4. Copy a `yaml_config` to `.loops/test-loop.yaml`
5. Run `ll-loop validate test-loop` to verify validity

### Integration Testing
1. Use skill without arguments (should run ll-messages automatically)
2. Verify skill handles empty message history gracefully
3. Verify skill handles messages without response_metadata

## References

- Original issue: `.issues/features/P3-FEAT-219-ll-messages-loop-suggestion-skill.md`
- Skill template: `skills/workflow-automation-proposer/SKILL.md`
- FSM schema: `scripts/little_loops/fsm/fsm-loop-schema.json`
- Paradigm compilers: `scripts/little_loops/fsm/compilers.py:81-119`
- User messages module: `scripts/little_loops/user_messages.py:36-102`

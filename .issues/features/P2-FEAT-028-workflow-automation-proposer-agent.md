---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T12:00:00Z
---

# FEAT-028: Workflow Automation Proposer Agent

## Summary

Create `workflow-automation-proposer` agent (Step 3 of the workflow analysis pipeline) that synthesizes patterns and workflows into concrete automation proposals including slash commands, scripts, and hooks.

## Motivation

Pattern analysis (FEAT-026) and workflow detection (FEAT-027) identify what users do repeatedly, but don't propose solutions. This agent:

- Synthesizes patterns and workflows into actionable proposals
- Proposes new slash commands for repeated multi-step workflows
- Suggests scripts for complex automation
- Recommends hooks for preventive automation
- Prioritizes proposals by frequency and implementation effort

This completes the analysis pipeline by providing implementable recommendations.

## Proposed Implementation

### 1. Agent Definition: `agents/workflow-automation-proposer.md`

```yaml
---
name: workflow-automation-proposer
description: |
  Final synthesis agent that proposes concrete automation solutions based on patterns and workflows.
  Used as Step 3 of the /ll:analyze-workflows pipeline.

  <example>
  Input: step1-patterns.yaml + step2-workflows.yaml
  → Analyze high-frequency patterns
  → Match to automation types
  → Generate implementation sketches
  → Output step3-proposals.yaml
  </example>

allowed_tools:
  - Read
  - Write
  - Grep
  - Glob
model: sonnet
---
```

### 2. Proposal Types

| Type | When to Propose | Example |
|------|-----------------|---------|
| `slash_command` | Multi-step workflow with 3+ occurrences | `/ll:cleanup-refs` for reference removal |
| `script_python` | Complex logic, data processing, external APIs | Entity extraction script |
| `script_bash` | Simple file operations, tool chains | Batch rename script |
| `hook_pre_tool` | Prevent unwanted tool usage | Block `rm -rf` patterns |
| `hook_post_tool` | React to tool completions | Auto-lint after edits |
| `hook_stop` | Session end automation | Auto-commit reminders |
| `agent_enhancement` | Extend existing agent capabilities | Add entity extraction to analyzer |
| `existing_command` | User should use existing command | Suggest `/ll:commit` for commit requests |

### 3. Priority Calculation

```python
def calculate_priority(pattern: Pattern, workflows: list[Workflow]) -> str:
    """Determine proposal priority based on frequency and impact."""

    frequency = pattern.frequency
    workflow_count = len([w for w in workflows if pattern in w.patterns])
    friction_score = estimate_friction(pattern)  # Manual steps, errors, time

    score = (
        frequency * 0.4 +           # How often does this occur?
        workflow_count * 0.3 +      # How many workflows affected?
        friction_score * 0.3        # How painful is the manual process?
    )

    if score >= 8:
        return "HIGH"      # 5+ occurrences, major friction
    elif score >= 4:
        return "MEDIUM"    # 3-4 occurrences, moderate friction
    else:
        return "LOW"       # 1-2 occurrences, minor friction
```

### 4. Effort Estimation

| Effort | Criteria | Example |
|--------|----------|---------|
| `SMALL` | Single file, <100 lines, no external dependencies | Simple slash command |
| `MEDIUM` | 2-3 files, 100-300 lines, uses existing patterns | Agent + command combo |
| `LARGE` | Multiple files, >300 lines, new patterns or dependencies | Full pipeline feature |

```python
def estimate_effort(proposal_type: str, complexity: str) -> str:
    """Estimate implementation effort."""

    effort_matrix = {
        ('slash_command', 'simple'): 'SMALL',
        ('slash_command', 'multi_step'): 'MEDIUM',
        ('script_python', 'simple'): 'SMALL',
        ('script_python', 'complex'): 'MEDIUM',
        ('hook_pre_tool', 'simple'): 'SMALL',
        ('hook_post_tool', 'complex'): 'MEDIUM',
        ('agent_enhancement', 'any'): 'MEDIUM',
        ('new_agent', 'any'): 'LARGE',
    }

    return effort_matrix.get((proposal_type, complexity), 'MEDIUM')
```

### 5. Implementation Sketch Generation

For each proposal, generate an actionable implementation plan:

```python
def generate_implementation_sketch(proposal: Proposal) -> str:
    """Generate step-by-step implementation plan."""

    if proposal.type == 'slash_command':
        return f"""
## Implementation: {proposal.name}

### 1. Create command file
Location: `commands/{proposal.name.replace('/ll:', '')}.md`

### 2. Define frontmatter
```yaml
---
description: {proposal.description}
allowed_tools: {proposal.required_tools}
---
```

### 3. Write command logic
{proposal.logic_outline}

### 4. Test
- Run with sample inputs
- Verify expected behavior
"""

    elif proposal.type == 'hook_pre_tool':
        return f"""
## Implementation: {proposal.name}

### 1. Add hook to hooks.json
```json
{{
  "event": "PreToolUse",
  "matcher": {proposal.matcher},
  "action": "prompt",
  "prompt_file": "hooks/prompts/{proposal.prompt_file}"
}}
```

### 2. Create prompt file
{proposal.prompt_content}
"""
    # ... more types
```

### 6. Output Schema: `step3-proposals.yaml`

```yaml
analysis_metadata:
  patterns_file: step1-patterns.yaml
  workflows_file: step2-workflows.yaml
  analysis_timestamp: 2026-01-12T10:30:00Z
  agent: workflow-automation-proposer
  version: "1.0"

summary:
  total_proposals: 8
  by_priority:
    HIGH: 2
    MEDIUM: 4
    LOW: 2
  by_type:
    slash_command: 3
    hook_pre_tool: 2
    script_python: 1
    existing_command: 2
  estimated_total_effort: "2-3 implementation sessions"

proposals:
  - id: "prop-001"
    type: slash_command
    name: "/ll:cleanup-refs"
    description: "Automate reference cleanup workflow"
    rationale: |
      Detected 15 occurrences of reference cleanup pattern across 3 workflows.
      Users repeatedly: search for references → review list → remove each → verify.
      This 4-step workflow can be automated into a single command.
    source_patterns:
      - pattern: "remove references"
        frequency: 8
      - pattern: "clean up"
        frequency: 7
    source_workflows:
      - "wf-001: Reference Cleanup (champion-insights)"
      - "wf-003: Reference Cleanup (SOW)"
    priority: HIGH
    effort: MEDIUM
    implementation_sketch: |
      1. Accept target file/concept as argument
      2. Search for all references (Grep with entity pattern)
      3. Present list for user confirmation
      4. Remove each reference (Edit tool)
      5. Run lint check to verify
      6. Optionally commit changes
    required_tools:
      - Grep
      - Edit
      - Bash
    example_usage: |
      /ll:cleanup-refs champion-insights.md
      /ll:cleanup-refs "SOW references"

  - id: "prop-002"
    type: hook_pre_tool
    name: "test-before-commit"
    description: "Prompt to run tests before git commits"
    rationale: |
      Detected pattern: users commit → tests fail → fix → commit again.
      8 occurrences of this cycle. A PreToolUse hook can remind users
      to run tests before committing.
    source_patterns:
      - pattern: "run tests"
        frequency: 12
      - pattern: "commit"
        frequency: 50
    priority: MEDIUM
    effort: SMALL
    implementation_sketch: |
      1. Add PreToolUse hook for Bash tool
      2. Match "git commit" commands
      3. Prompt: "Have you run tests? Consider /ll:run_tests first."
      4. User can proceed or run tests
    hooks_json_entry: |
      {
        "event": "PreToolUse",
        "matcher": {"tool": "Bash", "command_pattern": "git commit"},
        "action": "prompt",
        "prompt_file": "hooks/prompts/test-before-commit.md"
      }

  - id: "prop-003"
    type: existing_command
    name: "/ll:commit"
    description: "Suggest existing commit command"
    rationale: |
      Detected 50 manual commit requests ("commit these changes", "git commit").
      The /ll:commit command already handles this with proper commit messages
      and user approval flow.
    frequency: 50
    priority: HIGH
    effort: NONE
    recommendation: |
      Inform user that /ll:commit exists and handles:
      - Automatic commit message generation
      - User approval before committing
      - Proper attribution

  - id: "prop-004"
    type: script_python
    name: "batch-entity-extractor"
    description: "Extract entities from multiple files at once"
    rationale: |
      Entity extraction is used across pattern analysis and sequence analysis.
      A standalone script could pre-process files for faster analysis.
    source_workflows:
      - "wf-002: File Organization"
    priority: LOW
    effort: MEDIUM
    implementation_sketch: |
      1. Create scripts/little_loops/entity_extractor.py
      2. Accept glob pattern for input files
      3. Extract entities using regex patterns
      4. Output JSON/YAML with entity inventory
      5. CLI: ll-entities extract "*.md"

  - id: "prop-005"
    type: hook_post_tool
    name: "auto-lint-after-edit"
    description: "Run lint check after file edits"
    rationale: |
      Detected pattern: edit → lint fails → fix → edit → lint.
      A PostToolUse hook can auto-run lint after Edit operations.
    source_patterns:
      - pattern: "fix lint"
        frequency: 6
    priority: MEDIUM
    effort: SMALL
    implementation_sketch: |
      1. Add PostToolUse hook for Edit tool
      2. Run appropriate linter based on file type
      3. Report issues inline if found

existing_command_suggestions:
  - user_pattern: "commit these changes"
    suggested_command: "/ll:commit"
    frequency: 50
  - user_pattern: "run tests"
    suggested_command: "/ll:run_tests"
    frequency: 12
  - user_pattern: "check lint"
    suggested_command: "/ll:check_code"
    frequency: 8

implementation_roadmap:
  immediate:
    - prop-003  # Existing command awareness (no implementation needed)
    - prop-002  # Test-before-commit hook (SMALL effort)
  short_term:
    - prop-001  # Cleanup-refs command (MEDIUM effort)
    - prop-005  # Auto-lint hook (SMALL effort)
  future:
    - prop-004  # Entity extractor script (MEDIUM effort)
```

### 7. Agent System Prompt

```markdown
# Workflow Automation Proposer

You are the final step in a 3-step workflow analysis pipeline. Your job is to propose concrete automation solutions.

## Input

- `step1-patterns.yaml`: Pattern analysis results
- `step2-workflows.yaml`: Workflow detection results

## Output

Write proposals to `.claude/workflow-analysis/step3-proposals.yaml`

## Analysis Process

1. **Identify high-value targets**:
   - Patterns with frequency >= 5
   - Workflows spanning multiple sessions
   - Error/retry cycles

2. **Match to automation types**:
   - Multi-step workflows → slash commands
   - Preventive needs → PreToolUse hooks
   - Post-action automation → PostToolUse hooks
   - Complex logic → Python scripts

3. **Check for existing solutions**:
   - Does /ll:* already solve this?
   - Would a simple script suffice?

4. **Generate proposals**:
   - Clear rationale with data
   - Implementation sketch
   - Priority and effort estimates

5. **Create implementation roadmap**:
   - Group by effort and priority
   - Suggest implementation order

## Important Guidelines

- Propose specific, actionable solutions
- Include frequency data to justify priority
- Don't propose what already exists (suggest existing commands instead)
- Keep implementation sketches concrete but concise
- Consider dependencies between proposals
```

## Location

| Component | Path |
|-----------|------|
| Agent | `agents/workflow-automation-proposer.md` |
| Output | `.claude/workflow-analysis/step3-proposals.yaml` |

## Current Behavior

No automation proposal system exists. Users must manually identify automation opportunities.

## Expected Behavior

```bash
# After running /ll:analyze-workflows, Step 3 produces:
$ cat .claude/workflow-analysis/step3-proposals.yaml

summary:
  total_proposals: 8
  by_priority:
    HIGH: 2
    MEDIUM: 4
    LOW: 2
  ...

proposals:
  - id: "prop-001"
    type: slash_command
    name: "/ll:cleanup-refs"
    priority: HIGH
    effort: MEDIUM
    ...
```

## Impact

- **Severity**: High - Completes the workflow analysis pipeline
- **Effort**: Medium - Requires synthesis logic and template generation
- **Risk**: Low - Read-only analysis, proposals are suggestions only

## Dependencies

None external. Uses YAML processing.

## Blocked By

- FEAT-026: Workflow Pattern Analyzer Agent (provides pattern data)
- FEAT-027: Workflow Sequence Analyzer Agent (provides workflow data)

## Blocks

- FEAT-029: `/ll:analyze-workflows` Command (orchestrates this agent)

## Labels

`feature`, `agent`, `workflow-analysis`, `automation-proposals`

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2

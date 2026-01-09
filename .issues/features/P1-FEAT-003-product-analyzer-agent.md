---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-003: Product Analyzer Agent

## Summary

Create a specialized `product-analyzer` agent that analyzes the codebase against product goals to identify:
- Feature gaps (goals without implementation)
- User experience improvements
- Business value opportunities
- Strategic alignment issues

This agent operates at the product/business level, complementing the existing technical analysis agents.

## Motivation

Current agents (`codebase-analyzer`, `codebase-pattern-finder`, etc.) focus on technical aspects:
- Code quality
- Architectural patterns
- Implementation details

None answer the question: **"Is this codebase delivering on its product goals?"**

The `product-analyzer` agent bridges this gap by:
1. Reading product goals from `ll-goals.md`
2. Mapping goals to codebase capabilities
3. Identifying where code falls short of product vision
4. Suggesting features that would advance strategic priorities

## Proposed Implementation

### 1. Agent Definition

Create `agents/product-analyzer.md`:

```markdown
---
description: |
  Analyzes codebase against product goals to identify feature gaps,
  user experience improvements, and business value opportunities.
  Requires product analysis to be enabled and ll-goals.md to exist.
tools:
  - Read
  - Grep
  - Glob
model: sonnet
trigger:
  when_to_use: |
    Use this agent via /ll:scan_product when product analysis is enabled.
    This agent is specifically for product-focused analysis, separate from
    technical scanning done by /ll:scan_codebase.

    Use cases:
    - Identify features needed to meet product goals
    - Assess user experience from code structure
    - Find opportunities for business value
    - Validate strategic alignment of implementations
  example_prompts:
    - "What features are missing to meet our product goals?"
    - "How well does the codebase serve our target users?"
    - "Identify opportunities to improve business value"
---

# Product Analyzer Agent

You are a product-focused analyst examining a codebase against defined product goals.

## Context

You have access to:
1. **Product Goals** (`.claude/ll-goals.md`): Vision, personas, metrics, priorities
2. **Codebase**: Full read access to understand current capabilities
3. **Existing Issues** (`.issues/`): To avoid duplicating known work

## Analysis Framework

### 1. Goal-Gap Analysis

For each strategic priority in the goals document:
- Identify code that supports this goal
- Identify gaps where no code exists
- Rate alignment: Strong | Partial | Weak | Missing

### 2. Persona Journey Analysis

For each defined persona:
- Trace their likely usage paths through the code
- Identify friction points (complex APIs, missing features)
- Suggest improvements from their perspective

### 3. Business Value Opportunities

Look for:
- Features competitors likely have that are missing
- Underutilized capabilities that could be promoted
- Technical capabilities without user-facing exposure
- Quick wins with high user impact

## Output Format

Return findings as structured data:

```yaml
findings:
  - type: feature_gap
    issue_type: FEAT  # Will become FEAT-XXX with product context
    title: "Missing batch processing for large codebases"
    goal_alignment: "Maximize automation"
    persona_impact: "Developer"
    business_value: High
    effort: Medium
    evidence:
      - file: "scripts/little_loops/issue_manager.py"
        observation: "Processes issues sequentially, no batch mode"
      - file: ".claude/ll-goals.md"
        observation: "Goal states 'maximize automation'"

  - type: ux_improvement
    issue_type: ENH  # Will become ENH-XXX with product context
    title: "Progress feedback during long scans"
    goal_alignment: "Improve issue accuracy"
    persona_impact: "Developer"
    user_pain: "Users don't know if scan is progressing or stuck"
    business_value: Medium
    effort: Small
    evidence:
      - file: "commands/scan_codebase.md"
        observation: "No progress indicators for multi-file scans"
```

**Note**: All findings become standard FEAT-XXX or ENH-XXX issues with product context fields populated. There is no separate PROD issue type.

## Constraints

- Only analyze if `product.enabled: true` in config
- Return empty result if `ll-goals.md` doesn't exist
- Focus on product/business aspects, not technical debt
- Each finding must tie back to a goal or persona
```

### 2. Agent Behavior Specification

The agent should:

**Read First**:
1. `.claude/ll-goals.md` - Product goals (required)
2. `.claude/ll-config.json` - Check `product.enabled`
3. `.issues/**/*.md` - Existing issues (avoid duplicates)

**Analyze**:
1. Map strategic priorities to code areas
2. Trace persona journeys through public APIs/commands
3. Compare capabilities to stated goals

**Return**:
- Structured findings with evidence
- Each finding linked to goals/personas
- Business value and effort estimates
- File:line references for evidence

### 3. Integration with Existing Agents

The `product-analyzer` complements technical agents but runs separately:

| Agent | Focus | Finds | Used By |
|-------|-------|-------|---------|
| `codebase-analyzer` | Implementation | Bugs, tech debt | `/ll:scan_codebase` |
| `codebase-pattern-finder` | Architecture | Patterns, anti-patterns | `/ll:scan_codebase` |
| `product-analyzer` | Product | Feature gaps, UX issues | `/ll:scan_product` |

**Separation of Concerns**: Technical and product scanning are kept separate. `/ll:scan_codebase` remains focused on technical issues. `/ll:scan_product` is the dedicated command for product-focused analysis.

### 4. Guardrails

Prevent misuse:
- **Requires goals**: Returns empty if no `ll-goals.md`
- **Requires opt-in**: Checks `product.enabled` before analyzing
- **No hallucination**: Every finding must cite file:line evidence
- **Deduplication**: Checks existing issues before suggesting new ones

## Location

- **New File**: `agents/product-analyzer.md`
- **Used By**: `commands/scan_product.md` (dedicated product scanning command)

## Current Behavior

No agent exists for product-level analysis. All scanning is technical.

## Expected Behavior

When product analysis is enabled:
1. Agent reads goals document
2. Analyzes codebase against goals
3. Returns structured findings with business context
4. Findings become FEAT-XXX or ENH-XXX issues with product impact fields

## Acceptance Criteria

- [ ] Agent file `agents/product-analyzer.md` created with complete prompt
- [ ] Agent returns empty result when `product.enabled: false`
- [ ] Agent returns empty result when `ll-goals.md` doesn't exist
- [ ] Agent output follows structured YAML format with required fields
- [ ] Integration test: agent produces valid findings for sample goals file
- [ ] Findings include file:line evidence references
- [ ] Deduplication check against existing issues works

## Impact

- **Severity**: High - Core capability for Product dimension
- **Effort**: Medium - New agent with complex prompt
- **Risk**: Medium - Requires careful prompt engineering to avoid hallucination

## Dependencies

- FEAT-001: Product Analysis Opt-In Configuration
- FEAT-002: Goals/Vision Ingestion Mechanism

## Blocked By

- FEAT-001
- FEAT-002

## Blocks

- FEAT-004: Product Scanning Integration
- ENH-005: Product Impact Fields in Issue Templates

## Labels

`feature`, `product-dimension`, `agent`, `analysis`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P1

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
    Use this agent when product analysis is enabled and you need to:
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

### 3. Metric Impact Analysis

For each success metric:
- Identify code that affects this metric
- Suggest changes that would move the metric toward target
- Estimate impact: High | Medium | Low

### 4. Business Value Opportunities

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
    title: "Missing batch processing for large codebases"
    goal_alignment: "Maximize automation"
    persona_impact: ["Developer Dan"]
    metric_impact:
      - metric: "Issue resolution time"
        effect: "Would reduce by ~30%"
    business_value: High
    effort: Medium
    evidence:
      - file: "scripts/little_loops/issue_manager.py"
        observation: "Processes issues sequentially, no batch mode"
      - file: ".claude/ll-goals.md"
        observation: "Goal states 'maximize automation'"

  - type: ux_improvement
    title: "Progress feedback during long scans"
    goal_alignment: "Improve issue accuracy"
    persona_impact: ["Developer Dan", "Ops Olivia"]
    user_pain: "Users don't know if scan is progressing or stuck"
    business_value: Medium
    effort: Small
    evidence:
      - file: "commands/scan_codebase.md"
        observation: "No progress indicators for multi-file scans"
```

## Constraints

- Only analyze if `product.enabled: true` in config
- Return empty result if `ll-goals.md` doesn't exist
- Focus on product/business aspects, not technical debt
- Each finding must tie back to a goal, persona, or metric
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
3. Identify metric-affecting code paths
4. Compare capabilities to stated goals

**Return**:
- Structured findings with evidence
- Each finding linked to goals/personas/metrics
- Business value and effort estimates
- File:line references for evidence

### 3. Integration with Existing Agents

The `product-analyzer` complements technical agents:

| Agent | Focus | Finds |
|-------|-------|-------|
| `codebase-analyzer` | Implementation | Bugs, tech debt |
| `codebase-pattern-finder` | Architecture | Patterns, anti-patterns |
| `product-analyzer` | Product | Feature gaps, UX issues |

During `/ll:scan_codebase` (when product enabled), all three run in parallel.

### 4. Guardrails

Prevent misuse:
- **Requires goals**: Returns empty if no `ll-goals.md`
- **Requires opt-in**: Checks `product.enabled` before analyzing
- **No hallucination**: Every finding must cite file:line evidence
- **Deduplication**: Checks existing issues before suggesting new ones

## Location

- **New File**: `agents/product-analyzer.md`
- **Integration**: `commands/scan_codebase.md` (conditional 4th agent)

## Current Behavior

No agent exists for product-level analysis. All scanning is technical.

## Expected Behavior

When product analysis is enabled:
1. Agent reads goals document
2. Analyzes codebase against goals
3. Returns structured findings with business context
4. Findings can become PROD-XXX or FEAT-XXX issues

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

## Labels

`feature`, `product-dimension`, `agent`, `analysis`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2

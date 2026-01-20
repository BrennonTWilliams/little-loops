---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-022: Product Analyzer Skill

## Summary

Create a `product-analyzer` **skill** that analyzes the codebase against product goals to identify:
- Feature gaps (goals without implementation)
- User experience improvements
- Business value opportunities
- Strategic alignment issues

This skill operates at the product/business level, complementing the existing technical analysis capabilities.

> **Note**: Originally proposed as an agent, this was revised to be a skill per project guidelines: "Prefer Skills over Agents. Skills are simpler, more composable, and can be invoked directly. Reserve Agents for complex, autonomous multi-step tasks."

## Motivation

Current agents (`codebase-analyzer`, `codebase-pattern-finder`, etc.) focus on technical aspects:
- Code quality
- Architectural patterns
- Implementation details

None answer the question: **"Is this codebase delivering on its product goals?"**

The `product-analyzer` skill bridges this gap by:
1. Reading product goals from `ll-goals.md`
2. Mapping goals to codebase capabilities
3. Identifying where code falls short of product vision
4. Suggesting features that would advance strategic priorities

**Why a Skill, not an Agent:**
- Single-purpose analysis with fixed input/output
- No autonomous multi-step decision-making needed
- No sub-agent spawning required
- Command `/ll:scan_product` orchestrates; skill provides instructions

## Proposed Implementation

### 1. Skill Definition

Create `skills/product-analyzer.md`:

```markdown
---
description: |
  Analyzes codebase against product goals to identify feature gaps,
  user experience improvements, and business value opportunities.
  Requires product analysis to be enabled and ll-goals.md to exist.

  Trigger keywords: "product analysis", "analyze product goals",
  "feature gaps", "product scan", "goal alignment"
---

# Product Analyzer Skill

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

### 2. Skill Behavior Specification

When invoked (via `/ll:scan_product` or directly), the skill should:

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

### 3. Integration with Existing Components

The `product-analyzer` skill complements technical analysis but runs separately:

| Component | Type | Focus | Finds | Used By |
|-----------|------|-------|-------|---------|
| `codebase-analyzer` | Agent | Implementation | Bugs, tech debt | `/ll:scan_codebase` |
| `codebase-pattern-finder` | Agent | Architecture | Patterns, anti-patterns | `/ll:scan_codebase` |
| `product-analyzer` | **Skill** | Product | Feature gaps, UX issues | `/ll:scan_product` |

**Separation of Concerns**: Technical and product scanning are kept separate. `/ll:scan_codebase` remains focused on technical issues. `/ll:scan_product` is the dedicated command for product-focused analysis.

**Why a Skill here but Agents for codebase analysis?**
- Codebase analyzers need autonomous exploration across many files with dynamic decisions
- Product analyzer has a fixed workflow: read goals → scan codebase → compare → output

### 4. Guardrails

Prevent misuse:
- **Requires goals**: Returns empty if no `ll-goals.md`
- **Requires opt-in**: Checks `product.enabled` before analyzing
- **No hallucination**: Every finding must cite file:line evidence
- **Deduplication**: Checks existing issues before suggesting new ones

## Location

- **New File**: `skills/product-analyzer.md`
- **Used By**: `commands/scan_product.md` (dedicated product scanning command)

## Current Behavior

No skill exists for product-level analysis. All scanning is technical.

## Expected Behavior

When product analysis is enabled:
1. Skill reads goals document
2. Analyzes codebase against goals
3. Returns structured findings with business context
4. Findings become FEAT-XXX or ENH-XXX issues with product impact fields

## Acceptance Criteria

- [ ] Skill file `skills/product-analyzer.md` created with complete prompt
- [ ] Skill returns empty result when `product.enabled: false`
- [ ] Skill returns empty result when `ll-goals.md` doesn't exist
- [ ] Skill output follows structured YAML format with required fields
- [ ] Integration test: skill produces valid findings for sample goals file
- [ ] Findings include file:line evidence references
- [ ] Deduplication check against existing issues works

## Impact

- **Severity**: High - Core capability for Product dimension
- **Effort**: Medium - New skill with detailed prompt
- **Risk**: Medium - Requires careful prompt engineering to avoid hallucination

## Dependencies

- FEAT-020: Product Analysis Opt-In Configuration
- FEAT-021: Goals/Vision Ingestion Mechanism

## Blocked By

- FEAT-020
- FEAT-021

## Blocks

- FEAT-023: Product Scanning Integration
- ENH-024: Product Impact Fields in Issue Templates

## Labels

`feature`, `product-dimension`, `skill`, `analysis`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P1

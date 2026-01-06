---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-004: Product Scanning Integration

## Summary

Integrate product-focused analysis into the `/ll:scan_codebase` command and create a dedicated `/ll:scan_product` command for product-only scanning. When product analysis is enabled, scanning should identify issues at both technical and product levels.

## Motivation

The current `/ll:scan_codebase` command spawns three parallel agents:
1. Bug Scanner
2. Enhancement Scanner
3. Feature Scanner

All three focus on technical aspects. To fully realize the Product dimension vision, we need:
1. A fourth agent (product-analyzer) during full scans
2. A dedicated command for product-only analysis
3. Product findings synthesized into appropriate issue types

## Proposed Implementation

### 1. Update `/ll:scan_codebase` Command

Modify `commands/scan_codebase.md` to conditionally include product analysis:

```markdown
### 2. Spawn Parallel Scan Agents

Launch sub-agents in parallel:

**Always spawn (3 agents)**:
- Bug Scanner (codebase-analyzer)
- Enhancement Scanner (codebase-analyzer)
- Feature Scanner (codebase-analyzer)

**Conditionally spawn (if product.enabled)**:
- Product Scanner (product-analyzer)

#### Agent 4: Product Scanner (Conditional)
```
# Only if {{config.product.enabled}} is true

Use Task tool with subagent_type="product-analyzer"

Prompt: Analyze the codebase against product goals in {{config.product.goals_file}}:

1. Goal-Gap Analysis
   - Which strategic priorities lack implementation?
   - Which features are partially implemented?

2. Persona Journey Analysis
   - What friction points exist for target users?
   - What's missing from their expected workflows?

3. Metric Impact Opportunities
   - What changes would improve success metrics?
   - Which metrics are blocked by missing features?

4. Business Value Opportunities
   - What quick wins would deliver user value?
   - What capabilities exist but aren't exposed?

Return structured findings with:
- Title (brief description)
- Goal/Persona/Metric alignment
- Business value (High/Medium/Low)
- Effort estimate (Small/Medium/Large)
- Evidence with file:line references
```
```

### 2. Create `/ll:scan_product` Command

New command `commands/scan_product.md` for product-only scanning:

```markdown
---
description: Scan codebase for product-focused issues based on goals document
---

# Scan Product

Analyze the codebase against product goals to identify feature gaps,
user experience improvements, and business value opportunities.

## Prerequisites

- Product analysis must be enabled: `product.enabled: true` in config
- Goals document must exist: `{{config.product.goals_file}}`

## Process

### 1. Validate Prerequisites

```bash
# Check product analysis is enabled
if ! jq -e '.product.enabled == true' .claude/ll-config.json; then
  echo "Product analysis not enabled. Run /ll:init --interactive to enable."
  exit 1
fi

# Check goals file exists
if [ ! -f "{{config.product.goals_file}}" ]; then
  echo "Goals file not found: {{config.product.goals_file}}"
  echo "Create this file to define your product vision and priorities."
  exit 1
fi
```

### 2. Run Product Analysis

Spawn the product-analyzer agent with full context:

```
Use Task tool with subagent_type="product-analyzer"

Prompt: Perform comprehensive product analysis:

## Goals Document
Read and internalize: {{config.product.goals_file}}

## Analysis Scope

1. **Strategic Alignment Audit**
   - Score each strategic priority: Implemented | Partial | Missing
   - Identify code supporting each priority
   - Flag priorities with no supporting code

2. **User Journey Mapping**
   - For each persona, trace their primary workflows
   - Identify friction points and missing steps
   - Suggest improvements from user perspective

3. **Success Metric Analysis**
   - Map each metric to relevant code paths
   - Identify blockers preventing metric improvement
   - Suggest changes to move metrics toward targets

4. **Opportunity Identification**
   - Quick wins (small effort, high value)
   - Missing features (gaps vs. goals)
   - Underexposed capabilities

## Output Requirements
- Structured findings with evidence
- Each finding linked to goal/persona/metric
- Business value and effort estimates
- Deduplication against existing .issues/
```

### 3. Synthesize Findings

Process agent results:

1. **Deduplicate** against existing issues in `.issues/`
2. **Classify** findings:
   - Feature gaps -> FEAT-XXX or PROD-XXX
   - UX improvements -> ENH-XXX with product context
   - Quick wins -> Appropriate type with high priority
3. **Prioritize** based on:
   - Business value (primary)
   - Effort (secondary, inverse)
   - Goal alignment (tertiary)

### 4. Create Issue Files

For each finding, create issue with product context:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_product
---

# [PREFIX]-[NUMBER]: [Title]

## Summary

[Description of the product-focused finding]

## Product Context

### Goal Alignment
- **Strategic Priority**: [Which priority this supports]
- **Alignment Score**: [Strong | Partial | Weak]

### User Impact
- **Affected Personas**: [List of personas]
- **User Pain Point**: [What problem this solves]
- **Expected Benefit**: [How users benefit]

### Business Value
- **Value Score**: [High | Medium | Low]
- **Success Metrics Impacted**:
  - [Metric 1]: [Expected effect]
  - [Metric 2]: [Expected effect]

## Evidence

[File:line references showing the gap or opportunity]

## Proposed Solution

[High-level approach]

## Impact

- **Business Value**: [High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

## Labels

`product`, `[goal-id]`, `[persona-id]`

---

## Status

**Open** | Created: [DATE] | Priority: P[X]
```

### 5. Output Report

```markdown
# Product Scan Report

## Scan Context
- **Goals Document**: {{config.product.goals_file}}
- **Last Goals Update**: [from frontmatter]
- **Personas Analyzed**: [list]
- **Priorities Analyzed**: [list]

## Strategic Alignment Summary

| Priority | Alignment | Findings |
|----------|-----------|----------|
| Maximize automation | Partial | 2 gaps identified |
| Improve accuracy | Strong | 1 opportunity found |

## Findings by Category

### Feature Gaps (N)
| Priority | Title | Business Value | Effort |
|----------|-------|----------------|--------|
| P2 | Batch processing mode | High | Medium |

### UX Improvements (N)
| Priority | Title | Personas | Effort |
|----------|-------|----------|--------|
| P3 | Progress indicators | All | Small |

### Quick Wins (N)
| Priority | Title | Value | Effort |
|----------|-------|-------|--------|
| P2 | Expose hidden capability | High | Small |

## Next Steps

1. Review findings for accuracy
2. Adjust priorities based on business context
3. Run `/ll:manage_issue` to implement high-priority items
```
```

### 3. Scan Mode Configuration

Add to config schema:

```json
{
  "scan": {
    "modes": {
      "technical": true,
      "product": false
    },
    "default_mode": "technical"
  }
}
```

Commands respect mode:
- `/ll:scan_codebase` - Both modes if product enabled
- `/ll:scan_product` - Product mode only (requires opt-in)
- `/ll:scan_codebase --technical-only` - Skip product even if enabled

## Location

- **Modified**: `commands/scan_codebase.md`
- **New File**: `commands/scan_product.md`
- **Modified**: `config-schema.json` (scan modes)

## Current Behavior

`/ll:scan_codebase` only performs technical analysis with 3 agents.

## Expected Behavior

When product analysis is enabled:
- `/ll:scan_codebase` spawns 4 agents (including product-analyzer)
- `/ll:scan_product` available for product-only scanning
- Product findings create issues with business context
- Scan reports include product alignment summary

## Impact

- **Severity**: High - User-facing entry point for Product dimension
- **Effort**: Medium - Command updates + new command
- **Risk**: Low - Conditional behavior, backwards compatible

## Dependencies

- FEAT-001: Product Analysis Opt-In Configuration
- FEAT-002: Goals/Vision Ingestion Mechanism
- FEAT-003: Product Analyzer Agent

## Blocked By

- FEAT-001
- FEAT-002
- FEAT-003

## Blocks

None

## Labels

`feature`, `product-dimension`, `command`, `scanning`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2

---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-023: Product Scanning Integration

## Summary

Create a dedicated `/ll:scan_product` command for product-focused analysis. This command is the product counterpart to `/ll:scan_codebase`, maintaining clear separation between technical and product workflows.

## Motivation

**Separation of Concerns**: Technical and product analysis serve different purposes and are used in different workflows:

| Command | Focus | Users | When to Use |
|---------|-------|-------|-------------|
| `/ll:scan_codebase` | Technical issues | All users | Regular development |
| `/ll:scan_product` | Product gaps | Product-enabled users | Strategic planning |

Keeping these separate ensures:
1. `/ll:scan_codebase` remains fast and focused for all users
2. Product analysis is opt-in and explicit
3. Users can run product scans at appropriate times (e.g., sprint planning)
4. No confusion about what each command produces

## Proposed Implementation

### 1. Create `/ll:scan_product` Command

New command `commands/scan_product.md`:

```markdown
---
description: Scan codebase for product-focused issues based on goals document
---

# Scan Product

Analyze the codebase against product goals to identify feature gaps,
user experience improvements, and business value opportunities.

This command is the product counterpart to `/ll:scan_codebase`.

## Prerequisites

- Product analysis must be enabled: `product.enabled: true` in config
- Goals document must exist: `{{config.product.goals_file}}`

## Process

### 1. Validate Prerequisites

Check product analysis is enabled:
- If `product.enabled` is false, inform user and exit
- If goals file doesn't exist, inform user and exit

### 2. Load Product Context

Read and parse the goals file:
- Extract persona definition
- Extract strategic priorities
- Load full markdown content for agent context

### 3. Run Product Analysis

Spawn the product-analyzer agent:

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
   - For the primary persona, trace their workflows
   - Identify friction points and missing steps
   - Suggest improvements from user perspective

3. **Opportunity Identification**
   - Quick wins (small effort, high value)
   - Missing features (gaps vs. goals)
   - Underexposed capabilities

## Output Requirements
- Structured findings with evidence
- Each finding linked to goal/persona
- Issue type (FEAT or ENH) for each finding
- Business value and effort estimates
- Deduplication against existing .issues/
```

### 4. Process Findings

For each finding from the agent:

1. **Deduplicate** against existing issues in `.issues/`
2. **Classify** as FEAT-XXX or ENH-XXX based on finding type
3. **Enrich** with product context fields

### 5. Create Issue Files

Create issues in appropriate directories with product context:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_product
goal_alignment: [priority-id]
persona_impact: [persona-id]
business_value: [high|medium|low]
---

# [FEAT|ENH]-[NUMBER]: [Title]

## Summary

[Description of the product-focused finding]

## Product Context

### Goal Alignment
- **Strategic Priority**: [Which priority this supports]
- **Alignment**: [How this advances the goal]

### User Impact
- **Persona**: [Primary persona affected]
- **User Need**: [What problem this solves]
- **Expected Benefit**: [How users benefit]

### Business Value
- **Value Score**: [High | Medium | Low]
- **Rationale**: [Why this value assessment]

## Evidence

[File:line references showing the gap or opportunity]

## Proposed Approach

[High-level implementation direction]

## Impact

- **Business Value**: [High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

## Labels

`product-scan`, `[goal-id]`, `[persona-id]`

---

## Status

**Open** | Created: [DATE] | Priority: P[X]
```

### 6. Output Report

Display summary after scanning:

```markdown
# Product Scan Report

## Context
- **Goals File**: {{config.product.goals_file}}
- **Persona**: [Primary persona name]
- **Priorities Analyzed**: [N]

## Strategic Alignment Summary

| Priority | Alignment | Issues Created |
|----------|-----------|----------------|
| Priority 1 | Partial | 2 |
| Priority 2 | Strong | 0 |

## Findings Summary

| Priority | Type | Title | Business Value | Effort |
|----------|------|-------|----------------|--------|
| P2 | FEAT | [Title] | High | Medium |
| P3 | ENH | [Title] | Medium | Small |

## Next Steps

1. Review created issues for accuracy
2. Adjust priorities based on business context
3. Use `/ll:manage_issue` to implement high-priority items
```
```

### 2. No Changes to `/ll:scan_codebase`

The existing `/ll:scan_codebase` command remains unchanged:
- Continues to spawn 3 technical agents (bug, enhancement, feature scanners)
- Does not include product-analyzer
- Works identically whether product is enabled or not
- Maintains its focus on technical issue discovery

### 3. Workflow Separation

Product and technical workflows remain cleanly separated:

```
Technical Workflow (all users):
  /ll:scan_codebase → BUG/FEAT/ENH issues → /ll:manage_issue

Product Workflow (product-enabled users):
  /ll:scan_product → FEAT/ENH issues with product context → /ll:manage_issue
```

Both workflows feed into the same issue management commands, but discovery is separate.

### 4. Priority Considerations

Issues created by `/ll:scan_product` use product-aware prioritization:

```markdown
## Priority Assignment

For product-scan issues, priority considers:
1. **Business Value** (primary) - High/Medium/Low
2. **Goal Alignment** (primary) - How central to strategic priorities
3. **Effort** (secondary, inverse) - Prefer quick wins
4. **Persona Impact** (secondary) - How much it helps target user

Mapping:
- High value + core goal alignment → P1-P2
- Medium value or partial alignment → P2-P3
- Low value or tangential → P3-P4
```

## Location

- **New File**: `commands/scan_product.md`
- **Unchanged**: `commands/scan_codebase.md` (no modifications)

## Current Behavior

- `/ll:scan_codebase` performs technical-only analysis with 3 agents
- No product-focused scanning capability exists

## Expected Behavior

When product analysis is enabled:
- `/ll:scan_product` available for dedicated product scanning
- Creates FEAT/ENH issues with product context fields
- Scan report shows goal alignment summary
- `/ll:scan_codebase` continues to work exactly as before

## Impact

- **Severity**: High - User-facing entry point for Product dimension
- **Effort**: Medium - New command implementation
- **Risk**: Low - Additive feature, no changes to existing commands

## Dependencies

- FEAT-020: Product Analysis Opt-In Configuration
- FEAT-021: Goals/Vision Ingestion Mechanism
- FEAT-022: Product Analyzer Agent

## Blocked By

- FEAT-020
- FEAT-021
- FEAT-022

## Blocks

None

## Labels

`feature`, `product-dimension`, `command`, `scanning`

---

## Verification Notes

**Verified: 2026-01-24**

- Blocker FEAT-020 (Product Analysis Opt-In Configuration) is now **completed**
- Remaining blockers: FEAT-021, FEAT-022
- `commands/scan_product.md` does not exist - issue description remains accurate

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2

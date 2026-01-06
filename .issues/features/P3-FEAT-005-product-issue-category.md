---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-005: Product Issue Category

## Summary

Add a new `PROD` (Product) issue category alongside the existing `BUG`, `FEAT`, and `ENH` categories. Product issues represent work driven primarily by business goals, user needs, or strategic priorities rather than technical considerations.

## Motivation

Current issue categories are technically-oriented:
- **BUG**: Something is broken
- **FEAT**: New technical capability
- **ENH**: Improve existing technical implementation

These don't capture issues that are:
- Driven by user research findings
- Required to meet a business objective
- Strategic priorities without technical origin
- Product-market fit improvements

A `PROD` category provides a home for business-driven work that exists independently of technical debt or code quality concerns.

## Proposed Implementation

### 1. Category Definition

Add to `config.issues.categories`:

```json
{
  "issues": {
    "categories": {
      "bugs": { "prefix": "BUG", "dir": "bugs", "action": "fix" },
      "features": { "prefix": "FEAT", "dir": "features", "action": "implement" },
      "enhancements": { "prefix": "ENH", "dir": "enhancements", "action": "improve" },
      "product": { "prefix": "PROD", "dir": "product", "action": "deliver" }
    }
  }
}
```

### 2. Directory Structure

When product analysis is enabled, create `.issues/product/`:

```
.issues/
├── bugs/           # BUG-XXX: Technical bugs
├── features/       # FEAT-XXX: New technical features
├── enhancements/   # ENH-XXX: Technical improvements
├── product/        # PROD-XXX: Business-driven work (new)
└── completed/      # All completed issues
```

### 3. Product Issue Template

`PROD` issues have a distinct template emphasizing business context:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: [scan_product|manual|user_research]
goal_alignment: [priority-id]
affected_personas: [persona-ids]
business_value: [high|medium|low]
---

# PROD-[NUMBER]: [Business-focused title]

## Summary

[Description of the business need or opportunity]

## Business Context

### Strategic Alignment
- **Goal**: [Which strategic priority this advances]
- **Alignment Strength**: [Strong | Partial]
- **Rationale**: [Why this supports the goal]

### User Impact
- **Primary Persona**: [Name and role]
- **User Need**: [What users need that they don't have]
- **Current Workaround**: [How users cope without this]
- **Expected Outcome**: [How users will benefit]

### Success Metrics
| Metric | Current | Expected After | Confidence |
|--------|---------|----------------|------------|
| [Metric 1] | [Value] | [Target] | [High/Medium/Low] |

## Scope

### In Scope
- [What this issue includes]

### Out of Scope
- [What this issue explicitly excludes]

### Dependencies
- [Other issues or work this depends on]

## Technical Considerations

### Affected Areas
- **Files/Modules**: [List of likely affected code]
- **Integrations**: [External systems involved]

### Technical Approach (High-Level)
[Optional: Initial thoughts on implementation]

### Open Questions
- [Technical questions to resolve during implementation]

## Acceptance Criteria

### Business Criteria
- [ ] [Measurable business outcome 1]
- [ ] [Measurable business outcome 2]

### User Criteria
- [ ] [User can accomplish X]
- [ ] [User experience meets Y standard]

### Technical Criteria
- [ ] [Tests pass]
- [ ] [No regressions in Z]

## Impact Assessment

- **Business Value**: [High/Medium/Low]
- **User Impact**: [High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]
- **Time Sensitivity**: [Urgent/Normal/Flexible]

## Labels

`product`, `[goal-id]`, `[persona-id]`, `business-value-[level]`

---

## Status

**Open** | Created: [DATE] | Priority: P[X]
```

### 4. Product Issue Lifecycle

`PROD` issues follow a modified lifecycle emphasizing business validation:

```
Discovery -> Validation -> Planning -> Implementation -> Business Verification -> Completion
                ^                                              |
                |______________________________________________|
                     (May iterate if business criteria not met)
```

**Discovery**: From `/ll:scan_product`, user research, or manual creation
**Validation**: Confirm business need still exists and priority is correct
**Planning**: Include both technical plan and success metric targets
**Implementation**: Standard development work
**Business Verification**: Check business/user criteria (not just tests)
**Completion**: Move to completed with business outcome recorded

### 5. PROD Issue in Commands

Update commands to handle `PROD` category:

**`/ll:manage_issue`**:
```markdown
## Handling PROD Issues

Product issues require additional verification:

1. **Pre-Implementation**: Validate business context still relevant
2. **Post-Implementation**: Verify business acceptance criteria
3. **Completion**: Record business outcome achieved

### Business Verification Phase

Before marking PROD issue complete:
- Review acceptance criteria
- Confirm user-facing changes meet expectations
- Document metric impact if measurable
- Note any follow-up items identified
```

**`/ll:scan_product`**:
```markdown
# Creates PROD-XXX issues for:
- Feature gaps (goals without implementation)
- User experience improvements
- Business opportunities

# Creates FEAT-XXX or ENH-XXX with product context for:
- Technical work needed to support product goals
- Improvements that happen to align with business needs
```

**`/ll:prioritize_issues`**:
```markdown
# PROD issue priority considers:
1. Goal alignment (primary)
2. Business value (primary)
3. User impact (secondary)
4. Time sensitivity (secondary)
5. Effort (inverse, tertiary)

# Different from technical priority which considers:
1. Severity (primary)
2. Risk (secondary)
3. Effort (tertiary)
```

### 6. Integration with Automation

Update `ll-auto` and `ll-parallel` to handle `PROD` category:

```bash
# Process product issues
ll-auto --category product

# Process all categories including product
ll-auto --category all

# Default (if product disabled): bugs, features, enhancements
# Default (if product enabled): bugs, features, enhancements, product
```

### 7. Category-Specific Agents

When processing `PROD` issues, include product-analyzer in deep research:

```json
{
  "workflow": {
    "deep_research": {
      "agents": {
        "default": ["codebase-locator", "codebase-analyzer", "codebase-pattern-finder"],
        "product": ["codebase-locator", "codebase-analyzer", "product-analyzer"]
      }
    }
  }
}
```

### 8. Conditional Directory Creation

In `/ll:init`, create `.issues/product/` only when product analysis is enabled:

```bash
# Standard directories (always created)
mkdir -p .issues/bugs .issues/features .issues/enhancements .issues/completed

# Product directory (only if enabled)
if [ "{{config.product.enabled}}" = "true" ]; then
  mkdir -p .issues/product
fi
```

## Location

- **Modified**: `config-schema.json` (new category)
- **Modified**: `commands/init.md` (conditional directory)
- **Modified**: `commands/manage_issue.md` (PROD handling)
- **Modified**: `commands/prioritize_issues.md` (PROD priority logic)
- **Modified**: `commands/scan_product.md` (creates PROD issues)
- **New Directory**: `.issues/product/` (when enabled)
- **Modified**: `scripts/little_loops/cli.py` (category option)
- **Modified**: `scripts/little_loops/issue_lifecycle.py` (PROD lifecycle)

## Current Behavior

Three issue categories exist: BUG, FEAT, ENH. All are technically-oriented.

## Expected Behavior

When product analysis is enabled:
- Fourth category `PROD` becomes available
- `.issues/product/` directory is created
- Product scanner creates `PROD-XXX` issues
- Automation tools handle `PROD` category
- Priority considers business value for `PROD` issues

## Impact

- **Severity**: Medium - New category alongside existing ones
- **Effort**: Medium - Updates across multiple commands
- **Risk**: Low - Additive feature, backwards compatible

## Dependencies

- FEAT-001: Product Analysis Opt-In Configuration
- FEAT-002: Goals/Vision Ingestion Mechanism
- FEAT-003: Product Analyzer Agent
- FEAT-004: Product Scanning Integration

## Blocked By

- FEAT-001
- FEAT-004 (needs scanner to create PROD issues)

## Blocks

None (final piece of Product dimension)

## Labels

`feature`, `product-dimension`, `issue-category`, `workflow`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P3

---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# ENH-005: Product Impact Fields in Issue Templates

## Summary

Enhance existing issue file templates (BUG, FEAT, ENH) to optionally include product impact fields when product analysis is enabled. This allows technical issues to carry business context without requiring a separate product-specific issue type.

## Motivation

Even technical issues (bugs, enhancements) have product implications:
- A bug might block a critical user workflow
- An enhancement might significantly improve a success metric
- A technical debt item might be blocking a strategic priority

By adding optional product impact fields to all issue templates:
1. Technical issues gain business context for prioritization
2. Stakeholders can understand "why this matters"
3. Issues can be filtered/sorted by business impact
4. The gap between technical and product perspectives narrows

## Proposed Implementation

### 1. Extended Issue Template Structure

When `product.enabled: true`, issue templates include additional section:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
# New product-related frontmatter (optional)
goal_alignment: [priority-id or null]
affected_personas: [list of persona-ids or empty]
business_value: [high|medium|low|null]
---

# [PREFIX]-[NUMBER]: [Title]

## Summary
[Technical description]

## Location
[File:line references]

## Current Behavior
[What happens now]

## Expected Behavior
[What should happen]

## Proposed Fix
[Technical approach]

## Impact

### Technical Impact
- **Severity**: [Critical/High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

### Product Impact (if product analysis enabled)
- **Goal Alignment**: [Which strategic priority this supports, or "None"]
- **Affected Personas**: [Which user types are impacted]
- **Business Value**: [High/Medium/Low/None]
- **Success Metrics**:
  - [Metric name]: [Expected effect, e.g., "Reduces resolution time by ~20%"]

## Labels
`bug|enhancement|feature`, `priority-label`, `[goal-id]`, `[persona-id]`

---

## Status
**Open** | Created: [DATE] | Priority: P[X]
```

### 2. Conditional Template Rendering

Update issue creation logic in commands to conditionally include product fields:

```markdown
# In commands/scan_codebase.md and commands/audit_architecture.md

### Create Issue File

```python
# Pseudo-logic for issue creation

product_enabled = config.get("product", {}).get("enabled", False)

issue_content = f"""
## Impact

### Technical Impact
- **Severity**: {finding.severity}
- **Effort**: {finding.effort}
- **Risk**: {finding.risk}
"""

if product_enabled:
    issue_content += f"""
### Product Impact
- **Goal Alignment**: {finding.goal_alignment or "Not assessed"}
- **Affected Personas**: {", ".join(finding.personas) or "Not assessed"}
- **Business Value**: {finding.business_value or "Not assessed"}
- **Success Metrics**: {format_metrics(finding.metric_impacts) or "None identified"}
"""
```
```

### 3. Product Impact Assessment Agent Call

When creating technical issues with product enabled, optionally assess product impact:

```markdown
# Optional: Enrich technical finding with product context

If product analysis is enabled and the issue lacks product context:

Use Task tool with subagent_type="product-analyzer"

Prompt: Assess the product impact of this technical issue:

Issue: {issue_title}
Type: {issue_type}
Location: {file_path}:{line_number}
Technical Summary: {technical_description}

Given the goals in {{config.product.goals_file}}, determine:
1. Which strategic priority (if any) this issue affects
2. Which personas are impacted by this issue
3. Business value of fixing this issue (High/Medium/Low/None)
4. Which success metrics would improve if this is fixed

Return structured assessment or "No product impact" if purely technical.
```

### 4. Backwards Compatibility

Product impact fields must be:
- **Optional**: Issues without product fields remain valid
- **Graceful**: Commands handle missing product context
- **Non-breaking**: Existing issues don't need migration

```python
# In issue_parser.py

def parse_product_impact(content: str) -> Optional[ProductImpact]:
    """Extract product impact section if present."""
    if "### Product Impact" not in content:
        return None
    # Parse product impact fields
    return ProductImpact(...)
```

### 5. Issue Filtering by Product Impact

Enable filtering issues by product criteria:

```bash
# Future: Filter issues by goal alignment
ll-auto --goal automation

# Future: Filter by business value
ll-auto --business-value high

# Future: Filter by persona impact
ll-auto --persona developer
```

### 6. Updated Commands

Commands that create issues need updates:

| Command | Change |
|---------|--------|
| `/ll:scan_codebase` | Add product impact to findings |
| `/ll:audit_architecture` | Add product context to architectural issues |
| `/ll:manage_issue` | Display product impact in issue review |
| `/ll:prioritize_issues` | Consider business value in priority |

### 7. Issue Discovery Module Update

Update `scripts/little_loops/issue_discovery.py` to handle product fields:

```python
@dataclass
class ProductImpact:
    """Product impact assessment for an issue."""
    goal_alignment: Optional[str] = None
    affected_personas: list[str] = field(default_factory=list)
    business_value: Optional[str] = None  # high|medium|low
    metric_impacts: dict[str, str] = field(default_factory=dict)


@dataclass
class DiscoveredIssue:
    """Extended to include product impact."""
    # ... existing fields ...
    product_impact: Optional[ProductImpact] = None
```

## Location

- **Modified**: `commands/scan_codebase.md`
- **Modified**: `commands/audit_architecture.md`
- **Modified**: `commands/manage_issue.md`
- **Modified**: `commands/prioritize_issues.md`
- **Modified**: `scripts/little_loops/issue_discovery.py`
- **Modified**: `scripts/little_loops/issue_parser.py`

## Current Behavior

Issue templates contain only technical impact fields:
- Severity
- Effort
- Risk

No connection to product goals, personas, or business value.

## Expected Behavior

When product analysis is enabled:
- Issue templates include Product Impact section
- Technical findings optionally enriched with product context
- Issues carry goal alignment and persona impact data
- Prioritization can consider business value

## Impact

- **Severity**: Medium - Enhances existing functionality
- **Effort**: Medium - Multiple command and module updates
- **Risk**: Low - Optional fields, backwards compatible

## Dependencies

- FEAT-001: Product Analysis Opt-In Configuration
- FEAT-002: Goals/Vision Ingestion Mechanism (for goal/persona IDs)

## Blocked By

- FEAT-001
- FEAT-002

## Blocks

None (enhances existing issue types)

## Labels

`enhancement`, `product-dimension`, `templates`, `issue-format`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2

---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# ENH-024: Product Impact Fields in Issue Templates

## Summary

Enhance existing issue file templates (BUG, FEAT, ENH) to optionally include product impact fields. These fields are populated by product workflows (`/ll:scan_product`) and provide business context without requiring a separate issue type.

## Motivation

When product analysis is enabled, issues can carry business context:
- Goal alignment - which strategic priority this supports
- Persona impact - which users are affected
- Business value - relative importance from a product perspective

By adding optional product impact fields to issue templates:
1. Product-discovered issues gain business context for prioritization
2. Stakeholders can understand "why this matters"
3. Issues can be filtered/sorted by business impact
4. Technical and product perspectives coexist in a single issue format

**Separation of Concerns**: Product impact fields are populated by product workflows (`/ll:scan_product`), not technical workflows (`/ll:scan_codebase`). This maintains clean separation while allowing both to produce compatible issue files.

## Proposed Implementation

### 1. Extended Issue Template Structure

When product analysis is enabled and issues are created by `/ll:scan_product`, include product context:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_product
# Product-related frontmatter (populated by product workflows)
goal_alignment: [priority-id or null]
persona_impact: [persona-id or null]
business_value: [high|medium|low|null]
---

# [PREFIX]-[NUMBER]: [Title]

## Summary
[Description]

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

### Product Impact (present when discovered by product workflows)
- **Goal Alignment**: [Which strategic priority this supports]
- **Persona**: [Which user type is impacted]
- **Business Value**: [High/Medium/Low]
- **User Benefit**: [How this helps the target user]

## Labels
`bug|enhancement|feature`, `priority-label`, `product-scan`

---

## Status
**Open** | Created: [DATE] | Priority: P[X]
```

### 2. Workflow-Based Population

Product impact fields are populated based on which workflow created the issue:

| Workflow | Command | Product Impact Fields |
|----------|---------|----------------------|
| Technical | `/ll:scan_codebase` | Not included |
| Technical | `/ll:audit_architecture` | Not included |
| Product | `/ll:scan_product` | Populated |
| Manual | User creates issue | Optional, user decides |

This maintains separation of concerns:
- Technical commands remain fast and focused on technical issues
- Product commands add business context to their findings
- Both produce issues in the same format for downstream compatibility

### 3. Backwards Compatibility

Product impact fields must be:
- **Optional**: Issues without product fields remain valid
- **Graceful**: All commands handle missing product context
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

### 4. Issue Filtering by Product Impact

Enable filtering issues by product criteria (future enhancement):

```bash
# Filter issues by goal alignment
ll-auto --goal automation

# Filter by business value
ll-auto --business-value high

# Filter by discovery source
ll-auto --discovered-by scan_product
```

### 5. Commands That Read Product Impact

Commands that process issues should recognize product impact when present:

| Command | Behavior |
|---------|----------|
| `/ll:manage_issue` | Display product impact in issue review if present |
| `/ll:prioritize_issues` | Consider business value for issues that have it |

Note: Commands that CREATE issues are NOT modified except for `/ll:scan_product` (covered in FEAT-004).

### 6. Issue Parser Module Update

Update `scripts/little_loops/issue_parser.py` to handle product fields:

```python
@dataclass
class ProductImpact:
    """Product impact assessment for an issue."""
    goal_alignment: Optional[str] = None
    persona_impact: Optional[str] = None
    business_value: Optional[str] = None  # high|medium|low
    user_benefit: Optional[str] = None


@dataclass
class ParsedIssue:
    """Extended to include optional product impact."""
    # ... existing fields ...
    product_impact: Optional[ProductImpact] = None
    discovered_by: Optional[str] = None  # scan_codebase|scan_product|manual
```

### 7. Frontmatter Schema

Add optional product fields to issue frontmatter schema:

```yaml
# Optional product fields (present when discovered_by: scan_product)
# Note: discovered_by field is defined in ENH-006

goal_alignment:
  type: string
  description: ID of the strategic priority this supports
  optional: true

persona_impact:
  type: string
  description: ID of the persona affected
  optional: true

business_value:
  type: string
  enum: [high, medium, low]
  description: Business value assessment
  optional: true
```

## Location

- **Modified**: `commands/manage_issue.md` (display product impact)
- **Modified**: `commands/prioritize_issues.md` (consider business value)
- **Modified**: `scripts/little_loops/issue_parser.py` (parse product fields)
- **Used By**: `commands/scan_product.md` (populates product fields)

## Current Behavior

Issue templates contain only technical impact fields:
- Severity
- Effort
- Risk

No connection to product goals, personas, or business value.

## Expected Behavior

When product analysis is enabled:
- Issues from `/ll:scan_product` include Product Impact section
- Issues from technical commands remain unchanged (no product fields)
- Parser recognizes and extracts product fields when present
- Commands that read issues display/use product context if available

## Impact

- **Severity**: Medium - Enhances issue format for product workflows
- **Effort**: Medium - Parser updates and command display changes
- **Risk**: Low - Optional fields, backwards compatible

## Dependencies

- FEAT-020: Product Analysis Opt-In Configuration
- FEAT-021: Goals/Vision Ingestion Mechanism (for goal/persona IDs)
- FEAT-022: Product Analyzer Agent (populates product fields)
- ENH-025: Universal discovered_by Field (provides base tracking field)

## Blocked By

- FEAT-020
- FEAT-021
- FEAT-022
- ENH-025

## Blocks

None (enhances existing issue types)

## Labels

`enhancement`, `product-dimension`, `templates`, `issue-format`

---

## Verification Notes

**Verified: 2026-01-24**

- Blocker FEAT-020 (Product Analysis Opt-In Configuration) is now **completed**
- Blocker ENH-025 (Universal discovered_by Field) is now **completed**
- Remaining blockers: FEAT-021, FEAT-022
- Issue description remains accurate

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2

---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-001: Product Analysis Opt-In Configuration

## Summary

Add a Product analysis dimension to little-loops that enables issue identification at the product/business level. This feature should be **disabled by default** and opted into during the `/ll:init` process, ensuring users explicitly choose to enable product-focused analysis.

## Motivation

Currently, little-loops excels at technical issue identification (bugs, code quality, architecture) but has no capability to:
- Derive features from product goals
- Assess business impact of technical decisions
- Identify user-facing improvements
- Connect code changes to product strategy

Adding an optional Product dimension transforms little-loops from a technical issue tracker into a comprehensive development workflow that aligns code with business objectives.

## Proposed Implementation

### 1. Configuration Schema Updates (`config-schema.json`)

Add new `product` section:

```json
{
  "product": {
    "type": "object",
    "description": "Product/business analysis configuration (opt-in feature)",
    "properties": {
      "enabled": {
        "type": "boolean",
        "default": false,
        "description": "Enable product-focused issue analysis"
      },
      "goals_file": {
        "type": "string",
        "default": ".claude/ll-goals.md",
        "description": "Path to product goals/vision document"
      },
      "analyze_user_impact": {
        "type": "boolean",
        "default": true,
        "description": "Include user impact assessment in issues"
      },
      "analyze_business_value": {
        "type": "boolean",
        "default": true,
        "description": "Include business value scoring in issues"
      },
      "issue_category": {
        "type": "object",
        "description": "Product issue category configuration",
        "properties": {
          "prefix": { "type": "string", "default": "PROD" },
          "dir": { "type": "string", "default": "product" },
          "action": { "type": "string", "default": "deliver" }
        }
      }
    }
  }
}
```

### 2. Update `/ll:init` Command

Add interactive prompt when `--interactive` flag is used:

```markdown
## Product Analysis (Optional)

Would you like to enable product-focused issue analysis?

This feature allows little-loops to:
- Identify issues based on product goals and user needs
- Score issues by business impact and user value
- Create product-focused issues (PROD-XXX) alongside technical issues
- Connect technical work to product strategy

**Note**: Requires creating a goals document at `.claude/ll-goals.md`

[y] Enable product analysis
[n] Skip (technical analysis only) - DEFAULT
```

For non-interactive mode (`--yes`), default to `product.enabled: false`.

### 3. Default Configuration Template

Update `templates/*.json` to include disabled product config:

```json
{
  "product": {
    "enabled": false,
    "goals_file": ".claude/ll-goals.md"
  }
}
```

### 4. Goals File Scaffolding

When product analysis is enabled during init, create starter `ll-goals.md`:

```markdown
# Product Goals

## Vision

[Describe the high-level vision for this project]

## Target Users

### Primary Persona
- **Name**: [e.g., "Developer Dan"]
- **Role**: [e.g., "Full-stack developer"]
- **Needs**: [Key needs this project addresses]
- **Pain Points**: [Problems they currently face]

### Secondary Persona
[Additional user types if applicable]

## Success Metrics

| Metric | Current | Target | Priority |
|--------|---------|--------|----------|
| [e.g., Build time] | [e.g., 45s] | [e.g., <10s] | High |

## Strategic Priorities

1. **[Priority 1]**: [Description]
2. **[Priority 2]**: [Description]
3. **[Priority 3]**: [Description]

## Out of Scope

- [What this project intentionally does NOT do]
```

## Location

- **Primary**: `commands/init.md` (init command)
- **Secondary**: `config-schema.json` (schema updates)
- **New File**: `.claude/ll-goals.md` template in `templates/`

## Impact

- **Severity**: High - Foundation for entire Product dimension
- **Effort**: Medium - Schema + init command + template changes
- **Risk**: Low - Purely additive, opt-in, no breaking changes

## Dependencies

None - this is the foundational issue for the Product dimension.

## Blocked By

None

## Blocks

- FEAT-002: Goals/Vision Ingestion Mechanism
- FEAT-003: Product Analyzer Agent
- FEAT-004: Product Scanning Integration
- ENH-005: Product Impact Fields in Issue Templates
- FEAT-005: Product Issue Category

## Labels

`feature`, `product-dimension`, `configuration`, `init`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P1

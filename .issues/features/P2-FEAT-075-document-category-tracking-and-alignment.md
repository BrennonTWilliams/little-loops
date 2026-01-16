---
discovered_commit: 91d23ad
discovered_branch: main
discovered_date: 2026-01-16T00:00:00Z
discovered_by: capture_issue
---

# FEAT-075: Document Category Tracking and Issue Alignment

## Summary

Add configurable document category tracking to `ll-config.json` with categories like `architecture` and `product`, where each category contains a list of key markdown documents. Integrate discovery into `/ll:init` wizard and create a new `/ll:align_issues` command to validate active issues against these key documents.

## Motivation

Development teams maintain important markdown documents that define architecture decisions, product requirements, coding standards, and design patterns. Currently, there's no structured way to:

1. Track which documents are authoritative for different concerns
2. Ensure issues align with documented goals, rules, and designs
3. Validate that technical work reflects documented architecture
4. Keep issues synchronized with evolving documentation

This feature provides a general-purpose document tracking system that enables issue validation against any category of key documents, ensuring consistency between what's documented and what's being worked on.

## Proposed Implementation

### 1. Configuration Schema Updates (`config-schema.json`)

Add new `documents` section:

```json
{
  "documents": {
    "type": "object",
    "description": "Key document tracking by category",
    "properties": {
      "enabled": {
        "type": "boolean",
        "default": false,
        "description": "Enable document category tracking"
      },
      "categories": {
        "type": "object",
        "description": "Document categories with file lists",
        "additionalProperties": {
          "type": "object",
          "properties": {
            "description": {
              "type": "string",
              "description": "What this category covers"
            },
            "files": {
              "type": "array",
              "items": { "type": "string" },
              "description": "Relative paths to key documents"
            }
          },
          "required": ["files"]
        },
        "default": {}
      }
    }
  }
}
```

Example configuration:

```json
{
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": [
          "docs/ARCHITECTURE.md",
          "docs/API.md",
          "docs/TROUBLESHOOTING.md"
        ]
      },
      "product": {
        "description": "Product goals, requirements, and user needs",
        "files": [
          ".claude/ll-goals.md",
          "docs/ROADMAP.md"
        ]
      }
    }
  }
}
```

### 2. Update `/ll:init` Command

Add document tracking step to the interactive wizard (after basic project settings):

**Round N: Document Tracking**

```yaml
questions:
  - question: "Would you like to track key documents by category?"
    header: "Docs"
    options:
      - label: "Use defaults (Recommended)"
        description: "Track architecture and product documents"
      - label: "Custom categories"
        description: "Define your own document categories"
      - label: "Skip"
        description: "Don't track documents"
    multiSelect: false
```

**If "Use defaults" selected:**
1. Scan codebase for `.md` files
2. Auto-detect architecture docs: files containing "architecture", "design", "api", "troubleshoot" in name/path
3. Auto-detect product docs: files containing "goal", "roadmap", "product", "vision", "requirements"
4. Present discovered files grouped by category for user confirmation

**If "Custom categories" selected:**
1. Ask user to name their categories (comma-separated)
2. For each category, scan and present relevant `.md` files
3. Allow user to confirm/modify file lists

**Discovery heuristics for auto-detection:**

| Category | Path/Name Patterns | Content Patterns |
|----------|-------------------|------------------|
| architecture | `**/architecture*.md`, `**/design*.md`, `**/api*.md`, `docs/` | "## Architecture", "System Design" |
| product | `**/goal*.md`, `**/roadmap*.md`, `**/product*.md`, `**/vision*.md` | "## Product", "User Stories" |

### 3. New Command: `/ll:align_issues`

Create `commands/align_issues.md`:

**Usage:**
```bash
/ll:align_issues <category>           # Align all active issues against category
/ll:align_issues architecture         # Check architecture alignment
/ll:align_issues product              # Check product alignment
/ll:align_issues --all                # Check all configured categories
```

**Process:**

1. Load document category configuration from `ll-config.json`
2. Read all key documents for the specified category
3. Extract goals, rules, standards, and designs from documents
4. For each active issue in `.issues/{bugs,features,enhancements}/`:
   a. Analyze issue against document content
   b. Check for:
      - **Goal alignment**: Does the issue support documented goals?
      - **Rule compliance**: Does the proposed solution follow documented standards?
      - **Design consistency**: Is the approach consistent with documented architecture?
      - **Terminology alignment**: Does the issue use correct terms from docs?
   c. Generate alignment report with:
      - Alignment score (0-100%)
      - Specific misalignments found
      - Suggested improvements
5. Output summary report and optionally update issues with alignment notes

**Output Format:**

```markdown
================================================================================
ISSUE ALIGNMENT REPORT: architecture
================================================================================

Documents analyzed:
- docs/ARCHITECTURE.md
- docs/API.md

## High Alignment (80-100%)
| Issue | Score | Notes |
|-------|-------|-------|
| FEAT-033 | 95% | Follows config-driven pattern |
| BUG-052 | 88% | Addresses documented component |

## Medium Alignment (50-79%)
| Issue | Score | Concerns |
|-------|-------|----------|
| ENH-045 | 62% | Proposes pattern not in architecture docs |

## Low Alignment (0-49%)
| Issue | Score | Action Needed |
|-------|-------|---------------|
| FEAT-071 | 35% | Review against API.md section 3.2 |

## Recommendations
1. Update FEAT-071 to align with documented API patterns
2. Consider updating docs/ARCHITECTURE.md if ENH-045 pattern is approved

================================================================================
```

### 4. Integration with Existing Commands

**`/ll:ready_issue`**: Add optional alignment check
- If documents.enabled, run alignment check against relevant categories
- Include alignment warnings in readiness report

**`/ll:scan_codebase`**: Reference key documents
- When creating issues, check if related documents exist
- Add document references to discovered issues

## Location

- **Primary**: `config-schema.json` (schema updates)
- **Primary**: `commands/init.md` (wizard updates)
- **New File**: `commands/align_issues.md` (new command)
- **Secondary**: `commands/ready_issue.md` (optional integration)
- **Secondary**: `commands/scan_codebase.md` (optional integration)

## Current Behavior

No document category tracking exists. Issues are not validated against key documents. The `/ll:init` wizard does not ask about document tracking.

## Expected Behavior

1. `ll-config.json` supports `documents.categories` configuration
2. `/ll:init` wizard asks about document tracking with smart defaults
3. `/ll:align_issues <category>` validates issues against category documents
4. Issues can be systematically checked for alignment with documented goals/rules/designs

## Acceptance Criteria

- [ ] `config-schema.json` includes `documents` section with categories support
- [ ] `/ll:init` interactive mode prompts for document tracking setup
- [ ] `/ll:init` scans codebase for `.md` files and suggests categorization
- [ ] `/ll:init` allows custom category definition
- [ ] New `/ll:align_issues` command created with full implementation
- [ ] `/ll:align_issues` generates meaningful alignment reports
- [ ] Documentation updated (README.md, COMMANDS.md, ARCHITECTURE.md)
- [ ] Example configuration added to templates

## Impact

- **Severity**: Medium - Adds valuable governance capability
- **Effort**: Medium - Config schema + init wizard + new command
- **Risk**: Low - Purely additive, opt-in feature

## Dependencies

None - standalone feature.

## Related

- **FEAT-020**: Product Analysis Opt-In Configuration (related but distinct - FEAT-020 focuses on business metrics, this focuses on document tracking)
- **FEAT-033**: Generalize Issue Type System (both extend configuration capabilities)
- **BUG-052**: Outdated command count (will need update when this lands)

## Labels

`feature`, `configuration`, `init`, `alignment`, `documentation`

---

## Status

**Open** | Created: 2026-01-16 | Priority: P2

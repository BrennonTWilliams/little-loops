# FEAT-020: Product Analysis Opt-In Configuration - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-020-product-analysis-opt-in-configuration.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The codebase currently has no product analysis configuration. The feature must be added to:
1. `config-schema.json` - Defines the JSON Schema for configuration validation
2. `commands/init.md` - The interactive initialization wizard
3. `templates/*.json` - Project type templates (9 files)
4. A new template for the goals file scaffold

### Key Discoveries
- `config-schema.json:468-499` - The `documents` section provides a similar opt-in pattern with `enabled: false` default
- `config-schema.json:419-423` - The `context_monitor` section shows another opt-in pattern
- `commands/init.md:333-347` - Round 3 shows how to add feature selection
- `commands/init.md:433-506` - Round 5 shows how to add a dedicated round for opt-in features
- Templates do NOT include opt-in features by default (those are added via interactive prompts)

## Desired End State

After implementation:
1. `config-schema.json` contains a `product` section with `enabled: false` default
2. `/ll:init --interactive` includes a product analysis opt-in prompt
3. When enabled during init, a starter `ll-goals.md` file is created at `.claude/ll-goals.md`
4. All templates include `"product": { "enabled": false }` (optional but consistent)

### How to Verify
- Run `/ll:init --interactive` and verify product analysis question appears
- Schema validates a config with `product.enabled: true`
- Goals template file is created when product analysis is enabled

## What We're NOT Doing

- **NOT** implementing the actual product analysis functionality (that's FEAT-022)
- **NOT** creating the goals ingestion mechanism (that's FEAT-021)
- **NOT** integrating with scan_codebase (that's FEAT-023)
- **NOT** adding product impact fields to issue templates (that's ENH-024)
- **NOT** updating Python `config.py` (not needed until dependent features)

## Problem Analysis

This is a foundational feature that enables the Product dimension in little-loops. The changes are purely additive and opt-in, with no breaking changes to existing functionality.

## Solution Approach

Follow existing patterns in the codebase:
1. Add `product` section to schema following `documents` pattern (opt-in with `enabled: false`)
2. Insert a new round in init.md for product analysis opt-in (before Document Tracking)
3. Create a goals template file that gets copied when enabled
4. Update templates for consistency (optional but clean)

## Implementation Phases

### Phase 1: Update config-schema.json

#### Overview
Add the `product` configuration section to the JSON Schema, following the established pattern from `documents` and `context_monitor`.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add `product` section after `documents` section (at line 500, before the closing properties brace)

```json
"product": {
  "type": "object",
  "description": "Product/business analysis configuration (opt-in feature, disabled by default)",
  "properties": {
    "enabled": {
      "type": "boolean",
      "description": "Enable product-focused issue analysis",
      "default": false
    },
    "goals_file": {
      "type": "string",
      "description": "Path to product goals/vision document",
      "default": ".claude/ll-goals.md"
    },
    "analyze_user_impact": {
      "type": "boolean",
      "description": "Include user impact assessment in issues",
      "default": true
    },
    "analyze_business_value": {
      "type": "boolean",
      "description": "Include business value scoring in issues",
      "default": true
    }
  },
  "additionalProperties": false
}
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON Schema is valid: `python -c "import json; json.load(open('config-schema.json'))"`
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] The `product` section appears in schema after `documents` section

---

### Phase 2: Update /ll:init Command

#### Overview
Add a new round (Round 4.5) to the interactive wizard for product analysis opt-in. This goes between Features (Round 3) and the existing conditional Round 4.

#### Changes Required

**File**: `commands/init.md`

**Change 1**: Update the Interactive Mode Summary table (around line 728) to include the new round

**Change 2**: Add new Round 4 (Product Analysis) after Round 3 (Features), renumbering existing Round 4 to Round 5, and subsequent rounds accordingly

Insert after Step 5c (Features Selection) around line 348:

```markdown
#### Step 5d: Product Analysis (Round 4)

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Product"
    question: "Enable product-focused issue analysis? (Optional)"
    options:
      - label: "No, skip (Recommended)"
        description: "Technical analysis only - standard issue tracking"
      - label: "Yes, enable"
        description: "Add product goals, user impact, and business value to issues"
    multiSelect: false
```

**If "Yes, enable" selected:**
1. Create `.claude/ll-goals.md` from template (see Phase 3)
2. Add to configuration:
```json
{
  "product": {
    "enabled": true,
    "goals_file": ".claude/ll-goals.md"
  }
}
```

**If "No, skip" selected:**
- Omit the `product` section entirely (disabled is the default)

**Configuration notes:**
- Only include `product` section if enabled
- `analyze_user_impact` and `analyze_business_value` default to `true` and can be omitted

**After completing Round 4, proceed to Round 5 (Advanced Settings).**
```

**Change 3**: Renumber existing Round 4 (Advanced Settings) to Round 5, and update all subsequent round numbers and references

**Change 4**: Update the summary table at line 728 to include the new round

**Change 5**: Update total rounds from "5-9" to "6-10" in the summary

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes (no syntax errors in markdown): N/A for markdown

**Manual Verification**:
- [ ] Run `/ll:init --interactive` and verify the Product Analysis question appears after Features
- [ ] Selecting "Yes, enable" creates `.claude/ll-goals.md`
- [ ] Selecting "No, skip" does not create the goals file

---

### Phase 3: Create Goals Template File

#### Overview
Create a template for the goals/vision document that gets created when product analysis is enabled.

#### Changes Required

**File**: `templates/ll-goals-template.md` (new file)

```markdown
---
# Minimal structured metadata for programmatic access
version: "1.0"

# Primary user persona (who benefits most from this project)
persona:
  id: developer
  name: "Developer"
  role: "Software developer using this project"

# Strategic priorities (ordered by importance)
priorities:
  - id: priority-1
    name: "Primary goal description"
  - id: priority-2
    name: "Secondary goal description"
---

# Product Vision

## About This Project

[One-paragraph description of what this project does and why it exists]

## Target User

**[Persona Name]** - [Role description]

**Needs**: [What they need from this project]

**Pain Points**: [Problems they currently face that this project addresses]

## Strategic Priorities

### 1. [Priority 1 Name]
[Brief description of this priority and why it matters]

### 2. [Priority 2 Name]
[Brief description of this priority and why it matters]

## Out of Scope

- [What this project intentionally does NOT do]
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f templates/ll-goals-template.md`

**Manual Verification**:
- [ ] Template has valid YAML frontmatter
- [ ] Template is human-readable and actionable

---

### Phase 4: Update Configuration Templates (Optional)

#### Overview
Add the disabled `product` section to all project templates for consistency. This is optional since schema defaults handle it, but provides explicit visibility.

#### Changes Required

**Files**: All 9 templates in `templates/`
- `python-generic.json`
- `typescript.json`
- `javascript.json`
- `go.json`
- `rust.json`
- `java-maven.json`
- `java-gradle.json`
- `dotnet.json`
- `generic.json`

**Change for each**: Add after `issues` section:

```json
"product": {
  "enabled": false
}
```

#### Success Criteria

**Automated Verification**:
- [ ] All template JSON files are valid: `for f in templates/*.json; do python -c "import json; json.load(open('$f'))"; done`

**Manual Verification**:
- [ ] Each template includes the `product` section

---

### Phase 5: Update init.md Goals File Creation Logic

#### Overview
Add the logic in init.md to copy the goals template when product analysis is enabled.

#### Changes Required

**File**: `commands/init.md`

In the new Round 4 (Product Analysis) section, add after "If 'Yes, enable' selected":

```markdown
2. Copy goals template to project:
   ```bash
   # Copy from plugin templates to project
   cp templates/ll-goals-template.md .claude/ll-goals.md
   ```

   Note: The template path is relative to the little-loops plugin directory. Claude should read the template content and write it to `.claude/ll-goals.md`.
```

Also update Step 10 (Display Completion Message) to include:
```
Created: .claude/ll-goals.md (product goals template)  # Only show if product enabled
```

And update "Next steps" to include:
```
5. Configure product goals: .claude/ll-goals.md       # Only show if product enabled
```

#### Success Criteria

**Automated Verification**:
- [ ] N/A for markdown changes

**Manual Verification**:
- [ ] Running `/ll:init --interactive` with product enabled creates `.claude/ll-goals.md`
- [ ] The created file matches the template content

---

## Testing Strategy

### Integration Tests
- Run `/ll:init --interactive` and test the full flow with product enabled
- Run `/ll:init --interactive` and test the flow with product disabled (skip)
- Verify schema validation works with product config

### Edge Cases
- Existing `ll-goals.md` file should not be overwritten without warning
- Non-interactive mode (`--yes`) should default to product disabled

## References

- Original issue: `.issues/features/P1-FEAT-020-product-analysis-opt-in-configuration.md`
- Similar pattern: `config-schema.json:468-499` (documents section)
- Similar pattern: `commands/init.md:433-506` (Round 5 Document Tracking)
- Blocked issues: FEAT-021, FEAT-022, FEAT-023, ENH-024

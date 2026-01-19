# FEAT-075: Document Category Tracking and Issue Alignment - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-075-document-category-tracking-and-alignment.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `config-schema.json:1-470` defines all configuration sections using JSON Schema draft-07
- `commands/init.md:192-451` implements a multi-round interactive wizard using AskUserQuestion
- `commands/verify_issues.md:1-156` shows the pattern for iterating over issues and producing reports
- Configuration values are referenced with `{{config.section.property}}` syntax
- The schema uses `additionalProperties` pattern for dynamic keys (like `issues.categories`)

### Existing Patterns
- Schema sections have `enabled` boolean flags with defaults (see `context_monitor.enabled`)
- Wizard groups up to 4 questions per round using AskUserQuestion
- Commands produce machine-parseable output with `================` delimiters
- Issue iteration uses `find` with `-not -path "*/completed/*"`

## Desired End State

1. `config-schema.json` supports `documents` section with categories
2. `/ll:init` wizard includes document tracking setup (new Round 5)
3. New `/ll:align_issues` command validates issues against key documents
4. Issues can be systematically checked for alignment with documented goals/rules/designs

### How to Verify
- Run JSON schema validation on config-schema.json
- Test `/ll:init --interactive` to see document tracking questions
- Run `/ll:align_issues architecture` to see alignment report

## What We're NOT Doing

- Not integrating with `/ll:ready_issue` (deferred - optional integration per issue spec)
- Not integrating with `/ll:scan_codebase` (deferred - optional integration per issue spec)
- Not updating templates/*.json with document examples (keep them minimal)
- Not creating complex content parsing - using LLM-based analysis

## Solution Approach

Follow existing patterns exactly:
1. Add `documents` schema section modeled after `context_monitor` (enabled flag + nested config)
2. Add wizard round modeled after existing rounds in init.md
3. Create new command modeled after verify_issues.md structure

## Implementation Phases

### Phase 1: Update config-schema.json

#### Overview
Add new `documents` section to the configuration schema following the established pattern.

#### Changes Required

**File**: `config-schema.json`
**Location**: After `context_monitor` section (line ~467), before closing brace

```json
    "documents": {
      "type": "object",
      "description": "Key document tracking by category for issue alignment validation",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "Enable document category tracking",
          "default": false
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
                "items": {"type": "string"},
                "description": "Relative paths to key documents"
              }
            },
            "required": ["files"]
          },
          "default": {}
        }
      },
      "additionalProperties": false
    }
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON is valid: `python -c "import json; json.load(open('config-schema.json'))"`
- [ ] Schema validates against draft-07: `npx ajv-cli validate -s http://json-schema.org/draft-07/schema# -d config-schema.json` (or manual review)

**Manual Verification**:
- [ ] New section appears in schema file
- [ ] Pattern matches existing sections (context_monitor, issues.categories)

---

### Phase 2: Update /ll:init Command

#### Overview
Add document tracking questions to the interactive wizard. This will be a new Round 5 (after current Round 4 advanced settings).

#### Changes Required

**File**: `commands/init.md`

**Change 1**: Add Round 5 section after line ~426 (after Step 5d content)

```markdown
#### Step 5e: Document Tracking (Round 5)

**First, scan for markdown documents:**
```bash
# Find markdown files that might be key documents
find . -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/.issues/*" -not -path "*/.worktrees/*" | head -30
```

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Docs"
    question: "Would you like to track key documents by category for issue alignment?"
    options:
      - label: "Use defaults (Recommended)"
        description: "Auto-detect architecture and product documents"
      - label: "Custom categories"
        description: "Define your own document categories"
      - label: "Skip"
        description: "Don't track documents"
    multiSelect: false
```

**If "Use defaults" selected:**
1. Scan codebase for .md files
2. Auto-detect architecture docs: files matching `**/architecture*.md`, `**/design*.md`, `**/api*.md`, `docs/*.md`
3. Auto-detect product docs: files matching `**/goal*.md`, `**/roadmap*.md`, `**/vision*.md`, `**/requirements*.md`
4. Present discovered files for confirmation:

```yaml
questions:
  - header: "Confirm"
    question: "Found these key documents. Include them all?"
    options:
      - label: "Yes, use all found"
        description: "[list of discovered files]"
      - label: "Select specific files"
        description: "Choose which files to include"
      - label: "Skip document tracking"
        description: "Don't configure document tracking"
    multiSelect: false
```

**If "Custom categories" selected:**
Ask for category names and files.

**Configuration from Round 5 responses:**

If document tracking is enabled, add to configuration:
```json
{
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": ["docs/ARCHITECTURE.md", "docs/API.md"]
      },
      "product": {
        "description": "Product goals and requirements",
        "files": [".claude/ll-goals.md"]
      }
    }
  }
}
```

If "Skip" selected or no documents found, omit the `documents` section entirely.
```

**Change 2**: Update summary table at line ~434 to include Round 5

From:
```markdown
| Round | Group | Questions |
|-------|-------|-----------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes |
| 3 | Features | features (multi-select: parallel, context_monitor) |
| 4 | Advanced (dynamic) | issues_path?, worktree_files?, threshold? (0-3 questions based on R2/R3 selections) |
```

To:
```markdown
| Round | Group | Questions |
|-------|-------|-----------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes |
| 3 | Features | features (multi-select: parallel, context_monitor) |
| 4 | Advanced (dynamic) | issues_path?, worktree_files?, threshold? |
| 5 | Document Tracking | docs (auto-detect or custom categories) |
```

**Change 3**: Update summary output at line ~480 to include documents section

Add after CONTEXT MONITOR section:
```markdown
  [DOCUMENTS]                             # Only show if enabled
  documents.enabled: true
  documents.categories: [category names]
```

**Change 4**: Update section 8 (Write Configuration) at line ~517 to include documents

Add:
```markdown
   - Omit `documents` section if user selected "Skip" (disabled is the default)
```

#### Success Criteria

**Automated Verification**:
- [ ] No syntax errors in markdown

**Manual Verification**:
- [ ] Round 5 section is clearly documented
- [ ] Summary table is updated
- [ ] Configuration output section includes documents

---

### Phase 3: Create /ll:align_issues Command

#### Overview
Create new command file for issue alignment validation against key documents.

#### Changes Required

**File**: `commands/align_issues.md` (NEW FILE)

```markdown
---
description: Validate active issues against key documents for goal, rule, and design alignment
arguments:
  - name: category
    description: Document category to check against (e.g., architecture, product) or --all
    required: true
  - name: flags
    description: "Optional flags: --verbose (show detailed analysis)"
    required: false
---

# Align Issues with Documents

You are tasked with validating that active issues align with key documents configured in `ll-config.json`.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Documents enabled**: `{{config.documents.enabled}}`
- **Document categories**: `{{config.documents.categories}}`
- **Issues base**: `{{config.issues.base_dir}}`

## Pre-check

Before proceeding, verify document tracking is configured:

```bash
# Check if documents section exists and is enabled in ll-config.json
# If not configured, display:
# "Document tracking is not configured. Run /ll:init --interactive to set up."
# And stop.
```

## Arguments

$ARGUMENTS

- **category** (required): Document category to align against
  - `architecture` - Check alignment with architecture/design documents
  - `product` - Check alignment with product/goals documents
  - `--all` - Check all configured categories
  - Any custom category name defined in config

- **flags** (optional): Command flags
  - `--verbose` - Include detailed alignment analysis for each issue

## Process

### 1. Parse Arguments

```bash
CATEGORY="${category}"
FLAGS="${flags:-}"
VERBOSE=false

if [[ "$FLAGS" == *"--verbose"* ]]; then VERBOSE=true; fi
```

### 2. Load Document Category

```bash
# If CATEGORY is "--all", iterate through all categories in {{config.documents.categories}}
# Otherwise, load the specific category

# For each category, get:
# - description: What this category covers
# - files: Array of document paths
```

### 3. Read Key Documents

For each document file in the category:
1. Check if file exists
2. Read the document content
3. Extract key concepts:
   - Goals and objectives
   - Rules and standards
   - Design patterns
   - Architectural decisions
   - Terminology and naming conventions

### 4. Find Active Issues

```bash
# List all open issues (not in completed/)
find {{config.issues.base_dir}} -name "*.md" -not -path "*/completed/*" | sort
```

### 5. Analyze Each Issue

For each issue file:

#### A. Read Issue Content
- Title and summary
- Proposed implementation approach
- Expected changes
- Affected components

#### B. Check Alignment Against Documents

Evaluate these alignment dimensions:

| Dimension | Question |
|-----------|----------|
| **Goal Alignment** | Does this issue support documented goals? |
| **Rule Compliance** | Does the proposed solution follow documented standards? |
| **Design Consistency** | Is the approach consistent with documented architecture? |
| **Terminology** | Does the issue use correct terms from documentation? |

#### C. Calculate Alignment Score

Score from 0-100% based on:
- Goal alignment (30%)
- Rule compliance (25%)
- Design consistency (25%)
- Terminology (20%)

#### D. Identify Concerns

For scores below 80%, identify specific misalignments:
- "Proposes pattern not documented in architecture"
- "Uses term 'X' but docs use 'Y'"
- "Feature doesn't appear in roadmap"

### 6. Output Report

```markdown
================================================================================
ISSUE ALIGNMENT REPORT: [category]
================================================================================

## Documents Analyzed
- [doc1.md] - [description from file]
- [doc2.md] - [description from file]

## Summary
- **Issues analyzed**: X
- **High alignment (80-100%)**: N
- **Medium alignment (50-79%)**: N
- **Low alignment (0-49%)**: N

## High Alignment (80-100%)

| Issue | Score | Notes |
|-------|-------|-------|
| FEAT-033 | 95% | Follows config-driven pattern from ARCHITECTURE.md |
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

1. **High Priority**: Review FEAT-071 against documented API patterns
2. **Consider**: Update docs/ARCHITECTURE.md if ENH-045 pattern is approved
3. **Terminology**: Standardize usage of "[term]" across issues

================================================================================
```

### 7. Verbose Output (if --verbose)

For each issue with score below 80%, include detailed analysis:

```markdown
### Detailed Analysis: [ISSUE-ID]

**Score Breakdown**:
- Goal alignment: X/30
- Rule compliance: X/25
- Design consistency: X/25
- Terminology: X/20

**Specific Concerns**:
1. [Detailed concern with document reference]
2. [Detailed concern with document reference]

**Suggested Improvements**:
- [Specific suggestion]
- [Specific suggestion]
```

---

## Examples

```bash
# Check architecture alignment for all active issues
/ll:align_issues architecture

# Check product/roadmap alignment
/ll:align_issues product

# Check all configured categories
/ll:align_issues --all

# Verbose output with detailed analysis
/ll:align_issues architecture --verbose
```

---

## Integration

This command works well with:
- `/ll:init --interactive` - Set up document tracking
- `/ll:verify_issues` - Verify issue accuracy before alignment check
- `/ll:ready_issue` - (Future) Include alignment check in readiness validation
- `/ll:scan_codebase` - (Future) Reference key documents when creating issues

---

## Troubleshooting

**"Document tracking is not configured"**
- Run `/ll:init --interactive` and enable document tracking
- Or manually add `documents` section to `.claude/ll-config.json`

**"Category not found"**
- Check available categories in `.claude/ll-config.json` under `documents.categories`
- Use `--all` to see all configured categories

**"Document file not found"**
- Verify file paths in config are relative to project root
- Check that documents haven't been moved or renamed
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/align_issues.md`
- [ ] YAML frontmatter is valid

**Manual Verification**:
- [ ] Command structure matches existing commands (verify_issues.md)
- [ ] Arguments section is complete
- [ ] Output format follows project conventions

---

### Phase 4: Update Documentation

#### Overview
Update README.md and COMMANDS.md to document the new feature and command.

#### Changes Required

**File**: `docs/COMMANDS.md` (if exists) or README.md

Add entry for new command:

```markdown
### /ll:align_issues

Validate active issues against key documents for alignment with goals, rules, and designs.

**Usage:**
```bash
/ll:align_issues <category>           # Check specific category
/ll:align_issues architecture         # Check architecture alignment
/ll:align_issues product              # Check product alignment
/ll:align_issues --all                # Check all categories
/ll:align_issues architecture --verbose  # Detailed analysis
```

**Prerequisites:**
- Document tracking must be configured via `/ll:init --interactive` or manual config
```

**File**: Update command count references if applicable

Search for any hardcoded command counts and update them.

#### Success Criteria

**Automated Verification**:
- [ ] No broken markdown links

**Manual Verification**:
- [ ] New command is documented
- [ ] Configuration section mentions documents option

---

## Testing Strategy

### Manual Testing
1. Run `/ll:init --interactive` and test document tracking wizard
2. Create test configuration with document categories
3. Run `/ll:align_issues architecture` and verify output format
4. Run `/ll:align_issues --all` and verify multi-category output

### Edge Cases
- No documents configured (should show helpful message)
- Document files don't exist (should handle gracefully)
- No active issues (should show empty report)
- Custom category names

## References

- Original issue: `.issues/features/P2-FEAT-075-document-category-tracking-and-alignment.md`
- Schema pattern: `config-schema.json:415-466` (context_monitor section)
- Wizard pattern: `commands/init.md:333-426` (interactive rounds)
- Command pattern: `commands/verify_issues.md:1-156` (report structure)
- Categories pattern: `config-schema.json:67-93` (issues.categories with additionalProperties)

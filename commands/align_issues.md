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

1. Check if `documents` section exists in `.claude/ll-config.json`
2. Check if `documents.enabled` is `true`

If not configured or disabled, display:
```
Document tracking is not configured or is disabled.

To enable:
1. Run /ll:init --interactive and enable document tracking
2. Or manually add to .claude/ll-config.json:

   "documents": {
     "enabled": true,
     "categories": {
       "architecture": {
         "description": "System design and technical decisions",
         "files": ["docs/ARCHITECTURE.md"]
       }
     }
   }
```

And stop execution.

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

If the specified category doesn't exist in config:
```
Category '[CATEGORY]' not found in configuration.

Available categories:
- architecture
- product
- [other configured categories]

Use --all to check against all categories.
```

### 3. Read Key Documents

For each document file in the category:

1. **Check file exists** - If file doesn't exist, note it and continue:
   ```
   Warning: Document file not found: [path]
   ```

2. **Read document content**

3. **Extract key concepts** from the document:
   - Goals and objectives (look for "## Goals", "## Objectives", purpose statements)
   - Rules and standards (look for "must", "should", "never", guidelines)
   - Design patterns (look for architectural patterns, conventions)
   - Terminology and naming conventions (key terms used consistently)

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

| Dimension | Question | Weight |
|-----------|----------|--------|
| **Goal Alignment** | Does this issue support documented goals? | 30% |
| **Rule Compliance** | Does the proposed solution follow documented standards? | 25% |
| **Design Consistency** | Is the approach consistent with documented architecture? | 25% |
| **Terminology** | Does the issue use correct terms from documentation? | 20% |

#### C. Calculate Alignment Score

Score from 0-100% based on weighted dimensions:

- **High (80-100%)**: Issue aligns well with documents
- **Medium (50-79%)**: Issue has some misalignments that should be addressed
- **Low (0-49%)**: Issue has significant misalignments requiring review

#### D. Identify Concerns

For scores below 80%, identify specific misalignments:
- "Proposes pattern not documented in architecture"
- "Uses term 'X' but docs use 'Y'"
- "Feature doesn't appear in product roadmap"
- "Violates documented coding standard"

### 6. Output Report

```markdown
================================================================================
ISSUE ALIGNMENT REPORT: [category]
================================================================================

## Documents Analyzed

| Document | Description |
|----------|-------------|
| docs/ARCHITECTURE.md | System design and technical decisions |
| docs/API.md | API patterns and conventions |

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

**Issue**: [Title]
**File**: [path to issue file]

**Score Breakdown**:
- Goal alignment: X/30
- Rule compliance: X/25
- Design consistency: X/25
- Terminology: X/20
- **Total**: XX/100

**Specific Concerns**:
1. [Concern 1]: [Detailed explanation with reference to document section]
2. [Concern 2]: [Detailed explanation with reference to document section]

**Suggested Improvements**:
- [Specific suggestion 1]
- [Specific suggestion 2]

---
```

### 8. Multi-Category Output (if --all)

When checking all categories, produce a combined report:

```markdown
================================================================================
ISSUE ALIGNMENT REPORT: All Categories
================================================================================

## Categories Analyzed

| Category | Documents | Description |
|----------|-----------|-------------|
| architecture | 2 files | System design and technical decisions |
| product | 1 file | Product goals and requirements |

## Overall Summary

| Category | High | Medium | Low |
|----------|------|--------|-----|
| architecture | 5 | 2 | 1 |
| product | 4 | 3 | 1 |

## Issues Requiring Attention

Issues with low alignment in ANY category:

| Issue | architecture | product | Primary Concern |
|-------|--------------|---------|-----------------|
| FEAT-071 | 35% | 72% | Architecture misalignment |
| ENH-089 | 85% | 42% | Not in product roadmap |

## Per-Category Details

### Architecture Alignment
[Same format as single-category report]

### Product Alignment
[Same format as single-category report]

================================================================================
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
- `/ll:manage_issue` - Process issues after reviewing alignment
- `/ll:scan_codebase` - Create new issues that reference key documents

---

## Troubleshooting

**"Document tracking is not configured"**
- Run `/ll:init --interactive` and enable document tracking in Round 5
- Or manually add `documents` section to `.claude/ll-config.json`

**"Category not found"**
- Check available categories: `cat .claude/ll-config.json | grep -A 50 '"categories"'`
- Use `--all` to see results for all configured categories

**"Document file not found"**
- Verify file paths in config are relative to project root
- Check that documents haven't been moved or renamed
- Update paths in `.claude/ll-config.json` if files moved

**Low alignment scores**
- Review the specific concerns in the report
- Either update the issue to align with documentation
- Or update documentation if the issue represents a valid new direction

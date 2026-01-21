---
description: Validate active issues against key documents for relevance and alignment
arguments:
  - name: category
    description: Document category to check against (e.g., architecture, product) or --all
    required: true
  - name: flags
    description: "Optional flags: --verbose (detailed analysis), --fix (auto-fix relevance issues)"
    required: false
---

# Align Issues with Documents

You are tasked with validating that active issues have correct document references and align with key documents configured in `ll-config.json`.

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
  - `--fix` - Auto-fix relevance issues (add missing docs, remove irrelevant ones)

## Process

### 1. Parse Arguments

```bash
CATEGORY="${category}"
FLAGS="${flags:-}"
VERBOSE=false
FIX_MODE=false

if [[ "$FLAGS" == *"--verbose"* ]]; then VERBOSE=true; fi
if [[ "$FLAGS" == *"--fix"* ]]; then FIX_MODE=true; fi
```

### 2. Load Document Categories

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

3. **Extract constraints and concepts**:
   - Goals and objectives (from "## Goals", "## Objectives" sections)
   - Rules (statements with "must", "should", "never", "always")
   - Design patterns and conventions
   - Terminology definitions

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
- Related Key Documentation section (if present)

#### B. Doc Relevance Check

For each document linked in the issue's "Related Key Documentation" section:

1. **Read the linked document**
2. **Check for meaningful connection** to the issue:
   - Does the document discuss concepts mentioned in the issue?
   - Does the issue mention components/patterns from the document?
   - Is there terminology overlap?

3. **Classify relevance:**
   - **✓ Relevant** - Clear, meaningful connection
   - **⚠ Weak** - Tangential connection only
   - **✗ Not Relevant** - No meaningful connection

4. **Generate recommendation** for non-relevant docs:
   ```
   → Recommend: Remove [document] from Related Key Documentation
   ```

#### C. Missing Documentation Check

For documents NOT currently linked to the issue:

1. **Check if document should be linked:**
   - Does the issue propose changes to components mentioned in the document?
   - Does the issue's solution approach relate to patterns in the document?

2. **If high relevance detected:**
   ```
   → Recommend: Add [document] to Related Key Documentation
   ```

#### D. Alignment Check

For each RELEVANT linked document:

1. **Extract constraints from document:**
   - Direct rules ("must use X", "never do Y")
   - Patterns ("use exponential backoff", "all errors must be logged")
   - Conventions ("naming format: X", "file structure: Y")

2. **Compare against issue proposal:**
   - Does the proposed solution follow documented rules?
   - Does it use documented patterns?
   - Are there conflicts or contradictions?

3. **Classify alignment:**
   - **✓ Aligned** - Follows documented constraints
   - **⚠ Unclear** - Can't determine alignment (proposal too vague)
   - **✗ Misaligned** - Contradicts documented constraints

4. **For misalignments, generate specific recommendation:**
   ```markdown
   Document states:
     "[exact quote from document]"

   Issue proposes:
     "[quote from issue that conflicts]"

   → Recommend: [specific action to resolve]
   ```

### 6. Apply Fixes (if --fix)

When `--fix` flag is present:

**Auto-fix relevance issues:**
- Remove documents marked as "✗ Not Relevant" from issue's Related Key Documentation
- Add documents with high relevance that are missing

**Do NOT auto-fix alignment issues** - these require human decision:
- May need to update the issue to follow docs
- OR may need to update docs if issue represents valid new direction

For each fix applied:
```bash
# Edit the issue file to update Related Key Documentation section
# Use Edit tool to replace the table content
```

### 7. Output Report

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
- **Relevance issues found**: N (Y auto-fixed)
- **Alignment issues found**: M (require review)

## Results by Issue

### [ISSUE-ID]: [Title]

**Doc Relevance Check**
✓ docs/ARCHITECTURE.md - Relevant (discusses hook lifecycle)
✗ docs/ROADMAP.md - Not relevant
  → Recommend: Remove docs/ROADMAP.md from Related Key Documentation

**Missing Documentation**
  → Recommend: Add docs/API.md to Related Key Documentation (mentions error handling patterns)

**Alignment Check**
✓ Aligned with docs/ARCHITECTURE.md

---

### [ISSUE-ID]: [Title]

**Doc Relevance Check**
✓ docs/ARCHITECTURE.md - Relevant (retry logic patterns)

**Alignment Check**
✗ Misaligned with docs/ARCHITECTURE.md Section 4.2

  Document states:
    "All retry logic must use exponential backoff with jitter"

  Issue proposes:
    "Fixed 5-second retry interval"

  → Recommend: Update Proposed Solution to use exponential backoff
    OR update docs/ARCHITECTURE.md if fixed interval is intentional

---

## Action Summary

### Relevance Fixes Needed
| Issue | Action | Document |
|-------|--------|----------|
| FEAT-045 | Remove | docs/ROADMAP.md |
| FEAT-045 | Add | docs/API.md |
| BUG-032 | Remove | docs/GOALS.md |

### Alignment Issues (Require Review)
| Issue | Document | Conflict |
|-------|----------|----------|
| ENH-089 | docs/ARCHITECTURE.md | Proposes fixed retry vs exponential backoff |
| FEAT-071 | docs/API.md | Uses REST endpoint for streaming data |

================================================================================
```

### 8. Verbose Output (if --verbose)

Include full document quotes and detailed reasoning for each check.

### 9. Multi-Category Output (if --all)

When checking all categories, produce combined report with per-category sections.

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

# Auto-fix relevance issues (add missing docs, remove irrelevant)
/ll:align_issues architecture --fix

# Combined: verbose output and auto-fix
/ll:align_issues --all --verbose --fix
```

---

## Integration

This command works well with:
- `/ll:init --interactive` - Set up document tracking
- `/ll:capture_issue` - Creates issues with doc references
- `/ll:normalize_issues` - Adds doc references to existing issues
- `/ll:verify_issues` - Verify issue accuracy before alignment check
- `/ll:manage_issue` - Process issues after reviewing alignment

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

**Relevance marked as "Not relevant" incorrectly**
- Check if document was manually linked for a reason not obvious from content
- Use `--verbose` to see detailed reasoning
- Adjust document content to make connection clearer

**Alignment marked as "Misaligned" incorrectly**
- Review the quoted constraints from the document
- The issue may need more specific language to show alignment
- Or the document may need updating to reflect new valid approaches

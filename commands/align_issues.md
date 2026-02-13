---
description: Validate active issues against key documents for relevance and alignment
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(git:*)
arguments:
  - name: category
    description: "Document category, document path (.md), or omit to check each issue's linked docs. Use --all for all categories."
    required: false
  - name: flags
    description: "Optional flags: --verbose (detailed analysis), --dry-run (report only, no auto-fixing)"
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

- **category** (optional): What to align against
  - *(omitted)* - Check each issue against its own linked Key Documents (skip issues with no linked docs)
  - `path/to/doc.md` - Check all issues against a specific document file (detected by `.md` extension or `/` in argument)
  - `architecture` - Check alignment with architecture/design documents
  - `product` - Check alignment with product/goals documents
  - `--all` - Check all configured categories
  - Any custom category name defined in config

- **flags** (optional): Command flags
  - `--verbose` - Include detailed alignment analysis for each issue
  - `--dry-run` - Report-only mode; show what would be fixed without making changes

## Process

### 1. Parse Arguments

```bash
CATEGORY="${category:-}"
FLAGS="${flags:-}"
VERBOSE=false
DRY_RUN=false

if [[ "$FLAGS" == *"--verbose"* ]]; then VERBOSE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi

# Determine mode based on argument
if [[ -z "$CATEGORY" ]]; then
  MODE="linked-docs"       # No argument: check each issue against its own linked docs
elif [[ "$CATEGORY" == *.md || "$CATEGORY" == */* ]]; then
  MODE="specific-doc"      # Document path: check all issues against this document
elif [[ "$CATEGORY" == "--all" ]]; then
  MODE="all-categories"    # Existing behavior: all configured categories
else
  MODE="category"          # Existing behavior: specific category name
fi
```

### 2. Load Documents (mode-dependent)

**If MODE is "linked-docs":**
- Skip category loading entirely. Documents will be resolved per-issue from each issue's "Related Key Documentation" section in Step 5.

**If MODE is "specific-doc":**
- Verify the specified document file exists at the given path (relative to project root).
- If the file does not exist, display an error and stop:
  ```
  Document file not found: [CATEGORY]
  ```
- Read the document content and extract constraints/concepts (same as Step 3).

**If MODE is "category" or "all-categories":**

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

**Mode-specific behavior:**

**If MODE is "linked-docs":**
For each issue file, read its "Related Key Documentation" section. If the issue has no linked documents (section is missing, empty, or contains only placeholder text like `_No documents linked`), report:
```
Skipped [ISSUE-ID]: No linked documents — run /ll:normalize_issues first
```
For issues WITH linked documents, read each linked document and perform only the **Alignment Check (Step 5D)** against those documents. Skip the Relevance Check (5B) and Missing Documentation Check (5C) — we are only validating alignment of already-linked docs.

**If MODE is "specific-doc":**
For each issue file, perform only the **Alignment Check (Step 5D)** using the single specified document. Skip the Relevance Check (5B) and Missing Documentation Check (5C) — the user explicitly chose this document for all issues.

**If MODE is "category" or "all-categories":**
Use the full existing analysis flow below (Steps 5A through 5D).

---

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

### 6. Apply Fixes (unless --dry-run)

By default, auto-fix both relevance and alignment issues. Skip all fixes if `--dry-run` flag is present.

#### 6a. Auto-fix Relevance Issues

- **Remove** documents marked as "✗ Not Relevant" from issue's Related Key Documentation
- **Add** documents with high relevance that are missing

#### 6b. Auto-fix Alignment Issues

For issues marked as "✗ Misaligned":

1. **Determine if auto-fixable** - An alignment issue is auto-fixable when:
   - The document constraint is clear and specific
   - The issue's Proposed Solution explicitly contradicts it
   - There is one obvious way to align

2. **For auto-fixable issues:**
   - Locate the "Proposed Solution" or "Proposed Implementation" section
   - Update the conflicting text to align with the document constraint
   - Add a note explaining the alignment correction:

   ```markdown
   > **Auto-aligned**: Updated to follow [document] constraint:
   > "[constraint quote]"
   ```

3. **For non-auto-fixable issues** (ambiguous, multiple options, or intentional new direction):
   - Mark as "REQUIRES REVIEW" in the report
   - Do NOT auto-fix
   - List resolution options for human decision

#### 6c. Apply Edits

For each fix:
```bash
# Use Edit tool to update the issue file
# Track change for report output
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
- **Relevance issues**: N found (Y auto-fixed, Z skipped)
- **Alignment issues**: M found (K auto-fixed, L require review)
- **Mode**: [Auto-fix applied | Dry-run - no changes made]

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

### Relevance Fixes Applied
| Issue | Action | Document |
|-------|--------|----------|
| FEAT-045 | Removed | docs/ROADMAP.md |
| FEAT-045 | Added | docs/API.md |
| BUG-032 | Removed | docs/GOALS.md |

### Alignment Fixes Applied
| Issue | Document | Original | Fixed To |
|-------|----------|----------|----------|
| ENH-089 | docs/ARCHITECTURE.md | "Fixed retry interval" | "Exponential backoff" |

### Issues Requiring Review
| Issue | Document | Reason |
|-------|----------|--------|
| FEAT-071 | docs/API.md | Multiple resolution options |

================================================================================
```

### 8. Verbose Output (if --verbose)

Include full document quotes and detailed reasoning for each check.

### 9. Multi-Category Output (if --all)

When checking all categories, produce combined report with per-category sections.

---

## Examples

```bash
# Check each issue against its own linked documents (no argument)
/ll:align_issues

# Check all issues against a specific document
/ll:align_issues docs/ARCHITECTURE.md

# Check and auto-fix alignment by category
/ll:align_issues architecture

# Check product/roadmap alignment with auto-fix
/ll:align_issues product

# Check all configured categories with auto-fix
/ll:align_issues --all

# Verbose output with detailed analysis and auto-fix
/ll:align_issues architecture --verbose

# Dry-run: report only, no changes
/ll:align_issues architecture --dry-run

# Verbose dry-run for detailed analysis without changes
/ll:align_issues --all --verbose --dry-run
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

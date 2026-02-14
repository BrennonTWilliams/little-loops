# ENH-100: Improve Key Documents Alignment Workflow - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-100-improve-key-documents-alignment-workflow.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The key documents alignment feature (FEAT-075) exists but has usability issues:
- Issues have no explicit link to relevant documentation
- `/ll:align-issues` produces subjective 0-100% scores that are hard to action
- No integration with `/ll:capture-issue` or `/ll:normalize-issues`

### Key Discoveries
- `commands/capture_issue.md:338-419` - Issue templates have no "Related Key Documentation" section
- `commands/capture_issue.md:300-424` - Phase 4 ends at line 424; Phase 4b should be added after line 424
- `commands/normalize_issues.md:240-247` - Step 7 ends at line 247; Section 7b should be added after line 247
- `commands/align_issues.md:144-159` - Current subjective scoring system at lines 144-159
- `config-schema.json:468-499` - Documents config schema exists but little-loops doesn't use it
- `.claude/ll-config.json` - Missing `documents` section entirely (not dogfooded)
- Pattern for section insertion found at `commands/capture_issue.md:426-444` (cat >> with heredoc)
- Pattern for config check found at `commands/align_issues.md:25-49`

## Desired End State

1. Issue templates include a "Related Key Documentation" section
2. `/ll:capture-issue` suggests and links relevant docs at issue creation time (when `documents.enabled`)
3. `/ll:normalize-issues` adds missing doc references during normalization (when `documents.enabled`)
4. `/ll:align-issues` performs concrete relevance and alignment checks with actionable recommendations (no scores)
5. `/ll:align-issues --fix` auto-fixes relevance issues
6. little-loops dogfoods the `documents` config

### How to Verify
- Create a test issue and verify "Related Key Documentation" section is present
- Run `/ll:align-issues` and verify output shows relevance checks (✓/⚠/✗) not percentage scores
- Run `/ll:align-issues --fix` and verify it updates doc references

## What We're NOT Doing

- Not changing the `documents` config schema - it already works
- Not modifying `/ll:init` - Round 5 already handles document setup
- Not adding new Python code - this is all command/skill updates
- Not changing `/ll:ready-issue` or `/ll:verify-issues` - they don't need doc awareness

## Solution Approach

1. Update issue templates in `capture_issue.md` to include "Related Key Documentation" section
2. Add Phase 4b to `capture_issue.md` for document linking
3. Add Section 7b to `normalize_issues.md` for document linking
4. Completely rewrite `align_issues.md` with new relevance/alignment check system
5. Update skill to mention document linking
6. Add `documents` config to `.claude/ll-config.json` for dogfooding

## Implementation Phases

### Phase 1: Update Issue Templates

#### Overview
Add "Related Key Documentation" section to both minimal and full templates in `capture_issue.md`.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**:
1. Add section to minimal template (after line 363, before `---`)
2. Add section to full template (after line 411, before `## Labels`)

**Minimal Template (insert before line 361):**
```markdown
## Related Key Documentation

_No documents linked. Run `/ll:align-issues` to discover relevant docs._
```

**Full Template (insert before line 409):**
```markdown
## Related Key Documentation

_No documents linked. Run `/ll:align-issues` to discover relevant docs._
```

#### Success Criteria

**Automated Verification**:
- [ ] Grep for "Related Key Documentation" in capture_issue.md returns 2 matches

---

### Phase 2: Add Phase 4b to capture_issue.md

#### Overview
Add document linking after issue creation when `documents.enabled` is true.

#### Changes Required

**File**: `commands/capture_issue.md`
**Location**: After line 424 (after `git add` for new issue), before line 426 (Action: Update Existing Issue)

**Insert new section:**
```markdown

### Phase 4b: Link Relevant Documents (if documents.enabled)

**Skip this phase if**:
- `documents.enabled` is not `true` in `.claude/ll-config.json`
- OR no documents are configured in `documents.categories`

**Process:**

1. **Load configured documents:**
   ```bash
   # Read document categories from config
   # For each category in {{config.documents.categories}}:
   #   - Get the files array
   #   - Read each document file
   ```

2. **Extract key concepts from each document:**
   - Headers and section titles
   - Key terms (nouns, technical terms)
   - File paths mentioned

3. **Score relevance against issue content:**
   - Match issue summary, context, and proposed solution against document concepts
   - Use simple keyword overlap (similar to duplicate detection at line 153-158)
   - Score > 0.3 = relevant

4. **Select top matches (max 3 documents):**
   - Rank by relevance score
   - Take top 3 unique documents across all categories

5. **Update issue file:**

   Replace the placeholder "Related Key Documentation" section:

   ```markdown
   ## Related Key Documentation

   | Category | Document | Relevance |
   |----------|----------|-----------|
   | [category] | [document path] | [brief reason] |
   | [category] | [document path] | [brief reason] |
   ```

   Example:
   ```markdown
   ## Related Key Documentation

   | Category | Document | Relevance |
   |----------|----------|-----------|
   | architecture | docs/ARCHITECTURE.md | Mentions hook lifecycle |
   | product | .claude/ll-goals.md | Workflow automation goal |
   ```

6. **Note in output:**
   Add to Phase 5 report (line 497-510) a new field:
   ```markdown
   - **Linked Docs**: [count] documents linked
   ```

```

#### Success Criteria

**Automated Verification**:
- [ ] Grep for "Phase 4b" in capture_issue.md returns 1 match
- [ ] Grep for "documents.enabled" in capture_issue.md returns at least 1 match

---

### Phase 3: Add Section 7b to normalize_issues.md

#### Overview
Add document linking for issues missing the section during normalization.

#### Changes Required

**File**: `commands/normalize_issues.md`
**Location**: After line 247 (end of Step 7), before line 249 (Step 8: Output Report)

**Insert new section:**
```markdown

### 7b. Add Missing Document References (if documents.enabled)

**Skip this section if**:
- `documents.enabled` is not `true` in `.claude/ll-config.json`
- OR no documents are configured

**Process:**

For each issue file:

1. **Check if "Related Key Documentation" section exists:**
   ```bash
   grep -q "## Related Key Documentation" "$issue_file"
   ```

2. **If section is missing OR contains only placeholder text:**

   Placeholder text patterns:
   - `_No documents linked`
   - `_No relevant documents identified`

3. **Link relevant documents:**
   - Load documents from `{{config.documents.categories}}`
   - Read each document and extract key concepts
   - Match against issue content
   - Select top 3 matches

4. **Add or update section:**

   If section is missing, append to file before `## Labels` or `---` footer:
   ```bash
   # Find insertion point (before ## Labels or final ---)
   # Insert the Related Key Documentation section
   ```

   If section exists with placeholder, replace the placeholder line:
   ```bash
   # Replace "_No documents linked..." with the table
   ```

5. **Track in report:**
   Add to Step 8 output (line 252-292):
   ```markdown
   ## Document References Added

   | Issue | Documents Linked |
   |-------|------------------|
   | BUG-071 | docs/ARCHITECTURE.md, docs/API.md |
   | ENH-045 | .claude/ll-goals.md |
   ```

```

#### Success Criteria

**Automated Verification**:
- [ ] Grep for "7b" in normalize_issues.md returns at least 1 match
- [ ] Grep for "documents.enabled" in normalize_issues.md returns at least 1 match

---

### Phase 4: Rewrite align_issues.md

#### Overview
Complete rewrite to replace subjective scoring with concrete relevance/alignment checks.

#### Changes Required

**File**: `commands/align_issues.md`
**Changes**: Replace lines 51-329 (everything after Pre-check through end) with new implementation

**New content (starting after line 50):**

````markdown

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
/ll:align-issues architecture

# Check product/roadmap alignment
/ll:align-issues product

# Check all configured categories
/ll:align-issues --all

# Verbose output with detailed analysis
/ll:align-issues architecture --verbose

# Auto-fix relevance issues (add missing docs, remove irrelevant)
/ll:align-issues architecture --fix

# Combined: verbose output and auto-fix
/ll:align-issues --all --verbose --fix
```

---

## Integration

This command works well with:
- `/ll:init --interactive` - Set up document tracking
- `/ll:capture-issue` - Creates issues with doc references
- `/ll:normalize-issues` - Adds doc references to existing issues
- `/ll:verify-issues` - Verify issue accuracy before alignment check
- `/ll:manage-issue` - Process issues after reviewing alignment

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
````

#### Success Criteria

**Automated Verification**:
- [ ] Grep for "--fix" in align_issues.md returns at least 2 matches
- [ ] Grep for "Doc Relevance Check" in align_issues.md returns at least 1 match
- [ ] Grep for "Alignment Check" in align_issues.md returns at least 1 match
- [ ] Grep for "✓ Relevant" in align_issues.md returns at least 1 match
- [ ] Grep for "0-100%" in align_issues.md returns 0 matches (scores removed)

---

### Phase 5: Update Skill and Dogfood Config

#### Overview
Update capture-issue skill to mention document linking and add documents config to little-loops.

#### Changes Required

**File 1**: `skills/capture-issue/SKILL.md`
**Location**: After line 61, before final closing

**Insert:**
```markdown

## Document Linking

When `documents.enabled` is true in the project config, captured issues will automatically:
- Link relevant documents from configured categories
- Show linked docs in the capture report

To enable document linking:
1. Run `/ll:init --interactive` and enable document tracking
2. Or add `documents` section to `.claude/ll-config.json`
```

**File 2**: `.claude/ll-config.json`
**Changes**: Add `documents` section after `context_monitor` block

**Insert (before final `}`):**
```json
,
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": ["docs/ARCHITECTURE.md", "docs/API.md"]
      },
      "guidelines": {
        "description": "Development guidelines and conventions",
        "files": [".claude/CLAUDE.md", "CONTRIBUTING.md"]
      }
    }
  }
```

#### Success Criteria

**Automated Verification**:
- [ ] Grep for "Document Linking" in SKILL.md returns 1 match
- [ ] Grep for "documents.enabled" in SKILL.md returns 1 match
- [ ] JSON parse of ll-config.json succeeds
- [ ] Grep for '"documents"' in ll-config.json returns 1 match
- [ ] Grep for '"enabled": true' in ll-config.json returns 1 match (in documents section)

---

## Testing Strategy

### Manual Verification

1. **Create test issue and verify template:**
   ```bash
   /ll:capture-issue "Test issue for document linking"
   cat .issues/*/P*-*-test-issue*.md
   # Verify "Related Key Documentation" section exists
   ```

2. **Test align_issues new format:**
   ```bash
   /ll:align-issues architecture
   # Verify output shows ✓/⚠/✗ checks, not percentage scores
   ```

3. **Test --fix flag:**
   ```bash
   /ll:align-issues architecture --fix
   # Verify it updates issue files
   ```

### Automated Verification (All Phases)
```bash
# Run lint
ruff check scripts/

# Run type check
python -m mypy scripts/little_loops/

# Run tests
python -m pytest scripts/tests/
```

## References

- Original issue: `.issues/enhancements/P2-ENH-100-improve-key-documents-alignment-workflow.md`
- Pattern for section insertion: `commands/capture_issue.md:426-444`
- Pattern for config check: `commands/align_issues.md:25-49`
- Documents config schema: `config-schema.json:468-499`
- Completed FEAT-075: `.issues/completed/P2-FEAT-075-document-category-tracking-and-alignment.md`

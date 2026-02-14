# Format Issue Templates

This file contains the template v2.0 section definitions, alignment mappings, and output format templates for the format-issue skill.

## Template v2.0 Section Alignment

Read `templates/issue-sections.json` (relative to the little-loops plugin directory) and apply v1.0 → v2.0 section renaming.

### Known v1.0 → v2.0 Mappings

| Old Section (v1.0) | New Section (v2.0) | Issue Type |
|-------------------|-------------------|------------|
| `Reproduction Steps` | `Steps to Reproduce` | BUG |
| `Proposed Fix` | `Proposed Solution` | BUG |
| `User Story` | `Use Case` | FEAT |
| `Current Pain Point` | `Motivation` | ENH |

### Rename Logic

1. Scan the issue content for deprecated section headers
2. For each old section found:
   - Use Edit tool to replace the section header
   - Preserve all content under the section
   - Track rename for report output

### Example Rename

**Before:**
```markdown
## Reproduction Steps

1. Click the button
2. See error
```

**After:**
```markdown
## Steps to Reproduce

1. Click the button
2. See error
```

### Skip in Interactive Mode

In interactive mode (no --auto), skip automatic renaming and let user decide.

## Section Definitions

### Template v2.0 Structure

Analyze content against type-specific checklists defined in `templates/issue-sections.json` v2.0:

1. Read the shared template file `templates/issue-sections.json` (v2.0 - optimized for AI implementation)
2. For the issue's type (BUG/FEAT/ENH), look up `type_sections.[TYPE]` for type-specific sections
3. Also check `common_sections` for universal required sections (Summary, Current Behavior, Expected Behavior, Motivation, etc.)
4. For each section, use its `level` (required/conditional/nice-to-have) and `question` field
5. **Note**: Sections marked `deprecated: true` are still supported for backward compatibility but should not be suggested for new content

### New Sections in v2.0

Consider these new sections:
- **Motivation** (common): Why this matters - replaces "Current Pain Point" for ENH
- **Implementation Steps** (common): High-level outline for agent guidance (3-8 phases)
- **Root Cause** (BUG): File + function anchor + explanation
- **API/Interface** (FEAT/ENH): Public contract changes
- **Use Case** (FEAT): Concrete scenario (renamed from "User Story")

### Gap Presentation Format

Present gaps as a table:

| Section | Required? | Question if Missing |
|---------|-----------|---------------------|
| [section name from template] | [level from template] | [question from template] |

## Section Inference Templates (Auto Mode)

### Inference Rules

| Section | Inference Strategy | Issue Type |
|---------|-------------------|------------|
| **Motivation** | Extract from Summary: Look for "why this matters" language; add quantified impact placeholder | ENH, common |
| **Implementation Steps** | Parse Proposed Solution into 3-8 high-level phases; if no Proposed Solution, add generic steps | common |
| **Root Cause** | Extract from Location section if present; otherwise add placeholder with file/anchor fields | BUG |
| **API/Interface** | Scan Proposed Solution for function/class signatures; if none found, add "N/A - no public API changes" | FEAT/ENH |
| **Integration Map** | Scan issue for file paths mentioned in Location, Proposed Solution, or Context; populate Files to Modify; use placeholders for other sub-sections | common |

### Template: Motivation

```markdown
## Motivation

This [enhancement|issue] would:
- [Extract from Summary]: [What the issue aims to improve]
- Business value: [Enable X capability / Improve Y experience]
- Technical debt: [Reduce maintenance cost / Improve code clarity]

[Additional context from Summary or Context sections]
```

### Template: Implementation Steps

```markdown
## Implementation Steps

1. [Phase 1 from Proposed Solution - e.g., "Read and analyze current implementation"]
2. [Phase 2 from Proposed Solution - e.g., "Implement the proposed changes"]
3. [Phase 3 from Proposed Solution - e.g., "Add tests for new behavior"]
4. [Verification approach - e.g., "Run tests and verify fix resolves issue"]
```

### Template: Root Cause (BUG only)

```markdown
## Root Cause

- **File**: [Extract from Location section or 'TBD - requires investigation']
- **Anchor**: [Extract from Location or 'in function TBD()']
- **Cause**: [Extract from issue description or 'Requires investigation to determine why bug occurs']
```

### Template: API/Interface (FEAT/ENH)

```markdown
## API/Interface

N/A - No public API changes

[OR if signatures found in Proposed Solution]

```python
[Extracted function/class signatures from Proposed Solution]
```
```

### Template: Integration Map

```markdown
## Integration Map

### Files to Modify
- [Extract file paths from Location, Proposed Solution, Context sections]
- [Additional files from scanning issue content for path patterns like `path/to/file.py`]

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "affected_function_or_class" src/`

### Similar Patterns
- TBD - search for consistency: `grep -r "similar_pattern" src/`

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A [or list config files if mentioned in issue]
```

### Preservation Rule

**Do NOT overwrite non-empty sections**: If a section already exists and has content beyond just "TBD" or placeholder text, preserve it and do not apply inference.

**Detection**: Skip inference if section content has > 2 lines of meaningful text (not counting the header).

**Examples of content to preserve**:
- Any section with specific details, code examples, or numbered lists
- Any section that references specific files or functions
- Any section with concrete acceptance criteria

**Examples of content to replace with inference**:
- Empty section with just header
- Section containing only "TBD" or "to be determined"
- Section containing only placeholder text like "add details here"

## Issue File Templates

### BUG Template Example (v2.0)

```markdown
## Root Cause

- **File**: `path/to/buggy_file.py`
- **Anchor**: `in function problematic_func()`
- **Cause**: [Explanation of why the bug occurs - logic error, race condition, etc.]

## Proposed Solution

Fix in `buggy_file.py`, function `problematic_func()`:

```python
# Current (buggy) code shown for context
# Proposed fix with code example
```

## Implementation Steps

1. Fix root cause in identified function
2. Add regression test
3. Verify fix resolves issue
```

### FEAT Template Example (v2.0)

```markdown
## Use Case

**Who**: [Specific user role/persona]

**Context**: [When/where they need this]

**Goal**: [What they want to achieve]

**Outcome**: [Expected result]

## Acceptance Criteria

- [ ] [Testable criterion 1]
- [ ] [Testable criterion 2]
- [ ] [Testable criterion 3]

## API/Interface

```python
def new_function(arg: Type) -> ReturnType:
    """Function signature for new feature."""
```

## Implementation Steps

1. [High-level phase 1]
2. [High-level phase 2]
3. [Verification approach]
```

### ENH Template Example (v2.0)

```markdown
## Motivation

This enhancement would:
- [Quantified impact 1]: affects X users, saves Y minutes
- [Business value]: enables Z capability
- [Technical debt]: reduces maintenance cost by %

## Success Metrics

- [Metric 1]: [Current value] → [Target value]
- [Metric 2]: [Measurable before/after comparison]

## Scope Boundaries

- **In scope**: [Specific inclusions]
- **Out of scope**: [Specific exclusions with reasons]

## Implementation Steps

1. [High-level phase 1]
2. [High-level phase 2]
3. [Verification approach]
```

## Output Format Templates

### Interactive Mode Output (without --auto)

```
================================================================================
ISSUE FORMATTED: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]

## GAPS IDENTIFIED
- [Section 1]: [missing|vague|incomplete]
- [Section 2]: [missing|vague|incomplete]

## QUALITY ISSUES
- [Section 3]: [QUALITY] Vague language — "improve performance" lacks metric/target
- [Section 4]: [SPECIFICITY] Steps to Reproduce are generic — lacks concrete steps
- [Section 5]: [CONTRADICTION] Expected behavior conflicts with proposed solution

## CHANGES MADE
- [Section 1]: Added [description of content]
- [Section 3]: Clarified [specific improvement made]

## SKIPPED
- [Section 2]: User chose not to address
- [Section 5]: User chose not to address

## FILE STATUS
- [Staged|Not staged]

## NEXT STEPS
- Run `/ll:ready-issue [ID]` to validate
- Run `/ll:commit` to commit changes
================================================================================
```

### Auto Mode Output (--auto)

```
================================================================================
AUTO-FORMAT: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]
- Mode: Auto-format [--dry-run | --all]

## CHANGES APPLIED

### Section Renames (v1.0 → v2.0)
- `Reproduction Steps` → `Steps to Reproduce`
- `User Story` → `Use Case`
- [Additional renames]

### Sections Added (Inferred)
- **Motivation**: Inferred from Summary - [brief description]
- **Integration Map**: Files to Modify populated from issue content
- **Implementation Steps**: 3 phases extracted from Proposed Solution

### Sections Preserved
- **Proposed Solution**: Existing content preserved (non-empty)
- **Acceptance Criteria**: Existing content preserved
- [Additional preserved sections]

## DRY RUN PREVIEW [--dry-run only]
[Show exact changes that would be applied without applying them]
- Would rename: `## Reproduction Steps` → `## Steps to Reproduce`
- Would add: `## Motivation` section with inferred content
- Would add: `## Integration Map` section with placeholder

## FILE STATUS
- [Modified | Not modified (--dry-run)]
- [Staged | Not staged]

## NEXT STEPS
- Run `/ll:ready-issue [ID]` to validate
- Run `/ll:commit` to commit changes
================================================================================
```

### Batch Mode Output (--all --auto)

```
================================================================================
AUTO-FORMAT BATCH REPORT: --all mode
================================================================================

## SUMMARY
- Issues processed: 15
- Issues formatted: 12
- Issues skipped: 3 (already v2.0 compliant)
- Total section renames: 8
- Total sections added: 24

## RESULTS BY ISSUE

### BUG-071: Error in login flow
- Sections renamed: Reproduction Steps → Steps to Reproduce, Proposed Fix → Proposed Solution
- Sections added: Root Cause (from Location), Integration Map
- Status: Success

### FEAT-042: Add dark mode
- Sections renamed: User Story → Use Case
- Sections added: API/Interface (N/A), Implementation Steps (3 phases)
- Status: Success

### ENH-089: Improve performance
- Sections renamed: (none)
- Sections added: Motivation (from Summary), Success Metrics
- Status: Success

### BUG-123: Memory leak
- No changes needed (already v2.0 compliant)
- Status: No changes

## FILES MODIFIED
- .issues/bugs/P2-BUG-071-error-in-login-flow.md
- .issues/features/P1-FEAT-042-add-dark-mode.md
- .issues/enhancements/P3-ENH-089-improve-performance.md

## NEXT STEPS
- Review changes in each file
- Run `/ll:ready-issue --all` to validate all issues
- Run `/ll:commit` to commit changes
================================================================================
```

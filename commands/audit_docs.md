---
description: Audit documentation for accuracy and completeness
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Write
  - Bash(git:*)
arguments:
  - name: scope
    description: Audit scope (full|readme|file:<path>)
    required: false
  - name: fix
    description: Auto-apply fixable corrections without prompting
    required: false
---

# Audit Docs

You are tasked with auditing project documentation for accuracy, completeness, and consistency with the codebase.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Source directory**: `{{config.project.src_dir}}`

## Audit Scopes

- **full**: Audit all documentation files
- **readme**: Focus on README.md and linked docs
- **file:<path>**: Audit specific documentation file

## Process

### 1. Find Documentation Files

```bash
SCOPE="${scope:-readme}"

case "$SCOPE" in
    full)
        # Find all markdown files
        find . -name "*.md" -not -path "./.git/*" -not -path "./node_modules/*"
        ;;
    readme)
        # Start with README, follow links
        echo "README.md"
        ;;
    file:*)
        # Specific file
        echo "${SCOPE#file:}"
        ;;
esac
```

### 2. Audit Each Document

For each documentation file, check:

#### Accuracy
- [ ] Code examples compile/run
- [ ] File paths exist
- [ ] API references match actual code
- [ ] Version numbers are current
- [ ] Command examples work

#### Completeness
- [ ] All public APIs documented
- [ ] Installation instructions present
- [ ] Usage examples provided
- [ ] Error handling explained
- [ ] Configuration options listed

#### Consistency
- [ ] Terminology is consistent
- [ ] Formatting follows conventions
- [ ] Links are not broken
- [ ] Images are accessible

#### Currency
- [ ] No deprecated information
- [ ] Reflects latest features
- [ ] Version requirements accurate

### 3. Test Code Examples

```bash
# Extract and test code blocks
# For Python:
python -c "[extracted code]"

# For shell:
bash -n <<< "[extracted script]"
```

### 4. Output Report

```markdown
# Documentation Audit Report

## Summary
- **Files audited**: X
- **Issues found**: Y
  - Critical: N
  - Warning: N
  - Info: N

## Results by File

### README.md

| Check | Status | Details |
|-------|--------|---------|
| Code examples | PASS | All examples run |
| File paths | WARN | 2 broken links |
| API refs | PASS | Match codebase |
| Commands | FAIL | Install command outdated |

#### Issues
1. **[CRITICAL]** Line 45: Install command uses deprecated flag
2. **[WARNING]** Line 72: Link to docs/guide.md is broken
3. **[INFO]** Line 100: Consider adding example output

### docs/api.md
[Similar breakdown]

## Recommended Fixes

### Critical (Must Fix)
1. Update install command in README.md:45
   - Old: `pip install old-syntax`
   - New: `pip install new-syntax`

### Warnings (Should Fix)
2. Fix broken link in README.md:72
3. Update version number in docs/install.md

### Suggestions
4. Add example output for commands
5. Include troubleshooting section

## Auto-Fixable Issues
The following can be automatically corrected:
- [ ] Update version numbers
- [ ] Fix relative links
- [ ] Format code blocks

Run with `--fix` to apply automatic corrections.
```

### 4.5. Direct Fix Option

After generating the report, classify each finding and offer direct fixes for auto-fixable items.

#### Finding Classification

Classify each finding from the report:

| Category | Criteria | Examples |
|----------|----------|----------|
| **Auto-fixable** | Specific old/new content known, mechanical replacement | Wrong counts, outdated paths, broken relative links, incorrect version numbers, wrong command syntax |
| **Needs issue** | Requires investigation, writing, or design decisions | Missing sections, incomplete docs, content rewrites, new examples needed |

#### Action Selection

**If `--fix` flag is set**: Skip the prompt. Auto-apply all auto-fixable corrections and output progress:

```
Applying auto-fixes...
Fix 1/N: [description] in [file:line]... done
Fix 2/N: [description] in [file:line]... done
...
Applied: X fixes
Remaining: Y findings (need issue tracking)
```

Then proceed to Phase 5 with only the non-fixable findings.

**Otherwise**: Present findings grouped by fixability:

```markdown
## Auto-Fixable Findings (N)

These can be corrected directly:

| # | File:Line | Finding | Fix |
|---|-----------|---------|-----|
| 1 | README.md:45 | Outdated install command | `old-syntax` → `new-syntax` |
| 2 | README.md:72 | Broken relative link | `docs/guide.md` → `docs/user-guide.md` |

## Findings Needing Issues (M)

These require investigation or design:

| # | File:Line | Finding | Suggested Issue Type |
|---|-----------|---------|---------------------|
| 3 | README.md:100 | Missing example output | ENH (P4) |
| 4 | docs/api.md:30 | Incomplete API docs | ENH (P3) |
```

Use the AskUserQuestion tool with single-select:
- Question: "How would you like to handle the auto-fixable findings?"
- Header: "Doc fixes"
- Options:
  - label: "Fix all now"
    description: "Apply all N auto-fixable corrections directly to the documentation files"
  - label: "Create issues for all"
    description: "Skip direct fixes — create issues for all findings (auto-fixable and non-fixable)"
  - label: "Review each"
    description: "Decide per-finding whether to fix now, create issue, or skip"

If there are no auto-fixable findings, skip this phase and proceed directly to Phase 5 with all findings.

#### Fix All Now

For each auto-fixable finding:
1. Apply the edit using the Edit tool (old_string → new_string)
2. Report: `Fixed: [description] in [file:line]`

After all fixes applied:
```bash
git add [fixed files]
```

Output:
```
Direct fixes applied: N
- [file:line]: [description]
- [file:line]: [description]

Files staged. Run `/ll:commit` to commit, or continue to create issues for remaining findings.
```

Proceed to Phase 5 with only the non-fixable findings (skip issue management entirely if no non-fixable findings remain).

#### Create Issues for All

Skip direct fixes. Proceed to Phase 5 with all findings (both auto-fixable and non-fixable).

#### Review Each

For each auto-fixable finding, use the AskUserQuestion tool with single-select:
- Question: "Finding: [description] in [file:line]. Old: `[old]` → New: `[new]`"
- Header: "[file]:[line]"
- Options:
  - label: "Fix now"
    description: "Apply this correction directly"
  - label: "Create issue"
    description: "Create an issue for this finding instead"
  - label: "Skip"
    description: "Ignore this finding"

Apply fixes for "Fix now" selections, collect "Create issue" selections for Phase 5, discard "Skip" selections.

After review:
```bash
git add [fixed files]
```

Proceed to Phase 5 with findings marked "Create issue" plus all non-fixable findings.

### 5. Issue Management

**Note**: If findings were fixed directly in Phase 4.5, only the remaining unfixed findings are processed in this phase. If all findings were fixed directly, skip to Phase 8's summary output.

After generating the report, offer to create, update, or reopen issues for documentation problems.

#### Finding-to-Issue Mapping

| Finding Severity | Finding Type | Issue Type | Priority |
|-----------------|--------------|------------|----------|
| CRITICAL | Wrong/outdated command | BUG | P1 |
| CRITICAL | Incorrect API reference | BUG | P1 |
| CRITICAL | Broken installation steps | BUG | P1 |
| WARNING | Broken link | BUG | P2 |
| WARNING | Outdated version number | BUG | P2 |
| WARNING | Missing error handling docs | ENH | P3 |
| INFO | Missing example output | ENH | P4 |
| INFO | Could add troubleshooting | ENH | P4 |

**Rule of thumb**:
- **BUG**: Information is *wrong* or *broken* - needs fixing to be accurate
- **ENH**: Information is *missing* or *incomplete* - needs addition to be complete

#### Deduplication

Before creating issues, search for existing issues that cover the same problem:

1. **Search active issues** by file path:
   ```bash
   # Search for issues mentioning the doc file
   grep -r "README.md" .issues/bugs/ .issues/enhancements/
   ```

2. **Search completed issues** for potential reopen:
   ```bash
   # Check if this was previously fixed and regressed
   grep -r "README.md" .issues/completed/
   ```

3. **Match criteria**:
   - Same documentation file
   - Same type of issue (accuracy vs completeness)
   - Similar line numbers or sections

#### Deduplication Actions

| Match Found | Location | Action |
|-------------|----------|--------|
| High confidence match | Active issue | **Update** existing issue with new context |
| High confidence match | Completed | **Reopen** if problem recurred |
| Low/no match | - | **Create** new issue |

#### Issue File Format

```markdown
---
discovered_commit: [GIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [ISO_TIMESTAMP]
discovered_by: audit_docs
doc_file: [path/to/doc.md]
---

# [BUG|ENH]-XXX: [Title describing doc issue]

## Summary

Documentation issue found by `/ll:audit_docs`.

## Location

- **File**: `README.md`
- **Line(s)**: 45
- **Section**: Installation

## Current Content

```markdown
pip install old-package --deprecated-flag
```

## Problem

The install command uses a deprecated flag that no longer works.

## Expected Content

```markdown
pip install new-package
```

## Impact

- **Severity**: High (blocks new user setup)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug|enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: [DATE] | Priority: P1
```

### 6. Reopen Logic

If a completed issue matches a new finding:

1. **Verify it's the same problem**:
   - Same doc file
   - Same section or similar content
   - Problem has actually recurred (not just similar wording)

2. **Move from completed to active**:
   ```bash
   git mv .issues/completed/P2-BUG-XXX-broken-link.md .issues/bugs/
   ```

3. **Append Reopened section**:
   ```markdown
   ---

   ## Reopened

   - **Date**: [TODAY]
   - **By**: audit_docs
   - **Reason**: Documentation issue recurred

   ### New Findings

   The same broken link issue was found again at README.md:72.
   This may indicate the fix was incomplete or regressed.
   ```

### 7. User Approval

Present a summary before making any changes:

```markdown
## Proposed Issue Changes

Based on documentation audit findings:

### New Issues to Create (N)

| Type | Priority | Title | File:Line |
|------|----------|-------|-----------|
| BUG | P1 | Outdated install command | README.md:45 |
| BUG | P2 | Broken link to guide.md | README.md:72 |
| ENH | P4 | Add example output for CLI | README.md:100 |

### Existing Issues to Update (N)

| Issue | Update Reason |
|-------|---------------|
| BUG-023 | Found additional broken link in same file |

### Completed Issues to Reopen (N)

| Issue | Reopen Reason |
|-------|---------------|
| BUG-015 | Link broken again after previous fix |

---

```

Use the AskUserQuestion tool with single-select:
- Question: "Proceed with issue changes?"
- Options:
  - "Create all" - Create/update/reopen all listed issues
  - "Skip" - Keep report only, no issue changes
  - "Select items" - Choose specific items to process

Wait for user selection before modifying any files.

### 8. Execute Issue Changes

After approval:

1. **Create new issues** in appropriate directories
2. **Update existing issues** by appending audit results section
3. **Reopen completed issues** by moving and appending Reopened section
4. **Stage changes**:
   ```bash
   git add .issues/
   ```
5. **Output summary**:
   ```
   Audit complete:
   - Fixed directly: N findings
   - Created: N issues (N BUG, N ENH)
   - Updated: N issues
   - Reopened: N issues
   - Skipped: N findings

   Run `/ll:commit` to commit these changes.
   ```

---

## Arguments

$ARGUMENTS

- **scope** (optional, default: `readme`): What to audit
  - `full` - All documentation
  - `readme` - README and linked docs
  - `file:<path>` - Specific file

- **--fix** (optional, flag): Automatically apply all auto-fixable corrections without prompting. Skips the action selection prompt for fixable items and applies them directly. Non-fixable findings still flow to issue management.

---

## Examples

```bash
# Audit README and linked docs
/ll:audit_docs

# Full documentation audit
/ll:audit_docs full

# Audit specific file
/ll:audit_docs file:docs/api.md

# Auto-fix documentation issues
/ll:audit_docs --fix

# Full audit with auto-fix
/ll:audit_docs full --fix
```

---

## Integration

After auditing:
1. Review the audit report
2. **Fix directly** auto-fixable issues (counts, paths, links) or create issues
3. **Manage issues** (create/update/reopen) for remaining findings with user approval
4. Use `/ll:commit` to save all changes (direct fixes + issue files)

Works well with:
- `/ll:scan_codebase` - May find related code issues
- `/ll:verify_issues` - Validate existing doc-related issues
- `/ll:manage_issue` - Process created documentation issues

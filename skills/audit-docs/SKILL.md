---
description: Audit documentation for accuracy and completeness
argument-hint: "[scope]"
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

Generate a comprehensive audit report using the format defined in [templates.md](templates.md) (see "Audit Report Format" section).

### 4.5. Direct Fix Option

After generating the report, classify each finding and offer direct fixes for auto-fixable items.

#### Finding Classification

Classify each finding from the report using the classification table in [templates.md](templates.md):

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

**Otherwise**: Present findings grouped by fixability using the format in [templates.md](templates.md) (see "Auto-Fixable Findings Format" section).

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

Use the mapping table defined in [templates.md](templates.md) (see "Finding-to-Issue Mapping" section).

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

Use the issue file template defined in [templates.md](templates.md) (see "Issue File Template" section).

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

3. **Append Reopened section** using the template in [templates.md](templates.md) (see "Reopened Section Template").

### 7. User Approval

Present a summary before making any changes using the format in [templates.md](templates.md) (see "Proposed Issue Changes Format" section).

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
/ll:audit-docs

# Full documentation audit
/ll:audit-docs full

# Audit specific file
/ll:audit-docs file:docs/api.md

# Auto-fix documentation issues
/ll:audit-docs --fix

# Full audit with auto-fix
/ll:audit-docs full --fix
```

---

## Integration

After auditing:
1. Review the audit report
2. **Fix directly** auto-fixable issues (counts, paths, links) or create issues
3. **Manage issues** (create/update/reopen) for remaining findings with user approval
4. Use `/ll:commit` to save all changes (direct fixes + issue files)

Works well with:
- `/ll:scan-codebase` - May find related code issues
- `/ll:verify-issues` - Validate existing doc-related issues
- `/ll:manage-issue` - Process created documentation issues

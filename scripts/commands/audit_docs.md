---
description: Audit documentation for accuracy and completeness
arguments:
  - name: scope
    description: Audit scope (full|readme|file:<path>)
    required: false
---

# Audit Docs

You are tasked with auditing project documentation for accuracy, completeness, and consistency with the codebase.

## Configuration

This command uses project configuration from `.claude/cl-config.json`:
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

---

## Arguments

$ARGUMENTS

- **scope** (optional, default: `readme`): What to audit
  - `full` - All documentation
  - `readme` - README and linked docs
  - `file:<path>` - Specific file

---

## Examples

```bash
# Audit README and linked docs
/ll:audit_docs

# Full documentation audit
/ll:audit_docs full

# Audit specific file
/ll:audit_docs file:docs/api.md
```

---

## Integration

After auditing:
- Fix critical issues immediately
- Create enhancement issues for major updates
- Use `/ll:commit` to save documentation fixes

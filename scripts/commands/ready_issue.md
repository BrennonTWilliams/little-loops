---
description: Analyze and validate an issue file for accuracy, utility, and completeness, then auto-correct to make implementation-ready
arguments:
  - name: issue_id
    description: Issue ID to validate (e.g., BUG-004, FEAT-001)
    required: false
---

# Ready Issue

You are tasked with analyzing an issue file to determine if it's ready for implementation and auto-correcting any issues found.

## Configuration

This command uses project configuration from `.claude/cl-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`

## Process

### 1. Find Issue File

```bash
ISSUE_ID="${issue_id}"

# Search for issue file across categories
for dir in {{config.issues.base_dir}}/*/; do
    if [ -d "$dir" ]; then
        FILE=$(ls "$dir"*"$ISSUE_ID"*.md 2>/dev/null | head -1)
        if [ -n "$FILE" ]; then
            echo "Found: $FILE"
            break
        fi
    fi
done
```

### 2. Validate Issue Content

Check for completeness:

#### Required Sections
- [ ] Summary/description
- [ ] Current behavior (for bugs)
- [ ] Expected behavior
- [ ] Reproduction steps (for bugs)
- [ ] Proposed solution/approach

#### Code References
- [ ] File paths exist in codebase
- [ ] Line numbers are accurate
- [ ] Code snippets match current code

#### Metadata
- [ ] Priority prefix in filename
- [ ] Issue ID format correct
- [ ] Labels section present
- [ ] Status section present

### 3. Determine Verdict

| Verdict | Meaning | Action |
|---------|---------|--------|
| READY | Issue is complete and accurate | Proceed to implementation |
| NOT_READY | Missing critical information | Auto-correct or reject |
| NEEDS_REVIEW | Minor issues found | Update and proceed |

### 4. Auto-Correction

If issues found, attempt to fix:

1. **Update file paths** if files have moved
2. **Correct line numbers** if code has shifted
3. **Add missing sections** with placeholder text
4. **Update code snippets** to match current code
5. **Add verification notes** documenting changes

### 5. Output Format

```markdown
## VERDICT
[READY|NOT_READY|NEEDS_REVIEW]

## VALIDATION

| Check | Status | Details |
|-------|--------|---------|
| Summary | PASS | Clear description |
| File paths | PASS | All files exist |
| Line numbers | WARN | Updated 3 references |
| Code snippets | PASS | Match current code |
| Priority | PASS | P2 prefix present |
| Sections | PASS | All required present |

## CONCERNS
- [List any issues that couldn't be auto-corrected]
- [Or "None" if all checks pass]

## CORRECTIONS_MADE
- Updated line 42 -> 45 in src/module.py reference
- Added missing ## Expected Behavior section
- Refreshed code snippet on line 20

## READY_FOR
- Implementation: Yes/No
- Automated processing: Yes/No

## NEXT_STEPS
- [Recommended actions if not ready]
```

---

## Arguments

$ARGUMENTS

- **issue_id** (optional): Specific issue ID to validate
  - If provided, validates that specific issue
  - If omitted, finds and validates highest priority issue

---

## Examples

```bash
# Validate specific issue
/br:ready_issue BUG-042

# Validate highest priority issue
/br:ready_issue

# After validation, implement
/br:manage_issue bug fix BUG-042
```

---

## Integration

This command is typically run before `/br:manage_issue` to ensure:
1. Issue is accurate and up-to-date
2. Implementation can proceed smoothly
3. No surprises during development

The automation scripts (`cl-auto`) run this automatically before each issue.

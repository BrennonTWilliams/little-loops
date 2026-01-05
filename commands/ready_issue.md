---
description: Analyze and validate an issue file for accuracy, utility, and completeness, then auto-correct to make implementation-ready or close if invalid
arguments:
  - name: issue_id
    description: Issue ID to validate (e.g., BUG-004, FEAT-001)
    required: false
---

# Ready Issue

You are tasked with analyzing an issue file to determine if it's ready for implementation. You should:
1. Auto-correct any fixable issues
2. Close issues that should not be implemented
3. Only reject issues that truly need manual intervention

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`

## Process

### 1. Find Issue File

```bash
ISSUE_ID="${issue_id}"

# Search for issue file across categories
# Use strict matching: ID must be bounded by delimiters (-, _, .) to avoid
# matching BUG-1 against BUG-10 or ENH-1 against issue-enh-01-...
for dir in {{config.issues.base_dir}}/*/; do
    # Skip completed directory - only search active issue categories
    if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ]; then
        continue
    fi
    if [ -d "$dir" ]; then
        FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
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

### 3. Check for Closure Conditions

**IMPORTANT**: Before returning NOT_READY, check if the issue should be CLOSED instead:

| Condition | Close Reason | Close Status |
|-----------|--------------|--------------|
| Bug behavior no longer exists in code | already_fixed | Closed - Already Fixed |
| Feature/enhancement already implemented | already_fixed | Closed - Already Fixed |
| Referenced files/functions don't exist and can't be found | invalid_ref | Closed - Invalid |
| Issue is too stale/outdated to be relevant | stale | Closed - Invalid |
| Issue is too vague even after attempting to clarify | too_vague | Closed - Invalid |
| Duplicate of another issue | duplicate | Closed - Duplicate |
| Out of scope or rejected requirement | wont_do | Closed - Won't Do |

### 4. Determine Verdict

| Verdict | Meaning | When to Use |
|---------|---------|-------------|
| READY | Issue is complete and accurate | No changes needed |
| CORRECTED | Auto-corrections made, now ready | Fixed issues, proceed to implementation |
| NOT_READY | Cannot auto-correct | Needs manual intervention (use sparingly) |
| CLOSE | Issue should not be implemented | See closure conditions above |

**Priority order**:
1. First, try to auto-correct any issues
2. If issue is invalid/obsolete, use CLOSE
3. Only use NOT_READY if manual intervention is truly required

### 5. Auto-Correction

If issues found, attempt to fix:

1. **Update file paths** if files have moved
2. **Correct line numbers** if code has shifted
3. **Add missing sections** with placeholder text
4. **Update code snippets** to match current code
5. **Add verification notes** documenting changes
6. **Save the corrected issue file** with your changes

After making corrections, use verdict CORRECTED (not READY or NOT_READY).

### 6. Output Format

```markdown
## VERDICT
[READY|CORRECTED|NOT_READY|CLOSE]

## VALIDATED_FILE
[Absolute path to the issue file that was validated, e.g., /path/to/.issues/bugs/P1-BUG-002-description.md]

## CLOSE_REASON
[Only include this section if verdict is CLOSE]
- Reason: already_fixed|invalid_ref|stale|too_vague|duplicate|wont_do
- Evidence: [Specific evidence supporting closure, e.g., "The function foo() was removed in commit abc123" or "Feature X already exists in src/features/x.py"]

## CLOSE_STATUS
[Only include this section if verdict is CLOSE]
Closed - Already Fixed | Closed - Invalid | Closed - Duplicate | Closed - Won't Do

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
- [Or "None" if no corrections needed]

## READY_FOR
- Implementation: Yes/No
- Automated processing: Yes/No

## NEXT_STEPS
- [Recommended actions if not ready]
- [Or "Proceed to implementation" if ready/corrected]
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
/ll:ready_issue BUG-042

# Validate highest priority issue
/ll:ready_issue

# After validation, implement
/ll:manage_issue bug fix BUG-042
```

---

## Integration

This command is typically run before `/ll:manage_issue` to ensure:
1. Issue is accurate and up-to-date
2. Implementation can proceed smoothly
3. No surprises during development

The automation scripts (`ll-auto`, `ll-parallel`) run this automatically before each issue.

### Verdict Handling by Automation

| Verdict | Automation Action |
|---------|-------------------|
| READY | Proceed to implementation |
| CORRECTED | Proceed to implementation (corrections saved) |
| NOT_READY | Mark as failed, skip issue |
| CLOSE | Move to completed directory with closure status |

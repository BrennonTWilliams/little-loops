---
description: Analyze and validate an issue file for accuracy, utility, and completeness, then auto-correct to make implementation-ready or close if invalid
arguments:
  - name: issue_id
    description: Issue ID to validate (e.g., BUG-004, FEAT-001)
    required: false
  - name: flags
    description: "Optional flags: --deep (use sub-agents for comprehensive validation)"
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
ISSUE_INPUT="${issue_id}"

# Detect if input is a file path (contains "/" or ends with ".md")
# This allows ll-auto to retry with explicit paths on ID mismatch
if [[ "$ISSUE_INPUT" == *"/"* ]] || [[ "$ISSUE_INPUT" == *.md ]]; then
    # Input is an explicit file path
    if [ -f "$ISSUE_INPUT" ]; then
        FILE="$ISSUE_INPUT"
        echo "Found: $FILE"
    else
        echo "WARNING: File not found at specified path: $ISSUE_INPUT"
        echo "Falling back to ID search..."
        ISSUE_ID="$ISSUE_INPUT"
    fi
else
    # Input is an issue ID
    ISSUE_ID="$ISSUE_INPUT"
fi

# Only search if FILE not already set (path detection didn't find it)
if [ -z "$FILE" ]; then
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
fi
```

### 1.5 Deep Validation (--deep flag)

When `--deep` flag is specified, use sub-agents for comprehensive validation:

#### Spawn Validation Agents

1. **codebase-locator** - Verify file paths exist
   ```
   Verify the following file paths from issue [ISSUE-ID] exist in the codebase:
   - [List files mentioned in issue]

   Return: EXISTS or NOT_FOUND for each path, with suggested alternatives if not found.
   ```

2. **codebase-analyzer** - Verify code claims
   ```
   Verify the code claims in issue [ISSUE-ID]:
   - Line numbers are accurate
   - Code snippets match current code
   - Described behavior still exists

   Return: MATCH or MISMATCH for each claim, with current state if different.
   ```

#### Compare Issue Claims vs Reality

| Claim in Issue | Verified | Notes |
|----------------|----------|-------|
| File X exists at path | YES/NO | [Current location or "deleted"] |
| Line N contains Y | YES/NO | [Actual content at line N] |
| Bug behavior occurs | YES/NO | [Current behavior observed] |
| Function Z exists | YES/NO | [Renamed to / Removed in commit] |

#### Deep Validation Outcome

If deep validation reveals significant discrepancies:
- Auto-correct where possible (update paths, line numbers)
- Use CLOSE verdict if issue is obsolete (already fixed, invalid refs)
- Include detailed evidence in VALIDATION table

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
- [ ] Line numbers are accurate (or can be corrected using anchor)
- [ ] Code snippets match current code
- [ ] Anchor field present and valid (function/class name exists)

**Using Stable Anchors for Validation**:
If line numbers are outdated but an Anchor field exists:
1. Search for the anchor (function/class name or unique string) in the referenced file
2. Find the current line numbers for that anchor
3. Update line references automatically
4. Note in CORRECTIONS_MADE: `[line_drift] Updated line N -> M using anchor 'function_name'`

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

**IMPORTANT**: The `## VALIDATED_FILE` section is REQUIRED for ALL verdicts (READY, CORRECTED, NOT_READY, and CLOSE). This enables automation to verify the correct file was processed. Never omit this section.

### 6. Output Format

```markdown
## VERDICT
[READY|CORRECTED|NOT_READY|CLOSE]

## VALIDATED_FILE
[REQUIRED for ALL verdicts - Absolute path to the issue file that was validated, e.g., /path/to/.issues/bugs/P1-BUG-002-description.md]

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
- [line_drift] Updated line 42 -> 45 in src/module.py reference using anchor 'process_data'
- [file_moved] Updated path from old/path.py to new/path.py
- [content_fix] Added missing ## Expected Behavior section
- [content_fix] Refreshed code snippet on line 20
- [issue_status] Related issue ENH-042 marked as completed
- [Or "None" if no corrections needed]

**Correction categories**: Use these prefixes for tracking patterns:
- `[line_drift]` - Line numbers changed since scan
- `[file_moved]` - File path changed since scan
- `[content_fix]` - Content accuracy correction (missing sections, wrong info)
- `[issue_status]` - Related issue status updated

## READY_FOR
- Implementation: Yes/No
- Automated processing: Yes/No

## NEXT_STEPS
- [Recommended actions if not ready]
- [Or "Proceed to implementation with: `/ll:manage_issue [issue_type] [action] [ISSUE_ID]`" if ready/corrected]
```

---

## Arguments

$ARGUMENTS

- **issue_id** (optional): Specific issue ID to validate
  - If provided, validates that specific issue
  - If omitted, finds and validates highest priority issue

- **flags** (optional): Modify validation behavior
  - `--deep` - Use sub-agents for comprehensive validation (verifies file paths, line numbers, code snippets against actual codebase)

---

## Examples

```bash
# Validate specific issue (standard validation)
/ll:ready_issue BUG-042

# Validate with deep research (comprehensive verification)
/ll:ready_issue BUG-042 --deep

# Validate highest priority issue
/ll:ready_issue

# Deep validation on highest priority
/ll:ready_issue --deep

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
| CLOSE | Move to `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/` with closure status |

**Note**: The completed directory is a SIBLING to category directories (bugs/, features/, enhancements/), not a subdirectory within them.

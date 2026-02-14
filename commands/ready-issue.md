---
description: Analyze and validate an issue file for accuracy, utility, and completeness, then auto-correct to make implementation-ready or close if invalid
argument-hint: "[issue-id]"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - Bash(git:*)
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

Read `templates/issue-sections.json` v2.0 (relative to the little-loops plugin directory) and verify:
- [ ] All `common_sections` where `required: true` are present and non-empty (Summary, Current Behavior, Expected Behavior, Impact, Labels, Status)
- [ ] For the issue's type (BUG/FEAT/ENH), all `type_sections.[TYPE]` entries where `level: "required"` are present and non-empty
- [ ] Proposed Solution section is present (even if marked TBD)

**Backward Compatibility (v2.0)**:
- Sections marked `deprecated: true` in template are still valid and should be accepted
- Old section names (e.g., "User Story", "Current Pain Point") are supported alongside new names ("Use Case", "Motivation")
- Both old and new formats are considered VALID

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

#### Dependency Status
- [ ] If `## Blocked By` section exists:
  - Check each referenced issue ID
  - If any blocker is still in an active category (bugs/, features/, enhancements/) and NOT in `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/`:
    - Flag as WARNING: "Blocked by [ID] which is still open"
  - If all blockers are in completed/ or don't exist: PASS
- [ ] If `## Blocked By` section is empty or absent: PASS (no blockers)

**Note**: Open blockers are a WARNING, not a failure. The issue can still be marked READY
but the warning should be prominently displayed so the user is aware of open blockers.

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
| Matches completed issue, files modified since fix | regression_likely | Regression - Reopen as Regression |
| Matches completed issue, can't confirm regression | possible_regression | Possible Regression - Needs Review |

### 4. Determine Verdict

| Verdict | Meaning | When to Use |
|---------|---------|-------------|
| READY | Issue is complete and accurate | No changes needed |
| CORRECTED | Auto-corrections made, now ready | Fixed issues, proceed to implementation |
| NOT_READY | Cannot auto-correct | Needs manual intervention (use sparingly) |
| CLOSE | Issue should not be implemented | See closure conditions above |
| REGRESSION_LIKELY | Matches completed issue with evidence | Files modified since original fix |
| POSSIBLE_REGRESSION | Matches completed issue, uncertain | No fix commit or files tracked |

**Priority order**:
1. First, try to auto-correct any issues
2. If issue is invalid/obsolete, use CLOSE
3. If issue matches completed issue, analyze for regression (see Regression Detection below)
4. Only use NOT_READY if manual intervention is truly required

### 4.5 Regression Detection (when matching completed issues)

When an issue appears to match a completed issue, perform regression analysis:

1. **Check for completed issue match**: Search `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/` for similar issues
2. **Extract fix metadata** from matched completed issue's Resolution section:
   - `Fix Commit`: SHA of the commit that fixed the issue
   - `Files Changed`: List of files modified by the fix
3. **Classify the match**:
   | Scenario | Classification | Verdict |
   |----------|----------------|---------|
   | No fix commit tracked | UNVERIFIED | POSSIBLE_REGRESSION |
   | Fix commit not in history | INVALID_FIX | REGRESSION_LIKELY |
   | Files modified AFTER fix | REGRESSION | REGRESSION_LIKELY |
   | Files NOT modified after fix | INVALID_FIX | REGRESSION_LIKELY |

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
[READY|CORRECTED|NOT_READY|CLOSE|REGRESSION_LIKELY|POSSIBLE_REGRESSION]

## VALIDATED_FILE
[REQUIRED for ALL verdicts - Absolute path to the issue file that was validated, e.g., /path/to/.issues/bugs/P1-BUG-002-description.md]

## CLOSE_REASON
[Only include this section if verdict is CLOSE]
- Reason: already_fixed|invalid_ref|stale|too_vague|duplicate|wont_do
- Evidence: [Specific evidence supporting closure, e.g., "The function foo() was removed in commit abc123" or "Feature X already exists in src/features/x.py"]

## CLOSE_STATUS
[Only include this section if verdict is CLOSE]
Closed - Already Fixed | Closed - Invalid | Closed - Duplicate | Closed - Won't Do

## MATCHED_COMPLETED_ISSUE
[Only include this section if verdict is REGRESSION_LIKELY or POSSIBLE_REGRESSION]
- **Issue ID**: [Matched completed issue ID, e.g., BUG-003]
- **Path**: [Path to matched completed issue]
- **Similarity**: [Match score, e.g., 0.85]
- **Matched Terms**: [Terms that triggered the match]

## REGRESSION_EVIDENCE
[Only include this section if verdict is REGRESSION_LIKELY or POSSIBLE_REGRESSION]
- **Classification**: REGRESSION | INVALID_FIX | UNVERIFIED
- **Fix Commit**: [SHA or "Not tracked"]
- **Fix Commit Exists**: Yes | No
- **Files Changed in Fix**: [List of files from original fix]
- **Files Modified Since Fix**: [Files that were changed after the fix]
- **Related Commits**: [Commits that modified the fixed files]
- **Days Since Fix**: [Number of days]

## RECOMMENDED_ACTION
[Only include this section if verdict is REGRESSION_LIKELY or POSSIBLE_REGRESSION]
- For REGRESSION: "Reopen completed issue as regression - fix was broken by later changes"
- For INVALID_FIX: "Reopen completed issue - original fix never resolved the issue"
- For UNVERIFIED: "Cannot determine regression status - recommend manual review"

## REGRESSION_NOTE_TEMPLATE
[Only include this section if verdict is REGRESSION_LIKELY or POSSIBLE_REGRESSION]
```
## Regression

- **Date**: [Today's date]
- **Classification**: [REGRESSION | INVALID_FIX]
- **Original Fix Commit**: [SHA]
- **Files Modified Since Fix**: [List]
- **Related Commits**: [List]

### Evidence
[Description of why this is classified as regression/invalid fix]

### New Findings
[Current manifestation of the issue]
```

## VALIDATION

| Check | Status | Details |
|-------|--------|---------|
| Summary | PASS | Clear description |
| File paths | PASS | All files exist |
| Line numbers | WARN | Updated 3 references |
| Code snippets | PASS | Match current code |
| Priority | PASS | P2 prefix present |
| Sections | PASS | All required present |
| Blockers | PASS/WARN | "All blockers completed" or "Open blockers: FEAT-010, BUG-015" |

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
- [Or "Proceed to implementation with: `/ll:manage-issue [issue_type] [action] [ISSUE_ID]`" if ready/corrected]
- [Or "Reopen completed issue [ISSUE_ID] as regression" if REGRESSION_LIKELY]
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
/ll:ready-issue BUG-042

# Validate with deep research (comprehensive verification)
/ll:ready-issue BUG-042 --deep

# Validate highest priority issue
/ll:ready-issue

# Deep validation on highest priority
/ll:ready-issue --deep

# After validation, implement
/ll:manage-issue bug fix BUG-042
```

---

## Integration

This command is typically run before `/ll:manage-issue` to ensure:
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
| REGRESSION_LIKELY | Reopen completed issue with classification and evidence |
| POSSIBLE_REGRESSION | Flag for manual review, may reopen if confirmed |

**Note**: The completed directory is a SIBLING to category directories (bugs/, features/, enhancements/), not a subdirectory within them.

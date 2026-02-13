---
description: Verify issue files for accuracy, relevance, and completeness by testing claims against actual code
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(git:*)
arguments:
  - name: issue_id
    description: Optional specific issue ID to verify
    required: false
---

# Verify Issues

You are tasked with verifying that issue files accurately describe the current state of the codebase.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Source directory**: `{{config.project.src_dir}}`

## Process

### 1. Find Issues to Verify

```bash
# List all open issues (not in completed/)
find {{config.issues.base_dir}} -name "*.md" -not -path "*/completed/*" | sort
```

### 2. For Each Issue

#### A. Parse Issue Content
- Extract file paths and line numbers mentioned
- Identify code snippets quoted
- Note expected vs. actual behavior claims

#### B. Verify Against Codebase
1. **Check files exist**: Do referenced files still exist?
2. **Verify line numbers**: Has the code moved or changed?
3. **Validate code snippets**: Does quoted code match current code?
4. **Test claims**: Is the described behavior accurate?

#### C. Determine Verdict

| Verdict | Meaning |
|---------|---------|
| VALID | Issue accurately describes current state |
| OUTDATED | Referenced code has changed |
| RESOLVED | Issue appears to be fixed |
| INVALID | Issue description is incorrect |
| NEEDS_UPDATE | Valid but needs clarification |
| REGRESSION_LIKELY | Matches completed issue, files modified since fix |
| POSSIBLE_REGRESSION | Matches completed issue, but can't confirm regression |
| DEP_ISSUES | Dependency references have problems (broken refs, missing backlinks, cycles) |

#### E. Validate Dependency References

For each issue, check dependency integrity:

1. **Blocked By references**: For each ID in `## Blocked By`:
   - Verify the referenced issue exists (in active issues or completed)
   - If in completed: note as "satisfied" (informational, not an error)
   - If missing entirely: flag as BROKEN_REF

2. **Blocks backlinks**: For each ID in `## Blocked By`:
   - Check that the referenced issue has this issue in its `## Blocks` section
   - If missing: flag as MISSING_BACKLINK

3. **Cycle check**: After processing all issues, build a dependency graph and check for cycles

#### D. Regression Detection (for matches to completed issues)

When an issue matches a completed issue, perform regression analysis:

1. **Extract fix metadata** from the completed issue's Resolution section:
   - `Fix Commit`: SHA of the commit that fixed the issue
   - `Files Changed`: List of files modified by the fix

2. **Analyze git history** to classify the match:
   | Scenario | Classification | Meaning |
   |----------|----------------|---------|
   | No fix commit tracked | UNVERIFIED | Can't determine - original fix not recorded |
   | Fix commit not in history | INVALID_FIX | Fix was never merged/deployed |
   | Files modified AFTER fix | REGRESSION | Fix worked, later changes broke it |
   | Files NOT modified after fix | INVALID_FIX | Fix was applied but never actually worked |

3. **Present evidence** including:
   - Original fix commit SHA
   - Files modified since fix
   - Related commits that touched the fixed files
   - Days since original fix

### 3. Request User Approval

Before making any changes, present the verification results to the user:

1. Show the summary table with all verdicts
2. List specific changes that will be made:
   - Issues to update with verification notes
   - Issues to move to `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/`
3. Ask: "Proceed with these changes? (y/n)"
4. Wait for user confirmation before modifying any files

### 4. Update Issue Files

For issues needing updates:
- Add a `## Verification Notes` section
- Document what changed or needs correction
- Update file paths and line numbers if moved

For resolved issues:
- Add resolution note
- Consider moving to `{{config.issues.base_dir}}/completed/`

### 5. Output Report

```markdown
# Issue Verification Report

## Summary
- **Issues checked**: X
- **Valid**: N
- **Outdated**: N
- **Resolved**: N
- **Invalid**: N
- **Needs Update**: N

## Results by Issue

### Valid Issues
| Issue ID | Title | Notes |
|----------|-------|-------|
| BUG-001 | Title | Verified accurate |

### Outdated Issues
| Issue ID | Title | What Changed |
|----------|-------|--------------|
| ENH-002 | Title | File moved to new location |

### Resolved Issues
| Issue ID | Title | Resolution |
|----------|-------|------------|
| BUG-003 | Title | Fixed in commit abc123 |

### Invalid Issues
| Issue ID | Title | Problem |
|----------|-------|---------|
| FEAT-004 | Title | Described behavior is incorrect |

### Needs Update
| Issue ID | Title | Action Needed |
|----------|-------|---------------|
| ENH-005 | Title | Update line numbers |

### Potential Regressions
| Issue ID | Matched Completed | Classification | Evidence |
|----------|-------------------|----------------|----------|
| BUG-006 | BUG-003 | REGRESSION | Files modified after fix: `src/module.py` |
| ENH-007 | ENH-002 | INVALID_FIX | Files unchanged since fix - fix never worked |
| BUG-008 | BUG-001 | UNVERIFIED | No fix commit tracked |

### Dependency Issues
| Issue ID | Problem | Details |
|----------|---------|---------|
| [ID] | BROKEN_REF | References nonexistent [REF-ID] |
| [ID] | MISSING_BACKLINK | Blocked by [REF-ID], but [REF-ID] has no Blocks entry for [ID] |
| [IDs] | CYCLE | Circular dependency detected |

## Recommended Actions
1. Move resolved issues to `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/` (sibling to category dirs)
2. Update outdated issues with current info
3. Remove or archive invalid issues
4. Re-prioritize if needed
5. Review potential regressions - reopen completed issues with proper classification
6. Fix dependency issues - remove broken refs, add missing backlinks, resolve cycles
```

---

## Arguments

$ARGUMENTS

- **issue_id** (optional): Specific issue ID to verify
  - If provided, verifies only that specific issue
  - If omitted, verifies all open issues

---

## Examples

```bash
# Verify all open issues
/ll:verify_issues

# Verify a specific issue
/ll:verify_issues BUG-042

# After verification, process resolved issues
/ll:manage_issue bug fix RESOLVED-ISSUE-ID

# Update issues that need correction
# Then commit: /ll:commit
```

---

## Integration

Works well with:
- `/ll:scan_codebase` - Find new issues after verification
- `/ll:prioritize_issues` - Re-prioritize after verification
- `/ll:manage_issue` - Process verified issues

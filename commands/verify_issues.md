---
description: Verify issue files for accuracy, relevance, and completeness by testing claims against actual code
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

## Recommended Actions
1. Move resolved issues to `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/` (sibling to category dirs)
2. Update outdated issues with current info
3. Remove or archive invalid issues
4. Re-prioritize if needed
```

---

## Examples

```bash
# Verify all open issues
/ll:verify_issues

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

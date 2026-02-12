---
description: Analyze issues and prepend priority levels (P0-P5) to filenames
---

# Prioritize Issues

You are tasked with analyzing issue files and assigning priority prefixes to their filenames.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base directory**: `{{config.issues.base_dir}}`
- **Issue categories**: `{{config.issues.categories}}`
- **Valid priorities**: `{{config.issues.priorities}}`

## Priority Levels

| Priority | Description | Criteria |
|----------|-------------|----------|
| P0 | Critical | Production outages, data loss, security vulnerabilities |
| P1 | High | Major functionality broken, affects many users |
| P2 | Medium | Important improvements, moderate impact |
| P3 | Low | Nice-to-have, minor improvements |
| P4 | Backlog | Future consideration, low urgency |
| P5 | Wishlist | Ideas, long-term vision items |

## Process

### 0. Parse Flags

```bash
AUTO_MODE=false
if [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
```

### 1. Find Unprioritized Issues

```bash
# Find all issue files without priority prefix (exclude completed/)
for dir in {{config.issues.base_dir}}/*/; do
    dirname=$(basename "$dir")
    if [ -d "$dir" ] && [ "$dirname" != "completed" ]; then
        echo "Checking $dir..."
        ls "$dir"*.md 2>/dev/null | while read file; do
            basename=$(basename "$file")
            if [[ ! "$basename" =~ ^P[0-5]- ]]; then
                echo "  Unprioritized: $basename"
            fi
        done
    fi
done
```

### 1.5. Check If All Issues Already Prioritized

After scanning, determine if any unprioritized issues were found:

- If **unprioritized issues were found** → continue to Step 2 (existing flow)
- If **all issues already have `P[0-5]-` prefixes** → proceed to the re-prioritize prompt below

#### Re-prioritize Prompt

**If `AUTO_MODE` is true**: Skip the prompt and proceed directly to Step 2-RE (Re-evaluate all).

**If `AUTO_MODE` is false**: Use the `AskUserQuestion` tool:

```yaml
questions:
  - question: "All active issues are already prioritized. Would you like to re-evaluate priorities based on current context?"
    header: "Re-prioritize"
    multiSelect: false
    options:
      - label: "Re-evaluate all"
        description: "Re-assess priorities for all active issues and update where changed"
      - label: "View current"
        description: "Show current priority distribution and exit"
```

**If "View current"**: Output a summary of the current priority distribution across categories and stop:

```markdown
# Current Priority Distribution

| Priority | Bugs | Features | Enhancements | Total |
|----------|------|----------|--------------|-------|
| P0       | N    | N        | N            | N     |
| P1       | N    | N        | N            | N     |
| P2       | N    | N        | N            | N     |
| P3       | N    | N        | N            | N     |
| P4       | N    | N        | N            | N     |
| P5       | N    | N        | N            | N     |
```

**If "Re-evaluate all"**: Continue to Step 2-RE below.

### 2-RE. Re-evaluate All Active Issues

For each active issue file (in `bugs/`, `features/`, `enhancements/` — **not** `completed/`):

1. **Read the file content** to understand:
   - Summary/description
   - Impact and severity
   - Effort required
   - Dependencies

2. **Re-assess priority** using the same criteria as initial prioritization (see Step 2 below), considering:
   - Has the project context changed since the original priority was assigned?
   - Are there new issues that shift relative importance?
   - Has the issue's scope or understanding evolved?

3. **Compare** the re-assessed priority against the current `P[0-5]-` prefix:
   - If priority is **unchanged** → skip (no rename needed)
   - If priority **changed** → record the change for renaming

### 3-RE. Rename Changed Priority Files

For each issue where priority changed:

```bash
# Rename file with updated priority prefix (replace existing P[X]- with P[Y]-)
git mv "{{config.issues.base_dir}}/[category]/P[old]-[rest-of-name].md" \
       "{{config.issues.base_dir}}/[category]/P[new]-[rest-of-name].md"
```

Commit with: `git commit -m "chore(issues): re-prioritize issues"`

### 4-RE. Output Re-prioritize Report

```markdown
# Priority Re-evaluation Report

## Summary
- Issues re-evaluated: X
- Priorities changed: Y
- Priorities unchanged: Z

## Changes

| Category | Issue | Old Priority | New Priority | Reason |
|----------|-------|--------------|--------------|--------|
| bugs | BUG-001-description | P3 | P2 | Increased user impact since initial assessment |
| enhancements | ENH-042-description | P2 | P3 | Lower relative priority after new P1 issues |

## Unchanged
- [N] issues retained their current priority

## Next Steps
1. Review priority changes for accuracy
2. Run `/ll:manage_issue` to process highest priority
```

After outputting the report, **stop here** (do not continue to Step 2).

---

### 2. Analyze Each Issue

For each unprioritized issue:

1. **Read the file content** to understand:
   - Summary/description
   - Impact and severity
   - Effort required
   - Dependencies

2. **Assess priority** based on:
   - **User impact**: How many users affected?
   - **Business impact**: Revenue, reputation, compliance?
   - **Product fields** (if present in frontmatter):
     - `business_value`: high/medium/low from frontmatter
     - `goal_alignment`: Strategic priority connection
     - `persona_impact`: Which users are affected
   - **Technical debt**: Blocking other work?
   - **Effort**: Quick win vs. major undertaking?

3. **Assign priority** using the criteria above

### 3. Rename Files

```bash
# Rename file with priority prefix
git mv "{{config.issues.base_dir}}/[category]/[old-name].md" \
       "{{config.issues.base_dir}}/[category]/P[X]-[old-name].md"
```

### 4. Output Report

```markdown
# Priority Assignment Report

## Summary
- Issues analyzed: X
- P0 (Critical): N
- P1 (High): N
- P2 (Medium): N
- P3 (Low): N
- P4 (Backlog): N
- P5 (Wishlist): N

## Assignments

### Bugs
| Original Name | Priority | Reason |
|---------------|----------|--------|
| issue-name.md | P1 | Major functionality affected |

### Features
| Original Name | Priority | Reason |
|---------------|----------|--------|
| feature-name.md | P3 | Nice-to-have improvement |

### Enhancements
| Original Name | Priority | Reason |
|---------------|----------|--------|
| enhancement-name.md | P2 | Improves user experience |

## Next Steps
1. Review assignments for accuracy
2. Run `/ll:manage_issue` to process highest priority
```

---

## Examples

```bash
# Prioritize all unprioritized issues
/ll:prioritize_issues

# Then manage the highest priority
/ll:manage_issue bug fix
```

---

## Important Notes

- Always use `git mv` to rename files (preserves history)
- Commit the renames: `git commit -m "chore(issues): prioritize issues"`
- When all issues are already prioritized, the command offers to re-evaluate priorities
- Exclude `completed/` directory from both prioritization and re-prioritization scans

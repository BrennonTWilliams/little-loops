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

### 1. Find Unprioritized Issues

```bash
# Find all issue files without priority prefix
for dir in {{config.issues.base_dir}}/*/; do
    if [ -d "$dir" ]; then
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
- Re-evaluate priorities periodically as context changes

---
description: Find and fix issue filenames that lack valid issue IDs (e.g., BUG-001, FEAT-002)
---

# Normalize Issues

You are tasked with finding issue files that lack valid issue IDs and renaming them to follow the standard naming convention.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Valid priorities**: `{{config.issues.priorities}}`

## Problem This Solves

Issue files must follow the naming pattern `P[0-5]-[PREFIX]-[NNN]-[slug].md` where:
- `P[0-5]` is the priority prefix
- `[PREFIX]` is the category prefix (BUG, FEAT, ENH)
- `[NNN]` is a 3-digit sequential ID (e.g., 001, 042)
- `[slug]` is a descriptive slug

Files without valid IDs (like `P0-split-base-builder-god-class.md`) cannot be:
- Referenced by ID in automation scripts (`ll-auto`, `ll-parallel`)
- Tracked by the duplicate ID prevention hook
- Properly associated with their category

## Process

### 1. Scan for Invalid Filenames

```bash
# Find all issue files
for dir in {{config.issues.base_dir}}/*/; do
    if [ -d "$dir" ] && [[ "$dir" != *"/completed/"* ]]; then
        echo "Checking $dir..."
        ls "$dir"*.md 2>/dev/null | while read file; do
            basename=$(basename "$file")
            # Check if filename contains valid ID pattern: PREFIX-NNN
            if ! echo "$basename" | grep -qE '(BUG|FEAT|ENH)-[0-9]{3}'; then
                echo "  INVALID: $basename"
            fi
        done
    fi
done
```

### 2. Determine Category Mapping

Map directories to category prefixes based on configuration:

| Directory | Prefix | Pattern |
|-----------|--------|---------|
| `bugs/` | BUG | `P[X]-BUG-[NNN]-[slug].md` |
| `features/` | FEAT | `P[X]-FEAT-[NNN]-[slug].md` |
| `enhancements/` | ENH | `P[X]-ENH-[NNN]-[slug].md` |

### 3. Find Next Available ID

For each category, find the highest existing ID number:

```bash
# Example for bugs
find {{config.issues.base_dir}} -name "*BUG-*.md" -type f | \
    grep -oE 'BUG-[0-9]{3}' | \
    sort -t'-' -k2 -n | \
    tail -1
```

### 4. Generate New Filenames

For each invalid file:

1. **Extract priority** - If filename starts with `P[0-5]-`, preserve it. Otherwise, default to `P3-` (Medium).

2. **Determine prefix** from directory:
   - `bugs/` → `BUG`
   - `features/` → `FEAT`
   - `enhancements/` → `ENH`

3. **Assign next ID** - Use the next sequential number for that category.

4. **Generate slug** from existing filename:
   - Remove any existing `P[0-5]-` prefix
   - Convert to lowercase
   - Keep alphanumeric and hyphens

### 5. Request User Approval

Before making any changes, present the rename plan:

```markdown
## Normalization Plan

### Issues to Rename

| Current Filename | New Filename | Change |
|------------------|--------------|--------|
| `P0-split-base-builder-god-class.md` | `P0-ENH-004-split-base-builder-god-class.md` | Added ENH-004 |
| `fix-login-bug.md` | `P3-BUG-012-fix-login-bug.md` | Added P3-BUG-012 |

### Summary
- Files to rename: N
- New IDs to assign: BUG: [list], FEAT: [list], ENH: [list]

Proceed with renaming? (y/n)
```

**IMPORTANT**: Wait for user confirmation before proceeding.

### 6. Rename Files

Use `git mv` to preserve history:

```bash
# Rename each file
git mv "{{config.issues.base_dir}}/[dir]/[old-name].md" \
       "{{config.issues.base_dir}}/[dir]/[new-name].md"
```

### 7. Update Internal References (Optional)

Check if any other files reference the old filename and offer to update:

```bash
# Find references to old filename
grep -r "[old-filename]" {{config.issues.base_dir}}/ thoughts/shared/plans/
```

### 8. Output Report

```markdown
# Issue Normalization Report

## Summary
- **Files scanned**: X
- **Invalid filenames found**: Y
- **Files renamed**: Z

## Renames Completed

| Original | New Filename | ID Assigned |
|----------|--------------|-------------|
| `P0-split-base-builder-god-class.md` | `P0-ENH-004-split-base-builder-god-class.md` | ENH-004 |

## ID Ranges Used
- BUG: 012-014
- FEAT: (none)
- ENH: 004-006

## Next Steps
1. Commit the renames: `/ll:commit`
2. Update any external references to these issues
3. Run `/ll:verify_issues` to validate content accuracy
```

---

## Validation Rules

A filename is considered **valid** if it matches:
```regex
^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3}-[a-z0-9-]+\.md$
```

A filename is **invalid** if:
- Missing category prefix (`BUG`, `FEAT`, `ENH`)
- Missing 3-digit ID number
- Has non-standard prefix format

---

## Examples

```bash
# Find and fix all invalid issue filenames
/ll:normalize_issues

# After normalization, verify and commit
/ll:verify_issues
/ll:commit
```

---

## Integration

Works well with:
- `/ll:scan_codebase` - Run normalize after scanning to fix any non-standard filenames
- `/ll:verify_issues` - Run after normalizing to validate content
- `/ll:prioritize_issues` - Normalizes IDs before prioritization handles priorities

## Edge Cases

### Files in completed/ directory
- Skip files in `completed/` - they're historical records
- If needed, can be run with `--include-completed` flag (future enhancement)

### Custom category prefixes
- Respect `{{config.issues.categories}}` for prefix mappings
- Support custom prefixes defined in config

### Conflicting IDs
- If an ID is already taken, use the next available
- Never overwrite or duplicate IDs
